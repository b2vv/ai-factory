import subprocess,unittest
from types import SimpleNamespace as R
import disk_sample as d
GOOD=b'878500\t/work\n398960\t/capture\n'
ERR=("du: cannot access '"+d.PREFIX+"conftest': No such file or directory\n").encode()
def bad(err=ERR,out=GOOD):
 e=subprocess.CalledProcessError(1,['du'],output=out,stderr=err);e.truncated=[False,False];return e
class Tests(unittest.TestCase):
 def go(self,items):
  receipts=[];calls=[]
  def run(timeout):
   calls.append(timeout);item=items.pop(0)
   if isinstance(item,BaseException):raise item
   return item
  try:return d.sample(run,lambda r:receipts.append(__import__('copy').deepcopy(r)),lambda:None,10),receipts,calls
  except BaseException as e:return e,receipts,calls
 def test_one_clean_resample(self):
  result,r,c=self.go([bad(ERR+ERR.replace(b'conftest',b'conftest.c')),R(returncode=0,stdout=GOOD,stderr=b'')]);self.assertEqual(result,[878500,398960]);self.assertEqual(len(c),2);self.assertLessEqual(c[1],c[0]);self.assertEqual(len(r[-1]['attempts']),2)
 def test_clean_no_retry(self):self.assertEqual(len(self.go([R(returncode=0,stdout=GOOD,stderr=b'')])[2]),1)
 def test_bad_diagnostics(self):
  for err in [b'Permission denied\n',b'I/O error\n',ERR+b'other\n',ERR.replace(b'conftest',b'../x'),ERR.replace(d.PREFIX.encode(),b'/capture/'),ERR.replace(d.PREFIX.encode(),b'/work/'),ERR+b'\xff',ERR.replace(b'conftest',b"a'b")]:
   with self.subTest(err=err):
    result,r,c=self.go([bad(err)]);self.assertIsInstance(result,Exception);self.assertEqual(len(c),1)
 def test_bad_rows(self):
  for out in [b'1\t/work\n',b'1\t/work\n2\t/work\n',b'-1\t/work\n2\t/capture\n',b'1 /work\n2 /capture\n',b'\xff']:
   self.assertIsInstance(self.go([bad(out=out)])[0],Exception)
 def test_repeated_error_stops(self):self.assertIsInstance(self.go([bad(),bad()])[0],Exception)
 def test_truncated_stops(self):
  e=bad();e.truncated=[False,True];self.assertEqual(len(self.go([e])[2]),1)
 def test_timeout_stops(self):self.assertEqual(len(self.go([subprocess.TimeoutExpired('du',3)])[2]),1)
 def test_threshold_initial_and_resample(self):
  over=b'1\t/work\n2097153\t/capture\n'
  self.assertEqual(len(self.go([bad(out=over)])[2]),1)
  self.assertIsInstance(self.go([bad(),R(returncode=0,stdout=over,stderr=b'')])[0],Exception)
 def test_clean_with_stderr_blocks(self):self.assertIsInstance(self.go([bad(),R(returncode=0,stdout=GOOD,stderr=ERR)])[0],Exception)
 def test_deadline_no_second_call(self):
  ticks=iter([0,0,4]);calls=[]
  with self.assertRaises(TimeoutError):d.sample(lambda t:(calls.append(t) or (_ for _ in ()).throw(bad())),lambda r:None,lambda:None,3,clock=lambda:next(ticks))
  self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main()
