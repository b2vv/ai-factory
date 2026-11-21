import importlib.util,io,tarfile,unittest,tempfile,os,json
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
spec=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('launcher.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def fixture(name='compiler.txt',kind=tarfile.REGTYPE,payload=b'ok',link='',extra=False):
 b=io.BytesIO()
 with tarfile.open(fileobj=b,mode='w',format=tarfile.USTAR_FORMAT) as t:
  x=tarfile.TarInfo(name);x.type=kind;x.linkname=link;x.size=len(payload) if kind==tarfile.REGTYPE else 0;t.addfile(x,io.BytesIO(payload) if x.size else None)
  if extra:t.addfile(tarfile.TarInfo('extra'))
 return b.getvalue()
class Tests(unittest.TestCase):
 def test_regular(self):self.assertEqual(m.decode_export(fixture(),'compiler.txt',2),b'ok')
 def test_link(self):
  with self.assertRaises(ValueError):m.decode_export(fixture(kind=tarfile.SYMTYPE,link='/etc/passwd'),'compiler.txt',10)
 def test_hardlink(self):
  with self.assertRaises(ValueError):m.decode_export(fixture(kind=tarfile.LNKTYPE,link='/etc/passwd'),'compiler.txt',10)
 def test_fifo(self):
  with self.assertRaises(ValueError):m.decode_export(fixture(kind=tarfile.FIFOTYPE),'compiler.txt',10)
 def test_traversal(self):
  with self.assertRaises(ValueError):m.decode_export(fixture('../compiler.txt'),'compiler.txt',10)
 def test_absolute(self):
  with self.assertRaises(ValueError):m.decode_export(fixture('/compiler.txt'),'compiler.txt',10)
 def test_cap(self):
  with self.assertRaises(ValueError):m.decode_export(fixture(),'compiler.txt',1)
 def test_extra(self):
  with self.assertRaises(ValueError):m.decode_export(fixture(extra=True),'compiler.txt',10)
 def test_truncated(self):
  with self.assertRaises((ValueError,tarfile.TarError)):m.decode_export(fixture()[:513],'compiler.txt',10)
 def test_input_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'x').write_text('x');(p/'y').symlink_to(p/'x')
   with self.assertRaises(ValueError):m.regular(p/'y')
 def test_input_hardlink(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'x').write_text('x');os.link(p/'x',p/'y')
   with self.assertRaises(ValueError):m.regular(p/'y')
class LifecycleTests(unittest.TestCase):
 def test_uncertain_create_no_retry(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);run=m.Runner(root);proc=SimpleNamespace(stdout=io.BytesIO(),returncode=None)
   proc.kill=lambda:setattr(proc,'returncode',-9);proc.wait=lambda timeout:proc.returncode
   with patch.object(m.subprocess,'Popen',return_value=proc) as popen,patch.object(m.time,'monotonic',side_effect=[0,21,22]):
    with self.assertRaises(TimeoutError):run.call(['create','--name','exact-name'])
   self.assertEqual(popen.call_count,1)
   receipt=json.loads((root/'001-command.json').read_text());self.assertTrue(receipt['uncertain_mutation']);self.assertIn('reconcile',receipt['error'])
 def test_export_transport_cap(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);run=m.Runner(root);pipe=SimpleNamespace(fileno=lambda:123,close=lambda:None);proc=SimpleNamespace(stdout=pipe,returncode=None)
   proc.kill=lambda:setattr(proc,'returncode',-9);proc.wait=lambda timeout:proc.returncode
   with patch.object(m.subprocess,'Popen',return_value=proc),patch.object(m.select,'select',return_value=([pipe],[],[])),patch.object(m.os,'read',return_value=b'oversized'):
    with self.assertRaises(ValueError):run.call(['cp','cid:/file','-'],limit=1)
   self.assertEqual(json.loads((root/'001-command.json').read_text())['error'],'ValueError: command output cap')
if __name__=='__main__':unittest.main()

