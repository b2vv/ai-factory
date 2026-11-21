"""Inactive until approved: supervise one inspected task container; no creation/pulls."""
import json,os,re,shutil,subprocess,sys,time,signal,traceback
from pathlib import Path
import bounded_command
import disk_sample
config,cid,output,phase,budget=sys.argv[1:]
assert phase in ("online","offline")
budget=int(budget);assert 0<budget<=5400
assert re.fullmatch('[a-f0-9]{64}',cid)
out=Path(output);assert out.is_dir() and not out.is_symlink()
diagnostic_write_errors=[]
def save_diag(name,record):
 try:(out/name).write_text(json.dumps(record,ensure_ascii=True,indent=2)+'\n');return True
 except Exception as e:diagnostic_write_errors.append({'file':name,'error':type(e).__name__});return False
def unhandled(kind,value,tb):
 record={'error_type':kind.__name__,'message':str(value)[:2048],'traceback':''.join(traceback.format_exception(kind,value,tb,limit=8))[:8192]}
 save_diag('unhandled-error.json',record)
sys.excepthook=unhandled
d=['docker','--config',config,'--host','unix://TASK_DOCKER_ENDPOINT']
command_errors=0
def call(args,timeout=5):
 global command_errors
 beg=time.perf_counter()
 try:return bounded_command.run(d+args,capture_output=True,text=True,timeout=timeout,check=True).stdout
 except BaseException as exc:
  # Preserve command identity separately from the short human-readable reason.
  command_errors+=1
  def preview(value,cap):
   if value is None:return {'text':'','bytes_retained':0,'truncated':False}
   raw=value if isinstance(value,bytes) else str(value).encode('utf-8',errors='replace')
   return {'text':raw[:cap].decode('utf-8',errors='replace'),'bytes_retained':min(len(raw),cap),'truncated':len(raw)>cap}
  record={'sequence':command_errors,'subcommand':args[:16],'error_type':type(exc).__name__,
          'phase':phase,'elapsed':time.perf_counter()-beg,'observed_bytes':getattr(exc,'observed_bytes',None),'capture_truncated':getattr(exc,'truncated',None),'returncode':getattr(exc,'returncode',None),'timeout_seconds':getattr(exc,'timeout',None),
          'stdout':preview(getattr(exc,'stdout',None),2048),'stderr':preview(getattr(exc,'stderr',None),8192)}
  # First32 plus latest; write failure must not suppress shutdown.
  if command_errors<=32:save_diag('command-error-%02d.json'%command_errors,record)
  save_diag('last-command-error.json',record)
  raise
def parse_json(raw,stage):
 try:return json.loads(raw)
 except Exception as exc:
  save_diag('protocol-error.json',{'stage':stage,'error_type':type(exc).__name__,'stdout_prefix':raw[:8192]})
  raise
obj=parse_json(call(['inspect',cid]),'prestart')[0]
assert obj['Name']=='/af03-ce-build-'+phase+'-v2' and not obj['State']['Running']
h=obj['HostConfig'];c=obj['Config']
assert obj['Image']=='sha256:f6d31b983274a75183386cda3aac54849498fac0fc3e0d98f92ff56ed517d92b'
assert c['User']=='0:0' and c['Entrypoint']==['/bin/sh'] and c['Cmd']==['/input/build.sh',phase]
assert h['NetworkMode']==('bridge' if phase=='online' else 'none') and h['ReadonlyRootfs'] is False and not h['Privileged']
assert h['CapDrop']==['ALL'] and 'no-new-privileges' in ' '.join(h['SecurityOpt'])
assert h['NanoCpus']==4000000000 and h['Memory']==8589934592 and h['MemorySwap']==8589934592 and h['PidsLimit']==512
assert not h.get('Binds') and not h.get('CapAdd') and not h.get('DeviceRequests') and not h.get('Devices') and h.get('PidMode','')=='' and h.get('IpcMode')!='host'
mounts=[(x['Type'],x.get('Name'),x['Destination'],x['RW']) for x in obj['Mounts'] if x['Type']!='tmpfs']
assert sorted(mounts)==sorted([('volume','af03-ce-build-input-v2','/input',False),('volume','af03-ce-build-'+phase+'-v2','/work',True),('volume','af03-ce-build-capture-v2','/capture',phase=='online')])
assert not h.get('Tmpfs')
assert h['LogConfig']=={'Type':'local','Config':{'max-size':'1m','max-file':'2'}}
assert h.get('RestartPolicy',{}).get('Name')=='no' and not h.get('AutoRemove')
assert shutil.disk_usage(out).free>=10*1024**3
(out/'prestart-inspect.json').write_text(json.dumps(obj,indent=2)+'\n')
def terminal(state):
 if not isinstance(state,dict):return False
 return (state.get('Status')=='exited' and state.get('Running') is False
         and state.get('Paused') is False and state.get('Restarting') is False
         and state.get('Dead') is False and type(state.get('ExitCode')) is int
         and state['ExitCode']==0 and state.get('OOMKilled') is False
         and state.get('Error')=='')
def inspect_state():
 return parse_json(call(['inspect','--format','{{json .State}}',cid],timeout=3),'state')
def cancelled(signum,frame):
 raise KeyboardInterrupt('termination signal '+str(signum))
previous={sig:signal.signal(sig,cancelled) for sig in (signal.SIGINT,signal.SIGTERM)}
start=time.monotonic();reason=None;peak=0;p=None;completed=None;state=None;shutdown=[];attach=None;primary_command_error=None
def stop_exact():
 # Only the bound CID. Each command and wait is bounded; no retry loop.
 try:call(['stop','--time','10',cid],timeout=15);shutdown.append('stop requested')
 except BaseException:shutdown.append('stop failed/timeout')
 try:current=inspect_state()
 except BaseException:current=None;shutdown.append('poststop inspect unknown')
 if not isinstance(current,dict) or current.get('Running') is not False:
  try:call(['kill',cid],timeout=5);shutdown.append('kill requested')
  except BaseException:shutdown.append('kill failed/timeout')
 try:return inspect_state()
 except BaseException:shutdown.append('terminal inspect unknown');return None
disk_receipts=0
def disk_record(record):
 global disk_receipts
 disk_receipts+=1
 record.update(phase=phase,subcommand=['exec','-e','LC_ALL=C','-e','LANG=C',cid,'du','-sk','/work','/capture'])
 if disk_receipts>32:raise RuntimeError('disk diagnostic receipt bound')
 if not save_diag('disk-sample-%02d.json'%disk_receipts,record):raise RuntimeError('disk diagnostic persistence')
def reserve():
 if shutil.disk_usage(out).free<10*1024**3:raise RuntimeError('host reserve')
try:
 try:
  p=subprocess.Popen(d+['start','--attach',cid],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  attach=bounded_command.Drain(p)
 except BaseException as exc:
  save_diag('attach-spawn-error.json',{'subcommand':['start','--attach',cid],'error_type':type(exc).__name__,'message':str(exc)[:2048]})
  raise
 while True:
  state=inspect_state()
  if not isinstance(state,dict) or type(state.get('Running')) is not bool:
   raise RuntimeError('malformed running state')
  if not state['Running'] and p.poll() is not None:
   if not terminal(state):raise RuntimeError('invalid completion state')
   completed=state.copy();break
  if time.monotonic()-start>=budget:raise RuntimeError('shared pilot deadline')
  if shutil.disk_usage(out).free<10*1024**3:raise RuntimeError('host reserve')
  if state['Running']:
   totals=disk_sample.sample(lambda limit:bounded_command.run(d+['exec','-e','LC_ALL=C','-e','LANG=C',cid,'du','-sk','/work','/capture'],timeout=limit,text=False,check=True),disk_record,reserve,budget-(time.monotonic()-start))
   rw=call(['inspect','--size','--format','{{.SizeRw}}',cid],timeout=5).strip()
   assert rw.isdigit()
   # 128MiB conservative fixed allowance: opaque input, bounded exports/logs/receipts.
   peak=max(peak,sum(totals)*1024+int(rw)+128*1024**2)
   if peak>=25*1024**3:raise RuntimeError('soft disk threshold')
  time.sleep(1)
 p.wait(timeout=5)
 if p.returncode!=0:raise RuntimeError('attach failed')
 state=inspect_state()
 if not terminal(state) or state!=completed:
  raise RuntimeError('final state invalid or disagrees with completion')
except BaseException as e:
 reason=type(e).__name__+': '+str(e)[:200]
 primary_command_error=command_errors or None
finally:
 # Prevent a second catchable cancellation from interrupting bounded shutdown.
 for sig in previous:signal.signal(sig,signal.SIG_IGN)
 if reason is not None:state=stop_exact()
 if p is not None:
  try:
   if p.poll() is None:p.terminate()
   p.wait(timeout=3)
  except BaseException:
   reason=reason or 'attach client reap failed'
   try:p.kill();p.wait(timeout=3)
   except BaseException:shutdown.append('attach reap unknown')
 # Final terminal evidence is mandatory even after the normal completion path.
 try:final=inspect_state()
 except BaseException:final=None
 if reason is None and (not terminal(final) or final!=completed):
  reason='final terminal evidence invalid/disagrees'
  final=stop_exact()
 state=final
 if attach is not None:save_diag('attach-diagnostics.json',{'subcommand':['start','--attach',cid],'returncode':p.returncode,'streams':attach.snapshot()})
 if diagnostic_write_errors and reason is None:
  reason='diagnostic persistence failed';state=stop_exact()
 result={'status':'PASS' if reason is None and terminal(state) and state==completed and p is not None and p.returncode==0 else 'BLOCKED',
         'reason':reason,'primary_command_error_sequence':primary_command_error,'diagnostic_write_errors':diagnostic_write_errors,'state':state,'elapsed':time.monotonic()-start,
         'peak_observed_work_bytes':peak,'shutdown':shutdown,
         'terminal_confirmed':isinstance(state,dict) and state.get('Running') is False,
         'disk_limit':'SOFT; du may lag, timeout or overrun; not quota'}
 (out/'watchdog-result.json').write_text(json.dumps(result,indent=2)+'\n')
 for sig,handler in previous.items():signal.signal(sig,handler)
print(json.dumps(result));sys.exit(result['status']!='PASS')
