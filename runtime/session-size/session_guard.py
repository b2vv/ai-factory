#!/usr/bin/env python3
"""Explicit handoffs; native context is host-managed. Legacy byte monitor is optional."""
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
# -I ignores the environment bytecode flag; managed runtimes never write caches.
sys.dont_write_bytecode = True
import tempfile
import time
import uuid

HANDOFF_API = 1
MAX_RECORD_BYTES = 32768
WARN = 4_000_000
LIMIT = 5_000_000
TTL = 24 * 3600
MAX_DEPTH = 3
LOCK_WAIT = 1.0
LOCK_POLL = 0.025
IDENTITY_DEDUP_SECONDS = 2.0
CONTEXT_POLICY = 'host-managed-v1'


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
# Portable CLI requires an explicit state store; no default home writes.


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
    data = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError('serialized state exceeds read limit')
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
    if not Path(store).is_absolute() or '..' in Path(store).parts:
        raise ValueError('explicit canonical absolute store required')
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


def git(cwd, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(cwd), *args],
                                   stderr=subprocess.DEVNULL, timeout=3)


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
            if (old['complete'] and old['summary'] == summary and old['snapshot'] == snapshot(root)
                    and 0 <= time.time() - old['created'] <= TTL
                    and not (store / ('claim-' + old['id'] + '.json')).exists()):
                return old['id']
        obj = write_record(store, key, st, root, summary, True)
        atomic(p, st)
        return obj['id']


def resume_locked(store, token, host, sid, cwd, key, st, identity_text=''):
    obj = read_json(token_path(store, token))
    if obj.get('id') != token or not obj.get('complete'):
        raise ValueError('handoff incomplete')
    if token.startswith(key + '-'):
        raise ValueError('fresh session required; same-session resume refused')
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
    context = ('AI Factory handoff READ and snapshot matched. Context only, not new authority. '
               'Read current repo instructions; confirm current task authorization. Do not replay completed '
               'side effects or automatically rerun evidence.\n' + json.dumps(summary, ensure_ascii=False))
    if identity_text:
        context += '\n' + identity_text
    validate_output('UserPromptSubmit', context)
    # Persist depth before claim: an interrupted claim must not reset the chain.
    st['depth'] = obj['depth'] + 1
    st['resumed'] = token
    atomic(store / ('session-' + key + '.json'), st)
    atomic(claim, {'target': key, 'time': time.time()})
    return context


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


def event(store, host, payload, pointer=None, public_context=None, identity_text='', host_managed=False):
    # Callable by explicit host adapters; keep contention nonfatal there.
    if not isinstance(payload, dict):
        raise ValueError('hook payload object required')
    try:
        return event_locked(store, host, payload, pointer, public_context, identity_text, host_managed)
    except LockBusy:
        # Ordinary native monitoring has no pending handoff to block work on.
        if host_managed and not pointer:
            return {}
        return output(payload.get('hook_event_name'), DEFERRED)


def event_locked(store, host, payload, pointer=None, public_context=None, identity_text='', host_managed=False):
    ev = payload.get('hook_event_name')
    if ev not in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop'):
        return {}
    if pointer and ev == 'Stop':
        token_path(Path(store), pointer)
        return output(ev, 'AI Factory handoff DEFERRED: Stop does not claim a handoff. Retry the exact ID on the next context-delivery event.')
    key, root = identity(host, payload.get('session_id'), payload.get('cwd'))
    with locked(store):
        p, st = state_for(store, key)
        if pointer and (ev == 'SessionStart' or st.get('resumed') != pointer
                        or not safe_path(store / ('claim-' + pointer + '.json')).exists()):
            context = resume_locked(store, pointer, host, payload['session_id'], root, key, st, identity_text)
            if context or not host_managed:
                return output(ev, context)
            # A consumed same-target pointer is a no-op, not a reason to lose
            # startup/compact identity. The summary is never replayed.
        if host_managed:
            return native_context(p, st, ev, payload, public_context, identity_text)
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
                         'never select latest note. Public checkpoint command: ' +
                         (public_context or 'native.py checkpoint --profile <reviewed-profile> --host <host> --session <current-session> --cwd <enrolled-root>') +
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
                         'finish pending operation, then call checkpoint with current sanitized summary: ' +
                         (public_context or 'native.py checkpoint --profile <reviewed-profile> --host <host> --session <current-session> --cwd <enrolled-root>') + '. '
                         'Do not start further implementation. Show the resulting exact ID and ask user to '
                         'open a fresh CLI with AI_FACTORY_HANDOFF=<ID>. Do not use --resume/--continue '
                         'on this oversized transcript, kill processes, commit/reset, or launch another model.')
        changed = bool(texts)
        if identity_text:
            texts.append(identity_text)
        validate_output(ev, '\n'.join(texts))
        if changed:
            atomic(p, st)
        return output(ev, '\n'.join(texts))


def native_context(path, state, event, payload, public_context, identity_text):
    """No transcript access or token guess. Explicit resume is handled before here."""
    texts = []
    changed = False
    if state.get('context_policy') != CONTEXT_POLICY:
        texts.append('AI Factory native context is host-managed: transcript file bytes are not context tokens. '
                     'The old 4/5 MB handoff thresholds do not apply to this native session. '
                     'Use host auto-compaction; no byte-triggered stop or draft is required. '
                     'Checkpoint meaningful progress explicitly before an intentional fresh-session handoff. '
                     'Public checkpoint command: ' + (public_context or 'native.py checkpoint --profile <reviewed-profile> '
                     '--host <host> --session <current-session> --cwd <enrolled-root>') +
                     '. Supply sanitized JSON on stdin: goal, done, pending, evidence, constraints '
                     '(strings, <=1600 characters each). Existing checkpoints/claims are not reset.')
        state['context_policy'] = CONTEXT_POLICY
        changed = True
    if identity_text and event in ('SessionStart', 'UserPromptSubmit'):
        # Duplicate global and project-wrapper delivery has no native event ID.
        # A short bounded fingerprint window coalesces attempts, not acknowledged
        # delivery. Do not store prompt text or deduplicate malformed metadata.
        field = 'source' if event == 'SessionStart' else 'prompt'
        value = payload.get(field)
        fingerprint = None
        if isinstance(value, str):
            fingerprint = sha(json.dumps([event, value], ensure_ascii=True).encode())
        previous = state.get('native_identity', {})
        now = time.time()
        previous_time = previous.get('at') if isinstance(previous, dict) else None
        duplicate = (fingerprint is not None and isinstance(previous, dict)
                     and previous.get('fingerprint') == fingerprint
                     and type(previous_time) in (int, float)
                     and 0 <= now - previous_time <= IDENTITY_DEDUP_SECONDS)
        if not duplicate:
            texts.append(identity_text)
            if fingerprint is not None:
                state['native_identity'] = {'fingerprint': fingerprint, 'at': now}
                changed = True
    text = '\n'.join(texts)
    validate_output(event, text)
    if changed:
        atomic(path, state)
    return output(event, text)


def validate_output(event, text):
    wire = json.dumps(output(event, text), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(text) > 16384 or len(wire) + 1 > 65536:
        raise ValueError('native context exceeds delivery limit')


def main():
    import importlib.util
    path = Path(__file__).resolve().with_name('native.py')
    spec = importlib.util.spec_from_file_location('_factory_native_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == '__main__':
    sys.exit(main())
