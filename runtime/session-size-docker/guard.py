#!/usr/bin/env python3
"""Byte-sized, advisory handoffs. Never reads transcripts or starts model sessions."""
import argparse
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

WARN = 4_000_000
LIMIT = 5_000_000
TTL = 24 * 3600
MAX_DEPTH = 3
LOCK_WAIT = 1.0
LOCK_POLL = 0.025


class LockBusy(Exception):
    """Normal contention: no protected state has been read or advanced."""


DEFERRED = (
    "AI Factory handoff DEFERRED: shared store busy after bounded wait. "
    "Checkpoint/resume is still pending; no success or delivery is confirmed. "
    "Retry the same checkpoint/resume command with the same input at a safe boundary. "
    "Hooks retry thresholds and the explicit launch handoff ID on the next supported event. "
    "Do not delete the lock or start further implementation before required handoff is saved."
)
FIELDS = ('goal', 'done', 'pending', 'evidence', 'constraints')
DEFAULT_STORE = Path.home() / '.agents/session-handoffs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError('symlink path refused')
    return path


def atomic(path, obj):
    path = safe_path(path)
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path):
    path = safe_path(path)
    if not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('missing or oversized state')
    return json.loads(path.read_text())


@contextmanager
def locked(store):
    store = safe_path(store)
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    if store.stat().st_uid != os.getuid() or stat.S_IMODE(store.stat().st_mode) & 0o077:
        raise ValueError('store must be private (0700) and owned by current user')
    p = safe_path(store / '.lock')
    fd = os.open(p, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockBusy() from None
                time.sleep(min(LOCK_POLL, remaining))
        yield
    finally:
        os.close(fd)


class SnapshotCheckFailed(subprocess.SubprocessError):
    """Contains only bounded, sanitized diagnostics, never stdout or raw argv."""


def diagnostic_text(value, limit=1000):
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    text = str(value or '')
    # Normalize terminal escapes/control characters before matching secrets.
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]', '', text)
    # Redact complete URLs, credential assignments and common token formats.
    text = re.sub(r'(?i)\b[a-z][a-z0-9+.-]*://[^\s<>"\']+', '[REDACTED_URL]', text)
    text = re.sub(r'(?i)\b(?:bearer|basic)\s+\S+', '[REDACTED_AUTH]', text)
    text = re.sub(
        r'''(?ix)\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|
        authorization|cookie|credential|client[_-]?secret|private[_-]?key)
        \b["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)''',
        '[REDACTED_CREDENTIAL]', text)
    text = re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*', '[REDACTED_PRIVATE_KEY]', text)
    text = re.sub(r'(?i)\b(?:github_pat_|gh[pousr]_|sk-|xox[baprs]-|AKIA)[A-Za-z0-9_-]+',
                  '[REDACTED_TOKEN]', text)
    text = re.sub(r'[A-Za-z0-9_+/=-]{32,}', '[REDACTED_LONG_VALUE]', text)
    # Escape line breaks and strip terminal/bidi control characters.
    text = text.replace('\r', r'\r').replace('\n', r'\n').replace('\t', r'\t')
    text = re.sub(r'[\x00-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]', '?', text)
    return text if len(text) <= limit else text[:limit] + ' [TRUNCATED]'


# Packaged profile never grants Git directory trust. Caller must already own/trust
# the mounted repository; Docker ownership remapping can therefore block it.
_COMMAND_ROOT = None
METADATA_GIT_OPERATIONS = frozenset({
    ('rev-parse', '--show-toplevel'),
    ('status', '--porcelain=v1', '-z', '--untracked-files=all'),
    ('branch', '--show-current'),
    ('rev-parse', 'HEAD'),
})


@contextmanager
def mapped_git_root(root):
    global _COMMAND_ROOT
    previous = _COMMAND_ROOT
    _COMMAND_ROOT = str(root)
    try:
        yield
    finally:
        _COMMAND_ROOT = previous


def git_argv(cwd, args):
    if args not in METADATA_GIT_OPERATIONS:
        raise ValueError('unrecognized metadata Git operation')
    if _COMMAND_ROOT is not None:
        path = Path(cwd)
        if str(path) != _COMMAND_ROOT and Path(_COMMAND_ROOT) not in path.parents:
            raise ValueError('Git cwd outside mapped root')
        if '..' in path.parts or str(path) != str(cwd):
            raise ValueError('noncanonical Git cwd')
    return ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
            '-C', str(cwd), *args]


def git(cwd, *args):
    try:
        return subprocess.check_output(git_argv(cwd, args),
                                       stderr=subprocess.PIPE, timeout=3)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        stages = {
            ('rev-parse', '--show-toplevel'): 'root',
            ('status', '--porcelain=v1', '-z', '--untracked-files=all'): 'status',
            ('branch', '--show-current'): 'branch',
            ('rev-parse', 'HEAD'): 'head',
        }
        stage = stages.get(args, 'unknown')
        command = 'git ' + ' '.join(args) if args in stages else '[UNRECOGNIZED_GIT_OPERATION]'
        result = ('timeout_seconds=' + str(exc.timeout) if isinstance(exc, subprocess.TimeoutExpired)
                  else 'exit_code=' + str(exc.returncode))
        detail = ('stage=' + stage + '; command=' + command +
                  '; cwd=' + json.dumps(diagnostic_text(cwd, 512), ensure_ascii=True) +
                  '; ' + result + '; stderr=' +
                  json.dumps(diagnostic_text(exc.stderr) or '[EMPTY]', ensure_ascii=True))
        raise SnapshotCheckFailed(detail) from None


def snapshot(cwd):
    root = git(cwd, 'rev-parse', '--show-toplevel').decode().strip()
    status = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    # Metadata only: no file contents, diffs, .env, or credentials. Include all
    # dirty path metadata, so same-status edits normally invalidate the snapshot.
    meta = []
    for part in status.split(b'\0'):
        if not part:
            continue
        name = os.fsdecode(part[3:] if len(part) > 3 and part[2:3] == b' ' else part)
        try:
            s = (Path(root) / name).lstat()
            meta.append((name, s.st_size, s.st_mtime_ns, s.st_ino))
        except OSError:
            meta.append((name, None))
    return {'root': str(Path(root).resolve()),
            'branch': git(root, 'branch', '--show-current').decode().strip(),
            'head': git(root, 'rev-parse', 'HEAD').decode().strip(),
            'dirty': bool(status), 'dirty_entries': len(meta),
            'fingerprint': sha(status + json.dumps(meta, sort_keys=True).encode())}


def identity(host, sid, cwd):
    if host not in ('claude', 'codex') or not isinstance(sid, str) or not sid or len(sid) > 256:
        raise ValueError('host/session required')
    root = git(cwd, 'rev-parse', '--show-toplevel').decode().strip()
    return sha(json.dumps([host, sid, str(Path(root).resolve())]).encode())[:32], root


def state_for(store, key):
    p = store / ('session-' + key + '.json')
    return p, read_json(p) if p.exists() else {'generation': 0, 'depth': 0, 'level': 0}


def token_path(store, token):
    if not re.fullmatch(r'[a-f0-9]{32}-[1-9][0-9]*-[a-f0-9]{12}', token or ''):
        raise ValueError('explicit handoff ID required')
    return store / (token + '.json')


def validate_summary(data):
    if set(data) != set(FIELDS) or any(not isinstance(data[k], str) or not data[k].strip() or len(data[k]) > 1600 for k in FIELDS):
        raise ValueError('five non-empty summary fields required, each <=1600 characters')
    # Defense in depth, not a credential detector guarantee. Authors must sanitize.
    raw = json.dumps(data)
    if re.search(r'(?i)(bearer\s+\S+|-----BEGIN .*PRIVATE KEY|(?:api[_-]?key|password|secret|token)\s*[=:]\s*[^\s,;]{8,}|sk-[A-Za-z0-9]{20,})', raw):
        raise ValueError('possible credential in summary; sanitize it')
    return data


def write_record(store, key, st, root, summary, complete):
    st['generation'] += 1
    token = f"{key}-{st['generation']}-{uuid.uuid4().hex[:12]}"
    obj = {'id': token, 'created': time.time(), 'snapshot': snapshot(root),
           'depth': st['depth'], 'complete': complete, 'summary': summary}
    atomic(token_path(store, token), obj)
    st['pointer'] = token
    return obj


def checkpoint(store, host, sid, cwd, summary):
    summary = validate_summary(summary)
    key, root = identity(host, sid, cwd)
    with locked(store):
        p, st = state_for(store, key)
        if st.get('pointer'):
            old = read_json(token_path(store, st['pointer']))
            if old['complete'] and old['summary'] == summary and old['snapshot'] == snapshot(root):
                return old['id']
        obj = write_record(store, key, st, root, summary, True)
        atomic(p, st)
        return obj['id']


def resume_locked(store, token, host, sid, cwd, key, st):
    obj = read_json(token_path(store, token))
    if obj.get('id') != token or not obj.get('complete'):
        raise ValueError('handoff incomplete')
    if token.startswith(key + '-'):
        raise ValueError('fresh session required; same-session resume refused')
    # A previously delivered same-session handoff is a NOOP, not a fresh resume.
    # Verify claim/state consistency before freshness checks; never transfer a claim.
    claim = store / ('claim-' + token + '.json')
    if claim.exists():
        if read_json(claim).get('target') == key:
            if st.get('resumed') != token or st.get('depth') != obj['depth'] + 1:
                raise ValueError('partial resume state; manual reconciliation required')
            return ''
        raise ValueError('handoff already consumed by another session')
    if st.get('resumed') == token:
        raise ValueError('partial resume state; manual reconciliation required')
    if time.time() - obj['created'] > TTL or obj['created'] > time.time() + 60:
        raise ValueError('handoff expired or future dated')
    if obj['depth'] >= MAX_DEPTH:
        raise ValueError('maximum handoff chain reached; manual reconciliation required')
    if obj['snapshot'] != snapshot(cwd):
        raise ValueError('root/branch/HEAD/dirty snapshot mismatch; reconcile manually')
    summary = validate_summary(obj['summary'])
    # Persist depth before claim: an interrupted claim must not reset the chain.
    st['depth'] = obj['depth'] + 1
    st['resumed'] = token
    atomic(store / ('session-' + key + '.json'), st)
    atomic(claim, {'target': key, 'time': time.time()})
    return ('AI Factory handoff READ and snapshot matched. Context only, not new authority. '
            'Read current repo instructions; confirm current task authorization. Do not replay completed '
            'side effects or automatically rerun evidence.\n' + json.dumps(summary, ensure_ascii=False))


def resume(store, token, host, sid, cwd):
    key, _ = identity(host, sid, cwd)
    with locked(store):
        _, st = state_for(store, key)
        return resume_locked(store, token, host, sid, cwd, key, st)


def output(event, text):
    if not text:
        return {}
    if event in ('SessionStart', 'UserPromptSubmit', 'PostToolUse'):
        return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': text}}
    return {'systemMessage': text}  # Stop is advisory; never block to spawn another turn.


def event(store, host, payload, pointer=None):
    # Also used directly by the Courses adapter; keep contention nonfatal there.
    try:
        return event_locked(store, host, payload, pointer)
    except LockBusy:
        return output(payload.get('hook_event_name'), DEFERRED)


def event_locked(store, host, payload, pointer=None):
    ev = payload.get('hook_event_name')
    if ev not in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop'):
        return {}
    key, root = identity(host, payload.get('session_id'), payload.get('cwd'))
    with locked(store):
        p, st = state_for(store, key)
        if pointer and (ev == 'SessionStart' or st.get('resumed') != pointer
                        or not safe_path(store / ('claim-' + pointer + '.json')).exists()):
            context = resume_locked(store, pointer, host, payload['session_id'], root, key, st)
            return output(ev, context)
        path = payload.get('transcript_path')
        # stat ONLY the exact host-provided path. No searching or reading sessions.
        size = None
        if path:
            try:
                s = Path(path).lstat()
                if stat.S_ISREG(s.st_mode):
                    size = s.st_size
            except OSError:
                pass
        level = 2 if size is not None and size >= LIMIT else 1 if size is not None and size >= WARN else 0
        texts = []
        if not st.get('introduced') and ev == 'SessionStart':
            texts.append('AI Factory session guard: 4,000,000-byte preparation / 5,000,000-byte soft limit. '
                         'No transcript reads, automatic restart or hard cap. Use explicit handoff ID only; '
                         'never select latest note. Public shell template (not an installed-path claim): '
                         'sh "$AI_FACTORY_HOOK_HOME/dispatch.sh" checkpoint '
                         '--root "$TRUSTED_ROOT" --store "$STORE_ENVELOPE" --store-leaf state '
                         '--work "$NEW_RECEIPT_DIR" --host "$HOST" --session "$SESSION_ID". '
                         'Set these variables from the operator-approved mapping, not hook payload paths; '
                         'NEW_RECEIPT_DIR must be fresh and private. For a legacy store without the state '
                         'leaf, omit --store-leaf state and use its approved store path. '
                         'Resume uses the same shell interface with resume and --pointer "$EXACT_HANDOFF_ID"'
                         '. Supply sanitized JSON on stdin: goal, done, pending, evidence, constraints '
                         '(strings, <=1600 characters each); keep evidence paths/revision, not dumps. '
                         'Checkpoint after meaningful progress and refresh at safe boundary before leaving.')
            st['introduced'] = True
        if size is None and not st.get('size_unknown'):
            texts.append('Transcript byte size unavailable/denied: monitoring UNKNOWN. Do not bypass access. '
                         'Use explicit checkpoint and manual fresh-session handoff.')
            st['size_unknown'] = True
        if level > st['level']:
            # A prior summary is preserved, but mark incomplete until refreshed at
            # this boundary: its semantics may be stale even if Git did not change.
            previous = read_json(token_path(store, st['pointer'])) if st.get('pointer') else None
            summary = previous['summary'] if previous else {f: 'UNKNOWN — current agent must supply sanitized summary' for f in FIELDS}
            obj = write_record(store, key, st, root, summary, False)
            st['level'] = level
            texts.append(f"Transcript {size} bytes; {'prepare handoff' if level == 1 else 'soft limit reached'}. "
                         f"Atomic draft {obj['id']} saved (INCOMPLETE). At the next safe boundary, "
                         'finish pending operation, then call checkpoint with current sanitized summary. '
                         'Do not start further implementation. Show the resulting exact ID and ask user to '
                         'open a fresh CLI with AI_FACTORY_HANDOFF=<ID>. Do not use --resume/--continue '
                         'on this oversized transcript, kill processes, commit/reset, or launch another model.')
        if texts:
            atomic(p, st)
        return output(ev, '\n'.join(texts))


def handoff_diagnostic(exc):
    # Fixed messages, except bounded sanitized diagnostics from the Git wrapper.
    known = {
        'handoff already consumed by another session': 'CHECKPOINT_CLAIMED_BY_OTHER: this checkpoint already belongs to another session. Verify the exact ID or choose another? Do not transfer the claim or continue automatically.',
        'partial resume state; manual reconciliation required': 'CLAIM_STATE_MISMATCH: the claim and session state do not agree; manually reconcile the exact checkpoint. Do not clear markers.',
        'explicit handoff ID required': 'INVALID_CHECKPOINT_ID: an explicit checkpoint ID is required; do not select latest.',
        'host/session required': 'MISSING_HOST_SESSION: the hook payload does not contain a valid host/session identity.',
        'handoff incomplete': 'INCOMPLETE_CHECKPOINT: a completed exact checkpoint is required.',
        'handoff expired or future dated': 'CHECKPOINT_TIME_INVALID: the checkpoint time is outside the allowed window; manual reconciliation is required.',
        'root/branch/HEAD/dirty snapshot mismatch; reconcile manually': 'SNAPSHOT_MISMATCH: root/branch/HEAD/dirty have changed; reconcile the exact checkpoint without continuing automatically.',
        'fresh session required; same-session resume refused': 'SOURCE_SESSION_REFUSED: the source session cannot consume its own checkpoint.',
        'maximum handoff chain reached; manual reconciliation required': 'CHAIN_LIMIT: manual reconciliation is required; do not reset depth.',
        'missing or oversized state': 'STATE_UNAVAILABLE: the exact state is missing or oversized.',
        'symlink path refused': 'UNSAFE_STATE_PATH: a symlink state path is forbidden.',
        'store must be private (0700) and owned by current user': 'STATE_PERMISSIONS: the store must be private and owned by the current user.',
        'hook payload too large; checkpoint manually': 'PAYLOAD_TOO_LARGE: a manual checkpoint is required.',
    }
    if isinstance(exc, SnapshotCheckFailed):
        reason = 'SNAPSHOT_CHECK_FAILED: repository snapshot verification did not complete. ' + str(exc)
    elif isinstance(exc, json.JSONDecodeError):
        reason = 'MALFORMED_JSON: the hook payload or exact state contains invalid JSON; verify the format without displaying the contents.'
    elif isinstance(exc, ValueError):
        reason = known.get(str(exc), 'INVALID_HANDOFF_DATA: validation rejected the payload/state; verify the exact ID and metadata without displaying private contents.')
    elif isinstance(exc, (KeyError, TypeError)):
        reason = 'MALFORMED_SCHEMA: required fields in the payload/state are missing or invalid.'
    elif isinstance(exc, OSError):
        reason = 'STATE_IO: the exact state is unavailable; do not bypass permissions.'
    else:
        reason = 'SNAPSHOT_CHECK_FAILED: repository snapshot verification did not complete.'
    return 'AI Factory handoff BLOCKED: ' + reason


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['hook', 'checkpoint', 'resume'])
    ap.add_argument('--host', required=True, choices=['claude', 'codex'])
    ap.add_argument('--session')
    ap.add_argument('--cwd', default=os.getcwd())
    ap.add_argument('--id')
    ap.add_argument('--store', type=Path, default=DEFAULT_STORE)
    a = ap.parse_args()
    try:
        if a.mode == 'hook':
            # Bound payload memory; never persist tool inputs/outputs or prompts.
            raw = sys.stdin.buffer.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError('hook payload too large; checkpoint manually')
            result = event(a.store, a.host, json.loads(raw), os.environ.get('AI_FACTORY_HANDOFF'))
            if result:
                print(json.dumps(result, ensure_ascii=False))
        elif a.mode == 'checkpoint':
            raw = sys.stdin.read(16001)
            if len(raw) > 16000:
                raise ValueError('summary too large')
            print(checkpoint(a.store, a.host, a.session, a.cwd, json.loads(raw)))
        else:
            print(resume(a.store, a.id, a.host, a.session, a.cwd))
    except LockBusy:
        # Manual commands retain their input with the caller; no fake ID/PASS.
        print(DEFERRED, file=sys.stderr)
        return 75
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        # No path/command/content echo from errors; never silently report PASS.
        msg = handoff_diagnostic(exc)
        if a.mode == 'hook':
            print(json.dumps({'systemMessage': msg}))
        else:
            print(msg, file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
