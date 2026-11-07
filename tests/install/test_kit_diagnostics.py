"""kit.py BLOCKED reasons are specific and never echo a path, name or file content."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import kit

ROOT = Path(__file__).resolve().parents[2]


class BlockedReason(unittest.TestCase):
    def code(self, msg):
        return kit.blocked_reason(ValueError(msg)).split(':', 1)[0]

    def test_categories_are_distinct_and_actionable(self):
        cases = {
            'explicit canonical absolute path required': 'UNSAFE_OR_INVALID_PATH',
            'source and destination must not overlap': 'UNSAFE_OR_INVALID_PATH',
            'stale or wrong plan': 'STALE_OR_MISSING_PLAN',
            'plan id and exclusive writer window required': 'STALE_OR_MISSING_PLAN',
            'unfinished transaction: rollback first': 'UNFINISHED_TRANSACTION',
            'local edit or unmanaged collision: adapters/README.md': 'LOCAL_EDIT_COLLISION',
            'concurrent edit: installed.json': 'CONCURRENT_OR_CORRUPT_STATE',
            'use update for managed installation': 'ALREADY_INSTALLED',
            'use install for new destination': 'NOT_INSTALLED',
            'invalid transaction id': 'INVALID_TRANSACTION',
            'release hash mismatch': 'INVALID_PACKAGE',
            'state directory must be private and owned': 'STATE_PERMISSIONS',
        }
        for msg, expected in cases.items():
            self.assertEqual(self.code(msg), expected, msg)

    def test_reason_never_echoes_embedded_path(self):
        # Messages that carry a filename must not leak it into the reason.
        r = kit.blocked_reason(ValueError('local edit or unmanaged collision: secret/PRIVATE.txt'))
        self.assertNotIn('PRIVATE', r)
        self.assertNotIn('secret', r)

    def test_type_classified_reasons(self):
        self.assertTrue(kit.blocked_reason(OSError('x')).startswith('IO_ERROR'))
        self.assertTrue(kit.blocked_reason(json.JSONDecodeError('m', 'd', 0)).startswith('MALFORMED_JSON'))
        self.assertTrue(kit.blocked_reason(KeyError('k')).startswith('MALFORMED_METADATA'))

    def test_unknown_message_falls_back_without_echo(self):
        r = kit.blocked_reason(ValueError('PRIVATE_SENTINEL weird'))
        self.assertTrue(r.startswith('INVALID_OR_UNSAFE_INPUT'))
        self.assertNotIn('PRIVATE_SENTINEL', r)


class CliBlocked(unittest.TestCase):
    def test_cli_emits_specific_reason_on_stale_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'toolkit'
            # install --execute with a bogus plan id against an empty package -> BLOCKED.
            r = subprocess.run([sys.executable, str(ROOT / 'tools/kit.py'), 'install',
                                '--package', str(ROOT), '--root', str(root),
                                '--execute', '--exclusive-window', '--plan-id', 'deadbeef'],
                               capture_output=True, text=True)
            out = json.loads(r.stdout)
            self.assertEqual(out['status'], 'BLOCKED')
            # A concrete category, not the old catch-all sentence.
            self.assertRegex(out['reason'], r'^[A-Z_]+:')
            self.assertNotIn('invalid/stale input, unsafe path, conflict, lock or IO failure', out['reason'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
