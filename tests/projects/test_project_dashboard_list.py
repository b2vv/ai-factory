"""The dashboard's project list generated from the kit list (T15 P7).

Parity cases run the kit's ported rules and the real dashboard validator on the same rows
(`go run -tags nobundle . -list-projects`) and require identical verdicts. Skipped without Go.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load('projects_dashlist_base', ROOT / 'tests/projects/test_projects.py')
P, k, git_init = T.P, T.k, T.git_init
DB = P.DB
GO = shutil.which('go') or ('/usr/local/go/bin/go' if os.access('/usr/local/go/bin/go', os.X_OK) else None)
SOURCE = ROOT / 'runtime/dashboard'
CFG = {'go': GO, 'source': str(SOURCE)}


def cap(ident, **extra):
    return {'id': ident, 'name': extra.pop('name', ident.title()), **extra}


@unittest.skipUnless(GO, 'Go toolchain is not available')
class Parity(unittest.TestCase):
    """The kit accepts exactly what the dashboard accepts."""

    def verdicts(self, entries):
        try:
            DB.check_capabilities(entries)
            kit = True
        except DB.Blocked:
            kit = False
        data = (json.dumps(DB.rows(entries), ensure_ascii=False) + '\n').encode() if entries else b'[]'
        try:
            DB.go_validate(CFG, data)
            go = True
        except DB.Blocked:
            go = False
        return kit, go

    def test_same_verdicts(self):
        r = '/srv/p'
        cases = {
            'valid': [(r + 'a', cap('alpha')), (r + 'b', cap('beta', workflow='Review then merge.',
                                                              aliases=[{'id': 'beta-1', 'task': 't1'}]))],
            'bad id': [(r, cap('Alpha'))],
            'duplicate id': [(r + 'a', cap('alpha')), (r + 'b', cap('alpha'))],
            'alias equals an id': [(r + 'a', cap('alpha')), (r + 'b', cap('beta', aliases=[{'id': 'alpha', 'task': 't'}]))],
            'name 80 bytes': [(r, cap('alpha', name='a' * 80))],
            'name 81 bytes': [(r, cap('alpha', name='a' * 81))],
            'cyrillic name 82 bytes': [(r, cap('alpha', name='я' * 41))],
            'cyrillic name 80 bytes': [(r, cap('alpha', name='я' * 40))],
            'workflow 560': [(r, cap('alpha', workflow='w' * 560))],
            'workflow 561': [(r, cap('alpha', workflow='w' * 561))],
            'URL in name': [(r, cap('alpha', name='see https://example.invalid'))],
            'path in workflow': [(r, cap('alpha', workflow='read /etc/passwd'))],
            'windows path in name': [(r, cap('alpha', name='C:\\temp'))],
            'blank name': [(r, cap('alpha', name='   '))],
            'control char in name': [(r, cap('alpha', name='a\tb'))],
            '8 aliases': [(r, cap('alpha', aliases=[{'id': f'a{i}', 'task': f't{i}'} for i in range(8)]))],
            '9 aliases': [(r, cap('alpha', aliases=[{'id': f'a{i}', 'task': f't{i}'} for i in range(9)]))],
            'bad alias task': [(r, cap('alpha', aliases=[{'id': 'a1', 'task': 'Bad Task'}]))],
            'root with comma': [('/srv/a,b', cap('alpha'))],
            'root with quote': [('/srv/a"b', cap('alpha'))],
            'root not clean': [('/srv/a/../b', cap('alpha'))],
            'root double slash': [('//srv/a', cap('alpha'))],
            'root is slash': [('/', cap('alpha'))],
            'relative root': [('srv/a', cap('alpha'))],
            '32 projects': [(f'/srv/p{i}', cap(f'p{i}')) for i in range(32)],
            '33 projects': [(f'/srv/p{i}', cap(f'p{i}')) for i in range(33)],
        }
        for name, entries in cases.items():
            with self.subTest(name):
                kit, go = self.verdicts(entries)
                self.assertEqual(go, kit, f'kit={kit} dashboard={go}')
        self.assertTrue(self.verdicts(cases['valid'])[0])
        self.assertFalse(self.verdicts(cases['33 projects'])[0])


@unittest.skipUnless(GO, 'Go toolchain is not available')
class ListCommands(T.Base):
    capture = False

    def setUp(self):
        super().setUp()
        self.a = git_init(self.cf.base / 'alpha')
        self.b = git_init(self.cf.base / 'beta')
        self.gen = self.kit / k.STATE / DB.GENERATED
        self.feed = self.cf.base / 'feed'
        self.feed.mkdir(mode=0o700)

    def install(self, project, *extra):
        return self.ok('install', '--project', str(project), *extra, '--apply')

    def generated(self):
        return json.loads(self.gen.read_text()) if self.gen.exists() else None

    def test_install_sets_keeps_and_removes_the_row(self):
        self.install(self.a, '--dashboard-id', 'alpha', '--dashboard-name', 'Alpha')
        self.assertEqual([{'id': 'alpha', 'name': 'Alpha', 'root': str(self.a)}], self.generated())
        self.assertEqual(0o600, self.gen.stat().st_mode & 0o777)
        self.assertEqual('NOOP', self.ok('install', '--project', str(self.a), '--apply')['status'])
        self.assertEqual([{'id': 'alpha', 'name': 'Alpha', 'root': str(self.a)}],
                         self.ok('list', '--dashboard-config')['dashboard_projects'])
        self.assertNotIn('restart', self.install(self.b).get('dashboard', {}))  # no row change, no note
        out = self.install(self.b, '--dashboard-id', 'beta')
        self.assertIn('restart', out['dashboard'])
        data = self.gen.read_bytes()
        DB.go_validate(CFG, data)  # the real dashboard validator accepts it
        self.assertEqual(data, DB.generated_bytes(P.dashboard_entries(P.load(self.kit))))  # deterministic
        self.assertEqual(['alpha', 'beta'], [r['id'] for r in self.generated()])
        self.assertEqual('beta', self.generated()[1]['name'])  # defaults to the entry name
        self.install(self.b, '--no-dashboard')
        self.assertEqual(['alpha'], [r['id'] for r in self.generated()])
        self.install(self.a, '--no-dashboard')
        self.assertIsNone(self.generated())  # the last capability removed deletes the file

    def test_remove_drops_the_row(self):
        self.install(self.a, '--dashboard-id', 'alpha')
        self.install(self.b, '--dashboard-id', 'beta')
        self.ok('remove', '--project', str(self.a), '--apply')
        self.assertEqual(['beta'], [r['id'] for r in self.generated()])

    def test_edit_outside_the_kit_blocks(self):
        self.install(self.a, '--dashboard-id', 'alpha')
        self.gen.write_text('[]\n')
        self.assertIn('edited outside the kit', self.blocked('install', '--project', str(self.b), '--apply')['reason'])

    def test_invalid_capability_blocks_before_writing(self):
        self.assertIn('dashboard id', self.blocked('install', '--project', str(self.a), '--dashboard-id', 'Bad Id', '--apply')['reason'])
        self.install(self.a, '--dashboard-id', 'alpha')
        before = self.gen.read_bytes()
        self.assertIn('duplicate', self.blocked('install', '--project', str(self.b), '--dashboard-id', 'alpha', '--apply')['reason'])
        self.assertEqual(before, self.gen.read_bytes())

    def test_failure_mid_write_restores_the_generated_file(self):
        self.install(self.a, '--dashboard-id', 'alpha')
        before = self.gen.read_bytes()
        P.FAULT = ('before-list', ValueError('injected'))  # after the generated file is written
        self.blocked('install', '--project', str(self.b), '--dashboard-id', 'beta', '--apply')
        self.assertEqual(before, self.gen.read_bytes())

    def test_pointer_in_the_same_run_after_the_switch(self):
        self.install(self.a, '--dashboard-id', 'alpha')
        self.ok('dashboard', '--source', str(SOURCE), '--projects', str(self.gen), '--feed', str(self.feed), '--go', GO, '--apply')
        out = self.install(self.b, '--dashboard-id', 'beta')
        self.assertEqual('beta', out['dashboard']['project'])
        self.assertIn('Dashboard status for this project: id `beta`', (self.b / 'AGENTS.local.md').read_text())

    def test_import_matches_by_root_not_order(self):
        self.ok('install', '--project', str(self.a), '--apply')
        self.ok('install', '--project', str(self.b), '--apply')
        hand = self.cf.base / 'hand-projects.json'
        rows = [{'id': 'beta', 'name': 'Beta', 'root': str(self.b), 'aliases': [{'id': 'beta-1', 'task': 'one'}]},
                {'id': 'alpha', 'name': 'Alpha', 'root': str(self.a), 'workflow': 'Review, then merge.'}]
        hand.write_text(json.dumps(rows))
        plan = self.ok('dashboard-import', '--from', str(hand))
        self.assertTrue(plan['status'].startswith('PLANNED'))
        self.assertEqual('APPLIED', self.ok('dashboard-import', '--from', str(hand), '--apply')['status'])
        self.assertEqual({r['id']: r for r in rows}, {r['id']: r for r in self.generated()})
        self.assertEqual(['alpha', 'beta'], [r['id'] for r in self.generated()])  # kit list order
        self.assertEqual('NOOP', self.ok('dashboard-import', '--from', str(hand))['status'])

    def test_import_conflicts_write_nothing(self):
        self.ok('install', '--project', str(self.a), '--dashboard-id', 'alpha', '--apply')
        listed = (self.kit / k.STATE / P.LIST).read_bytes()
        hand = self.cf.base / 'hand-projects.json'
        hand.write_text(json.dumps([{'id': 'other', 'name': 'Other', 'root': str(self.a)},
                                    {'id': 'ghost', 'name': 'Ghost', 'root': str(self.cf.base / 'nowhere')}]))
        out = self.run_cli('dashboard-import', '--from', str(hand), '--apply')
        self.assertEqual('BLOCKED', out['status'])
        self.assertEqual(2, len(out['conflicts']))
        self.assertEqual(listed, (self.kit / k.STATE / P.LIST).read_bytes())


if __name__ == '__main__':
    unittest.main()
