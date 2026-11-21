#!/usr/bin/env python3
"""Socket-free primitives for Docker-only preparation. No daemon or subprocess access."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sys

# -I deliberately excludes script directory. Only this reviewed RO module directory is added.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scanner as s
import update_db as u


def host_path(value):
    """Lexical host identity only: host shell checks filesystem ancestors."""
    s.need(isinstance(value, str) and value.startswith('/') and value != '/', 'host path required')
    s.need(not any(c in value for c in '\t\n\r,$') and '\x00' not in value, 'unsafe host path')
    s.need(all(p not in ('', '.', '..') for p in value.split('/')[1:]), 'noncanonical host spelling')
    return value


def identity(uid, gid):
    s.need(type(uid) is int and type(gid) is int and 0 < uid < 2**31 and 0 <= gid < 2**31,
           'explicit nonroot UID/GID required')
    return str(uid) + ':' + str(gid)


def relative(name):
    s.need(isinstance(name, str) and name and not any(c in name for c in '\t\n\r,$\x00'), 'unsafe selected name')
    p = PurePosixPath(name)
    s.need(not p.is_absolute() and str(p) == name and all(x not in ('.', '..') and not x.startswith('.') for x in p.parts), 'unsafe selected name')
    return name


def plan(config, uid, gid):
    s.need(config.get('schema_version') == 1 and config.get('sanitized_inputs_reviewed') is True, 'input attestation required')
    root = host_path(config['root']); selected = config['files']
    # Host namespace comparison is lexical after shell ancestor checks, never container resolve().
    roots=[PurePosixPath(root)]+[PurePosixPath(host_path(config[k])) for k in ('reports','db_store') if k in config]
    for i,a in enumerate(roots):
        for b in roots[i+1:]: s.need(a!=b and a not in b.parents and b not in a.parents,'host roots overlap')
    s.need(isinstance(selected, dict) and 0 < len(selected) <= 2000, 'bounded input allowlist required')
    mounts = []
    for i, (name, digest) in enumerate(sorted(selected.items())):
        relative(name)
        s.need(isinstance(digest, str) and s.SHA.fullmatch(digest), 'invalid hash')
        mounts.append({'host': host_path(root + '/' + name), 'local': '/input/' + str(i).zfill(6), 'name': name, 'sha256': digest})
    return {'schema_version': 1, 'user': identity(uid, gid), 'inputs': mounts,
            'host_ancestor_check': 'REQUIRED_BEFORE_CREATE', 'hostile_same_user_race': 'NOT_PREVENTED'}


def stage(config, mapping, destination, input_base=Path('/input')):
    s.need(mapping == plan(config, *map(int, mapping['user'].split(':'))), 'mapping drift')
    destination = s.canonical(str(destination), exists=False)
    s.need(not destination.exists(), 'fresh stage required')
    destination.mkdir(mode=0o700)
    total = 0
    try:
        for item in mapping['inputs']:
            source = s.regular(input_base / Path(item['local']).name, s.MAX_FILE)
            total += source.stat().st_size
            s.need(total <= s.MAX_TOTAL and s.sha(source) == item['sha256'], 'input hash/size mismatch')
            target = destination / item['name']; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out, source.open('rb') as incoming:
                while chunk := incoming.read(65536): out.write(chunk)
            s.need(s.sha(target) == item['sha256'] and s.sha(source) == item['sha256'], 'input changed during copy')
            target.chmod(0o444)
        local = dict(config, root=str(destination))
        s.source_files(local)  # secret pattern, extension, Yarn pair/dev coverage retained
        for p in destination.rglob('*'):
            if p.is_dir(): p.chmod(0o555)
        destination.chmod(0o555)
        return {'staged': True, 'files': config['files']}
    except BaseException:
        # Failed stage is retained, never presented as accepted; coordinator owns exact cleanup.
        raise


def verify_host_inspect(obj, service, image_id):
    """Reuse verifier without resolving HOST path strings in container namespace."""
    expected = service['volumes']
    actual = obj.get('Mounts', [])
    expected_set = {(host_path(v['source']), v['target'], not v['read_only']) for v in expected}
    binds = [v for v in actual if v['Type'] == 'bind']
    s.need(len(binds) == len(expected_set) == len(expected), 'duplicate/missing bind')
    s.need({(host_path(v['Source']), v['Destination'], v['RW']) for v in binds} == expected_set, 'host bind mismatch')
    s.verify_container(obj, service, image_id, path_identity=host_path)


def terminal(state):
    s.need(isinstance(state, dict) and state.get('Status') == 'exited' and state.get('Running') is False
           and state.get('OOMKilled') is False and state.get('Dead') is False and state.get('Error') == ''
           and type(state.get('ExitCode')) is int, 'terminal state incomplete/unsafe')
    return state['ExitCode']


def acquire_lease(store, token, intent):
    store = s.store_root(str(store)); s.need(re.fullmatch('[a-f0-9]{64}', token) is not None, 'invalid owner token')
    s.need(isinstance(intent, dict) and re.fullmatch('factory-db-[a-f0-9]{32}', intent.get('container_name', '')), 'exact container intent required')
    lease = store / '.update-lease'; s.canonical(str(lease), exists=False)
    lease.mkdir(mode=0o700)  # Atomic exclusion. Failure after this leaves lease; never auto-reclaim.
    u.exclusive_json(lease / 'owner.json', {'token': token, 'intent': intent})
    return lease


def check_lease(store, token):
    lease = s.canonical(str(store / '.update-lease'))
    owner = s.read_json(lease / 'owner.json')
    s.need(owner.get('token') == token, 'lease owned by someone else')
    s.need({p.name for p in lease.iterdir()} == {'owner.json'}, 'unexpected lease contents')
    return lease


def release_lease(store, token, cleanup, result_path):
    lease = check_lease(store, token)
    s.need(cleanup == {'removed': True, 'uncertain': False}, 'cleanup not confirmed')
    result = s.read_json(result_path)
    s.need(result.get('owner_token') == token and result.get('terminal') is True, 'durable owner result required')
    (lease / 'owner.json').unlink(); lease.rmdir()


def publish(store, token, cache, manifest, state, removed):
    store = s.store_root(str(store)); check_lease(store, token)
    s.need(terminal(state) == 0 and removed is True, 'updater not successfully removed')
    cache = s.canonical(str(cache))
    s.need(cache.parent == store / ('download-' + token) and cache.name == 'cache', 'nonowned cache')
    u.validate_download(cache)
    budget(cache)
    files = {n: s.sha(s.regular(cache / n)) for n in ('db/trivy.db', 'db/metadata.json')}
    snapshot = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    staging = cache.parent / 'staging'; staging.mkdir(mode=0o700)
    u.exclusive_json(staging / 'owner.json', {'owner': 'AI Factory', 'schema_version': 1})
    candidate = staging / snapshot; cache.rename(candidate)
    u.exclusive_json(candidate / 'snapshot.json', {'schema_version': 1, 'engine_image': manifest['engines']['trivy']['image'],
                     'db_source': manifest['db']['repository'], 'files': files})
    for p in candidate.rglob('*'): p.chmod(0o555 if p.is_dir() else 0o444)
    candidate.chmod(0o555); s.validate_snapshot(staging, snapshot, manifest)
    check_lease(store, token)
    destination = s.canonical(str(store / snapshot), exists=False)
    if destination.exists():
        s.validate_snapshot(store, snapshot, manifest)
        # Only the validated duplicate in this owner-token staging tree is disposable.
        # Never remove the accepted destination or an uncertain download.
        check_lease(store, token)
        s.canonical(str(candidate))
        u.remove_private_tree(candidate)
        s.need(not candidate.exists(), 'duplicate removal not confirmed')
        s.validate_snapshot(store, snapshot, manifest)
        return {'status': 'NOOP', 'snapshot': snapshot, 'duplicate_removed': True}
    # Match existing updater portability: macOS-backed bind rename requires source directory write.
    # Readers reject this brief unsealed directory; all DB files remain0444.
    candidate.chmod(0o755)
    moved=False
    try:
        candidate.rename(destination); moved=True
        destination.chmod(0o555)
        s.validate_snapshot(store, snapshot, manifest)
    except BaseException:
        try: (destination if moved else candidate).chmod(0o555)
        except OSError: pass  # Primary remains; retained lease prevents success/retry assumptions.
        raise
    return {'status': 'SNAPSHOT_CREATED', 'snapshot': snapshot}


def dump(path, value):
    u.exclusive_json(Path(path), value)


def check_image(obj, pin):
    s.need(obj['Os'] == 'linux' and obj['Architecture'] == 'amd64' and pin in obj['RepoDigests'], 'image identity/platform mismatch')
    s.need(obj['Size'] <= 2 * 1024**3, 'image soft threshold exceeded')
    return obj['Id']


def budget(work, store=None):
    import shutil
    s.need(shutil.disk_usage(work).free >= 10 * 1024**3, '10GiB reserve missing')
    # Distinct per-object thresholds, never the old25GiB build budget.
    for root in [work] + ([store] if store is not None else []):
        total = 0
        for p in root.rglob('*'):
            s.canonical(str(p))
            if p.is_file(): total += s.regular(p).stat().st_size
            else: s.need(p.is_dir(), 'unexpected resource object')
            s.need(total <= 2 * 1024**3, '2GiB per work/store threshold exceeded')


def runtime_result(name, cid, work, selected):
    """Runtime state/output failure is ERROR, never an input-preflight BLOCKED."""
    result={'status':'ERROR','exit_code':None,'container_id':cid}
    try:
        objects=s.read_json(work/(name+'-terminal.json'))
        s.need(isinstance(objects,list) and len(objects)==1 and isinstance(objects[0],dict),'invalid terminal inspect shape')
        obj=objects[0];state=obj.get('State')
        s.need(isinstance(state,dict),'invalid terminal State shape')
        if type(state.get('ExitCode')) is int: result['exit_code']=state['ExitCode']
        s.need(obj.get('Id')==cid,'terminal CID mismatch')
        code=terminal(state)
        if code != 0:
            result['reason']='engine exited nonzero; report not required to classify failure'
            return result
        report=s.read_json(work/'reports'/(name+'.json'))
        result['status']=s.classify(name,report,code,selected,work/'source')
        if result['status']=='ERROR': result['reason']='invalid runtime report or coverage'
    except (s.Blocked,OSError,ValueError,KeyError,TypeError,IndexError,AttributeError) as error:
        result['reason']=(type(error).__name__+': '+str(error))[:2048]
    return result


def verify_classification(work, token):
    """Independent helper phase: a process exit1 alone can never authorize FINDINGS."""
    s.need(isinstance(token,str) and s.SHA.fullmatch(token),'classification owner token missing')
    result=s.read_json(work/'result-pending-cleanup.json')
    s.need(isinstance(result,dict) and result.get('owner_token')==token,'invalid classification owner/artifact')
    engines=result.get('engines');verified=s.read_json(work/'verified.json')
    s.need(isinstance(engines,dict) and set(engines)=={'semgrep','trivy'} and isinstance(verified,dict) and set(verified)==set(engines),'invalid classification engines')
    statuses=[]
    for name,item in engines.items():
        s.need(isinstance(item,dict) and item.get('container_id')==verified[name] and isinstance(verified[name],str) and verified[name],'invalid classification engine identity')
        status=item.get('status');code=item.get('exit_code')
        s.need(status in ('CLEAN','FINDINGS','ERROR') and (code is None or type(code) is int),'invalid engine classification')
        s.need(status=='ERROR' or type(code) is int and code==0,'successful classification with failing engine')
        statuses.append(status)
    aggregate='ERROR' if 'ERROR' in statuses else ('FINDINGS' if 'FINDINGS' in statuses else 'CLEAN')
    s.need(result.get('status')==aggregate,'classification aggregate mismatch')
    plan=s.read_json(work/'plan.json')
    s.need(isinstance(plan,dict) and isinstance(plan.get('config'),dict) and isinstance(result.get('snapshot'),str) and s.SHA.fullmatch(result['snapshot']) and result['snapshot']==plan['config'].get('db_snapshot'),'classification snapshot mismatch')
    return s.EXIT[aggregate]


def cli(argv=None):
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['plan','stage','verify','finalize','verify-result','lease','update-verify','publish','release'])
    ap.add_argument('--host-work',required=True);ap.add_argument('--host-store');ap.add_argument('--compose-sha');ap.add_argument('--token')
    args=ap.parse_args(argv);hw=host_path(args.host_work);work=Path('/work');m=s.load_manifest();budget(work)
    user=identity(os.getuid(),os.getgid())
    if args.phase=='plan':
        c=s.read_json(Path('/config'));mapping=plan(c,os.getuid(),os.getgid())
        s.need(c['reports']==hw+'/reports','reports must be fresh run/reports')
        host_path(c['db_store']);s.need(s.SHA.fullmatch(c['db_snapshot']) is not None,'invalid snapshot')
        s.need(args.compose_sha and s.SHA.fullmatch(args.compose_sha) and s.sha(s.regular(Path('/compose-bin'),64*1024**2))==args.compose_sha,'Compose binary hash mismatch')
        dump(work/'plan.json',{'config':c,'mapping':mapping,'host_work':hw,'user':user})
        (work/'mounts.tsv').write_text(''.join(x['host']+'\t'+x['local']+'\n' for x in mapping['inputs']))
        (work/'store.txt').write_text(c['db_store']+'\n')
        (work/'snapshot.txt').write_text(c['db_snapshot']+'\n')
        (work/'images.tsv').write_text(''.join(k+'\t'+m['engines'][k]['image']+'\n' for k in ('semgrep','trivy')))
    elif args.phase=='stage':
        p=s.read_json(work/'plan.json');s.need(p['host_work']==hw and p['user']==user,'run identity drift')
        c=p['config'];stage(c,p['mapping'],work/'source');s.stage_rules(m,work/'rules')
        db,meta=s.validate_snapshot('/store',c['db_snapshot'],m)
        (work/'reports').mkdir(mode=0o700)
        doc=s.render(m,Path(hw)/'source',Path(hw)/'rules',Path(c['db_store'])/c['db_snapshot'],Path(hw)/'reports')
        for service in doc['services'].values():
            service['logging']={'driver':'local','options':{'max-size':'1m','max-file':'1','compress':'false'}}
        s.need(args.token and s.SHA.fullmatch(args.token), 'run token required')
        for name, service in doc['services'].items():
            service['container_name']='factory-scan-'+args.token[:32]+'-'+name
            service['labels']={'ai-factory.run':args.token}
        dump(work/'compose.json',doc);dump(work/'snapshot-before.json',meta)
    elif args.phase=='verify':
        doc=s.read_json(work/'compose.json');verified={}
        for name,service in doc['services'].items():
            image=s.read_json(work/(name+'-image.json'))[0]
            image_id=check_image(image,service['image'])
            obj=s.read_json(work/(name+'-inspect.json'))[0]
            s.need(obj['State']['Status']=='created' and not obj['State']['Running'],'engine already started')
            s.need(obj['Config'].get('Labels',{}).get('ai-factory.run')==args.token,'container owner mismatch')
            verify_host_inspect(obj,service,image_id)
            s.need(obj['HostConfig']['LogConfig']=={'Type':'local','Config':{'max-size':'1m','max-file':'1','compress':'false'}},'log bounds mismatch')
            verified[name]=obj['Id']
        dump(work/'verified.json',verified)
    elif args.phase=='finalize':
        p=s.read_json(work/'plan.json');c=p['config'];states={};statuses=[]
        # Recheck originals through per-file binds, not whole product root.
        for x in p['mapping']['inputs']:
            s.need(s.sha(s.regular(Path(x['local']),s.MAX_FILE))==x['sha256'],'original input drift')
        _,meta=s.validate_snapshot('/store',c['db_snapshot'],m)
        s.need(meta==s.read_json(work/'snapshot-before.json'),'snapshot drift')
        verified=s.read_json(work/'verified.json')
        s.need(isinstance(verified,dict) and set(verified)=={'semgrep','trivy'} and all(isinstance(cid,str) and cid for cid in verified.values()),'invalid verified identity map')
        for name,cid in verified.items():
            result=runtime_result(name,cid,work,c['files'])
            states[name]=result;statuses.append(result['status'])
        status='ERROR' if 'ERROR' in statuses else ('FINDINGS' if 'FINDINGS' in statuses else 'CLEAN')
        dump(work/'result-pending-cleanup.json',{'status':status,'engines':states,'snapshot':c['db_snapshot'],'owner_token':args.token})
        return s.EXIT[status]
    elif args.phase=='verify-result':
        code=verify_classification(work,args.token)
        receipt=work/'classification-verified.txt'
        with receipt.open('x') as stream: stream.write(args.token+'|'+str(code)+'\n')
    elif args.phase=='lease':
        store=Path('/store');host_path(args.host_store)
        import shutil
        s.need(shutil.disk_usage(store).free >= 10*1024**3,'10GiB store reserve missing')
        s.need(args.token and s.SHA.fullmatch(args.token),'invalid token')
        acquire_lease(store,args.token,{'container_name':'factory-db-'+args.token[:32]})
        cache=store/('download-'+args.token)/'cache';cache.mkdir(parents=True,mode=0o700)
        cmd=['fs','--download-db-only','--db-repository',m['db']['repository'],'--cache-dir','/cache','--disable-telemetry']
        dump(work/'updater.json',{'image':m['engines']['trivy']['image'],'command':cmd,'cache':host_path(args.host_store)+'/download-'+args.token+'/cache'})
        (work/'db-pin.txt').write_text(m['db']['repository']+'\n')
        (work/'trivy-pin.txt').write_text(m['engines']['trivy']['image']+'\n')
    elif args.phase=='update-verify':
        record=s.read_json(work/'updater.json');obj=s.read_json(work/'updater-inspect.json')[0];image=s.read_json(work/'trivy-image.json')[0]
        s.need(obj['State']['Status']=='created','updater already started')
        s.need(obj['Config'].get('Labels',{}).get('ai-factory.run')==args.token,'updater owner mismatch')
        binds=[v for v in obj['Mounts'] if v['Type']=='bind']
        s.need(len(binds)==1 and binds[0]['Source']==record['cache'],'updater host cache mismatch')
        u.verify_updater(obj,check_image(image,record['image']),record['image'],record['cache'],record['command'],path_identity=host_path)
        s.need(obj['HostConfig']['LogConfig']=={'Type':'local','Config':{'max-size':'1m','max-file':'1','compress':'false'}},'log bounds mismatch')
        dump(work/'updater-verified.json',{'cid':obj['Id']})
    elif args.phase=='publish':
        obj=s.read_json(work/'updater-terminal.json')[0]
        s.need(obj['Id']==s.read_json(work/'updater-verified.json')['cid'],'updater terminal CID mismatch')
        s.need((work/'updater-removed').read_text()=='CONFIRMED\n','updater removal unknown')
        result=publish(Path('/store'),args.token,Path('/store')/('download-'+args.token)/'cache',m,obj['State'],True)
        dump(work/'update-result.json',dict(result,owner_token=args.token,terminal=True))
    elif args.phase=='release':
        release_lease(Path('/store'),args.token,{'removed':True,'uncertain':False},work/'update-result.json')
    return 0


if __name__=='__main__':
    try: raise SystemExit(cli())
    except (s.Blocked,OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)[:2048]}),file=sys.stderr)
        raise SystemExit(3)
