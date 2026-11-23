"""Move the installed kit to another directory: `kit.py move --root K --to K2 --package P [--apply]`.

K2 must already hold the same release (`kit.py install --package P --root K2`). The move re-points every file that
names K — the home binding, the global instruction targets, the capture and handoff hooks and their registration
records, the project list and its derived files, every listed project's managed block, the capture worker plists
and the skills links — to K2, then checks each part with its own module (NOOP from K2) and keeps the move only if
all agree; otherwise it restores every file. K's payload and records are not changed; rollback
(`kit.py move --root K2 --rollback`) restores the exact bytes every file had before the move.

New bytes come from an exact path-boundary replacement of K by K2; registration records with integrity envelopes are
rebuilt, never substituted. Codex hooks rewritten here need the owner to trust them again in Codex; dashboard
containers that mount K's dashboard projects file need a restart — both are reported, not done.
"""
import base64
from contextlib import ExitStack, contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
import kit as k  # noqa: E402


MODULES = {}  # sibling modules by file name, loaded once (tests may pre-seed fixture instances)


def _load(name, file):
    if file not in MODULES:
        spec = importlib.util.spec_from_file_location(name, HERE / file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        MODULES[file] = module
    return MODULES[file]


MARKER = 'move-interrupted.json'
RECORDS = 'move-records'
HOME_STATE = '.agents/.ai-factory-instructions'
CARRIED = ('projects.json', 'archive.json', 'dashboard.json', 'handoff.json', 'dashboard-projects.json',
           'capture-registration.json', 'instruction-registration.json')
SPECS = ('capture-registration.json', 'instruction-registration.json')
BUSY = ('pending.json', 'capture-update-pending.json', 'instruction-update-pending.json', 'project-op-pending.json')
SEARCH_ROUTES = 'runtime/storage/deploy/search-client/search-routes.json'
CONTRACTS = 'search-contracts'
SKILL_DIRS = ('.claude/skills', '.agents/skills', '.cursor/skills')
FAULT = None  # tests only: (step name, exception)
LAUNCHCTL = None  # tests only: a recording fake for launchctl


class Blocked(ValueError):
    pass


def checkpoint(name):
    if FAULT and FAULT[0] == name:
        raise FAULT[1]


# --- path-boundary replacement ---------------------------------------------------------------

def boundary(old):
    return re.compile(re.escape(old) + r'(?=[/\'"`\s\]),:;}]|$)')


def swap_text(text, old, new):
    out = boundary(old).sub(lambda _: new, text)
    if boundary(old).search(out):
        raise Blocked('a file still names the old kit after replacement')
    return out


def swap_json(value, old, new):
    if isinstance(value, str):
        return boundary(old).sub(lambda _: new, value)
    if isinstance(value, list):
        return [swap_json(v, old, new) for v in value]
    if isinstance(value, dict):
        return {swap_json(key, old, new): swap_json(v, old, new) for key, v in value.items()}
    return value


def names(raw, old):
    return raw is not None and boundary(old).search(raw.decode('utf-8', 'replace')) is not None


# --- inventory --------------------------------------------------------------------------------

def private_json(path):
    raw = k.regular(path)
    return None if raw is None else json.loads(raw)


def owner_path(home):
    return k.absolute(Path(home) / HOME_STATE / 'owner.json')


def find_home(old, handoff_registration=None, explicit=None):
    """The home bound to K, only as a registration names it (or --home); never guessed from the environment."""
    for name in SPECS:
        reg = private_json(old / k.STATE / name)
        if reg: return k.absolute(reg['spec']['home'])
    if handoff_registration is not None:
        current = k.absolute(handoff_registration) / k.STATE / 'current.json'
        if current.exists(): return k.absolute(k.read_tx(current)['spec']['home'])
    return None if explicit is None else k.absolute(explicit)


class Plan:
    def __init__(self, old, new, home):
        self.old, self.new, self.home = old, new, home
        self.files = {}      # path -> new bytes (None = remove)
        self.modes = {}
        self.links = {}      # link path -> new target
        self.workers = []    # (label, plist)
        self.notes = []
        self.blockers = []
        self.capture = None  # (registration root, new spec)
        self.instruction_spec = None
        self.verify = []
        self.commands = {}
        self.project_status = {}  # project -> status from K before the move   # exact old hook command -> new command, from each owning module

    def put(self, path, data, mode=None):
        path = k.absolute(path)
        if path in self.files and self.files[path] != data:
            raise Blocked(f'two different rewrites planned for {path.name}')
        self.files[path] = data
        sig = k.signature(path)
        self.modes[path] = mode if mode is not None else (sig['mode'] if sig else 0o600)

    def json(self, path):
        """Rewrite a JSON file: exact hook commands first, then any other K path at a boundary."""
        path = k.absolute(path)
        raw = self.files.get(path) if path in self.files else k.regular(path)
        if raw is None: return
        doc = json.loads(raw)
        def walk(v):
            if isinstance(v, str): return self.commands.get(v, v)
            if isinstance(v, list): return [walk(x) for x in v]
            if isinstance(v, dict): return {key: walk(x) for key, x in v.items()}
            return v
        data = k.encode(swap_json(walk(doc), str(self.old), str(self.new)))
        if names(data, str(self.old)): raise Blocked(f'{path.name} still names the old kit')
        if data != raw: self.put(path, data)

    def text(self, path):
        """Rewrite a host text file that names K; untouched when it does not."""
        path = k.absolute(path)
        raw = self.files.get(path) if path in self.files else k.regular(path)
        if raw is None or not names(raw, str(self.old)): return
        self.put(path, swap_text(raw.decode('utf-8'), str(self.old), str(self.new)).encode('utf-8'))


def preconditions(p, package):
    old, new = p.old, p.new
    if old == new or old in new.parents or new in old.parents:
        p.blockers.append('the kits must be two separate directories, neither inside the other')
    for root in (old, new):
        for name in BUSY + (MARKER,):
            if (root / k.STATE / name).exists():
                p.blockers.append(f'{root} has an unfinished operation ({name})')
    a, b = k.current(old), k.current(new)
    if not a['files']: p.blockers.append('no kit is installed at the old root')
    if not b['files']: p.blockers.append('install the same release at the new root first: kit.py install --package P --root K2')
    elif a['files'] != b['files'] or a.get('components') != b.get('components'):
        p.blockers.append('the new root holds a different release or components')
    if package is not None and not p.blockers:
        try:
            planned = k.plan(k.absolute(package), new, b.get('components') or [])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            p.blockers.append('the new root cannot be checked: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
        else:
            if planned['status'] != 'NOOP': p.blockers.append('the package is not the release installed at the new root')
    owner = private_json(owner_path(p.home)) if p.home and owner_path(p.home).exists() else None
    if owner is not None and owner != {'schema': 1, 'root': str(old)}:
        p.blockers.append('the home is bound to another kit: ' + str((owner or {}).get('root')))
    for name in CARRIED:
        if (new / k.STATE / name).exists(): p.blockers.append(f'the new root already has {name}')


def plan_state(p):
    """K's list-level state carried into K2 with K paths rewritten; specs re-sealed."""
    for name in CARRIED:
        doc = private_json(p.old / k.STATE / name)
        if doc is None: continue
        doc = swap_json(doc, str(p.old), str(p.new))
        if name in SPECS: doc['spec_sha256'] = k.digest(k.encode(doc['spec']))
        p.put(p.new / k.STATE / name, k.encode(doc), 0o600)
        if name == 'capture-registration.json': p.capture = (k.absolute(doc['spec']['registration_root']), doc['spec'])
        if name == 'instruction-registration.json': p.instruction_spec = doc['spec']
    contracts = p.old / k.STATE / CONTRACTS
    if contracts.is_dir():
        for f in sorted(contracts.glob('*.md')):
            p.put(p.new / k.STATE / CONTRACTS / f.name,
                  swap_text(k.regular(f).decode('utf-8'), str(p.old), str(p.new)).encode('utf-8'), 0o600)
    routes = p.old / SEARCH_ROUTES
    if routes.exists():
        p.put(p.new / SEARCH_ROUTES, k.regular(routes), k.signature(routes)['mode'])


def plan_home(p):
    if p.home is None:
        p.notes.append('no registration names a home: global files and skills links were not looked at (pass --home)')
        return
    owner = owner_path(p.home)
    if owner.exists(): p.put(owner, k.encode({'schema': 1, 'root': str(p.new)}), 0o600)
    if p.instruction_spec:
        iu = _load('_move_instruction_update', 'instruction_update.py')
        _, targets = iu.validate_spec(k, p.new, p.instruction_spec)
        for _, path in targets: p.text(path)
    for sub in SKILL_DIRS:
        base = p.home / sub
        if not base.is_dir() or base.is_symlink(): continue
        for dirpath, dirnames, filenames in os.walk(base):
            for n in list(dirnames) + filenames:
                link = Path(dirpath) / n
                if not link.is_symlink(): continue
                target = os.readlink(link)
                if target == str(p.old) or target.startswith(str(p.old) + '/'):
                    p.links[link] = str(p.new) + target[len(str(p.old)):]
            dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]


def plan_hooks(p):
    """settings.json and Codex hooks.json, after capture and handoff named their exact commands."""
    if p.home is None: return
    for name in ('.claude/settings.json', '.codex/hooks.json'):
        if (p.home / name).exists(): p.json(p.home / name)
    if k.absolute(p.home / '.codex/hooks.json') in p.files:
        p.notes.append('Codex hooks now name the new kit: trust them again in Codex')


def rebuilt_record(record_path, old, new, binding, files, extra=None):
    """A registration's current record re-sealed for K2: K paths swapped, kit binding and file signatures recomputed."""
    rec = k.read_tx(record_path)
    rec = swap_json(rec, str(old), str(new))
    rec['kit'] = binding
    rec['files'] = files
    rec['id'] = uuid.uuid4().hex
    rec.update(extra or {})
    clean = {key: value for key, value in rec.items() if key != 'integrity'}
    return rec['id'], k.encode({**clean, 'integrity': k.digest(k.encode(clean))})


def receipt(ident, old_ident, old_root):
    tx = {'id': ident, 'status': 'APPLIED', 'plan': {'moved_from': {'root': str(old_root), 'id': old_ident}, 'changes': []},
          'applied': [], 'backups': {}}
    return k.encode({**tx, 'integrity': k.digest(k.encode(tx))})


def planned_signature(p, path):
    path = k.absolute(path)
    if path in p.files:
        data = p.files[path]
        return None if data is None else {'sha256': k.digest(data), 'mode': p.modes[path]}
    return k.signature(path)


def capture_commands(p):
    if not p.capture: return
    cc = _load('_move_connect_capture', 'connect-capture.py')
    old_spec = private_json(p.old / k.STATE / 'capture-registration.json')['spec']
    if cc.current(cc.validate_spec(old_spec)) is None:  # also refuses drift before the move
        raise Blocked('capture is registered but its registration root has no current record')
    p.commands[cc.command(cc.validate_spec(old_spec))] = cc.command(cc.validate_spec(p.capture[1]))


def plan_capture(p):
    if not p.capture: return
    reg, spec = p.capture
    cc = _load('_move_connect_capture', 'connect-capture.py')
    current = reg / k.STATE / 'current.json'
    old_id = k.read_tx(current)['id']
    files = {name: planned_signature(p, name) for name in k.read_tx(current)['files']}
    ident, raw = rebuilt_record(current, p.old, p.new, cc.kit_binding(p.new), files)
    p.put(current, raw, 0o600)
    p.put(reg / k.STATE / 'receipts' / (ident + '.json'), receipt(ident, old_id, p.old), 0o600)
    p.verify.append('capture')


def handoff_commands(p, handoff_registration):
    doc = private_json(p.old / k.STATE / 'handoff.json')
    if doc is None: return None
    if handoff_registration is None:
        p.blockers.append('native handoff is enrolled: pass --handoff-registration <its registration root>')
        return None
    ch = _load('_move_connect_handoff', 'connect-handoff.py')
    hr = k.absolute(handoff_registration)
    rec = k.read_tx(hr / k.STATE / 'current.json')
    if rec['spec']['managed_root'] != str(p.old): raise Blocked('the handoff registration does not belong to the old kit')
    old_paths = ch.validate_spec(rec['spec'])
    ch.current(old_paths)  # refuses drift before the move
    new_spec = swap_json(rec['spec'], str(p.old), str(p.new))
    new_paths = ch.validate_spec(new_spec)
    for host in rec['spec']['hosts']:
        p.commands[ch.command(old_paths, host)] = ch.command(new_paths, host)
    return hr, rec, old_paths, new_paths


def plan_handoff(p, found):
    if not found: return
    hr, rec, old_paths, new_paths = found
    ch = _load('_move_connect_handoff', 'connect-handoff.py')
    current = hr / k.STATE / 'current.json'
    p.json(old_paths['profile_path'])
    if 'legacy' in rec['spec']: p.put(rec['spec']['legacy']['path'], ch.loader(new_paths))
    files = {name: planned_signature(p, name) for name in rec['files']}
    ident, raw = rebuilt_record(current, p.old, p.new, ch.kit_binding(p.new), files)
    p.put(current, raw, 0o600)
    p.put(hr / k.STATE / 'receipts' / (ident + '.json'), receipt(ident, rec['id'], p.old), 0o600)
    p.verify.append(('handoff', hr))


def plan_projects(p):
    doc = private_json(p.old / k.STATE / 'projects.json')
    if doc is None: return
    for entry in doc['projects']:
        p.text(Path(entry['root']) / 'AGENTS.local.md')
        rec = entry.get('archive')
        if rec and rec.get('worker'):
            plist = Path(rec['files']['plist'])
            p.text(plist)
            p.workers.append((rec['worker'], str(plist)))
    dash = private_json(p.old / k.STATE / 'dashboard.json')
    if dash and dash.get('projects', '').startswith(str(p.old) + '/'):
        p.notes.append('dashboard containers read the old kit\'s dashboard projects file: point DASHBOARD_PROJECTS at '
                       f'{p.new}/.ai-factory-state/dashboard-projects.json and restart them')
    P = _load('_move_projects', 'projects.py')
    p.project_status = {r['project']: r['status'] for r in (P.check_projects(p.old) or [])}
    p.verify.append('projects')


def build(old, new, package, handoff_registration=None, home=None):
    old, new = k.safe_root(old), k.safe_root(new)
    p = Plan(old, new, find_home(old, handoff_registration, home))
    preconditions(p, package)
    if p.blockers: return p
    try:
        plan_state(p); plan_home(p)
        capture_commands(p); found = handoff_commands(p, handoff_registration)
        plan_hooks(p); plan_capture(p); plan_handoff(p, found); plan_projects(p)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        p.blockers.append(str(exc) if isinstance(exc, ValueError) else type(exc).__name__ + ' while planning')
    return p


def public(p):
    return {'from': str(p.old), 'to': str(p.new), 'home': None if p.home is None else str(p.home),
            'files': sorted(str(x) for x in p.files), 'links': len(p.links), 'workers': [w for w, _ in p.workers],
            'notes': p.notes}


# --- apply, verify, restore -------------------------------------------------------------------

@contextmanager
def flock(path):
    path = k.absolute(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def locks(stack, p):
    stack.enter_context(k.lock(p.old)); stack.enter_context(k.lock(p.new))
    if p.home and owner_path(p.home).parent.exists(): stack.enter_context(flock(owner_path(p.home).parent / 'lock'))
    for item in p.verify:
        if isinstance(item, tuple): stack.enter_context(k.lock(item[1]))
    if p.capture: stack.enter_context(k.lock(p.capture[0]))


def record_entries(p):
    entries = []
    for path, data in sorted(p.files.items()):
        before = k.signature(path)
        entries.append({'path': str(path), 'before': before, 'bytes': None if before is None else base64.b64encode(k.regular(path)).decode(),
                        'after': None if data is None else {'sha256': k.digest(data), 'mode': p.modes[path]}})
    for link, target in sorted(p.links.items()):
        entries.append({'link': str(link), 'before': os.readlink(link), 'after': target})
    return entries


def write_marker(root, op, p):
    k.atomic(root / k.STATE / MARKER, k.encode({'op': op, 'from': str(p.old), 'to': str(p.new),
                                                'home': None if p.home is None else str(p.home)}))


def set_link(path, target):
    tmp = path.with_name('.kit-move-' + path.name)
    if os.path.lexists(tmp): os.unlink(tmp)
    os.symlink(target, tmp); os.replace(tmp, path)


def restore_entries(entries):
    """Put every entry back to its before state; an entry at neither state is reported, not overwritten."""
    unknown = []
    for e in reversed(entries):
        if 'link' in e:
            link = Path(e['link'])
            now = os.readlink(link) if os.path.islink(link) else None
            if now == e['before']: continue
            if now != e['after']: unknown.append(e['link']); continue
            set_link(link, e['before']); continue
        path = Path(e['path']); now = k.signature(path)
        if now == e['before']: continue
        if now != e['after']: unknown.append(e['path']); continue
        if e['before'] is None: path.unlink()
        else: k.atomic(path, base64.b64decode(e['bytes']), e['before']['mode'])
    return unknown


def reload_workers(workers):
    A = _load('_move_archive', 'project_archive.py')
    if LAUNCHCTL: A.LAUNCHCTL = LAUNCHCTL
    out = []
    for label, plist in workers:
        try: ok = A.bootout(label) and A.bootstrap(plist)
        except OSError: ok = False
        out.append({'worker': label, 'status': 'reloaded' if ok else
                    f'failed: run launchctl bootout gui/$(id -u)/{label}; launchctl bootstrap gui/$(id -u) {plist}'})
    return out


def verify(p, package):
    """Each part checked by its own module from K2; any non-NOOP keeps the move from completing."""
    failed = []
    if p.instruction_spec:
        iu = _load('_move_instruction_update2', 'instruction_update.py')
        r = iu.plan(k, k.absolute(package), p.new, k.current(p.new).get('components') or [])
        if r['status'] != 'NOOP': failed.append('instructions')
    elif p.capture:
        cu = _load('_move_capture_update', 'capture_update.py')
        if cu.plan(k, k.absolute(package), p.new, k.current(p.new).get('components') or [])['status'] != 'NOOP':
            failed.append('capture')
    for item in p.verify:
        if isinstance(item, tuple):
            ch = _load('_move_connect_handoff2', 'connect-handoff.py')
            rec = k.read_tx(item[1] / k.STATE / 'current.json')
            if ch.plan(rec['spec'])['status'] != 'NOOP': failed.append('handoff')
        elif item == 'projects':
            P = _load('_move_projects', 'projects.py')
            after = {r['project']: r['status'] for r in (P.check_projects(p.new) or [])}
            if after != p.project_status: failed.append('projects')  # each project exactly as it was from K
    return failed


def instruction_current(p):
    """K2's instruction lineage starts here; its dependency fingerprint is taken after every other write."""
    if not p.instruction_spec: return None
    iu = _load('_move_instruction_update3', 'instruction_update.py')
    spec = p.capture[1] if p.capture else None
    cur = {'id': uuid.uuid4().hex, 'root': str(p.new), 'parent': None, 'dependencies': iu.fingerprint(k, p.new, spec)}
    return p.new / k.STATE / iu.CURRENT, k.encode(cur)


def apply(old, new, package, handoff_registration=None, home=None):
    p = build(old, new, package, handoff_registration, home)
    if p.blockers: return {'status': 'BLOCKED', 'reason': 'cannot move the kit: ' + '; '.join(p.blockers)}
    op = uuid.uuid4().hex
    with ExitStack() as stack:
        locks(stack, p)
        entries = record_entries(p)
        current = p.new / k.STATE / 'instruction-current.json'
        if p.instruction_spec:
            entries.append({'path': str(current), 'before': None, 'bytes': None, 'after': None})
        record = p.new / k.STATE / RECORDS / (op + '.json')
        k.atomic(record, k.encode({'op': op, 'from': str(p.old), 'to': str(p.new), 'entries': entries, 'workers': p.workers}))
        write_marker(p.old, op, p); write_marker(p.new, op, p)
        try:
            for e in entries:
                if 'path' in e and Path(e['path']).is_relative_to(p.new / k.STATE):
                    for d in reversed(Path(e['path']).relative_to(p.new / k.STATE).parents[:-1]):
                        (p.new / k.STATE / d).mkdir(mode=0o700, exist_ok=True)
                if 'link' in e:
                    checkpoint('link'); set_link(Path(e['link']), e['after']); continue
                path = Path(e['path'])
                if e['after'] is None: continue
                checkpoint(path.name)
                k.guarded_write(path, e['before'], e['after'], p.files[path])
            if p.instruction_spec:
                path, raw = instruction_current(p)
                k.guarded_write(path, None, {'sha256': k.digest(raw), 'mode': 0o600}, raw)
                entries[-1]['after'] = {'sha256': k.digest(raw), 'mode': 0o600}
                k.atomic(record, k.encode({'op': op, 'from': str(p.old), 'to': str(p.new), 'entries': entries, 'workers': p.workers}))
            checkpoint('verify')
            failed = verify(p, package)
            if failed: raise Blocked('the moved kit did not check NOOP: ' + ', '.join(failed))
        except Exception as exc:  # a kill (BaseException) leaves the markers for recover()
            unknown = restore_entries(entries)
            if not unknown:
                (p.new / k.STATE / MARKER).unlink(); (p.old / k.STATE / MARKER).unlink()
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            return {'status': 'BLOCKED', 'reason': 'move failed and was restored: ' + reason,
                    **({'not_restored': unknown} if unknown else {})}
        workers = reload_workers(p.workers)
        (p.new / k.STATE / MARKER).unlink()  # commit point: owner.json names K2 and K2 has no marker
        (p.old / k.STATE / MARKER).unlink()
    return {'status': 'APPLIED', 'op': op, **public(p), 'workers': workers}


def latest_record(root):
    records = sorted((root / k.STATE / RECORDS).glob('*.json'), key=lambda f: f.stat().st_mtime)
    if not records: raise Blocked('no move was made into this root')
    return private_json(records[-1])


def rollback(root):
    root = k.safe_root(root)
    rec = latest_record(root)
    if rec['to'] != str(root): raise Blocked('the last move did not end at this root')
    old = Path(rec['from'])
    with ExitStack() as stack:
        stack.enter_context(k.lock(root)); stack.enter_context(k.lock(old))
        drift = [e.get('path') or e.get('link') for e in rec['entries'] if not at_after(e)]
        if drift: return {'status': 'BLOCKED', 'reason': 'changed since the move, not overwritten: ' + ', '.join(drift)}
        unknown = restore_entries(rec['entries'])
        if unknown: return {'status': 'BLOCKED', 'reason': 'could not restore: ' + ', '.join(unknown)}
        workers = reload_workers([tuple(w) for w in rec['workers']])
        (root / k.STATE / RECORDS / (rec['op'] + '.json')).rename(root / k.STATE / RECORDS / (rec['op'] + '.rolled-back'))
    return {'status': 'ROLLED_BACK', 'op': rec['op'], 'to': rec['from'], 'workers': workers}


def at_after(e):
    if 'link' in e:
        return os.path.islink(e['link']) and os.readlink(e['link']) == e['after']
    return k.signature(Path(e['path'])) == e['after']


def recover(root):
    """An interrupted move: restore from either root, or only drop a stale marker after the commit point."""
    root = k.safe_root(root)
    marker = private_json(root / k.STATE / MARKER)
    if marker is None: return {'status': 'NOOP'}
    old, new = Path(marker['from']), Path(marker['to'])
    rec = private_json(new / k.STATE / RECORDS / (marker['op'] + '.json'))
    home = Path(marker['home']) if marker.get('home') else None
    owner = private_json(owner_path(home)) if home and owner_path(home).exists() else None
    if root == old and not (new / k.STATE / MARKER).exists() and owner == {'schema': 1, 'root': str(new)}:
        (root / k.STATE / MARKER).unlink()
        return {'status': 'STALE_MARKER_REMOVED'}
    unknown = restore_entries(rec['entries']) if rec else []
    if unknown: return {'status': 'BLOCKED', 'reason': 'could not restore: ' + ', '.join(unknown)}
    for r in (new, old):
        if (r / k.STATE / MARKER).exists(): (r / k.STATE / MARKER).unlink()
    return {'status': 'RESTORED', 'op': marker['op']}


def interrupted(root):
    return (Path(root) / k.STATE / MARKER).exists()


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='kit.py move')
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--to', type=Path)
    ap.add_argument('--package', type=Path)
    ap.add_argument('--handoff-registration', type=Path)
    ap.add_argument('--home', type=Path, help='home whose global files and skills links name the kit, when no registration names it')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', action='store_true')
    mode.add_argument('--recover', action='store_true')
    a = ap.parse_args(argv)
    try:
        if a.recover: out = recover(a.root)
        elif a.rollback: out = rollback(a.root)
        else:
            if a.to is None or a.package is None: raise Blocked('--to and --package are required')
            if a.apply: out = apply(a.root, a.to, a.package, a.handoff_registration, a.home)
            else:
                p = build(a.root, a.to, a.package, a.handoff_registration, a.home)
                out = ({'status': 'BLOCKED', 'reason': 'cannot move the kit: ' + '; '.join(p.blockers)} if p.blockers
                       else {'status': 'PLANNED (dry-run; pass --apply to move)', **public(p)})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        out = {'status': 'BLOCKED', 'reason': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
    print(json.dumps(out, indent=2))
    return 1 if out['status'] == 'BLOCKED' else 0
