import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('precode', ROOT/'runtime/checkpoint/precode.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

class CritiqueTests(unittest.TestCase):
    def setUp(self):
        self.r = json.loads((ROOT/'examples/checkpoint/record.json').read_text())
        self.c = json.loads((ROOT/'examples/checkpoint/snapshot.json').read_text())
        self.prompt = {'path':'prompts/plan-critic.md','version':'1','sha256':hashlib.sha256((ROOT/'prompts/plan-critic.md').read_bytes()).hexdigest()}
        self.c['review_prompt'] = copy.deepcopy(self.prompt)
        self.r.update(mode='full', plan_review={'required':True,'status':'ACCEPTED','stage':'plan','author':'author-session','route':'existing-session','reference':'critic-session','evidence':'synthetic verdict fixture','defense':['synthetic defense fixture'],'plan':copy.deepcopy(self.r['plan']),'snapshot':copy.deepcopy(self.r['snapshot']),'prompt':self.prompt,'findings':[]})
    def status(self):
        return p.validate(self.r,self.c)['status']
    def before(self):
        return {k:copy.deepcopy(self.r[k]) for k in ('plan','snapshot','decision_surface')}
    def advance_plan(self):
        self.r['plan']={'version':'example-v2','sha256':'b'*64};self.c['plan']=copy.deepcopy(self.r['plan'])
    def carry(self,before):
        self.r['plan_review']['carry_forward']={'before':before,'target_plan':copy.deepcopy(self.r['plan']),'target_snapshot':copy.deepcopy(self.r['snapshot']),'owner':'operator','reason':'Compared exact delta, unchanged decisions','evidence':['synthetic before-after delta, not actual acceptance']}
    def test_exact_plan_snapshot_prompt_binding(self):
        self.assertEqual(self.status(),'READY')
    def test_missing_or_stale_plan_identity_blocks(self):
        for value in (None,{}, {'version':'v2','sha256':'b'*64}):
            self.c['plan']=value;self.assertEqual(self.status(),'BLOCKED')
    def test_changed_prompt_requires_explicit_current_identity(self):
        self.c['review_prompt']['sha256']='c'*64;self.assertEqual(self.status(),'BLOCKED')
    def test_implementation_review_cannot_accept_plan(self):
        self.r['plan_review']['stage']='implementation';self.assertEqual(self.status(),'BLOCKED')
    def test_accepted_header_with_open_blocker_is_blocked(self):
        self.r['plan_review']['findings']=[{'id':'B1','severity':'blocker','status':'open','disposition':'owner later','evidence':'missing contract'}]
        self.assertEqual(self.status(),'BLOCKED')
        self.r['plan_review']['findings'][0].update(status='resolved',disposition='contract accepted',evidence='synthetic sourced owner decision')
        self.assertEqual(self.status(),'READY')
    def test_blocker_cannot_hide_behind_small_na(self):
        self.r['plan_review'].update(required=False,status='N/A',reason='small')
        self.r['plan_review']['findings']=[{'id':'B1','severity':'blocker','status':'open','disposition':'later','evidence':'required gap'}]
        self.assertEqual(self.status(),'BLOCKED')
    def test_material_categories_require_recritique(self):
        for field in p.MATERIAL_FIELDS:
            before=self.before();after=copy.deepcopy(before);after['decision_surface'][field]+=' changed'
            self.assertEqual(p.classify_change(before,after),{'status':'RECRITIQUE','material_fields':[field]})
    def test_cosmetic_change_does_not_imply_new_critique(self):
        before=self.before();self.advance_plan()
        self.assertEqual(p.classify_change(before,self.before())['status'],'REAFFIRM')
        self.assertEqual(self.status(),'BLOCKED')
        self.carry(before);self.assertEqual(self.status(),'READY')
        self.assertEqual(self.r['plan_review']['plan'],before['plan'])
    def test_material_change_cannot_carry_old_verdict(self):
        before=self.before();self.advance_plan();self.r['decision_surface']['contracts']='new contract';self.carry(before)
        self.assertEqual(self.status(),'BLOCKED')
        self.r['plan_review'].update(plan=copy.deepcopy(self.r['plan']),snapshot=copy.deepcopy(self.r['snapshot']),evidence='synthetic fresh critic verdict on changed contract')
        self.assertEqual(self.status(),'READY')
    def test_snapshot_delta_needs_scoped_revalidation(self):
        before=self.before();self.r['snapshot']['dirty_scope']='new scoped bytes';self.c['dirty_scope']='new scoped bytes';self.r['impact']['snapshot']=copy.deepcopy(self.r['snapshot'])
        self.assertEqual(p.classify_change(before,self.before())['status'],'REVALIDATE');self.assertEqual(self.status(),'BLOCKED')
        self.carry(before);self.assertEqual(self.status(),'READY')
    def test_carry_forward_requires_owner_and_evidence(self):
        before=self.before();self.advance_plan();self.carry(before);self.r['plan_review']['carry_forward']['evidence']=[];self.assertEqual(self.status(),'BLOCKED')
    def test_unknown_decision_surface_fails_closed(self):
        before=self.before();del before['decision_surface']['risk'];self.assertEqual(p.classify_change(before,self.before())['status'],'BLOCKED')
    def test_change_without_target_snapshot_fails_closed(self):
        before=self.before();del before['snapshot'];self.assertEqual(p.classify_change(before,self.before())['status'],'BLOCKED')
    def test_unchanged_scope_retains_readiness_in_batch(self):
        a=copy.deepcopy(self.r);b=copy.deepcopy(self.r);b['task_id']='dependent';b['plan']={'version':'changed','sha256':'b'*64};b['decision_surface']['acceptance']='new behavior'
        snapshots={a['task_id']:self.c,b['task_id']:{**self.c,'plan':b['plan']}}
        result=p.validate_batch({'approved':True,'tasks':[a,b]},snapshots)
        self.assertEqual([r['status'] for r in result['tasks']],['READY','BLOCKED'])
    def test_synthetic_batch_has_real_blocker_not_fake_pass(self):
        batch=json.loads((ROOT/'examples/checkpoint/batch.json').read_text());snap=json.loads((ROOT/'examples/checkpoint/batch-snapshots.json').read_text());result=p.validate_batch(batch,snap)
        self.assertEqual(result['status'],'BLOCKED');self.assertEqual([t['status'] for t in result['tasks']],['READY','BLOCKED'])
    def measurement(self):
        return {'command':'example-check --scope mapping','exit_code':0,'status':'PASS','required':True,'artifact':'synthetic-fixture-only.log','snapshot':copy.deepcopy(self.r['snapshot'])}
    def test_pass_requires_exit_zero_and_exact_dirty_snapshot(self):
        e=self.measurement();self.r['measurements']=[e];self.assertEqual(self.status(),'READY');e['exit_code']=1;self.assertEqual(self.status(),'BLOCKED');e['exit_code']=0;e['snapshot']['dirty_scope']='old';self.assertEqual(self.status(),'BLOCKED')
    def test_unrun_required_check_is_not_ready(self):
        e=self.measurement();e.update(status='NOT_TESTED',exit_code=None,reason='not authorized');self.r['measurements']=[e];self.assertEqual(self.status(),'BLOCKED');e['required']=False;self.assertEqual(self.status(),'READY')
    def test_missing_exit_or_boolean_zero_is_not_pass(self):
        e=self.measurement();self.r['measurements']=[e]
        for value in (None,False,'0'):
            e['exit_code']=value;self.assertEqual(self.status(),'BLOCKED')
    def test_missing_findings_list_blocks_claimed_approval(self):
        del self.r['plan_review']['findings'];self.assertEqual(self.status(),'BLOCKED')

if __name__=='__main__':unittest.main()
