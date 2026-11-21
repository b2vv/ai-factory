"""Offline policy shape: no host configuration, Docker or private data read."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class RestartPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / 'restart.compose.json').read_text())

    def test_exact_service_scope(self):
        self.assertEqual(set(self.policy), {'services'})
        self.assertEqual(set(self.policy['services']), {'factory', 'postgres', 'mongo'})

    def test_persistent_but_respects_operator_stop(self):
        for service in self.policy['services'].values():
            self.assertEqual(service['restart'], 'unless-stopped')

    def test_database_health_dependencies(self):
        self.assertEqual(self.policy['services']['factory']['depends_on'], {
            'postgres': {'condition': 'service_healthy'},
            'mongo': {'condition': 'service_healthy'},
        })

    def test_no_image_storage_exposure_or_credential_overrides(self):
        for name, service in self.policy['services'].items():
            self.assertEqual(set(service), {'restart', 'depends_on'} if name == 'factory' else {'restart'})

    def test_disposable_harnesses_remain_manual(self):
        for name in ('dev', 'test'):
            text = (ROOT.parent / name / 'compose.yaml').read_text()
            self.assertNotIn('unless-stopped', text)
            self.assertNotIn('restart: always', text)
            self.assertIn('restart: "no"', text)


if __name__ == '__main__':
    unittest.main()
