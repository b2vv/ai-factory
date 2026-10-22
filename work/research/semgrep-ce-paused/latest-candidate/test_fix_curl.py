import importlib.util,hashlib,tempfile,unittest,os
from pathlib import Path
s=importlib.util.spec_from_file_location('fix',Path(__file__).with_name('fix_curl.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
RAW=Path(__file__).with_name('helper-before.fixture').read_bytes()
class Tests(unittest.TestCase):
 def test_exact_one_line(self):
  new=m.transform(RAW)
  self.assertEqual(new.replace(m.NEW,m.OLD),RAW)
  self.assertEqual(hashlib.sha256(new).hexdigest(),m.AFTER)
  self.assertIn(b'| sha256sum -c -',new);self.assertIn(b'05fc17ff25b793a437a0906e0484b82172a9f4de02be5ed447e0cab8c3475add',new)
  self.assertLess(new.index(b'| sha256sum -c -'),new.index(m.NEW))
 def test_drift(self):
  with self.assertRaises(ValueError):m.transform(RAW+b'\n')
 def test_duplicate(self):
  with self.assertRaises(ValueError):m.transform(RAW+m.OLD)
 def test_missing(self):
  with self.assertRaises(ValueError):m.transform(RAW.replace(m.OLD,b''))
 def test_no_implicit_repeat(self):
  with self.assertRaises(ValueError):m.transform(m.transform(RAW))
 def test_scoped_apply(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();(p/'scripts').mkdir();f=p/'scripts/build-static-libcurl.sh';f.write_bytes(RAW);f.chmod(0o750);other=p/'other';other.write_bytes(RAW)
   m.apply(p);self.assertEqual(f.read_bytes(),m.transform(RAW));self.assertEqual(f.stat().st_mode&0o777,0o750);self.assertEqual(other.read_bytes(),RAW)
 def test_symlink_rejected_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();(p/'scripts').mkdir();f=p/'original';f.write_bytes(RAW);(p/'scripts/build-static-libcurl.sh').symlink_to(f)
   with self.assertRaises(ValueError):m.apply(p)
   self.assertEqual(f.read_bytes(),RAW)
 def test_hardlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();(p/'scripts').mkdir();f=p/'original';f.write_bytes(RAW);os.link(f,p/'scripts/build-static-libcurl.sh')
   with self.assertRaises(ValueError):m.apply(p)
   self.assertEqual(f.read_bytes(),RAW)
 def test_no_global_tar_override(self):
  script=Path(__file__).with_name('build.sh').read_text()
  self.assertNotIn('TAR_OPTIONS',script)
  self.assertLess(script.index('python3 /input/fix_curl.py'),script.index('make install-deps'))
if __name__=='__main__':unittest.main()
