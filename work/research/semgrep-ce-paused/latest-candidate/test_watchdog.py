import contextlib,copy,io,json,runpy,signal,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
SCRIPT=Path(__file__).with_name('watchdog.py')
GOOD={'Status':'exited','Running':False,'Paused':False,'Restarting':False,'Dead':False,'ExitCode':0,'OOMKilled':False,'Error':''}
RUNNING={**GOOD,'Status':'running','Running':True}
class Tests(unittest.TestCase):
 def check_case(self,mode):
  calls=[];polls=0;handlers={};stopped=False;du_calls=0
  obj={'Name':'/af03-ce-build-online-v2','State':{'Running':False},'Image':'sha256:f6d31b983274a75183386cda3aac54849498fac0fc3e0d98f92ff56ed517d92b','Config':{'User':'0:0','Entrypoint':['/bin/sh'],'Cmd':['/input/build.sh','online']},'HostConfig':{'NetworkMode':'bridge','ReadonlyRootfs':False,'Privileged':False,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'NanoCpus':4000000000,'Memory':8589934592,'MemorySwap':8589934592,'PidsLimit':512,'Tmpfs':{},'LogConfig':{'Type':'local','Config':{'max-size':'1m','max-file':'2'}},'RestartPolicy':{'Name':'no'}},'Mounts':[{'Type':'volume','Name':'af03-ce-build-input-v2','Destination':'/input','RW':False},{'Type':'volume','Name':'af03-ce-build-online-v2','Destination':'/work','RW':True},{'Type':'volume','Name':'af03-ce-build-capture-v2','Destination':'/capture','RW':True}]}
  if mode=='offline_success':
   obj['Name']='/af03-ce-build-offline-v2';obj['Config']['Cmd']=['/input/build.sh','offline'];obj['HostConfig']['NetworkMode']='none';obj['Mounts'][1]['Name']='af03-ce-build-offline-v2';obj['Mounts'][2]['RW']=False
  class Proc:
   returncode=1 if mode=='attach_failure' else 0
   def poll(self):return self.returncode
   def wait(self,timeout):
    if mode=='reap_timeout':raise subprocess.TimeoutExpired('mock',timeout)
    return self.returncode
   def terminate(self):calls.append(['attach-terminate'])
   def kill(self):calls.append(['attach-kill']);self.returncode=-9
  def fake_run(argv,**kw):
   nonlocal polls,stopped,du_calls
   a=argv[5:];calls.append(a)
   if '--size' in a:return SimpleNamespace(stdout='0')
   if a[0]=='stop':
    if mode in ('stop_failure','kill_failure','stop_timeout'):raise subprocess.TimeoutExpired('mock',kw['timeout'])
    stopped=True;return SimpleNamespace(stdout='')
   if a[0]=='kill':
    if mode=='kill_failure':raise subprocess.TimeoutExpired('mock',kw['timeout'])
    stopped=True;return SimpleNamespace(stdout='')
   if a[0]=='exec' and mode=='disk_recovery':
    du_calls+=1
    if du_calls==1:
     exc=subprocess.CalledProcessError(1,argv,output=b'1\t/work\n1\t/capture\n',stderr=b"du: cannot access '/work/opam/5.4.0/.opam-switch/build/ocaml-compiler.5.4.0/conftest': No such file or directory\n")
     exc.truncated=[False,False];raise exc
   if a[0]=='exec':return SimpleNamespace(returncode=0,stderr=b'',stdout=((str(25*1024**2-64*1024)+'\t/work\n0\t/capture\n') if mode=='disk_edge' else '1\t/work\n1\t/capture\n').encode())
   if '--format' not in a:return SimpleNamespace(stdout=json.dumps([obj]))
   polls+=1
   interrupt=mode in ('interrupt','sigterm','stop_failure','kill_failure','stop_timeout','inspect_failure','reap_timeout','control_failure','diagnostic_write_failure')
   if polls==1 and interrupt:
    if mode in ('control_failure','diagnostic_write_failure'):raise subprocess.CalledProcessError(17,argv,output='out',stderr='control detail')
    if mode=='sigterm':handlers[signal.SIGTERM](signal.SIGTERM,None)
    if mode=='inspect_failure':raise subprocess.TimeoutExpired('mock',kw['timeout'])
    raise KeyboardInterrupt('mock interruption')
   if interrupt:return SimpleNamespace(stdout=json.dumps(GOOD if stopped else RUNNING))
   if mode in ('deadline','disk_edge','disk_recovery') and polls==1:return SimpleNamespace(stdout=json.dumps(RUNNING))
   state=copy.deepcopy(GOOD)
   if polls>=2:
    if mode=='oom':state.update(ExitCode=137,OOMKilled=True)
    if mode=='dead':state['Dead']=True
    if mode=='missing':state.pop('ExitCode')
    if mode=='bool_exit':state['ExitCode']=False
    if mode=='disagreement':state['FinishedAt']='different'
    if mode=='malformed':state=[]
    if mode=='final_inspect_failure':raise subprocess.TimeoutExpired('mock',kw['timeout'])
   return SimpleNamespace(stdout=json.dumps(state))
  def sig(sig,handler):old=handlers.get(sig,signal.SIG_DFL);handlers[sig]=handler;return old
  original_write=Path.write_text
  def write(path,*args,**kw):
   if mode=='diagnostic_write_failure' and 'command-error' in path.name:raise OSError('disk write mock')
   return original_write(path,*args,**kw)
  with tempfile.TemporaryDirectory() as tmp:
   argv=[str(SCRIPT),'/unused/config','a'*64,tmp,'offline' if mode=='offline_success' else 'online','5400']
   ticks=iter([0,5401,5402,5403,5404])
   with patch.object(Path,'write_text',write),patch.object(sys,'argv',argv),patch('bounded_command.run',side_effect=fake_run),patch('subprocess.Popen',return_value=Proc()),patch('shutil.disk_usage',return_value=SimpleNamespace(free=20*1024**3)),patch('signal.signal',side_effect=sig),patch('time.sleep'),patch('time.monotonic',side_effect=(lambda:next(ticks)) if mode=='deadline' else None,return_value=1),contextlib.redirect_stdout(io.StringIO()):
    try:runpy.run_path(str(SCRIPT),run_name='__main__')
    except SystemExit as e:code=e.code
    except KeyboardInterrupt:code=130
   result=json.loads((Path(tmp)/'watchdog-result.json').read_text())
  if mode in ('success','offline_success','disk_recovery'):self.assertEqual(result['status'],'PASS');self.assertEqual(code,False)
  else:
   self.assertEqual(result['status'],'BLOCKED');self.assertTrue(code)
   self.assertTrue(any(a[0]=='stop' for a in calls),'no container stop')
  if mode in ('stop_failure','stop_timeout','kill_failure'):self.assertTrue(any(a[0]=='kill' for a in calls))
  if mode=='kill_failure':self.assertFalse(result['terminal_confirmed'])
  if mode=='disk_recovery':self.assertEqual(du_calls,2);self.assertGreater(result['peak_observed_work_bytes'],0)
  for a in calls:
   if a[0] in ('stop','kill'):self.assertEqual(a[-1],'a'*64)
for mode in ['success','offline_success','interrupt','sigterm','oom','dead','missing','bool_exit','disagreement','malformed','final_inspect_failure','inspect_failure','stop_failure','stop_timeout','kill_failure','reap_timeout','deadline','disk_edge','control_failure','diagnostic_write_failure','attach_failure','disk_recovery']:
 setattr(Tests,'test_'+mode,lambda self,m=mode:self.check_case(m))
if __name__=='__main__':unittest.main()
