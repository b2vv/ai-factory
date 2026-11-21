#!/usr/bin/env python3
"""Explicit scoped review evidence. No dispatch, test execution or repository writes."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MAX_FILE = 1_000_000
MAX_TOTAL = 8_000_000


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(path):
    p = Path(path).absolute()
    for q in (p, *p.parents):
        if q.is_symlink():
            raise ValueError('symlink refused')
    return p


def allowed_name(path):
    parts = Path(path).parts
    if any(x in ('.git', '.aws', '.ssh') or x.startswith('.env') or
           re.search(r'(?i)(credential|secret|token|id_rsa|\.pem$|\.key$)', x) for x in parts):
        raise ValueError('sensitive path refused')
    if Path(path).name in ('settings.json', 'settings.local.json', 'config.toml', '.mcp.json'):
        raise ValueError('configuration values out of scope')


def text_bytes(data):
    if len(data) > MAX_FILE or b'\0' in data:
        raise ValueError('oversized/binary source refused')
    text = data.decode('utf-8')
    if re.search(r'(?i)(bearer\s+\S+|-----BEGIN .*PRIVATE KEY|(?:api[_-]?key|password|secret|token)\s*[=:]\s*[\"\']?[^\s,;\"\']{12,}|sk-[A-Za-z0-9]{20,})', text):
        raise ValueError('possible credential; use sanitized explicit evidence')
    return data


def read(path):
    p = safe(path)
    allowed_name(p)
    if not p.is_file() or p.stat().st_size > MAX_FILE:
        raise ValueError('missing/nonregular/oversized source')
    return text_bytes(p.read_bytes())


def git(root, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
                                   stderr=subprocess.DEVNULL, timeout=10)


def routes(manifest):
    result = []
    for r in manifest.get('routes', []):
        mode = r.get('mode')
        reason = None
        if mode not in ('subagent', 'existing-session'):
            reason = 'ASK: select new subagent or existing separate session before dispatch'
        elif not r.get('owner') or not r.get('authorization'):
            reason = 'BLOCKED: owner and current assignment/selection evidence required'
        elif mode == 'existing-session' and not r.get('reference'):
            reason = 'BLOCKED: exact existing session reference required; do not guess'
        result.append(dict(r, status='BLOCKED' if reason else 'SELECTED', next=reason))
    if not result:
        result = [{'purpose': 'review', 'mode': 'unspecified', 'status': 'BLOCKED',
                   'next': 'ASK: select route; inventory/planning may continue'}]
    return result


def scoped_path(root, rel):
    p = Path(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('scope requires literal relative file paths')
    allowed_name(p)
    return safe(Path(root) / p)


def collect(manifest):
    root = str(safe(manifest['root']))
    actual = git(root, 'rev-parse', '--show-toplevel').decode().strip()
    if actual != root:
        raise ValueError('exact repository root required')
    base = git(root, 'rev-parse', '--verify', manifest['base'] + '^{commit}').decode().strip()
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    branch = git(root, 'branch', '--show-current').decode().strip()
    if not manifest.get('task_id') or not manifest.get('author_session'):
        raise ValueError('task_id and author_session required')
    scope = manifest['scope']
    if not scope or len(scope) != len(set(scope)) or len(scope) > 100:
        raise ValueError('explicit unique nonempty file scope required (max 100)')
    blobs = {}
    def keep(data):
        data = text_bytes(data)
        h = digest(data)
        blobs[h] = data
        if sum(map(len, blobs.values())) > MAX_TOTAL:
            raise ValueError('package exceeds 8 MB; narrow scope')
        return h
    files = {}
    patches = []
    for rel in sorted(scope):
        p = scoped_path(root, rel)
        current = read(p) if p.exists() else None
        spec = base + ':' + rel
        try:
            size = int(git(root, 'cat-file', '-s', spec))
            if size > MAX_FILE:
                raise ValueError('base file too large')
            before = text_bytes(git(root, 'show', spec))
        except subprocess.CalledProcessError:
            before = None
        if current is None and before is None:
            raise ValueError('scope file absent both at base and working tree')
        index_spec = ':' + rel
        try:
            index_size = int(git(root, 'cat-file', '-s', index_spec))
            if index_size > MAX_FILE:
                raise ValueError('index file too large')
            indexed = text_bytes(git(root, 'show', index_spec))
        except subprocess.CalledProcessError:
            indexed = None
        status = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--', ':(literal)' + rel).decode()
        files[rel] = {'base': keep(before) if before is not None else None,
                      'current': keep(current) if current is not None else None,
                      'index': keep(indexed) if indexed is not None else None,
                      'mode': (p.stat().st_mode & 0o777) if current is not None else None, 'status': status}
        chunk = difflib.unified_diff((before or b'').decode().splitlines(True),
                                          (current or b'').decode().splitlines(True),
                                          fromfile='base/' + rel, tofile='working/' + rel)
        for line in chunk:
            patches.append(line if line.endswith('\n') else line + '\n' + chr(92) + ' No newline at end of file\n')
    references = {}
    for kind in ('acceptance', 'contracts'):
        refs = manifest.get(kind, [])
        if kind == 'acceptance' and not refs:
            raise ValueError('at least one immutable acceptance source required')
        references[kind] = [{'path': str(safe(p)), 'sha256': keep(read(p))} for p in refs]
    evidence = []
    for e in manifest.get('evidence', []):
        item = {k: e.get(k) for k in ('name', 'command', 'exit_code', 'status', 'limitation')}
        if item['status'] not in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED', 'N/A'):
            raise ValueError('explicit evidence status required')
        if item['status'] == 'PASS' and (not item['command'] or item['exit_code'] != 0 or not e.get('artifact')):
            raise ValueError('PASS evidence requires command, exit 0, artifact')
        if e.get('artifact'):
            item.update(path=str(safe(e['artifact'])), sha256=keep(read(e['artifact'])))
        evidence.append(item)
    data = {'schema': 1, 'task_id': manifest['task_id'], 'author_session': manifest['author_session'],
            'root': root, 'base': base, 'head': head, 'branch': branch, 'scope': files,
            'references': references, 'evidence': evidence, 'routes': routes(manifest),
            'constraints': manifest.get('constraints', []),
            'required_checks': manifest.get('required_checks', []), 'diff': keep(''.join(patches).encode())}
    if git(root, 'rev-parse', 'HEAD').decode().strip() != head:
        raise ValueError('concurrent HEAD change')
    return data, blobs


def capture(manifest, destination):
    # Double collection detects ordinary concurrent source/reference/untracked edits.
    data, blobs = collect(manifest)
    again, _ = collect(manifest)
    if data != again:
        raise ValueError('concurrent edits: no review package published')
    package_id = digest(encoded(data))
    dest = safe(destination)
    dest.mkdir(parents=True, exist_ok=True)
    target = safe(dest / package_id)
    if target.exists():
        load(target)
        return target, 'NOOP'
    temp = Path(tempfile.mkdtemp(prefix='.review-', dir=dest))
    try:
        (temp / 'objects').mkdir()
        for h, content in blobs.items():
            p = temp / 'objects' / h
            p.write_bytes(content)
            p.chmod(0o600)
        (temp / 'package.json').write_bytes(encoded({'id': package_id, 'data': data}))
        (temp / 'package.json').chmod(0o600)
        # Same-id concurrent publication is safe; never replace a different package.
        try:
            temp.rename(target)
        except OSError:
            if not target.exists():
                raise
            load(target)
        return target, 'CREATED'
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def load(path):
    path = safe(path)
    obj = json.loads((safe(path / 'package.json')).read_bytes())
    data = obj['data']
    if obj['id'] != digest(encoded(data)):
        raise ValueError('package metadata changed')
    hashes = {data['diff']}
    for f in data['scope'].values():
        hashes.update(h for h in (f['base'], f['current'], f['index']) if h)
    for refs in data['references'].values():
        hashes.update(r['sha256'] for r in refs)
    hashes.update(e['sha256'] for e in data['evidence'] if e.get('sha256'))
    for h in hashes:
        if not re.fullmatch(r'[a-f0-9]{64}', h):
            raise ValueError('invalid object hash')
        if digest(safe(path / 'objects' / h).read_bytes()) != h:
            raise ValueError('package object changed')
    return obj


def fresh(package):
    d = package['data']
    manifest = {'root': d['root'], 'base': d['base'], 'task_id': d['task_id'],
                'author_session': d['author_session'], 'scope': list(d['scope']),
                'acceptance': [r['path'] for r in d['references']['acceptance']],
                'contracts': [r['path'] for r in d['references']['contracts']],
                'routes': [{k:v for k,v in r.items() if k not in ('status','next')} for r in d['routes']],
                'constraints': d['constraints'], 'required_checks': d['required_checks'],
                'evidence': [dict(e, artifact=e.get('path')) for e in d['evidence']]}
    current, _ = collect(manifest)
    return current == d


def assess(package_path, response=None):
    pkg = load(package_path)
    if not fresh(pkg):
        return {'status': 'BLOCKED', 'reason': 'STALE snapshot; capture final delta'}
    if any(r['status'] != 'SELECTED' for r in pkg['data']['routes']):
        return {'status': 'BLOCKED', 'reason': 'route unresolved; do not dispatch'}
    if not response:
        return {'status': 'BLOCKED', 'review': 'NOT_TESTED', 'reason': 'missing reviewer response'}
    d = pkg['data']
    if response.get('package_id') != pkg['id'] or not response.get('reviewer_reference') or response['reviewer_reference'] == d['author_session']:
        return {'status': 'BLOCKED', 'reason': 'wrong snapshot or no independent reviewer identity'}
    selected = [r for r in d['routes'] if r.get('purpose') == 'review']
    if not selected or any(r.get('reference') and r['reference'] != response['reviewer_reference'] for r in selected):
        return {'status': 'BLOCKED', 'reason': 'reviewer does not match selected route'}
    if response.get('completion') != 'complete' or not set(d['scope']).issubset(set(response.get('inspected', []))):
        return {'status': 'BLOCKED', 'reason': 'incomplete response/scope inspection'}
    for f in response.get('findings', []):
        if not all(k in f for k in ('file', 'line', 'impact', 'verification', 'blocking')):
            return {'status': 'BLOCKED', 'reason': 'finding lacks location/impact/verification'}
    checks = {c.get('name'): c for c in response.get('checks', [])}
    for name in d['required_checks']:
        c = checks.get(name, {})
        if c.get('status') == 'PASS' and (not c.get('command') or c.get('exit_code') != 0):
            return {'status': 'BLOCKED', 'reason': 'PASS check lacks command/exit 0: ' + name}
        if c.get('status') not in ('PASS', 'N/A') or not c.get('evidence') or (c['status'] == 'N/A' and not c.get('reason')):
            return {'status': 'BLOCKED', 'reason': 'missing required check evidence: ' + name}
    verdict = response.get('verdict')
    if verdict not in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED'):
        return {'status': 'BLOCKED', 'reason': 'no explicit verdict'}
    if verdict == 'PASS' and any(f['blocking'] for f in response.get('findings', [])):
        return {'status': 'BLOCKED', 'reason': 'PASS conflicts with blocking findings'}
    return {'status': verdict, 'package_id': pkg['id'],
            'limitation': 'structural freshness/declarations checked; independence and evidence validity require reviewer/operator judgment'}


def delta(old_path, new_path):
    old, new = load(old_path), load(new_path)
    a, b = old['data'], new['data']
    if a['root'] != b['root'] or a['task_id'] != b['task_id']:
        raise ValueError('delta requires same task and root')
    changed = sorted(p for p in set(a['scope']) | set(b['scope']) if a['scope'].get(p) != b['scope'].get(p))
    return {'old': old['id'], 'new': new['id'], 'changed_files': changed,
            'references_changed': a['references'] != b['references'],
            'base_changed': a['base'] != b['base'], 'head_changed': a['head'] != b['head'],
            'action': 'NOOP' if old['id'] == new['id'] else 'FINAL_DELTA_REVIEW_REQUIRED',
            'rule': 'Reviewer maps delta to affected criteria/checks; retain only explicitly unaffected evidence. No automatic stale PASS or blanket rerun.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('capture'); c.add_argument('manifest'); c.add_argument('destination')
    c = sub.add_parser('assess'); c.add_argument('package'); c.add_argument('--response')
    c = sub.add_parser('delta'); c.add_argument('old'); c.add_argument('new')
    c = sub.add_parser('route'); c.add_argument('manifest')
    a = p.parse_args()
    try:
        if a.command == 'capture':
            path, status = capture(json.loads(read(a.manifest)), a.destination)
            out = {'status': status, 'package': str(path)}
        elif a.command == 'route':
            out = routes(json.loads(read(a.manifest)))
        elif a.command == 'delta':
            out = delta(a.old, a.new)
        else:
            response = json.loads(read(a.response)) if a.response else None
            out = assess(a.package, response)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as e:
        print(json.dumps({'status': 'BLOCKED', 'reason': type(e).__name__ + ': explicit input/snapshot unavailable or invalid'}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
