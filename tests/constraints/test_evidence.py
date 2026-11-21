import copy,importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('evidence_check',ROOT/'runtime/constraints/evidence_check.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def valid():
 s={'root':'fixture','base':'base1','head':'head1','scope':['a.py','new.py','old.py'],'files':{'a.py':{'state':'tracked','sha256':'a'*64},'new.py':{'state':'untracked','sha256':'b'*64},'old.py':{'state':'deleted','sha256':None}}}
 return {'current':s,'evidence_snapshot':copy.deepcopy(s),'task':'B','checkpoint_task':'B','graph':'not_used','review_required':True,'review_status':'PASS','review_snapshot':copy.deepcopy(s),'review_evidence':['review.json'],'floor_evidence':['diff-and-check-results.txt'],'signals':[],'required_ui':[],'ui_evidence':{}}

class EvidenceTests(unittest.TestCase):
 def check(self,r,status): self.assertEqual(mod.assess(r)['status'],status,mod.assess(r))
 def test_complete_declared_record(self): self.check(valid(),'PASS')
 def test_second_task(self):
  r=valid();r['checkpoint_task']='A';self.check(r,'BLOCKED')
 def test_stale_graph(self):
  r=valid();r['graph']='stale';self.check(r,'BLOCKED');r['file_fallback_evidence']=['caller-inspection.txt'];self.check(r,'PASS')
 def test_head_drift(self):
  r=valid();r['current']['head']='head2';self.check(r,'BLOCKED')
 def test_dirty_drift(self):
  r=valid();r['current']['files']['a.py']['sha256']='c'*64;self.check(r,'BLOCKED')
 def test_missing_untracked(self):
  r=valid();del r['current']['files']['new.py'];self.check(r,'BLOCKED')
 def test_review_missing(self):
  r=valid();r['review_status']='PENDING';self.check(r,'BLOCKED')
 def test_review_drift(self):
  r=valid();r['review_snapshot']['base']='other';self.check(r,'BLOCKED')
 def test_confirmed_weakening(self):
  r=valid();r['signals']=[{'location':'tests:12','disposition':'confirmed_weakening','evidence':['old failure now passes']}];self.check(r,'FAIL')
 def test_regex_signal_is_not_violation(self):
  r=valid();r['signals']=[{'location':'tests:12','disposition':'suspected','evidence':['assertion removed']}];self.check(r,'BLOCKED')
 def test_equivalent_assertion_refactor(self):
  r=valid();r['signals']=[{'location':'tests:12','disposition':'equivalent','evidence':['diff'],'before_after_behavior':['same mutant fails before and after']}];self.check(r,'PASS');del r['signals'][0]['before_after_behavior'];self.check(r,'BLOCKED')
 def test_exception_owner_and_scope(self):
  r=valid();s={'location':'tests:12','disposition':'accepted_exception','evidence':['decision.txt']};r['signals']=[s];self.check(r,'BLOCKED');s['owner_decision']={'owner':'contract owner','reference':'decision.txt','rationale':'approved changed contract','snapshot':copy.deepcopy(r['current'])};self.check(r,'PASS_WITH_EXCEPTIONS');s['owner_decision']['snapshot']['head']='old';self.check(r,'BLOCKED')
 def test_resume(self):
  r=valid();r['resumed']=True;self.check(r,'BLOCKED');r['resume_reconciled']=True;self.check(r,'PASS')
 def test_omitted_entity_view(self):
  r=valid();r['required_ui']=['persisted-view'];self.check(r,'BLOCKED')
 def test_story_not_entity_integration(self):
  r=valid();r['required_ui']=['view'];r['ui_evidence']['view']={'status':'PASS','snapshot':copy.deepcopy(r['current']),'evidence':['runtime.txt'],'acceptance':'persisted result visible','existing_scenario':'entity.spec.ts:view','surface':'integration','kind':'storybook'};self.check(r,'BLOCKED');r['ui_evidence']['view']['kind']='e2e';self.check(r,'PASS')
 def test_permission_error_states(self):
  r=valid();r['required_ui']=['denied','retry'];self.check(r,'BLOCKED')
  for n in r['required_ui']:r['ui_evidence'][n]={'status':'PASS','snapshot':copy.deepcopy(r['current']),'evidence':['storybook-runtime.txt'],'acceptance':n,'existing_scenario':'Form.stories.ts:'+n,'surface':'component','kind':'storybook'}
  self.check(r,'PASS');r['ui_evidence']['retry']['status']='NOT_RUN';self.check(r,'BLOCKED')
 def test_empty_scan_is_not_clean(self):
  r=valid();r['floor_evidence']=[];self.check(r,'BLOCKED')
 def test_invalid(self):
  for r in [None,[],{}, {'current':{}},valid()|{'signals':'bad'}]:self.check(r,'BLOCKED')

 def test_component_unit_evidence(self):
  r=valid();r['required_ui']=['component-contract'];r['ui_evidence']['component-contract']={'status':'PASS','snapshot':copy.deepcopy(r['current']),'evidence':['unit-run.txt'],'acceptance':'component event contract','existing_scenario':'Form.test.ts:submit','surface':'component','kind':'unit_component'};self.check(r,'PASS');r['ui_evidence']['component-contract']['surface']='integration';self.check(r,'BLOCKED')
