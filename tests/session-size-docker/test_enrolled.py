from pathlib import Path
import tempfile
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
TESTS = str(Path(__file__).resolve().parent)
import os,sys,json,shutil,subprocess,time,unittest,importlib.util
from pathlib import Path
sys.path.insert(0,(TESTS + ''))
import test_native
spec=importlib.util.spec_from_file_location('session_key',(CODE + '/session-key.py'))
parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)

FAKE='''#!/usr/bin/env python3
import os,sys,json,subprocess
from pathlib import Path
p=Path(os.environ['FAKE_STATE']);a=sys.argv[1:];op=a[0]
with open(str(p)+'.calls','a') as f:f.write(op+'\\n')
if op=='create':
 p.write_text(json.dumps(a));print('c'*64)
elif op=='ps':
 if not p.exists():sys.exit(0)
 c=json.loads(p.read_text());owner=next(x.split('=',1)[1] for x in c if x.startswith('ai-factory.invocation='));print('c'*64+'|'+owner+'|'+owner)
elif op=='inspect':
 if 'ai-factory.invocation' in a[2]:
  c=json.loads(p.read_text());print('c'*64+'|/'+a[-1]+'|'+next(x.split('=',1)[1] for x in c if x.startswith('ai-factory.invocation=')))
 elif '.State.ExitCode' in a[2]:print('exited|0|false|false')
 else:
  c=json.loads(p.read_text());image=c[c.index('--entrypoint')+2];uid=c[c.index('--user')+1]
  print('created|'+image+'|'+uid+'|none|true|false|2000000000|2147483648|2147483648|128|["ALL"]|["no-new-privileges"]|rw,noexec,nosuid,nodev,size=16777216|python3|'+('1' if os.environ.get('BAD_POLICY') else '0')+'|0|0|0|0||private|none')
elif op=='start':
 if os.environ.get('BAD_OUTPUT'):print('not-a-key');sys.exit(0)
 c=json.loads(p.read_text());i=c.index('-c');r=subprocess.run([sys.executable,'-c',c[i+1],c[i+2]],input=sys.stdin.buffer.read(),capture_output=True);sys.stdout.buffer.write(r.stdout);sys.exit(r.returncode)
elif op=='rm':
 if os.environ.get('BAD_CLEANUP'):sys.exit(1)
 p.unlink(missing_ok=True);print('c'*64)
else:sys.exit(2)
'''

class Enrolled(unittest.TestCase):
 def setUp(self):
  self.n=test_native.Native();self.n.setUp();self.n.provision();self.p=self.n.p
  self.code=self.p/'code';shutil.copytree((CODE + ''),self.code)
  (self.code/'dispatch.sh').write_text('#!/bin/sh\nprintf "DISPATCH\\n"\nprintf "%s\\n" "$@"\ncat\n')
  fake=self.p/'bin'/'docker';fake.write_text(FAKE);fake.chmod(0o700)
  self.env=dict(self.n.env,PATH=str(self.p/'bin')+':'+os.environ['PATH'],FAKE_STATE=str(self.p/'docker-state'))
  self.payload={'hook_event_name':'SessionStart','session_id':'session-1','cwd':str(self.p/'repo'),'transcript_path':str(self.n.transcript)}
 def tearDown(self):self.n.tearDown()
 def call(self,payload=None,**env):
  raw=json.dumps(self.payload if payload is None else payload).encode()
  return subprocess.run(['sh',str(self.code/'native.sh'),'codex',str(self.p/'registry'),str(self.p/'receipts')],input=raw,capture_output=True,env=dict(self.env,**env),timeout=11)
 def test_enrolled_without_environment(self):
  r=self.call();self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(r.stdout.startswith(b'DISPATCH\n'),r)
  self.assertEqual(json.loads(r.stdout.split(b'\n')[-2]),self.payload);self.assertIn(str(self.p/'repo').encode(),r.stdout)
  self.assertFalse((self.p/'docker-state').exists())
 def test_private_extras_never_persist(self):
  p=dict(self.payload,prompt='PRIVATE_SENTINEL',tool_response={'secret':'PRIVATE_SENTINEL'})
  for sid in ['session-1','unknown']:
   p['session_id']=sid;r=self.call(p)
   self.assertNotIn(b'PRIVATE_SENTINEL',r.stdout+r.stderr)
   for f in (self.p/'receipts').rglob('*'):
    if f.is_file():self.assertNotIn(b'PRIVATE_SENTINEL',f.read_bytes())
   if sid=='unknown':
    latest=max((self.p/'receipts').glob('selection.*'),key=lambda f:f.stat().st_mtime_ns)
    self.assertFalse((latest/'payload.json').exists());self.assertFalse((latest/'projected').exists());self.assertFalse((latest/'key.txt').exists())
 def test_unbound_never_enrolls_or_dispatches(self):
  before={p.name:p.read_bytes() for p in (self.p/'registry').iterdir()}
  p=dict(self.payload,session_id='unknown',cwd='/secret',transcript_path='/secret')
  for pointer,rc in [('',0),('explicit',2)]:
   r=self.call(p,AI_FACTORY_HANDOFF=pointer);self.assertEqual(r.returncode,rc);self.assertEqual(r.stdout,b'');self.assertIn(b'UNBOUND_OR_INVALID',r.stderr)
  self.assertEqual(before,{p.name:p.read_bytes() for p in (self.p/'registry').iterdir()})
 def test_duplicate_and_bad_session(self):
  for p in [None,[],dict(self.payload,session_id=[]),dict(self.payload,session_id='bad\n'),dict(self.payload,session_id='x'*257)]:
   raw=json.dumps(p).encode()
   with self.assertRaises(ValueError):parser.select('codex',raw)
  with self.assertRaises(ValueError):parser.select('codex',b'{"session_id":"a","session_id":"b"}')
 def test_paths_not_part_of_selection_authority(self):
  p=dict(self.payload,cwd='/arbitrary',transcript_path='/secret')
  self.assertEqual(parser.select('codex',json.dumps(p).encode()),self.n.key)
  r=self.call(p);args=r.stdout.split(b'\n{')[0]
  self.assertNotIn(b'/arbitrary',args);self.assertNotIn(b'/secret',args)
  # Real entry.py still rejects mismatched paths: retained test_native covers it.
 def test_policy_output_cleanup_fail_closed(self):
  for env in ['BAD_POLICY','BAD_OUTPUT','BAD_CLEANUP']:
   r=self.call(**{env:'1','AI_FACTORY_HANDOFF':'explicit'});self.assertEqual(r.returncode,2,r);self.assertEqual(r.stdout,b'')
   if env=='BAD_POLICY':
    calls=Path(str(self.p/'docker-state')+'.calls').read_text();self.assertNotIn('start',calls)
   Path(str(self.p/'docker-state')+'.calls').unlink(missing_ok=True)
 def test_existing_explicit_binding_compatibility(self):
  r=self.call(AI_FACTORY_SESSION_BINDING=self.n.key);self.assertTrue(r.stdout.startswith(b'DISPATCH\n'))
  self.assertIn('start',Path(str(self.p/'docker-state')+'.calls').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
