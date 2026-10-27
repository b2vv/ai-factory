"""Synthetic event-boundary acceptance tests; no host sessions or live state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, os.environ.get('CODE_DIR', str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')))
import entry
import guard
import validate
from unittest.mock import patch
import contextlib
import io
import importlib.util
spec = importlib.util.spec_from_file_location("selector", Path(entry.__file__).with_name("session-key.py"))
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)

class IdentityDelivery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.store = self.base / 'store'
        self.store.mkdir(mode=0o700)
        self.args = SimpleNamespace(root=str(self.root), store=str(self.store),
            mode='hook', host='claude', session='fixture-A', transcript=None,
            pointer='', store_leaf=None)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, event='SessionStart', **fields):
        payload = dict(hook_event_name=event, session_id=self.args.session,
                       cwd=str(self.root), transcript_path=None)
        payload.update(fields)
        return entry.execute(self.args, json.dumps(payload).encode())

    def identity(self, result):
        self.assertIn('hookSpecificOutput', result, 'current identity envelope must be delivered')
        text = result['hookSpecificOutput']['additionalContext']
        lines = [line for line in text.splitlines() if line.startswith('AI_FACTORY_NATIVE_IDENTITY ')]
        self.assertEqual(len(lines), 1, 'one current identity envelope must be delivered')
        return json.loads(lines[0].split(' ', 1)[1])

    def test_current_native_identity_is_delivered(self):
        result = self.invoke()
        self.assertEqual(self.identity(result), {
            'schema': 'ai-factory-native-identity/1', 'host': 'claude',
            'session_id': 'fixture-A', 'root': str(self.root), 'event': 'SessionStart'})
        text = result['hookSpecificOutput']['additionalContext']
        self.assertIn('not required exported environment variables', text)
        self.assertIn('native.sh', text)
        self.assertIn('CURRENT_NATIVE_IDENTITY_UNAVAILABLE', text)

    def test_repeat_and_other_context_events_do_not_write_state(self):
        self.invoke()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.store.iterdir()}
        for event in ['SessionStart', 'UserPromptSubmit', 'PostToolUse']:
            result = self.invoke(event)
            self.assertEqual(self.identity(result)['event'], event)
            validate.validate('hook', result)
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.store.iterdir()}
        self.assertEqual(before, after)

    def test_first_successful_prompt_after_deferred_start_gets_guidance(self):
        result = self.invoke('UserPromptSubmit')
        self.assertIn('not required exported environment variables',
                      result['hookSpecificOutput']['additionalContext'])
        again = self.invoke('PostToolUse')
        self.assertNotIn('not required exported environment variables',
                         again['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.identity(again)['session_id'], 'fixture-A')

    def test_old_intro_marker_gets_new_guidance_once(self):
        self.invoke()
        record = next(self.store.glob('session-*.json'))
        state = json.loads(record.read_text())
        state['introduced'] = True
        record.write_text(json.dumps(state))
        result = self.invoke('PostToolUse')
        self.assertIn('not required exported environment variables',
                      result['hookSpecificOutput']['additionalContext'])
        before = (record.read_bytes(), record.stat().st_mtime_ns)
        self.invoke('PostToolUse')
        self.assertEqual(before, (record.read_bytes(), record.stat().st_mtime_ns))

    def test_cross_session_host_and_root_are_exact(self):
        self.assertEqual(self.identity(self.invoke())['session_id'], 'fixture-A')
        self.args.session = 'fixture-B'
        self.args.host = 'codex'
        value = self.identity(self.invoke())
        self.assertEqual(value['session_id'], 'fixture-B')
        self.assertEqual(value['host'], 'codex')
        self.root = self.base / 'other'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.args.root = str(self.root)
        self.assertEqual(self.identity(self.invoke())['root'], str(self.root))

    def test_invalid_session_never_emits_or_advances_state(self):
        for sid in [None, '', [], 3, ' ', 'bad\n', 'bad\u202e', 'a'*257, '$(touch X)', 'x;echo bad']:
            with self.subTest(sid=repr(sid)):
                self.args.session = sid
                with self.assertRaises((ValueError, TypeError)):
                    self.invoke()
                self.assertEqual(list(self.store.iterdir()), [])

    def test_allowed_session_grammar(self):
        for sid in ['A_z-09', 'a'*256]:
            self.args.session = sid
            self.assertEqual(self.identity(self.invoke())['session_id'], sid)

    def test_payload_cli_identity_mismatch_rejected(self):
        for field, value in [('session_id', 'foreign'), ('cwd', str(self.base)),
                             ('transcript_path', '/private/not-authorized')]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.invoke(**{field: value})
                self.assertEqual(list(self.store.iterdir()), [])

    def test_no_prompt_tool_transcript_or_new_identity_persistence(self):
        result = self.invoke(prompt='PRIVATE_SENTINEL', tool_input={'x': 'PRIVATE_SENTINEL'},
                             tool_response='PRIVATE_SENTINEL')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
        self.assertNotIn('transcript_path', json.dumps(self.identity(result)))
        for p in self.store.iterdir():
            text = p.read_text()
            self.assertNotIn('PRIVATE_SENTINEL', text)
            self.assertNotIn('AI_FACTORY_NATIVE_IDENTITY', text)
            self.assertNotIn('fixture-A', text)

    def test_shell_special_root_is_json_data(self):
        self.root = self.base / "quote' dollar$ semicolon; backtick` space"
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.args.root = str(self.root)
        self.assertEqual(self.identity(self.invoke())['root'], str(self.root))
        self.assertFalse((self.base / 'X').exists())

    def test_non_ascii_root_is_ascii_json_and_round_trips(self):
        self.root = self.base / 'caf\u00e9'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.args.root = str(self.root)
        result = self.invoke()
        text = result['hookSpecificOutput']['additionalContext']
        line = next(line for line in text.splitlines() if line.startswith('AI_FACTORY_NATIVE_IDENTITY '))
        self.assertTrue(line.isascii())
        self.assertEqual(self.identity(result)['root'], str(self.root))

    def test_unrepresentable_root_rejected_before_state(self):
        for root in ['relative', '/bad\nroot', '/bad\u007froot', '/bad\u202eroot', '/'+'x'*4096, '/'+'\U0001f600'*1000]:
            with self.subTest(root_length=len(root)):
                with patch.object(guard, 'identity', return_value=('key', root)):
                    with self.assertRaisesRegex(ValueError, 'current native identity unavailable'):
                        guard.event(self.store, 'claude', {'hook_event_name': 'SessionStart',
                            'session_id': 'fixture-A', 'cwd': str(self.root)})
                self.assertEqual(list(self.store.iterdir()), [])

    def test_invalid_event_and_host_never_emit(self):
        with self.assertRaises(ValueError):
            self.invoke('OtherEvent')
        self.args.host = 'other'
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(list(self.store.iterdir()), [])

    def test_stop_does_not_deliver_identity(self):
        self.assertNotIn('AI_FACTORY_NATIVE_IDENTITY', json.dumps(self.invoke('Stop')))

    def test_busy_and_bad_state_do_not_confirm_identity(self):
        with patch.object(guard, 'locked', side_effect=guard.LockBusy):
            self.assertNotIn('AI_FACTORY_NATIVE_IDENTITY', json.dumps(self.invoke()))
            self.args.pointer = 'explicit'
            with self.assertRaises(guard.LockBusy):
                self.invoke()
        self.args.pointer = ''
        self.invoke()
        for p in self.store.glob('session-*.json'):
            p.write_text('{')
        with self.assertRaises(json.JSONDecodeError):
            self.invoke()

    def resume_fixture(self, summary):
        token = 'a'*32 + '-1-' + 'b'*12
        self.args.pointer = token
        obj = {'id': token, 'complete': True, 'created': time.time(), 'depth': 0,
               'snapshot': {'root': str(self.root)}, 'summary': summary}
        (self.store/(token+'.json')).write_text(json.dumps(obj, ensure_ascii=False))
        return token

    def test_successful_resume_and_noop_keep_current_identity(self):
        token = self.resume_fixture({f: 'Synthetic approved summary' for f in guard.FIELDS})
        with patch.object(guard, 'snapshot', return_value={'root': str(self.root)}):
            result = self.invoke('PostToolUse')
            record = next(self.store.glob('session-*.json'))
            before = (record.read_bytes(), record.stat().st_mtime_ns)
            again = self.invoke('SessionStart')
            self.assertEqual(before, (record.read_bytes(), record.stat().st_mtime_ns))
        self.assertEqual(self.identity(result)['session_id'], 'fixture-A')
        self.assertIn('Synthetic approved summary', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.identity(again)['session_id'], 'fixture-A')
        self.assertNotIn('Synthetic approved summary', again['hookSpecificOutput']['additionalContext'])
        validate.validate('hook', result)
        validate.validate('hook', again)
        self.args.session = 'foreign-session'
        with patch.object(guard, 'snapshot', return_value={'root': str(self.root)}):
            with self.assertRaisesRegex(ValueError, 'consumed by another session'):
                self.invoke()
        self.args.session = 'fixture-A'
        self.args.pointer = ''
        normal = self.invoke('UserPromptSubmit')
        self.assertIn('not required exported environment variables',
                      normal['hookSpecificOutput']['additionalContext'])
        self.assertEqual(json.loads(record.read_text())['introduced'], 'native-identity-v1')

    def test_stop_pointer_resume_does_not_deliver_identity(self):
        self.resume_fixture({f: 'Synthetic approved summary' for f in guard.FIELDS})
        with patch.object(guard, 'snapshot', return_value={'root': str(self.root)}):
            result = self.invoke('Stop')
        self.assertNotIn('AI_FACTORY_NATIVE_IDENTITY', json.dumps(result))

    def test_oversized_resume_context_rejects_before_claim(self):
        token = self.resume_fixture({f: '\\'*1600 for f in guard.FIELDS})
        with patch.object(guard, 'snapshot', return_value={'root': str(self.root)}):
            with self.assertRaisesRegex(ValueError, 'native identity context exceeds delivery limit'):
                self.invoke()
        self.assertFalse((self.store/('claim-'+token+'.json')).exists())
        self.assertEqual(list(self.store.glob('session-*.json')), [])

    def test_serialized_resume_bound_rejects_before_claim(self):
        self.root = self.base.joinpath(*['\U0001f600'*50 for _ in range(12)])
        self.root.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.args.root = str(self.root)
        token = self.resume_fixture({f: '\U0001f600'*1000 for f in guard.FIELDS})
        with patch.object(guard, 'snapshot', return_value={'root': str(self.root)}):
            with self.assertRaisesRegex(ValueError, 'native identity context exceeds delivery limit'):
                self.invoke()
        self.assertFalse((self.store/('claim-'+token+'.json')).exists())
        self.assertEqual(list(self.store.glob('session-*.json')), [])

    def test_diagnostics_are_english_and_do_not_echo_rejected_value(self):
        text = guard.handoff_diagnostic(ValueError('current native identity unavailable'))
        self.assertIn('CURRENT_NATIVE_IDENTITY_UNAVAILABLE', text)
        self.assertIn('session_id', text)
        self.assertNotIn('PRIVATE_SENTINEL', guard.handoff_diagnostic(ValueError('PRIVATE_SENTINEL')))
        for p in Path(entry.__file__).parent.glob('*'):
            if p.suffix in ('.py', '.sh'):
                self.assertFalse(any(1024 <= ord(c) <= 1327 for c in p.read_text()), p.name)

    def test_selector_projects_only_event_fields(self):
        payload = {'hook_event_name': 'PostToolUse', 'cwd': str(self.root),
            'session_id': 'fixture-A', 'transcript_path': None,
            'prompt': 'PRIVATE_SENTINEL', 'tool_response': 'PRIVATE_SENTINEL'}
        projected = selector.project('claude', json.dumps(payload).encode())
        key, data = projected.splitlines()
        self.assertEqual(len(key), 64)
        self.assertEqual(json.loads(data), {'hook_event_name': 'PostToolUse',
            'cwd': str(self.root), 'session_id': 'fixture-A', 'transcript_path': None})
        self.assertNotIn('PRIVATE_SENTINEL', projected)
        for sid in [None, 'bad\n', '']:
            with self.assertRaises(ValueError):
                selector.project('claude', json.dumps(dict(payload, session_id=sid)).encode())
        with self.assertRaises(ValueError):
            selector.project('claude', b'{"session_id":"a","session_id":"b"}')

    def test_dispatch_pointer_conflict_stops_before_docker(self):
        code = Path(entry.__file__).parent
        env = dict(os.environ, AI_FACTORY_HANDOFF='old-pointer')
        result = subprocess.run(['sh', str(code/'dispatch.sh'), 'resume', '--pointer', 'new-pointer'],
                                env=env, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')

if __name__ == '__main__':
    unittest.main(verbosity=2)
