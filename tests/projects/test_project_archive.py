"""Archive access on `project install/remove` (T15 P6) against a real local factory server.

The server is built from runtime/storage/cmd/factory and runs without databases on a random
loopback port with a synthetic operator token; launchctl is a recording fake. Skipped without Go.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load('projects_archive_base', ROOT / 'tests/projects/test_projects.py')
P, k, git_init = T.P, T.k, T.git_init
A = P.A
GO = shutil.which('go') or ('/usr/local/go/bin/go' if os.access('/usr/local/go/bin/go', os.X_OK) else None)
BUILD = {}

FAKE_LAUNCHCTL = """#!/bin/sh
d='{d}'
echo "$@" >> "$d/calls"
case "$1" in
  print) grep -qx "${{2##*/}}" "$d/loaded" 2>/dev/null ;;
  bootstrap) [ -e "$d/fail-bootstrap" ] && exit 5; basename "$3" .plist >> "$d/loaded" ;;
  bootout) grep -vx "${{2##*/}}" "$d/loaded" > "$d/loaded.new"; mv "$d/loaded.new" "$d/loaded" ;;
esac
"""


def factory_binary():
    if 'path' not in BUILD:
        out = Path(tempfile.mkdtemp(prefix='factory-bin-')) / 'factory'
        r = subprocess.run([GO, 'build', '-o', str(out), './cmd/factory'], cwd=ROOT / 'runtime/storage',
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0: raise RuntimeError('go build failed: ' + r.stderr[-2000:])
        BUILD['path'] = out
    return BUILD['path']


@unittest.skipUnless(GO, 'Go toolchain is not available')
class Archive(T.Base):
    capture = True

    def setUp(self):
        super().setUp()
        self.base = self.cf.base
        self.ops = self.private_dir('ops')
        self.token = self.ops / 'operator.json'
        self.operator_secret = 'synthetic-operator-secret-0123456789'
        self.token.write_text(json.dumps({'id': 'op-test', 'secret': self.operator_secret})); self.token.chmod(0o600)
        self.start_server()
        self.capture_dir, self.search_dir = self.private_dir('capture'), self.private_dir('search')
        self.logs, self.agents = self.private_dir('logs'), self.private_dir('agents')
        self.fake = self.private_dir('launchd')
        script = self.fake / 'launchctl'
        script.write_text(FAKE_LAUNCHCTL.format(d=self.fake)); script.chmod(0o700)
        self.addCleanup(setattr, A, 'LAUNCHCTL', A.LAUNCHCTL)
        A.LAUNCHCTL = str(script)
        self.routes = self.kit / 'runtime/storage/deploy/search-client/search-routes.json'
        self.routes.parent.mkdir(parents=True, exist_ok=True)
        self.ok('migrate', '--apply')

    def private_dir(self, name):
        p = self.base / name
        p.mkdir(mode=0o700)
        return p

    def start_server(self):
        state = self.base / 'state'
        subprocess.run([str(factory_binary()), '-init', '-state', str(state), '-operator-token', str(self.token)],
                       check=True, capture_output=True, timeout=60)
        log = open(self.base / 'server.log', 'w+')
        self.server = subprocess.Popen([str(factory_binary()), '-state', str(state), '-listen', '127.0.0.1:0',
                                        '-operator-token', str(self.token)], stdout=log, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop_server)
        self.addCleanup(log.close)
        deadline = time.time() + 30
        while time.time() < deadline:
            log.seek(0)
            for line in log.read().splitlines():
                if line.startswith('LISTEN '): self.endpoint = 'http://' + line.split()[1]; return
            time.sleep(0.05)
        self.fail('factory server did not start')

    def stop_server(self):
        if self.server.poll() is None:
            self.server.terminate(); self.server.wait(10)

    def configure(self, *extra):
        argv = ['archive', '--endpoint', self.endpoint, '--operator-secret-file', str(self.token),
                '--capture-dir', str(self.capture_dir), '--search-dir', str(self.search_dir),
                '--search-routes', str(self.routes), '--worker', 'launchd', '--agents-dir', str(self.agents),
                '--log-dir', str(self.logs), '--python', sys.executable, *extra]
        return self.ok(*argv, '--apply')

    # --- server-side observations -----------------------------------------------------------

    def whoami(self, ident, op, principal, epoch, secret):
        q = urllib.parse.urlencode({'project': ident, 'op': op})
        req = urllib.request.Request(f'{self.endpoint}/v1/whoami?{q}', headers={
            'X-Principal-Id': principal, 'X-Grant-Epoch': str(epoch), 'X-Secret': secret})
        try:
            with urllib.request.urlopen(req, timeout=10) as r: return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def operator(self, path, body):
        req = urllib.request.Request(self.endpoint + path, data=json.dumps(body).encode(), method='POST',
                                     headers={'X-Operator-Secret': self.operator_secret})
        try:
            with urllib.request.urlopen(req, timeout=10) as r: return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def creds(self, name):
        cap_path = self.capture_dir / f'{name}.cred.json'
        cap = json.loads(cap_path.read_text()) if cap_path.exists() else None
        search = None
        if (self.search_dir / f'{name}.search.secret').exists():
            search = (int((self.search_dir / f'{name}.search.epoch').read_text()),
                      (self.search_dir / f'{name}.search.secret').read_text().rstrip('\n'))
        return cap, search

    def calls(self):
        p = self.fake / 'calls'
        return p.read_text().splitlines() if p.exists() else []

    def assert_no_secret(self, out, *secrets):
        text = json.dumps(out)
        for s in (self.operator_secret, *secrets):
            self.assertNotIn(s, text)

    # --- cases ---------------------------------------------------------------------------------

    def install(self, name='alpha', *extra):
        project = git_init(self.base / name)
        return project, self.ok('install', '--project', str(project), *extra, '--apply')

    def test_install_issues_two_separate_grants_files_route_contract_worker(self):
        self.configure()
        project, out = self.install()
        self.assertEqual('APPLIED', out['status'], out)
        ident = out['project']['id']
        self.assertEqual('started', out['archive']['worker'])
        self.assertEqual('minted', out['archive']['project'])
        cap, (s_epoch, s_secret) = self.creds('alpha')
        self.assert_no_secret(out, cap['secret'], s_secret)
        cap_p, search_p = f'p-{ident}-capture', f'p-{ident}-search'
        self.assertEqual(cap_p, cap['principal_id'])
        # Each file's epoch is the live grant's: the server accepts it, and only for its own op.
        self.assertEqual(200, self.whoami(ident, 'capture', cap_p, cap['epoch'], cap['secret']))
        self.assertEqual(403, self.whoami(ident, 'search', cap_p, cap['epoch'], cap['secret']))
        self.assertEqual(200, self.whoami(ident, 'search', search_p, s_epoch, s_secret))
        self.assertEqual(403, self.whoami(ident, 'capture', search_p, s_epoch, s_secret))
        for f in (self.capture_dir / 'alpha.cred.json', self.search_dir / 'alpha.search.secret',
                  self.search_dir / 'alpha.search.epoch'):
            self.assertEqual(0o600, f.stat().st_mode & 0o777)
        route = json.loads(self.routes.read_text())['projects']['alpha']
        self.assertEqual({'project_id': ident, 'principal_id': search_p, 'credential_format': 'split',
                          'secret_file': str(self.search_dir / 'alpha.search.secret'),
                          'epoch_file': str(self.search_dir / 'alpha.search.epoch'),
                          'port': int(self.endpoint.rsplit(':', 1)[1])}, route)
        contract = self.kit / k.STATE / 'search-contracts' / f'{ident}.md'
        self.assertIn('archive_search.py alpha', contract.read_text())
        self.assertIn(str(contract), (project / 'AGENTS.local.md').read_text())
        plist = self.agents / 'local.ai-factory.capture.alpha.plist'
        raw = plist.read_bytes()
        self.assertEqual(0o600, plist.stat().st_mode & 0o777)
        for s in (cap['secret'], s_secret, self.operator_secret): self.assertNotIn(s.encode(), raw)
        import plistlib
        doc = plistlib.loads(raw)
        self.assertEqual(['-I', '-B', str(self.kit / A.BRIDGE), '--worker'], doc['ProgramArguments'][1:])
        row = json.loads(self.mapping.read_text())['projects'][-1]
        self.assertEqual(str(self.capture_dir / 'alpha.cred.json'), row['credential_file'])
        self.assertEqual(row['queue_dir'], doc['EnvironmentVariables']['AF_CAPTURE_QUEUE_DIR'])
        self.assertIn(f'bootstrap gui/{os.getuid()} {plist}', self.calls())
        listed = self.ok('list')
        self.assertEqual({'enabled': True, 'alias': 'alpha'}, listed['projects'][-1]['capabilities']['search'])
        text = json.dumps(listed)
        for p in (str(self.capture_dir), str(self.search_dir), str(plist)): self.assertNotIn(p, text)
        # A full rerun probes the live state and changes nothing.
        files = self.snapshot(self.list_path, self.routes, contract, plist, self.mapping, project / 'AGENTS.local.md')
        rerun = self.ok('install', '--project', str(project), '--apply')
        self.assertEqual('NOOP', rerun['status'], rerun)
        self.assertEqual(files, self.snapshot(*map(Path, files)))

    def test_failure_after_grants_revokes_them_and_restores_files(self):
        self.configure()
        import uuid
        project, ident = git_init(self.base / 'alpha'), str(uuid.uuid4())
        made = []
        real = A.new_secret
        self.addCleanup(setattr, A, 'new_secret', real)
        A.new_secret = lambda: made.append(real()) or made[-1]
        P.FAULT = ('before-list', RuntimeError('injected'))
        before = self.snapshot(self.mapping, self.list_path, project / 'AGENTS.local.md')
        out = self.blocked('install', '--project', str(project), '--id', ident, '--apply')
        self.assertIn('issued grants were revoked', out['reason'])
        self.assert_no_secret(out, *made)
        self.assertEqual(before, self.snapshot(self.mapping, self.list_path, project / 'AGENTS.local.md'))
        self.assertEqual([], list(self.capture_dir.iterdir()) + list(self.search_dir.iterdir()))
        self.assertFalse(self.routes.exists())
        self.assertEqual([], [c for c in self.calls() if c.startswith('bootstrap')])
        # Issued at epoch 1, revoked since: the server refuses both, whatever epoch is presented.
        for (op, role), secret in zip((('capture', 'capture'), ('search', 'search')), made):
            for epoch in (1, 2):
                self.assertEqual(403, self.whoami(ident, op, f'p-{ident}-{role}', epoch, secret))
        # Rerun after the failure enrolls cleanly (the project is already minted: explicit --id reuses it).
        P.FAULT = None
        again = self.ok('install', '--project', str(project), '--id', ident, '--apply')
        self.assertEqual('existing', again['archive']['project'])

    def test_remove_revokes_each_recorded_grant_and_deletes_every_file(self):
        self.configure()
        project, out = self.install()
        ident = out['project']['id']
        cap, (s_epoch, s_secret) = self.creds('alpha')
        plan = self.ok('remove', '--project', str(project))
        self.assertEqual(sorted([f'p-{ident}-capture', f'p-{ident}-search']), plan['archive']['revoke'])
        removed = self.ok('remove', '--project', str(project), '--apply')
        self.assertEqual('APPLIED', removed['status'], removed)
        self.assertEqual(403, self.whoami(ident, 'capture', cap['principal_id'], cap['epoch'], cap['secret']))
        self.assertEqual(403, self.whoami(ident, 'search', f'p-{ident}-search', s_epoch, s_secret))
        self.assertEqual([], list(self.capture_dir.iterdir()) + list(self.search_dir.iterdir()))
        self.assertEqual([], list(self.agents.iterdir()))
        self.assertNotIn('alpha', json.loads(self.routes.read_text())['projects'])
        self.assertFalse((self.kit / k.STATE / 'search-contracts' / f'{ident}.md').exists())
        self.assertIn(f'bootout gui/{os.getuid()}/local.ai-factory.capture.alpha', self.calls())
        self.assertEqual([], [e for e in json.loads(self.list_path.read_text())['projects'] if e['id'] == ident])
        self.assertTrue((self.base / 'state').is_dir())  # archive data stays
        # No backup holds a credential copy.
        backups = self.kit / k.STATE / P.BACKUPS
        for f in backups.rglob('*'):
            if f.is_file():
                for s in (cap['secret'], s_secret): self.assertNotIn(s.encode(), f.read_bytes())

    def test_server_down_stops_before_any_write(self):
        self.configure()
        self.stop_server()
        project = git_init(self.base / 'alpha')
        before = self.snapshot(self.mapping, self.list_path, project / 'AGENTS.local.md')
        out = self.blocked('install', '--project', str(project), '--apply')
        self.assertIn('not reachable', out['reason'])
        self.assertEqual(before, self.snapshot(*map(Path, before)))
        self.assertEqual([], list(self.capture_dir.iterdir()) + list(self.search_dir.iterdir()))

    def test_existing_alias_or_credential_stops(self):
        self.configure()
        self.routes.write_text(json.dumps({'version': 1, 'projects': {'alpha': {}}})); self.routes.chmod(0o600)
        project = git_init(self.base / 'alpha')
        listed = self.list_path.read_bytes()
        self.assertIn('alias alpha already exists', self.blocked('install', '--project', str(project), '--apply')['reason'])
        self.routes.unlink()
        (self.search_dir / 'alpha.search.secret').write_text('old'); (self.search_dir / 'alpha.search.secret').chmod(0o600)
        self.assertIn('search_secret', self.blocked('install', '--project', str(project), '--apply')['reason'])
        self.assertEqual(listed, self.list_path.read_bytes())

    def test_no_capture_issues_search_only_and_remove_revokes_only_it(self):
        self.configure()
        project, out = self.install('beta', '--no-capture')
        ident = out['project']['id']
        self.assertEqual([f'p-{ident}-search'], out['archive']['will_issue'])
        self.assertIsNone(out['archive']['worker'])
        cap, (s_epoch, s_secret) = self.creds('beta')
        self.assertIsNone(cap)
        self.assertEqual(200, self.whoami(ident, 'search', f'p-{ident}-search', s_epoch, s_secret))
        self.assertEqual([], list(self.agents.iterdir()))
        self.assertEqual('NOOP', self.ok('install', '--project', str(project), '--apply')['status'])
        removed = self.ok('remove', '--project', str(project), '--apply')
        self.assertEqual([f'p-{ident}-search'], removed['archive']['revoke'])
        self.assertEqual(403, self.whoami(ident, 'search', f'p-{ident}-search', s_epoch, s_secret))
        self.assertEqual([], list(self.search_dir.iterdir()))

    def test_failed_bootstrap_is_retried_by_rerun_then_noop(self):
        self.configure()
        (self.fake / 'fail-bootstrap').write_text('')
        project, out = self.install()
        self.assertIn('bootstrap failed', out['archive']['worker'])
        (self.fake / 'fail-bootstrap').unlink()
        plan = self.ok('install', '--project', str(project))
        self.assertEqual('bootstrap needed', plan['archive']['worker'])
        again = self.ok('install', '--project', str(project), '--apply')
        self.assertEqual('started', again['archive']['worker'])
        self.assertEqual('NOOP', self.ok('install', '--project', str(project), '--apply')['status'])

    def test_rerun_with_revoked_grant_is_blocked_naming_it(self):
        self.configure()
        project, out = self.install()
        ident = out['project']['id']
        self.assertEqual(200, self.operator('/v1/grants/revoke', {'principal_id': f'p-{ident}-search'}))
        reason = self.blocked('install', '--project', str(project), '--apply')['reason']
        self.assertIn(f'search grant p-{ident}-search is not accepted', reason)
        self.assertNotIn('capture grant', reason)

    def test_existing_id_needs_explicit_flag_and_is_reused(self):
        self.configure()
        import uuid
        ident = str(uuid.uuid4())
        self.assertEqual(201, self.operator('/v1/projects', {'UUID': ident, 'Label': 'old'}))
        project, out = self.install('alpha', '--id', ident)
        self.assertEqual('existing', out['archive']['project'])

    def test_capture_credential_install_is_not_archive_managed(self):
        self.configure()
        project = git_init(self.base / 'gamma')
        cred = self.credential('gamma')
        out = self.ok('install', '--project', str(project), '--capture-credential', str(cred), '--apply')
        self.assertNotIn('archive', out)
        removed = self.ok('remove', '--project', str(project), '--apply')
        self.assertNotIn('archive', removed)
        self.assertIn('not managed by the kit', ' '.join(removed['kept']))
        self.assertTrue(cred.exists())

    def test_archive_config_holds_paths_only_and_reruns_noop(self):
        out = self.configure()
        cfg = self.kit / k.STATE / A.CONFIG
        self.assertEqual(0o600, cfg.stat().st_mode & 0o777)
        self.assertNotIn(self.operator_secret, cfg.read_text())
        self.assertEqual(str(self.token), json.loads(cfg.read_text())['operator_secret_file'])
        self.assertEqual('NOOP', self.configure()['status'])
        self.logs.chmod(0o755)
        self.assertIn('log dir', self.blocked('archive', '--endpoint', self.endpoint, '--operator-secret-file', str(self.token),
                                              '--capture-dir', str(self.capture_dir), '--search-dir', str(self.search_dir),
                                              '--search-routes', str(self.routes), '--worker', 'launchd',
                                              '--agents-dir', str(self.agents), '--log-dir', str(self.logs),
                                              '--python', sys.executable)['reason'])
        wrong = self.base / 'search-routes.json'
        self.logs.chmod(0o700)
        self.assertIn('next to the installed search client', self.blocked(
            'archive', '--operator-secret-file', str(self.token), '--capture-dir', str(self.capture_dir),
            '--search-dir', str(self.search_dir), '--search-routes', str(wrong), '--worker', 'none')['reason'])



class Consent(unittest.TestCase):
    """Install turns on capture consent for every provider the kit wires (Claude Code and Codex hooks)."""
    def server(self, codes):
        srv = object.__new__(A.Server)
        sent = []
        def operator(path, body):
            sent.append((path, body)); return codes.pop(0), {}
        srv.operator = operator
        return srv, sent

    def test_consent_covers_claude_and_codex(self):
        srv, sent = self.server([200, 200])
        srv.consent('p1')
        self.assertEqual([('/v1/consent', {'Project': 'p1', 'Provider': p, 'Capability': 'capture', 'Enabled': True})
                          for p in ('claude-code', 'codex-hook-v2')], sent)

    def test_a_refused_provider_stops_install(self):
        srv, _ = self.server([200, 403])
        with self.assertRaisesRegex(A.Blocked, 'codex-hook-v2 capture consent failed'):
            srv.consent('p1')

    def test_provider_name_matches_the_server(self):
        go = (Path(__file__).resolve().parents[2] / 'runtime/storage/internal/capture/codex_event.go').read_text()
        self.assertIn('CodexSnapshotProvider = "codex-hook-v2"', go)

if __name__ == '__main__':
    unittest.main()
