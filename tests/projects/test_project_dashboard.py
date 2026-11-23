"""Dashboard status publishing via `kit.py project dashboard|status` (T23 Part B).

Runs the real dashboard publisher (runtime/dashboard, `go run -tags nobundle`) against a
temporary project with a real commit and a private feed. Skipped without Go.
"""
import importlib.util
import io
import json
import time
import os
from pathlib import Path
import shutil
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


T = load('projects_dashboard_base', ROOT / 'tests/projects/test_projects.py')
P, k, git_init = T.P, T.k, T.git_init
DB = P.DB
GO = shutil.which('go') or ('/usr/local/go/bin/go' if os.access('/usr/local/go/bin/go', os.X_OK) else None)
SOURCE = ROOT / 'runtime/dashboard'


def commit(repo):
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(repo), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid', 'GIT_COMMITTER_NAME': 't',
           'GIT_COMMITTER_EMAIL': 't@example.invalid'}
    (repo / 'f.txt').write_text(str(len(list(repo.iterdir()))))
    subprocess.run(['/usr/bin/git', '-C', str(repo), 'add', '-A'], check=True, env=env)
    subprocess.run(['/usr/bin/git', '-C', str(repo), 'commit', '-q', '-m', 'c'], check=True, env=env)
    return subprocess.run(['/usr/bin/git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def status_doc(**edit):
    doc = {'taskId': 'task-a', 'title': 'Secret-free fixture title', 'state': 'Recorded', 'next': 'Fixture next action',
           'sources': [{'id': 'work', 'kind': 'work-record', 'role': 'author-recorded', 'label': 'Task record',
                        'recordedAt': '2026-11-20T10:00:00Z'}],
           'stages': [{'name': n, 'state': 'Unknown', 'detail': 'No result'} for n in
                      ('Plan', 'Implementation', 'Tests', 'Review', 'Push', 'Update')]}
    doc['stages'][1] = {'name': 'Implementation', 'state': 'Recorded', 'detail': 'Done', 'sourceId': 'work'}
    doc.update(edit)
    return doc


@unittest.skipUnless(GO, 'Go toolchain is not available')
class Dashboard(T.Base):
    capture = False

    def setUp(self):
        super().setUp()
        self.base = self.cf.base
        self.project = git_init(self.base / 'alpha')
        self.head = commit(self.project)
        self.projects = self.base / 'dashboard-projects.json'
        self.projects.write_text(json.dumps([{'id': 'alpha', 'name': 'Alpha', 'root': str(self.project)}]))
        self.projects.chmod(0o600)
        self.feed = self.base / 'feed'
        self.feed.mkdir(mode=0o700)

    def configure(self, *extra, apply=True):
        return self.ok('dashboard', '--source', str(SOURCE), '--projects', str(self.projects), '--feed', str(self.feed),
                       '--go', GO, *extra, *(['--apply'] if apply else []))

    def status(self, doc, *extra, raw=None):
        stdin = io.BytesIO(raw if raw is not None else json.dumps(doc).encode())
        old = sys.stdin
        sys.stdin = io.TextIOWrapper(stdin)
        try:
            return self.run_cli('status', '--project', 'alpha', *extra)
        finally:
            sys.stdin = old

    def test_config_is_private_paths_only_and_reruns_noop(self):
        plan = self.configure(apply=False)
        self.assertEqual(['alpha'], plan['dashboard_projects'])
        self.assertTrue(plan['status'].startswith('PLANNED'))
        self.assertEqual('APPLIED', self.configure()['status'])
        cfg = self.kit / k.STATE / 'dashboard.json'
        self.assertEqual(0o600, cfg.stat().st_mode & 0o777)
        self.assertEqual(str(self.feed), json.loads(cfg.read_text())['feed'])
        self.assertEqual('NOOP', self.configure()['status'])
        self.feed.chmod(0o755)
        self.assertIn('feed', self.blocked('dashboard', '--source', str(SOURCE), '--projects', str(self.projects),
                                           '--feed', str(self.feed), '--go', GO)['reason'])

    def test_status_without_config_names_the_setup_command(self):
        self.assertIn('project dashboard', self.status(status_doc())['reason'])

    def test_dry_run_then_apply_binds_to_head_and_prints_no_record_text(self):
        self.configure()
        dry = self.status(status_doc())
        self.assertTrue(dry['status'].startswith('VALID'), dry)
        self.assertFalse((self.feed / 'alpha.json').exists())
        out = self.status(status_doc(), '--apply')
        self.assertEqual('APPLIED', out['status'], out)
        rec = json.loads((self.feed / 'alpha.json').read_text())
        self.assertEqual(self.head, rec['revision'])
        self.assertEqual('alpha', rec['project'])
        self.assertEqual('factory-dashboard/status/1', rec['schema'])
        for text in ('Secret-free fixture title', 'Fixture next action'):
            self.assertNotIn(text, json.dumps(out))

    def test_refusals(self):
        self.configure()
        self.assertIn('must not set revision', self.status(status_doc(revision='a' * 40))['reason'])
        self.assertIn('unknown status fields', self.status(status_doc(extra=1))['reason'])
        self.assertIn('not JSON', self.status(None, raw=b'{nope')['reason'])
        self.assertIn('16 KiB', self.status(None, raw=b' ' * (17 * 1024))['reason'])
        leak = self.status(status_doc(next='see /home/example/private-plan.md'), '--apply')
        self.assertEqual('BLOCKED', leak['status'])
        self.assertIn('refused', leak['reason'])
        self.assertNotIn('private-plan', json.dumps(leak))
        self.assertFalse((self.feed / 'alpha.json').exists())
        unknown = self.run_cli_with_stdin(['status', '--project', 'beta'], status_doc())
        self.assertIn('not in the dashboard projects config', unknown['reason'])

    def test_install_adds_pointer_and_reruns_noop(self):
        self.configure()
        out = self.ok('install', '--project', str(self.project), '--apply')
        self.assertEqual({'project': 'alpha'}, out['dashboard'])
        agents = (self.project / 'AGENTS.local.md').read_text()
        self.assertIn('Dashboard status for this project: id `alpha`', agents)
        self.assertIn('project status --root', agents)
        # The pointer asks for the card's details and the open-task list, not only the stages.
        self.assertIn('Include `markdown`', agents)
        self.assertIn('project queue --root', agents)
        self.assertIn('--project alpha --apply < queue.json', agents)
        self.assertEqual('NOOP', self.ok('install', '--project', str(self.project), '--apply')['status'])

    def test_search_contract_and_dashboard_pointer_together(self):
        # Regression (review B1): an archive-enrolled project that is also on the dashboard
        # reconnects with both pointers; argparse must accept them together.
        contract = self.base / 'search-contract.md'
        contract.write_text('# contract\n')
        report = P.connect(self.kit, self.project, False, str(contract), 'alpha')
        self.assertNotEqual('BLOCKED', report.get('status'), report)
        P.connect(self.kit, self.project, True, str(contract), 'alpha')
        agents = (self.project / 'AGENTS.local.md').read_text()
        self.assertIn(str(contract), agents)
        self.assertIn('Dashboard status for this project: id `alpha`', agents)
        # Both pointers are retained by a plain reconnect.
        P.connect(self.kit, self.project, True)
        again = (self.project / 'AGENTS.local.md').read_text()
        self.assertEqual(agents, again)

    def queue(self, doc, *extra, raw=None):
        stdin = io.BytesIO(raw if raw is not None else json.dumps(doc).encode())
        old = sys.stdin
        sys.stdin = io.TextIOWrapper(stdin)
        try:
            return self.run_cli('queue', '--project', 'alpha', *extra)
        finally:
            sys.stdin = old

    def test_queue_publishes_in_order_and_prints_no_item_text(self):
        self.configure()
        items = [{'id': 't2', 'title': 'Second fixture task', 'state': 'Ready', 'summary': 'Fixture summary two.', 'recommended': True},
                 {'id': 't1', 'title': 'First fixture task', 'state': 'Blocked', 'summary': 'Fixture summary one.', 'blockedBy': 'T9'}]
        dry = self.queue({'items': items})
        self.assertTrue(dry['status'].startswith('VALID'), dry)
        self.assertFalse((self.feed / 'alpha.queue.json').exists())
        out = self.queue({'items': items}, '--apply')
        self.assertEqual(('APPLIED', 2, 0), (out['status'], out['items'], out['omitted']), out)
        rec = json.loads((self.feed / 'alpha.queue.json').read_text())
        self.assertEqual(('factory-dashboard/queue/1', 'alpha', ['t2', 't1']),
                         (rec['schema'], rec['project'], [i['id'] for i in rec['items']]))
        self.assertNotIn('fixture task', json.dumps(out))
        time.sleep(1.1)  # the publisher needs a strictly newer observation
        self.assertEqual('APPLIED', self.queue({'items': []}, '--apply')['status'])
        self.assertEqual([], json.loads((self.feed / 'alpha.queue.json').read_text())['items'])

    def test_queue_trims_from_the_end_and_counts_it(self):
        self.configure()
        items = [{'id': f't{i}', 'title': f'Task {i}', 'state': 'Ready', 'summary': 'S' * 500} for i in range(80)]
        out = self.queue({'items': items}, '--apply')
        self.assertEqual('APPLIED', out['status'], out)
        rec = json.loads((self.feed / 'alpha.queue.json').read_bytes())
        self.assertEqual(80, len(rec['items']) + rec['omitted'])
        self.assertEqual(['t0', 't1'], [i['id'] for i in rec['items'][:2]])
        self.assertLessEqual(len((self.feed / 'alpha.queue.json').read_bytes()), 32 * 1024)
        self.assertGreater(rec['omitted'], 16)  # 64-item cap and the 32 KiB cap both applied

    def test_queue_refusals(self):
        self.configure()
        self.assertIn('must not set omitted', self.queue({'items': [], 'omitted': 3})['reason'])
        self.assertIn('{"items"', self.queue({'items': {}})['reason'])
        self.assertIn('256 KiB', self.queue(None, raw=b' ' * (257 * 1024))['reason'])
        leak = self.queue({'items': [{'id': 't1', 'title': 'T', 'state': 'Ready', 'summary': 'see /home/example/plan.md'}]}, '--apply')
        self.assertIn('refused', leak['reason'])
        self.assertNotIn('plan.md', json.dumps(leak))
        self.assertFalse((self.feed / 'alpha.queue.json').exists())
        # The publisher's own reason is shown, not the trailing "exit status 1" of `go run`.
        bad = self.queue({'items': [{'id': 't1', 'title': 'T', 'state': 'Verified locally', 'summary': 'S'}]})
        self.assertIn('invalid queue task t1', bad['reason'])
        self.assertNotIn('exit status', bad['reason'])

    def test_last_line_skips_go_run_exit_status(self):
        self.assertEqual('invalid Plan evidence state',
                         DB.last_line('2026/11/23 21:35:51 invalid Plan evidence state\nexit status 1\n'))
        self.assertEqual('', DB.last_line('exit status 2\n'))

    def run_cli_with_stdin(self, argv, doc):
        old = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(doc).encode()))
        try:
            return self.run_cli(*argv)
        finally:
            sys.stdin = old


if __name__ == '__main__':
    unittest.main()
