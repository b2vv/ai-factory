#!/usr/bin/env python3
"""Explicit enrolled, non-Docker handoff entry point. No transcript reads or launches."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
# -I ignores the environment bytecode flag; managed runtimes never write caches.
sys.dont_write_bytecode = True
import unicodedata

HANDOFF_API = 1
EVENTS = ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop')
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_factory_guard_native', HERE / 'session_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class _UnavailableLock(Exception):
    pass


_lock_type = getattr(guard, 'LockBusy', None)
LockBusy = (_lock_type if isinstance(_lock_type, type) and issubclass(_lock_type, Exception)
            else _UnavailableLock)


def validate_guard_api():
    required = ('safe_path', 'git', 'event', 'checkpoint', 'resume', 'validate_output')
    if (type(getattr(guard, 'HANDOFF_API', None)) is not int or guard.HANDOFF_API != HANDOFF_API
            or any(not callable(getattr(guard, name, None)) for name in required)
            or not isinstance(getattr(guard, 'LockBusy', None), type)
            or not issubclass(guard.LockBusy, Exception)
            or not isinstance(getattr(guard, 'DEFERRED', None), str)):
        raise ValueError('incompatible canonical handoff API')


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def canonical(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 or unicodedata.category(c) == 'Cf' for c in value)):
        raise ValueError('invalid explicit path')
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts or str(p) != value:
        raise ValueError('noncanonical explicit path')
    return guard.safe_path(p)


def load_profile(path):
    validate_guard_api()
    path = canonical(str(path))
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 32768 or st.st_uid != os.getuid():
        raise ValueError('invalid profile file')
    if st.st_mode & 0o022:
        raise ValueError('profile must not be writable by other users')
    data = json.loads(path.read_bytes(), object_pairs_hook=pairs)
    if (not isinstance(data, dict) or set(data) != {'schema', 'managed_root', 'store', 'roots'}
            or type(data['schema']) is not int or data['schema'] != HANDOFF_API):
        raise ValueError('unsupported profile schema')
    root = canonical(data['managed_root'])
    if root / 'runtime/session-size' != HERE:
        raise ValueError('profile does not select this installed runtime')
    # Installation may be in a multi-file transaction. Never use partially updated runtime.
    if (root / '.ai-factory-state/pending.json').exists():
        raise ValueError('managed update pending')
    canonical(data['store'])
    roots = data['roots']
    if not isinstance(roots, list) or not 1 <= len(roots) <= 64 or any(not isinstance(r, str) for r in roots):
        raise ValueError('invalid enrolled roots')
    if len(roots) != len(set(roots)):
        raise ValueError('duplicate enrolled roots')
    for r in roots:
        canonical(r)
    return data


def identity_context(host, sid, root, event):
    if host not in ('claude', 'codex') or not isinstance(sid, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,256}', sid) is None:
        raise ValueError('current native identity unavailable')
    canonical(root)
    value = {'schema': 'ai-factory-native-identity/1', 'host': host,
             'session_id': sid, 'root': root, 'event': event}
    text = 'AI_FACTORY_NATIVE_IDENTITY ' + json.dumps(value, ensure_ascii=True, separators=(',', ':'))
    if len(text) > 8192:
        raise ValueError('current native identity unavailable')
    return text


def enrolled(profile, host, sid, cwd):
    if not isinstance(cwd, str):
        raise ValueError('current root unavailable')
    canonical(cwd)
    root = guard.git(cwd, 'rev-parse', '--show-toplevel').decode().strip()
    identity_context(host, sid, root, 'manual')
    return root if root in profile['roots'] else None


def command(profile_path, host, sid, root):
    return shlex.join([sys.executable, '-I', str(HERE / 'native.py'), 'checkpoint',
                       '--profile', str(profile_path), '--host', host, '--session', sid, '--cwd', root])


def event(profile_path, host, payload, pointer=None, store=None):
    profile = load_profile(profile_path)
    if store is not None and str(canonical(str(store))) != profile['store']:
        raise ValueError('alternate store refused')
    if not isinstance(payload, dict):
        raise ValueError('hook payload object required')
    ev = payload.get('hook_event_name')
    if ev not in EVENTS:
        return {}
    root = enrolled(profile, host, payload.get('session_id'), payload.get('cwd'))
    if root is None:
        if pointer:
            raise ValueError('explicit handoff outside enrolled root')
        return {}
    current = identity_context(host, payload['session_id'], root, ev) if ev != 'Stop' else ''
    public = command(profile_path, host, payload['session_id'], root)
    # Reject excessive configuration/identity before any store mutation.
    guard.validate_output(ev, current + '\n' + public + '\n' + ('x' * 4096))
    return guard.event(Path(profile['store']), host, payload, pointer,
                       public_context=public, identity_text=current)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['hook', 'checkpoint', 'resume'])
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--host', required=True, choices=['claude', 'codex'])
    parser.add_argument('--session')
    parser.add_argument('--cwd')
    parser.add_argument('--id')
    a = parser.parse_args(argv)
    try:
        if a.mode == 'hook':
            raw = sys.stdin.buffer.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError('hook payload too large')
            value = event(a.profile, a.host, json.loads(raw, object_pairs_hook=pairs), os.environ.get('AI_FACTORY_HANDOFF'))
            if value:
                print(json.dumps(value, ensure_ascii=False))
        else:
            profile = load_profile(a.profile)
            root = enrolled(profile, a.host, a.session, a.cwd)
            if root is None:
                raise ValueError('manual operation outside enrolled root')
            store = Path(profile['store'])
            if a.mode == 'checkpoint':
                raw = sys.stdin.buffer.read(65537)
                if len(raw) > 65536:
                    raise ValueError('summary too large')
                print(guard.checkpoint(store, a.host, a.session, root, json.loads(raw, object_pairs_hook=pairs)))
            else:
                print(guard.resume(store, a.id, a.host, a.session, root))
    except LockBusy:
        print(guard.DEFERRED, file=sys.stderr)
        return 75
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        # No private data, command, path or parser error echo. Outcome may follow a persisted claim.
        message = ('AI Factory handoff BLOCKED: input, enrollment, snapshot, or state validation failed. '
                   'No delivery is confirmed. If interrupted after a claim, OUTCOME_UNCERTAIN; '
                   'reconcile the exact ID manually, never clear claims or replay automatically.')
        if a.mode == 'hook':
            print(json.dumps({'systemMessage': message}))
        else:
            print(message, file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
