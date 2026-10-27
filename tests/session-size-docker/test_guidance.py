from pathlib import Path
import tempfile
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
TESTS = str(Path(__file__).resolve().parent)
import sys, unittest, contextlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, (CODE + ''))
import guard

class Guidance(unittest.TestCase):
    def invoke(self, event='SessionStart', introduced=False):
        state = {'introduced': introduced, 'level': 0, 'size_unknown': True}
        payload = {'hook_event_name': event, 'session_id': 'fixture-A', 'cwd': '/untrusted;path'}
        with patch.object(guard, 'identity', return_value=('key', '/trusted')), patch.object(guard, 'locked', return_value=contextlib.nullcontext()), patch.object(guard, 'state_for', return_value=(Path('/state'), state)), patch.object(guard, 'atomic') as atomic:
            result = guard.event_locked(Path('/store'), 'codex', payload)
        return result, state, atomic.call_count

    def test_public_interface(self):
        r, state, writes = self.invoke()
        text = r['hookSpecificOutput']['additionalContext']
        self.assertIn('sh "$AI_FACTORY_HOOK_HOME/dispatch.sh" checkpoint', text)
        self.assertIn('--root "$TRUSTED_ROOT"', text)
        self.assertIn('--work "$NEW_RECEIPT_DIR"', text)
        self.assertIn('--pointer "$EXACT_HANDOFF_ID"', text)
        self.assertNotIn('guard.py', text)
        self.assertNotIn('--cwd', text)
        self.assertNotIn('$(unsafe)', text)
        self.assertTrue(state['introduced']); self.assertEqual(writes, 1)

    def test_template_limitations_explicit(self):
        text = self.invoke()[0]['hookSpecificOutput']['additionalContext']
        for term in ['not an installed-path claim', 'operator-approved mapping', 'not hook payload paths', 'fresh and private', 'legacy store', 'sanitized JSON']:
            self.assertIn(term, text)

    def test_no_repeat_but_current_identity(self):
        r, state, writes = self.invoke(introduced='native-identity-v1')
        text = r['hookSpecificOutput']['additionalContext']
        self.assertIn('AI_FACTORY_NATIVE_IDENTITY', text)
        self.assertNotIn('Public shell template', text)
        self.assertEqual(writes, 0)

    def test_first_normal_event_introduces_and_stop_does_not(self):
        for ev in ['UserPromptSubmit', 'PostToolUse']:
            r, state, writes = self.invoke(event=ev)
            self.assertIn('not required exported environment variables', r['hookSpecificOutput']['additionalContext'])
            self.assertEqual(state['introduced'], 'native-identity-v1')
            self.assertEqual(writes, 1)
        r, state, writes = self.invoke(event='Stop')
        self.assertEqual(r, {})
        self.assertFalse(state['introduced'])
        self.assertEqual(writes, 0)

    def test_registry_route_and_no_overlay_contract(self):
        text = self.invoke()[0]['hookSpecificOutput']['additionalContext']
        self.assertIn('registry', text)
        self.assertIn('registered native.sh command', text)
        self.assertNotIn('policy.json', text)
        self.assertNotIn('--git-trust-root', text)

if __name__ == '__main__': unittest.main(verbosity=2)
