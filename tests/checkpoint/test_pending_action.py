"""Read-only pending-action regression tests with disposable Git repositories."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pending_action', ROOT / 'runtime/checkpoint/pending_action.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PendingAction(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base / 'repo'; self.root.mkdir()
        self.evidence = self.base / 'evidence'; self.evidence.mkdir()
        self.git('init', '-q'); self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                     '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'fixture')
        (self.root / 'file.txt').write_text('current')
        self.record = self.evidence / 'task.md'
        self.data = dict(schema='ai-factory-pending/1', root=str(self.root), task_id='T1', revision='r1',
                         stage='review', head=self.git('rev-parse', 'HEAD').strip(),
                         scope={'file.txt': hashlib.sha256(b'current').hexdigest()},
                         review_mode='independent_subagent', writer='writer', reviewer='reviewer',
                         action_id='review-1', action_owner='writer', state='pending', transfer='prepared',
                         next_action='Deliver the exact package to the assigned reviewer',
                         contact_mechanism='native result', delivery_owner='writer', authorization_source='current request',
                         runtime_available=True, required_final_verdict=True, package_id='package-1', checks=[])
        self.save()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL, text=True)

    def save(self):
        self.record.write_text('# Existing primary record\n\n```ai-factory-pending-action\n' + json.dumps(self.data) + '\n```\n')

    def inspect(self):
        self.save(); return p.inspect(self.root, self.record, 'T1')

    def complete(self):
        self.data['state'] = 'completed'; self.data['transfer'] = 'verdict_received'
        (self.evidence / 'check.txt').write_text('command: test; exit: 0')
        self.data['checks'] = [dict(id='tests', required=True, status='PASS',
                                   snapshot_id=p.snapshot_id(self.data), path='check.txt',
                                   sha256=hashlib.sha256((self.evidence / 'check.txt').read_bytes()).hexdigest())]
        verdict = {k: self.data[k] for k in ('task_id', 'revision', 'root', 'head', 'scope', 'package_id', 'reviewer')}
        verdict.update(outcome='ACCEPTED', blocking_findings=[], evidence=['check.txt'])
        raw = json.dumps(verdict).encode(); (self.evidence / 'verdict.json').write_bytes(raw)
        self.data.update(verdict_path='verdict.json', verdict_sha256=hashlib.sha256(raw).hexdigest())

    def test_read_only_recovery(self):
        before = {str(f): f.read_bytes() for f in self.base.rglob('*') if f.is_file()}
        result = p.inspect(self.root, self.record, 'T1')
        self.assertEqual(result['status'], 'CONSISTENT'); self.assertEqual(result['continuation'], 'REVALIDATE_AUTHORIZATION')
        self.assertEqual(result['next_action'], self.data['next_action']); self.assertEqual(result['reviewer'], 'reviewer')
        self.assertEqual(before, {str(f): f.read_bytes() for f in self.base.rglob('*') if f.is_file()})

    def test_wrong_task_head_root_and_hash(self):
        for key, value in [('task_id','T2'),('head','f'*40),('root',str(self.base)),('scope',{'file.txt':'f'*64})]:
            original = copy.deepcopy(self.data); self.data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.inspect()
            self.data = original

    def test_nonexistent_and_deleted_scope(self):
        self.data['scope']['deleted.txt'] = None
        self.assertEqual(self.inspect()['status'],'CONSISTENT')
        (self.root/'deleted.txt').write_text('returned')
        with self.assertRaises(ValueError): self.inspect()

    def test_transfer_and_lifecycle_never_resend(self):
        for state, transfer, expected in [('pending','attempted','RECONCILE_DELIVERY'),('pending','sent','WAIT'),
                ('pending','acknowledged','WAIT'),('waiting','none','WAIT'),('blocked','none','BLOCKED'),
                ('paused','none','DO_NOT_RESUME')]:
            self.data.update(state=state,transfer=transfer,next_check='assigned owner checks receipt')
            with self.subTest(state=state,transfer=transfer): self.assertEqual(self.inspect()['continuation'],expected)

    def test_wait_and_unavailable_require_blocker(self):
        self.data['state']='waiting'
        with self.assertRaises(ValueError):self.inspect()
        self.data.update(state='pending',runtime_available=False)
        with self.assertRaises(ValueError):self.inspect()

    def test_completion_is_bound_and_requires_checks(self):
        self.complete(); self.assertEqual(self.inspect()['continuation'],'DO_NOT_RESUME')
        for key, value in [('checks',[]),('transfer','sent'),('reviewer','writer'),('verdict_sha256','f'*64)]:
            original=copy.deepcopy(self.data);self.data[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.inspect()
            self.data=original
        self.data['checks'][0]['status']='NOT_TESTED'
        with self.assertRaises(ValueError):self.inspect()

    def test_verdict_must_bind_scope_not_only_head(self):
        self.complete(); v=json.loads((self.evidence/'verdict.json').read_text()); v['scope']={'other':'a'*64}
        raw=json.dumps(v).encode();(self.evidence/'verdict.json').write_bytes(raw)
        self.data['verdict_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):self.inspect()

    def test_review_na_is_explicit_and_checks_still_required(self):
        self.complete();self.data.update(required_final_verdict=False,review_na_basis='Documentation-only local rule')
        self.assertEqual(self.inspect()['continuation'],'DO_NOT_RESUME')
        del self.data['review_na_basis']
        with self.assertRaises(ValueError):self.inspect()

    def test_stale_check_evidence_and_snapshot(self):
        self.complete();self.data['checks'][0]['snapshot_id']='a'*64
        with self.assertRaises(ValueError):self.inspect()
        self.data['checks'][0]['snapshot_id']=p.snapshot_id(self.data)
        (self.evidence/'check.txt').write_text('changed')
        with self.assertRaises(ValueError):self.inspect()

    def test_unsafe_scope_and_evidence(self):
        for name in ['../outside','/absolute','.git/config','.env','credentials.json']:
            self.data['scope']={name:'a'*64}
            with self.subTest(name=name),self.assertRaises(ValueError):self.inspect()
        self.data['scope']={'link':'a'*64};(self.root/'link').symlink_to(self.record)
        with self.assertRaises(ValueError):self.inspect()

    def test_unsafe_and_oversize_record(self):
        link=self.evidence/'link.md';link.symlink_to(self.record)
        with self.assertRaises(ValueError):p.inspect(self.root,link,'T1')
        os.mkfifo(self.evidence/'fifo')
        with self.assertRaises(ValueError):p.inspect(self.root,self.evidence/'fifo','T1')
        self.record.write_bytes(b'x'*524289)
        with self.assertRaises(ValueError):p.inspect(self.root,self.record,'T1')

    def test_duplicate_blocks_and_keys(self):
        self.record.write_text(self.record.read_text()*2)
        with self.assertRaises(ValueError):p.inspect(self.root,self.record,'T1')
        self.record.write_text('{"task_id":"T1","task_id":"T2"}')
        with self.assertRaises(ValueError):p.inspect(self.root,self.record,'T1')

    def test_observed_scope_drift_blocks(self):
        original=p.git_head; calls=[]
        def drift(root):
            calls.append(1)
            if len(calls)==2:(self.root/'file.txt').write_text('concurrent writer')
            return original(root)
        with patch.object(p,'git_head',side_effect=drift),self.assertRaises(ValueError):self.inspect()

    def test_cli_blocked_diagnostic_does_not_echo_input(self):
        self.record.write_text('private malformed payload')
        result=subprocess.run(['python3','-B',str(ROOT/'runtime/checkpoint/pending_action.py'),
                '--root',str(self.root),'--record',str(self.record),'--task','T1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1); self.assertEqual(json.loads(result.stdout)['status'],'BLOCKED')
        self.assertNotIn('private malformed payload',result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
