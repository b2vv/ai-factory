#!/usr/bin/env python3
"""Offline exact-manifest export; preserve but never distribute declared research archive."""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile
import kit

ARCHIVE = 'provenance/research-archive.json'
PREFIX = 'work/research/semgrep-ce-paused/'

def collect(root):
    root = kit.absolute(root)
    manifest = kit.read_json(root / 'release-manifest.json')
    release = [e['path'] for e in manifest['files']]
    if len(set(release)) != len(release): raise ValueError('duplicate release path')
    expected = set(release) | {'release-manifest.json', 'checksums.sha256'}
    if ARCHIVE not in release: raise ValueError('missing archive inventory binding')
    archive = kit.read_json(root / ARCHIVE)
    if archive.get('schema_version') != 1 or archive.get('status') != 'PAUSED_SUPERSEDED_NOT_RUNNABLE':
        raise ValueError('unsupported archive inventory')
    entries = archive.get('files')
    if not isinstance(entries, dict) or len(entries) != 30: raise ValueError('exact 30-file archive required')
    for name, digest in entries.items():
        kit.relative(name)
        if not name.startswith(PREFIX) or name in expected: raise ValueError('invalid archive scope')
        raw = kit.regular(root / name)
        if raw is None or kit.digest(raw) != digest: raise ValueError('archive hash mismatch')
    actual = set()
    for base, dirs, files in os.walk(root, followlinks=False):
        if Path(base) == root and '.git' in dirs:
            if (root / '.git').is_symlink(): raise ValueError('symlink Git directory')
            dirs.remove('.git')
        for name in dirs + files:
            p = Path(base) / name
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode): raise ValueError('symlink refused')
            if stat.S_ISDIR(st.st_mode): continue
            if Path(base) == root and name == '.git':
                import re
                if not re.fullmatch(rb'gitdir: [^\x00\r\n]+\n?', kit.regular(p)): raise ValueError('invalid gitfile')
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1: raise ValueError('nonregular/hardlinked source')
            actual.add(str(p.relative_to(root)))
    if actual != expected | set(entries): raise ValueError('undeclared repository file')
    payload = {}
    for name in sorted(expected):
        kit.relative(name)
        payload[name] = kit.regular(root / name)
        if payload[name] is None: raise ValueError('missing payload')
    # Reuse unchanged strict installer validator on only the declared distribution.
    with tempfile.TemporaryDirectory(prefix='factory-export-check-') as tmp:
        temp = Path(tmp).resolve()
        for name, data in payload.items():
            p = temp / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        kit.payload(temp, [])
    return payload

def export(root, destination):
    root = kit.absolute(root); destination = kit.absolute(destination)
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('export must not overlap source')
    if destination.exists() or not destination.parent.is_dir(): raise ValueError('new export directory required')
    payload = collect(root)
    destination.mkdir(mode=0o700)
    # Failures leave a partial destination for diagnosis; never overwrite or auto-clean.
    for name, data in payload.items():
        p = destination / name; p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as stream: stream.write(data)
    kit.payload(destination, [])
    return {'status': 'EXPORTED', 'files': len(payload), 'archive_files_exported': 0}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.destination)))
