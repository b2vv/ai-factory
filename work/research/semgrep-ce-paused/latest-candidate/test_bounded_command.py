import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bounded_command as b
class Tests(unittest.TestCase):
 def test_stderr_limit_before_capture_completes(self):
  with self.assertRaises(b.OutputLimit) as c:b.run([sys.executable,'-c',"import os;os.write(2,b'x'*1000000)"])
  self.assertEqual(len(c.exception.stderr),8192);self.assertTrue(c.exception.truncated[1])
 def test_stdout_limit(self):
  with self.assertRaises(b.OutputLimit) as c:b.run([sys.executable,'-c',"import os;os.write(1,b'x'*2000000)"])
  self.assertEqual(len(c.exception.stdout),1048576)
 def test_nonutf8_separate(self):
  r=b.run([sys.executable,'-c',"import os;os.write(1,b'[]');os.write(2,bytes([255,0]))"])
  self.assertEqual(r.stdout,'[]');self.assertIn('\ufffd',r.stderr)
 def test_timeout(self):
  with self.assertRaises(subprocess.TimeoutExpired) as c:b.run([sys.executable,'-c',"import os,time;os.write(2,b'cause');time.sleep(5)"],timeout=.3)
  self.assertEqual(c.exception.stderr,b'cause')
 def test_attach_tail_is_bounded(self):
  p=subprocess.Popen([sys.executable,'-c',"import os;os.write(1,b'A'*10000);os.write(2,b'B'*100000)"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  d=b.Drain(p);p.wait(timeout=3);r=d.snapshot();p.stdout.close();p.stderr.close()
  self.assertEqual(len(r[0]['tail']),2048);self.assertEqual(len(r[1]['tail']),8192);self.assertEqual(r[1]['observed_bytes'],100000)
 def test_watchdog_prestart_parse_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   script=Path(__file__).with_name('watchdog.py');code="import sys,runpy;from unittest.mock import patch;from types import SimpleNamespace;sys.path.insert(0,sys.argv[1]);sys.argv=[sys.argv[1]+'/watchdog.py','config','a'*64,sys.argv[2],'online','1'];p=patch('bounded_command.run',return_value=SimpleNamespace(stdout='bad JSON'));p.start();runpy.run_path(sys.argv[0],run_name='__main__')"
   c=subprocess.run([sys.executable,'-B','-c',code,str(script.parent),d],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(c.returncode,0);self.assertEqual(json.loads((Path(d)/'protocol-error.json').read_text())['stage'],'prestart');self.assertEqual(json.loads((Path(d)/'unhandled-error.json').read_text())['error_type'],'JSONDecodeError')
 def test_watchdog_prestart_assert_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   script=Path(__file__).with_name('watchdog.py');code="import sys,runpy,json;from unittest.mock import patch;from types import SimpleNamespace;sys.path.insert(0,sys.argv[1]);sys.argv=[sys.argv[1]+'/watchdog.py','config','a'*64,sys.argv[2],'online','1'];p=patch('bounded_command.run',return_value=SimpleNamespace(stdout=json.dumps([{'Name':'WRONG','State':{'Running':False}}])));p.start();runpy.run_path(sys.argv[0],run_name='__main__')"
   c=subprocess.run([sys.executable,'-B','-c',code,str(script.parent),d],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(c.returncode,0);self.assertEqual(json.loads((Path(d)/'unhandled-error.json').read_text())['error_type'],'AssertionError')
if __name__=='__main__':unittest.main()
