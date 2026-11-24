#!/usr/bin/env python3
"""Guarded global Claude capture registration. Default plan is read-only.

Use the normal kit update integration for installation. No credential values,
server grants, consent, native trust or unrelated settings are changed here.
"""
import argparse
import ast
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import uuid
sys.dont_write_bytecode = True


def local_module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


HERE = Path(__file__).resolve().parent
installer = local_module('_capture_kit', HERE / 'kit.py')
old = sys.modules.get('kit'); sys.modules['kit'] = installer
try:
    connection = local_module('_capture_connection', HERE / 'connect-project.py')
finally:
    if old is None: del sys.modules['kit']
    else: sys.modules['kit'] = old
DISPATCH = 'runtime/storage/deploy/capture-bridge/claude_capture_dispatcher.py'
BRIDGE = 'runtime/storage/deploy/capture-bridge/capture_bridge.py'
QUEUE = 'runtime/storage/deploy/capture-bridge/capture_queue.py'
dispatcher = local_module('_capture_dispatch', HERE.parent / DISPATCH)
strict_json = dispatcher.strict_json
canonical = dispatcher.canonical
private_directory = dispatcher.private_dir


def validate_spec(spec):
    required = {'schema', 'home', 'managed_root', 'registration_root', 'mapping_path', 'python', 'projects'}
    if not isinstance(spec, dict) or set(spec) - required - {'retire'} or not required <= set(spec) or type(spec['schema']) is not int or spec['schema'] != 1:
        raise ValueError('invalid capture registration specification')
    paths = {k: canonical(spec[k]) for k in required - {'schema', 'projects'}}
    for k in ['home', 'managed_root']:
        if not paths[k].is_dir(): raise ValueError('missing directory')
    if not paths['python'].is_file() or not os.access(paths['python'], os.X_OK):
        raise ValueError('interpreter missing')
    reg = paths['registration_root']
    installer.safe_root(reg)
    if reg.exists(): private_directory(reg)
    if paths['mapping_path'].parent != reg:
        raise ValueError('mapping must be inside dedicated registration root')
    if reg == paths['managed_root'] or reg in paths['managed_root'].parents or paths['managed_root'] in reg.parents:
        raise ValueError('registration must be outside managed payload')
    if list_owned(paths):
        # The kit's project list owns the mapping; registered rows are the historical first enrollment.
        if (not isinstance(spec['projects'], list) or len(spec['projects']) > 128
                or any(not isinstance(r, dict) or set(r) != dispatcher.ROW_KEYS for r in spec['projects'])):
            raise ValueError('invalid historical enrollment rows')
    else:
        dispatcher.validate_mapping({'schema': 1, 'projects': spec['projects']})
        for row in spec['projects']:
            if paths['mapping_path'] in [Path(row[k]) for k in ('credential_file', 'queue_dir', 'status_file')]:
                raise ValueError('mapping collides with route file')
            # Metadata only; never open or serialize credential contents into receipts.
            dispatcher.private_file(row['credential_file'], limit=64 * 1024)
    retires = spec.get('retire', [])
    if not isinstance(retires, list) or len(retires) > 256: raise ValueError('invalid retirement list')
    seen = set()
    for entry in retires:
        if not isinstance(entry, dict) or set(entry) != {'path', 'command', 'hook_sha256'}:
            raise ValueError('invalid retirement entry')
        p = canonical(entry['path'])
        if p.name != 'settings.local.json' or p.parent.name != '.claude' or p == paths['home'] / '.claude/settings.local.json':
            raise ValueError('only explicitly named project local hook retirement allowed')
        if not any(p.parent.parent == Path(row['root']) or p.parent.parent in Path(row['root']).parents for row in spec['projects']):
            raise ValueError('retirement not related to enrolled root')
        if not isinstance(entry['command'], str) or not re.fullmatch('[a-f0-9]{64}', entry['hook_sha256']):
            raise ValueError('invalid exact retirement identity')
        if (entry['path'], entry['command']) in seen: raise ValueError('duplicate retirement')
        prove_legacy(entry['command'], spec, paths)
        seen.add((entry['path'], entry['command']))
    return paths


def prove_legacy(cmd, spec, paths):
    tokens = shlex.split(cmd)
    env = {}
    while tokens and '=' in tokens[0] and not tokens[0].startswith('/'):
        key, value = tokens.pop(0).split('=', 1)
        if key in env: raise ValueError('duplicate legacy environment')
        env[key] = value
    allowed = {'AF_CAPTURE_ENDPOINT', 'AF_CAPTURE_PROJECT', 'AF_CAPTURE_SOURCE', 'AF_CAPTURE_AGENT_CREDENTIAL_FILE', 'AF_CAPTURE_QUEUE_DIR', 'AF_CAPTURE_STATUS_FILE'}
    if set(env) - allowed or env.get('AF_CAPTURE_ENDPOINT') != 'http://127.0.0.1:8780':
        raise ValueError('not a recognized scoped legacy hook')
    wrapper = str(paths['managed_root'] / 'runtime/storage/deploy/capture-bridge/claude-code-stop-hook.sh')
    if tokens not in (['sh', wrapper], ['/bin/sh', wrapper]):
        raise ValueError('legacy hook is not managed bridge wrapper')
    matches = [r for r in spec['projects'] if r['project'] == env.get('AF_CAPTURE_PROJECT') and r['source_instance'] == env.get('AF_CAPTURE_SOURCE') and r['credential_file'] == env.get('AF_CAPTURE_AGENT_CREDENTIAL_FILE')]
    if len(matches) != 1: raise ValueError('legacy route does not match enrollment')
    inferred = str(Path(matches[0]['credential_file']).parent / 'capture-queue')
    if env.get('AF_CAPTURE_QUEUE_DIR', inferred) != matches[0]['queue_dir']:
        raise ValueError('legacy queue partition would change')


PROJECT_LIST = 'projects.json'


def list_owned(paths):
    """True once the kit's project list exists: `tools/projects.py` then writes the mapping."""
    return (paths['managed_root'] / installer.STATE / PROJECT_LIST).exists()


def kit_binding(root, required=False):
    identity = connection.kit_identity(root)
    files = installer.current(root)['files']
    if not {BRIDGE, QUEUE} <= set(files): raise ValueError('capture bridge component absent')
    present = DISPATCH in files
    if required and not present: raise ValueError('dispatcher not installed')
    if present:
        tree = ast.parse(installer.regular(root / DISPATCH))
        marker = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CAPTURE_DISPATCH_API' for t in n.targets)
                     and isinstance(n.value, ast.Constant) and type(n.value.value) is int and n.value.value == 1 for n in tree.body)
        if not marker: raise ValueError('unsupported dispatcher API')
    return {'identity': identity, 'runtime': {name: installer.signature(root / name) if name in files else None for name in [DISPATCH, BRIDGE, QUEUE]}}


def state_path(paths): return paths['registration_root'] / installer.STATE


def python_signature(paths):
    return {'sha256': installer.digest(paths['python'].read_bytes()), 'mode': stat.S_IMODE(paths['python'].stat().st_mode)}


def current(paths):
    state = state_path(paths)
    if (state / 'pending.json').exists(): raise ValueError('pending registration: explicit rollback required')
    for receipt in sorted((state / 'receipts').glob('*.json')):
        if installer.read_tx(receipt).get('status') == 'PREPARED': raise ValueError('prepared registration: explicit rollback required')
    p = state / 'current.json'
    if not p.exists(): return None
    d = installer.read_tx(p)
    if d.get('status') != 'APPLIED': raise ValueError('invalid registration state')
    owned = list_owned(paths)
    shared = str(paths['home'] / '.claude/settings.json')
    for n, sig in d['files'].items():
        if owned and n == str(paths['mapping_path']): continue  # written by the project list
        if installer.signature(canonical(n)) == sig: continue
        if n != shared: raise ValueError('registered file drift')
        # A shared host file: other registrations and the owner edit it too. Pin only this registration's hook and
        # the permissions section (C6). A record without the pin recovers it from its receipts.
        raw = installer.regular(canonical(n))
        if not own_hook_present(raw, d['command']): raise ValueError('registered hook drift')
        if permissions_digest(raw) != recorded_permissions(state, d, n, sig): raise ValueError('registered permissions drift')
    return d


def recorded_permissions(state, record, path, signature):
    """The pinned permissions digest; for a record written before the pin, recover it from the receipt bytes."""
    if path in record.get('permissions', {}): return record['permissions'][path]
    for file in sorted((state / 'receipts').glob('*.json')):
        for entry in installer.read_tx(file).get('plan', {}).get('changes', []):
            if entry['path'] == path and entry['after'] == signature:
                raw = base64.b64decode(entry['bytes'], validate=True)
                if installer.digest(raw) != signature['sha256']: raise ValueError('invalid registered settings evidence')
                return permissions_digest(raw)
    raise ValueError('registered file drift')


def permissions_digest(raw):
    d = strict_json(raw) if raw is not None else {}
    return installer.digest(installer.encode(d.get('permissions') if isinstance(d, dict) else None))


def own_hook_present(raw, wanted):
    if raw is None: return False
    d = hooks_document(raw)
    expected = {'type': 'command', 'command': wanted, 'timeout': 15}
    groups = [g for g in d['hooks'].get('Stop', []) for h in g['hooks'] if h.get('command') == wanted]
    return len(groups) == 1 and groups[0] == {'hooks': [expected]}


def command(paths):
    return shlex.join([str(paths['python']), '-I', '-B', str(paths['managed_root'] / DISPATCH), '--mapping', str(paths['mapping_path'])])


def hooks_document(raw):
    d = strict_json(raw) if raw is not None else {}
    if not isinstance(d, dict): raise ValueError('invalid settings')
    hooks = d.setdefault('hooks', {})
    if not isinstance(hooks, dict): raise ValueError('invalid hooks')
    for groups in hooks.values():
        if not isinstance(groups, list): raise ValueError('invalid groups')
        for g in groups:
            if not isinstance(g, dict) or not isinstance(g.get('hooks'), list) or any(not isinstance(h, dict) for h in g['hooks']):
                raise ValueError('invalid hook group')
    return d


def edit_global(raw, wanted, prior):
    d = hooks_document(raw)
    stop = d['hooks'].setdefault('Stop', [])
    matches = [(g, h) for g in stop for h in g['hooks'] if h.get('command') == wanted]
    expected = {'type': 'command', 'command': wanted, 'timeout': 15}
    if matches:
        if len(matches) != 1 or matches[0][1] != expected or matches[0][0] != {'hooks': [expected]}:
            raise ValueError('global hook collision')
        if not prior: raise ValueError('unowned global hook collision')
    else:
        if prior: raise ValueError('registered hook missing')
        stop.append({'hooks': [expected]})
    return installer.encode(d)


def retire_hooks(raw, entries, prior):
    if raw is None: raise ValueError('retirement file missing')
    d = hooks_document(raw)
    for entry in entries:
        found = []
        for event, groups in d['hooks'].items():
            for g in groups:
                for h in g['hooks']:
                    if h.get('command') == entry['command']:
                        found.append((event, g, h))
        if not found:
            if prior and entry in prior['spec'].get('retire', []): continue
            raise ValueError('retirement command absent')
        if len(found) != 1 or found[0][0] != 'Stop': raise ValueError('ambiguous retirement')
        event, group, hook = found[0]
        if installer.digest(installer.encode(hook)) != entry['hook_sha256']:
            raise ValueError('retirement hook changed')
        # Explicit exact approved hook identity, not a heuristic substring deletion.
        group['hooks'].remove(hook)
        if not group['hooks'] and set(group) == {'hooks'}:
            d['hooks'][event].remove(group)
        if not d['hooks'][event]: del d['hooks'][event]
    return installer.encode(d)


def target_baselines(spec):
    paths = validate_spec(spec)
    names = [str(paths['mapping_path']), str(paths['home'] / '.claude/settings.json')]
    names += [e['path'] for e in spec.get('retire', [])]
    return {n: installer.signature(canonical(n)) for n in sorted(set(names))}


def plan(spec):
    paths = validate_spec(spec); prior = current(paths)
    if prior and prior['spec'] != spec:
        previous = dict(prior['spec']); current_spec = dict(spec)
        old_retires = previous.pop('retire', []); new_retires = current_spec.pop('retire', [])
        if previous != current_spec or any(entry not in new_retires for entry in old_retires):
            raise ValueError('scope change requires new explicit registration review')
    binding = kit_binding(paths['managed_root'])
    wanted = command(paths)
    desired = {}
    # Publication order: mapping, global hook, then exact local duplicate retirement.
    owned = list_owned(paths)
    if not owned:
        desired[str(paths['mapping_path'])] = (installer.encode({'schema': 1, 'projects': spec['projects']}), 0o600)
    global_path = paths['home'] / '.claude/settings.json'
    before = installer.signature(global_path)
    raw = installer.regular(global_path); edited = edit_global(raw, wanted, prior)
    if raw is not None and installer.encode(strict_json(edited)) == installer.encode(strict_json(raw)):
        edited = raw  # nothing of ours to change: keep the owner's exact bytes and formatting
    desired[str(global_path)] = (edited, before['mode'] if before else 0o600)
    if not owned and installer.signature(paths['mapping_path']) and not prior: raise ValueError('unowned mapping collision')
    for n in sorted(set(e['path'] for e in spec.get('retire', []))):
        raw = installer.regular(Path(n)); before = installer.signature(Path(n))
        desired[n] = (retire_hooks(raw, [e for e in spec['retire'] if e['path'] == n], prior), before['mode'])
    files, changes = {}, []
    for target, (raw, mode) in desired.items():
        before = installer.signature(Path(target)); after = {'sha256': installer.digest(raw), 'mode': mode}; files[target] = after
        if before != after: changes.append({'path': target, 'before': before, 'after': after, 'bytes': base64.b64encode(raw).decode()})
    permissions = {str(global_path): permissions_digest(desired[str(global_path)][0])}
    data = {'schema': 1, 'spec': spec, 'kit': binding, 'python_signature': python_signature(paths), 'files': files,
            'changes': changes, 'prior': prior, 'command': wanted, 'permissions': permissions}
    result = {**data, 'plan_id': installer.digest(installer.encode(data)), 'status': 'PLANNED' if changes or not prior or prior['kit'] != binding or prior['python_signature'] != python_signature(paths) or prior['spec'] != spec or prior.get('permissions') != permissions else 'NOOP'}
    prepare_transaction(result, '0' * 32)
    return result


def receipt_bytes(value):
    clean = {k: v for k, v in value.items() if k != 'integrity'}
    raw = installer.encode({**clean, 'integrity': installer.digest(installer.encode(clean))})
    if len(raw) > installer.MAX: raise ValueError('receipt too large')
    return raw


def write_receipt(path, value):
    receipt_bytes(value); installer.write_tx(path, value)


def installed_record(p, txid):
    return {**{k: p[k] for k in ['spec', 'kit', 'files', 'command', 'python_signature', 'permissions']}, 'status': 'APPLIED', 'id': txid}


def prepare_transaction(p, txid):
    tx = {'id': txid, 'status': 'PREPARED', 'plan': p, 'applied': [], 'backups': {}}
    for entry in p['changes']:
        if entry['before']:
            raw = installer.regular(Path(entry['path']))
            if installer.digest(raw) != entry['before']['sha256']: raise ValueError('baseline changed')
            tx['backups'][entry['path']] = base64.b64encode(raw).decode()
    receipt_bytes(installed_record(p, txid))
    for count in range(len(p['changes']) + 1):
        for status in ['PREPARED', 'APPLIED', 'ROLLED_BACK']:
            receipt_bytes({**tx, 'status': status, 'applied': [e['path'] for e in p['changes'][:count]]})
    return tx


def apply(spec, expected_plan, exclusive_window=False):
    if not exclusive_window: raise ValueError('exclusive writer window required')
    p = plan(spec)
    if p['plan_id'] != expected_plan: raise ValueError('stale registration plan')
    paths = validate_spec(spec); kit_binding(paths['managed_root'], required=True)
    if p['status'] == 'NOOP': return {'status': 'NOOP', 'plan_id': expected_plan}
    paths['registration_root'].mkdir(mode=0o700, parents=True, exist_ok=True); private_directory(paths['registration_root'])
    with installer.lock(paths['registration_root']):
        p = plan(spec)
        if p['plan_id'] != expected_plan: raise ValueError('registration changed before lock')
        state = state_path(paths); txid = uuid.uuid4().hex; tx = prepare_transaction(p, txid)
        receipt = state / 'receipts' / (txid + '.json'); receipt.parent.mkdir(mode=0o700, exist_ok=True)
        write_receipt(receipt, tx); installer.atomic(state / 'pending.json', installer.encode({'id': txid}))
        for entry in p['changes']:
            installer.guarded_write(Path(entry['path']), entry['before'], entry['after'], base64.b64decode(entry['bytes']))
            tx['applied'].append(entry['path']); write_receipt(receipt, tx)
        if kit_binding(paths['managed_root']) != p['kit'] or python_signature(paths) != p['python_signature'] or any(installer.signature(Path(n)) != s for n, s in p['files'].items()):
            raise ValueError('post-write verification failed')
        write_receipt(state / 'current.json', installed_record(p, txid)); tx['status'] = 'APPLIED'; write_receipt(receipt, tx)
        (state / 'pending.json').unlink()
        return {'status': 'APPLIED', 'transaction': txid, 'receipt': str(receipt), 'plan_id': expected_plan}


def verify(spec):
    paths = validate_spec(spec); record = current(paths)
    if record is None or record['spec'] != spec: raise ValueError('registration missing')
    if python_signature(paths) != record['python_signature']: raise ValueError('interpreter changed')
    binding = kit_binding(paths['managed_root'], required=True)
    return {'status': 'VERIFIED', 'kit_changed': record['kit'] != binding, 'native_delivery': 'NOT_TESTED'}


def find_transaction(spec, plan_id):
    paths = validate_spec(spec)
    if not isinstance(plan_id, str) or not re.fullmatch('[a-f0-9]{64}', plan_id):
        raise ValueError('invalid registration plan identity')
    state = state_path(paths)
    ids = []
    for f in sorted((state / 'receipts').glob('*.json')):
        tx = installer.read_tx(f)
        if tx.get('plan', {}).get('plan_id') == plan_id and tx['plan'].get('spec') == spec and tx.get('status') in ('PREPARED', 'APPLIED'):
            ids.append(tx['id'])
    if len(ids) > 1: raise ValueError('ambiguous registration transaction')
    if not ids: return None
    txid = ids[0]
    matched = installer.read_tx(state / 'receipts' / (txid + '.json'))
    pending = installer.read_json(state / 'pending.json')['id'] if (state / 'pending.json').exists() else None
    active = installer.read_tx(state / 'current.json') if (state / 'current.json').exists() else None
    orphan = matched['status'] == 'PREPARED' and active == matched['plan']['prior']
    if pending not in (None, txid) or (active and active['id'] != txid and pending != txid and not orphan):
        raise ValueError('registration transaction no longer current')
    return txid


def rollback_plan(spec, txid):
    paths = validate_spec(spec)
    if not isinstance(txid, str) or not re.fullmatch('[a-f0-9]{32}', txid): raise ValueError('invalid transaction')
    state = state_path(paths); tx = installer.read_tx(state / 'receipts' / (txid + '.json'))
    if tx['plan']['spec'] != spec: raise ValueError('rollback scope mismatch')
    pending = installer.read_json(state / 'pending.json')['id'] if (state / 'pending.json').exists() else None
    active = installer.read_tx(state / 'current.json') if (state / 'current.json').exists() else None
    if tx['status'] == 'ROLLED_BACK' and pending is None: return {'status': 'NOOP', 'transaction': txid, 'plan_id': installer.digest(installer.encode(tx))}
    orphan = tx['status'] == 'PREPARED' and active == tx['plan']['prior']
    if pending not in (None, txid) or pending is None and not orphan and (active is None or active['id'] != txid):
        raise ValueError('not current/pending transaction')
    changed = {e['path'] for e in tx['plan']['changes']}
    for n, sig in tx['plan']['files'].items():
        if n not in changed and installer.signature(canonical(n)) != sig: raise ValueError('rollback unchanged target drift')
    for e in tx['plan']['changes']:
        if installer.signature(canonical(e['path'])) not in (e['before'], e['after']): raise ValueError('rollback target drift')
        if e['before'] and installer.digest(base64.b64decode(tx['backups'][e['path']], validate=True)) != e['before']['sha256']:
            raise ValueError('rollback backup corrupt')
    data = {'transaction': txid, 'tx': tx, 'active': active, 'pending': pending, 'targets': target_baselines(spec)}
    return {**data, 'status': 'PLANNED', 'plan_id': installer.digest(installer.encode(data))}


def rollback(spec, txid, expected_plan, exclusive_window=False):
    if not exclusive_window: raise ValueError('exclusive writer window required')
    p = rollback_plan(spec, txid)
    if p['plan_id'] != expected_plan: raise ValueError('stale rollback plan')
    if p['status'] == 'NOOP': return {'status': 'NOOP', 'transaction': txid}
    paths = validate_spec(spec); state = state_path(paths)
    with installer.lock(paths['registration_root']):
        p = rollback_plan(spec, txid)
        if p['plan_id'] != expected_plan: raise ValueError('rollback changed before lock')
        tx = p['tx']; installer.atomic(state / 'pending.json', installer.encode({'id': txid}))
        for e in reversed(tx['plan']['changes']):
            if installer.signature(Path(e['path'])) == e['after']:
                raw = base64.b64decode(tx['backups'][e['path']]) if e['before'] else None
                installer.guarded_write(Path(e['path']), e['after'], e['before'], raw)
        prior = tx['plan']['prior']
        if prior: write_receipt(state / 'current.json', prior)
        elif (state / 'current.json').exists(): (state / 'current.json').unlink()
        tx['status'] = 'ROLLED_BACK'; write_receipt(state / 'receipts' / (txid + '.json'), tx); (state / 'pending.json').unlink()
        return {'status': 'ROLLED_BACK', 'transaction': txid}


def summary(p):
    return {k: v for k, v in p.items() if k in ['status', 'transaction', 'receipt', 'plan_id', 'kit_changed', 'native_delivery']} | {
        'changes': [{k: e[k] for k in ['path', 'before', 'after']} for e in p.get('changes', [])]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'apply', 'verify', 'rollback-plan', 'rollback'], nargs='?', default='plan')
    parser.add_argument('--spec', required=True); parser.add_argument('--plan-id'); parser.add_argument('--transaction'); parser.add_argument('--exclusive-window', action='store_true')
    args = parser.parse_args(argv)
    try:
        spec = strict_json(dispatcher.private_file(args.spec, read=True))
        if args.action == 'plan': result = plan(spec)
        elif args.action == 'apply': result = apply(spec, args.plan_id, args.exclusive_window)
        elif args.action == 'verify': result = verify(spec)
        elif args.action == 'rollback-plan': result = rollback_plan(spec, args.transaction)
        else: result = rollback(spec, args.transaction, args.plan_id, args.exclusive_window)
        print(json.dumps(summary(result), indent=2)); return 0
    except Exception as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': type(exc).__name__})); return 1


if __name__ == '__main__': sys.exit(main())
