import ast,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import launcher
class Tests(unittest.TestCase):
 def cleanup(self,fault=None,primary=False):
  tree=ast.parse(Path('launcher.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  block=next(n for n in main.body if isinstance(n,ast.Try) and n.finalbody)
  state={'containers':['cid'],'volumes':['vol'],'phase_result':'PASS_TWO_PHASE_CE_PROTOTYPE_NOT_RELEASE','status':'CLEANUP_PENDING'}
  class Run:
   uncertain_cids=set();diagnostic_errors=['failed receipt'] if fault=='diagnostic' else []
   def obj(self,args):
    return [{'State':{'Running':False},'Labels':{'ai-factory.task':'af03-ce-build-v2'}}]
   def call(self,args):
    if (fault=='rm' and args[0]=='rm') or (fault=='volume-rm' and args[:2]==['volume','rm']) or (fault=='list' and args==['ps','-aq','--no-trunc']):raise RuntimeError('injected '+fault)
    if args==['ps','-aq','--no-trunc']:return b'' if fault=='preservation' else b'prior\n'
    if args==['volume','ls','-q']:return b'priorvol\n'
    return b''
  body=ast.parse("raise ValueError('PRIMARY')" if primary else 'pass').body
  wrapper=ast.Try(body=body,handlers=[],orelse=[],finalbody=block.finalbody)
  ns={'state':state,'run':Run(),'sys':sys,'before_c':['prior'],'before_v':['priorvol'],'save':lambda:None,'persist_failure_receipt':launcher.persist_failure_receipt}
  error=None
  try:exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'exact-main-cleanup','exec'),ns)
  except Exception as e:error=e
  return state,error
 def test_clean_pass(self):
  s,e=self.cleanup();self.assertIsNone(e);self.assertTrue(s['status'].startswith('PASS'))
 def test_cleanup_failures_block(self):
  for fault in ('rm','volume-rm','list','diagnostic','preservation'):
   with self.subTest(fault=fault):
    s,e=self.cleanup(fault);self.assertEqual(s['status'],'BLOCKED');self.assertIsInstance(e,RuntimeError);self.assertTrue(s['phase_result'].startswith('PASS'))
 def test_primary_preserved(self):
  s,e=self.cleanup('rm',True);self.assertEqual(str(e),'PRIMARY');self.assertEqual(s['status'],'BLOCKED');self.assertTrue(s['cleanup_errors'])
 def supervise_case(self,code):
  with tempfile.TemporaryDirectory() as d:
   run=SimpleNamespace(root=Path(d),env={},diagnostic_errors=[],uncertain_cids=set())
   child=SimpleNamespace(returncode=code,wait=lambda **k:code,poll=lambda:code)
   def write(path,data,*a,**k):
    if path.name=='watchdog-child.json':raise OSError('disk failure')
    return len(data)
   with patch('launcher.subprocess.Popen',return_value=child),patch('launcher.stopped_state',return_value={'Running':False}),patch.object(Path,'write_text',write):
    with self.assertRaises(RuntimeError) as got:launcher.supervise(run,['mock'],'cid',1)
   return str(got.exception),run.diagnostic_errors
 def test_child_receipt_blocks_success(self):
  msg,errors=self.supervise_case(0);self.assertIn('diagnostic persistence failed',msg);self.assertTrue(errors)
 def test_child_receipt_preserves_failure(self):
  msg,errors=self.supervise_case(7);self.assertEqual(msg,'watchdog exit 7');self.assertTrue(errors)
if __name__=='__main__':unittest.main()
