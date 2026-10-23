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
        payload = {'hook_event_name': event, 'session_id': '$(unsafe)', 'cwd': '/untrusted;path'}
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

    def test_no_repeat(self):
        r, state, writes = self.invoke(introduced=True)
        self.assertEqual(r, {}); self.assertEqual(writes, 0)

    def test_other_events_unchanged(self):
        for ev in ['UserPromptSubmit', 'PostToolUse', 'Stop']:
            r, state, writes = self.invoke(event=ev)
            self.assertEqual(r, {}); self.assertFalse(state['introduced']); self.assertEqual(writes, 0)

if __name__ == '__main__': unittest.main(verbosity=2)
