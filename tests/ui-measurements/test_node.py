"""Plain deterministic boundary coverage; real layout is in test_browser.py."""
import os,shutil,subprocess,unittest
from pathlib import Path
class NodeBoundary(unittest.TestCase):
 def test_public_measurement_contract(self):
  node=shutil.which('node')
  if not node:
   if os.environ.get('AI_FACTORY_REQUIRE_UI_NODE')=='1':self.fail('Required Node unavailable')
   self.skipTest('NOT_TESTED deterministic UI measurements: Node unavailable')
  r=subprocess.run([node,str(Path(__file__).with_name('cases.cjs'))],capture_output=True,text=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main(verbosity=2)
