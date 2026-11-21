"""Real Python guard and Git snapshots; Docker transport is synthetic."""
import json,os,shutil,subprocess,sys,tempfile,unittest,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CODE=ROOT/'runtime/session-size-docker'
class StoreContract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve()
  for n in ('home','bin','repo','selected','legacy','receipts','registry'):(self.p/n).mkdir(mode=0o700)
  (self.p/'selected/state').mkdir(mode=0o700)
  shutil.copyfile(ROOT/'tests/session-size-docker/fake_docker.py',self.p/'bin/docker');(self.p/'bin/docker').chmod(0o700)
  self.env=dict(os.environ,HOME=str(self.p/'home'),PATH=str(self.p/'bin')+':'+os.environ['PATH'],FAULT='execute',FAKE_STATE=str(self.p/'fake'),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',PYTHONDONTWRITEBYTECODE='1');self.env.pop('AI_FACTORY_HANDOFF',None)
  for args in (['init','-q'],['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','--allow-empty','-qm','fixture']):
   subprocess.run(['git',*args],cwd=self.p/'repo',env=self.env,check=True,capture_output=True)
  self.summary=json.dumps({k:'Synthetic '+k for k in ('goal','done','pending','evidence','constraints')}).encode()
 def tearDown(self):self.tmp.cleanup()
 def bind(self,host,sid):
  f=self.p/'registry'/hashlib.sha256((host+'\n'+sid+'\n').encode()).hexdigest()
  f.write_text('\n'.join(['AF16-MAPPING-2',host,sid,str(self.p/'repo'),str(self.p/'unused-transcript'),str(self.p/'selected'),'state'])+'\n');f.chmod(0o600)
 def manual(self,host,sid,mode='checkpoint',token=None,env=None):
  self.bind(host,sid);args=['sh',str(CODE/'manual.sh'),mode,host,str(self.p/'registry'),str(self.p/'receipts'),sid]
  if token:args.append(token)
  return subprocess.run(args,input=self.summary if mode=='checkpoint' else b'{}',capture_output=True,env=env or self.env)
 def hook(self,host,sid,token,event='UserPromptSubmit'):
  work=self.p/('event-'+sid+event);work.mkdir(mode=0o700)
  payload=json.dumps({'session_id':sid,'cwd':str(self.p/'repo'),'hook_event_name':event}).encode()
  return subprocess.run(['sh',str(CODE/'dispatch.sh'),'hook','--root',str(self.p/'repo'),'--store',str(self.p/'selected'),'--store-leaf','state','--work',str(work),'--host',host,'--session',sid],input=payload,capture_output=True,env=dict(self.env,AI_FACTORY_HANDOFF=token))
 def test_checkpoint_selected_store_then_fresh_native_resume_both_hosts(self):
  for host in ('claude','codex'):
   r=self.manual(host,host+'-source');self.assertEqual(r.returncode,0,r.stderr)
   token=json.loads(r.stdout)['result']['checkpoint_id'];self.assertTrue((self.p/'selected/state'/(token+'.json')).is_file())
   r=self.hook(host,host+'-target',token);self.assertEqual(r.returncode,0,r.stderr);self.assertIn(b'handoff READ',r.stdout)
   r=self.manual(host,host+'-target',env=dict(self.env,AI_FACTORY_HANDOFF=token));self.assertEqual(r.returncode,0,r.stderr)
 def test_legacy_token_is_not_imported_and_fixed_failure_is_delivered(self):
  r=subprocess.run([sys.executable,'-B',str(ROOT/'runtime/legacy/session-size/session_guard.py'),'checkpoint','--store',str(self.p/'legacy'),'--host','claude','--session','source','--cwd',str(self.p/'repo')],input=self.summary,capture_output=True,env=self.env)
  self.assertEqual(r.returncode,0,r.stderr);token=r.stdout.decode().strip()
  for event in ('SessionStart','UserPromptSubmit'):
   r=self.hook('claude','target',token,event);self.assertEqual(r.returncode,2)
   self.assertIn(b'STATE_UNAVAILABLE',r.stderr);self.assertNotIn(b'Synthetic',r.stderr);self.assertEqual(r.stdout,b'')
  self.assertFalse((self.p/'selected/state'/(token+'.json')).exists())
 def test_manual_resume_missing_exact_id_relays_fixed_diagnostic(self):
  r=self.manual('codex','target','resume','a'*32+'-1-'+'b'*12)
  self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'');self.assertIn(b'STATE_UNAVAILABLE: the exact state is missing or oversized.',r.stderr)
 def test_only_exact_fixed_diagnostic_shapes_are_relayed(self):
  message='AI Factory handoff BLOCKED: STATE_UNAVAILABLE: the exact state is missing or oversized.'
  valid=[json.dumps({'systemMessage':message}),json.dumps({'status':'BLOCKED','diagnostic':message})]
  invalid=[json.dumps({'systemMessage':message+' PRIVATE_SENTINEL'}),json.dumps({'systemMessage':message,'extra':'PRIVATE_SENTINEL'}),json.dumps({'status':'BLOCKED','diagnostic':message,'extra':'PRIVATE_SENTINEL'}),json.dumps({'systemMessage':'PRIVATE_SENTINEL '+message}),json.dumps({'systemMessage':message+'x'*5000})]
  for index,body in enumerate(valid+invalid):
   work=self.p/('relay-'+str(index));work.mkdir(mode=0o700)
   r=subprocess.run(['sh',str(CODE/'dispatch.sh'),'checkpoint','--root',str(self.p/'repo'),'--store',str(self.p/'selected'),'--store-leaf','state','--work',str(work),'--host','codex','--session','source'],input=self.summary,capture_output=True,env=dict(self.env,FAULT='fixedfailure',FAKE_ERROR=body))
   self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'');self.assertNotIn(b'PRIVATE_SENTINEL',r.stderr);self.assertEqual(message.encode() in r.stderr,index<2)
 def test_oversized_failure_is_not_loaded_for_relay(self):
  work=self.p/'bounded';work.mkdir(mode=0o700);marker=self.p/'read-attempt';cat=self.p/'bin/cat'
  cat.write_text('#!/bin/sh\ncase "$1" in */result.json) touch "$READ_ATTEMPT";exit 1;; esac\nexec /bin/cat "$@"\n');cat.chmod(0o700)
  r=subprocess.run(['sh',str(CODE/'dispatch.sh'),'checkpoint','--root',str(self.p/'repo'),'--store',str(self.p/'selected'),'--work',str(work),'--host','codex','--session','source'],input=self.summary,capture_output=True,env=dict(self.env,FAULT='fixedfailure',FAKE_ERROR='x'*5000,READ_ATTEMPT=str(marker)))
  self.assertEqual(r.returncode,2);self.assertFalse(marker.exists());self.assertEqual(r.stdout,b'')
 def test_incomplete_checkpoint_stays_blocked(self):
  r=self.manual('claude','source');token=json.loads(r.stdout)['result']['checkpoint_id']
  f=self.p/'selected/state'/(token+'.json');v=json.loads(f.read_text());v['complete']=False;f.write_text(json.dumps(v))
  r=self.hook('claude','target',token);self.assertEqual(r.returncode,2);self.assertIn(b'INCOMPLETE_CHECKPOINT',r.stderr)
if __name__=='__main__':unittest.main()
