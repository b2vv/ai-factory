"""Selected-primary-record dashboard projection, with no live feed or project mutations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/checkpoint'))
import publish_status as p


class PublishStatus(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'fixture')
        self.record = self.repo / 'TASK.md'
        self.record.write_text('# Existing plaintext\nSensitive memo and command. All tests PASS here.\n')
        self.feed = self.base / 'feed'
        self.feed.mkdir(mode=0o700)
        self.binary = self.base / 'dashboard-writer'
        self.binary.write_text('#!/bin/sh\nexit 0\n')
        self.binary.chmod(0o700)
        self.registry = self.base / 'projects.json'
        self.registered = [{'id': 'project-a', 'name': 'Project A', 'root': str(self.repo)},
                           {'id': 'project-b', 'name': 'Project B', 'root': str(self.base / 'other')}]
        self.config = self.base / 'bindings.json'
        self.settings = {
            'schema': 'ai-factory-dashboard-bindings/2',
            'projects': {'project-a': {'root': str(self.repo)}},
            'feed': str(self.feed), 'publisher': str(self.binary), 'dashboard_projects': str(self.registry),
        }
        self.save()

    def git(self, *args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(self.repo), *args],
                                       text=True).strip()

    def save(self):
        self.config.write_text(json.dumps(self.settings))
        self.config.chmod(0o600)
        self.registry.write_text(json.dumps(self.registered))
        self.registry.chmod(0o600)

    def run_publish(self, **kw):
        args = dict(project='project-a', root=self.repo, record=self.record, task='M1', event='handoff',
                    config=self.config)
        args.update(kw)
        return p.publish(**args)

    def receipt(self, command, data, apply):
        if apply:
            (self.feed / 'project-a.transition.json').write_bytes(data)

    def test_plain_markdown_is_not_parsed_or_copied(self):
        with patch.object(p, 'call_writer') as writer:
            self.assertEqual(self.run_publish(), 'VALIDATED')
        writer.assert_called_once()
        command, raw, write = writer.call_args.args
        details = json.loads(raw)
        self.assertFalse(write)
        self.assertIn('-publish-transition', command)
        self.assertEqual(command[1:3], ['-projects', str(self.registry)])
        self.assertNotIn('-apply', command)
        self.assertEqual(details['revision'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(details['taskId'], 'm1')
        self.assertEqual(details['schema'], 'factory-dashboard/transition/1')
        self.assertEqual(details['event'], 'handoff')
        self.assertFalse({'stages', 'state', 'markdown', 'scopeId'} & set(details))
        self.assertNotIn(b'Sensitive', raw)
        self.assertNotIn(b'PASS', raw)
        self.assertNotIn(str(self.record).encode(), raw)

    def test_apply_only_writes_and_confirms_transition_receipt(self):
        curated = self.feed / 'project-a.json'
        curated.write_text('earlier gate evidence')
        before = curated.stat()
        with patch.object(p, 'call_writer', side_effect=self.receipt) as writer:
            self.assertEqual(self.run_publish(event='stage', stage='review', apply=True), 'PUBLISHED')
        preview, apply = [call.args for call in writer.call_args_list]
        self.assertEqual(apply[0][:-1], preview[0])
        self.assertEqual(apply[0][-1], '-apply')
        self.assertEqual(preview[1], apply[1])
        self.assertFalse(preview[2])
        self.assertTrue(apply[2])
        self.assertEqual(json.loads(apply[1])['stage'], 'review')
        self.assertEqual(curated.read_text(), 'earlier gate evidence')
        self.assertEqual(curated.stat().st_mtime_ns, before.st_mtime_ns)

    def test_rejects_wrong_binding_path_head_version_and_typed_stage(self):
        other = self.base / 'elsewhere.md'
        other.write_text('unbound')
        symlink = self.repo / 'linked.md'
        symlink.symlink_to(self.record)
        for args in (
                {'root': self.base}, {'record': other}, {'record': symlink}, {'task': '../anything'},
                {'expected_head': 'f'*40}, {'expected_record': 'f'*64}, {'event': 'stage'},
                {'stage': 'review'}, {'event': 'stage', 'stage': 'pass'}):
            with self.subTest(args=args), patch.object(p, 'call_writer') as writer:
                with self.assertRaises(ValueError):
                    self.run_publish(**args)
                writer.assert_not_called()

    def test_rejects_unregistered_or_mismatched_dashboard_project(self):
        cases = (
            ('settings', 'schema', 'ai-factory-dashboard-bindings/1'),
            ('registered', 0, {'id': 'project-a', 'name': 'Project A', 'root': str(self.base)}),
            ('registered', 0, {'id': 'project-c', 'name': 'Project C', 'root': str(self.repo)}),
            ('settings', 'dashboard_projects', str(self.feed / 'projects.json')),
        )
        for target, key, value in cases:
            with self.subTest(key=key, value=value), patch.object(p, 'call_writer') as writer:
                saved = json.loads(json.dumps((self.settings, self.registered)))
                getattr(self, target)[key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.run_publish()
                writer.assert_not_called()
                self.settings, self.registered = saved
                self.save()
        with patch.object(p, 'call_writer') as writer, self.assertRaises(ValueError):
            self.run_publish(project='Project-A')
        writer.assert_not_called()

    def test_caller_task_id_not_attested_by_markdown(self):
        with patch.object(p, 'call_writer') as writer:
            self.assertEqual(self.run_publish(task='OTHER-1'), 'VALIDATED')
        result = json.loads(writer.call_args.args[1])
        self.assertEqual(result['taskId'], 'other-1')
        self.assertFalse({'scopeId', 'stages', 'state'} & set(result))

    def test_accepts_explicit_external_record_root_only(self):
        records = self.base / 'evidence'
        records.mkdir()
        record = records / 'TASK.md'
        record.write_text('owner-selected private primary record')
        self.settings['projects']['project-a']['record_roots'] = [str(records)]
        self.save()
        with patch.object(p, 'call_writer') as writer:
            self.assertEqual(self.run_publish(record=record), 'VALIDATED')
        self.assertNotIn(b'owner-selected', writer.call_args.args[1])

    def test_record_change_after_preview_prevents_apply(self):
        def mutate(command, data, apply):
            self.record.write_text('new version during validation')
        with patch.object(p, 'call_writer', side_effect=mutate) as writer:
            with self.assertRaises(ValueError):
                self.run_publish(apply=True)
        writer.assert_called_once()

    def test_move_after_apply_is_uncertain_not_retried(self):
        def mutate(command, data, apply):
            self.receipt(command, data, apply)
            if apply:
                self.record.write_text('new version after apply')
        with patch.object(p, 'call_writer', side_effect=mutate) as writer:
            with self.assertRaises(p.Uncertain):
                self.run_publish(apply=True)
        self.assertEqual(writer.call_count, 2)

    def test_writer_success_without_exact_receipt_is_uncertain(self):
        with self.assertRaises(p.Uncertain):
            self.run_publish(apply=True)
        self.assertEqual(list(self.feed.iterdir()), [])

    def test_opt_in_scope_requires_existing_exact_pending_action_evidence(self):
        with patch.object(p, 'call_writer') as writer:
            with self.assertRaises(ValueError):
                self.run_publish(scope_id='3a')
            writer.assert_not_called()
        local = self.repo / 'relevant.md'
        local.write_text('exact bytes')
        data = {
            'schema': 'ai-factory-pending/1', 'root': str(self.repo), 'head': self.git('rev-parse', 'HEAD'),
            'task_id': 'M1', 'revision': 'r1', 'stage': 'review', 'scope': {'relevant.md': p.digest(local.read_bytes())},
            'review_mode': 'independent_subagent', 'writer': 'fixture-writer', 'reviewer': None,
            'action_id': 'review-one', 'action_owner': 'fixture-writer', 'state': 'pending', 'transfer': 'none',
            'next_action': 'Prepare review', 'contact_mechanism': 'native result', 'delivery_owner': 'fixture-writer',
            'authorization_source': 'explicit user', 'runtime_available': True, 'required_final_verdict': True,
            'checks': [],
        }
        self.record.write_text('# Task\n```ai-factory-pending-action\n' + json.dumps(data) + '\n```\n')
        with patch.object(p, 'call_writer') as writer:
            self.assertEqual(self.run_publish(scope_id='3a'), 'VALIDATED')
        result = json.loads(writer.call_args.args[1])
        self.assertEqual(result['scopeId'], '3a')
        self.assertEqual(result['scopeSnapshot'], p.inspect(self.repo, self.record, 'M1')['snapshot_id'])
        self.assertNotIn('relevant.md', json.dumps(result))
        local.write_text('changed under the same HEAD')
        with self.assertRaises(ValueError):
            self.run_publish(scope_id='3a')
