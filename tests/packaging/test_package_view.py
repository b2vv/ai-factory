import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import package_view as pv  # noqa: E402


class PackageView(unittest.TestCase):
    """C3: suites that treat their tree as a package run on manifest-listed files only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.tree = Path(os.path.realpath(self.tmp.name)) / 'checkout'
        (self.tree / 'tools').mkdir(parents=True)
        (self.tree / 'tools/a.py').write_text('a'); (self.tree / 'tools/a.py').chmod(0o755)
        (self.tree / 'b.md').write_text('b')
        entries = [{'path': n, 'component': 'core', 'sha256': hashlib.sha256((self.tree / n).read_bytes()).hexdigest()}
                   for n in ('tools/a.py', 'b.md')]
        (self.tree / 'release-manifest.json').write_text(json.dumps({'files': entries}))
        (self.tree / 'checksums.sha256').write_text('x')
        (self.tree / 'untracked-notes').mkdir(); (self.tree / 'untracked-notes/n.txt').write_text('private')
        (self.tree / 'node_modules').symlink_to(self.tree / 'untracked-notes')

    def test_view_holds_only_listed_files_with_modes(self):
        view = pv.package_view(self.tree, self.tree.parent / 'view')
        files = sorted(str(p.relative_to(view)) for p in view.rglob('*') if p.is_file() or p.is_symlink())
        self.assertEqual(['b.md', 'checksums.sha256', 'release-manifest.json', 'tools/a.py'], files)
        self.assertEqual(0o755, (view / 'tools/a.py').stat().st_mode & 0o777)

    def test_stale_manifest_names_changed_and_missing_files(self):
        self.assertEqual([], pv.stale_manifest(self.tree))
        (self.tree / 'b.md').write_text('changed'); (self.tree / 'tools/a.py').unlink()
        self.assertEqual(['tools/a.py', 'b.md'], pv.stale_manifest(self.tree))

    def test_real_checkout_view_is_a_valid_package(self):
        if not (ROOT / '.git').exists() or pv.stale_manifest(ROOT): self.skipTest('needs a checkout with a current manifest')
        import kit
        view = pv.package_view(ROOT, self.tree.parent / 'repo-view')
        kit.payload(view, ['core'])  # raises on unlisted files, symlinks or hash mismatch


    def test_export_check_refuses_an_undeclared_tracked_file(self):
        if not (ROOT / '.git').exists() or pv.stale_manifest(ROOT): self.skipTest('needs a checkout with a current manifest')
        import subprocess
        self.assertIsNone(pv.export_check(ROOT))
        repo = self.tree.parent / 'repo-copy'
        names = subprocess.run(['/usr/bin/git', '-C', str(ROOT), 'ls-files', '-z'], check=True, capture_output=True).stdout
        for name in filter(None, names.decode().split('\0')):
            if (ROOT / name).is_file():
                (repo / name).parent.mkdir(parents=True, exist_ok=True); (repo / name).write_bytes((ROOT / name).read_bytes())
        git = ['/usr/bin/git', '-C', str(repo)]
        env = {'PATH': '/usr/bin:/bin', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
        subprocess.run(git + ['init', '-q'], check=True, env=env)
        (repo / 'work/notes.md').parent.mkdir(exist_ok=True); (repo / 'work/notes.md').write_text('undeclared')
        subprocess.run(git + ['add', '-A'], check=True, env=env)
        self.assertEqual('undeclared repository file', pv.export_check(repo))

if __name__ == '__main__':
    unittest.main()
