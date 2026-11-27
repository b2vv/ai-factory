"""Dashboard publish reminder (T36): the Stop hook script and its registration by `project dashboard`.

Disposable fixtures only: temporary Git repos, a temporary kit state and a temporary home. No host settings.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'tools/dashboard_reminder.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load('reminder_projects_base', ROOT / 'tests/projects/test_projects.py')
P, k, git_init = T.P, T.k, T.git_init
GIT_ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid', 'GIT_COMMITTER_NAME': 't',
           'GIT_COMMITTER_EMAIL': 't@example.invalid'}


def commit(repo):
    subprocess.run(['/usr/bin/git', '-C', str(repo), 'commit', '-q', '--allow-empty', '-m', 'c'], check=True, env=GIT_ENV)
    return subprocess.run(['/usr/bin/git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, env=GIT_ENV,
                          capture_output=True, text=True).stdout.strip()


def claude_event(cwd, active=False):
    return {'session_id': 's1', 'transcript_path': '/example/t.jsonl', 'cwd': str(cwd), 'hook_event_name': 'Stop',
            'stop_hook_active': active}


def codex_event(cwd, active=False):
    return {'session_id': 's1', 'transcript_path': None, 'cwd': str(cwd), 'hook_event_name': 'Stop', 'model': 'm',
            'turn_id': 't1', 'stop_hook_active': active, 'last_assistant_message': 'done', 'permission_mode': 'default'}


class Hook(unittest.TestCase):
    """Acceptance 1-4: silent unless a dashboard project's HEAD moved; once per HEAD; fail-open."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.kit = self.base / 'kit'; self.state = self.kit / '.ai-factory-state'; self.state.mkdir(parents=True, mode=0o700)
        self.alpha = git_init(self.base / 'alpha'); self.head = commit(self.alpha)
        self.other = git_init(self.base / 'other'); commit(self.other)
        self.feed = self.base / 'feed'; self.feed.mkdir(mode=0o700)
        self.projects = self.base / 'dashboard-projects.json'
        self.projects.write_text(json.dumps([{'id': 'alpha', 'name': 'Alpha', 'root': str(self.alpha)}]))
        self.configure()

    def configure(self):
        cfg = self.state / 'dashboard.json'
        cfg.write_text(json.dumps({'schema': 1, 'source': '/example/src', 'projects': str(self.projects),
                                   'feed': str(self.feed), 'go': '/example/go'})); cfg.chmod(0o600)

    def publish(self, revision):
        (self.feed / 'alpha.json').write_text(json.dumps({'schema': 'factory-dashboard/status/1', 'project': 'alpha',
                                                          'revision': revision, 'title': 'Private record title'}))

    def hook(self, event, host='claude', raw=None):
        data = raw if raw is not None else json.dumps(event).encode()
        r = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), '--kit', str(self.kit), '--host', host],
                           input=data, capture_output=True, timeout=30)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(b'', r.stderr)
        return r.stdout.decode()

    def blocks(self, out):
        lines = out.splitlines()
        self.assertEqual(1, len(lines), out)
        doc = json.loads(lines[0])
        self.assertEqual({'decision', 'reason'}, set(doc)); self.assertEqual('block', doc['decision'])
        return doc['reason']

    def test_1_silent_outside_the_dashboard(self):
        self.assertEqual('', self.hook(claude_event(self.other)))           # not a dashboard project
        self.assertEqual('', self.hook(claude_event(self.base)))            # not a Git checkout
        (self.state / 'dashboard.json').unlink()
        self.assertEqual('', self.hook(claude_event(self.alpha)))           # no dashboard on this host
        self.assertFalse((self.state / 'dashboard-reminded.json').exists())

    def test_2_silent_when_head_is_published(self):
        self.publish(self.head)
        self.assertEqual('', self.hook(claude_event(self.alpha)))
        sub = self.alpha / 'sub'; sub.mkdir()
        self.assertEqual('', self.hook(claude_event(sub)))                  # a subdirectory resolves to the Git root

    def test_3_once_per_head(self):
        self.publish(self.head)
        new = commit(self.alpha)
        reason = self.blocks(self.hook(claude_event(self.alpha)))
        self.assertIn(new[:12], reason); self.assertIn(self.head[:12], reason)
        self.assertNotIn(new, reason)                                       # short hashes only
        self.assertIn('kit.py project status', reason); self.assertIn('why no publish is needed', reason)
        self.assertNotIn('Private record title', reason); self.assertNotIn(str(self.base), reason)
        self.assertEqual(0o600, (self.state / 'dashboard-reminded.json').stat().st_mode & 0o777)
        self.assertEqual('', self.hook(claude_event(self.alpha)))           # same HEAD: silent
        newer = commit(self.alpha)
        self.assertIn(newer[:12], self.blocks(self.hook(claude_event(self.alpha))))
        self.assertEqual('', self.hook(claude_event(self.alpha)))

    def test_3_never_published_counts_as_moved(self):
        self.assertIn('never published', self.blocks(self.hook(claude_event(self.alpha))))

    def test_4_continued_stop_and_bad_input_are_silent(self):
        self.assertEqual('', self.hook(claude_event(self.alpha, active=True)))
        self.assertEqual('', self.hook(None, raw=b'{nope'))
        self.assertEqual('', self.hook(None, raw=b'[]'))
        self.assertEqual('', self.hook({'cwd': 'relative/path', 'stop_hook_active': False}))
        self.assertEqual('', self.hook({'cwd': str(self.alpha), 'stop_hook_active': 'yes'}))
        (self.state / 'dashboard.json').write_text('{broken')
        self.assertEqual('', self.hook(claude_event(self.alpha)))
        self.configure(); self.projects.write_text('not json')
        self.assertEqual('', self.hook(claude_event(self.alpha)))
        self.assertFalse((self.state / 'dashboard-reminded.json').exists())

    def test_4_unreadable_state_is_silent(self):
        self.publish('b' * 40)
        (self.state / 'dashboard-reminded.json').write_text('{}'); (self.state / 'dashboard-reminded.json').chmod(0)
        self.addCleanup((self.state / 'dashboard-reminded.json').chmod, 0o600)
        if os.access(self.state / 'dashboard-reminded.json', os.R_OK): self.skipTest('running with read access to mode 000')
        self.assertEqual('', self.hook(claude_event(self.alpha)))

    def test_codex_shape(self):
        """Codex Stop input carries turn_id/last_assistant_message; Stop output must be JSON only (no plain text)."""
        self.assertEqual('', self.hook(codex_event(self.alpha, active=True), host='codex'))
        reason = self.blocks(self.hook(codex_event(self.alpha), host='codex'))
        self.assertIn('alpha', reason)
        self.assertNotIn('done', reason)                                    # no assistant text is echoed
        self.assertEqual('', self.hook(claude_event(self.alpha)))           # one reminder per HEAD across hosts


class Registration(T.Base):
    """Acceptance 5: `project dashboard --apply` registers the Stop hook for Claude and Codex; reruns NOOP."""

    def setUp(self):
        super().setUp()
        self.home = Path(self.cf.spec['home'])
        shutil.copy(SCRIPT, self.kit / P.REMINDER)
        self.project = git_init(self.cf.base / 'alpha')
        self.projects = self.cf.base / 'dash-projects.json'
        self.projects.write_text(json.dumps([{'id': 'alpha', 'name': 'Alpha', 'root': str(self.project)}]))
        self.feed = self.cf.base / 'feed'; self.feed.mkdir(mode=0o700)
        cfg = {'schema': 1, 'source': str(self.cf.base), 'projects': str(self.projects), 'feed': str(self.feed), 'go': '/example/go'}
        # The Go-backed config validation is covered by test_project_dashboard.py; here it is a fixed stub.
        for name, value in (('build_config', lambda args: cfg), ('validate_projects', lambda c: {'alpha': str(self.project)})):
            old = getattr(P.DB, name); setattr(P.DB, name, value); self.addCleanup(setattr, P.DB, name, old)
        self.settings = self.home / '.claude/settings.json'
        doc = json.loads(self.settings.read_text())
        doc['hooks']['PreToolUse'] = [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'owner-guard'}]}]
        doc['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': 'owner-stop'}]})
        doc['permissions'] = {'allow': ['Bash(ls:*)'], 'deny': []}
        doc['model'] = 'owner-choice'
        self.settings.write_bytes(k.encode(doc))
        self.codex = self.home / '.codex/hooks.json'; self.codex.parent.mkdir()
        self.codex.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'owner-codex'}]}]}}))
        self.before = {p: p.read_bytes() for p in (self.settings, self.codex)}
        self.record = self.kit / k.STATE / P.REMINDER_REG

    def dash(self, *extra):
        return self.run_cli('dashboard', '--source', 'x', '--projects', 'x', '--feed', 'x', *extra)

    def own(self, path):
        return [h for g in json.loads(path.read_text())['hooks'].get('Stop', []) for h in g['hooks']
                if P.REMINDER in h['command']]

    def without_own(self, path):
        doc = json.loads(path.read_text())
        doc['hooks']['Stop'] = [g for g in doc['hooks']['Stop'] if not any(P.REMINDER in h['command'] for h in g['hooks'])]
        return doc

    def test_5_register_rerun_noop_and_owner_content_kept(self):
        plan = self.dash()
        self.assertTrue(plan['status'].startswith('PLANNED'))
        self.assertEqual({'claude': 'register', 'codex': 'register'}, {h: v['hook'] for h, v in plan['reminder']['hosts'].items()})
        self.assertEqual(self.before, {p: p.read_bytes() for p in self.before})  # dry-run writes nothing
        self.assertFalse(self.record.exists())
        out = self.dash('--apply')
        self.assertEqual('APPLIED', out['status'], out)
        self.assertIn('--no-reminder', out['reminder']['remove_with'])
        self.assertIn('never writes Codex trust', out['reminder']['codex_trust'])
        for path, host in ((self.settings, 'claude'), (self.codex, 'codex')):
            own = self.own(path)
            self.assertEqual(1, len(own))
            self.assertEqual(15, own[0]['timeout'])
            self.assertTrue(own[0]['command'].endswith(f'--kit {self.kit} --host {host}'))
            # Codex lists hooks for trust review by label; Claude gets none.
            self.assertEqual('AI Factory dashboard reminder' if host == 'codex' else None, own[0].get('statusMessage'))
            self.assertEqual(json.loads(self.before[path]), self.without_own(path))  # everything else kept, same order
        stops = json.loads(self.settings.read_text())['hooks']['Stop']
        self.assertIn('owner-stop', json.dumps(stops[-2]))                     # appended after existing hooks
        self.assertEqual(0o600, self.record.stat().st_mode & 0o777)
        self.assertNotIn('trust', self.codex.read_text())
        after = {p: p.read_bytes() for p in (self.settings, self.codex, self.record)}
        again = self.dash('--apply')
        self.assertEqual('NOOP', again['status'], again)
        self.assertEqual({'claude': 'registered', 'codex': 'registered'}, {h: v['hook'] for h, v in again['reminder']['hosts'].items()})
        self.assertEqual(after, {p: p.read_bytes() for p in after})
        # The capture registration's own pin (its hook + the permissions section) is unchanged by the reminder.
        cc = load('reminder_connect_capture', ROOT / 'tools/connect-capture.py')
        raw = self.settings.read_bytes()
        self.assertTrue(cc.own_hook_present(raw, cc.command(cc.validate_spec(self.cf.spec))))
        self.assertEqual(cc.permissions_digest(self.before[self.settings]), cc.permissions_digest(raw))

    def test_5_owner_edits_elsewhere_keep_noop_and_bytes(self):
        self.dash('--apply')
        doc = json.loads(self.settings.read_text()); doc['model'] = 'changed-by-owner'
        raw = json.dumps(doc, indent=4).encode(); self.settings.write_bytes(raw)
        self.assertEqual('NOOP', self.dash('--apply')['status'])
        self.assertEqual(raw, self.settings.read_bytes())

    def test_5_remove_restores_owner_content(self):
        self.codex.unlink(); self.before.pop(self.codex)
        self.dash('--apply')
        self.assertEqual(1, len(self.own(self.codex)))
        out = self.dash('--no-reminder', '--apply')
        self.assertEqual('APPLIED', out['status'], out)
        self.assertEqual(json.loads(self.before[self.settings]), json.loads(self.settings.read_text()))
        self.assertFalse(self.codex.exists())                                 # created by the kit, removed with it
        self.assertFalse(self.record.exists())
        self.assertEqual('NOOP', self.dash('--no-reminder', '--apply')['status'])

    def test_5_drift_and_collision_block(self):
        self.dash('--apply')
        doc = json.loads(self.settings.read_text())
        doc['permissions']['allow'].append('Bash(rm:*)'); self.settings.write_bytes(k.encode(doc))
        self.assertIn('permissions', self.dash('--apply')['reason'])
        self.assertEqual('APPLIED', self.dash('--no-reminder', '--apply')['status'])   # removal stays possible
        self.assertEqual([], self.own(self.settings))
        doc = json.loads(self.codex.read_text())
        doc['hooks']['Stop'].append({'hooks': [P.reminder_handler(P.reminder_command(self.kit, 'codex'))]})
        self.codex.write_text(json.dumps(doc))
        self.assertIn('did not register', self.dash('--apply')['reason'])

    def test_5_changed_own_hook_blocks(self):
        self.dash('--apply')
        doc = json.loads(self.settings.read_text())
        for g in doc['hooks']['Stop']:
            for h in g['hooks']:
                if P.REMINDER in h['command']: h['timeout'] = 99
        self.settings.write_bytes(k.encode(doc))
        self.assertIn('was changed', self.dash('--apply')['reason'])

    def test_failed_write_restores_every_file(self):
        P.FAULT = ('before-reminder-record', RuntimeError('fault'))
        with self.assertRaises(RuntimeError): self.dash('--apply')
        P.FAULT = None
        self.assertEqual(self.before, {p: p.read_bytes() for p in self.before})
        self.assertFalse(self.record.exists())
        self.assertFalse((self.kit / k.STATE / 'dashboard.json').exists())

    def test_install_does_not_register(self):
        self.ok('migrate', '--apply')
        self.ok('install', '--project', str(self.project), '--no-capture', '--apply')
        self.assertEqual(self.before, {p: p.read_bytes() for p in self.before})
        self.assertFalse(self.record.exists())


class NoNamedHome(T.Base):
    """Without a registration naming the home (and no --home), nothing outside the kit is written."""
    capture = False

    def test_skipped_with_note(self):
        projects = self.cf.base / 'p.json'; projects.write_text('[]')
        cfg = {'schema': 1, 'source': 'x', 'projects': str(projects), 'feed': 'x', 'go': '/example/go'}
        for name, value in (('build_config', lambda args: cfg), ('validate_projects', lambda c: {})):
            old = getattr(P.DB, name); setattr(P.DB, name, value); self.addCleanup(setattr, P.DB, name, old)
        out = self.run_cli('dashboard', '--source', 'x', '--projects', 'x', '--feed', 'x', '--apply')
        self.assertEqual('APPLIED', out['status'], out)
        self.assertEqual({}, out['reminder']['hosts'])
        self.assertIn('--home', out['reminder']['note'])
        self.assertFalse((self.kit / k.STATE / P.REMINDER_REG).exists())


if __name__ == '__main__':
    unittest.main()
