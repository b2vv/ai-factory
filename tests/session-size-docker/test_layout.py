from pathlib import Path
import tempfile
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
TESTS = str(Path(__file__).resolve().parent)
import time,os,sys,subprocess,tempfile,shutil,unittest,json,contextlib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,(CODE + ''));sys.path.insert(0,(TESTS + ''))
import entry,guard
import test_native,test_candidate
class Layout(unittest.TestCase):
 def test_fast_success_cleanup(self):
  r=test_candidate.Lifecycle.run_case(self,'');self.assertEqual(r[0],0,r);self.assertLess(r[1],6,r)
 def test_v2_and_v1_semantics(self):
  n=test_native.Native();n.setUp()
  try:
   (n.p/'store'/'state').mkdir(mode=0o700)
   args=n.bind+['state'];r=subprocess.run(args,capture_output=True,env=n.env);self.assertEqual(r.returncode,0,r.stderr)
   key=r.stdout.decode().strip();record=n.p/'registry'/key;original=record.read_bytes();self.assertTrue(original.startswith(b'AF16-MAPPING-2\n'));self.assertTrue(original.endswith(b'\nstate\n'))
   code=n.p/'code';shutil.copytree((CODE + ''),code);(code/'dispatch.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
   cmd=['sh',str(code/'native-worker.sh'),'codex',str(n.p/'registry'),str(n.p/'receipts')];env=dict(n.env,AI_FACTORY_SESSION_BINDING=key)
   r=subprocess.run(cmd,input=json.dumps(n.payload).encode(),capture_output=True,env=dict(env,AF16_EVENT_STARTED=str(int(time.time()))));self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(r.stdout.endswith(b'--store-leaf\nstate\n'))
   for data in [original+b'EXTRA',original+b'\n',original[:-1],original.replace(b'\nstate\n',b'\n../escape\n'),original.replace(b'\nstate\n',b'\n\n')]:
    record.write_bytes(data);r=subprocess.run(cmd,input=json.dumps(n.payload).encode(),capture_output=True,env=dict(env,AF16_EVENT_STARTED=str(int(time.time()))));self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,b'')
  finally:n.tearDown()
 def test_missing_or_symlink_leaf_refused(self):
  n=test_native.Native();n.setUp()
  try:
   self.assertNotEqual(subprocess.run(n.bind+['state'],capture_output=True).returncode,0)
   (n.p/'store'/'state').symlink_to(n.p/'repo',target_is_directory=True)
   self.assertNotEqual(subprocess.run(n.bind+['state'],capture_output=True).returncode,0)
  finally:n.tearDown()
 def test_entry_passes_child_without_weakening_guard(self):
  with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as t:
   p=Path(t);root=p/'repo';store=p/'store';root.mkdir();store.mkdir();(store/'state').mkdir(mode=0o700)
   a=SimpleNamespace(root=str(root),store=str(store),mode='hook',host='codex',session='s',transcript=None,pointer='',store_leaf='state')
   payload={'hook_event_name':'SessionStart','cwd':str(root),'session_id':'s'}
   with patch.object(guard,'git',return_value=str(root).encode()),patch.object(guard,'event',return_value={}) as event:
    self.assertEqual(entry.execute(a,json.dumps(payload).encode()),{});self.assertEqual(event.call_args.args[0],store/'state')
   with guard.locked(store/'state'):pass
   self.assertTrue((store/'state'/'.lock').is_file());self.assertFalse((store/'.lock').exists())
   with patch.object(guard.os,'getuid',return_value=99999):self.assertRaises(ValueError,lambda:guard.locked(store/'state').__enter__())
if __name__=='__main__':unittest.main(verbosity=2)
