from pathlib import Path
import tempfile
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
TESTS = str(Path(__file__).resolve().parent)
import sys,os,json,subprocess,tempfile,time,unittest,importlib.util,contextlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,(CODE + ''));import guard,entry
from types import SimpleNamespace
class Resume(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=tempfile.gettempdir());self.store=Path(self.tmp.name);self.key='b'*32;self.token='a'*32+'-1-'+'c'*12;self.st={};self.obj={'id':self.token,'complete':True,'created':time.time(),'depth':0,'snapshot':{'root':'/fixture'},'summary':{f:'synthetic' for f in guard.FIELDS}}
  self.record=self.store/(self.token+'.json');self.claim=self.store/('claim-'+self.token+'.json');self.save()
 def tearDown(self):self.tmp.cleanup()
 def save(self):self.record.write_text(json.dumps(self.obj))
 def run_resume(self):
  with patch.object(guard,'snapshot',return_value={'root':'/fixture'}):return guard.resume_locked(self.store,self.token,'codex','sid','/fixture',self.key,self.st)
 def test_incomplete(self):self.obj['complete']=False;self.save();self.assertRaises(ValueError,self.run_resume)
 def test_wrong_id(self):self.obj['id']='x';self.save();self.assertRaises(ValueError,self.run_resume)
 def test_source_session(self):self.key='a'*32;self.assertRaises(ValueError,self.run_resume)
 def test_other_claim(self):self.claim.write_text(json.dumps({'target':'other'}));self.assertRaises(ValueError,self.run_resume)
 def test_same_claim_noop_expired_depth_changed(self):
  self.obj.update(created=0,depth=3,snapshot={'different':1});self.save();self.claim.write_text(json.dumps({'target':self.key}));self.st={'resumed':self.token,'depth':4};self.assertEqual(self.run_resume(),'')
 def test_partial_claim(self):self.claim.write_text(json.dumps({'target':self.key}));self.assertRaises(ValueError,self.run_resume)
 def test_expired(self):self.obj['created']=0;self.save();self.assertRaises(ValueError,self.run_resume)
 def test_future(self):self.obj['created']=time.time()+3600;self.save();self.assertRaises(ValueError,self.run_resume)
 def test_maxdepth(self):self.obj['depth']=3;self.save();self.assertRaises(ValueError,self.run_resume)
 def test_snapshot_mismatch(self):self.obj['snapshot']={};self.save();self.assertRaises(ValueError,self.run_resume)
 def test_valid_then_noop(self):self.assertIn('handoff READ',self.run_resume());self.assertEqual(self.run_resume(),'')
 def test_state_without_claim(self):self.st={'resumed':self.token,'depth':1};self.assertRaises(ValueError,self.run_resume)
 def test_claim_write_failure(self):
  real=guard.atomic
  def atom(p,v):
   if p==self.claim:raise OSError('fixture')
   return real(p,v)
  with patch.object(guard,'atomic',side_effect=atom):self.assertRaises(OSError,self.run_resume)
  self.assertTrue((self.store/('session-'+self.key+'.json')).exists());self.assertRaises(ValueError,self.run_resume)
 def test_corrupt_claim(self):self.claim.write_text('{');self.assertRaises(ValueError,self.run_resume)
class Inputs(unittest.TestCase):
 def test_shapes(self):
  a=SimpleNamespace(root='/missing',store='/other',mode='hook')
  for v in [None,[],1,'x']:self.assertRaises(ValueError,entry.execute,a,json.dumps(v).encode())
 def test_missing_mount(self):self.assertRaises(ValueError,entry.execute,SimpleNamespace(root='/definitely-absent-fixture',store='/other',mode='hook'),b'{}')
 def test_crossroot_identity(self):
  with patch.object(guard,'git',side_effect=lambda cwd,*args:cwd.encode()):
   self.assertNotEqual(guard.identity('codex','same','/first')[0],guard.identity('codex','same','/second')[0]);self.assertEqual(guard.identity('codex','same','/first'),guard.identity('codex','same','/first'))
class Shell(unittest.TestCase):
 def test_optional(self):
  env=dict(os.environ);env.pop('AI_FACTORY_HANDOFF',None)
  r=subprocess.run(['sh',(CODE + '/dispatch.sh'),'optional'],env=env,capture_output=True);self.assertEqual(r.returncode,0)
 def test_optional_pointer(self):
  for args in [[],['--unexpected','x']]:
   env=dict(os.environ,AI_FACTORY_HANDOFF='explicit');r=subprocess.run(['sh',(CODE + '/dispatch.sh'),'optional',*args],env=env,capture_output=True);self.assertNotEqual(r.returncode,0)
 def test_required_missing_args(self):
  r=subprocess.run(['sh',(CODE + '/dispatch.sh'),'resume'],input=b'{}',capture_output=True);self.assertNotEqual(r.returncode,0)
class Lifecycle(unittest.TestCase):
 def run_case(self,fault,cancel=False,preflight_stall=False):
  with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as temp:
   p=Path(temp);root=p/'repo';store=p/'store';work=p/'work';bin=p/'bin'
   for x in [root,store,work,bin]:x.mkdir()
   import shutil
   shutil.copy((TESTS + '/fake_docker.py'),bin/'docker');(bin/'docker').chmod(0o700)
   env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'],FAULT=fault,FAKE_STATE=str(p/'fake.json'));env.pop('AI_FACTORY_HANDOFF',None)
   dispatch=(CODE + '/dispatch.sh')
   if preflight_stall:
    shutil.copytree((CODE + ''),p/'code');(p/'code'/'preflight.sh').write_text('#!/bin/sh\nexec sleep 30\n');dispatch=str(p/'code'/'dispatch.sh')
   cmd=['sh',dispatch,'checkpoint','--root',str(root),'--store',str(store),'--work',str(work),'--host','codex','--session','fixture']
   t=time.monotonic()
   proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   if cancel:
    proc.stdin.write(b'{}');proc.stdin.close();proc.stdin=None
    limit=time.monotonic()+3
    while time.monotonic()<limit:
     if (p/'fake.log').exists() and 'start' in (p/'fake.log').read_text():break
     time.sleep(.02)
    proc.terminate()
   stdout,stderr=proc.communicate(None if cancel else b'{}',timeout=12)
   elapsed=time.monotonic()-t
   log=(p/'fake.log').read_text() if (p/'fake.log').exists() else ''
   return proc.returncode,elapsed,log,stdout,stderr
 def test_success(self):
  r=self.run_case('');self.assertEqual(r[0],0,r);self.assertIn('rm',r[2]);self.assertIn(b'OK',r[3])
 def test_failures_cleanup(self):
  for fault in ['createfail','badpolicy','startfail','oom','cleanupfail']:
   with self.subTest(fault=fault):
    r=self.run_case(fault);self.assertNotEqual(r[0],0,r);self.assertIn('rm',r[2],r)
 def test_deadline(self):
  r=self.run_case('hang');self.assertNotEqual(r[0],0,r);self.assertLess(r[1],10,r);self.assertIn('rm',r[2],r)
 def test_parent_cancellation(self):
  r=self.run_case('hang',True);self.assertNotEqual(r[0],0,r);self.assertLess(r[1],10,r);self.assertIn('rm',r[2],r)
class OutputContract(unittest.TestCase):
 def call(self,result=None,error=None,pointer=''):
  import io
  with tempfile.NamedTemporaryFile(dir=tempfile.gettempdir()) as f:
   f.write(b'{}');f.flush();argv=['entry.py','hook','--root','/fixture','--store','/store','--host','codex','--input',f.name,'--pointer',pointer]
   output=io.StringIO()
   with patch.object(sys,'argv',argv),patch.object(entry,'execute',return_value=result,side_effect=error),contextlib.redirect_stdout(output):rc=entry.main()
   return rc,json.loads(output.getvalue())
 def test_host_native_output(self):
  result={'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':'synthetic'}}
  self.assertEqual(self.call(result), (0,result))
 def test_unknown_hook_advisory(self):
  rc,out=self.call(error=ValueError('fixture'));self.assertEqual(rc,0);self.assertIn('systemMessage',out)
 def test_required_hook_error(self):
  rc,out=self.call(error=ValueError('fixture'),pointer='required');self.assertEqual(rc,2);self.assertIn('systemMessage',out)
class RequiredBusy(unittest.TestCase):
 def test_real_entry_busy_pointer(self):
  import io
  with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as tmp:
   root=Path(tmp)/'repo';store=Path(tmp)/'store';root.mkdir();store.mkdir()
   payload={'hook_event_name':'SessionStart','cwd':str(root),'session_id':'fixture'}
   path=Path(tmp)/'input.json';path.write_text(json.dumps(payload))
   for pointer,expected in [('a'*32+'-1-'+'b'*12,2),('',0)]:
    argv=['entry.py','hook','--root',str(root),'--store',str(store),'--host','codex','--input',str(path),'--pointer',pointer]
    with patch.object(sys,'argv',argv),patch.object(guard,'git',return_value=str(root).encode()),patch.object(guard,'locked',side_effect=guard.LockBusy),contextlib.redirect_stdout(io.StringIO()):
     self.assertEqual(entry.main(),expected)
class CorrectedLifecycle(unittest.TestCase):
 run_case=Lifecycle.run_case
 def test_malformed_streams(self):
  for fault in ['malformed','empty','wrongshape','oversize']:
   with self.subTest(fault=fault):
    r=self.run_case(fault);self.assertNotEqual(r[0],0,r);self.assertEqual(r[3],b'',r);self.assertIn('rm',r[2],r);self.assertEqual(r[2].count('start\n'),2,r)
 def test_preflight_in_deadline(self):
  r=self.run_case('',preflight_stall=True);self.assertNotEqual(r[0],0,r);self.assertLess(r[1],10,r);self.assertEqual(r[2],'',r)
 def test_null_template_is_not_mocked_away(self):
  # The fake rejects the former template exactly as the real Go formatter does.
  with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as t:
   state=Path(t)/'state';state.write_text(json.dumps({'image':'x','user':'0:0'}))
   r=subprocess.run([sys.executable,(TESTS + '/fake_docker.py'),'inspect','--format','{{.HostConfig.NanoCpus}}|{{len .HostConfig.DeviceRequests}}','x'],env=dict(os.environ,FAKE_STATE=str(state)),capture_output=True)
   self.assertNotEqual(r.returncode,0);self.assertIn(b'len of nil',r.stderr)
class Validator(unittest.TestCase):
 def test_shape_matrix(self):
  import validate
  for mode in ['hook','checkpoint','resume']:
   for v in [None,[],1,'x',{'result':None},{'status':'OK','result':[]},{'hookSpecificOutput':None}]:
    with self.subTest(mode=mode,value=v):self.assertRaises(ValueError,validate.validate,mode,v)
  validate.validate('hook',{})
  validate.validate('resume',{'status':'OK','result':{'context':''}})
  validate.validate('checkpoint',{'status':'OK','result':{'checkpoint_id':'a'*32+'-1-'+'b'*12}})
 def test_duplicate_keys(self):
  import validate
  self.assertRaises(ValueError,json.loads,'{"status":"OK","status":"bad"}',object_pairs_hook=validate.pairs)

if __name__=='__main__':unittest.main(verbosity=2)
