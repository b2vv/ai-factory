from pathlib import Path
import tempfile
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
TESTS = str(Path(__file__).resolve().parent)
import os,sys,json,tempfile,shutil,subprocess,time,unittest,io,contextlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,(CODE + ''));import entry,guard
class Native(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=tempfile.gettempdir());self.p=Path(self.tmp.name)
  for name in ['registry','receipts','store','repo','bin']:(self.p/name).mkdir(mode=0o700)
  self.transcript=self.p/'transcript.jsonl';self.transcript.write_text('synthetic\n')
  self.roots=self.p/'roots';self.roots.write_text(str(self.p/'repo')+'\n');self.roots.chmod(0o600)
  self.bind=['sh',(CODE + '/bind-session.sh'),str(self.p/'registry'),str(self.roots),'codex','session-1',str(self.p/'repo'),str(self.transcript),str(self.p/'store')]
  self.payload={'hook_event_name':'SessionStart','session_id':'session-1','cwd':str(self.p/'repo'),'transcript_path':str(self.transcript)}
  shutil.copy((TESTS + '/fake_selector.py'),self.p/'bin'/'docker');(self.p/'bin'/'docker').chmod(0o700)
  self.env=dict(os.environ,PATH=str(self.p/'bin')+':'+os.environ['PATH'],FAKE_STATE=str(self.p/'native-docker-state'));self.env.pop('AI_FACTORY_HANDOFF',None);self.env.pop('AI_FACTORY_SESSION_BINDING',None)
 def tearDown(self):self.tmp.cleanup()
 def provision(self):
  r=subprocess.run(self.bind,capture_output=True,env=self.env);self.assertEqual(r.returncode,0,r.stderr);self.key=r.stdout.decode().strip();return self.key
 def test_provision_no_replace(self):
  self.provision();record=self.p/'registry'/self.key;before=record.read_bytes();self.assertEqual(record.stat().st_mode&0o777,0o600)
  self.assertNotEqual(subprocess.run(self.bind,capture_output=True,env=self.env).returncode,0);self.assertEqual(record.read_bytes(),before)
 def test_exact_binding_framing(self):
  self.provision();record=self.p/'registry'/self.key;original=record.read_bytes()
  code=self.p/'code';shutil.copytree((CODE + ''),code)
  (code/'dispatch.sh').write_text('#!/bin/sh\necho DISPATCH_REACHED\n')
  cmd=['sh',str(code/'native-worker.sh'),'codex',str(self.p/'registry'),str(self.p/'receipts')]
  env=dict(self.env,AI_FACTORY_SESSION_BINDING=self.key)
  good=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(env,AF16_EVENT_STARTED=str(int(time.time()))));self.assertEqual(good.returncode,0);self.assertIn(b'DISPATCH_REACHED',good.stdout)
  cases=[original+b'EXTRA\n',original+b'UNTERMINATED-EXTRA',original+b'\n',original[:-1],b'\n'.join(original.splitlines()[:5])+b'\n',b'']
  for data in cases:
   with self.subTest(data=data[-40:]):
    record.write_bytes(data)
    r=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(env,AF16_EVENT_STARTED=str(int(time.time()))))
    self.assertNotEqual(r.returncode,0);self.assertNotIn(b'DISPATCH_REACHED',r.stdout)
  # Demonstrate the original EOF bug with all other guards unchanged.
  old=(code/'native-worker.sh').read_text().replace('extra=;if IFS= read -r extra;then exit 2;fi;[ -z "$extra" ];','! IFS= read -r extra;')
  (code/'native-worker.sh').write_text(old);record.write_bytes(original+b'UNTERMINATED-EXTRA')
  r=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(env,AF16_EVENT_STARTED=str(int(time.time()))));self.assertEqual(r.returncode,0);self.assertIn(b'DISPATCH_REACHED',r.stdout)
 def test_unapproved_root(self):
  other=self.p/'other';other.mkdir();args=self.bind.copy();args[-3]=str(other)
  self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0);self.assertEqual(list((self.p/'registry').iterdir()),[])
 def test_missing_mapping_required_and_optional(self):
  cmd=['sh',(CODE + '/native.sh'),'codex',str(self.p/'registry'),str(self.p/'receipts')]
  for pointer,expected in [('',0),('explicit',2)]:
   r=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(self.env,AI_FACTORY_HANDOFF=pointer));self.assertEqual(r.returncode,expected);self.assertEqual(r.stdout,b'')
 def test_mapping_is_data_no_eval(self):
  self.provision();code=self.p/'code';shutil.copytree((CODE + ''),code)
  (code/'dispatch.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$@"\ncat >/dev/null\n')
  cmd=['sh',str(code/'native.sh'),'codex',str(self.p/'registry'),str(self.p/'receipts')]
  r=subprocess.run(cmd,input=json.dumps(dict(self.payload,cwd='/arbitrary',transcript_path='/secret')).encode(),capture_output=True,env=dict(self.env,AI_FACTORY_SESSION_BINDING=self.key))
  self.assertEqual(r.returncode,0,r.stderr);self.assertIn(str(self.p/'repo').encode(),r.stdout);self.assertNotIn(b'/secret',r.stdout);self.assertNotIn(b'/arbitrary',r.stdout)
 def test_bad_binding_paths_and_host(self):
  self.provision();cmd=['sh',(CODE + '/native.sh'),'claude',str(self.p/'registry'),str(self.p/'receipts')]
  for key in [self.key,'../escape','x'*64,'a'*63]:
   r=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(self.env,AI_FACTORY_SESSION_BINDING=key,AI_FACTORY_HANDOFF='explicit'));self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'')
 def test_insecure_or_linked_record(self):
  self.provision();record=self.p/'registry'/self.key;cmd=['sh',(CODE + '/native.sh'),'codex',str(self.p/'registry'),str(self.p/'receipts')]
  for fault in ['mode','link']:
   if fault=='mode':record.chmod(0o644)
   else:record.chmod(0o600);os.link(record,self.p/'second-link')
   r=subprocess.run(cmd,input=json.dumps(self.payload).encode(),capture_output=True,env=dict(self.env,AI_FACTORY_SESSION_BINDING=self.key,AI_FACTORY_HANDOFF='explicit'));self.assertEqual(r.returncode,2)
 def test_mapping_deadline_no_reset(self):
  code=self.p/'code';shutil.copytree((CODE + ''),code);(code/'native-worker.sh').write_text('#!/bin/sh\nexec sleep 30\n')
  t=time.monotonic();r=subprocess.run(['sh',str(code/'native.sh'),'codex','x','y'],capture_output=True,env=dict(self.env,AI_FACTORY_HANDOFF='explicit'),timeout=11)
  self.assertEqual(r.returncode,2);self.assertLess(time.monotonic()-t,10)
 def test_payload_session_and_transcript(self):
  self.provision();input=self.p/'input';argv=['entry.py','hook','--root',str(self.p/'repo'),'--store',str(self.p/'store'),'--host','codex','--session','session-1','--transcript',str(self.transcript),'--input',str(input),'--pointer','explicit']
  base={'hook_event_name':'SessionStart','session_id':'session-1','cwd':str(self.p/'repo'),'transcript_path':str(self.transcript)}
  for field,value in [('session_id','other'),('transcript_path','/secret'),('cwd','/other')]:
   payload=dict(base);payload[field]=value;input.write_text(json.dumps(payload))
   with patch.object(sys,'argv',argv),patch.object(guard,'git',return_value=str(self.p/'repo').encode()),patch.object(guard,'event_locked') as event,contextlib.redirect_stdout(io.StringIO()):self.assertEqual(entry.main(),2);event.assert_not_called()
 def test_expired_dispatch_clock(self):
  r=subprocess.run(['sh',(CODE + '/dispatch.sh'),'resume'],input=json.dumps(self.payload).encode(),capture_output=True,env=dict(self.env,AF16_EVENT_STARTED='1'));self.assertNotEqual(r.returncode,0)
if __name__=='__main__':unittest.main(verbosity=2)
