import ast,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import launcher
class Tests(unittest.TestCase):
 def test_inputs_and_order_both_phases(self):
  self.assertIn('tar-foreign-owner.tar.gz',launcher.FILES);self.assertIn('tar-preflight.sh',launcher.FILES)
  s=Path('build.sh').read_text();gate=s.index('/bin/sh /input/tar-preflight.sh')
  self.assertLess(s.index('apk --no-network'),gate);self.assertLess(gate,s.index('while IFS='));self.assertLess(gate,s.index('make switch'))
  self.assertIn('tar-preflight.txt',launcher.EXPORTS)
 def test_fixture_pin(self):
  h=hashlib.sha256(Path('tar-foreign-owner.tar.gz').read_bytes()).hexdigest();self.assertIn(h,Path('tar-preflight.sh').read_text())
 def exercise(self,failure='',corrupt=False):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td);(d/'input').mkdir();(d/'work').mkdir();(d/'bin').mkdir()
   (d/'input/tar-foreign-owner.tar.gz').write_bytes(b'bad' if corrupt else Path('tar-foreign-owner.tar.gz').read_bytes())
   script='#!'+sys.executable+'\n'+'''import os,sys,pathlib,hashlib
name=pathlib.Path(sys.argv[0]).name
with open(os.environ['CALLS'],'a') as f:f.write(name+'\\n')
if name=='sha256sum':
 if '-c' in sys.argv:
  digest,path=sys.stdin.read().strip().split(None,1)
  sys.exit(0 if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==digest else 1)
 print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest());sys.exit(0)
if name=='readlink':print(sys.argv[-1]);sys.exit(0)
if name=='timeout':os.execv(sys.argv[2],sys.argv[2:]) if '/' in sys.argv[2] else os.execvp(sys.argv[2],sys.argv[2:])
if name=='tar':
 if os.environ.get('FAIL')=='tar':sys.exit(2)
 pathlib.Path('authored.txt').write_bytes(b'AF03 ownership-neutral option fixture\\n');sys.exit(0)
if name=='stat':print('999' if os.environ.get('FAIL')=='owner' else '0');sys.exit(0)
if name=='id':print('0');sys.exit(0)
'''
   for n in ('sha256sum','readlink','timeout','tar','stat','id'):
    f=d/'bin'/n;f.write_text(script);f.chmod(0o700)
   body=Path('tar-preflight.sh').read_text().replace('/input/',str(d/'input')+'/').replace('/work/',str(d/'work')+'/')
   env=dict(os.environ,PATH=str(d/'bin')+':/usr/bin:/bin',CALLS=str(d/'calls'),FAIL=failure)
   r=subprocess.run(['/bin/sh','-c',body],env=env,capture_output=True,timeout=5)
   return r,(d/'calls').read_text()
 def test_mock_success(self):
  r,c=self.exercise();self.assertEqual(r.returncode,0,r.stderr);self.assertIn(b'TAR_FOREIGN_OWNER_GZIP_PASS',r.stdout)
 def test_mock_tar_failure(self):
  r,c=self.exercise('tar');self.assertNotEqual(r.returncode,0);self.assertNotIn('stat',c);self.assertNotIn(b'_PASS',r.stdout)
 def test_mock_owner_failure(self):
  r,c=self.exercise('owner');self.assertNotEqual(r.returncode,0);self.assertNotIn(b'_PASS',r.stdout)
 def test_corrupt_fixture_stops_before_tar(self):
  r,c=self.exercise(corrupt=True);self.assertNotEqual(r.returncode,0);self.assertNotIn('tar',c)
if __name__=='__main__':unittest.main()
