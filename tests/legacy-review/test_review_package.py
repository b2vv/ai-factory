import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('review_package',Path(__file__).resolve().parents[2]/'runtime/legacy/review/review_package.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class PackageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve()/'repo';self.root.mkdir();self.out=Path(self.tmp.name).resolve()/'packages'
  self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
  (self.root/'a.py').write_text('before = 1\n');self.git('add','a.py');self.git('commit','-qm','fixture')
  self.ac=Path(self.tmp.name).resolve()/'acceptance.md';self.ac.write_text('Change before to after; preserve invariant\n')
  self.m={'root':str(self.root),'base':'HEAD','task_id':'T1','author_session':'writer1','scope':['a.py'],
          'acceptance':[str(self.ac)],'contracts':[],'required_checks':['targeted'],
          'routes':[{'purpose':'review','mode':'subagent','owner':'operator','authorization':'current user selection'}],
          'constraints':['Read only; no shared stand access']}
  (self.root/'a.py').write_text('after = 2\n')
 def git(self,*a):
  return subprocess.check_output(['git','-C',str(self.root),*a],stderr=subprocess.DEVNULL)
 def package(self):return g.capture(self.m,self.out)[0]
 def response(self,p):
  return {'package_id':g.load(p)['id'],'reviewer_reference':'reviewer1','completion':'complete','inspected':list(self.m['scope']),
          'findings':[],'verdict':'PASS','checks':[{'name':'targeted','status':'PASS','evidence':'fixture log; exit 0','command':'fixture check','exit_code':0}]}
 def test_subagent_route(self):self.assertEqual('SELECTED',g.routes(self.m)[0]['status'])
 def test_existing_named_session(self):
  self.m['routes'][0].update(mode='existing-session',reference='Cargo1:exact-id')
  p=self.package();r=self.response(p);self.assertEqual('BLOCKED',g.assess(p,r)['status'])
  r['reviewer_reference']='Cargo1:exact-id';self.assertEqual('PASS',g.assess(p,r)['status'])
 def test_unspecified_and_unnamed_routes_block(self):
  for route in [[],[{'purpose':'review','mode':'unspecified'}],[{'purpose':'review','mode':'existing-session','owner':'me','authorization':'yes'}]]:
   self.m['routes']=route;p=self.package();self.assertEqual('BLOCKED',g.assess(p,self.response(p))['status'])
 def test_missing_response(self):self.assertEqual('NOT_TESTED',g.assess(self.package())['review'])
 def test_snapshot_copy_and_exact_diff(self):
  p=self.package();d=g.load(p)['data'];text=(p/'objects'/d['diff']).read_text()
  self.assertIn('-before = 1',text);self.assertIn('+after = 2',text)
  self.assertEqual(self.ac.read_bytes(),(p/'objects'/d['references']['acceptance'][0]['sha256']).read_bytes())
 def test_same_handoff_noop(self):
  p=self.package();p2,status=g.capture(self.m,self.out);self.assertEqual(p,p2);self.assertEqual('NOOP',status)
 def test_concurrent_edit_no_publication(self):
  original=g.collect;count=0
  def change(m):
   nonlocal count
   result=original(m);count+=1
   if count==1:(self.root/'a.py').write_text('raced = 3\n')
   return result
  with patch.object(g,'collect',side_effect=change):
   with self.assertRaises(ValueError):self.package()
  self.assertFalse(self.out.exists())
 def test_untracked_changed_stales(self):
  (self.root/'new.py').write_text('new = 1\n');self.m['scope'].append('new.py');p=self.package()
  self.assertIn('??',g.load(p)['data']['scope']['new.py']['status'])
  (self.root/'new.py').write_text('new = 2\n');self.assertEqual('BLOCKED',g.assess(p,self.response(p))['status'])
 def test_dirty_change_same_size_stales(self):
  p=self.package();(self.root/'a.py').write_text('after = 3\n');self.assertFalse(g.fresh(g.load(p)))
 def test_acceptance_change_stales(self):
  p=self.package();self.ac.write_text('different contract');self.assertFalse(g.fresh(g.load(p)))
 def test_final_delta(self):
  old=self.package();(self.root/'a.py').write_text('after = 4\n');new=self.package()
  d=g.delta(old,new);self.assertEqual(['a.py'],d['changed_files']);self.assertEqual('FINAL_DELTA_REVIEW_REQUIRED',d['action'])
  self.assertEqual('BLOCKED',g.assess(new,self.response(old))['status'])
  self.assertEqual('NOOP',g.delta(new,new)['action'])
 def test_irrelevant_unscoped_change_keeps_proof(self):
  p=self.package();(self.root/'unrelated.md').write_text('outside agreed scope')
  self.assertEqual('PASS',g.assess(p,self.response(p))['status'])
 def test_missing_check_self_review_incomplete(self):
  p=self.package()
  for change in [{'checks':[]},{'reviewer_reference':'writer1'},{'inspected':[]},{'completion':'pending'}]:
   r=self.response(p);r.update(change);self.assertEqual('BLOCKED',g.assess(p,r)['status'])
 def test_finding_shape_and_blocking(self):
  p=self.package();r=self.response(p);r['findings']=[{'file':'a.py'}];self.assertEqual('BLOCKED',g.assess(p,r)['status'])
  r['findings']=[{'file':'a.py','line':1,'impact':'wrong behavior','verification':'reproduce X','blocking':True}]
  self.assertEqual('BLOCKED',g.assess(p,r)['status']);r['verdict']='FAIL';self.assertEqual('FAIL',g.assess(p,r)['status'])
 def test_tampered_copy_refused(self):
  p=self.package();d=g.load(p)['data'];(p/'objects'/d['diff']).write_text('tampered')
  with self.assertRaises(ValueError):g.load(p)
 def test_secret_symlink_traversal_refused(self):
  for rel in ['.env','../outside','/tmp/file']:
   self.m['scope']=[rel]
   with self.assertRaises(ValueError):self.package()
  (self.root/'link.py').symlink_to(self.root/'a.py');self.m['scope']=['link.py']
  with self.assertRaises(ValueError):self.package()
 def test_no_automatic_commands(self):
  self.m['evidence']=[{'name':'targeted','command':'never execute this command','exit_code':None,'status':'NOT_TESTED','limitation':'not authorized'}]
  p=self.package();self.assertEqual('NOT_TESTED',g.load(p)['data']['evidence'][0]['status'])
 def test_index_change_same_worktree_stales(self):
  self.git('add','a.py');(self.root/'a.py').write_text('working = 7\n');p=self.package()
  (self.root/'a.py').write_text('staged = 8\n');self.git('add','a.py');(self.root/'a.py').write_text('working = 7\n')
  self.assertFalse(g.fresh(g.load(p)))
 def test_no_final_newline_diff(self):
  (self.root/'a.py').write_text('after = 2');p=self.package();d=g.load(p)['data']
  self.assertIn('No newline at end of file',(p/'objects'/d['diff']).read_text())
 def test_mode_change_stales(self):
  p=self.package();(self.root/'a.py').chmod(0o755);self.assertFalse(g.fresh(g.load(p)))
 def test_pass_evidence_needs_artifact_and_exit(self):
  self.m['evidence']=[{'name':'x','command':'false','exit_code':1,'status':'PASS'}]
  with self.assertRaises(ValueError):self.package()

if __name__=='__main__':unittest.main(verbosity=2)
