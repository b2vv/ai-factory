"""One task-specific pilot launcher. Execution requires separate review and owner grant."""
import argparse,hashlib,io,json,os,re,select,shutil,stat,subprocess,sys,tarfile,time,signal
from pathlib import Path
import bounded_command
IMAGE='docker.io/library/alpine@sha256:1f3591b8a02ea153f41c5bba878ad477f63ab3d19349762cb77504db02a23e15'
IMAGE_ID='sha256:f6d31b983274a75183386cda3aac54849498fac0fc3e0d98f92ff56ed517d92b'
ARCHIVE_SHA='be58ce9c2b00934cb5907f09483c6848b3777006154c30f62b1d0db624ce4f3e'
PKG=Path(__file__).resolve().parent
FILES=['build.sh','curl-shim','ledger.py','git-pins.txt','fix_curl.py','tar-preflight.sh','tar-foreign-owner.tar.gz']
EXPORTS={'tar-preflight.txt':65536,'curl-recipe-patch.json':65536,'compiler.txt':65536,'semgrep-version.txt':65536,'opam-installed.txt':1048576,'apk-installed.txt':1048576,'pip-inspect.json':1048576,'cache-ledger.jsonl':8388608,'cache-summary.json':65536,'python-license-metadata.json':1048576}
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(65536),b''):d.update(c)
 return d.hexdigest()
def regular(p):
 for q in [p,*p.parents]:
  if q.is_symlink():raise ValueError('symlink path')
 s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:raise ValueError('not single-link regular')
def decode_export(raw,name,limit):
 # Standard parser over already capped daemon-created transport tar, no extraction.
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
  entries=tf.getmembers()
  if len(entries)!=1:raise ValueError('export member count')
  m=entries[0]
  if m.name!=name or not m.isfile() or m.linkname or not 0<=m.size<=limit:raise ValueError('unsafe export member')
  f=tf.extractfile(m);data=f.read(limit+1)
  if len(data)!=m.size:raise ValueError('export size mismatch')
  return data
class Runner:
 def __init__(self,root):
  self.root=root;self.count=0;self.uncertain_cids=set();self.diagnostic_errors=[]
  self.env={'PATH':'/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin','HOME':str(root/'home'),'PYTHONDONTWRITEBYTECODE':'1'}
  self.d=['docker','--config',str(root/'docker-config'),'--host','unix://TASK_DOCKER_ENDPOINT']
 def save_bytes(self,name,data):
  try:(self.root/name).write_bytes(data);return True
  except Exception as exc:self.diagnostic_errors.append({'file':name,'error_type':type(exc).__name__});return False
 def call(self,args,timeout=20,limit=1048576):
  self.count+=1;beg=time.monotonic();merged=args[0]=='logs'
  p=None;chunks=[];size=0;errchunks=[];errsize=0;reason=None;reap_error=None
  try:
   p=subprocess.Popen(self.d+args,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT if merged else subprocess.PIPE)
   streams=[p.stdout]
   if not merged and getattr(p,'stderr',None) is not None:streams.append(p.stderr)
   while streams:
    remaining=timeout-(time.monotonic()-beg)
    if remaining<=0:raise TimeoutError('command timeout; reconcile exact resource before retry')
    ready,_,_=select.select(streams,[],[],min(remaining,1))
    for stream in ready:
     c=os.read(stream.fileno(),65536)
     if not c:streams.remove(stream);continue
     if stream is p.stdout:
      size+=len(c)
      if size>limit:
       if merged:chunks.append(c[:max(0,limit-(size-len(c)))])
       raise ValueError('command output cap')
      chunks.append(c)
     else:
      errsize+=len(c);errchunks.append(c[:max(0,32768-(errsize-len(c)))])
      if errsize>32768:raise ValueError('command stderr cap')
   code=p.wait(timeout=max(.1,timeout-(time.monotonic()-beg)))
   if code:raise RuntimeError('Docker command exit '+str(code))
  except BaseException as e:
   reason=type(e).__name__+': '+str(e)[:200]
   if p is not None:
    try:p.kill();p.wait(timeout=3)
    except BaseException as child_error:reap_error=type(child_error).__name__
   raise
  finally:
   if p is not None:
    for stream in [p.stdout,getattr(p,'stderr',None)]:
     if stream is not None:stream.close()
   raw=b''.join(chunks);err=b''.join(errchunks)
   receipt={'argv':self.d+args,'subcommand':args,'elapsed':time.monotonic()-beg,'exit':None if p is None else p.returncode,'output_bytes':size,'sha256':hashlib.sha256(raw).hexdigest(),'error':reason,'reap_error':reap_error,'uncertain_mutation':reason is not None and args[0] in ('create','start','cp','rm','volume')}
   saved=True
   if merged:
    name='%03d-combined-log.bin'%self.count
    saved=self.save_bytes(name,raw)
    receipt.update(streams='stdout+stderr',retained_bytes=len(raw),truncated=size>limit,diagnostic_file=name)
   else:
    name='%03d-stderr.bin'%self.count
    saved=self.save_bytes(name,err)
    receipt.update(stderr_file=name,stderr_retained_bytes=len(err),stderr_observed_bytes=errsize,stderr_truncated=errsize>32768,stderr_sha256=hashlib.sha256(err).hexdigest())
   saved=self.save_bytes('%03d-command.json'%self.count,(json.dumps(receipt,indent=2)+'\n').encode()) and saved
   if not saved and reason is None:raise RuntimeError('diagnostic persistence failed')
  return raw
 def obj(self,args,timeout=20):
  raw=self.call(args,timeout=timeout)
  try:return json.loads(raw)
  except Exception as exc:
   self.save_bytes('%03d-protocol-error.json'%self.count,(json.dumps({'subcommand':args,'error_type':type(exc).__name__,'message':str(exc)[:1024],'stdout_prefix_hex':raw[:4096].hex(),'truncated':len(raw)>4096})+'\n').encode())
   raise
def cancelled(signum,frame):
 raise KeyboardInterrupt('parent signal '+str(signum))
def stopped_state(run,cid):
 try:
  obj=run.obj(['inspect',cid],timeout=3)[0]
  if obj.get('Id')!=cid: return None
  st=obj.get('State')
  if not isinstance(st,dict) or type(st.get('Running')) is not bool:return None
  return st
 except Exception:return None
def supervise(run,args,cid,budget):
 """Bound one child and exact CID; never retry start or kill a process group."""
 child=None;child_drain=None;primary_failure=False;events=[];previous={s:signal.signal(s,cancelled) for s in (signal.SIGINT,signal.SIGTERM)}
 try:
  child=subprocess.Popen(args,env=run.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  child_drain=bounded_command.Drain(child)
  code=child.wait(timeout=budget+90)
  if code!=0:raise RuntimeError('watchdog exit '+str(code))
  state=stopped_state(run,cid)
  if state is None or state['Running'] is not False:raise RuntimeError('watchdog exit lacks terminal evidence')
  return code
 except BaseException as failure:
  primary_failure=True
  # Repeated catchable signals cannot interrupt the bounded shutdown sequence.
  for sig in previous:signal.signal(sig,signal.SIG_IGN)
  if child is not None:
   try:
    if child.poll() is None:child.send_signal(signal.SIGTERM);events.append('forwarded SIGTERM')
    child.wait(timeout=45)
   except BaseException:
    events.append('child grace failed')
    try:child.kill();child.wait(timeout=3);events.append('exact child killed/reaped')
    except BaseException:events.append('child outcome UNKNOWN')
  state=stopped_state(run,cid)
  if state is None or state['Running'] is not False:
   try:run.call(['stop','--time','10',cid],timeout=15);events.append('exact CID stop')
   except BaseException:events.append('stop failed/uncertain')
   state=stopped_state(run,cid)
   if state is None or state['Running'] is not False:
    try:run.call(['kill',cid],timeout=5);events.append('exact CID kill')
    except BaseException:events.append('kill failed/uncertain')
  state=stopped_state(run,cid)
  if child is None or child.poll() is None:run.uncertain_cids.add(cid)
  try:(run.root/'parent-shutdown.json').write_text(json.dumps({'cid':cid,'events':events,'failure_type':type(failure).__name__,'failure_message':str(failure)[:4096],'child_returncode':None if child is None else child.returncode,'state':state,'terminal_confirmed':isinstance(state,dict) and state.get('Running') is False,'child_reaped':child is not None and child.poll() is not None,'no_retry':True},indent=2)+'\n')
  except Exception as detail:
   if hasattr(run,'diagnostic_errors'):run.diagnostic_errors.append({'file':'parent-shutdown.json','error_type':type(detail).__name__})
  raise
 finally:
  diagnostic_failure=None
  try:
   (run.root/'watchdog-child.json').write_text(json.dumps({'argv':args,'returncode':None if child is None else child.returncode,'streams':None if child_drain is None else child_drain.snapshot()})+'\n')
  except Exception as detail:
   diagnostic_failure=detail
   if hasattr(run,'diagnostic_errors'):run.diagnostic_errors.append({'file':'watchdog-child.json','error_type':type(detail).__name__})
  for sig,handler in previous.items():signal.signal(sig,handler)
  if diagnostic_failure is not None and not primary_failure:raise RuntimeError('required watchdog-child diagnostic persistence failed') from diagnostic_failure
def retire_online(run,cid,volume):
 """After safe export remove only online rootfs/work; replay inputs remain."""
 state=stopped_state(run,cid)
 if state is None or state.get('Running') is not False or state.get('Status')!='exited':raise RuntimeError('online state not terminal')
 run.call(['rm',cid])
 if cid in run.call(['ps','-aq','--no-trunc']).decode().split():raise RuntimeError('online CID deletion unconfirmed')
 obj=run.obj(['volume','inspect',volume])[0]
 if obj.get('Name')!=volume or obj.get('Labels')!={'ai-factory.task':'af03-ce-build-v2'}:raise RuntimeError('online work ownership')
 if run.call(['ps','-aq','--filter','volume='+volume]).strip():raise RuntimeError('online work has consumer')
 run.call(['volume','rm',volume])
 if volume in run.call(['volume','ls','-q']).decode().split():raise RuntimeError('online work deletion unconfirmed')
 (run.root/'online-retirement.json').write_text(json.dumps({'cid':cid,'volume':volume,'container_absent':True,'volume_absent':True,'capture_and_input_untouched':True})+'\n')
def capture_tar_receipt(run,cid,phase):
 """One fixed optional-on-failure receipt; never replace the primary error."""
 result={'phase':phase,'cid':cid}
 try:
  raw=run.call(['cp',cid+':/work/evidence/tar-preflight.txt','-'],timeout=5,limit=73728)
  data=decode_export(raw,'tar-preflight.txt',65536)
  path=run.root/(phase+'-tar-preflight.txt')
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(data)
  result.update(status='CAPTURED',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 except Exception as exc:
  result.update(status='CAPTURE_FAILED',error_type=type(exc).__name__,message=str(exc)[:200])
  try:
   stderr=(run.root/('%03d-stderr.bin'%run.count)).read_bytes()
   expected=('Error response from daemon: Could not find the file /work/evidence/tar-preflight.txt in container '+cid+'\n').encode()
   if stderr==expected:result['status']='MISSING_OR_NOT_REACHED'
  except Exception:pass
 run.save_bytes(phase+'-tar-capture.json',(json.dumps(result)+'\n').encode())
 return result
def persist_failure_receipt(save,state,run,stage):
 """Best effort on failure paths only; return the write error, never mask primary."""
 try:save();return None
 except Exception as detail:
  record={'file':'resources.json','stage':stage,'error_type':type(detail).__name__,'message':str(detail)[:200]}
  state.setdefault('persistence_errors',[]).append(record)
  run.diagnostic_errors.append(record)
  state['status']='BLOCKED'
  # A separate bounded stderr report remains useful if storage is unavailable.
  try:sys.stderr.write(json.dumps({'persistence_error':record},ensure_ascii=True)+'\n')
  except Exception:pass
  return detail
def main():
 for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,cancelled)
 ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--reviewed-manifest',required=True);ap.add_argument('--owner-grant',required=True);a=ap.parse_args()
 if not re.fullmatch('[a-f0-9]{64}',a.reviewed_manifest) or not a.owner_grant.strip():raise ValueError('missing exact review/grant')
 if sha(PKG/'review-hashes.json')!=a.reviewed_manifest:raise ValueError('review binding mismatch')
 for n,d in json.loads((PKG/'review-hashes.json').read_text())['files'].items():
  regular(PKG/n)
  if sha(PKG/n)!=d:raise ValueError('package drift')
 regular(a.archive)
 if a.archive.stat().st_size!=33910855 or sha(a.archive)!=ARCHIVE_SHA:raise ValueError('source identity')
 for q in [a.run,*a.run.parents]:
  if q.is_symlink():raise ValueError('run path symlink')
 if a.run.exists():raise ValueError('fresh run required; use reconciliation on previous run')
 a.run.mkdir();(a.run/'home').mkdir();(a.run/'docker-config').mkdir();run=Runner(a.run)
 state={'owner_grant':a.owner_grant,'reviewed_manifest':a.reviewed_manifest,'containers':[],'volumes':[],'status':'PREFLIGHT','note':'no automatic rerun; inspect recorded names/CIDs on uncertain outcome'}
 def save():
  state['diagnostic_errors']=run.diagnostic_errors
  (a.run/'resources.json').write_text(json.dumps(state,indent=2)+'\n')
 save()
 before_c=run.call(['ps','-aq','--no-trunc']).decode().split();before_v=run.call(['volume','ls','-q']).decode().split()
 names=['af03-ce-build-'+x+'-v2' for x in ['holder','online','offline']];volumes=['af03-ce-build-'+x+'-v2' for x in ['input','capture','online','offline']]
 existing=run.call(['ps','-a','--format','{{.Names}}']).decode().split()
 if set(names)&set(existing) or set(volumes)&set(before_v):raise ValueError('owned name collision: stop')
 image=run.obj(['image','inspect',IMAGE])[0]
 if image['Id']!=IMAGE_ID or (image['Os'],image['Architecture'])!=('linux','amd64') or image['RootFS']['Layers']!=['sha256:e63b02c2b5c761df2cb95e657d744f27d95da4e051235a13c80b88cd68eab188']:raise ValueError('image mismatch')
 if image['Config']!={'Env':['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'],'Cmd':['/bin/sh'],'WorkingDir':'/'}:raise ValueError('image config')
 (a.run/'image.json').write_text(json.dumps(image,indent=2)+'\n')
 deadline=time.monotonic()+5400
 try:
  for v in volumes:
   run.call(['volume','create','--label','ai-factory.task=af03-ce-build-v2',v]);state['volumes'].append(v);save()
  common=['--platform','linux/amd64','--pull','never','--cap-drop','ALL','--security-opt','no-new-privileges','--user','0:0']
  holder=run.call(['create','--name',names[0],*common,'--network','none','--read-only','--mount','type=volume,src='+volumes[0]+',dst=/input','--entrypoint','/bin/true',IMAGE]).decode().strip()
  if not re.fullmatch('[a-f0-9]{64}',holder):raise ValueError('unknown holder CID')
  state['containers'].append(holder);save()
  for source,dest in [(a.archive,'source.tar.gz')]+[(PKG/n,n) for n in FILES]:run.call(['cp',str(source),holder+':/input/'+dest],timeout=30)
  run.call(['rm',holder]);state['containers'].remove(holder);save()
  for phase in ['online','offline']:
   remaining=int(deadline-time.monotonic())
   if remaining<=0:raise TimeoutError('shared90min deadline before phase')
   name='af03-ce-build-'+phase+'-v2';capture='type=volume,src='+volumes[1]+',dst=/capture'+(',readonly' if phase=='offline' else '')
   cid=run.call(['create','--name',name,*common,'--network','bridge' if phase=='online' else 'none','--cpus','4','--memory','8g','--memory-swap','8g','--pids-limit','512','--log-driver','local','--log-opt','max-size=1m','--log-opt','max-file=2','--mount','type=volume,src='+volumes[0]+',dst=/input,readonly','--mount','type=volume,src='+name+',dst=/work','--mount',capture,'--workdir','/work','--entrypoint','/bin/sh',IMAGE,'/input/build.sh',phase]).decode().strip()
   if not re.fullmatch('[a-f0-9]{64}',cid):raise ValueError('unknown main CID')
   state['containers'].append(cid);state['status']=phase;save();out=a.run/phase;out.mkdir()
   args=[sys.executable,'-B',str(PKG/'watchdog.py'),str(a.run/'docker-config'),cid,str(out),phase,str(remaining)]
   # Parent-only cancellation forwards and reconciles exact CID before cleanup.
   code=supervise(run,args,cid,remaining)
   result=json.loads((out/'watchdog-result.json').read_text())
   if code or result['status']!='PASS':raise RuntimeError(phase+' BLOCKED; inspect watchdog evidence')
   exported=out/'export';exported.mkdir();total=0
   for n,cap in EXPORTS.items():
    data=decode_export(run.call(['cp',cid+':/work/evidence/'+n,'-'],timeout=20,limit=cap+65536),n,cap);total+=len(data)
    if total>16*1024**2:raise ValueError('export total cap')
    fd=os.open(exported/n,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data)
   (out/'export-hashes.json').write_text(json.dumps({n:sha(exported/n) for n in EXPORTS},indent=2)+'\n')
   if phase=='offline' and (exported/'cache-ledger.jsonl').read_bytes()!=(a.run/'online/export/cache-ledger.jsonl').read_bytes():raise ValueError('capture identity changed between phases')
   if phase=='online':
    retire_online(run,cid,name)
    state['containers'].remove(cid);state['volumes'].remove(name);save()
   # Online rootfs/work deletion confirmed before the offline phase.
  state['phase_result']='PASS_TWO_PHASE_CE_PROTOTYPE_NOT_RELEASE';state['status']='CLEANUP_PENDING';save()
 except BaseException as e:
  for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,signal.SIG_IGN)
  state['status']='BLOCKED';state['error']=type(e).__name__+': '+str(e)[:200]
  persist_failure_receipt(save,state,run,'before-failure-capture')
  for cid in state['containers']:
   try:(a.run/(cid+'-bounded-log.txt')).write_bytes(run.call(['logs','--tail','64',cid],timeout=5,limit=65536))
   except Exception:state.setdefault('log_errors',[]).append('bounded logs unavailable for '+cid)
   try:
    data=decode_export(run.call(['cp',cid+':/work/evidence/stage.txt','-'],timeout=5,limit=8192),'stage.txt',1024)
    run.save_bytes(cid+'-stage.txt',data)
   except Exception as detail:state.setdefault('stage_errors',[]).append({'cid':cid,'error_type':type(detail).__name__,'message':str(detail)[:200]})
   if state.get('status')=='BLOCKED':
    try:capture_tar_receipt(run,cid,'online' if not (a.run/'offline').exists() else 'offline')
    except Exception as detail:state.setdefault('tar_capture_errors',[]).append(type(detail).__name__)
  persist_failure_receipt(save,state,run,'after-failure-capture');raise
 finally:
  primary_failure=sys.exc_info()[0] is not None
  # No force; uncertain/live resource retained for exact-ID reconciliation.
  clean=[]
  for cid in list(state['containers']):
   try:
    if cid in run.uncertain_cids:raise RuntimeError('child lifecycle UNKNOWN; retain exact CID')
    o=run.obj(['inspect',cid])[0]
    if o['State']['Running'] is not False:raise ValueError('container not stopped; retain')
    run.call(['rm',cid]);clean.append(cid);state['containers'].remove(cid);save()
   except Exception as e:state.setdefault('cleanup_errors',[]).append(str(e)[:200])
  if not state['containers']:
   for v in list(state['volumes']):
    try:
     o=run.obj(['volume','inspect',v])[0]
     if o['Labels']!={'ai-factory.task':'af03-ce-build-v2'} or run.call(['ps','-aq','--filter','volume='+v]).strip():raise ValueError('volume ownership/consumer')
     run.call(['volume','rm',v]);state['volumes'].remove(v);save()
    except Exception as e:state.setdefault('cleanup_errors',[]).append(str(e)[:200])
  for kind,before,args in [('containers',before_c,['ps','-aq','--no-trunc']),('volumes',before_v,['volume','ls','-q'])]:
   try:state['unrelated_'+kind+'_preserved']=set(before)<=set(run.call(args).decode().split())
   except Exception as detail:
    state['unrelated_'+kind+'_preserved']=None
    state.setdefault('cleanup_errors',[]).append({'check':kind,'error_type':type(detail).__name__,'message':str(detail)[:200]})
  failures=[]
  if state['containers'] or state['volumes'] or run.uncertain_cids:failures.append('retained or uncertain resources')
  if state.get('cleanup_errors'):failures.append('cleanup errors')
  if run.diagnostic_errors:failures.append('required diagnostic errors')
  if any(state.get('unrelated_'+k+'_preserved') is not True for k in ('containers','volumes')):failures.append('preservation unconfirmed')
  state['completion_errors']=failures
  if failures or primary_failure or state.get('phase_result')!='PASS_TWO_PHASE_CE_PROTOTYPE_NOT_RELEASE':state['status']='BLOCKED'
  else:state['status']='PASS_TWO_PHASE_CE_PROTOTYPE_NOT_RELEASE'
  persistence_error=persist_failure_receipt(save,state,run,'final-completion')
  if persistence_error is not None and not primary_failure:raise persistence_error
  if state['status']=='BLOCKED' and not primary_failure:raise RuntimeError('final completion gate BLOCKED: '+', '.join(failures))
if __name__=='__main__':main()
