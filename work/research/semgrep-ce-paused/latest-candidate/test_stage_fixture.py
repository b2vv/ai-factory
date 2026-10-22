import io,tarfile,unittest
from pathlib import Path
from prepare_tar_fixture import fixture,PAYLOAD
class Tests(unittest.TestCase):
 def test_authored_compressed_foreign_owner(self):
  raw=fixture();self.assertEqual(raw[:2],b'\x1f\x8b')
  with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
   members=archive.getmembers();self.assertEqual(len(members),1)
   m=members[0];self.assertTrue(m.isfile());self.assertEqual((m.uid,m.gid),(12345,23456))
   self.assertEqual(archive.extractfile(m).read(),PAYLOAD)
 def test_stage_trap_failure(self):
  import subprocess,tempfile
  s=Path('build.sh').read_text();block=s[s.index('stage() {'):s.index('stage setup')]
  with tempfile.TemporaryDirectory() as tmp:
   block=block.replace('/work/evidence/stage.txt',tmp+'/stage.txt')
   p=subprocess.run(['/bin/sh','-c','set -eu; phase=offline;\n'+block+'stage core-start\nfalse'],capture_output=True)
   self.assertEqual(p.returncode,1);self.assertIn(b'stage=core-start exit=1',p.stderr)
   self.assertEqual(Path(tmp,'stage.txt').read_text(),'phase=offline stage=core-start\n')
 def test_stage_scopes(self):
  s=Path('build.sh').read_text()
  for stage in ('switch','curl-patch','install-deps','core','cli'):
   self.assertIn('stage '+stage+'-start',s);self.assertIn('stage '+stage+'-complete',s)
if __name__=='__main__':unittest.main()
