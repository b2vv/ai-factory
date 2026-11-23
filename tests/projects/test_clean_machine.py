"""T15 P11 / A8: on a clean machine (empty HOME, empty kit root) the kit installs, connects a project and updates.

The release is exported from this checkout, so the test exercises the real package. It writes only to a
temporary directory and checks that no path or name of the machine running it appears in kit state, project
files or command output.
"""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import export_release  # noqa: E402


class CleanMachine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.home = base / 'home'; self.home.mkdir(mode=0o700)
        self.pkg = base / 'release'
        export_release.export(self.manifest_copy(base / 'source'), self.pkg)
        self.kit = self.home / 'kit'
        self.project = self.home / 'work' / 'app'; self.project.mkdir(parents=True)
        subprocess.run(['/usr/bin/git', 'init', '-q', str(self.project)], check=True,
                       env={'PATH': '/usr/bin:/bin', 'HOME': str(self.home)})
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.home), 'LC_ALL': 'C'}
        self.outputs = []

    @staticmethod
    def manifest_copy(dest):
        """Only the files the release lists (plus the declared archive inventory): a checkout's untracked files stay out."""
        manifest = json.loads((ROOT / 'release-manifest.json').read_text())
        archive = json.loads((ROOT / export_release.ARCHIVE).read_text())['files']
        for name in [e['path'] for e in manifest['files']] + list(archive) + ['release-manifest.json', 'checksums.sha256']:
            target = dest / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes()); target.chmod((ROOT / name).stat().st_mode & 0o777)
        return dest

    def kit_cli(self, tool, *argv):
        r = subprocess.run([sys.executable, '-I', str(tool), *argv], capture_output=True, text=True, env=self.env, cwd=self.home)
        self.outputs.append(r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(1 if out.get('status') == 'BLOCKED' else 0, r.returncode, r.stdout + r.stderr)
        self.assertNotEqual('BLOCKED', out.get('status'), out)
        return out

    def test_install_kit_connect_project_update(self):
        package_kit = self.pkg / 'tools/kit.py'
        plan = self.kit_cli(package_kit, 'install', '--package', str(self.pkg), '--root', str(self.kit))
        self.assertEqual('PLANNED', plan['status'])
        done = self.kit_cli(package_kit, 'install', '--package', str(self.pkg), '--root', str(self.kit),
                            '--plan-id', plan['plan_id'], '--execute', '--exclusive-window')
        self.assertEqual('APPLIED', done['status'])
        installed = self.kit / 'tools/kit.py'
        connected = self.kit_cli(installed, 'project', 'install', '--root', str(self.kit), '--project', str(self.project), '--apply')
        self.assertEqual('APPLIED', connected['status'])
        self.assertIn('@AGENTS.local.md', (self.project / 'CLAUDE.local.md').read_text())
        self.assertEqual(['app'], [e['name'] for e in self.kit_cli(installed, 'project', 'list', '--root', str(self.kit))['projects']])
        update = self.kit_cli(installed, 'update', '--package', str(self.pkg), '--root', str(self.kit))
        self.assertEqual('NOOP', update['status'])
        self.assertEqual([('app', 'OK')], [(r['project'], r['status']) for r in update['projects']])
        self.assertNoHostTrace()

    def assertNoHostTrace(self):
        me = pwd.getpwuid(os.getuid())
        tokens = {me.pw_dir, me.pw_name, str(ROOT)}
        texts = list(self.outputs)
        state = self.kit / '.ai-factory-state'
        texts += [p.read_text(errors='replace') for p in state.rglob('*') if p.is_file()]
        texts += [(self.project / n).read_text() for n in ('AGENTS.local.md', 'CLAUDE.local.md', '.gitignore')]
        for token in tokens:
            hits = [t for t in texts if token in t]
            self.assertEqual([], [h[:200] for h in hits], f'host trace {token!r}')


if __name__ == '__main__':
    unittest.main()
