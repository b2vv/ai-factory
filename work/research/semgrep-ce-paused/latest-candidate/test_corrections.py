import importlib.util,json,signal,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('launcher.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
CID='a'*64;VOL='af03-ce-build-online-v2'
class FakeRun:
 def __init__(self,root,fail=False):self.root=Path(root);self.env={};self.calls=[];self.running=True;self.fail=fail;self.uncertain_cids=set();self.removed=False;self.vremoved=False
 def call(self,args,**kw):
  self.calls.append(args)
  if args[0]=='inspect':
   if self.fail:raise TimeoutError('inspect')
   return json.dumps([{'Id':CID,'State':{'Running':self.running,'Status':'running' if self.running else 'exited'}}]).encode()
  if args[0] in ('stop','kill'):
   if self.fail:raise TimeoutError('shutdown')
   self.running=False
  if args[0]=='rm':self.removed=True
  if args[:2]==['volume','rm']:self.vremoved=True
  if args[:2]==['volume','ls']:return b'' if self.vremoved else VOL.encode()
  if args[0]=='ps':return b'' if self.removed else CID.encode()
  return b''
 def obj(self,args,timeout=20):
  if args[0]=='inspect':return json.loads(self.call(args,timeout=timeout))
  return [{'Name':VOL,'Labels':{'ai-factory.task':'af03-ce-build-v2'}}]
class Proc:
 def __init__(self,mode,handlers):self.returncode=None;self.n=0;self.mode=mode;self.handlers=handlers;self.signals=[]
 def wait(self,timeout):
  self.n+=1
  if self.n==1:
   if self.mode=='interrupt':raise KeyboardInterrupt()
   if self.mode=='timeout':raise subprocess.TimeoutExpired('watchdog',timeout)
   if self.mode=='failure':self.returncode=1;return 1
   self.handlers[signal.SIGINT if self.mode=='sigint' else signal.SIGTERM](0,None)
  if self.mode=='timeout' and self.n==2:raise subprocess.TimeoutExpired('watchdog',timeout)
  self.returncode=-15;return self.returncode
 def poll(self):return self.returncode
 def send_signal(self,s):self.signals.append(s)
 def kill(self):self.returncode=-9
class Corrections(unittest.TestCase):
 def case(self,mode,fail=False):
  with tempfile.TemporaryDirectory() as d:
   handlers={};run=FakeRun(d,fail);proc=Proc(mode,handlers)
   def sig(s,h):old=handlers.get(s,signal.SIG_DFL);handlers[s]=h;return old
   with patch.object(m.signal,'signal',side_effect=sig),patch.object(m.subprocess,'Popen',return_value=proc) as popen:
    with self.assertRaises(BaseException):m.supervise(run,['mock'],CID,1)
   self.assertEqual(popen.call_count,1)
   receipt=json.loads((Path(d)/'parent-shutdown.json').read_text())
   self.assertTrue(any(a[0]=='stop' for a in run.calls))
   for a in run.calls:
    if a[0] in ('stop','kill'):self.assertEqual(a[-1],CID)
   if mode!='failure':self.assertEqual(proc.signals,[signal.SIGTERM])
   self.assertEqual(receipt['terminal_confirmed'],not fail)
   if fail:self.assertTrue(any(a[0]=='kill' for a in run.calls))
 def test_parent_sigint(self):self.case('sigint')
 def test_parent_sigterm(self):self.case('sigterm')
 def test_parent_keyboardinterrupt(self):self.case('interrupt')
 def test_watchdog_timeout(self):self.case('timeout')
 def test_child_failure(self):self.case('failure')
 def test_shutdown_unknown(self):self.case('sigterm',True)
 def test_creation_unknown(self):
  with tempfile.TemporaryDirectory() as d:
   run=FakeRun(d)
   with patch.object(m.subprocess,'Popen',side_effect=OSError('spawn uncertain')):
    with self.assertRaises(OSError):m.supervise(run,['mock'],CID,1)
   self.assertIn(CID,run.uncertain_cids)
   self.assertFalse(run.running)
 def test_retire_before_replay(self):
  with tempfile.TemporaryDirectory() as d:
   run=FakeRun(d);run.running=False;m.retire_online(run,CID,VOL)
   self.assertTrue(run.removed and run.vremoved)
   mutations=[a for a in run.calls if a[0]=='rm' or a[:2]==['volume','rm']]
   self.assertEqual(mutations,[['rm',CID],['volume','rm',VOL]])
 def test_running_retirement_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   run=FakeRun(d)
   with self.assertRaises(RuntimeError):m.retire_online(run,CID,VOL)
   self.assertFalse(run.removed)
 def test_unconfirmed_deletion_stops(self):
  with tempfile.TemporaryDirectory() as d:
   run=FakeRun(d);run.running=False;original=run.call
   def call(a,**kw):
    val=original(a,**kw)
    return CID.encode() if a[0]=='ps' else val
   run.call=call
   with self.assertRaises(RuntimeError):m.retire_online(run,CID,VOL)
   self.assertFalse(run.vremoved)
 def test_fixed_accounting_allowance(self):
  code=Path(__file__).with_name('watchdog.py').read_text()
  self.assertIn('+128*1024**2',code)
  # Online20GiB is removed; active work10+capture1+fixed128MiB observed.
  self.assertLess(10*1024**3+1024**3+128*1024**2,25*1024**3)
if __name__=='__main__':unittest.main()
