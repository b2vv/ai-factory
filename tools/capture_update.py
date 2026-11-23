"""Explicit, journaled capture companion for normal managed updates.

No registration exists until --capture-spec is explicitly supplied. Once registered,
normal updates reconcile the same pinned spec. Multi-resource completion is NOT atomic.
"""
import base64
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import uuid

REG = 'capture-registration.json'
PENDING = 'capture-update-pending.json'
RECEIPTS = 'capture-updates'
CONNECTOR = 'tools/connect-capture.py'
DISPATCHER = 'runtime/storage/deploy/capture-bridge/claude_capture_dispatcher.py'


def private_json(k, path):
    raw = k.regular(path)
    if raw is None:
        return None
    s = path.stat()
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise ValueError('capture state must be private and owned')
    def pairs(items):
        d = {}
        for key, value in items:
            if key in d: raise ValueError('duplicate capture metadata key')
            d[key] = value
        return d
    return json.loads(raw, object_pairs_hook=pairs)


def active(k, root, spec_path=None):
    return spec_path is not None or (Path(root)/k.STATE/REG).exists() or (Path(root)/k.STATE/PENDING).exists()


def connector(k, package, components, expected_release=None):
    # All selected bytes are verified before importing any candidate Python code.
    m, files, _ = k.payload(Path(package), components)
    release = k.digest(k.encode(m))
    if expected_release is not None and release != expected_release:
        raise ValueError('capture recovery package changed')
    if CONNECTOR not in files or DISPATCHER not in files:
        raise ValueError('registered capture requires connector and dispatcher components')
    path = Path(package)/CONNECTOR
    spec = importlib.util.spec_from_file_location('_factory_capture_connector', path)
    mod = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def material(cp):
    # Connector guarantees these fields completely describe target before/after writes.
    return {key: cp.get(key) for key in ('spec', 'python_signature', 'files', 'changes', 'prior', 'command')}


def plan(k, package, root, components=(), spec_path=None):
    root = k.safe_root(root)
    if (root/k.STATE/PENDING).exists():
        raise ValueError('unfinished capture update: explicit rollback required')
    kp = k.plan(Path(package), root, components)
    c = connector(k, package, kp['components'])
    regpath = root/k.STATE/REG
    old = private_json(k, regpath)
    if spec_path is not None:
        spec = private_json(k, k.absolute(spec_path))
        if spec is None: raise ValueError('missing capture specification')
    elif old:
        spec = old['spec']
        if old.get('spec_sha256') != k.digest(k.encode(spec)):
            raise ValueError('capture registered specification integrity mismatch')
    else:
        raise ValueError('capture specification required')
    if spec.get('managed_root') != str(root):
        raise ValueError('capture specification root mismatch')
    # One global kit per home (T15 A17): the instruction owner record names it; capture writes the same global files.
    owner_path = k.absolute(spec['home'])/'.agents/.ai-factory-instructions/owner.json'
    owner = private_json(k, owner_path) if owner_path.exists() else None
    if owner is not None and owner != {'schema': 1, 'root': str(root)}:
        bound = owner.get('root') if isinstance(owner, dict) else None
        raise ValueError('home already bound to another managed root' + (f': {bound}' if isinstance(bound, str) else ''))
    cp = c.plan(spec)
    new = {'schema': 1, 'spec': spec, 'spec_sha256': k.digest(k.encode(spec))}
    desired = k.encode(new)
    regbefore = k.signature(regpath)
    regafter = {'sha256': k.digest(desired), 'mode': 0o600}
    binding = {'kit_plan_id': kp['plan_id'], 'spec': spec, 'capture_plan_id': cp['plan_id'],
               'host_changes': material(cp), 'registration_before': regbefore,
               'registration_after': regafter}
    ident = k.digest(k.encode(binding))
    noop = kp['status'] == 'NOOP' and cp['status'] == 'NOOP' and regbefore == regafter
    return {**kp, 'plan_id': ident, 'status': 'NOOP' if noop else 'PLANNED',
            'capture': {'spec_sha256': new['spec_sha256'], 'changes': [{key: e.get(key) for key in ('path','before','after')} for e in cp['changes']],
                        'registration_changed': regbefore != regafter},
            '_capture': {'binding': binding, 'kit': kp, 'connector': cp, 'registration': new}}


def public(p):
    result = {key: value for key, value in p.items() if key not in ('_capture', 'capture_rollback')}
    if p.get('capture_rollback'):
        cp=p['capture_rollback']; result['capture_rollback']={key:cp.get(key) for key in ('status','transaction','plan_id')}
    return result


def write_receipt(k, path, tx):
    if len(k.encode({**tx, 'integrity': '0'*64})) > k.MAX:
        raise ValueError('capture update receipt too large')
    k.write_tx(path, tx)


@contextmanager
def integration_lock(k, root):
    root = k.safe_root(root)
    state = root/k.STATE
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_uid != os.getuid() or stat.S_IMODE(state.stat().st_mode) & 0o077:
        raise ValueError('state directory must be private and owned')
    path = k.absolute(state/'capture-update-lock')
    fd = os.open(path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def apply(k, package, root, components, spec_path, expected, exclusive):
    k.instruction_barrier(root)
    if not exclusive: raise ValueError('exclusive writer window required')
    pre = plan(k, package, root, components, spec_path)
    if pre['plan_id'] != expected: raise ValueError('stale combined capture plan')
    if pre['status'] == 'NOOP': return {'status': 'NOOP', 'plan_id': expected}
    root = Path(root)
    with integration_lock(k, root):
        p = plan(k, package, root, components, spec_path)
        if p['plan_id'] != expected: raise ValueError('combined capture plan changed')
        b = p['_capture']['binding']; txid = uuid.uuid4().hex
        receipt = root/k.STATE/RECEIPTS/(txid+'.json')
        oldraw = k.regular(root/k.STATE/REG)
        tx = {'id': txid, 'root': str(root), 'status': 'PREPARED', 'plan': p,
              'registration_before_bytes': base64.b64encode(oldraw).decode() if oldraw is not None else None,
              'kit_result': None, 'capture_result': None}
        write_receipt(k, receipt, tx)
        k.atomic(root/k.STATE/PENDING, k.encode({'id': txid}))
        try:
            tx['kit_result'] = k.apply(package, root, components, b['kit_plan_id'])
            tx['status'] = 'KIT_APPLIED'; write_receipt(k, receipt, tx)
            c = connector(k, package, p['components'], p['release_sha256'])
            cp = c.plan(b['spec'])
            if material(cp) != b['host_changes']:
                raise ValueError('capture host plan changed after kit update')
            # Store the exact new connector plan before its first mutation.
            tx['capture_plan'] = cp; tx['status'] = 'CAPTURE_APPLYING'; write_receipt(k, receipt, tx)
            tx['capture_result'] = c.apply(b['spec'], cp['plan_id'], exclusive_window=True)
            tx['status'] = 'CAPTURE_APPLIED'; write_receipt(k, receipt, tx)
            k.guarded_write(root/k.STATE/REG, b['registration_before'], b['registration_after'],
                            k.encode(p['_capture']['registration']))
            tx['status'] = 'APPLIED'; write_receipt(k, receipt, tx)
            (root/k.STATE/PENDING).unlink()
            return {'status': 'APPLIED', 'transaction': txid,
                    'kit_transaction': tx['kit_result'].get('transaction'),
                    'capture_transaction': tx['capture_result'].get('transaction'),
                    'receipt': str(receipt), 'plan_id': expected}
        except Exception:
            # Never hide partial success or replay a registration automatically.
            return {'status': 'BLOCKED', 'phase': tx['status'], 'transaction': txid,
                    'kit_transaction': (tx.get('kit_result') or {}).get('transaction'),
                    'reason': 'Capture update incomplete; inspect receipt and run explicit guarded rollback. No automatic replay.'}


def is_transaction(k, root, txid):
    return bool(txid and len(txid) == 32 and all(c in '0123456789abcdef' for c in txid)
                and (Path(root)/k.STATE/RECEIPTS/(txid+'.json')).exists())


def _kit_transaction(k, tx):
    result = tx.get('kit_result') or {}
    if result.get('transaction'): return result['transaction']
    if tx['plan']['_capture']['kit']['status'] == 'NOOP': return None
    # Crash after kit.apply but before saving its result: identify only an exact plan match.
    root = Path(tx['root']); candidates = {k.current(root).get('latest'), k.pending(root)}
    for ident in candidates - {None}:
        receipt = k.read_tx(root/k.STATE/'receipts'/(ident+'.json'))
        if receipt['plan']['plan_id'] == tx['plan']['_capture']['binding']['kit_plan_id']:
            return ident
    if k.current(root) == tx['plan']['_capture']['kit']['before']: return None
    raise ValueError('uncertain kit transaction; manual receipt reconciliation required')


def rollback_plan(k, root, txid):
    root = k.safe_root(root); tx = k.read_tx(root/k.STATE/RECEIPTS/(txid+'.json'))
    if tx['root'] != str(root) or tx['id'] != txid: raise ValueError('capture receipt mismatch')
    if tx['status'] == 'ROLLED_BACK': return {'status': 'NOOP', 'transaction': txid}
    p = tx['plan']; b = p['_capture']['binding']
    c = connector(k, p['package'], p['components'], p['release_sha256'])
    cr = tx.get('capture_result') or {}
    ctx = cr.get('transaction')
    if not ctx and tx.get('capture_plan'):
        ctx = c.find_transaction(b['spec'], tx['capture_plan']['plan_id'])
    cp = c.rollback_plan(b['spec'], ctx) if ctx else None
    kt = _kit_transaction(k, tx)
    kp = k.rollback_plan(root, kt) if kt else None
    now = k.signature(root/k.STATE/REG)
    if now not in (b['registration_before'], b['registration_after']):
        raise ValueError('capture registration changed; rollback blocked')
    result = {'status': 'PLANNED', 'transaction': txid, 'capture_transaction': ctx,
              'capture_rollback': cp, 'kit_transaction': kt, 'kit_rollback': kp,
              'registration_current': now}
    result['plan_id'] = k.digest(k.encode(result))
    return result


def rollback(k, root, txid, expected, exclusive):
    k.instruction_barrier(root)
    if not exclusive: raise ValueError('exclusive writer window required')
    pre = rollback_plan(k, root, txid)
    if pre['status'] == 'NOOP':
        pending = Path(root)/k.STATE/PENDING
        if pending.exists():
            with integration_lock(k, Path(root)):
                if k.read_json(pending).get('id') != txid:
                    raise ValueError('different pending capture update')
                tx = k.read_tx(Path(root)/k.STATE/RECEIPTS/(txid+'.json'))
                b = tx['plan']['_capture']['binding']
                if k.signature(Path(root)/k.STATE/REG) != b['registration_before'] or k.current(Path(root)) != tx['plan']['_capture']['kit']['before']:
                    raise ValueError('rollback completion state changed')
                cp = tx['plan']['_capture']['connector']
                before = {e['path']: e['before'] for e in cp['changes']}
                for name, sig in cp['files'].items():
                    if k.signature(Path(name)) != before.get(name, sig):
                        raise ValueError('rollback completion target changed')
                pending.unlink()
        return pre
    if pre['plan_id'] != expected: raise ValueError('stale capture rollback plan')
    root = Path(root)
    with integration_lock(k, root):
        p = rollback_plan(k, root, txid)
        if p['plan_id'] != expected: raise ValueError('capture rollback state changed')
        path = root/k.STATE/RECEIPTS/(txid+'.json'); tx = k.read_tx(path)
        b = tx['plan']['_capture']['binding']
        c = connector(k, tx['plan']['package'], tx['plan']['components'], tx['plan']['release_sha256'])
        if p['capture_transaction']:
            c.rollback(b['spec'], p['capture_transaction'], p['capture_rollback'].get('plan_id'), exclusive_window=True)
        # Restore prior registration only after local hooks have been restored by connector.
        now = k.signature(root/k.STATE/REG)
        if now != b['registration_before']:
            raw = tx['registration_before_bytes']
            k.guarded_write(root/k.STATE/REG, now, b['registration_before'], base64.b64decode(raw) if raw is not None else None)
        if p['kit_transaction']:
            k.rollback(root, p['kit_transaction'], p['kit_rollback'].get('plan_id'))
        tx['status'] = 'ROLLED_BACK'; write_receipt(k, path, tx)
        pending = root/k.STATE/PENDING
        if pending.exists() and k.read_json(pending).get('id') == txid: pending.unlink()
        return {'status': 'ROLLED_BACK', 'transaction': txid}
