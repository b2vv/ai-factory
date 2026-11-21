"""Local authored synthetic child only; no Docker or downloaded code."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('launcher.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def run_case(self,body,args=None,limit=65536,timeout=3,error=None):
  with tempfile.TemporaryDirectory() as d:
   r=m.Runner(Path(d));r.d=[sys.executable,'-c',body];raw=None
   if error:
    with self.assertRaises(error):r.call(args or ['logs'],limit=limit,timeout=timeout)
   else:raw=r.call(args or ['logs'],limit=limit,timeout=timeout)
   rec=json.loads((Path(d)/'001-command.json').read_text());p=Path(d)/'001-combined-log.bin';saved=p.read_bytes() if p.exists() else None
   return raw,rec,saved
 def test_observed_lost_stderr(self):
  raw,rec,saved=self.run_case("import os;os.write(1,b'make leaving\\n');os.write(2,b'BUILD ERROR detail\\n')")
  self.assertIn(b'BUILD ERROR detail',raw);self.assertIn(b'make leaving',raw);self.assertEqual(saved,raw);self.assertEqual(rec['streams'],'stdout+stderr')
 def test_stderr_only(self):
  raw,rec,saved=self.run_case("import os;os.write(2,b'failure')")
  self.assertEqual(raw,b'failure');self.assertEqual(saved,raw)
 def test_combined_cap(self):
  _,rec,saved=self.run_case("import os;os.write(1,b'A'*8);os.write(2,b'B'*100000)",limit=16,error=ValueError)
  self.assertEqual(len(saved),16);self.assertEqual(rec['retained_bytes'],16);self.assertTrue(rec['truncated']);self.assertIn('output cap',rec['error'])
 def test_nonzero_keeps_diagnostic(self):
  _,rec,saved=self.run_case("import os;os.write(2,b'root cause');raise SystemExit(2)",error=RuntimeError)
  self.assertEqual(saved,b'root cause');self.assertEqual(rec['exit'],2)
 def test_timeout_keeps_prefix(self):
  _,rec,saved=self.run_case("import os,time;os.write(2,b'last detail');time.sleep(5)",timeout=.3,error=TimeoutError)
  self.assertEqual(saved,b'last detail');self.assertIn('timeout',rec['error'])
 def test_nonlogs_stdout_stays_parseable(self):
  raw,rec,saved=self.run_case("import os;os.write(1,b'[]');os.write(2,b'warning')",args=['inspect'])
  self.assertEqual(raw,b'[]');self.assertIsNone(saved);self.assertNotIn('streams',rec)
 def test_exact_boundary(self):
  raw,rec,saved=self.run_case("import os;os.write(2,b'1234')",limit=4)
  self.assertEqual(saved,b'1234');self.assertFalse(rec['truncated'])
 def test_binary_bytes_preserved_no_decode(self):
  raw,rec,saved=self.run_case("import os;os.write(2,bytes([255,0,27]))")
  self.assertEqual(saved,bytes([255,0,27]))
if __name__=='__main__':unittest.main()
