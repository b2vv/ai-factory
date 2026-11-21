"""Task/roadmap reconciliation declarations with pinned real Markdown evidence."""
import copy
import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch
import test_pending_action as fixture
p = fixture.p


class TaskOrder(unittest.TestCase):
    setUp = fixture.PendingAction.setUp
    git = fixture.PendingAction.git
    def save(self):
        fixture.PendingAction.save(self)
        if getattr(self, 'primary_context', None):
            self.record.write_text(self.primary_context + '\n' + self.record.read_text())

    def source(self, name, quote):
        path=self.evidence/name;path.write_text(quote+'\n')
        return {'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'quote':quote}

    def order(self):
        task=self.source('candidate.md','Task T1 is in_progress; continue the selected unfinished library slice.')
        roadmap=self.source('roadmap.md','Current approved roadmap R2: a headless library with optional UI adapters.')
        approval=self.source('approval.md','Owner approved R2 as direction; execution still needs a current task request.')
        coverage=self.source('coverage.md','Checked delivery ledger: PRE completed; the selected T1 feature is not delivered.')
        pre=self.source('predecessor.md','PRE completed and accepted; result.txt is the required reusable output.')
        output=self.source('result.txt','Verified predecessor output for the unfinished library slice.')
        self.data['ordering']={
            'observations':[
                {'id':'task-current','kind':'task','subject':'T1','value':'in_progress','source':task},
                {'id':'pre-done','kind':'task','subject':'PRE','value':'completed','source':pre}],
            'dependencies':[{'task_id':'PRE','outputs':[output]}],
            'decision_topics':[],
            'direction':{'task':task,'roadmap':roadmap,'approval':approval,'coverage':coverage,
                         'assessment':'aligned','rationale':'T1 implements the unfinished R2 slice, not PRE.',
                         'completed':[{'task_id':'PRE','relation':'distinct','evidence':pre}]}}
        return self.data['ordering']

    def inspect(self, require=True):
        self.save();return p.inspect(self.root,self.record,'T1',require_ordering=require)

    def test_legacy_optional_and_explicit_required(self):
        result=self.inspect(False)
        self.assertEqual(result['status'],'CONSISTENT');self.assertEqual(result['ordering']['status'],'NOT_CHECKED')
        result=self.inspect();self.assertEqual(result['status'],'NEEDS_RECONCILIATION')
        self.assertEqual(result['continuation'],'BLOCKED')

    def test_completed_predecessor_not_reopened(self):
        self.order();result=self.inspect()
        self.assertEqual(result['ordering']['status'],'RECONCILED')
        self.assertEqual(result['ordering']['completed_dependencies'],['PRE'])
        self.assertEqual(result['continuation'],'REVALIDATE_AUTHORIZATION')
        self.assertNotIn('READY',json.dumps(result))

    def test_old_task_vs_roadmap_conflict_does_not_close_task(self):
        o=self.order();o['direction']['assessment']='conflict';before=copy.deepcopy(self.data)
        result=self.inspect();self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['state'],'pending');self.assertEqual(before,self.data)
        self.assertNotEqual(result['next_action'],self.data['next_action'])
        self.assertEqual(result['recorded_next_action'],self.data['next_action'])

    def test_differently_named_completed_slice_blocks_duplicate_or_partial(self):
        for relation in ['duplicate','overlap','unknown']:
            o=self.order();o['direction']['completed'][0].update(task_id='DELIVERED-OTHER-NAME',relation=relation)
            result=self.inspect()
            with self.subTest(relation=relation):
                self.assertIn(result['status'],('BLOCKED','NEEDS_RECONCILIATION'))
                self.assertEqual(result['continuation'],'BLOCKED');self.assertEqual(self.data['state'],'pending')
        for assessment in ['duplicate','partial','unknown']:
            o=self.order();o['direction']['assessment']=assessment
            with self.subTest(assessment=assessment):self.assertNotEqual(self.inspect()['status'],'CONSISTENT')

    def test_missing_direction_and_coverage_not_proof_of_absence(self):
        o=self.order();del o['direction'];self.assertEqual(self.inspect()['status'],'NEEDS_RECONCILIATION')
        o=self.order();del o['direction']['coverage']
        with self.assertRaises(ValueError):self.inspect()

    def test_historical_status_requires_sourced_supersession(self):
        o=self.order();old=self.source('old.md','Historical task header: T1 planned, no work started.')
        o['observations'].append({'id':'task-old','kind':'task','subject':'T1','value':'planned','source':old})
        self.assertEqual(self.inspect()['status'],'NEEDS_RECONCILIATION')
        resolution=self.source('resolution.md','Current status replaces the historical T1 header; implementation is in progress.')
        o['observations'][0].update(supersedes=['task-old'],resolution=resolution)
        self.assertEqual(self.inspect()['ordering']['status'],'RECONCILED')

    def test_new_date_or_owner_role_does_not_resolve_conflict(self):
        o=self.order()
        for id_,value,quote in [('d1','allow','Owner note on Monday: allow feature X within the old roadmap.'),
                                ('d2','block','Owner note on Tuesday: stop feature X pending direction reconciliation.')]:
            o['observations'].append({'id':id_,'kind':'decision','subject':'FEATURE-X','value':value,'source':self.source(id_+'.md',quote)})
        o['decision_topics']=['FEATURE-X']
        self.assertEqual(self.inspect()['status'],'NEEDS_RECONCILIATION')
        o['observations'][-1].update(supersedes=['d1'],resolution=self.source('decision-resolution.md','Owner explicitly withdraws the earlier approval of feature X; keep it stopped.'))
        self.assertEqual(self.inspect()['status'],'BLOCKED')

    def test_superseded_task_never_follows_replacement(self):
        o=self.order();self.data['state']='superseded'
        o['observations'][0].update(value='superseded',replacement='T2',source=self.source('superseded.md','Owner explicitly superseded T1 with T2; T2 has a separate scope and approval.'))
        result=self.inspect();self.assertEqual(result['continuation'],'DO_NOT_RESUME')
        self.assertEqual(result['ordering']['replacement'],'T2');self.assertEqual(result['task_id'],'T1')

    def test_superseded_record_needs_evidence_and_pending_mismatch_reconciles(self):
        self.data['state']='superseded';self.assertEqual(self.inspect(False)['status'],'NEEDS_RECONCILIATION')
        self.data['state']='pending';o=self.order();o['observations'][0].update(value='superseded',replacement='T2')
        self.assertEqual(self.inspect()['status'],'NEEDS_RECONCILIATION')

    def test_dependency_unknown_unfinished_superseded_or_missing_output_blocks(self):
        for value in ['planned','in_progress','blocked','unknown','superseded']:
            o=self.order();o['observations'][1]['value']=value
            if value=='superseded':o['observations'][1]['replacement']='OTHER'
            with self.subTest(value=value):self.assertIn(self.inspect()['status'],('BLOCKED','NEEDS_RECONCILIATION'))
        o=self.order();o['dependencies'][0]['outputs']=[]
        self.assertEqual(self.inspect()['status'],'BLOCKED')
        o=self.order();(self.evidence/'result.txt').unlink()
        with self.assertRaises(OSError):self.inspect()

    def test_conflict_only_blocks_relevant_task(self):
        o=self.order()
        for id_,value in [('else1','planned'),('else2','completed')]:
            o['observations'].append({'id':id_,'kind':'task','subject':'UNRELATED','value':value,
                                      'source':self.source(id_+'.md','Unrelated task status '+value+'; independent scope.')})
        self.assertEqual(self.inspect()['ordering']['status'],'RECONCILED')

    def test_cycles_unknown_edges_duplicates_and_self_dependency(self):
        for mutation in ['cycle','unknown','duplicate','self']:
            o=self.order()
            if mutation=='cycle':
                obs=copy.deepcopy(o['observations'][0]);obs['id']='cycle';obs.update(supersedes=['task-current'],resolution=obs['source']);o['observations'].append(obs)
                o['observations'][0].update(supersedes=['cycle'],resolution=obs['source'])
            elif mutation=='unknown':o['observations'][0].update(supersedes=['missing'],resolution=o['direction']['task'])
            elif mutation=='duplicate':o['observations'].append(copy.deepcopy(o['observations'][0]))
            else:o['dependencies'][0]['task_id']='T1'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.inspect()

    def test_stale_source_quote_and_unsafe_path_fail_closed(self):
        for mutation in ['hash','quote','path']:
            o=self.order()
            if mutation=='hash':(self.evidence/'roadmap.md').write_text('changed direction')
            elif mutation=='quote':o['direction']['roadmap']['quote']='Invented approval that is absent from the cited source.'
            else:o['direction']['roadmap']['path']='../outside.md'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.inspect()

    def test_repository_evidence_and_observed_drift(self):
        o=self.order();(self.root/'roadmap.md').write_text('Repo direction remains the approved headless library.')
        o['direction']['roadmap']={'base':'repository','path':'roadmap.md','sha256':hashlib.sha256((self.root/'roadmap.md').read_bytes()).hexdigest(),'quote':'Repo direction remains the approved headless library.'}
        self.assertEqual(self.inspect()['ordering']['status'],'RECONCILED')
        original=p.git_head;calls=[]
        def drift(root):
            calls.append(1)
            if len(calls)==2:(self.root/'roadmap.md').write_text('concurrent changed direction')
            return original(root)
        with patch.object(p,'git_head',side_effect=drift),self.assertRaises(ValueError):self.inspect()

    def test_primary_prose_evidence_needs_no_duplicate_record(self):
        o=self.order();quote='Current T1 status is in_progress; its original task history stays here.'
        source={'base':'primary','quote':quote,'sha256':hashlib.sha256(quote.encode()).hexdigest()}
        o['observations'][0]['source']=source;o['direction']['task']=source
        with self.assertRaises(ValueError):self.inspect()  # Quote only inside JSON is not evidence.
        self.primary_context=quote
        self.assertEqual(self.inspect()['ordering']['status'],'RECONCILED')

    def test_completion_binds_ordering_and_changes_invalidate_checks(self):
        o=self.order();o['observations'][0]['value']='completed'
        fixture.PendingAction.complete(self)
        with self.assertRaises(ValueError):self.inspect()  # Review must bind ordering as well.
        path=self.evidence/'verdict.json';v=json.loads(path.read_text());v['ordering_snapshot_id']=p.snapshot_id(self.data)
        raw=json.dumps(v).encode();path.write_bytes(raw);self.data['verdict_sha256']=hashlib.sha256(raw).hexdigest()
        self.assertEqual(self.inspect()['continuation'],'DO_NOT_RESUME')
        o['direction']['rationale']='Changed reasoning after review requires evidence revalidation.'
        with self.assertRaises(ValueError):self.inspect()

    def test_ordering_cli_requires_evidence_and_is_read_only(self):
        self.order();self.save();before={str(f):f.read_bytes() for f in self.base.rglob('*') if f.is_file()}
        cmd=['python3','-B',str(fixture.ROOT/'runtime/checkpoint/pending_action.py'),'--root',str(self.root),'--record',str(self.record),'--task','T1','--require-ordering']
        result=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['ordering']['status'],'RECONCILED')
        self.assertEqual(before,{str(f):f.read_bytes() for f in self.base.rglob('*') if f.is_file()})
        self.data['ordering']['direction']['assessment']='unknown';self.save()
        result=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['status'],'NEEDS_RECONCILIATION')

if __name__=='__main__':unittest.main()
