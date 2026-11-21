import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import export_release as e
import kit
class Export(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name).resolve();self.root=self.base/'source';self.root.mkdir()
  inv={}
  for i in range(30):
   n=e.PREFIX+str(i)+'.txt';p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('inert');inv[n]=kit.digest(p.read_bytes())
  p=self.root/e.ARCHIVE;p.parent.mkdir();p.write_bytes(kit.encode({'schema_version':1,'status':'PAUSED_SUPERSEDED_NOT_RUNNABLE','files':inv}))
  (self.root/'hello.txt').write_text('payload');files=[{'path':n,'sha256':kit.digest((self.root/n).read_bytes()),'component':'core'} for n in ['hello.txt',e.ARCHIVE]]
  (self.root/'release-manifest.json').write_bytes(kit.encode({'schema_version':2,'components':{'core':{}},'files':files}))
  (self.root/'checksums.sha256').write_text(''.join(kit.digest((self.root/n).read_bytes())+'  '+n+'\n' for n in ['hello.txt',e.ARCHIVE,'release-manifest.json']))
 def test_exact_export(self):
  out=self.base/'out';self.assertEqual(e.export(self.root,out)['files'],4);self.assertFalse((out/'work').exists());kit.payload(out,[])
 def test_strict_payload_unchanged(self):
  with self.assertRaises(ValueError):kit.payload(self.root,[])
 def test_undeclared(self):
  (self.root/'unlisted').write_text('x')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_tampered_archive(self):
  (self.root/e.PREFIX/'0.txt').write_text('changed')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_missing_archive(self):
  (self.root/e.PREFIX/'0.txt').unlink()
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_symlink(self):
  p=self.root/e.PREFIX/'0.txt';p.unlink();p.symlink_to(self.root/'hello.txt')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_hardlink(self):
  os.link(self.root/e.PREFIX/'0.txt',self.base/'link')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_fifo(self):
  os.mkfifo(self.root/'pipe')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_tampered_payload(self):
  (self.root/'hello.txt').write_text('bad')
  with self.assertRaises(ValueError):e.collect(self.root)
 def test_existing_destination(self):
  with self.assertRaises(ValueError):e.export(self.root,self.root)
if __name__=='__main__':unittest.main()
