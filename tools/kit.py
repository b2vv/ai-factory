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
    selected = sorted(set(['core'] + list(components)))
    if not set(selected) <= set(names): raise ValueError('unknown component')
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
        if Path(base)==package and '.git' in dirs: dirs.remove('.git')
        for name in dirs + names_on_disk:
            p=Path(base)/name
            if p.is_symlink(): raise ValueError('symlink in package')
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


def apply(package, root, components, expected_plan):
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


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',nargs='?',default='plan',choices=['plan','install','update','rollback'])
    ap.add_argument('--package',type=Path);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--component',action='append',default=[])
    ap.add_argument('--transaction');ap.add_argument('--plan-id')
    ap.add_argument('--execute',action='store_true')
    ap.add_argument('--exclusive-window',action='store_true',help='confirm no uncoordinated writer during apply/restore')
    a=ap.parse_args()
    try:
        if a.action=='rollback':
            if not a.transaction:raise ValueError('transaction required')
            out=rollback_plan(a.root,a.transaction)
            if a.execute:
                if not a.exclusive_window or not a.plan_id:raise ValueError('plan id and exclusive writer window required')
                out=rollback(a.root,a.transaction,a.plan_id)
        else:
            if not a.package:raise ValueError('package required')
            out=plan(a.package,a.root,a.component)
            if a.execute:
                if a.action=='plan':raise ValueError('plan never executes')
                if not a.exclusive_window or not a.plan_id:raise ValueError('plan id and exclusive writer window required')
                if a.action=='install' and current(a.root)['files'] and out['status']!='NOOP':raise ValueError('use update for managed installation')
                if a.action=='update' and not current(a.root)['files']:raise ValueError('use install for new destination')
                out=apply(a.package,a.root,a.component,a.plan_id)
        print(json.dumps(out,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError):
        print(json.dumps({'status':'BLOCKED','reason':'invalid/stale input, unsafe path, conflict, lock or IO failure; preserve receipt and inspect without forcing'}));return 1


if __name__=='__main__':sys.exit(main())
