import ast,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bounded_command
s=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('launcher.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def watchdog_call(out):
 tree=ast.parse(Path(__file__).with_name('watchdog.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='call')
 ns={'subprocess':subprocess,'json':json,'out':out,'d':['docker','--config','x'*3000,'--host','endpoint'],'command_errors':0,'bounded_command':bounded_command,'time':__import__('time'),'phase':'online','save_diag':lambda name,record:(out/name).write_text(json.dumps(record))}
 exec(compile(ast.Module(body=[node],type_ignores=[]),'authored-watchdog-call','exec'),ns);return ns['call']
class WatchdogDiagnostics(unittest.TestCase):
 def test_exit_subcommand_stderr(self):
  with tempfile.TemporaryDirectory() as d:
   f=watchdog_call(Path(d));err=subprocess.CalledProcessError(17,['ignored'],output='out',stderr='specific failure')
   with patch('bounded_command.run',side_effect=err):
    with self.assertRaises(subprocess.CalledProcessError):f(['exec','a'*64,'du','-sk','/work','/capture'])
   r=json.loads((Path(d)/'command-error-01.json').read_text());self.assertEqual(r['returncode'],17);self.assertEqual(r['subcommand'][-2:],['/work','/capture']);self.assertEqual(r['stderr']['text'],'specific failure')
 def test_timeout_partial_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   f=watchdog_call(Path(d))
   with patch('bounded_command.run',side_effect=subprocess.TimeoutExpired('x',3,output=b'prefix',stderr=b'\xfferror')):
    with self.assertRaises(subprocess.TimeoutExpired):f(['inspect','cid'])
   r=json.loads((Path(d)/'last-command-error.json').read_text());self.assertEqual(r['timeout_seconds'],3);self.assertIn('error',r['stderr']['text'])
 def test_bounded_records_and_streams(self):
  with tempfile.TemporaryDirectory() as d:
   f=watchdog_call(Path(d))
   with patch('bounded_command.run',side_effect=subprocess.CalledProcessError(1,[],output='O'*50000,stderr='E'*100000)):
    for _ in range(35):
     with self.assertRaises(subprocess.CalledProcessError):f(['stop','cid'])
   files=list(Path(d).glob('*.json'));self.assertEqual(len(files),33)
   r=json.loads((Path(d)/'last-command-error.json').read_text());self.assertEqual(r['sequence'],35);self.assertEqual(r['stderr']['bytes_retained'],8192);self.assertTrue(r['stderr']['truncated']);self.assertTrue(all(p.stat().st_size<=65536 for p in files))
 def test_spawn_failure_recorded(self):
  with tempfile.TemporaryDirectory() as d:
   f=watchdog_call(Path(d))
   with patch('bounded_command.run',side_effect=OSError('missing executable')):
    with self.assertRaises(OSError):f(['inspect','cid'])
   self.assertEqual(json.loads((Path(d)/'last-command-error.json').read_text())['error_type'],'OSError')
class LauncherDiagnostics(unittest.TestCase):
 def case(self,body,error=None,timeout=3):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);r=m.Runner(root);r.d=[sys.executable,'-c',body];out=None
   if error:
    with self.assertRaises(error):r.call(['inspect'],timeout=timeout)
   else:out=r.call(['inspect'],timeout=timeout)
   rec=json.loads((root/'001-command.json').read_text());return out,rec,(root/'001-stderr.bin').read_bytes()
 def test_nonlog_failure_detail(self):
  _,r,e=self.case("import os;os.write(2,b'actual daemon detail');raise SystemExit(7)",RuntimeError)
  self.assertEqual(r['exit'],7);self.assertEqual(e,b'actual daemon detail')
 def test_stdout_unchanged(self):
  out,r,e=self.case("import os;os.write(1,b'[]');os.write(2,b'warning')")
  self.assertEqual(out,b'[]');self.assertEqual(e,b'warning')
 def test_stderr_overflow(self):
  _,r,e=self.case("import os;os.write(2,b'x'*100000)",ValueError)
  self.assertEqual(len(e),32768);self.assertTrue(r['stderr_truncated'])
 def test_timeout_partial(self):
  _,r,e=self.case("import os,time;os.write(2,b'before hang');time.sleep(5)",TimeoutError,.3)
  self.assertEqual(e,b'before hang');self.assertIn('timeout',r['error'])
 def test_malformed_json_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   r=m.Runner(Path(d));r.d=[sys.executable,'-c',"print('not json')"]
   with self.assertRaises(json.JSONDecodeError):r.obj(['inspect'])
   self.assertEqual(json.loads((Path(d)/'001-protocol-error.json').read_text())['subcommand'],['inspect'])
 def test_write_failure_preserves_primary(self):
  with tempfile.TemporaryDirectory() as d:
   r=m.Runner(Path(d));r.d=[sys.executable,'-c',"raise SystemExit(7)"]
   with patch.object(Path,'write_bytes',side_effect=OSError('disk full')):
    with self.assertRaisesRegex(RuntimeError,'Docker command exit 7'):r.call(['inspect'])
   self.assertTrue(r.diagnostic_errors)
 def test_spawn_error_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   r=m.Runner(Path(d))
   with patch.object(m.subprocess,'Popen',side_effect=OSError('missing docker')):
    with self.assertRaises(OSError):r.call(['create','--name','owned'])
   rec=json.loads((Path(d)/'001-command.json').read_text());self.assertIn('missing docker',rec['error']);self.assertTrue(rec['uncertain_mutation']);self.assertIsNone(rec['exit'])
if __name__=='__main__':unittest.main()
