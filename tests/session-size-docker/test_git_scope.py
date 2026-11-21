"""Package never grants Git trust; all subprocesses below are mocked."""
import sys, unittest, subprocess
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/session-size-docker'))
import guard, entry
class Scope(unittest.TestCase):
 def test_all_operations_no_trust_override(self):
  for root in ['/fixture/repo','/fixture/other','*']:
   with guard.mapped_git_root(root),patch.object(guard.subprocess,'check_output',return_value=b'fixture') as call:
    for op in guard.METADATA_GIT_OPERATIONS:
     guard.git(root,*op)
     self.assertEqual(call.call_args.args[0],['git','--no-optional-locks','-c','core.fsmonitor=false','-C',root,*op])
     self.assertEqual(call.call_args.kwargs,{'stderr':subprocess.PIPE,'timeout':3})
   self.assertIsNone(guard._COMMAND_ROOT)
 def test_disallowed_operation_and_cwd_no_subprocess(self):
  with guard.mapped_git_root('/fixture/repo'),patch.object(guard.subprocess,'check_output') as call:
   for op in [('config','--global','safe.directory','*'),('commit',),('status','--porcelain=v1')]:
    self.assertRaises(ValueError,guard.git,'/fixture/repo',*op)
   for cwd in ['/other','/fixture/repo/../other','/fixture/repo-other']:
    self.assertRaises(ValueError,guard.git,cwd,'rev-parse','HEAD')
   call.assert_not_called()
 def test_context_restored_on_error(self):
  with self.assertRaises(RuntimeError):
   with guard.mapped_git_root('/fixture/repo'):raise RuntimeError('fixture')
  self.assertIsNone(guard._COMMAND_ROOT)
 def test_git_ownership_error_stays_failure(self):
  with guard.mapped_git_root('/fixture/repo'),patch.object(guard.subprocess,'check_output',side_effect=subprocess.CalledProcessError(128,['git'],stderr=b'fatal: detected dubious ownership')):
   self.assertRaises(guard.SnapshotCheckFailed,guard.git,'/fixture/repo','rev-parse','HEAD')
 def test_root_mismatch_blocks_worker(self):
  a=SimpleNamespace(root='/fixture/repo',store='/store',mode='checkpoint',session='fixture',host='codex')
  with patch.object(entry,'checked_path',side_effect=lambda x:Path(x)),patch.object(Path,'is_dir',return_value=True),patch.object(guard.subprocess,'check_output',return_value=b'/different/root'),patch.object(guard,'checkpoint') as checkpoint:
   self.assertRaises(ValueError,entry.execute,a,b'{}');checkpoint.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
