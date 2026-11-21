import ast,contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import launcher
class Tests(unittest.TestCase):
 def exercise(self,fail_at,primary=True):
  tree=ast.parse(Path('launcher.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  block=next(n for n in main.body if isinstance(n,ast.Try) and n.finalbody)
  # Exact production handlers/finally; replace only build body with authored failure/success.
  block.body=ast.parse('raise primary_error' if primary else "state['phase_result']='PASS_TWO_PHASE_CE_PROTOTYPE_NOT_RELEASE';state['status']='CLEANUP_PENDING'").body
  calls=[];saved=[];counter=0
  original=ValueError('PRIMARY identity');disk=OSError('injected receipt failure')
  state={'containers':['cid'],'volumes':['vol'],'status':'online'}
  class Run:
   uncertain_cids=set()
   def __init__(self):self.diagnostic_errors=[]
   def call(self,args,**kw):calls.append(args);return b''
   def obj(self,args,**kw):calls.append(args);return [{'State':{'Running':False},'Labels':{'ai-factory.task':'af03-ce-build-v2'}}]
   def save_bytes(self,name,data):calls.append(['save_bytes',name]);return True
  run=Run()
  def save():
   nonlocal counter
   counter+=1
   if fail_at=='all' or counter==fail_at:raise disk
   saved.append(json.loads(json.dumps(state)))
  err=None;stderr=io.StringIO()
  with tempfile.TemporaryDirectory() as d:
   ns={'state':state,'run':run,'sys':sys,'signal':SimpleNamespace(SIGINT=2,SIGTERM=15,SIG_IGN=1,signal=lambda *a:None),'before_c':[],'before_v':[], 'save':save,'a':SimpleNamespace(run=Path(d)),'decode_export':lambda *a:b'phase=online stage=core-start\n','persist_failure_receipt':getattr(launcher,'persist_failure_receipt',None),'primary_error':original}
   with contextlib.redirect_stderr(stderr):
    try:exec(compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),'exact-main-handlers','exec'),ns)
    except Exception as e:err=e
  return state,err,original,disk,calls,saved,stderr.getvalue()
 def test_before_capture_save(self):self.primary_check(1,'before-failure-capture')
 def test_after_capture_save(self):self.primary_check(2,'after-failure-capture')
 def test_final_save(self):self.primary_check(5,'final-completion')
 def primary_check(self,index,stage):
  s,e,original,disk,calls,saved,stderr=self.exercise(index)
  self.assertIs(e,original);self.assertEqual(s['status'],'BLOCKED')
  self.assertTrue(any(c[0]=='logs' for c in calls));self.assertTrue(any(c[0]=='cp' for c in calls))
  self.assertIn(['rm','cid'],calls);self.assertIn(['volume','rm','vol'],calls)
  self.assertEqual(s['containers'],[]);self.assertEqual(s['volumes'],[])
  self.assertEqual(s['persistence_errors'][0]['stage'],stage);self.assertIn('persistence_error',stderr)
  if index<5:self.assertTrue(any(x.get('persistence_errors') for x in saved))
 def test_all_writes_fail_primary_still_identity(self):
  s,e,original,disk,calls,_,_=self.exercise('all');self.assertIs(e,original)
  self.assertIn(['rm','cid'],calls);self.assertIn(['volume','rm','vol'],calls);self.assertEqual(s['status'],'BLOCKED')
 def test_no_primary_final_save_nonzero(self):
  # No failure-capture saves: cleanup rm, volume-rm, then final is third save.
  s,e,_,disk,calls,_,stderr=self.exercise(3,False)
  self.assertIs(e,disk);self.assertEqual(s['status'],'BLOCKED');self.assertTrue(s['phase_result'].startswith('PASS'))
  self.assertIn('final-completion',stderr)
 def test_clean_path(self):
  s,e,*_=self.exercise(99,False);self.assertIsNone(e);self.assertTrue(s['status'].startswith('PASS'))
if __name__=='__main__':unittest.main()
