"""One project list (T15 P1/P3/P5) on disposable fixtures; no host settings or credentials."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P = load('projects_under_test', ROOT / 'tools/projects.py')
fixture = load('projects_capture_fixture', ROOT / 'tests/install/test_capture_update.py')
instructions = load('projects_instruction_fixture', ROOT / 'tests/install/test_instruction_update.py')
D = load('projects_dispatcher', ROOT / 'runtime/storage/deploy/capture-bridge/claude_capture_dispatcher.py')
k = P.k


class Killed(BaseException):
    pass


def git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['/usr/bin/git', 'init', '-q', str(path)], check=True)
    return path


class Base(unittest.TestCase):
    capture = True

    def setUp(self):
        self.cf = fixture.UpdateTests(); self.cf.setUp(); self.addCleanup(self.cf.doCleanups)
        if self.capture:
            self.assertEqual('APPLIED', self.cf.apply()['status'])
        self.kit = self.cf.root
        self.addCleanup(setattr, P, 'FAULT', None)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = P.main([argv[0], '--root', str(self.kit), *argv[1:]])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 1 if out['status'] == 'BLOCKED' else 0)
        return out

    def ok(self, *argv):
        out = self.run_cli(*argv)
        self.assertNotEqual('BLOCKED', out['status'], out)
        return out

    def blocked(self, *argv):
        out = self.run_cli(*argv)
        self.assertEqual('BLOCKED', out['status'], out)
        return out

    @property
    def mapping(self):
        return Path(self.cf.spec['mapping_path'])

    @property
    def list_path(self):
        return self.kit / k.STATE / P.LIST

    def credential(self, name):
        path = self.cf.private / f'{name}.cred.json'
        path.write_text('{}'); path.chmod(0o600)
        return path

    def snapshot(self, *paths):
        return {str(p): (p.read_bytes() if p.exists() else None) for p in paths}


class CleanMachine(Base):
    """No capture registered: a project is listed with the default wiring only (A1, A2, A10)."""
    capture = False

    def test_install_list_rerun_noop(self):
        project = git_init(self.cf.base / 'alpha')
        plan = self.ok('install', '--project', str(project))
        self.assertTrue(plan['status'].startswith('PLANNED'))
        self.assertFalse(self.list_path.exists())
        applied = self.ok('install', '--project', str(project), '--apply')
        self.assertEqual('APPLIED', applied['status'])
        self.assertIn('@', (project / 'AGENTS.local.md').read_text())
        self.assertIn('@AGENTS.local.md', (project / 'CLAUDE.local.md').read_text())
        self.assertEqual(0o600, self.list_path.stat().st_mode & 0o777)
        listed = self.ok('list')['projects']
        self.assertEqual([{'id': applied['project']['id'], 'name': 'alpha', 'root': str(project), 'group': None,
                           'capabilities': {'capture': {'enabled': False, 'channel': None},
                                        'search': {'enabled': False, 'alias': None}}}], listed)
        before = self.snapshot(self.list_path, project / 'AGENTS.local.md')
        self.assertEqual('NOOP', self.ok('install', '--project', str(project), '--apply')['status'])
        self.assertEqual(before, self.snapshot(self.list_path, project / 'AGENTS.local.md'))

    def test_input_checks(self):
        project = git_init(self.cf.base / 'alpha')
        self.blocked('install', '--project', str(self.cf.base / 'missing'))
        self.blocked('install', '--project', str(project), '--name', 'bad name')
        self.blocked('install', '--project', str(project), '--capture-credential', str(self.credential('a')))
        sub = project / 'sub'; sub.mkdir()
        self.blocked('install', '--project', str(sub))
        subprocess.run(['/usr/bin/git', '-C', str(project), 'commit', '-q', '--allow-empty', '-m', 'x'],
                       check=True, env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
                                        'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'})
        tree = self.cf.base / 'alpha-wt'
        subprocess.run(['/usr/bin/git', '-C', str(project), 'worktree', 'add', '-q', str(tree)], check=True)
        self.assertIn('worktree', self.blocked('install', '--project', str(tree))['reason'])
        self.blocked('remove', '--project', str(project))

    def test_remove_keeps_owner_text(self):
        project = git_init(self.cf.base / 'alpha')
        (project / 'AGENTS.local.md').write_text('# Owner notes\n\nkeep me\n')
        self.ok('install', '--project', str(project), '--apply')
        self.ok('remove', '--project', str(project), '--apply')
        self.assertEqual('# Owner notes\n\nkeep me\n', (project / 'AGENTS.local.md').read_text())
        self.assertFalse((project / 'CLAUDE.local.md').exists())
        self.assertEqual([], self.ok('list')['projects'])


class UpdateReport(Base):
    """A6: update checks every listed project and reports each one; it repairs nothing and keeps the list bytes."""
    capture = False

    def update(self, *extra):
        cmd = [sys.executable, str(ROOT / 'tools/kit.py'), 'update', '--package', str(self.cf.pkg), '--root', str(self.kit), *extra]
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = json.loads(r.stdout)
        self.assertEqual(1 if out['status'] == 'BLOCKED' else 0, r.returncode, r.stdout + r.stderr)
        return out

    def test_update_reports_each_project_and_repairs_nothing(self):
        roots = [git_init(self.cf.base / n) for n in ('alpha', 'beta', 'gamma')]
        for p in roots: self.ok('install', '--project', str(p), '--apply')
        (roots[1] / 'CLAUDE.local.md').write_text('# imports nothing\n')
        before = self.snapshot(self.list_path, *(p / n for p in roots for n in ('AGENTS.local.md', 'CLAUDE.local.md')))
        plan = self.update()
        self.assertEqual({'alpha', 'beta', 'gamma'}, {r['project'] for r in plan['projects']})
        out = self.update('--execute', '--exclusive-window', '--plan-id', plan['plan_id'])
        self.assertEqual('APPLIED', out['status'], out)
        report = {r['project']: r for r in out['projects']}
        self.assertEqual({'alpha', 'beta', 'gamma'}, set(report))
        self.assertEqual(('OK', 'OK'), (report['alpha']['status'], report['gamma']['status']))
        beta = report['beta']
        self.assertEqual('NEEDS_REPAIR', beta['status'], beta)
        self.assertTrue(any(c['file'] == 'CLAUDE.local.md' for c in beta['changes']), beta)
        self.assertIn('project install', beta['fix']); self.assertIn(str(roots[1]), beta['fix'])
        self.assertEqual(before, self.snapshot(self.list_path, *(p / n for p in roots for n in ('AGENTS.local.md', 'CLAUDE.local.md'))))
        self.assertEqual('OK', {r['project']: r for r in self.update()['projects']}['alpha']['status'])

    def test_missing_root_is_a_problem_and_no_list_means_no_report(self):
        self.assertNotIn('projects', self.update())
        gone = git_init(self.cf.base / 'gone')
        entry = self.ok('install', '--project', str(gone), '--apply')['project']
        subprocess.run(['/bin/rm', '-r', str(gone)], check=True)
        row = self.update()['projects'][0]
        self.assertEqual(('gone', 'PROBLEM'), (row['project'], row['status']), row)
        self.assertIn('does not exist', row['problem']); self.assertIn('project remove', row['fix'])
        self.assertIn(entry['id'], row['fix'])


class WithCapture(Base):
    """Capture registered (and later instructions): the frozen case of T15 (A4, A9, A12, A16)."""

    def migrate(self, *extra):
        out = self.ok('migrate', *extra, '--apply')
        self.assertEqual('APPLIED', out['status'])
        return out

    def second(self, name='beta'):
        return git_init(self.cf.base / name)

    def test_install_refused_before_migration(self):
        self.assertIn('migrate', self.blocked('install', '--project', str(self.second()), '--no-capture')['reason'])

    def test_migration_writes_only_the_list_and_regenerates_mapping_bytes(self):
        settings = self.cf.home / '.claude/settings.json'
        before = self.snapshot(self.mapping, settings)
        plan = self.ok('migrate')
        self.assertEqual([self.cf.spec['projects'][0]['project']], [e['id'] for e in plan['projects']])
        self.assertFalse(self.list_path.exists())
        self.migrate()
        self.assertEqual(before, self.snapshot(self.mapping, settings))
        self.assertEqual(self.mapping.read_bytes(), P.mapping_bytes(P.load(self.kit)))
        self.assertEqual('NOOP', self.ok('migrate', '--apply')['status'])
        listed = json.dumps(self.ok('list'))
        for key in ('credential_file', 'queue_dir', 'status_file'):
            self.assertNotIn(self.cf.spec['projects'][0][key], listed)

    def test_add_then_remove_project_with_capture(self):
        self.migrate()
        original = self.mapping.read_bytes()
        project = self.second()
        self.blocked('install', '--project', str(project))  # capture default needs a credential or --no-capture
        out = self.ok('install', '--project', str(project), '--capture-credential', str(self.credential('beta')), '--apply')
        rows = json.loads(self.mapping.read_text())['projects']
        self.assertEqual([self.cf.spec['projects'][0]['root'], str(project)], [r['root'] for r in rows])
        self.assertEqual('claude-code-beta', rows[1]['source_instance'])
        self.assertEqual(out['project']['id'], rows[1]['project'])
        # A normal kit update after the scope change still plans and applies (no frozen scope).
        self.cf.release('3')
        self.assertEqual('APPLIED', self.cf.apply(False)['status'])
        self.ok('remove', '--project', str(project), '--apply')
        self.assertEqual(original, self.mapping.read_bytes())
        self.assertEqual('NOOP', self.cf.plan(False)['status'])

    def test_mapping_edit_outside_the_kit_blocks(self):
        self.migrate()
        self.mapping.write_bytes(self.mapping.read_bytes() + b'\n')
        self.assertIn('outside', self.blocked('install', '--project', str(self.second()), '--no-capture')['reason'])

    def test_failure_restores_every_file(self):
        self.migrate()
        project = self.second()
        files = [self.mapping, self.list_path, project / 'AGENTS.local.md', project / 'CLAUDE.local.md', project / '.gitignore']
        before = self.snapshot(*files)
        P.FAULT = ('before-list', ValueError('injected'))
        self.blocked('install', '--project', str(project), '--capture-credential', str(self.credential('beta')), '--apply')
        self.assertEqual(before, self.snapshot(*files))
        self.assertFalse((self.kit / k.STATE / P.MARKER).exists())

    def test_killed_write_is_restored_by_next_command(self):
        self.migrate()
        project = self.second()
        files = [self.mapping, self.list_path, project / 'AGENTS.local.md', project / 'CLAUDE.local.md', project / '.gitignore']
        before = self.snapshot(*files)
        P.FAULT = ('before-list', Killed())
        with self.assertRaises(Killed):
            self.run_cli('install', '--project', str(project), '--capture-credential', str(self.credential('beta')), '--apply')
        P.FAULT = None
        self.assertNotEqual(before, self.snapshot(*files))
        self.assertIn('interrupted', self.ok('list'))
        out = self.ok('install', '--project', str(project), '--no-capture', '--apply')
        self.assertIn('restored_first', out)
        self.assertEqual(before[str(self.mapping)], self.mapping.read_bytes())

    def test_failure_at_each_step_restores(self):
        self.migrate()
        project = self.second()
        files = [self.mapping, self.list_path, project / 'AGENTS.local.md', project / 'CLAUDE.local.md', project / '.gitignore']
        before = self.snapshot(*files)
        for step in ('before-connect', 'before-mapping', 'before-clear'):
            P.FAULT = (step, ValueError('injected'))
            self.blocked('install', '--project', str(project), '--capture-credential', str(self.credential('beta')), '--apply')
            self.assertEqual(before, self.snapshot(*files), step)

    def test_reinstall_keeps_existing_route(self):
        self.migrate()
        project = self.second(); cred = str(self.credential('beta'))
        self.ok('install', '--project', str(project), '--capture-credential', cred, '--source-instance', 'custom-beta', '--apply')
        mapping = self.mapping.read_bytes()
        self.assertEqual('NOOP', self.ok('install', '--project', str(project), '--capture-credential', cred, '--apply')['status'])
        self.assertEqual(mapping, self.mapping.read_bytes())

    def test_project_local_hook_is_inventoried_not_rerouted(self):
        project = self.second()
        hook = shlex.join(['sh', str(self.kit / 'runtime/storage/deploy/capture-bridge/claude-code-stop-hook.sh')])
        command = 'AF_CAPTURE_PROJECT=33333333-3333-4333-8333-333333333333 AF_CAPTURE_SOURCE=x ' + hook
        (project / '.claude').mkdir()
        (project / '.claude/settings.local.json').write_text(json.dumps(
            {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': command}]}]}}))
        out = self.migrate('--include-root', str(project))
        entry = [e for e in out['projects'] if e['root'] == str(project)][0]
        self.assertEqual('33333333-3333-4333-8333-333333333333', entry['id'])
        self.assertEqual({'enabled': True, 'channel': 'project-local'}, entry['capabilities']['capture'])
        self.assertEqual(1, len(json.loads(self.mapping.read_text())['projects']))
        self.blocked('install', '--project', str(project), '--capture-credential', str(self.credential('beta')))

    def test_migration_conflicts_stop_before_writing(self):
        self.blocked('migrate', '--include-root', str(self.cf.base / 'missing'), '--apply')
        self.assertFalse(self.list_path.exists())


class WithInstructions(unittest.TestCase):
    """Instructions and capture registered: the 5 freeze probes now have a supported path (A4)."""

    def setUp(self):
        self.ci = instructions.CaptureInstructionTests('test_combined_capture_no_hook_change_and_rollback')
        self.ci.setUp(); self.addCleanup(self.ci.doCleanups)
        self.assertEqual('APPLIED', self.ci.apply()['status'])
        self.cf = self.ci.cf; self.kit = self.cf.root

    def cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            P.main([argv[0], '--root', str(self.kit), *argv[1:]])
        return json.loads(buf.getvalue())

    def test_add_and_remove_project_while_instructions_registered(self):
        out = self.cli('migrate', '--include-root', str(self.ci.project), '--apply')
        self.assertEqual('APPLIED', out['status'], out)
        marked = [e for e in out['projects'] if e['root'] == str(self.ci.project)][0]
        self.assertEqual(['retired-recipe'], marked['history'])
        project = git_init(self.cf.base / 'beta')
        cred = self.cf.private / 'beta.cred.json'; cred.write_text('{}'); cred.chmod(0o600)
        self.assertEqual('APPLIED', self.cli('install', '--project', str(project), '--capture-credential', str(cred), '--apply')['status'])
        self.assertEqual(2, len(json.loads(Path(self.cf.spec['mapping_path']).read_text())['projects']))
        # The outer instruction update is not asked to change capture, so it does not refuse.
        self.assertEqual('NOOP', self.ci.plan()['status'])
        self.assertEqual('APPLIED', self.cli('remove', '--project', str(project), '--apply')['status'])
        self.assertEqual(1, len(json.loads(Path(self.cf.spec['mapping_path']).read_text())['projects']))


class Dispatcher(unittest.TestCase):
    def test_empty_mapping_is_valid(self):
        self.assertEqual([], D.validate_mapping({'schema': 1, 'projects': []}))

    def test_worktree_routes_to_main_checkout(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            main = git_init(base / 'main')
            env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
                   'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
            subprocess.run(['/usr/bin/git', '-C', str(main), 'commit', '-q', '--allow-empty', '-m', 'x'], check=True, env=env)
            tree = base / 'tree'
            subprocess.run(['/usr/bin/git', '-C', str(main), 'worktree', 'add', '-q', str(tree)], check=True)
            rows = [{'root': str(main), 'project': 'p'}]
            self.assertEqual(rows[0], D.select_route(rows, str(tree)))
            self.assertEqual(rows[0], D.select_route(rows, str(main)))
            self.assertIsNone(D.select_route(rows, str(git_init(base / 'other'))))


if __name__ == '__main__':
    unittest.main()
