"""Current Docker guard CLI never silently chooses the legacy hook store."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ExplicitStore(unittest.TestCase):
 def test_manual_modes_require_explicit_store_without_creating_default(self):
  with tempfile.TemporaryDirectory() as temp:
   home=Path(temp).resolve()
   for mode in ('checkpoint','resume','resolve','candidates'):
    r=subprocess.run([sys.executable,'-B',str(ROOT/'runtime/session-size-docker/guard.py'),mode,'--host','claude','--session','synthetic'],input=b'{}',capture_output=True,env=dict(os.environ,HOME=str(home)))
    self.assertEqual(r.returncode,2);self.assertIn(b'EXPLICIT_STORE_REQUIRED',r.stderr)
    self.assertFalse((home/'.agents/session-handoffs').exists())
 def test_relative_store_rejected_before_state_access(self):
  with tempfile.TemporaryDirectory() as temp:
   r=subprocess.run([sys.executable,'-B',str(ROOT/'runtime/session-size-docker/guard.py'),'checkpoint','--host','codex','--store','relative'],cwd=temp,input=b'{}',capture_output=True)
   self.assertEqual(r.returncode,2);self.assertIn(b'EXPLICIT_STORE_REQUIRED',r.stderr);self.assertFalse((Path(temp)/'relative').exists())
if __name__=='__main__':unittest.main()
