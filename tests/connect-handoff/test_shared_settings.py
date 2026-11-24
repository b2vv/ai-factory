"""C6: capture and native handoff registered on one home both write ~/.claude/settings.json.

Re-registering either must not make the other report drift.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


fx = load('shared_settings_capture_fixture', ROOT / 'tests/install/test_capture_update.py')
ch = load('shared_settings_handoff', ROOT / 'tools/connect-handoff.py')
k = fx.k


class SharedSettings(unittest.TestCase):
    def setUp(self):
        cf = self.cf = fx.UpdateTests('test_explicit_registration_normal_update_and_idempotence')
        cf.setUp(); self.addCleanup(cf.doCleanups)
        for name, text in ((ch.NATIVE, 'HANDOFF_API = 1\ndef load_profile(p): pass\ndef event(*a, **kw): pass\ndef main(argv=None): pass\n'),
                           (ch.GUARD, '# guard\n')):
            (cf.pkg / name).parent.mkdir(parents=True, exist_ok=True); (cf.pkg / name).write_text(text)
        manifest = k.read_json(cf.pkg / 'release-manifest.json')
        for name in (ch.NATIVE, ch.GUARD):
            manifest['files'].append({'path': name, 'sha256': k.digest((cf.pkg / name).read_bytes()), 'component': 'core'})
        (cf.pkg / 'release-manifest.json').write_bytes(k.encode(manifest))
        (cf.pkg / 'checksums.sha256').write_text(''.join(
            k.digest(p.read_bytes()) + '  ' + str(p.relative_to(cf.pkg)) + '\n'
            for p in sorted(cf.pkg.rglob('*')) if p.is_file() and p.name != 'checksums.sha256'))
        self.assertEqual('APPLIED', cf.apply()['status'])
        self.spec = {'home': str(cf.home), 'managed_root': str(cf.root), 'store': str(cf.base / 'store'), 'roots': [str(cf.project)],
                     'profile_path': str(cf.private / 'profile.json'), 'registration_root': str(cf.base / 'handoff-reg'),
                     'hosts': ['claude'], 'python': str(Path(sys.executable).resolve())}

    def test_both_registrations_stay_noop_on_one_settings_file(self):
        self.assertEqual('APPLIED', ch.apply(self.spec, ch.plan(self.spec)['plan_id'], True)['status'])
        self.assertEqual('NOOP', fx.u.plan(k, self.cf.pkg, self.cf.root, [])['status'])
        self.assertEqual('NOOP', ch.plan(self.spec)['status'])
        self.assertEqual('VERIFIED', ch.verify(self.spec)['status'])

    def test_permissions_change_blocks_both(self):
        ch.apply(self.spec, ch.plan(self.spec)['plan_id'], True)
        settings = self.cf.home / '.claude/settings.json'
        doc = json.loads(settings.read_bytes()); doc['permissions'] = {'defaultMode': 'bypassPermissions'}
        settings.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'permissions drift'): fx.u.plan(k, self.cf.pkg, self.cf.root, [])
        with self.assertRaisesRegex(ValueError, 'permissions drift'): ch.plan(self.spec)


if __name__ == '__main__':
    unittest.main()
