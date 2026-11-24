"""T30: `kit.py move` re-points a kit with capture, instructions and a listed project to K2, and rolls back.

Disposable fixtures only (the shared capture + instruction fixtures); no host files.
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


instructions = load('move_instruction_fixture', ROOT / 'tests/install/test_instruction_update.py')
M = load('kit_move_under_test', ROOT / 'tools/kit_move.py')


class Move(unittest.TestCase):
    def setUp(self):
        self.ci = instructions.CaptureInstructionTests('test_combined_capture_no_hook_change_and_rollback')
        self.ci.setUp(); self.addCleanup(self.ci.doCleanups)
        self.assertEqual('APPLIED', self.ci.apply()['status'])
        self.cf = self.ci.cf; self.k = self.ci.ck
        self.old = self.cf.root; self.new = self.cf.home / 'kit2'
        p = self.k.plan(self.cf.pkg, self.new, []); self.k.apply(self.cf.pkg, self.new, [], p['plan_id'])
        M.MODULES.clear(); M.MODULES['instruction_update.py'] = instructions.u
        self.addCleanup(M.MODULES.clear); self.addCleanup(setattr, M, 'FAULT', None)
        skills = self.cf.home / '.claude/skills'; skills.mkdir(parents=True)
        (self.old / 'skills').mkdir(exist_ok=True); (self.new / 'skills').mkdir(exist_ok=True)
        os.symlink(str(self.old / 'skills/alpha'), skills / 'alpha')
        self.link = skills / 'alpha'

    def tracked(self):
        files = [self.cf.home / '.claude/settings.json', self.ci.target,
                 self.cf.home / '.agents/.ai-factory-instructions/owner.json',
                 Path(self.cf.spec['registration_root']) / '.ai-factory-state/current.json']
        return {str(f): (f.read_bytes() if f.exists() else None) for f in files} | {'link': os.readlink(self.link)}

    def names_old(self, snapshot):
        return [n for n, v in snapshot.items() if v is not None and str(self.old) + '/' in (v if isinstance(v, str) else v.decode())]

    def test_move_then_rollback(self):
        before = self.tracked()
        self.assertTrue(self.names_old(before))
        dry = M.build(self.old, self.new, self.cf.pkg)
        self.assertEqual([], dry.blockers)
        out = M.apply(self.old, self.new, self.cf.pkg)
        self.assertEqual('APPLIED', out['status'], out)
        after = self.tracked()
        self.assertEqual([], self.names_old(after))
        self.assertEqual(str(self.new / 'skills/alpha'), after['link'])
        self.assertEqual({'schema': 1, 'root': str(self.new)},
                         json.loads((self.cf.home / '.agents/.ai-factory-instructions/owner.json').read_text()))
        self.assertEqual('NOOP', instructions.u.plan(self.k, self.cf.pkg, self.new, [])['status'])
        self.assertFalse((self.old / self.k.STATE / M.MARKER).exists())
        back = M.rollback(self.new)
        self.assertEqual('ROLLED_BACK', back['status'], back)
        self.assertEqual(before, self.tracked())
        self.assertEqual('NOOP', instructions.u.plan(self.k, self.cf.pkg, self.old, [])['status'])

    def test_failure_at_each_step_restores_everything(self):
        before = self.tracked()
        for step in ('settings.json', 'owner.json', 'current.json', 'link', 'verify'):
            M.FAULT = (step, ValueError('injected'))
            out = M.apply(self.old, self.new, self.cf.pkg)
            self.assertEqual('BLOCKED', out['status'], step)
            self.assertNotIn('not_restored', out, step)
            self.assertEqual(before, self.tracked(), step)
            for root in (self.old, self.new):
                self.assertFalse((root / self.k.STATE / M.MARKER).exists(), step)
        M.FAULT = None
        self.assertEqual('APPLIED', M.apply(self.old, self.new, self.cf.pkg)['status'])

    def test_killed_move_is_recovered_from_either_root(self):
        before = self.tracked()

        class Killed(BaseException):
            pass
        for root in ('old', 'new'):
            M.FAULT = ('owner.json', Killed())
            with self.assertRaises(Killed):
                M.apply(self.old, self.new, self.cf.pkg)
            M.FAULT = None
            for r in (self.old, self.new):
                self.assertTrue((r / self.k.STATE / M.MARKER).exists())
            self.assertEqual('RESTORED', M.recover(getattr(self, root))['status'])
            self.assertEqual(before, self.tracked(), root)
            for r in (self.old, self.new):
                self.assertFalse((r / self.k.STATE / M.MARKER).exists())

    def test_refusals_before_any_write(self):
        before = self.tracked()
        self.assertTrue(M.build(self.old, self.old / 'nested', self.cf.pkg).blockers)
        (self.new / self.k.STATE / 'pending.json').write_text('{}')
        self.assertTrue(any('unfinished' in b for b in M.build(self.old, self.new, self.cf.pkg).blockers))
        (self.new / self.k.STATE / 'pending.json').unlink()
        settings = self.cf.home / '.claude/settings.json'
        doc = json.loads(settings.read_bytes()); doc['permissions'] = {'defaultMode': 'bypassPermissions'}
        settings.write_bytes(json.dumps(doc).encode())  # drift from the capture record (C6: permissions are pinned)
        blocked = M.build(self.old, self.new, self.cf.pkg).blockers
        self.assertTrue(any('drift' in b for b in blocked), blocked)
        settings.write_bytes(before[str(settings)])
        self.assertEqual(before, self.tracked())


if __name__ == '__main__':
    unittest.main()


handoff = load('move_handoff_fixture', ROOT / 'tests/connect-handoff/test_connect_handoff.py')


class MoveHandoff(unittest.TestCase):
    """Native handoff for Claude and Codex, kit path that shlex must quote."""

    def setUp(self):
        self.h = handoff.RegistrationTests('test_read_only_apply_repeat_noop_and_exact_rollback')
        self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.assertEqual('APPLIED', self.h.apply()['status'])
        self.k = handoff.k
        self.old = self.h.root; self.new = self.h.base / 'kit two'
        p = self.k.plan(self.h.package, self.new); self.k.apply(self.h.package, self.new, [], p['plan_id'])
        state = self.old / self.k.STATE
        (state / 'handoff.json').write_bytes(self.k.encode({'profile': self.h.spec['profile_path']})); (state / 'handoff.json').chmod(0o600)
        M.MODULES.clear(); self.addCleanup(M.MODULES.clear)
        self.reg = Path(self.h.spec['registration_root'])

    def files(self):
        names = [self.h.config('claude'), self.h.config('codex'), Path(self.h.spec['profile_path']), self.reg / '.ai-factory-state/current.json']
        return {str(n): n.read_bytes() for n in names}

    def test_handoff_needs_its_registration_root(self):
        self.assertTrue(any('--handoff-registration' in b for b in M.build(self.old, self.new, self.h.package).blockers))

    def test_handoff_move_and_rollback(self):
        before = self.files()
        out = M.apply(self.old, self.new, self.h.package, self.reg)
        self.assertEqual('APPLIED', out['status'], out)
        self.assertIn('trust them again in Codex', ' '.join(out['notes']))
        after = self.files()
        for name, raw in after.items():
            self.assertNotIn(str(self.old) + '/', raw.decode(), name)
        rec = self.k.read_tx(self.reg / '.ai-factory-state/current.json')
        self.assertEqual('NOOP', handoff.c.plan(rec['spec'])['status'])
        self.assertEqual('ROLLED_BACK', M.rollback(self.new)['status'])
        self.assertEqual(before, self.files())


projects_fixture = load('move_projects_fixture', ROOT / 'tests/projects/test_projects.py')


class MoveProjects(projects_fixture.Base):
    """A listed project with capture: its managed block and the list follow the kit; kit.py refuses while interrupted."""

    def setUp(self):
        super().setUp()
        self.ok('migrate', '--apply')
        self.project = projects_fixture.git_init(self.cf.base / 'alpha')
        self.ok('install', '--project', str(self.project), '--capture-credential', str(self.credential('alpha')), '--apply')
        self.k = projects_fixture.k
        self.old = self.kit; self.new = self.cf.home / 'kit2'
        p = self.k.plan(self.cf.pkg, self.new, []); self.k.apply(self.cf.pkg, self.new, [], p['plan_id'])
        M.MODULES.clear(); self.addCleanup(M.MODULES.clear); self.addCleanup(setattr, M, 'FAULT', None)

    def test_project_block_and_list_follow_and_roll_back(self):
        agents = self.project / 'AGENTS.local.md'; before = agents.read_bytes()
        self.assertIn(str(self.old) + '/', before.decode())
        out = M.apply(self.old, self.new, self.cf.pkg)
        self.assertEqual('APPLIED', out['status'], out)
        self.assertNotIn(str(self.old) + '/', agents.read_text())
        self.assertIn(('alpha', 'OK'), [(r['project'], r['status']) for r in projects_fixture.P.check_projects(self.new)])
        self.assertEqual('ROLLED_BACK', M.rollback(self.new)['status'])
        self.assertEqual(before, agents.read_bytes())

    def test_rollback_refuses_a_file_changed_after_the_move(self):
        self.assertEqual('APPLIED', M.apply(self.old, self.new, self.cf.pkg)['status'])
        agents = self.project / 'AGENTS.local.md'; agents.write_text(agents.read_text() + 'owner edit\n')
        out = M.rollback(self.new)
        self.assertEqual('BLOCKED', out['status']); self.assertIn('AGENTS.local.md', out['reason'])
        self.assertIn('owner edit', agents.read_text())

    def test_kit_commands_refuse_while_a_move_is_interrupted(self):
        class Killed(BaseException):
            pass
        M.FAULT = ('AGENTS.local.md', Killed())
        with self.assertRaises(Killed):
            M.apply(self.old, self.new, self.cf.pkg)
        M.FAULT = None
        import subprocess
        r = subprocess.run([sys.executable, '-I', str(ROOT / 'tools/kit.py'), 'project', 'list', '--root', str(self.old)],
                           capture_output=True, text=True)
        self.assertEqual(1, r.returncode); self.assertIn('--recover', r.stdout)
        r = subprocess.run([sys.executable, '-I', str(ROOT / 'tools/kit.py'), 'plan', '--root=' + str(self.new), '--package', str(self.cf.pkg)],
                           capture_output=True, text=True)
        self.assertEqual(1, r.returncode); self.assertIn('--recover', r.stdout)  # the --root=VALUE form too
        self.assertEqual('RESTORED', M.recover(self.new)['status'])


class OneKitPerHome(unittest.TestCase):
    """T30 A6: connect-handoff and connect-skills refuse a home bound to another kit."""

    def bind(self, home, root):
        d = home / '.agents/.ai-factory-instructions'; d.mkdir(parents=True); d.chmod(0o700)
        (d / 'owner.json').write_text(json.dumps({'schema': 1, 'root': str(root)})); (d / 'owner.json').chmod(0o600)

    def test_handoff_refuses_another_kits_home(self):
        h = handoff.RegistrationTests('test_read_only_apply_repeat_noop_and_exact_rollback'); h.setUp(); self.addCleanup(h.doCleanups)
        self.bind(h.home, h.base / 'first-kit')
        with self.assertRaises(ValueError) as cm:
            handoff.c.plan(h.spec)
        self.assertIn('first-kit', str(cm.exception))
        self.assertFalse(h.config('claude').exists())

    def test_skills_script_refuses_another_kits_home(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as t:
            home = Path(t).resolve() / 'home'; (home / '.claude/skills').mkdir(parents=True)
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(home)}
            script = ROOT / 'tools/connect-skills.sh'
            self.bind(home, Path(t).resolve() / 'first-kit')
            r = subprocess.run(['/bin/sh', str(script), '--dry-run', str(home / '.claude/skills')], env=env, capture_output=True, text=True)
            self.assertEqual(3, r.returncode, r.stdout + r.stderr); self.assertIn('first-kit', r.stderr)
            (home / '.agents/.ai-factory-instructions/owner.json').write_text(json.dumps({'schema': 1, 'root': str(ROOT)}))
            r = subprocess.run(['/bin/sh', str(script), '--dry-run', str(home / '.claude/skills')], env=env, capture_output=True, text=True)
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
            self.assertEqual([], list((home / '.claude/skills').iterdir()))  # dry run


archive_fixture = load('move_archive_fixture', ROOT / 'tests/projects/test_project_archive.py')


@unittest.skipUnless(archive_fixture.GO, 'Go toolchain is not available')
class MoveArchive(archive_fixture.Archive):
    """An archive-enrolled project with a launchd worker: plist, contract and routes follow; the worker is reloaded."""

    def test_worker_plist_contract_follow_and_reload(self):
        self.configure()
        project, out = self.install()
        self.assertEqual('APPLIED', out['status'], out)
        k = archive_fixture.k
        new = self.cf.home / 'kit2'
        p = k.plan(self.cf.pkg, new, []); k.apply(self.cf.pkg, new, [], p['plan_id'])
        M.MODULES.clear(); self.addCleanup(M.MODULES.clear)
        M.LAUNCHCTL = str(self.fake / 'launchctl'); self.addCleanup(setattr, M, 'LAUNCHCTL', None)
        plist = next(self.agents.glob('*.plist')); before = plist.read_bytes()
        calls = len(self.calls())
        out = M.apply(self.kit, new, self.cf.pkg)
        self.assertEqual('APPLIED', out['status'], out)
        self.assertNotIn(str(self.kit) + '/', plist.read_text())
        self.assertIn(str(new / archive_fixture.A.BRIDGE), plist.read_text())
        self.assertEqual(['reloaded'], [w['status'] for w in out['workers']])
        self.assertTrue(any(c.startswith('bootstrap') for c in self.calls()[calls:]))
        self.assertTrue((new / 'runtime/storage/deploy/search-client/search-routes.json').exists())
        self.assert_no_secret(out)
        self.assertEqual('ROLLED_BACK', M.rollback(new)['status'])
        self.assertEqual(before, plist.read_bytes())


capture_fixture = load('move_capture_fixture', ROOT / 'tests/install/test_capture_update.py')


class MoveBareKit(unittest.TestCase):
    """Boundary: nothing registered, no project list, no home named by a registration."""

    def test_bare_kit_moves_and_names_what_it_did_not_look_at(self):
        cf = capture_fixture.UpdateTests('test_explicit_registration_normal_update_and_idempotence'); cf.setUp(); self.addCleanup(cf.doCleanups)
        k = capture_fixture.k
        p = k.plan(cf.pkg, cf.root, []); k.apply(cf.pkg, cf.root, [], p['plan_id'])
        new = cf.home / 'kit2'; p = k.plan(cf.pkg, new, []); k.apply(cf.pkg, new, [], p['plan_id'])
        M.MODULES.clear(); self.addCleanup(M.MODULES.clear)
        out = M.apply(cf.root, new, cf.pkg)
        self.assertEqual('APPLIED', out['status'], out)
        self.assertEqual([], out['files'])
        self.assertIn('pass --home', ' '.join(out['notes']))
        self.assertEqual('ROLLED_BACK', M.rollback(new)['status'])

    def test_different_release_is_refused(self):
        cf = capture_fixture.UpdateTests('test_explicit_registration_normal_update_and_idempotence'); cf.setUp(); self.addCleanup(cf.doCleanups)
        k = capture_fixture.k
        new = cf.home / 'kit2'; p = k.plan(cf.pkg, new, []); k.apply(cf.pkg, new, [], p['plan_id'])  # K holds release 1
        M.MODULES.clear(); self.addCleanup(M.MODULES.clear)
        self.assertTrue(any('different release' in b for b in M.build(cf.root, new, cf.pkg).blockers))


for _name in dir(archive_fixture.Archive):  # run only the move case, not the inherited archive suite again
    if _name.startswith('test_') and _name not in vars(MoveArchive):
        setattr(MoveArchive, _name, None)
