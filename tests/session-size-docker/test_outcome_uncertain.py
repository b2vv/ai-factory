"""Persist real synthetic state, then fail transport; never retry automatically."""
import json,os,shutil,subprocess,sys,time,unittest
from pathlib import Path
import test_store_contract as contract
class Outcome(unittest.TestCase):
 def exercise(self,fault,operation="checkpoint"):
  fixture=contract.StoreContract();fixture.setUp();self.addCleanup(fixture.tearDown)
  p=fixture.p;code=p/'code';shutil.copytree(contract.CODE,code)
  work=p/'work';work.mkdir(mode=0o700)
  pointer=None
  if operation in ('resume','hook'):
   summary=p/'summary.json';summary.write_bytes(fixture.summary)
   seed=subprocess.run([sys.executable,'-B',str(code/'entry.py'),'checkpoint','--root',str(p/'repo'),'--store',str(p/'selected'),'--store-leaf','state','--host','claude','--session','synthetic-source','--input',str(summary)],capture_output=True,env=fixture.env)
   self.assertEqual(seed.returncode,0);pointer=json.loads(seed.stdout)['result']['checkpoint_id']
  marker=p/'deadline';epoch=int(time.time())
  # Advance the dispatch clock only after validator mount verification. This
  # exercises run()'s actual expired-budget branch, without sleeps or live Docker.
  date=p/'bin/date';date.write_text('#!/bin/sh\nnow=$(/bin/date +%s)\nif [ -f "$DEADLINE_MARKER" ] && [ "$now" -lt '+str(epoch+7)+' ];then echo '+str(epoch+7)+';else echo "$now";fi\n');date.chmod(0o700)
  if fault=='cleanup':date.unlink()
  if fault=='delivery':
   cat=p/'bin/cat';cat.write_text('#!/bin/sh\ncase "$1" in */result.json) exit 1;; esac\nexec /bin/cat "$@"\n');cat.chmod(0o700)
  env=dict(fixture.env,POST_WORKER_FAULT=fault,DEADLINE_MARKER=str(marker),AF16_EVENT_STARTED=str(epoch))
  args=['sh',str(code/'dispatch.sh'),operation,'--root',str(p/'repo'),'--store',str(p/'selected'),'--store-leaf','state','--work',str(work),'--host','claude','--session','synthetic-target' if pointer else 'synthetic-source']
  if pointer:args+=['--pointer',pointer]
  payload=(json.dumps({'hook_event_name':'UserPromptSubmit','session_id':'synthetic-target','cwd':str(p/'repo')}).encode() if operation=='hook' else b'{}') if pointer else fixture.summary
  r=subprocess.run(args,input=payload,capture_output=True,env=env,timeout=15)
  records=[f for f in (p/'selected/state').glob('*.json') if len(f.stem.split('-')[0])==32]
  self.assertEqual(len(records),1);record=json.loads(records[0].read_text());self.assertTrue(record['complete'])
  self.assertEqual(bool(list((p/'selected/state').glob('claim-*'))),bool(pointer))
  self.assertEqual(json.loads((work/'cleanup-status.json').read_text())['status'],'UNRESOLVED' if fault=='cleanup' else 'REMOVED')
  if fault:
   self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'')
   self.assertIn(b'HANDOFF_OUTCOME_UNCERTAIN',r.stderr);self.assertIn(b'before retrying',r.stderr)
   for private in (b'PRIVATE_SENTINEL',b'Synthetic',record['id'].encode(),str(p).encode()):self.assertNotIn(private,r.stderr)
   failure=json.loads((work/'failure-status.json').read_text())
   self.assertEqual(failure,{'status':'FAILED','stage':{'deadline':'validator_environment','invalid':'validator_start','cleanup':'cleanup','delivery':'delivery'}[fault],'worker_started':1})
   self.assertEqual((work/'failure-status.json').stat().st_mode&0o777,0o600)
   if fault=='deadline':
    self.assertEqual((work/'env.raw').read_bytes(),b'');self.assertFalse((work/'validation.txt').exists())
    self.assertEqual((p/'fake.log').read_text().splitlines().count('start'),1)
  else:
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['result']['checkpoint_id'],record['id'])
   self.assertFalse((work/'failure-status.json').exists());self.assertNotIn(b'OUTCOME_UNCERTAIN',r.stderr)
 def test_optional_hook_failure_remains_advisory(self):
  fixture=contract.StoreContract();fixture.setUp();self.addCleanup(fixture.tearDown)
  p=fixture.p;work=p/'work';work.mkdir(mode=0o700)
  r=subprocess.run(['sh',str(contract.CODE/'dispatch.sh'),'hook','--root',str(p/'repo'),'--store',str(p/'selected'),'--work',str(work),'--host','claude','--session','source'],input=b'{}',capture_output=True,env=dict(fixture.env,FAULT='malformed'))
  self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'');self.assertIn(b'UNKNOWN optional monitoring',r.stderr);self.assertNotIn(b'OUTCOME_UNCERTAIN',r.stderr)
  self.assertEqual(json.loads((work/'failure-status.json').read_text())['stage'],'validator_start')
 def test_preworker_failure_does_not_claim_uncertain_persistence(self):
  fixture=contract.StoreContract();fixture.setUp();self.addCleanup(fixture.tearDown)
  p=fixture.p;work=p/'work';work.mkdir();(work/'existing').write_text('sentinel')
  r=subprocess.run(['sh',str(contract.CODE/'dispatch.sh'),'checkpoint','--root',str(p/'repo'),'--store',str(p/'selected'),'--work',str(work),'--host','claude','--session','source'],input=fixture.summary,capture_output=True,env=fixture.env)
  self.assertEqual(r.returncode,2);self.assertNotIn(b'OUTCOME_UNCERTAIN',r.stderr)
  self.assertFalse((work/'failure-status.json').exists());self.assertFalse(list((p/'selected/state').iterdir()))
 def test_start_attempt_uncertain_but_create_failure_is_not(self):
  for fault,uncertain in [('startfail',True),('createfail',False),('privatefailure',True)]:
   fixture=contract.StoreContract();fixture.setUp();self.addCleanup(fixture.tearDown)
   p=fixture.p;work=p/'work';work.mkdir(mode=0o700)
   r=subprocess.run(['sh',str(contract.CODE/'dispatch.sh'),'checkpoint','--root',str(p/'repo'),'--store',str(p/'selected'),'--store-leaf','state','--work',str(work),'--host','claude','--session','source'],input=fixture.summary,capture_output=True,env=dict(fixture.env,FAULT=fault))
   self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'');self.assertEqual(b'HANDOFF_OUTCOME_UNCERTAIN' in r.stderr,uncertain);self.assertNotIn(b'PRIVATE_SENTINEL',r.stderr)
 def test_deadline_after_persistence(self):
  self.exercise('deadline')
 def test_invalid_output_after_persistence(self):
  self.exercise('invalid')
 def test_cleanup_and_delivery_failures(self):
  for fault in ('cleanup','delivery'):
   with self.subTest(fault=fault):self.exercise(fault)
 def test_required_resume_and_native_hook_uncertain(self):
  for mode in ('resume','hook'):
   with self.subTest(mode=mode):self.exercise('deadline',mode)
 def test_success(self):
  self.exercise('')
if __name__=='__main__':unittest.main()
