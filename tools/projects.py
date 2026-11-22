#!/usr/bin/env python3
"""One list of connected projects in the managed kit: list, install, remove, migrate.

The list is host state, `<kit>/.ai-factory-state/projects.json` (0600), one entry per project.
Capture routing (the global hook's mapping file) is generated from it, so adding or removing a
project is one standard command and never a registration-scope change. Read-only by default;
every write needs --apply. A write takes the kit lock, backs up every file it may change, writes,
writes the list last and clears its marker; an interrupted write is restored from that backup by
the next write command. No secret values are printed; `list` prints no route or credential paths.
With an archive configuration (`project archive`), install also issues the project's archive
access (grants, credential files, search route and contract, worker) under the operator's
authority and remove revokes it; see tools/project_archive.py. Groups (P2), the update report
(P4) and kit moves (P10) are not done here.
"""
import argparse
from contextlib import contextmanager, nullcontext, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import uuid
sys.dont_write_bytecode = True

HERE = Path(__file__).absolute().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


k = _load('_projects_kit', HERE / 'kit.py')
A = _load('_projects_archive', HERE / 'project_archive.py')

LIST = 'projects.json'
MARKER = 'project-op-pending.json'
BACKUPS = 'project-backups'
KEEP_BACKUPS = 20
CAPTURE_REG = 'capture-registration.json'
INSTRUCTION_REG = 'instruction-registration.json'
BUSY = ('pending.json', 'capture-update-pending.json', 'instruction-update-pending.json')
DISPATCH = 'runtime/storage/deploy/capture-bridge/claude_capture_dispatcher.py'
WRAPPER = 'claude-code-stop-hook.sh'
NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
ROUTE_KEYS = {'source_instance', 'credential_file', 'queue_dir', 'status_file'}
ENTRY_KEYS = {'id', 'name', 'root', 'group', 'capabilities'}
CHANNELS = (None, 'global', 'project-local')
FAULT = None  # tests only: (checkpoint name, exception)


class Blocked(ValueError):
    pass


def checkpoint(name):
    if FAULT and FAULT[0] == name:
        raise FAULT[1]


def connection():
    previous = sys.modules.get('kit'); sys.modules['kit'] = k
    try:
        return _load('_projects_connection', HERE / 'connect-project.py')
    finally:
        if previous is None: del sys.modules['kit']
        else: sys.modules['kit'] = previous


def dispatcher(root):
    path = HERE.parent / DISPATCH
    if not path.exists(): path = Path(root) / DISPATCH
    if not path.exists(): raise Blocked('capture dispatcher is not installed')
    return _load('_projects_dispatch', path)


def strict(raw):
    def pairs(items):
        d = {}
        for key, value in items:
            if key in d: raise ValueError('duplicate key')
            d[key] = value
        return d
    return json.loads(raw, object_pairs_hook=pairs)


def private_json(path):
    raw = k.regular(path)
    if raw is None: return None
    s = path.stat()
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise Blocked(f'{path.name} must be private (0600) and owned')
    return strict(raw)


def canonical_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise Blocked('project id must be a canonical UUID')
    return value


def validate(doc):
    if not isinstance(doc, dict) or set(doc) != {'schema', 'projects', 'routes'} or doc['schema'] != 1:
        raise Blocked('unsupported project list')
    if not isinstance(doc['projects'], list) or not isinstance(doc['routes'], dict):
        raise Blocked('invalid project list')
    ids, roots, names = set(), set(), set()
    for e in doc['projects']:
        if not isinstance(e, dict) or not ENTRY_KEYS <= set(e) <= ENTRY_KEYS | {'history', 'archive'}:
            raise Blocked('invalid project entry')
        if 'archive' in e:
            rec = A.check_record(e['archive'])
            if ('capture' in rec['principals']) != (e['capabilities']['capture'].get('channel') == 'global'):
                raise Blocked('archive record and capture capability disagree')
        canonical_uuid(e['id'])
        if not isinstance(e['name'], str) or not NAME.fullmatch(e['name']): raise Blocked('invalid project name')
        if not isinstance(e['root'], str) or not Path(e['root']).is_absolute(): raise Blocked('invalid project root')
        if e['group'] is not None and (not isinstance(e['group'], str) or not NAME.fullmatch(e['group'])):
            raise Blocked('invalid group')
        cap = e['capabilities']
        if (not isinstance(cap, dict) or set(cap) != {'capture'} or not isinstance(cap['capture'], dict)
                or set(cap['capture']) != {'enabled', 'channel'} or type(cap['capture']['enabled']) is not bool
                or cap['capture']['channel'] not in CHANNELS
                or cap['capture']['enabled'] != (cap['capture']['channel'] is not None)):
            raise Blocked('invalid capabilities')
        if e['id'] in ids or e['root'] in roots or e['name'] in names: raise Blocked('duplicate project entry')
        ids.add(e['id']); roots.add(e['root']); names.add(e['name'])
        routed = cap['capture']['channel'] == 'global'
        if routed != (e['id'] in doc['routes']): raise Blocked('capture route and capability disagree')
    for ident, route in doc['routes'].items():
        if ident not in ids or not isinstance(route, dict) or set(route) != ROUTE_KEYS:
            raise Blocked('invalid capture route')
    return doc


def load(root):
    doc = private_json(root / k.STATE / LIST)
    return None if doc is None else validate(doc)


def empty():
    return {'schema': 1, 'projects': [], 'routes': {}}


def encode(doc):
    return k.encode(validate(doc))


def capture_context(root):
    """Mapping location from the registered global capture, or None when capture is absent."""
    reg = private_json(root / k.STATE / CAPTURE_REG)
    if reg is None: return None
    spec = reg['spec']
    return {'mapping': k.absolute(spec['mapping_path']), 'registration_root': k.absolute(spec['registration_root']),
            'rows': spec['projects']}


def mapping_rows(doc):
    return [{'root': e['root'], 'project': e['id'], **doc['routes'][e['id']]}
            for e in doc['projects'] if e['capabilities']['capture']['channel'] == 'global']


def mapping_bytes(doc):
    # Same encoding as tools/connect-capture.py, so migrated rows regenerate byte-identically.
    return k.encode({'schema': 1, 'projects': mapping_rows(doc)})


def git(path, *args):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    r = subprocess.run(['/usr/bin/git', '-C', str(path), 'rev-parse', *args], env=env,
                       capture_output=True, text=True, timeout=10)
    return r.stdout.rstrip('\n') if r.returncode == 0 else None


def checkout_root(value):
    """An existing main checkout root, canonical, not a linked worktree."""
    p = k.absolute(value)
    if str(p.resolve()) != str(p) or not p.is_dir(): raise Blocked('project must be an existing canonical directory')
    if git(p, '--show-toplevel') != str(p): raise Blocked('project is not a Git checkout root')
    common = git(p, '--path-format=absolute', '--git-common-dir')
    if common is None or Path(common) != p / '.git': raise Blocked('project is a linked worktree; install its main checkout')
    return p


def busy(root):
    state = root / k.STATE
    for name in BUSY:
        if (state / name).exists(): raise Blocked('a kit update is unfinished; finish or roll it back first')


def find(doc, root=None, ident=None):
    for e in doc['projects']:
        if (root is not None and e['root'] == str(root)) or (ident is not None and e['id'] == ident):
            return e
    return None


def public_entry(e):
    """An entry without private paths: the archive record shows only as the search capability."""
    out = json.loads(json.dumps({key: e[key] for key in ('id', 'name', 'root', 'group', 'capabilities')}))
    rec = e.get('archive')
    out['capabilities']['search'] = {'enabled': rec is not None, 'alias': rec['alias'] if rec else None}
    if rec: out['archive'] = {'managed_by_kit': True, 'principals': sorted(rec['principals'].values()),
                              'worker': rec['worker']}
    return out | ({'history': e['history']} if 'history' in e else {})


# --- one write: lock, backups, marker, writes, list last ---------------------------------

def restore(root):
    """Restore an interrupted write from its backup. Returns the op id, or None."""
    state = root / k.STATE
    marker = private_json(state / MARKER)
    if marker is None: return None
    op = marker.get('op')
    if not isinstance(op, str) or not re.fullmatch('[a-f0-9]{32}', op): raise Blocked('invalid project op marker')
    bdir = state / BACKUPS / op
    record = private_json(bdir / 'op.json')
    if record is None or record.get('op') != op: raise Blocked('project op backup missing; inspect ' + str(bdir))
    for f in reversed(record['files']):
        path = k.absolute(f['path']); before = f['before']
        if k.signature(path) == before: continue
        if before is None:
            path.unlink()
        else:
            raw = k.regular(bdir / before['sha256'])
            if raw is None or k.digest(raw) != before['sha256']: raise Blocked('corrupt project op backup')
            k.atomic(path, raw, before['mode'])
    (state / MARKER).unlink()
    return op


def prune(state):
    d = state / BACKUPS
    ops = sorted((p for p in d.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for p in ops[:-KEEP_BACKUPS]:
        for child in p.iterdir(): child.unlink()
        p.rmdir()


@contextmanager
def operation(root, ctx):
    with k.lock(root), (k.lock(ctx['registration_root']) if ctx else nullcontext()):
        restored = restore(root)
        busy(root)
        yield restored


def commit(root, command, paths, steps):
    """Back up `paths`, run `steps` in order; any failure restores the backup before re-raising."""
    state = root / k.STATE
    op = uuid.uuid4().hex
    bdir = state / BACKUPS / op
    (state / BACKUPS).mkdir(mode=0o700, exist_ok=True); bdir.mkdir(mode=0o700)
    record = {'op': op, 'command': command, 'files': []}
    for path in paths:
        before = k.signature(path)
        if before is not None:
            k.atomic(bdir / before['sha256'], k.regular(path), 0o600)
        record['files'].append({'path': str(path), 'before': before})
    k.atomic(bdir / 'op.json', k.encode(record))
    k.atomic(state / MARKER, k.encode({'op': op}))
    try:
        for name, step in steps:
            checkpoint('before-' + name)
            step()
        checkpoint('before-clear')
    except Exception:
        restore(root)
        raise
    (state / MARKER).unlink()
    prune(state)
    return op


def guarded(path, data, mode=0o600):
    before = k.signature(path)
    if data is None:
        if before is not None: k.guarded_write(path, before, None, None)
        return
    after = {'sha256': k.digest(data), 'mode': before['mode'] if before else mode}
    if before != after: k.guarded_write(path, before, after, data)


# --- commands -----------------------------------------------------------------------------

def cmd_list(root):
    doc = load(root)
    out = {'status': 'OK', 'projects': [public_entry(e) for e in (doc or empty())['projects']],
           'list': 'present' if doc else 'absent'}
    if (root / k.STATE / MARKER).exists(): out['interrupted'] = 'a project write was interrupted; the next write command restores it'
    return out


def connect(root, project, apply, contract=None):
    """Run the existing connect-project step in-process; returns its report."""
    argv = (['--managed-root', str(root), '--project', str(project)] + (['--apply'] if apply else [])
            + (['--search-contract', str(contract)] if contract else []))
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = connection().main(argv)
    report = json.loads(buf.getvalue())
    if code != 0 or report.get('status') == 'BLOCKED':
        raise Blocked('connect-project: ' + '; '.join(report.get('conflicts') or [report.get('reason', 'blocked')]))
    return report


def check_mapping(root, ctx, doc):
    """The mapping on disk must be exactly what the current list generates (D-3)."""
    if ctx is None: return
    if doc is None:
        raise Blocked('capture is registered but the project list is absent: run `kit.py project migrate` first')
    now = k.regular(ctx['mapping'])
    expected = mapping_bytes(doc) if (now is not None or mapping_rows(doc)) else None
    if now != expected:
        raise Blocked('capture mapping differs from the project list; it was edited outside the kit')


def capture_route(root, doc, name, args):
    rows = list(doc['routes'].values())
    credential = k.absolute(args.capture_credential)
    if args.capture_queue: queue = k.absolute(args.capture_queue)
    elif rows and len({r['queue_dir'] for r in rows}) == 1: queue = Path(rows[0]['queue_dir'])
    else: queue = credential.parent / 'capture-queue'
    if args.capture_status: status = k.absolute(args.capture_status)
    elif rows and len({str(Path(r['status_file']).parent) for r in rows}) == 1:
        status = Path(rows[0]['status_file']).parent / f'global-claude-{name}.status.jsonl'
    else: status = credential.parent / f'global-claude-{name}.status.jsonl'
    source = args.source_instance or f'claude-code-{name}'
    return {'source_instance': source, 'credential_file': str(credential), 'queue_dir': str(queue), 'status_file': str(status)}


def archive_surface(root, cfg, entry, route):
    """Files the kit derives for an archive-managed entry: {path: bytes}. Credentials are not here."""
    rec = entry['archive']
    routes_path = Path(cfg['search_routes'])
    out = {routes_path: A.routes_with(k.regular(routes_path), rec['alias'], A.search_route(cfg, entry['id'], rec)),
           Path(rec['files']['search_contract']): A.contract_bytes(root, rec['alias'])}
    if rec['worker']:
        out[Path(rec['files']['plist'])] = A.plist_bytes(cfg, root, entry['id'], route, rec, entry['name'])
    return out


def install(root, args):
    project = checkout_root(args.project)
    busy(root)
    ctx = capture_context(root)
    cfg = A.load_config(root, private_json)
    before = load(root)
    check_mapping(root, ctx, before)
    doc = json.loads(json.dumps(before or empty()))
    entry = find(doc, root=project)
    new_entry = entry is None
    if args.id: canonical_uuid(args.id)
    if args.name and not NAME.fullmatch(args.name): raise Blocked('invalid --name')
    if entry:
        if args.id and args.id != entry['id']: raise Blocked(f"project is listed as {entry['id']}")
        if args.name and args.name != entry['name']: raise Blocked(f"project is listed as {entry['name']}; renaming is not supported")
    else:
        ident = args.id or str(uuid.uuid4())
        name = args.name or project.name
        if find(doc, ident=ident): raise Blocked('project id is already listed for another root')
        if any(e['name'] == name for e in doc['projects']): raise Blocked(f'name {name} is taken; pass --name')
        entry = {'id': ident, 'name': name, 'root': str(project), 'group': None,
                 'capabilities': {'capture': {'enabled': False, 'channel': None}}}
        doc['projects'].append(entry)
    rec = entry.get('archive')
    enroll = cfg is not None and new_entry and not args.capture_credential
    if rec is not None:
        if cfg is None: raise Blocked('this project has kit-managed archive access but the archive configuration is absent')
        if args.capture_credential or (args.no_capture and 'capture' in rec['principals']):
            raise Blocked('archive access is managed by the kit for this project; remove and install it again to change capture')
    capture = entry['capabilities']['capture']
    server = A.Server(cfg) if cfg is not None and (enroll or rec is not None) else None
    if enroll:
        with_capture = not args.no_capture
        if with_capture and ctx is None: raise Blocked('global capture is not registered in this kit; pass --no-capture')
        files, worker = A.plan_files(cfg, root, entry['id'], entry['name'], with_capture)
        rec = entry['archive'] = A.new_record(entry['id'], entry['name'], files, worker, with_capture)
        if with_capture:
            ns = argparse.Namespace(capture_credential=files['capture_credential'], capture_queue=args.capture_queue,
                                    capture_status=args.capture_status, source_instance=args.source_instance)
            doc['routes'][entry['id']] = capture_route(root, doc, entry['name'], ns)
            capture.update(enabled=True, channel='global')
    elif args.no_capture:
        if capture['channel'] == 'project-local': raise Blocked('captured by a project-local hook; retire it separately')
        capture.update(enabled=False, channel=None); doc['routes'].pop(entry['id'], None)
    elif args.capture_credential:
        if ctx is None: raise Blocked('global capture is not registered in this kit')
        if capture['channel'] == 'project-local': raise Blocked('captured by a project-local hook; converting it is a separate step')
        existing = doc['routes'].get(entry['id'])
        explicit = args.capture_queue or args.capture_status or args.source_instance
        if not (existing and existing['credential_file'] == str(k.absolute(args.capture_credential)) and not explicit):
            doc['routes'][entry['id']] = capture_route(root, doc, entry['name'], args)  # an existing route is kept as is
        capture.update(enabled=True, channel='global')
    elif new_entry and ctx is not None:
        raise Blocked('capture needs an archive configuration (`kit.py project archive`), --capture-credential or --no-capture')
    validate(doc)
    if ctx and mapping_rows(doc) != mapping_rows(before or empty()):
        dispatcher(root).validate_mapping({'schema': 1, 'projects': mapping_rows(doc)})
        route = doc['routes'].get(entry['id'])
        if route and not enroll: dispatcher(root).private_file(route['credential_file'], limit=64 * 1024)
    surface, bootstrap_needed = {}, False
    if rec is not None:
        server.health()
        if enroll:
            taken = [role for role, path in rec['files'].items() if os.path.lexists(path)]
            if taken: raise Blocked('files for this project already exist: ' + ', '.join(sorted(taken)))
            if rec['alias'] in A.routes_doc(k.regular(Path(cfg['search_routes'])))['projects']:
                raise Blocked(f"search route alias {rec['alias']} already exists")
            if rec['worker'] and A.worker_loaded(rec['worker']): raise Blocked(f"worker {rec['worker']} is already loaded")
        else:
            problems = A.probe(server, entry['id'], rec)
            if problems: raise Blocked('; '.join(problems) + ' — no grant is re-issued automatically; remove and install again')
            bootstrap_needed = bool(rec['worker']) and not A.worker_loaded(rec['worker'])
        surface = archive_surface(root, cfg, entry, doc['routes'].get(entry['id']))
    contract = rec['files']['search_contract'] if rec is not None and not enroll else None
    report = connect(root, project, False, contract)
    files = [project / n for n in ('AGENTS.local.md', 'CLAUDE.local.md', '.gitignore')]
    new_list = encode(doc)
    unchanged = (k.regular(root / k.STATE / LIST) == new_list and not bootstrap_needed
                 and all(k.regular(p) == data for p, data in surface.items())
                 and all(a['action'] in ('noop', 'present') for a in report['actions']))
    out = {'status': 'NOOP' if unchanged else 'PLANNED', 'project': public_entry(entry),
           'connection': report['actions'], 'capture_rows': len(mapping_rows(doc))}
    if enroll:
        out['archive'] = {'authority': 'uses the operator secret file named in the archive configuration',
                          'will_issue': sorted(rec['principals'].values()), 'worker': rec['worker'],
                          'files': sorted(rec['files']),
                          'search_contract': 'written on apply and pointed to from the managed block'}
    elif rec is not None:
        out['archive'] = {'grants': 'accepted by the server', 'worker': (
            'bootstrap needed' if bootstrap_needed else ('loaded' if rec['worker'] else 'none'))}
    elif cfg is None:
        out['not_done'] = ['archive access: no archive configuration (`kit.py project archive`)']
    if cfg is not None and rec is not None and cfg['worker']['kind'] == 'none' and 'capture' in rec['principals']:
        out['supervise'] = 'no worker is installed on this OS: supervise `capture_bridge.py --worker` yourself'
    if unchanged or not args.apply:
        if not unchanged: out['status'] = 'PLANNED (dry-run; pass --apply to write)'
        return out
    paths = files + list(surface) + ([ctx['mapping']] if ctx else []) + [root / k.STATE / LIST]
    if enroll: paths = [Path(rec['files'][r]) for r in ('capture_credential', 'search_secret', 'search_epoch')
                        if r in rec['files']] + paths
    with operation(root, ctx) as restored:
        if load(root) != before: raise Blocked('project list changed while planning')
        check_mapping(root, ctx, before)
        steps = [('surface', lambda: [guarded(p, data) for p, data in surface.items()]),
                 ('connect', lambda: connect(root, project, True, rec['files']['search_contract'] if rec else None))]
        if ctx: steps.append(('mapping', lambda: guarded(ctx['mapping'], mapping_bytes(doc))))
        steps.append(('list', lambda: guarded(root / k.STATE / LIST, new_list)))
        if enroll:
            op, minted = enroll_apply(root, server, args, entry, rec, paths, steps)
            out['archive']['project'] = minted
        else:
            op = commit(root, 'install', paths, steps)
    if rec is not None and rec['worker'] and (enroll or bootstrap_needed):
        out['archive']['worker'] = ('started' if A.bootstrap(rec['files']['plist'])
                                    else 'bootstrap failed; files are kept: rerun install to retry')
    return {**out, 'status': 'APPLIED', 'op': op} | ({'restored_first': restored} if restored else {})


def enroll_apply(root, server, args, entry, rec, paths, steps):
    """Server side first (project, consent, grants), then the files in one guarded write.
    Any failure after a grant was issued revokes the issued grants; the file write restores itself."""
    with_capture = 'capture' in rec['principals']
    for role, path in rec['files'].items():
        if os.path.lexists(path): raise Blocked(f'{role} file appeared while planning')
    minted = server.mint(entry['id'], entry['name'], bool(args.id))
    issued = []
    try:
        if with_capture: server.consent(entry['id'])
        writes = []
        if with_capture:
            secret = A.new_secret(); principal = rec['principals']['capture']
            epoch = server.grant(principal, entry['id'], 'capture', secret); issued.append(principal)
            writes.append((rec['files']['capture_credential'], A.credential_bytes(principal, epoch, secret)))
        secret = A.new_secret(); principal = rec['principals']['search']
        epoch = server.grant(principal, entry['id'], 'search', secret); issued.append(principal)
        writes += [(rec['files']['search_secret'], (secret + '\n').encode()),
                   (rec['files']['search_epoch'], f'{epoch}\n'.encode())]
        del secret
        creds = ('credentials', lambda: [guarded(Path(p), data) for p, data in writes])
        op = commit(root, 'install', paths, [creds] + steps)
    except Exception as exc:
        failed = []
        for principal in issued:
            try: server.revoke(principal)
            except Exception: failed.append(principal)
        note = f'archive project {entry["id"]} stays ({minted}, empty unless it was existing)'
        if failed: note += '; STILL LIVE, revoke by hand: ' + ', '.join(failed)
        elif issued: note += '; issued grants were revoked'
        raise Blocked(f'{exc}; files restored; {note}') from exc
    return op, minted


def strip_block(text, begin, end):
    if text is None or begin not in text: return text
    pre, rest = text.split(begin, 1)
    post = rest.split(end, 1)[1]
    post = post[1:] if post.startswith('\n') else post
    pre = pre.rstrip('\n') + '\n' if pre.strip() else ''
    result = pre + post if post.strip() else pre
    return result if result.strip() else None


def remove(root, args):
    busy(root)
    ctx = capture_context(root)
    before = load(root)
    if before is None: raise Blocked('project list is absent')
    check_mapping(root, ctx, before)
    if args.id: canonical_uuid(args.id)
    entry = find(before, root=k.absolute(args.project) if args.project else None, ident=args.id)
    if entry is None: raise Blocked('project is not in the list')
    doc = json.loads(json.dumps(before))
    doc['projects'] = [e for e in doc['projects'] if e['id'] != entry['id']]
    doc['routes'].pop(entry['id'], None)
    validate(doc)
    rec = entry.get('archive')
    cfg = A.load_config(root, private_json) if rec else None
    if rec and cfg is None: raise Blocked('this project has kit-managed archive access but the archive configuration is absent')
    conn = connection()
    project = Path(entry['root'])
    edits = {}
    if project.is_dir():
        for name in ('AGENTS.local.md', 'CLAUDE.local.md'):
            path = project / name
            raw = k.regular(path)
            if raw is None: continue
            text = raw.decode('utf-8'); conn.validate_markers(text)
            new = strip_block(text, conn.BEGIN, conn.END)
            if new != text: edits[path] = None if new is None else new.encode('utf-8')
    credentials = []
    if rec:
        routes_path = Path(cfg['search_routes'])
        routes_raw = k.regular(routes_path)
        if routes_raw is not None and rec['alias'] in A.routes_doc(routes_raw)['projects']:
            edits[routes_path] = A.routes_with(routes_raw, rec['alias'], None)
        for role in ('search_contract', 'plist'):
            path = Path(rec['files'][role]) if role in rec['files'] else None
            if path and k.regular(path) is not None: edits[path] = None
        credentials = [rec['files'][r] for r in ('capture_credential', 'search_secret', 'search_epoch') if r in rec['files']]
    out = {'status': 'PLANNED (dry-run; pass --apply to write)', 'project': public_entry(entry),
           'files': {str(p): ('delete' if d is None else 'remove managed block' if p.name.endswith('.md') and p.parent == project
                              else 'remove route alias' if d is not None else 'delete') for p, d in edits.items()},
           'capture_rows': len(mapping_rows(doc))}
    if rec:
        out['archive'] = {'revoke': sorted(rec['principals'].values()), 'worker': rec['worker'],
                          'delete_credentials': len(credentials)}
        out['kept'] = ['.gitignore entries', 'archive data and capture consent']
    else:
        out['kept'] = ['.gitignore entries', 'archive data, grants and credential files (not managed by the kit for this project)']
    if entry['capabilities']['capture']['channel'] == 'project-local':
        out['kept'].append('project-local capture hook (retire it separately)')
    if not args.apply: return out
    paths = list(edits) + ([ctx['mapping']] if ctx else []) + [root / k.STATE / LIST]
    with operation(root, ctx) as restored:
        if load(root) != before: raise Blocked('project list changed while planning')
        check_mapping(root, ctx, before)
        if rec:
            server = A.Server(cfg)
            server.health()
            revoked = []
            for principal in sorted(rec['principals'].values()):
                try: server.revoke(principal)
                except ValueError as exc:
                    raise Blocked(f'{exc}; nothing else changed' + (f"; already revoked: {', '.join(revoked)}" if revoked else '')) from exc
                revoked.append(principal)
            stranded = 'revoked but not deleted credential files: ' + ', '.join(credentials)
            if rec['worker'] and not A.bootout(rec['worker']):
                raise Blocked(f"stopping worker {rec['worker']} failed; grants are revoked; {stranded}")
        steps = [('files', lambda: [guarded(p, d) for p, d in edits.items()])]
        if ctx: steps.append(('mapping', lambda: guarded(ctx['mapping'], mapping_bytes(doc))))
        steps.append(('list', lambda: guarded(root / k.STATE / LIST, encode(doc))))
        try:
            op = commit(root, 'remove', paths, steps)
        except Exception as exc:
            if rec: raise Blocked(f'{exc}; files restored; grants are revoked; {stranded}') from exc
            raise
        # Credentials of revoked grants are deleted last and never copied into a backup.
        left = []
        for path in credentials:
            try:
                if os.path.lexists(path): os.unlink(path)
            except OSError:
                left.append(path)
        if left: out['stranded'] = 'revoked but not deleted credential files: ' + ', '.join(left)
    return {**out, 'status': 'APPLIED', 'op': op} | ({'restored_first': restored} if restored else {})


def archive(root, args):
    """Write the archive configuration: paths only, never a secret."""
    cfg = A.build_config(root, args)
    path = root / k.STATE / A.CONFIG
    data = k.encode(cfg)
    out = {'status': 'NOOP' if k.regular(path) == data else 'PLANNED (dry-run; pass --apply to write)',
           'config': str(path), 'worker': cfg['worker']['kind'],
           'effect': 'later `project install` runs issue archive grants with the operator secret file named here'}
    if cfg['worker']['kind'] == 'none':
        out['supervise'] = 'no worker will be installed: supervise `capture_bridge.py --worker` yourself'
    if out['status'] == 'NOOP' or not args.apply: return out
    with operation(root, None) as restored:
        op = commit(root, 'archive', [path], [('config', lambda: guarded(path, data))])
    return {**out, 'status': 'APPLIED', 'op': op} | ({'restored_first': restored} if restored else {})


def local_hook_ids(root_path):
    """Capture project ids from a project's own Claude Stop hooks (the managed bridge wrapper)."""
    path = root_path / '.claude/settings.local.json'
    raw = k.regular(path)
    if raw is None: return []
    d = strict(raw)
    found = []
    for group in (d.get('hooks') or {}).get('Stop', []):
        for h in group.get('hooks', []):
            cmd = h.get('command')
            if not isinstance(cmd, str) or WRAPPER not in cmd: continue
            env = dict(t.split('=', 1) for t in shlex.split(cmd) if '=' in t and not t.startswith('/'))
            if 'AF_CAPTURE_PROJECT' in env: found.append(canonical_uuid(env['AF_CAPTURE_PROJECT']))
    return found


def migrate(root, args):
    busy(root)
    if load(root) is not None:
        return {'status': 'NOOP', 'reason': 'project list already exists'}
    ctx = capture_context(root)
    conn = connection()
    doc = empty(); inventory = []; conflicts = []
    by_root = {}

    def add(path, source):
        key = str(Path(path).resolve())
        if key != str(path): conflicts.append(f'{source}: root {path} is not canonical')
        if not Path(key).is_dir(): conflicts.append(f'{source}: root {path} does not exist')
        if key not in by_root:
            by_root[key] = {'id': None, 'name': Path(key).name, 'root': key, 'group': None,
                            'capabilities': {'capture': {'enabled': False, 'channel': None}}}
            doc['projects'].append(by_root[key])
        return by_root[key]

    def bind(e, ident, channel, source):
        if e['id'] not in (None, ident): conflicts.append(f"{source}: root {e['root']} has two ids")
        other = find(doc, ident=ident)
        if other is not None and other is not e: conflicts.append(f'{source}: id {ident} is used by two roots')
        if e['capabilities']['capture']['channel'] not in (None, channel):
            conflicts.append(f"{source}: {e['root']} is captured by two channels")
        e['id'] = ident; e['capabilities']['capture'] = {'enabled': True, 'channel': channel}

    for row in (ctx['rows'] if ctx else []):
        e = add(row['root'], 'capture registration')
        bind(e, canonical_uuid(row['project']), 'global', 'capture registration')
        doc['routes'][row['project']] = {key: row[key] for key in ROUTE_KEYS}
        inventory.append({'source': 'capture registration', 'root': row['root'], 'entry': row['project']})
    for hint in args.include_root:
        add(str(k.absolute(hint)), 'include-root')
    for e in list(doc['projects']):
        p = Path(e['root'])
        if not p.is_dir(): continue
        for ident in local_hook_ids(p):
            bind(e, ident, 'project-local', 'project-local hook')
            inventory.append({'source': 'project-local hook', 'root': e['root'], 'entry': ident})
        agents = k.regular(p / 'AGENTS.local.md')
        if agents is not None and conn.BEGIN in agents.decode('utf-8'):
            inventory.append({'source': 'managed block', 'root': e['root']})
    ins = private_json(root / k.STATE / INSTRUCTION_REG)
    for target in ((ins or {}).get('spec') or {}).get('targets', []):
        if target.get('project'):
            e = by_root.get(str(Path(target['project']).resolve()))
            if e is None:
                conflicts.append(f"instruction registration: {target['project']} is not a listed root; pass --include-root")
                continue
            e['history'] = ['retired-recipe']
            inventory.append({'source': 'instruction registration (retired recipe, untouched)', 'root': e['root']})
    for e in doc['projects']:
        if e['id'] is None: e['id'] = str(uuid.uuid4())
    names = [e['name'] for e in doc['projects']]
    conflicts += [f'name {n} is used by two roots' for n in sorted({n for n in names if names.count(n) > 1})]
    if conflicts:
        return {'status': 'BLOCKED', 'conflicts': conflicts, 'inventory': inventory}
    validate(doc)
    if ctx:
        now = k.regular(ctx['mapping'])
        if now is None or now != mapping_bytes(doc):
            return {'status': 'BLOCKED', 'conflicts': ['the list would not regenerate the current capture mapping byte-for-byte'],
                    'inventory': inventory}
    out = {'status': 'PLANNED (dry-run; pass --apply to write)', 'projects': [public_entry(e) for e in doc['projects']],
           'inventory': inventory, 'writes': [str(root / k.STATE / LIST)],
           'not_inventoried': ['dashboard config (P7)', 'native handoff enrollment (P8)'],
           'rollback': 'delete projects.json; no other file is changed'}
    if not args.apply: return out
    with operation(root, ctx) as restored:
        if load(root) is not None: raise Blocked('project list appeared while planning')
        op = commit(root, 'migrate', [root / k.STATE / LIST],
                    [('list', lambda: guarded(root / k.STATE / LIST, encode(doc)))])
    return {**out, 'status': 'APPLIED', 'op': op} | ({'restored_first': restored} if restored else {})


def main(argv=None):
    ap = argparse.ArgumentParser(prog='kit.py project', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('list', 'install', 'remove', 'migrate', 'archive'):
        p = sub.add_parser(name); p.add_argument('--root', required=True, help='installed kit root')
        if name != 'list': p.add_argument('--apply', action='store_true', help='write (default: dry-run plan)')
        if name == 'install':
            p.add_argument('--project', required=True, help='main checkout root of the project')
            p.add_argument('--name'); p.add_argument('--id', help='existing archive project UUID')
            c = p.add_mutually_exclusive_group()
            c.add_argument('--capture-credential', help='existing private capture credential file for this project')
            c.add_argument('--no-capture', action='store_true')
            p.add_argument('--capture-queue'); p.add_argument('--capture-status'); p.add_argument('--source-instance')
        if name == 'remove':
            w = p.add_mutually_exclusive_group(required=True)
            w.add_argument('--project'); w.add_argument('--id')
        if name == 'archive':
            p.add_argument('--endpoint', help=f'loopback archive endpoint (default {A.ENDPOINT})')
            p.add_argument('--operator-secret-file', required=True, help='private operator secret file (read by install/remove only)')
            p.add_argument('--capture-dir', required=True, help='private directory for capture credential files')
            p.add_argument('--search-dir', required=True, help='private directory for search credential files')
            p.add_argument('--search-routes', required=True, help='search-routes.json next to the installed search client')
            p.add_argument('--worker', choices=('launchd', 'none'), help='default: launchd on macOS, else none')
            p.add_argument('--agents-dir', help='LaunchAgents directory'); p.add_argument('--log-dir', help='private worker log directory')
            p.add_argument('--python', help='absolute python3 for the worker')
        if name == 'migrate':
            p.add_argument('--include-root', action='append', default=[],
                           help='another project root to inventory (for example one captured by its own hook)')
    a = ap.parse_args(argv)
    try:
        root = k.safe_root(a.root)
        if not k.current(root)['files']: raise Blocked('no managed kit is installed at --root')
        restored = None
        if a.command != 'list' and (root / k.STATE / MARKER).exists():
            # An interrupted write is restored before anything is planned against its partial state.
            if not a.apply: raise Blocked('a project write was interrupted; rerun with --apply to restore it first')
            ctx = capture_context(root)
            with k.lock(root), (k.lock(ctx['registration_root']) if ctx else nullcontext()):
                restored = restore(root)
        out = {'list': cmd_list, 'install': install, 'remove': remove, 'migrate': migrate, 'archive': archive}[a.command](
            *((root,) if a.command == 'list' else (root, a)))
        if restored: out['restored_first'] = restored
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        out = {'status': 'BLOCKED', 'reason': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if out['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    sys.exit(main())
