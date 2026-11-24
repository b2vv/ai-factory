"""T33: the Obsidian pointer in the project list (`capabilities.obsidian`) drives the managed block.

Disposable fixtures only; a stub HTTP server on an ephemeral 127.0.0.1 port stands in for the plugin.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load('projects_obsidian_base', ROOT / 'tests/projects/test_projects.py')
C = load('projects_obsidian_connect', ROOT / 'tests/connect/test_connect_obsidian.py')
P, k, git_init = T.P, T.k, T.git_init
MARKER = C.MARKER


class ObsidianRegistry(T.Base):
    capture = False

    def setUp(self):
        super().setUp()
        self.server = None
        self.addCleanup(self.stop)
        self.vaults = self.cf.base / 'vaults'

    def stop(self):
        if self.server:
            self.server.shutdown(); self.server.server_close()

    def vault(self, name, port):
        v = self.vaults / name
        plugin = v / '.obsidian' / 'plugins' / 'obsidian-local-rest-api'
        plugin.mkdir(parents=True, exist_ok=True)
        (plugin / 'data.json').write_text(json.dumps({'apiKey': C.SENTINEL, 'insecurePort': port, 'enableInsecureServer': True}))
        return v.resolve()

    def serve(self):
        import http.server, threading
        C.Stub.body = {'status': 'OK', 'service': 'Obsidian Local REST API'}
        self.server = http.server.HTTPServer(('127.0.0.1', 0), C.Stub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    def block(self, project):
        text = (project / 'AGENTS.local.md').read_text()
        return text.split(P.connection().BEGIN, 1)[1].split(P.connection().END, 1)[0]

    def listed(self, name):
        return next(e for e in self.ok('list')['projects'] if e['name'] == name)

    def obs(self, vault, port):
        return ['--obsidian-vault', str(vault), '--obsidian-port', str(port)]

    def test_install_records_lists_and_retains(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        plan = self.ok('install', '--project', str(project), *self.obs(vault, port))
        self.assertEqual('OK', plan['obsidian']['state'])
        self.assertNotIn(C.SENTINEL, json.dumps(plan))
        self.ok('install', '--project', str(project), *self.obs(vault, port), '--apply')
        self.assertEqual({'vault': str(vault), 'port': port}, self.listed('alpha')['capabilities']['obsidian'])
        self.assertIn(MARKER, self.block(project))
        self.assertEqual(0o600, self.list_path.stat().st_mode & 0o777)
        before = self.snapshot(self.list_path, project / 'AGENTS.local.md')
        self.assertEqual('NOOP', self.ok('install', '--project', str(project), '--apply')['status'])
        self.assertEqual(before, self.snapshot(self.list_path, project / 'AGENTS.local.md'))
        self.assertNotIn(C.SENTINEL, self.list_path.read_text())

    def test_registry_wins_over_hand_edited_marker(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(project), *self.obs(vault, port), '--apply')
        agents = project / 'AGENTS.local.md'
        line = next(l for l in agents.read_text().splitlines() if l.startswith(MARKER))
        stale = MARKER + json.dumps({'port': port + 1, 'vault': str(vault)}, sort_keys=True) + ' -->'
        agents.write_text(agents.read_text().replace(line, stale))
        plan = self.ok('install', '--project', str(project))
        self.assertTrue(plan['status'].startswith('PLANNED'), plan)
        self.assertTrue(plan['obsidian']['reconciled'])
        self.ok('install', '--project', str(project), '--apply')
        self.assertIn(line, self.block(project))
        self.assertNotIn(stale, self.block(project))

    def test_marker_without_registry_key_is_cleared(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(project), '--apply')
        cp = P.connection()
        rc = cp.main(['--managed-root', str(self.kit), '--project', str(project), *self.obs(vault, port), '--apply'])
        self.assertEqual(0, rc)
        self.assertIn(MARKER, self.block(project))
        out = self.ok('install', '--project', str(project), '--apply')
        self.assertTrue(out['obsidian']['reconciled'], out)
        self.assertNotIn(MARKER, self.block(project))

    def test_clear_removes_key_and_lines_and_rollback_restores_both(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(project), *self.obs(vault, port), '--apply')
        files = [self.list_path, project / 'AGENTS.local.md']
        before = self.snapshot(*files)
        P.FAULT = ('before-list', ValueError('injected'))
        self.blocked('install', '--project', str(project), '--clear-obsidian', '--apply')
        P.FAULT = None
        self.assertEqual(before, self.snapshot(*files))
        self.ok('install', '--project', str(project), '--clear-obsidian', '--apply')
        self.assertNotIn('obsidian', self.listed('alpha')['capabilities'])
        self.assertNotIn(MARKER, self.block(project))

    def test_port_collision_and_bad_input_block_without_writes(self):
        port = self.serve()
        a, b = git_init(self.cf.base / 'alpha'), git_init(self.cf.base / 'beta')
        self.ok('install', '--project', str(a), *self.obs(self.vault('alpha', port), port), '--apply')
        self.ok('install', '--project', str(b), '--apply')
        before = self.snapshot(self.list_path, b / 'AGENTS.local.md')
        reason = self.blocked('install', '--project', str(b), *self.obs(self.vault('beta', port), port), '--apply')['reason']
        self.assertIn('obsidian port', reason)
        self.assertIn('port', self.blocked('install', '--project', str(b), *self.obs(self.vault('beta', port), port + 3),
                                           '--apply')['reason'])           # not this vault's port
        self.blocked('install', '--project', str(b), '--obsidian-vault', str(self.vault('beta', port)), '--apply')
        self.assertEqual(before, self.snapshot(self.list_path, b / 'AGENTS.local.md'))
        # re-installing the owner of the port is not a collision with itself
        self.assertEqual('NOOP', self.ok('install', '--project', str(a), *self.obs(self.vault('alpha', port), port))['status'])

    def test_validate_shape(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(project), *self.obs(vault, port), '--apply')
        doc = json.loads(self.list_path.read_text())
        P.validate(json.loads(json.dumps(doc)))
        for bad in ({'vault': str(vault)}, {'vault': 'rel', 'port': port}, {'vault': str(vault), 'port': '1'},
                    {'vault': str(vault), 'port': 80}, {'vault': str(vault), 'port': port, 'x': 1},
                    {'vault': str(vault) + '`', 'port': port}, {'vault': str(vault) + '\u0085', 'port': port}, 'x'):
            d = json.loads(json.dumps(doc)); d['projects'][0]['capabilities']['obsidian'] = bad
            with self.assertRaises(ValueError, msg=bad):
                P.validate(d)

    def test_move_root_and_update_report_carry_the_pointer(self):
        port = self.serve(); vault = self.vault('alpha', port)
        project = git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(project), *self.obs(vault, port), '--apply')
        moved = self.cf.base / 'alpha-moved'
        os.rename(project, moved)
        self.ok('move-root', '--project', str(project), '--to', str(moved), '--apply')
        self.assertIn(MARKER, self.block(moved))
        self.assertEqual({'vault': str(vault), 'port': port}, self.listed('alpha')['capabilities']['obsidian'])
        rows = P.check_projects(self.kit)
        self.assertEqual('OK', rows[0]['status'], rows)


if __name__ == '__main__':
    unittest.main()
