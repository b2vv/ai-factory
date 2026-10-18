import tempfile,json,unittest
from pathlib import Path
import kit
class ComponentTests(unittest.TestCase):
 def fixture(self,root,components):
  p=root/'a.md';p.write_text('fixture');m={'schema_version':2,'version':'fixture','components':components,'files':[{'path':'a.md','component':'leaf','sha256':kit.digest(p.read_bytes())}]};(root/'release-manifest.json').write_bytes(kit.encode(m));(root/'checksums.sha256').write_text(''.join(kit.digest(p.read_bytes())+'  '+p.name+'\n' for p in [root/'a.md',root/'release-manifest.json']))
 def test_transitive_alias_and_dedup(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();self.fixture(p,{'core':{},'alias':{'dependencies':['leaf','core']},'leaf':{'dependencies':['core']}});_,files,selected=kit.payload(p,['alias','leaf']);self.assertEqual(['alias','core','leaf'],selected);self.assertIn('a.md',files)
 def test_cycle_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();self.fixture(p,{'core':{},'alias':{'dependencies':['leaf']},'leaf':{'dependencies':['alias']}})
   with self.assertRaises(ValueError):kit.payload(p,['alias'])
 def test_unknown_dependency_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();self.fixture(p,{'core':{},'leaf':{'dependencies':['missing']}})
   with self.assertRaises(ValueError):kit.payload(p,['leaf'])
