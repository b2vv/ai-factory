import io,tarfile,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import launcher
class Tests(unittest.TestCase):
 def case(self,mode):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);r=launcher.Runner(root);r.count=1
   raw=io.BytesIO()
   with tarfile.open(fileobj=raw,mode='w') as tf:
    m=tarfile.TarInfo('tar-preflight.txt');m.size=65537 if mode=='oversize' else 2
    if mode=='symlink':m.type=tarfile.SYMTYPE;m.linkname='/outside';m.size=0
    tf.addfile(m,io.BytesIO(b'x'*m.size))
   def call(*args,**kwargs):
    if mode in ('missing','error'):
     (root/'001-stderr.bin').write_bytes(b'Error response from daemon: Could not find the file /work/evidence/tar-preflight.txt in container cid\n' if mode=='missing' else b'permission denied')
     raise RuntimeError('cp failed')
    return raw.getvalue()
   with patch.object(r,'call',side_effect=call):result=launcher.capture_tar_receipt(r,'cid','online')
   return result,list(x.name for x in root.iterdir())
 def test_success(self):
  r,files=self.case('ok');self.assertEqual(r['status'],'CAPTURED');self.assertIn('online-tar-preflight.txt',files)
 def test_missing_distinct(self):self.assertEqual(self.case('missing')[0]['status'],'MISSING_OR_NOT_REACHED')
 def test_other_failures(self):
  for mode in ('error','symlink','oversize'):
   r,files=self.case(mode);self.assertEqual(r['status'],'CAPTURE_FAILED');self.assertNotIn('online-tar-preflight.txt',files)
if __name__=='__main__':unittest.main()
