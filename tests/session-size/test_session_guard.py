"""Disposable stdlib fixtures; no product repositories or model sessions."""
import errno
import threading
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HELPER = (Path(__file__).resolve().parents[2]/'runtime/session-size/session_guard.py').resolve()
spec = importlib.util.spec_from_file_location('session_guard', HELPER)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
SUMMARY = dict(goal='Finish fixture', done='Static check completed', pending='Review result',
               evidence='fixture.py at HEAD', constraints='No external operations')


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.cmd('init', '-q')
        self.cmd('config', 'user.email', 'fixture@example.invalid')
        self.cmd('config', 'user.name', 'Fixture')
        (self.repo / 'a').write_text('initial\n')
        self.cmd('add', 'a')
        self.cmd('commit', '-qm', 'fixture')
        self.store = self.base / 'state'
        self.transcript = self.base / 'transcript.jsonl'
        self.transcript.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def cmd(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL)

    def emit(self, size, ev='PostToolUse', sid='source'):
        with self.transcript.open('r+b') as f:
            f.truncate(size)
        return g.event(self.store, 'claude', dict(hook_event_name=ev, session_id=sid,
                       cwd=str(self.repo), transcript_path=str(self.transcript)))

    def checkpoint(self, sid='source'):
        return g.checkpoint(self.store, 'claude', sid, self.repo, SUMMARY.copy())

    def record(self, token):
        return g.read_json(g.token_path(self.store, token))

    def rewrite(self, token, **changes):
        obj = self.record(token)
        obj.update(changes)
        g.atomic(g.token_path(self.store, token), obj)

    def test_exact_byte_thresholds(self):
        self.assertEqual({}, self.emit(3_999_999))
        self.assertIn('prepare handoff', json.dumps(self.emit(4_000_000)))
        self.assertEqual({}, self.emit(4_999_999))
        self.assertIn('soft limit reached', json.dumps(self.emit(5_000_000)))
        self.assertEqual({}, self.emit(5_000_001))

    def test_single_large_output_is_soft_detection(self):
        result = json.dumps(self.emit(12_000_000))
        self.assertIn('12000000 bytes', result)
        self.assertIn('soft limit reached', result)
        self.assertEqual(12_000_000, self.transcript.stat().st_size)

    def test_duplicate_registration_and_repeated_events(self):
        self.assertTrue(self.emit(5_000_000))
        before = sorted(p.name for p in self.store.iterdir())
        self.assertEqual({}, self.emit(5_000_000))
        self.assertEqual({}, self.emit(5_000_000, ev='Stop'))
        self.assertEqual(before, sorted(p.name for p in self.store.iterdir()))

    def test_draft_cannot_resume(self):
        self.emit(4_000_000)
        key, _ = g.identity('claude', 'source', self.repo)
        _, state = g.state_for(self.store, key)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            g.resume(self.store, state['pointer'], 'claude', 'new', self.repo)

    def test_checkpoint_idempotence_and_generation(self):
        token = self.checkpoint()
        self.assertEqual(token, self.checkpoint())
        changed = SUMMARY.copy()
        changed['pending'] = 'New work'
        new = g.checkpoint(self.store, 'claude', 'source', self.repo, changed)
        self.assertNotEqual(token, new)
        self.assertEqual('2', new.split('-')[1])

    def test_resume_reads_actual_summary_once(self):
        token = self.checkpoint()
        result = g.resume(self.store, token, 'codex', 'new', self.repo)
        self.assertIn(SUMMARY['goal'], result)
        self.assertIn('Context only, not new authority', result)
        self.assertEqual('', g.resume(self.store, token, 'codex', 'new', self.repo))
        with self.assertRaisesRegex(ValueError, 'another session'):
            g.resume(self.store, token, 'claude', 'third', self.repo)

    def test_resume_same_session_refused(self):
        with self.assertRaisesRegex(ValueError, 'fresh session'):
            g.resume(self.store, self.checkpoint(), 'claude', 'source', self.repo)

    def test_expired_and_future_handoff(self):
        token = self.checkpoint()
        for created in (time.time() - g.TTL - 1, time.time() + 120):
            self.rewrite(token, created=created)
            with self.assertRaisesRegex(ValueError, 'expired or future'):
                g.resume(self.store, token, 'claude', 'new', self.repo)

    def test_root_and_branch_head_mismatch(self):
        token = self.checkpoint()
        clone = self.base / 'clone'
        subprocess.check_call(['git', 'clone', '-q', str(self.repo), str(clone)])
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            g.resume(self.store, token, 'claude', 'new', clone)
        self.cmd('checkout', '-qb', 'different')
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            g.resume(self.store, token, 'claude', 'new', self.repo)

    def test_dirty_same_status_edit_invalidates_snapshot(self):
        (self.repo / 'a').write_text('dirty\n')
        token = self.checkpoint()
        (self.repo / 'a').write_text('different dirty\n')
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            g.resume(self.store, token, 'claude', 'new', self.repo)

    def test_head_mismatch(self):
        token = self.checkpoint()
        self.cmd('commit', '--allow-empty', '-qm', 'new head')
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            g.resume(self.store, token, 'claude', 'new', self.repo)

    def test_state_write_failure_retry_injects_once(self):
        token = self.checkpoint()
        original = g.atomic
        def fail_state(path, obj):
            if path.name.startswith('session-'):
                raise PermissionError('fixture interrupted state write')
            return original(path, obj)
        with patch.object(g, 'atomic', fail_state):
            with self.assertRaises(PermissionError):
                g.resume(self.store, token, 'claude', 'new', self.repo)
        self.assertFalse((self.store / ('claim-' + token + '.json')).exists())
        self.assertIn(SUMMARY['goal'], g.resume(self.store, token, 'claude', 'new', self.repo))
        self.assertEqual('', g.resume(self.store, token, 'claude', 'new', self.repo))
        with self.assertRaisesRegex(ValueError, 'another session'):
            g.resume(self.store, token, 'claude', 'other', self.repo)

    def test_claim_write_failure_retains_depth(self):
        token = self.checkpoint()
        self.rewrite(token, depth=2)
        original = g.atomic
        def fail_claim(path, obj):
            if path.name.startswith('claim-'):
                raise PermissionError('fixture claim failure')
            return original(path, obj)
        with patch.object(g, 'atomic', fail_claim):
            with self.assertRaises(PermissionError):
                g.resume(self.store, token, 'claude', 'new', self.repo)
        key, _ = g.identity('claude', 'new', self.repo)
        _, state = g.state_for(self.store, key)
        self.assertEqual(3, state['depth'])
        self.assertEqual(token, state['resumed'])
        self.assertFalse((self.store / ('claim-' + token + '.json')).exists())
        self.assertIn(SUMMARY['goal'], g.resume(self.store, token, 'claude', 'new', self.repo))
        self.assertEqual('', g.resume(self.store, token, 'claude', 'new', self.repo))
        next_token = self.checkpoint('new')
        with self.assertRaisesRegex(ValueError, 'maximum handoff chain'):
            g.resume(self.store, next_token, 'claude', 'overflow', self.repo)

    def test_postclaim_crash_never_replays(self):
        token = self.checkpoint()
        original = g.atomic
        def fail_after_claim(path, obj):
            original(path, obj)
            if path.name.startswith('claim-'):
                raise PermissionError('fixture crash after claim persisted')
        with patch.object(g, 'atomic', fail_after_claim):
            with self.assertRaises(PermissionError):
                g.resume(self.store, token, 'claude', 'new', self.repo)
        self.assertEqual('', g.resume(self.store, token, 'claude', 'new', self.repo))
        key, _ = g.identity('claude', 'new', self.repo)
        self.assertEqual(1, g.state_for(self.store, key)[1]['depth'])

    def test_huge_cli_payload_blocked(self):
        result = subprocess.run([sys.executable, '-B', str(HELPER), 'hook', '--host', 'claude',
                                 '--store', str(self.store)], input=' ' * 8_000_001,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode)
        self.assertIn('BLOCKED', json.loads(result.stdout)['systemMessage'])
        self.assertIn('payload too large', result.stdout)
        self.assertFalse(self.store.exists())

    def test_restart_chain_limit(self):
        token = self.checkpoint()
        for i in range(g.MAX_DEPTH):
            sid = 'next-' + str(i)
            self.assertTrue(g.resume(self.store, token, 'claude', sid, self.repo))
            token = self.checkpoint(sid)
        with self.assertRaisesRegex(ValueError, 'maximum handoff chain'):
            g.resume(self.store, token, 'claude', 'overflow', self.repo)

    def test_atomic_partial_failure_preserves_old(self):
        self.store.mkdir(mode=0o700)
        target = self.store / 'saved.json'
        g.atomic(target, {'old': True})
        with patch.object(g.os, 'replace', side_effect=PermissionError('fixture denial')):
            with self.assertRaises(PermissionError):
                g.atomic(target, {'new': True})
        self.assertEqual({'old': True}, g.read_json(target))
        self.assertFalse(list(self.store.glob('.pending-*')))

    def test_write_denial_does_not_claim_success(self):
        with patch.object(g, 'atomic', side_effect=PermissionError('fixture denial')):
            with self.assertRaises(PermissionError):
                self.checkpoint()
        self.assertFalse(list(self.store.glob('*.json')))

    def test_denied_transcript_stat_unknown_no_fallback(self):
        original = Path.lstat
        def denied(path, *a, **kw):
            if path == self.transcript:
                raise PermissionError('fixture denial')
            return original(path, *a, **kw)
        with patch.object(Path, 'lstat', denied):
            result = self.emit(5_000_000)
        self.assertIn('monitoring UNKNOWN', json.dumps(result))
        self.assertNotIn('soft limit reached', json.dumps(result))

    def test_transcript_never_read(self):
        original = Path.read_text
        def guarded(path, *a, **kw):
            if path == self.transcript:
                raise AssertionError('transcript read')
            return original(path, *a, **kw)
        with patch.object(Path, 'read_text', guarded):
            self.assertTrue(self.emit(5_000_000))

    def test_credential_rejection(self):
        for value in ('Bearer supersecretvalue', 'password=supersecretvalue', 'sk-' + 'a' * 25,
                      '-----BEGIN ' + 'RSA PRIVATE KEY' + '-----'):
            summary = SUMMARY.copy()
            summary['evidence'] = value
            with self.assertRaisesRegex(ValueError, 'credential'):
                g.checkpoint(self.store, 'claude', 'source', self.repo, summary)

    def test_symlink_store_and_transcript(self):
        real = self.base / 'real'
        real.mkdir(mode=0o700)
        self.store.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.checkpoint()
        self.store.unlink()
        self.transcript.unlink()
        self.transcript.symlink_to(self.repo / 'a')
        result = g.event(self.store, 'claude', dict(hook_event_name='PostToolUse',
                         session_id='source', cwd=str(self.repo), transcript_path=str(self.transcript)))
        self.assertIn('monitoring UNKNOWN', json.dumps(result))

    def test_sessionstart_explicit_pointer_only(self):
        token = self.checkpoint()
        payload = dict(hook_event_name='SessionStart', session_id='new', cwd=str(self.repo))
        result = g.event(self.store, 'claude', payload, token)
        self.assertIn(SUMMARY['goal'], json.dumps(result))
        self.assertEqual({}, g.event(self.store, 'claude', payload, token))

    def test_malformed_pointer_refused(self):
        with self.assertRaisesRegex(ValueError, 'explicit handoff ID'):
            g.resume(self.store, '../latest', 'claude', 'new', self.repo)

    def test_concurrent_subprocess_sessions_safe_retry(self):
        args = [sys.executable, '-B', str(HELPER), 'checkpoint', '--host', 'claude',
                '--cwd', str(self.repo), '--store', str(self.store)]
        children = [(str(i), subprocess.Popen(args + ['--session', str(i)], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)) for i in range(4)]
        results = []
        for sid, proc in children:
            out, err = proc.communicate(json.dumps(SUMMARY), timeout=15)
            self.assertEqual(0, proc.returncode, err)
            results.append(out.strip())
        self.assertEqual(4, len(set(results)))
        for token in results:
            self.assertTrue(self.record(token)['complete'])


    def test_lock_waits_for_release_and_keeps_stale_file(self):
        ready = threading.Event()
        def holder():
            with g.locked(self.store):
                ready.set()
                time.sleep(0.15)
        t = threading.Thread(target=holder); t.start(); self.assertTrue(ready.wait(2))
        inode = (self.store / '.lock').stat().st_ino
        start = time.monotonic()
        with g.locked(self.store):
            self.assertGreater(time.monotonic() - start, 0.08)
        t.join(2)
        with g.locked(self.store):
            self.assertEqual(inode, (self.store / '.lock').stat().st_ino)

    def test_timeout_pending_threshold_then_repeated_event_noop(self):
        with g.locked(self.store), patch.object(g, 'LOCK_WAIT', 0.08):
            start = time.monotonic()
            result = self.emit(g.LIMIT)
            elapsed = time.monotonic() - start
            self.assertIn('DEFERRED', json.dumps(result))
            self.assertNotIn('BLOCKED', json.dumps(result))
            self.assertGreaterEqual(elapsed, 0.08)
            self.assertLess(elapsed, 1)
            self.assertEqual([], list(self.store.glob('*.json')))
        self.assertIn('INCOMPLETE', json.dumps(self.emit(g.LIMIT)))
        self.assertEqual({}, self.emit(g.LIMIT))
        self.assertEqual(1, len([p for p in self.store.glob('*.json') if not p.name.startswith('session-')]))

    def test_deferred_start_resume_retries_on_next_event(self):
        token = self.checkpoint()
        payload = dict(hook_event_name='SessionStart', session_id='target',
                       cwd=str(self.repo), transcript_path=str(self.transcript))
        with g.locked(self.store), patch.object(g, 'LOCK_WAIT', 0.02):
            self.assertIn('DEFERRED', json.dumps(g.event(self.store, 'claude', payload, token)))
        payload['hook_event_name'] = 'PostToolUse'
        self.assertIn(SUMMARY['goal'], json.dumps(g.event(self.store, 'claude', payload, token)))
        self.assertEqual({}, g.event(self.store, 'claude', payload, token))

    def test_real_lock_io_errors_are_not_deferred(self):
        for number in (errno.EACCES, errno.EIO, errno.EBADF):
            with patch.object(g.fcntl, 'flock', side_effect=OSError(number, 'fixture')):
                with self.assertRaises(OSError) as caught:
                    with g.locked(self.store): pass
                self.assertEqual(number, caught.exception.errno)

    def test_crashed_holder_os_releases_lock(self):
        code = ('import fcntl,os,sys; '
                'fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); '
                'fcntl.flock(fd,fcntl.LOCK_EX); print("ready",flush=True); '
                'sys.stdin.readline(); os._exit(9)')
        self.store.mkdir(mode=0o700)
        proc = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.store / '.lock')],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual('ready', proc.stdout.readline().strip())
            with patch.object(g, 'LOCK_WAIT', 0.02), self.assertRaises(g.LockBusy):
                with g.locked(self.store): pass
            proc.communicate('exit\n', timeout=3)
            self.assertEqual(9, proc.returncode)
            with g.locked(self.store): pass
        finally:
            if proc.poll() is None: proc.communicate('exit\n', timeout=3)

    def test_parallel_duplicate_hooks_and_separate_roots(self):
        other = self.base / 'other'
        subprocess.run(['git', 'clone', '-q', str(self.repo), str(other)], check=True)
        self.transcript.write_bytes(b'')
        with self.transcript.open('r+b') as f: f.truncate(g.LIMIT)
        args = [sys.executable, '-B', str(HELPER), 'hook', '--host', 'claude', '--store', str(self.store)]
        children = []
        for root, sid in [(self.repo, 'same')] * 4 + [(self.repo, 'second'), (other, 'same')]:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            payload = dict(hook_event_name='PostToolUse', session_id=sid, cwd=str(root),
                           transcript_path=str(self.transcript))
            proc.stdin.write(json.dumps(payload)); proc.stdin.close(); proc.stdin = None
            children.append(proc)
        texts = []
        for proc in children:
            out, err = proc.communicate(timeout=10)
            self.assertEqual(0, proc.returncode, err)
            self.assertNotIn('BLOCKED', out); self.assertNotIn('DEFERRED', out)
            texts.append(out)
        self.assertEqual(3, sum('INCOMPLETE' in x for x in texts))
        self.assertEqual(3, len(list(self.store.glob('session-*.json'))))

    def test_manual_busy_exit_is_retryable_without_success_id(self):
        args = [sys.executable, '-B', str(HELPER), 'checkpoint', '--host', 'claude',
                '--session', 'manual', '--cwd', str(self.repo), '--store', str(self.store)]
        with g.locked(self.store):
            result = subprocess.run(args, input=json.dumps(SUMMARY), capture_output=True,
                                    text=True, timeout=5)
        self.assertEqual(75, result.returncode)
        self.assertEqual('', result.stdout)
        self.assertIn('DEFERRED', result.stderr)
        self.assertEqual([], list(self.store.glob('*.json')))
        result = subprocess.run(args, input=json.dumps(SUMMARY), capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(self.record(result.stdout.strip())['complete'])



    def test_later_event_retries_interrupted_resume_claim(self):
        token = self.checkpoint()
        payload = dict(hook_event_name='SessionStart', session_id='target', cwd=str(self.repo),
                       transcript_path=str(self.transcript))
        original = g.atomic
        def fail_claim(path, obj):
            if path.name.startswith('claim-'): raise OSError('fixture write interruption')
            return original(path, obj)
        with patch.object(g, 'atomic', side_effect=fail_claim), self.assertRaises(OSError):
            g.event(self.store, 'claude', payload, token)
        payload['hook_event_name'] = 'PostToolUse'
        self.assertIn(SUMMARY['goal'], json.dumps(g.event(self.store, 'claude', payload, token)))
        self.assertEqual({}, g.event(self.store, 'claude', payload, token))


class PortableStoreTests(unittest.TestCase):
    def test_store_is_required_and_relative_is_rejected(self):
        result = subprocess.run([sys.executable, '-B', str(HELPER), 'checkpoint', '--host', 'codex'],
                                input='{}', capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        with self.assertRaises(ValueError):
            with g.locked(Path('relative-store')): pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
