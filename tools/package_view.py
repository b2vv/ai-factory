#!/usr/bin/env python3
"""A package view of a Git checkout: only the files the release manifest lists (C3).

Several suites treat their own tree as a release package (every file listed, no symlinks). In a checkout they would
fail on untracked files and local symlinks such as node_modules; on a package view they see what an exported package
holds. A tracked file changed without regenerating the manifest is still reported, as it should be.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def _entries(tree):
    return json.loads((Path(tree) / 'release-manifest.json').read_text())['files']


def stale_manifest(tree):
    """Listed files that are missing or whose bytes no longer match the manifest."""
    tree = Path(tree)
    return [e['path'] for e in _entries(tree)
            if not (tree / e['path']).is_file() or hashlib.sha256((tree / e['path']).read_bytes()).hexdigest() != e['sha256']]


def package_view(tree, dest):
    """Copy the listed files plus the manifest and checksums into dest (bytes and permission bits only)."""
    tree, dest = Path(tree), Path(dest)
    for name in [e['path'] for e in _entries(tree)] + ['release-manifest.json', 'checksums.sha256']:
        source = tree / name
        if not source.is_file() or source.is_symlink(): continue  # stale_manifest reports it; the suites then fail on it
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes()); target.chmod(source.stat().st_mode & 0o777)
    return dest


def export_check(tree):
    """Run the exporter's own tree check on the tracked files, using their working-tree bytes (stricter than the
    committed bytes `git archive` would hand over: an uncommitted edit without a manifest update is refused too).

    The package view hides a tracked file the manifest does not declare; the exporter refuses it. None when it passes,
    otherwise the exporter's reason. Run tests directly (without the runner) to exercise this on the real checkout.
    """
    tree = Path(tree)
    listed = subprocess.run(['/usr/bin/git', '-C', str(tree), 'ls-files', '-z'], check=True, capture_output=True).stdout
    import export_release  # tools/ is on sys.path: the runner and the exporter live side by side
    with tempfile.TemporaryDirectory(prefix='ai-factory-export-check-') as tmp:
        dest = Path(tmp).resolve()
        for name in filter(None, listed.decode().split('\0')):
            source = tree / name
            if source.is_symlink(): return 'symlink refused'  # git archive would hand it over; the exporter refuses it
            if not source.is_file(): continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes()); target.chmod(source.stat().st_mode & 0o777)
        try:
            export_release.collect(dest)
        except ValueError as error:
            return str(error)
    return None
