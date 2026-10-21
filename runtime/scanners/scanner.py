#!/usr/bin/env python3
"""Explicit, fail-closed local scanners. Stdlib only; importing/validating never calls Docker."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
EXIT = {'CLEAN': 0, 'FINDINGS': 1, 'ERROR': 2, 'BLOCKED': 3}
SHA = re.compile(r'^[a-f0-9]{64}$')
PIN = re.compile(r'^[a-z0-9][a-z0-9./_-]*@sha256:[a-f0-9]{64}$')
SOURCE_EXT = {'.js', '.jsx', '.ts', '.tsx', '.py'}
MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024
SAFE_IMAGE_ENV = {'PATH', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                  'PYTHONPATH', 'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE'}


class Blocked(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Blocked(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def canonical(value, exists=True):
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and not any(c in str(p) for c in '$,\n\r'),
         'explicit absolute path without interpolation required')
    for q in (p, *p.parents):
        need(not q.is_symlink(), 'symlink path refused')
    need(p.resolve() == p, 'noncanonical path refused')
    need(not exists or p.exists(), 'required path missing')
    return p


def regular(p, limit=None):
    p = canonical(p)
    s = p.stat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular non-hardlinked file required')
    need(limit is None or s.st_size <= limit, 'input too large')
    return p


def read_json(p):
    return json.loads(regular(p, MAX_FILE).read_text())


def write_json(p, obj):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def disjoint(*paths):
    for i, p in enumerate(paths):
        for q in paths[i + 1:]:
            need(p != q and p not in q.parents and q not in p.parents, 'paths overlap')


def timestamp(value):
    try:
        v = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        need(v.tzinfo is not None, 'timezone required')
        return v
    except (ValueError, TypeError, AttributeError):
        raise Blocked('invalid DB timestamp')


def load_manifest(path=HERE / 'manifest.json'):
    m = read_json(path)
    need(m.get('schema_version') == 1, 'unsupported scanner manifest')
    for name in ('semgrep', 'trivy'):
        e = m['engines'][name]
        need(isinstance(e.get('image'), str) and PIN.fullmatch(e['image']), name + ': reviewed digest pin missing')
        need(e.get('version') and e.get('platform') in ('linux/arm64', 'linux/amd64'), name + ': version/platform missing')
        need(e.get('provenance_review') == 'ACCEPTED' and e.get('review_evidence') and
             e.get('license_review') == 'ACCEPTED', name + ': provenance/license review missing')
    need(m['rules']['review'] == 'ACCEPTED', 'rules review missing')
    need(m['db']['license_review'] == 'ACCEPTED' and m['db'].get('review_evidence'), 'DB terms review missing')
    need(isinstance(m['db']['schema'], int) and m['db']['schema'] > 0, 'DB schema missing')
    need(isinstance(m['db']['max_age_hours'], int) and 0 < m['db']['max_age_hours'] <= 168,
         'invalid DB freshness limit')
    return m


def rules_files(m, rules_dir=None):
    root = canonical(rules_dir if rules_dir is not None else HERE / 'rules')
    need(root.is_dir(), 'rules root must be directory')
    files = m['rules']['files']
    need(isinstance(files, dict) and 0 < len(files) <= 2000, 'explicit bounded rules allowlist required')
    total = 0
    for n, h in files.items():
        need(isinstance(n, str), 'invalid rule path')
        rel = Path(n)
        need(not rel.is_absolute() and str(rel) == n and '..' not in rel.parts and
             all(not part.startswith('.') for part in rel.parts), 'unsafe rule relative path')
        need(n == 'baseline.json' or (len(rel.parts) > 1 and rel.parts[0] == 'semgrep-rules' and
             rel.suffix in {'.yaml', '.yml', '.json'}), 'unexpected rules closure')
        p = regular(root / rel, MAX_FILE)
        total += p.stat().st_size
        need(total <= MAX_TOTAL and isinstance(h, str) and SHA.fullmatch(h) and sha(p) == h,
             'rules hash/size mismatch')
    return files


def stage_rules(m, destination):
    for n, h in rules_files(m).items():
        dst = destination / n
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((HERE / 'rules' / n).read_bytes())
        need(sha(dst) == h, 'rules changed during staging')
        dst.chmod(0o444)


def source_files(config):
    need(config.get('schema_version') == 1 and config.get('sanitized_inputs_reviewed') is True,
         'explicit sanitized input review required')
    root = canonical(config['root'])
    need(root.is_dir(), 'source root must be directory')
    selected = config['files']
    need(isinstance(selected, dict) and 0 < len(selected) <= 2000, 'explicit bounded file allowlist required')
    total = 0
    for n, expected in selected.items():
        p = Path(n)
        need(not p.is_absolute() and str(p) == n and '..' not in p.parts and
             all(not part.startswith('.') for part in p.parts), 'unsafe selected relative path')
        need(not re.search(r'(?i)(secret|credential|token|private[ _-]?key)', n), 'sensitive filename refused')
        need(p.suffix in SOURCE_EXT or p.name in ('package.json', 'yarn.lock'), 'unsupported input kind')
        f = regular(root / p, MAX_FILE)
        total += f.stat().st_size
        need(total <= MAX_TOTAL and SHA.fullmatch(expected) and sha(f) == expected,
             'source snapshot hash/size mismatch')
        # Conservative rejection, not a universal secret detector. Owner review is also mandatory.
        data = f.read_bytes()
        need(not re.search(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:ghp_|github_pat_|AKIA)[A-Za-z0-9]{16,}', data),
             'possible credential in selected input')
    need(any(Path(n).suffix in SOURCE_EXT for n in selected), 'source coverage empty')
    locks = [n for n in selected if Path(n).name == 'yarn.lock']
    need(locks, 'baseline dependency coverage requires yarn.lock')
    for n in locks:
        parent = str(Path(n).with_name('package.json'))
        need(parent in selected, 'yarn.lock requires paired package.json')
        p = read_json(root / parent)
        need(isinstance(p.get('devDependencies'), dict) and p['devDependencies'],
             'baseline requires explicit dev dependency coverage')
    return root, selected, locks


def store_root(value):
    root = canonical(value)
    need(root.is_dir() and read_json(root / 'owner.json') == {'owner': 'AI Factory', 'schema_version': 1},
         'Factory-owned DB storage required')
    need(not any((p / '.git').exists() for p in (root, *root.parents)), 'DB storage must be outside Git')
    return root


def validate_snapshot(store, snapshot, m, now=None):
    store = store_root(store)
    need(isinstance(snapshot, str) and SHA.fullmatch(snapshot), 'explicit content-addressed snapshot required')
    base = canonical(store / snapshot)
    need(base.is_dir(), 'snapshot missing')
    meta = read_json(base / 'snapshot.json')
    need(meta.get('schema_version') == 1 and meta.get('engine_image') == m['engines']['trivy']['image'],
         'snapshot engine mismatch')
    need(meta.get('db_source') == m['db']['repository'] and PIN.fullmatch(meta['db_source']), 'DB provenance mismatch')
    expected = meta.get('files', {})
    need(set(expected) == {'db/trivy.db', 'db/metadata.json'}, 'invalid DB snapshot closure')
    actual = set()
    for p in base.rglob('*'):
        canonical(p)
        need(p.is_dir() or p.is_file(), 'nonregular snapshot entry')
        need(not p.stat().st_mode & 0o222, 'snapshot is writable')
        if p.is_file():
            regular(p)
            actual.add(str(p.relative_to(base)))
    need(actual == set(expected) | {'snapshot.json'}, 'unexpected snapshot file')
    need(not base.stat().st_mode & 0o222, 'snapshot directory is writable')
    for n, h in expected.items():
        need(SHA.fullmatch(h) and sha(base / n) == h, 'DB snapshot hash mismatch')
    identity = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    need(identity == snapshot, 'snapshot identity mismatch')
    db = read_json(base / 'db/metadata.json')
    need(db.get('Version') == m['db']['schema'], 'DB schema incompatible')
    now = now or dt.datetime.now(dt.timezone.utc)
    updated, next_update = timestamp(db['UpdatedAt']), timestamp(db['NextUpdate'])
    age = (now - updated).total_seconds()
    need(0 <= age <= m['db']['max_age_hours'] * 3600 and updated < next_update and now < next_update,
         'DB stale or timestamp in future')
    return base, meta


def prepare(config, m):
    root, selected, locks = source_files(config)
    reports = canonical(config['reports'], exists=False)
    need(not reports.exists() and reports.parent.is_dir(), 'fresh reports directory with existing parent required')
    store = store_root(config['db_store'])
    disjoint(root, reports, store, HERE.parent.parent)
    db, snapshot = validate_snapshot(store, config['db_snapshot'], m)
    rules_files(m)
    return root, reports, db, selected, locks, snapshot


def render(m, source, rules, db, reports):
    doc = read_json(HERE / 'compose.yaml')
    for name, s in doc['services'].items():
        s['image'] = m['engines'][name]['image']
        s['platform'] = m['engines'][name]['platform']
        s['user'] = str(os.getuid()) + ':' + str(os.getgid())
        bindings = [(source, '/src', True), (reports, '/reports', False)]
        bindings += [(rules, '/rules', True)] if name == 'semgrep' else [(db, '/cache', True)]
        s['volumes'] = [{'type': 'bind', 'source': str(p), 'target': target,
                         'read_only': ro, 'bind': {'create_host_path': False}} for p, target, ro in bindings]
    return doc


def verify_tmpfs(tmpfs):
    """Validate inspect scratch options, accepting reordered flags and byte/unit sizes."""
    need(isinstance(tmpfs, dict) and set(tmpfs) == {'/tmp'}, 'unexpected scratch mounts')
    value = tmpfs['/tmp']
    need(isinstance(value, str), 'invalid scratch options')
    options = [part.strip() for part in value.split(',')]
    flags = set(); size = None
    for option in options:
        if option.startswith('size='):
            need(size is None, 'duplicate scratch size')
            match = re.fullmatch(r'size=([0-9]+)([kKmMgG]?)', option)
            need(match is not None, 'invalid scratch size')
            size = int(match[1]) * (1024 ** {'': 0, 'k': 1, 'm': 2, 'g': 3}[match[2].lower()])
        else:
            need(option in {'rw', 'noexec', 'nosuid', 'nodev'} and option not in flags,
                 'unsafe or duplicate scratch option')
            flags.add(option)
    need({'rw', 'noexec', 'nosuid'} <= flags and size is not None and 0 < size <= 256 * 1024 * 1024,
         'scratch must be noexec/nosuid and bounded to 256 MiB')


def verify_container(obj, service, image_id):
    h, c = obj['HostConfig'], obj['Config']
    need(obj['Image'] == image_id and c['Image'] == service['image'], 'actual image mismatch')
    need(h['NetworkMode'] == 'none' and h['ReadonlyRootfs'] and not h.get('Privileged'), 'unsafe actual isolation')
    need(set(x.upper() for x in h.get('CapDrop', [])) == {'ALL'} and not h.get('CapAdd') and
         any(v in h.get('SecurityOpt', []) for v in ('no-new-privileges:true', 'no-new-privileges')), 'unsafe actual privileges')
    need(not h.get('Devices') and not h.get('DeviceRequests') and not h.get('VolumesFrom') and
         not h.get('PortBindings') and not h.get('PidMode') and not h.get('IpcMode', '').startswith(('host', 'container:')),
         'unexpected host sharing')
    need(c['User'] == service['user'] and c['Entrypoint'] == service['entrypoint'] and
         c['Cmd'] == service['command'] and c['WorkingDir'] == '/src', 'actual process mismatch')
    env = dict(x.split('=', 1) for x in c.get('Env', []))
    need(all(env.get(k) == v for k, v in service['environment'].items()) and
         set(env) <= set(service['environment']) | SAFE_IMAGE_ENV, 'unexpected container environment')
    expected = {(str(canonical(v['source'])), v['target'], not v['read_only']) for v in service['volumes']}
    mounts = obj.get('Mounts', [])
    binds = [v for v in mounts if v['Type'] == 'bind']
    need(len(binds) == len(expected) and
         {(str(canonical(v['Source'])), v['Destination'], v['RW']) for v in binds} == expected,
         'actual bind mounts differ from approved resolved paths')
    need(all(v['Type'] == 'bind' or (v['Type'] == 'tmpfs' and v['Destination'] == '/tmp') for v in mounts),
         'unexpected volume mount')
    verify_tmpfs(h.get('Tmpfs'))


def classify(name, report, code, selected, root):
    if code != 0 or not isinstance(report, dict):
        return 'ERROR'
    if name == 'semgrep':
        if not isinstance(report.get('results'), list) or report.get('errors') != []:
            return 'ERROR'
        scanned = report.get('paths', {}).get('scanned', [])
        required = {n for n in selected if Path(n).suffix in SOURCE_EXT}
        normalized = {p.removeprefix('/src/').removeprefix('./') for p in scanned}
        if not required <= normalized:
            return 'ERROR'
        return 'FINDINGS' if report['results'] else 'CLEAN'
    if type(report.get('SchemaVersion')) is not int or report['SchemaVersion'] != 2 or not isinstance(report.get('Results'), list):
        return 'ERROR'
    results = report['Results']
    def text_field(obj, key):
        return isinstance(obj.get(key), str) and bool(obj[key].strip())
    for result in results:
        if not isinstance(result, dict) or not all(text_field(result, k) for k in ('Target', 'Type')):
            return 'ERROR'
        packages = result.get('Packages')
        # This baseline explicitly requests inventory with --list-all-pkgs.
        # Omitted/null inventory is not evidence of a completed dependency scan.
        if not isinstance(packages, list) or any(
                not isinstance(p, dict) or not all(text_field(p, k) for k in ('Name', 'Version'))
                for p in packages):
            return 'ERROR'
        vulnerabilities = result.get('Vulnerabilities')
        # Trivy may omit or emit null for an empty optional vulnerability collection.
        # Only those forms and an actual list are accepted, never falsey {} or "".
        if vulnerabilities is not None and (
                not isinstance(vulnerabilities, list) or any(
                    not isinstance(v, dict) or not all(text_field(v, k) for k in
                                                     ('VulnerabilityID', 'PkgName', 'InstalledVersion'))
                    for v in vulnerabilities)):
            return 'ERROR'
    for lock in (n for n in selected if Path(n).name == 'yarn.lock'):
        matches = [r for r in results if r.get('Target', '').removeprefix('/src/').removeprefix('./') == lock]
        if len(matches) != 1 or matches[0].get('Type') != 'yarn' or not matches[0].get('Packages'):
            return 'ERROR'
        packages = matches[0]['Packages']
        dev = read_json(root / Path(lock).with_name('package.json'))['devDependencies']
        # No zero-findings PASS if any direct dev dependency vanished from scanner inventory.
        if not set(dev) <= {p.get('Name') for p in packages}:
            return 'ERROR'
    return 'FINDINGS' if any(r.get('Vulnerabilities') for r in results) else 'CLEAN'


def docker_call(prefix, args, env, timeout=600):
    return subprocess.run(prefix + args, env=env, capture_output=True, text=True, timeout=timeout, check=False)


def run_scan(config, m, socket):
    root, reports, db, selected, locks, snapshot = prepare(config, m)
    need(str(socket).startswith('/'), 'explicit local Docker socket required')
    # No Docker call happens before all validation. Never pull or build.
    reports.mkdir(mode=0o700)
    outcome = {'status': 'ERROR', 'runtime_acceptance': 'NOT_ESTABLISHED', 'engines': {},
               'input_hashes': selected, 'manifest_sha256': sha(HERE / 'manifest.json'),
               'snapshot': snapshot, 'image_pins': {k: v['image'] for k, v in m['engines'].items()}}
    with tempfile.TemporaryDirectory(prefix='factory-scan-') as temp:
        work = Path(temp).resolve()
        source, rules = work / 'source', work / 'rules'
        source.mkdir(); rules.mkdir(); (work / 'home').mkdir()
        for n, h in selected.items():
            src = regular(root / n, MAX_FILE)
            need(sha(src) == h, 'source changed before staging')
            dst = source / n; dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes()); need(sha(dst) == h, 'source changed during staging'); dst.chmod(0o444)
        stage_rules(m, rules)
        doc = render(m, source, rules, db, reports)
        compose = work / 'compose.json'; write_json(compose, doc)
        write_json(reports / 'resolved-compose.json', doc)
        project = 'factory-scan-' + uuid.uuid4().hex
        env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(work / 'home'),
               'DOCKER_CONFIG': str(work / 'home'), 'COMPOSE_DISABLE_ENV_FILE': '1'}
        prefix = ['docker', '--host', 'unix://' + str(socket)]
        cp = ['compose', '--project-name', project, '--project-directory', str(work), '-f', str(compose)]
        created = False
        try:
            images = {}
            for name, service in doc['services'].items():
                r = docker_call(prefix, ['image', 'inspect', service['image']], env)
                need(r.returncode == 0, 'pinned image not available locally')
                image = json.loads(r.stdout)[0]
                need(service['image'] in image.get('RepoDigests', []), 'local image digest mismatch')
                need(image['Os'] + '/' + image['Architecture'] == service['platform'], 'local image platform mismatch')
                images[name] = image['Id']
            created = True  # cleanup also on partial create
            r = docker_call(prefix, cp + ['create', '--pull', 'never', '--no-build'], env)
            need(r.returncode == 0, 'container creation failed')
            for name, service in doc['services'].items():
                r = docker_call(prefix, cp + ['ps', '--all', '--quiet', name], env)
                ids = r.stdout.split()
                need(r.returncode == 0 and len(ids) == 1 and re.fullmatch('[a-f0-9]{12,64}', ids[0]), 'container identity missing')
                cid = ids[0]
                r = docker_call(prefix, ['inspect', cid], env)
                need(r.returncode == 0, 'container inspect failed')
                obj = json.loads(r.stdout)[0]
                verify_container(obj, service, images[name])
                write_json(reports / (name + '-inspect.json'), obj)
                validate_snapshot(config['db_store'], config['db_snapshot'], m)
                r = docker_call(prefix, ['start', '--attach', cid], env)
                # Attach return code is not trusted as the container exit status.
                exit_result = docker_call(prefix, ['inspect', '--format', '{{json .State}}', cid], env)
                need(exit_result.returncode == 0, 'final state unavailable')
                state = json.loads(exit_result.stdout)
                need(not state['Running'] and not state.get('OOMKilled') and not state.get('Error'), 'container failed')
                report_path = reports / (name + '.json')
                result = classify(name, read_json(report_path), state['ExitCode'], selected, root)
                if r.returncode != 0:
                    result = 'ERROR'
                outcome['engines'][name] = {'status': result, 'exit_code': state['ExitCode'],
                                            'report_sha256': sha(report_path)}
            validate_snapshot(config['db_store'], config['db_snapshot'], m)
            source_files(config)  # detect changes to original snapshot too
            statuses = [e['status'] for e in outcome['engines'].values()]
            outcome['status'] = 'ERROR' if 'ERROR' in statuses else ('FINDINGS' if 'FINDINGS' in statuses else 'CLEAN')
        except Blocked as e:
            outcome.update(status='BLOCKED', reason=str(e))
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            outcome.update(status='ERROR', reason='execution or structured report failure')
        finally:
            if created:
                try:
                    r = docker_call(prefix, cp + ['down', '--timeout', '5'], env)
                    if r.returncode != 0:
                        outcome.update(status='ERROR', reason='scoped container cleanup failed', project=project)
                except (OSError, subprocess.SubprocessError):
                    outcome.update(status='ERROR', reason='scoped cleanup outcome unknown', project=project)
            write_json(reports / 'result.json', outcome)
    return outcome


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['validate', 'scan'])
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--socket', type=Path)
    a = ap.parse_args()
    try:
        config = read_json(canonical(a.config)); m = load_manifest()
        if a.action == 'scan':
            need(a.execute and a.socket, 'scan needs explicit --execute and local --socket')
            result = run_scan(config, m, a.socket)
        else:
            prepare(config, m)
            result = {'status': 'VALIDATED', 'runtime_acceptance': 'NOT_RUN'}
    except Blocked as e:
        result = {'status': 'BLOCKED', 'reason': str(e)}
    except (OSError, ValueError, KeyError, TypeError):
        result = {'status': 'ERROR', 'reason': 'invalid input/configuration'}
    print(json.dumps(result, indent=2))
    return EXIT.get(result['status'], 0)


if __name__ == '__main__':
    raise SystemExit(main())
