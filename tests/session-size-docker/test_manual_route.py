"""Trusted registry manual routing, without a Docker daemon."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
CODE=Path(__file__).resolve().parents[2]/'runtime/session-size-docker'
class ManualRoute(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve()
  for n in ('code','registry','receipts','repo','store'):(self.p/n).mkdir(mode=0o700)
  (self.p/'store/state').mkdir(mode=0o700)
  shutil.copytree(CODE,self.p/'code',dirs_exist_ok=True)
  (self.p/'code/dispatch.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$@"\ncat\n')
  self.env=dict(os.environ);self.env.pop('AI_FACTORY_HANDOFF',None)
 def tearDown(self):self.tmp.cleanup()
 def bind(self,host='claude',sid='source'):
  import hashlib
  key=hashlib.sha256((host+'\n'+sid+'\n').encode()).hexdigest()
  f=self.p/'registry'/key
  f.write_text('\n'.join(['AF16-MAPPING-2',host,sid,str(self.p/'repo'),str(self.p/'transcript'),str(self.p/'store'),'state'])+'\n');f.chmod(0o600)
  return f
 def call(self,mode='checkpoint',host='claude',sid='source',pointer=None,env=None):
  cmd=['sh',str(self.p/'code/manual.sh'),mode,host,str(self.p/'registry'),str(self.p/'receipts'),sid]
  if pointer is not None:cmd.append(pointer)
  return subprocess.run(cmd,input=b'{"goal":"synthetic"}',capture_output=True,env=env or self.env)
 def test_selected_mapping_both_hosts_and_inherited_pointer(self):
  for host in ('claude','codex'):
   self.bind(host)
   r=self.call(host=host,env=dict(self.env,AI_FACTORY_HANDOFF='inherited-source-pointer'))
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn(str(self.p/'store').encode(),r.stdout)
   self.assertIn(b'--store-leaf\nstate',r.stdout);self.assertTrue(r.stdout.endswith(b'{"goal":"synthetic"}'))
 def test_missing_mapping_and_wrong_host_fail_before_dispatch(self):
  self.bind();r=self.call(host='codex');self.assertNotEqual(r.returncode,0);self.assertNotIn(b'--store',r.stdout)
 def test_extra_mapping_fields_and_symlink_rejected(self):
  f=self.bind();f.write_text(f.read_text()+'extra\n');self.assertNotEqual(self.call().returncode,0)
  f.unlink();f.symlink_to(self.p/'repo');self.assertNotEqual(self.call().returncode,0)
 def test_resume_requires_explicit_id(self):
  self.bind();self.assertNotEqual(self.call(mode='resume').returncode,0)
  r=self.call(mode='resume',pointer='a'*32+'-1-'+'b'*12);self.assertEqual(r.returncode,0);self.assertIn(b'--pointer',r.stdout)
 def test_version_one_without_leaf_and_wrong_identity_rejected(self):
  f=self.bind();data=f.read_text().replace('AF16-MAPPING-2','AF16-MAPPING-1').rsplit('state\n',1)[0];f.write_text(data)
  r=self.call();self.assertEqual(r.returncode,0);self.assertNotIn(b'--store-leaf',r.stdout)
  f.write_text(data.replace('\nsource\n','\nother\n'));self.assertNotEqual(self.call().returncode,0)
 def test_unknown_mode_missing_resume_id_and_private_store_checks(self):
  self.bind()
  for mode in ('unexpected','resume'):
   self.assertNotEqual(self.call(mode=mode).returncode,0)
  (self.p/'store').chmod(0o755);self.assertNotEqual(self.call().returncode,0)
 def test_mapping_bounds_private_mode_and_leaf_are_enforced(self):
  f=self.bind();original=f.read_text()
  cases=[original.replace('AF16-MAPPING-2','UNKNOWN').rsplit('state\n',1)[0],original.replace(str(self.p/'transcript'),'x'*9000),original+'x'*8193,original.replace('AF16-MAPPING-2','UNKNOWN'),original.replace('state\n','unknown\n'),original.replace('\nclaude\n','\ncodex\n'),original+'unterminated']
  for data in cases:
   f.write_text(data);self.assertNotEqual(self.call().returncode,0)
  f.write_text(original);f.chmod(0o644);self.assertNotEqual(self.call().returncode,0)
  f.chmod(0o600);(self.p/'store/state').rmdir();self.assertNotEqual(self.call().returncode,0)
 def test_mode_arity_host_and_empty_pointer_are_rejected(self):
  self.bind();self.bind('unknown');self.bind(sid='s'*257)
  for kwargs in ({'mode':'unexpected'},{'host':'unknown'},{'sid':'s'*257},{'pointer':'extra'},{'mode':'resume','pointer':''}):
   r=self.call(**kwargs);self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,b'')
 def test_registry_receipts_and_root_checks(self):
  f=self.bind()
  for directory in ('registry','receipts'):
   (self.p/directory).chmod(0o755);self.assertNotEqual(self.call().returncode,0);(self.p/directory).chmod(0o700)
  link=self.p/'root-link';link.symlink_to(self.p/'repo',target_is_directory=True)
  f.write_text(f.read_text().replace(str(self.p/'repo'),str(link)));self.assertNotEqual(self.call().returncode,0)
 def test_symlink_to_valid_mapping_is_refused(self):
  f=self.bind();saved=self.p/'saved-record';f.rename(saved);f.symlink_to(saved)
  self.assertNotEqual(self.call().returncode,0)
if __name__=='__main__':unittest.main()
