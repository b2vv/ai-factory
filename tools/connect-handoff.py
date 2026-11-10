#!/usr/bin/env python3
"""Explicit offline native handoff registration. Default: read-only plan.

No project settings, trust, Docker, or session stores are mutated. Apply requires
an exact freshly computed plan ID and a coordinated exclusive writer window.
Interrupted transactions require explicit guarded rollback, never replay.
"""
import argparse
import ast
import base64
import importlib.util
import json
import math
from decimal import Decimal
import os
from pathlib import Path
import re
import shlex
import stat
import sys
sys.dont_write_bytecode = True
import uuid
import unicodedata

# Imports come from the connector's exact distribution directory, not cwd/PYTHONPATH.
def local_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

HERE = Path(__file__).resolve().parent
installer = local_module('kit', HERE / 'kit.py')
# connect-project has a legacy `import kit`; bind only our exact adjacent helper.
_previous_kit = sys.modules.get('kit')
sys.modules['kit'] = installer
try:
    connection = local_module('_handoff_connect_project', HERE / 'connect-project.py')
finally:
    if _previous_kit is None:
        del sys.modules['kit']
    else:
        sys.modules['kit'] = _previous_kit

EVENTS = ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop')
HOSTS = ('claude', 'codex')
NATIVE = 'runtime/session-size/native.py'
GUARD = 'runtime/session-size/session_guard.py'


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON value')
    def exact_float(value):
        number = float(value)
        if not math.isfinite(number) or Decimal(str(number)) != Decimal(value):
            raise ValueError('unrepresentable JSON number')
        return number
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=exact_float)


def canonical(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(ch) < 32 or ord(ch) == 127 or unicodedata.category(ch) == 'Cf' for ch in value):
        raise ValueError('invalid path')
    path = installer.absolute(value)
    if str(path) != value or path == Path(path.anchor):
        raise ValueError('canonical dedicated path required')
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError('non-directory path ancestor')
    return path


def overlaps(a, b):
    return a == b or a in b.parents or b in a.parents


def private_directory(path):
    if path.exists():
        s = path.stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise ValueError('registration directory must be private and owned')


def validate_spec(spec):
    required = {'home', 'managed_root', 'store', 'roots', 'profile_path', 'registration_root', 'hosts', 'python'}
    if not isinstance(spec, dict) or not required <= spec.keys() or set(spec) - required - {'legacy', 'retire'}:
        raise ValueError('invalid registration specification')
    paths = {key: canonical(spec[key]) for key in required - {'roots', 'hosts'}}
    if not paths['home'].is_dir() or not paths['managed_root'].is_dir():
        raise ValueError('home/managed root missing')
    if not isinstance(spec['hosts'], list) or not spec['hosts'] or len(set(spec['hosts'])) != len(spec['hosts']) or any(h not in HOSTS for h in spec['hosts']):
        raise ValueError('explicit unique approved hosts required')
    roots = spec['roots']
    if not isinstance(roots, list) or not 1 <= len(roots) <= 64 or any(not isinstance(r, str) for r in roots) or len(set(roots)) != len(roots):
        raise ValueError('unique project roots required')
    for root in map(canonical, roots):
        if not root.is_dir() or not (root / '.git').exists():
            raise ValueError('enrolled Git root required')
        installer.absolute(root / '.git')
    executable = paths['python'].stat()
    if not stat.S_ISREG(executable.st_mode) or executable.st_nlink != 1 or not os.access(paths['python'], os.X_OK):
        raise ValueError('reviewed Python executable must be regular and executable')
    host_roots = [canonical(str(paths['home'] / name)) for name in ('.claude', '.codex')]
    targets = [paths['profile_path']]
    if 'legacy' in spec:
        legacy = spec['legacy']
        if not isinstance(legacy, dict) or set(legacy) != {'path', 'before_sha256'} or not isinstance(legacy['before_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', legacy['before_sha256']):
            raise ValueError('explicit legacy path and SHA256 required')
        legacy_path = canonical(legacy['path'])
        if legacy_path != paths['home'] / '.agents/ai-factory/session-size/session_guard.py':
            raise ValueError('legacy target outside authorized migration boundary')
        targets.append(legacy_path)
    protected = [paths['managed_root'], paths['store'], paths['registration_root'], *map(Path, roots), *host_roots]
    for index, path in enumerate(protected):
        for other in protected[index + 1:]:
            if overlaps(path, other):
                raise ValueError('protected directory overlap')
    for target in targets:
        if target == paths['home'] or any(overlaps(target, p) for p in protected):
            raise ValueError('target overlaps protected directory')
    if len(targets) == 2 and overlaps(*targets):
        raise ValueError('targets overlap')
    private_directory(paths['store'])
    private_directory(paths['registration_root'])
    # The installer lock and receipts use its private state child; never adopt foreign state.
    private_directory(paths['registration_root'] / installer.STATE)
    private_directory(paths['registration_root'] / installer.STATE / 'receipts')
    retires = spec.get('retire', [])
    if not isinstance(retires, list):
        raise ValueError('invalid retirement inventory')
    seen = set()
    for item in retires:
        if (not isinstance(item, dict) or set(item) != {'host', 'event', 'command'} or item['host'] not in spec['hosts']
                or not isinstance(item['event'], str) or not item['event']
                or not isinstance(item['command'], str) or not item['command']):
            raise ValueError('invalid exact retirement entry')
        key = (item['host'], item['event'], item['command'])
        if key in seen:
            raise ValueError('duplicate retirement entry')
        seen.add(key)
    return paths


def kit_binding(root):
    identity = connection.kit_identity(root)
    files = installer.current(root)['files']
    if any(name not in files for name in (NATIVE, GUARD)):
        raise ValueError('handoff component missing')
    tree = ast.parse(installer.regular(root / NATIVE))
    marker = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HANDOFF_API' for t in n.targets)
                 and isinstance(n.value, ast.Constant) and type(n.value.value) is int and n.value.value == 1 for n in tree.body)
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if not marker or not {'load_profile', 'event', 'main'} <= functions:
        raise ValueError('unsupported native handoff API')
    return {'identity': identity, 'runtime': {name: installer.signature(root / name) for name in (NATIVE, GUARD)}}


def python_signature(paths):
    executable = paths['python']
    return {'sha256': installer.digest(executable.read_bytes()), 'mode': stat.S_IMODE(executable.stat().st_mode)}


def state_path(paths):
    return paths['registration_root'] / installer.STATE


def current(paths):
    state = state_path(paths)
    if (state / 'pending.json').exists():
        raise ValueError('pending registration: explicit rollback required')
    for receipt_path in sorted((state / 'receipts').glob('*.json')):
        if installer.read_tx(receipt_path).get('status') == 'PREPARED':
            raise ValueError('prepared registration: explicit rollback required')
    file = state / 'current.json'
    if not file.exists():
        if paths['registration_root'].exists() and any(paths['registration_root'].iterdir()) and not state.exists():
            raise ValueError('registration root is not dedicated')
        return None
    receipt = installer.read_tx(file)
    if receipt.get('status') != 'APPLIED':
        raise ValueError('invalid current registration')
    for path, signature in receipt['files'].items():
        if installer.signature(canonical(path)) != signature:
            raise ValueError('registered file drift')
    return receipt


def command(paths, host):
    return shlex.join([str(paths['python']), '-I', '-B', str(paths['managed_root'] / NATIVE), 'hook', '--profile', str(paths['profile_path']), '--host', host])


def loader(paths):
    # Values are Python string literals, never interpolated executable expressions.
    return ("#!/usr/bin/env python3\nimport importlib.util\nimport sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\n"
            f"_PROFILE = {str(paths['profile_path'])!r}\n"
            f"_spec = importlib.util.spec_from_file_location('_managed_handoff_native', {str(paths['managed_root'] / NATIVE)!r})\n"
            "_native = importlib.util.module_from_spec(_spec)\n_spec.loader.exec_module(_native)\n"
            "DEFAULT_STORE = Path(_native.load_profile(_PROFILE)['store'])\n"
            "def event(store, host, payload, pointer=None):\n"
            "    return _native.event(_PROFILE, host, payload, pointer=pointer, store=store)\n"
            "if __name__ == '__main__':\n    import sys\n"
            "    if '--profile' in sys.argv[1:] or any(a.startswith('--profile=') for a in sys.argv[1:]):\n"
            "        raise SystemExit('legacy profile is fixed')\n"
            "    raise SystemExit(_native.main(sys.argv[1:] + ['--profile', _PROFILE]))\n").encode()


def hooks_document(raw):
    obj = {} if raw is None else strict_json(raw)
    if not isinstance(obj, dict) or not isinstance(obj.get('hooks', {}), dict):
        raise ValueError('unsupported hooks configuration')
    for event, groups in obj.get('hooks', {}).items():
        if not isinstance(event, str) or not event or not isinstance(groups, list):
            raise ValueError('unsupported hooks event')
        for group in groups:
            if (not isinstance(group, dict) or 'hooks' not in group or not isinstance(group['hooks'], list)
                    or set(group) - {'hooks', 'matcher'} or ('matcher' in group and not isinstance(group['matcher'], str))):
                raise ValueError('unsupported hooks group')
            for handler in group['hooks']:
                if not isinstance(handler, dict) or not isinstance(handler.get('type'), str):
                    raise ValueError('unsupported handler')
                if handler['type'] == 'command' and not isinstance(handler.get('command'), str):
                    raise ValueError('invalid command handler')
    return obj


def edit_hooks(raw, host, wanted, prior, retires):
    obj = hooks_document(raw)
    hooks = obj.setdefault('hooks', {})
    old_commands = {(x['event'], x['command']) for x in (prior or {}).get('commands', []) if x['host'] == host}
    selected = {(x['event'], x['command']) for x in retires if x['host'] == host}
    previous_retired = {(x['event'], x['command']) for x in (prior or {}).get('retired', []) if x['host'] == host}
    for event, value in sorted(old_commands | selected):
        matches = [(group, handler) for group in hooks.get(event, []) for handler in group['hooks']
                   if handler.get('type') == 'command' and handler.get('command') == value]
        if len(matches) > 1 or (not matches and (event, value) not in previous_retired):
            raise ValueError('ambiguous or absent exact retirement')
        emptied = set()
        for group, handler in matches:
            group['hooks'].remove(handler)
            if not group['hooks']:
                emptied.add(id(group))
        # Preserve unrelated empty groups, including ones equal by value to a removed group.
        hooks[event] = [g for g in hooks.get(event, []) if id(g) not in emptied]
    for event in EVENTS:
        if any(h.get('command') == wanted for g in hooks.get(event, []) for h in g['hooks']):
            raise ValueError('unowned command collision')
        hooks.setdefault(event, []).append({'hooks': [{'type': 'command', 'command': wanted}]})
    encoded = installer.encode(obj)
    # Unchanged semantic document retains original formatting/bytes.
    return raw if raw is not None and strict_json(raw) == obj else encoded


def plan(spec):
    paths = validate_spec(spec)
    binding = kit_binding(paths['managed_root'])
    prior = current(paths)
    if prior and (prior['spec']['home'] != spec['home'] or set(prior['spec']['hosts']) - set(spec['hosts'])):
        raise ValueError('cannot abandon previously owned host configuration')
    desired = {}
    profile = {'schema': 1, 'managed_root': spec['managed_root'], 'store': spec['store'], 'roots': spec['roots']}
    if len(installer.encode(profile)) > 32768:
        raise ValueError('profile exceeds native adapter limit')
    desired[str(paths['profile_path'])] = (installer.encode(profile), 0o600)
    if 'legacy' in spec:
        target = spec['legacy']['path']
        desired[target] = (loader(paths), 0o644)
        if not prior or target not in prior['files']:
            sig = installer.signature(Path(target))
            if not sig or sig['sha256'] != spec['legacy']['before_sha256']:
                raise ValueError('legacy baseline hash mismatch')
    for host in spec['hosts']:
        target = paths['home'] / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')
        canonical(str(target))
        raw = installer.regular(target)
        desired[str(target)] = (edit_hooks(raw, host, command(paths, host), prior, spec.get('retire', [])),
                                installer.signature(target)['mode'] if raw is not None else 0o600)
    if prior and set(prior['files']) - set(desired):
        raise ValueError('cannot abandon an owned target')
    profile_before = installer.signature(paths['profile_path'])
    if profile_before is not None and (not prior or str(paths['profile_path']) not in prior['files']):
        raise ValueError('unowned profile collision')
    files, changes = {}, []
    for target, (raw, mode) in sorted(desired.items()):
        before = installer.signature(Path(target))
        after = {'sha256': installer.digest(raw), 'mode': mode}
        files[target] = after
        if before != after:
            changes.append({'path': target, 'before': before, 'after': after, 'bytes': base64.b64encode(raw).decode()})
    data = {'schema': 1, 'spec': spec, 'kit': binding, 'python_signature': python_signature(paths), 'files': files, 'changes': changes,
            'prior': prior, 'commands': [{'host': h, 'event': e, 'command': command(paths, h)} for h in spec['hosts'] for e in EVENTS],
            'retired': spec.get('retire', [])}
    result = {**data, 'plan_id': installer.digest(installer.encode(data)), 'status': 'PLANNED' if changes or (prior and (prior['kit'] != binding or prior['python_signature'] != python_signature(paths) or prior['spec'] != spec)) else 'NOOP'}
    # Bind the maximum journal size while planning, before creating state or publishing targets.
    prepare_transaction(result, '0' * 32)
    return result


def receipt_bytes(value):
    """Use the installer's exact integrity envelope and reader byte limit."""
    clean = {key: item for key, item in value.items() if key != 'integrity'}
    raw = installer.encode({**clean, 'integrity': installer.digest(installer.encode(clean))})
    if len(raw) > installer.MAX:
        raise ValueError('registration receipt exceeds readable size limit')
    return raw


def write_receipt(path, value):
    # Defense at every transition; prepare_transaction already preflights all reachable states.
    receipt_bytes(value)
    installer.write_tx(path, value)


def installed_record(p, txid):
    record = {key: p[key] for key in ('spec', 'kit', 'files', 'commands', 'retired', 'python_signature')}
    return {**record, 'status': 'APPLIED', 'id': txid}


def prepare_transaction(p, txid):
    tx = {'id': txid, 'status': 'PREPARED', 'plan': p, 'applied': [], 'backups': {}}
    for entry in p['changes']:
        if entry['before']:
            raw = installer.regular(Path(entry['path']))
            if installer.digest(raw) != entry['before']['sha256']:
                raise ValueError('baseline changed')
            tx['backups'][entry['path']] = base64.b64encode(raw).decode()
    receipt_bytes(installed_record(p, txid))
    if p['prior']:
        receipt_bytes(p['prior'])
    # Every completed-write prefix can be persisted, completed, or explicitly rolled back.
    paths = [entry['path'] for entry in p['changes']]
    for count in range(len(paths) + 1):
        for status in ('PREPARED', 'APPLIED', 'ROLLED_BACK'):
            receipt_bytes({**tx, 'status': status, 'applied': paths[:count]})
    return tx


def apply(spec, expected_plan, exclusive_window=False):
    if not exclusive_window:
        raise ValueError('exclusive writer window required')
    p = plan(spec)
    if p['plan_id'] != expected_plan:
        raise ValueError('stale or wrong registration plan')
    if p['status'] == 'NOOP':
        return {'status': 'NOOP', 'plan_id': expected_plan}
    paths = validate_spec(spec)
    root = paths['registration_root']
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_directory(root)
    with installer.lock(root):
        p = plan(spec)
        if p['plan_id'] != expected_plan:
            raise ValueError('registration plan changed before lock')
        state = state_path(paths)
        txid = uuid.uuid4().hex
        tx = prepare_transaction(p, txid)
        receipt_path = state / 'receipts' / (txid + '.json')
        receipt_path.parent.mkdir(mode=0o700, exist_ok=True)
        write_receipt(receipt_path, tx)
        installer.atomic(state / 'pending.json', installer.encode({'id': txid}))
        for entry in p['changes']:
            installer.guarded_write(Path(entry['path']), entry['before'], entry['after'], base64.b64decode(entry['bytes']))
            tx['applied'].append(entry['path'])
            write_receipt(receipt_path, tx)
        if python_signature(paths) != p['python_signature'] or kit_binding(paths['managed_root']) != p['kit'] or any(installer.signature(Path(path)) != sig for path, sig in p['files'].items()):
            raise ValueError('post-write verification failed; rollback required')
        installed = installed_record(p, txid)
        write_receipt(state / 'current.json', installed)
        tx['status'] = 'APPLIED'
        write_receipt(receipt_path, tx)
        (state / 'pending.json').unlink()
        return {'status': 'APPLIED', 'transaction': txid, 'receipt': str(receipt_path), 'plan_id': expected_plan}


def verify(spec):
    paths = validate_spec(spec)
    installed = current(paths)
    if installed is None or installed['spec'] != spec:
        raise ValueError('registration absent or specification changed')
    binding = kit_binding(paths['managed_root'])
    if python_signature(paths) != installed['python_signature']:
        raise ValueError('registered interpreter drift')
    return {'status': 'VERIFIED', 'registered_kit': installed['kit'], 'current_kit': binding,
            'kit_changed': installed['kit'] != binding, 'native_delivery': 'NOT_TESTED'}


def rollback(spec, txid, exclusive_window=False):
    if not exclusive_window or not isinstance(txid, str) or not re.fullmatch('[a-f0-9]{32}', txid):
        raise ValueError('exclusive window and exact transaction required')
    paths = validate_spec(spec)
    state = state_path(paths)
    receipt = state / 'receipts' / (txid + '.json')
    tx = installer.read_tx(receipt)
    if tx['plan']['spec'] != spec:
        raise ValueError('rollback specification mismatch')
    if tx['status'] == 'ROLLED_BACK' and not (state / 'pending.json').exists():
        return {'status': 'NOOP', 'transaction': txid}
    with installer.lock(paths['registration_root']):
        tx = installer.read_tx(receipt)
        pending = installer.read_json(state / 'pending.json')['id'] if (state / 'pending.json').exists() else None
        active = installer.read_tx(state / 'current.json') if (state / 'current.json').exists() else None
        prior = tx['plan']['prior']
        orphan_prepared = tx['status'] == 'PREPARED' and active == prior
        if pending not in (None, txid) or (pending is None and not orphan_prepared and (active is None or active['id'] != txid)):
            raise ValueError('not the current or pending transaction')
        # Validate rollback's final receipt before any target is restored.
        receipt_bytes({**tx, 'status': 'ROLLED_BACK'})
        if prior:
            receipt_bytes(prior)
        # Preflight ALL targets, including unchanged targets and unjournaled writes.
        changed = {entry['path'] for entry in tx['plan']['changes']}
        for path, signature in tx['plan']['files'].items():
            if path not in changed and installer.signature(canonical(path)) != signature:
                raise ValueError('rollback blocked by unchanged target drift')
        for entry in tx['plan']['changes']:
            if installer.signature(canonical(entry['path'])) not in (entry['before'], entry['after']):
                raise ValueError('rollback blocked by drift')
            if entry['before'] and installer.digest(base64.b64decode(tx['backups'][entry['path']], validate=True)) != entry['before']['sha256']:
                raise ValueError('corrupt rollback backup')
        installer.atomic(state / 'pending.json', installer.encode({'id': txid}))
        for entry in reversed(tx['plan']['changes']):
            if installer.signature(Path(entry['path'])) == entry['after']:
                raw = base64.b64decode(tx['backups'][entry['path']]) if entry['before'] else None
                installer.guarded_write(Path(entry['path']), entry['after'], entry['before'], raw)
        prior = tx['plan']['prior']
        if prior:
            write_receipt(state / 'current.json', prior)
        elif (state / 'current.json').exists():
            (state / 'current.json').unlink()
        tx['status'] = 'ROLLED_BACK'
        write_receipt(receipt, tx)
        (state / 'pending.json').unlink()
        return {'status': 'ROLLED_BACK', 'transaction': txid}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='plan', choices=('plan', 'apply', 'verify', 'rollback'))
    parser.add_argument('--spec', required=True)
    parser.add_argument('--plan-id')
    parser.add_argument('--transaction')
    parser.add_argument('--exclusive-window', action='store_true')
    args = parser.parse_args(argv)
    try:
        spec = strict_json(installer.regular(canonical(args.spec)))
        if args.mode == 'plan':
            result = plan(spec)
        elif args.mode == 'apply':
            result = apply(spec, args.plan_id, args.exclusive_window)
        elif args.mode == 'verify':
            result = verify(spec)
        else:
            result = rollback(spec, args.transaction, args.exclusive_window)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError):
        print('BLOCKED: invalid, stale, unsupported, or interrupted handoff registration; inspect the read-only plan and private receipt.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
