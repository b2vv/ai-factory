import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('precode', ROOT / 'runtime/checkpoint/precode.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((ROOT / 'examples/checkpoint/record.json').read_text())
        self.current = json.loads((ROOT / 'examples/checkpoint/snapshot.json').read_text())
    def status(self):
        return p.validate(self.record, self.current)['status']
    def test_valid_small_file_fallback(self):
        self.assertEqual(self.status(), 'READY')
    def test_missing_impact_cannot_be_ready(self):
        del self.record['impact']; self.assertEqual(self.status(), 'BLOCKED')
    def test_unresolved_required_question(self):
        self.record['grilling']['questions'] = [{'question':'Which owner policy?', 'required':True, 'status':'deferred', 'reason':'later'}]
        self.assertEqual(self.status(), 'BLOCKED')
    def test_resolved_question_requires_decision_source(self):
        self.record['grilling']['questions'] = [{'question':'Policy?', 'required':True, 'status':'resolved', 'decision':'A'}]
        self.assertEqual(self.status(), 'BLOCKED')
        self.record['grilling']['questions'][0]['source'] = 'task.md#owner-decision'
        self.assertEqual(self.status(), 'READY')
    def test_blocked_dependency(self):
        self.record['dependencies'] = [{'id':'shared-file-predecessor', 'status':'BLOCKED', 'evidence':'awaiting change'}]
        self.assertEqual(self.status(), 'BLOCKED')
    def test_dirty_snapshot_drift(self):
        self.current['dirty_scope'] = 'new bytes'; self.assertEqual(self.status(), 'BLOCKED')
    def test_head_and_root_drift(self):
        for key in ('head', 'root'):
            current = dict(self.current); current[key] = 'other'
            self.assertEqual(p.validate(self.record, current)['status'], 'BLOCKED')
    def test_missing_current_snapshot(self):
        self.assertEqual(p.validate(self.record, {})['status'], 'BLOCKED')
    def test_empty_impact_not_safety_proof(self):
        self.record['impact']['callers'] = []; self.assertEqual(self.status(), 'BLOCKED')
    def test_file_fallback_needs_reason_and_evidence(self):
        self.record['impact']['reason'] = ''; self.assertEqual(self.status(), 'BLOCKED')
    def test_stale_graph_then_valid_file_fallback(self):
        self.record['impact'].update(method='crg',fresh=False,hash_evidence=['hash-list'],untracked_coverage='not indexed; checked directly')
        self.assertEqual(self.status(), 'BLOCKED')
        self.record['impact'].update(method='files',reason='Graph stale; inspected named callers/contracts by rg')
        self.assertEqual(self.status(), 'READY')
    def test_fresh_graph_requires_hash_and_coverage(self):
        self.record['impact'].update(method='ttsc',fresh=True)
        self.assertEqual(self.status(), 'BLOCKED')
        self.record['impact'].update(hash_evidence=['checked scoped hashes'],untracked_coverage='explicit file inventory checked')
        self.assertEqual(self.status(), 'READY')
    def test_null_graph_freshness(self):
        self.record['impact'].update(method='graphify',fresh=None)
        self.assertEqual(self.status(), 'BLOCKED')
    def test_required_review_author_cannot_self_accept(self):
        self.record.update(mode='full',plan_review={'required':True,'status':'ACCEPTED','evidence':'plan.md#verdict','route':'existing-session','reference':'author','author':'author','defense':['plan.md#defense']})
        self.assertEqual(self.status(), 'BLOCKED')
        self.record['plan_review']['reference'] = 'independent-session'
        prompt = {'path':'prompts/plan-critic.md','version':'1','sha256':__import__('hashlib').sha256((ROOT/'prompts/plan-critic.md').read_bytes()).hexdigest()}
        self.current['review_prompt'] = prompt
        self.record['plan_review'].update(stage='plan', plan=copy.deepcopy(self.record['plan']), snapshot=copy.deepcopy(self.record['snapshot']), prompt=prompt, findings=[])
        self.assertEqual(self.status(), 'READY')
    def test_required_review_pending_blocks(self):
        self.record['plan_review'] = {'required':True,'status':'PENDING'}
        self.assertEqual(self.status(), 'BLOCKED')
    def test_small_requires_reason(self):
        self.record['small_reason'] = ''; self.assertEqual(self.status(), 'BLOCKED')
    def test_resume_revalidates_delta_without_full_replay(self):
        self.record['mode'] = 'resume'; self.assertEqual(self.status(), 'BLOCKED')
        self.record['resume'] = {'previous_record':'task.md#checkpoint','delta':'only changed caller; acceptance unchanged','revalidated':['current caller hashes and impact; retained accepted unaffected evidence']}
        self.assertEqual(self.status(), 'READY')
    def test_batch_approval_never_waives_per_task_blocker(self):
        blocked = copy.deepcopy(self.record); blocked['task_id'] = 'second'; del blocked['impact']
        result = p.validate_batch({'approved':True,'status':'READY','tasks':[self.record, blocked]}, {self.record['task_id']:self.current,'second':self.current})
        self.assertEqual(result['status'],'BLOCKED'); self.assertEqual([t['status'] for t in result['tasks']],['READY','BLOCKED'])
    def test_empty_or_duplicate_batch(self):
        self.assertEqual(p.validate_batch({'approved':True,'tasks':[]},{})['status'],'BLOCKED')
        self.assertEqual(p.validate_batch({'tasks':[self.record,self.record]}, {})['status'],'BLOCKED')
    def test_malformed_inputs_fail_closed(self):
        self.assertEqual(p.validate([],self.current)['status'],'BLOCKED')
        for key in ('impact','grilling','plan_review'):
            obj=copy.deepcopy(self.record);obj[key]=False
            self.assertEqual(p.validate(obj,self.current)['status'],'BLOCKED')
    def test_index_detects_missing_task_and_broken_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tasks=root/'work/tasks';tasks.mkdir(parents=True);(tasks/'001-real').mkdir();(tasks/'001-real/task.md').write_text('task')
            index=tasks/'README.md';index.write_text('[bad](002-missing/plan.md)\nНаступний вільний номер — **001**.\n')
            result=p.check_index(root,'work/tasks/README.md','work/tasks')
            self.assertEqual({i['kind'] for i in result['issues']},{'missing-or-outside-link','unindexed-task','hardcoded-next-number'})
            index.write_text('[task](001-real/task.md)\n')
            self.assertEqual(p.check_index(root,'work/tasks/README.md','work/tasks')['status'],'PASS')
    def test_checkpoint_is_reachable_from_all_shared_entries(self):
        for name in ('ai-factory-plan.md','feature-lifecycle.md','workflow.md'):
            self.assertIn('](pre-code-checkpoint.md)', (ROOT/'ai-factory'/name).read_text())

if __name__ == '__main__': unittest.main()
