#!/usr/bin/env python3
"""Global Claude Stop router. Explicit private enrollment is not authorization.

Unknown roots are a no-op before transcript/credential access. The existing bridge
and server remain responsible for immutable queue identity and capture permission.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_queue import deadline, DeadlineExpired
from capture_bridge import emit_status

CAPTURE_DISPATCH_API = 1
MAX_INPUT = 1024 * 1024
MAX_MAPPING = 256 * 1024
ROW_KEYS = {'root', 'project', 'source_instance', 'credential_file', 'queue_dir', 'status_file'}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def canonical(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('invalid path')
    p = Path(value)
    if not p.is_absolute() or str(p) != value or '..' in p.parts or str(p.resolve()) != value:
        raise ValueError('canonical nonsymlink path required')
    for q in (p, *p.parents):
        if q.is_symlink():
            raise ValueError('symlink refused')
    return p


def private_dir(path):
    p = canonical(str(path))
    s = p.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise ValueError('private owned directory required')


def private_file(path, read=False, limit=MAX_MAPPING):
    p = canonical(str(path))
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid()
                or stat.S_IMODE(s.st_mode) & 0o077 or s.st_size > limit):
            raise ValueError('private owned regular file required')
        if not read:
            return None
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('file too large')
        return raw
    finally:
        os.close(fd)


def _git(cwd, *args):
    p = canonical(cwd)
    if not p.is_dir():
        raise ValueError('cwd missing')
    # No caller-controlled Git executable, environment, aliases or shell expansion.
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'LC_ALL': 'C',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    proc = subprocess.Popen(['/usr/bin/git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
                             '-C', str(p), 'rev-parse', *args], env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with deadline(1):
            raw = proc.stdout.read(8193)
            if len(raw) > 8192: raise ValueError('oversized git output')
            code = proc.wait(timeout=.2)
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait(timeout=1)
        proc.stdout.close()
    return p, (raw.decode('utf-8').rstrip('\n') if code == 0 else None)


def git_root(cwd):
    p, out = _git(cwd, '--show-toplevel')
    if out is None:
        return None
    root = canonical(out)
    if root != p and root not in p.parents:
        raise ValueError('git root outside cwd ancestry')
    return root


def main_checkout(cwd):
    """The main checkout of a linked worktree: the parent of its common `.git` directory."""
    _, out = _git(cwd, '--path-format=absolute', '--git-common-dir')
    if out is None:
        return None
    common = canonical(out)
    return common.parent if common.name == '.git' and common.is_dir() else None


def validate_mapping(doc, check_roots=True):
    if not isinstance(doc, dict) or set(doc) != {'schema', 'projects'} or type(doc['schema']) is not int or doc['schema'] != 1:
        raise ValueError('unsupported mapping')
    rows = doc['projects']
    if not isinstance(rows, list) or not 0 <= len(rows) <= 128:
        raise ValueError('invalid enrollment list')
    roots, projects, sources, statuses = set(), set(), set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise ValueError('invalid enrollment row')
        root = canonical(row['root'])
        if str(root) in roots or row['project'] in projects or row['source_instance'] in sources:
            raise ValueError('ambiguous enrollment')
        if str(uuid.UUID(row['project'])) != row['project']:
            raise ValueError('canonical project UUID required')
        if not isinstance(row['source_instance'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', row['source_instance']):
            raise ValueError('invalid source')
        if check_roots and git_root(str(root)) != root:
            raise ValueError('enrollment is not a git root')
        credential = canonical(row['credential_file'])
        queue = canonical(row['queue_dir'])
        status = canonical(row['status_file'])
        if status in statuses or status == credential or queue in (root, credential) or status == queue:
            raise ValueError('route path collision')
        # Mapping validation never opens credentials; selected bridge reads its own.
        if queue.exists():
            private_dir(queue)
        private_dir(status.parent)
        if status.exists():
            private_file(status, limit=64 * 1024 * 1024)
        roots.add(str(root)); projects.add(row['project']); sources.add(row['source_instance']); statuses.add(status)
    return rows


def load_mapping(path):
    p = canonical(path)
    private_dir(p.parent)
    return validate_mapping(strict_json(private_file(p, read=True)), check_roots=False)


def select_route(rows, cwd):
    root = git_root(cwd)
    if root is None:
        return None
    matches = [row for row in rows if row['root'] == str(root)]
    if not matches:
        # A linked worktree belongs to the project of its main checkout.
        main = main_checkout(str(root))
        if main is not None and main != root:
            matches = [row for row in rows if row['root'] == str(main)]
    return matches[0] if len(matches) == 1 else None


def dispatch(raw, mapping_path):
    if len(raw) > MAX_INPUT:
        raise ValueError('hook input too large')
    event = strict_json(raw)
    if not isinstance(event, dict) or event.get('hook_event_name') != 'Stop':
        return {'status': 'ignored_event'}
    rows = load_mapping(mapping_path)
    row = select_route(rows, event.get('cwd'))
    if row is None:
        return {'status': 'unenrolled'}
    # Refuse a replaced/nonrepository enrollment and any path rebinding at use time.
    if git_root(row['root']) != Path(row['root']):
        raise ValueError('enrollment changed')
    private_file(row['credential_file'], limit=64 * 1024)
    env = {k: v for k, v in os.environ.items() if not k.startswith('AF_CAPTURE_')}
    env.update(AF_CAPTURE_ENDPOINT='http://127.0.0.1:8780', AF_CAPTURE_PROJECT=row['project'],
               AF_CAPTURE_SOURCE=row['source_instance'], AF_CAPTURE_AGENT_CREDENTIAL_FILE=row['credential_file'],
               AF_CAPTURE_QUEUE_DIR=row['queue_dir'], AF_CAPTURE_STATUS_FILE=row['status_file'])
    # Inherit stderr for bounded bridge status only, never relay transcript/payload stdout.
    bridge = Path(__file__).resolve().with_name('capture_bridge.py')
    r = subprocess.run([sys.executable, '-I', '-B', str(bridge)], input=raw, env=env,
                       stdout=subprocess.DEVNULL, timeout=9, check=False)
    return {'status': 'bridge_returned', 'returncode': r.returncode}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping', required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        with deadline(12):
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            result = dispatch(raw, args.mapping)
    except (Exception, DeadlineExpired) as exc:
        result = {'status': 'blocked', 'error': type(exc).__name__}
    # No paths, identities, transcript text, credential contents or exception messages.
    emit_status(result, '', prefix='af-claude-dispatch ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
