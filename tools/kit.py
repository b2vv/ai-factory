#!/usr/bin/env python3
"""Offline managed toolkit installer. No arguments that execute arbitrary commands."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
sys.dont_write_bytecode = True  # Planning must not mutate candidate package inventories.
import tempfile
import uuid

STATE = '.ai-factory-state'
MAX = 2_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + '\n').encode()


def absolute(value):
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts:
        raise ValueError('explicit canonical absolute path required')
    for q in (p, *p.parents):
        if q.is_symlink():
            raise ValueError('symlink refused')
    return p


def relative(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('invalid release path')
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('noncanonical release path')
    if any(x in (STATE, '.git', '.ssh', '.aws') or x.startswith('.env') or
           re.search(r'(?i)credential|\.pem$|\.key$', x) for x in p.parts):
        raise ValueError('sensitive/reserved release path')
    return p


def regular(p):
    p = absolute(p)
    if not p.exists():
        return None
    s = p.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_size > MAX:
        raise ValueError('nonregular/hardlinked/oversized file refused')
    return p.read_bytes()


def signature(p):
    data = regular(p)
    return None if data is None else {'sha256': digest(data), 'mode': stat.S_IMODE(p.stat().st_mode)}


def read_json(p):
    data = regular(p)
    if data is None:
        raise ValueError('missing metadata')
    return json.loads(data)


def safe_root(root):
    root = absolute(root)
    # The managed root must be a dedicated child, never an existing host/config root.
    if root == Path(root.anchor) or root == Path.home() or root.name in ('.agents', '.claude', '.codex', '.cursor', 'skills'):
        raise ValueError('choose a dedicated toolkit directory')
    if root.exists() and not root.is_dir():
        raise ValueError('root is not a directory')
    return root


def payload(package, components):
    package = absolute(package)
    raw = regular(package / 'release-manifest.json')
    if raw is None: raise ValueError('missing release manifest')
    m = json.loads(raw)
    if m.get('schema_version') != 2: raise ValueError('unsupported release schema')
    names = m['components']
    selected_set = set(); visiting = set()
    def include(name):
        if name not in names: raise ValueError('unknown component')
        if name in visiting: raise ValueError('component dependency cycle')
        if name in selected_set: return
        visiting.add(name)
        deps = names[name].get('dependencies', [])
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps): raise ValueError('invalid dependencies')
        for dependency in deps: include(dependency)
        visiting.remove(name); selected_set.add(name)
    for name in ['core'] + list(components): include(name)
    selected = sorted(selected_set)
    files = {}; all_names = set()
    for e in m['files']:
        name = e['path']; relative(name)
        if name in all_names or e['component'] not in names: raise ValueError('duplicate/invalid component path')
        all_names.add(name)
        data = regular(package / name)
        if data is None or digest(data) != e['sha256']: raise ValueError('release hash mismatch')
        if e['component'] in selected: files[name] = data
    checks = regular(package / 'checksums.sha256')
    if checks is None: raise ValueError('missing checksums')
    declared = {}
    for line in checks.decode().splitlines():
        h, n = line.split('  ', 1); relative(n)
        if n in declared or not re.fullmatch('[a-f0-9]{64}',h): raise ValueError('invalid checksums')
        declared[n]=h
    expected = all_names | {'release-manifest.json'}
    if set(declared) != expected: raise ValueError('checksum inventory mismatch')
    actual = set()
    for base, dirs, names_on_disk in os.walk(package, followlinks=False):
        if Path(base)==package and '.git' in dirs:
            if (package/'.git').is_symlink(): raise ValueError('symlink in package')
            dirs.remove('.git')
        for name in dirs + names_on_disk:
            p=Path(base)/name
            if p.is_symlink(): raise ValueError('symlink in package')
            if Path(base) == package and name == '.git' and p.is_file():
                # A worktree gitfile is metadata, never a payload or a path to traverse.
                data = regular(p)
                if not re.fullmatch(rb'gitdir: [^\x00\r\n]+\n?', data):
                    raise ValueError('invalid root Git metadata file')
                continue
            if p.is_file(): actual.add(str(p.relative_to(package)))
    if actual != expected | {'checksums.sha256'}: raise ValueError('unlisted package file')
    for name,h in declared.items():
        if digest(regular(package/name)) != h: raise ValueError('checksum mismatch')
    files['release-manifest.json']=raw; files['checksums.sha256']=checks
    return m, files, selected


def current(root):
    p = root / STATE / 'installed.json'
    if not p.exists(): return {'files': {}, 'version': None, 'components': [], 'latest': None}
    obj = read_json(p)
    for name in obj['files']: relative(name)
    return obj


def write_tx(path, tx):
    clean = {k:v for k,v in tx.items() if k != 'integrity'}
    atomic(path, encode({**clean, 'integrity': digest(encode(clean))}))


def read_tx(path):
    obj = read_json(path)
    integrity = obj.pop('integrity', None)
    if integrity != digest(encode(obj)): raise ValueError('receipt integrity mismatch')
    return obj


def pending(root):
    p=root/STATE/'pending.json'
    return read_json(p)['id'] if p.exists() else None


def plan(package, root, components=()):
    root=safe_root(root); package=absolute(package)
    if root == package or root in package.parents or package in root.parents:
        raise ValueError('source and destination must not overlap')
    if pending(root): raise ValueError('unfinished transaction: rollback first')
    m, files, selected=payload(package,components); before=current(root)
    changes=[]
    for name in sorted(set(before['files']) | set(files)):
        p=absolute(root/relative(name)); old=before['files'].get(name); observed=signature(p)
        if observed != old: raise ValueError('local edit or unmanaged collision: '+name)
        for parent in p.parents:
            if parent == root: break
            if parent.exists() and not parent.is_dir(): raise ValueError('file in destination parent')
        new={'sha256':digest(files[name]),'mode':0o644} if name in files else None
        if old != new: changes.append({'path':name,'before':old,'after':new})
    data={'root':str(root),'package':str(package),'release_sha256':digest(encode(m)),
          'version':m['version'],'components':selected,'before':before,'changes':changes,
          'files':{n:{'sha256':digest(b),'mode':0o644} for n,b in files.items()}}
    return {'plan_id':digest(encode(data)),'status':'NOOP' if not changes else 'PLANNED',**data}


def atomic(p, data, mode=0o600):
    p=absolute(p); p.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.kit-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),mode)
        os.replace(name,p)
        dfd=os.open(p.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if os.path.exists(name):os.unlink(name)


@contextmanager
def lock(root):
    root=safe_root(root);root.mkdir(parents=True,exist_ok=True)
    d=absolute(root/STATE); d.mkdir(mode=0o700,exist_ok=True)
    s=d.stat()
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode)&0o077: raise ValueError('state directory must be private and owned')
    p=absolute(d/'lock');fd=os.open(p,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


def guarded_write(path, expected, desired, data):
    path=absolute(path)
    if signature(path) != expected: raise ValueError('concurrent edit: '+path.name)
    if desired is None:
        path.unlink()
        dfd=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
        return
    if digest(data) != desired['sha256']: raise ValueError('invalid replacement bytes')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.kit-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),desired['mode'])
        if signature(path) != expected: raise ValueError('concurrent edit before replace')
        if expected is None:
            os.link(temp,path)  # atomic no-clobber publication for additions
        else:
            os.replace(temp,path)  # guarded, coordinated writer window required
        if os.path.exists(temp): os.unlink(temp)
        if signature(path) != desired: raise ValueError('post-write mismatch')
        dfd=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def instruction_barrier(root):
    """Registered instructions require the outer transaction, never a CLI bypass."""
    root = safe_root(root)
    state = root / STATE
    if any((state / name).exists() for name in ('instruction-registration.json', 'instruction-update-pending.json')):
        context = globals().get('_instruction_context')
        pending_path = state / 'instruction-update-pending.json'
        if (not isinstance(context, tuple) or len(context) != 2 or context[0] != str(root)
                or not pending_path.exists() or read_json(pending_path) != {'id': context[1]}):
            raise ValueError('registered instructions require owned outer update/rollback')


def apply(package, root, components, expected_plan):
    instruction_barrier(root)
    # Validate without writes first. A later locked recheck protects against stale plans.
    pre=plan(package,root,components)
    if pre['plan_id']!=expected_plan:raise ValueError('stale or wrong plan')
    if pre['status']=='NOOP':return {'status':'NOOP','plan_id':expected_plan}
    with lock(root):
        p=plan(package,root,components)
        if p['plan_id']!=expected_plan:raise ValueError('plan changed before lock')
        _,files,_=payload(package,components)
        root=Path(root);state=root/STATE;txid=uuid.uuid4().hex
        tx={'id':txid,'status':'APPLYING','plan':p,'applied':[],'before':p['before']}
        txn=state/'receipts'/str(txid+'.json');objdir=state/'objects';objdir.mkdir(exist_ok=True)
        # Back up all changed originals before any payload write.
        for e in p['changes']:
            if e['before']:
                b=regular(root/e['path'])
                if digest(b)!=e['before']['sha256']:raise ValueError('baseline changed')
                target=objdir/e['before']['sha256']
                if target.exists():
                    if digest(regular(target))!=target.name:raise ValueError('corrupt backup')
                else:atomic(target,b)
        write_tx(txn,tx);atomic(state/'pending.json',encode({'id':txid}))
        for e in p['changes']:
            guarded_write(root/e['path'],e['before'],e['after'],files.get(e['path']))
            tx['applied'].append(e['path']);write_tx(txn,tx)
        installed={'files':p['files'],'version':p['version'],'components':p['components'],'latest':txid}
        atomic(state/'installed.json',encode(installed))
        tx['status']='APPLIED';write_tx(txn,tx);(state/'pending.json').unlink()
        return {'status':'APPLIED','transaction':txid,'receipt':str(txn),'plan_id':expected_plan}


def rollback_plan(root, txid):
    root=safe_root(root)
    if not re.fullmatch('[a-f0-9]{32}',txid):raise ValueError('invalid transaction id')
    tx=read_tx(root/STATE/'receipts'/(txid+'.json'))
    if tx['id']!=txid or tx['plan']['root']!=str(root):raise ValueError('receipt/root mismatch')
    if tx['status']=='ROLLED_BACK':return {'status':'NOOP','transaction':txid,'changes':[]}
    if txid not in (current(root)['latest'],pending(root)):raise ValueError('rollback must target latest/pending transaction')
    changes=[]
    for e in reversed(tx['plan']['changes']):
        relative(e['path']);now=signature(root/e['path'])
        if now==e['before']:continue  # never written or already restored after interruption
        if now!=e['after']:raise ValueError('concurrent change blocks rollback: '+e['path'])
        if e['before']:
            b=regular(root/STATE/'objects'/e['before']['sha256'])
            if b is None or digest(b)!=e['before']['sha256']:raise ValueError('missing/corrupt backup')
        changes.append(e)
    result={'status':'PLANNED','transaction':txid,'changes':changes,'before':tx['before']}
    result['plan_id']=digest(encode(result));return result


def rollback(root,txid,expected_plan):
    instruction_barrier(root)
    pre=rollback_plan(root,txid)
    if pre['status']=='NOOP':
        if pending(root)==txid:
            with lock(root):
                tx=read_tx(Path(root)/STATE/'receipts'/(txid+'.json'))
                if current(root)!=tx['before']:raise ValueError('rollback state mismatch')
                (Path(root)/STATE/'pending.json').unlink()
        return pre
    if pre['plan_id']!=expected_plan:raise ValueError('stale rollback plan')
    with lock(root):
        p=rollback_plan(root,txid)
        if p.get('plan_id')!=expected_plan:raise ValueError('rollback state changed')
        root=Path(root);state=root/STATE
        atomic(state/'pending.json',encode({'id':txid}))
        for e in p['changes']:
            data=regular(state/'objects'/e['before']['sha256']) if e['before'] else None
            guarded_write(root/e['path'],e['after'],e['before'],data)
        atomic(state/'installed.json',encode(p['before']))
        txn=state/'receipts'/(txid+'.json');tx=read_tx(txn);tx['status']='ROLLED_BACK';write_tx(txn,tx)
        if pending(root)==txid:(state/'pending.json').unlink()
        return {'status':'ROLLED_BACK','transaction':txid}


def blocked_reason(exc):
    # Specific, actionable category WITHOUT echoing any path, name or file content.
    if isinstance(exc, json.JSONDecodeError):
        return 'MALFORMED_JSON: a manifest, checksum or receipt file is not valid JSON.'
    if isinstance(exc, OSError):
        return 'IO_ERROR: a filesystem operation failed; inspect the receipt and permissions, do not force.'
    if isinstance(exc, (KeyError, TypeError)):
        return 'MALFORMED_METADATA: required manifest/receipt fields are missing or the wrong type.'
    msg = str(exc)
    # A hand-edited instruction target: re-emit only a strictly matched suffix (position, fixed recipe name, hash prefixes).
    edited = 'instruction user edit blocks rollback'
    if msg.startswith(edited):
        reason = ('INSTRUCTION_TARGET_EDITED: a managed instruction target differs from both recorded states; '
                  'put it back to the expected bytes (docs/managed-kit-connections.md), then re-plan.')
        m = re.fullmatch(edited + r': (target \d+ recipe [a-z0-9-]+ sha256 (?:[0-9a-f]{12}|none) expected '
                         r'(?:[0-9a-f]{12}|none)(?: or (?:[0-9a-f]{12}|none))?)', msg)
        return reason + (' ' + m.group(1) if m else '')
    groups = [
        (('explicit canonical absolute path required', 'symlink refused', 'noncanonical release path',
          'invalid release path', 'sensitive/reserved release path', 'choose a dedicated toolkit directory',
          'root is not a directory', 'source and destination must not overlap', 'file in destination parent'),
         'UNSAFE_OR_INVALID_PATH: a path is non-canonical, a symlink, reserved, or source/destination overlap; fix the path, do not weaken the guard.'),
        (('stale or wrong plan', 'plan changed before lock', 'plan never executes', 'stale rollback plan',
          'rollback state changed', 'plan id and exclusive writer window required'),
         'STALE_OR_MISSING_PLAN: recompute the plan and re-run with the fresh --plan-id and --exclusive-window.'),
        (('unfinished transaction: rollback first',),
         'UNFINISHED_TRANSACTION: a previous transaction did not finish; roll it back before planning again.'),
        (('local edit or unmanaged collision',),
         'LOCAL_EDIT_COLLISION: a managed file was modified or an unmanaged file is in the way; reconcile it before install/update.'),
        (('concurrent edit', 'concurrent change blocks rollback', 'post-write mismatch', 'invalid replacement bytes',
          'baseline changed', 'corrupt backup', 'missing/corrupt backup'),
         'CONCURRENT_OR_CORRUPT_STATE: files changed under the operation or a backup is missing/corrupt; do not force, inspect the receipt.'),
        (('use update for managed installation',),
         'ALREADY_INSTALLED: this root already has a managed install; use "update" instead of "install".'),
        (('use install for new destination',),
         'NOT_INSTALLED: this root has no managed install yet; use "install" instead of "update".'),
        (('transaction required', 'invalid transaction id', 'receipt/root mismatch',
          'rollback must target latest/pending transaction', 'rollback state mismatch', 'receipt integrity mismatch'),
         'INVALID_TRANSACTION: the transaction id/receipt does not match this root or is not the latest/pending one.'),
        (('state directory must be private and owned',),
         'STATE_PERMISSIONS: the .ai-factory-state directory must be private (0700) and owned by the current user.'),
        (('missing release manifest', 'unsupported release schema', 'unknown component', 'component dependency cycle',
          'invalid dependencies', 'duplicate/invalid component path', 'release hash mismatch', 'missing checksums',
          'invalid checksums', 'checksum inventory mismatch', 'unlisted package file', 'checksum mismatch',
          'symlink in package', 'invalid root Git metadata file', 'missing metadata',
          'nonregular/hardlinked/oversized file refused', 'package required'),
         'INVALID_PACKAGE: the release package failed integrity/inventory verification; re-export or re-fetch it.'),
    ]
    for needles, reason in groups:
        if any(msg.startswith(n) for n in needles):
            return reason
    return 'INVALID_OR_UNSAFE_INPUT: validation rejected the input/state; inspect the receipt without forcing.'


def main():
    if sys.argv[1:2]==['project']:
        # One project list: tools/projects.py (list/install/remove/migrate); no barrier, own lock and backups.
        import importlib.util
        ps=importlib.util.spec_from_file_location('_factory_projects',Path(__file__).absolute().parent/'projects.py')
        projects=importlib.util.module_from_spec(ps);ps.loader.exec_module(projects)
        return projects.main(sys.argv[2:])
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',nargs='?',default='plan',choices=['plan','install','update','rollback'])
    ap.add_argument('--package',type=Path);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--component',action='append',default=[])
    ap.add_argument('--transaction');ap.add_argument('--plan-id')
    ap.add_argument('--capture-spec',type=Path,help='explicit initial global Claude capture registration; subsequent updates reconcile the pinned registration')
    ap.add_argument('--instruction-spec',type=Path,help='explicit initial exact legacy-instruction migration; later normal updates reconcile pinned scope')
    ap.add_argument('--execute',action='store_true')
    ap.add_argument('--exclusive-window',action='store_true',help='confirm no uncoordinated writer during apply/restore')
    a=ap.parse_args()
    try:
        # This optional companion never activates unless explicitly selected once.
        import importlib.util
        companion_path=Path(__file__).absolute().parent/'capture_update.py'
        capture=None
        if companion_path.exists():
            cs=importlib.util.spec_from_file_location('_factory_capture_update',companion_path)
            capture=importlib.util.module_from_spec(cs);cs.loader.exec_module(capture)
        registered = a.capture_spec is not None or (a.root/STATE/'capture-registration.json').exists() or (a.root/STATE/'capture-update-pending.json').exists()
        if registered and capture is None:raise ValueError('capture update companion missing')
        if a.capture_spec and a.action not in ('plan','update'):raise ValueError('capture registration requires update')
        instruction_path=Path(__file__).absolute().parent/'instruction_update.py'
        instructions=None
        instruction_registered = a.instruction_spec is not None or any((a.root/STATE/n).exists() for n in ('instruction-registration.json','instruction-update-pending.json'))
        if instruction_registered:
            if not instruction_path.exists(): raise ValueError('instruction update companion missing')
            ins=importlib.util.spec_from_file_location('_factory_instruction_update',instruction_path)
            instructions=importlib.util.module_from_spec(ins);ins.loader.exec_module(instructions)
            if a.instruction_spec is not None and a.action not in ('plan','update'):
                raise ValueError('instruction registration requires update')
        # Rolled-back outer transactions remain addressable after registration restoration.
        if a.action=='rollback' and not instructions and instruction_path.exists():
            ins=importlib.util.spec_from_file_location('_factory_instruction_update',instruction_path)
            candidate=importlib.util.module_from_spec(ins);ins.loader.exec_module(candidate)
            if candidate.is_transaction(sys.modules[__name__],a.root,a.transaction): instructions=candidate
        if instructions:
            if a.action=='rollback':
                if not a.transaction or not instructions.is_transaction(sys.modules[__name__],a.root,a.transaction):
                    raise ValueError('registered instructions require outer rollback transaction')
                out=instructions.rollback_plan(sys.modules[__name__],a.root,a.transaction)
                if a.execute:
                    if not a.exclusive_window or not a.plan_id: raise ValueError('plan id and exclusive writer window required')
                    out=instructions.rollback(sys.modules[__name__],a.root,a.transaction,a.plan_id,True)
            else:
                if not a.package: raise ValueError('package required')
                out=instructions.plan(sys.modules[__name__],a.package,a.root,a.component,a.instruction_spec,a.capture_spec)
                if a.execute:
                    if a.action!='update' or not current(a.root)['files']: raise ValueError('instruction migration requires installed update')
                    if not a.exclusive_window or not a.plan_id: raise ValueError('plan id and exclusive writer window required')
                    out=instructions.apply(sys.modules[__name__],a.package,a.root,a.component,a.instruction_spec,a.capture_spec,a.plan_id,True)
            print(json.dumps(instructions.public(out),indent=2));return 1 if out.get('status')=='BLOCKED' else 0
        if a.action=='rollback':
            if not a.transaction:raise ValueError('transaction required')
            combined=capture is not None and capture.is_transaction(sys.modules[__name__],a.root,a.transaction)
            out=capture.rollback_plan(sys.modules[__name__],a.root,a.transaction) if combined else rollback_plan(a.root,a.transaction)
            if registered and not combined:raise ValueError('registered capture requires combined update rollback transaction')
            if a.execute:
                if not a.exclusive_window or not a.plan_id:raise ValueError('plan id and exclusive writer window required')
                out=capture.rollback(sys.modules[__name__],a.root,a.transaction,a.plan_id,a.exclusive_window) if combined else rollback(a.root,a.transaction,a.plan_id)
        else:
            if not a.package:raise ValueError('package required')
            out=capture.plan(sys.modules[__name__],a.package,a.root,a.component,a.capture_spec) if registered else plan(a.package,a.root,a.component)
            if a.execute:
                if a.action=='plan':raise ValueError('plan never executes')
                if not a.exclusive_window or not a.plan_id:raise ValueError('plan id and exclusive writer window required')
                if a.action=='install' and current(a.root)['files'] and out['status']!='NOOP':raise ValueError('use update for managed installation')
                if a.action=='update' and not current(a.root)['files']:raise ValueError('use install for new destination')
                out=capture.apply(sys.modules[__name__],a.package,a.root,a.component,a.capture_spec,a.plan_id,a.exclusive_window) if registered else apply(a.package,a.root,a.component,a.plan_id)
        print(json.dumps(capture.public(out) if capture else out,indent=2));return 1 if out.get('status')=='BLOCKED' else 0
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':blocked_reason(exc)}));return 1


if __name__=='__main__':sys.exit(main())
