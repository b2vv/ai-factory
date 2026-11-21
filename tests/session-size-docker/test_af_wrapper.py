"""af.sh convenience wrapper: path derivation, fresh receipt dir, mode mapping.

Delegate scripts (bind-session.sh / dispatch.sh) are replaced by stubs that record
their argv. This proves the wrapper's own logic WITHOUT Docker or a real daemon; the
native round-trip and real enrollment remain NOT exercised here.
"""
from pathlib import Path
SRC = Path(__file__).resolve().parents[2] / 'runtime/session-size-docker'
import os, shutil, subprocess, tempfile, unittest, sys

STUB = "#!/bin/sh\n{ printf '%s ' \"$0\"; printf '%s ' \"$@\"; printf '\\n'; } >> \"$LOG\"\ncat >/dev/null 2>&1 || :\nexit 0\n"


class AfWrapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.base = Path(self.tmp.name).resolve()
        self.code = self.base / 'code'
        self.code.mkdir()
        shutil.copy(SRC / 'af.sh', self.code / 'af.sh')
        for name in ('bind-session.sh', 'dispatch.sh'):
            (self.code / name).write_text(STUB)
            (self.code / name).chmod(0o755)
        self.home = self.base / 'afhome'
        self.repo = self.base / 'project'
        self.repo.mkdir()
        self.transcript = self.base / 'transcript.jsonl'
        self.transcript.write_text('x\n')
        self.log = self.base / 'calls.log'

    def tearDown(self):
        self.tmp.cleanup()

    def run_af(self, *args, stdin=b''):
        env = dict(os.environ, LOG=str(self.log), AF_HOME=str(self.home))
        return subprocess.run(['sh', str(self.code / 'af.sh'), *args],
                              input=stdin, capture_output=True, env=env)

    def last_call(self):
        return self.log.read_text().strip().splitlines()[-1]

    def test_relative_or_parent_home_refused(self):
        for home in [Path('relative'),self.base/'missing/../other']:
            self.home=home
            result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((self.base/'relative').exists());self.assertFalse((self.base/'other').exists())

    def test_regular_file_base_refused(self):
        self.home.write_text('synthetic');self.home.chmod(0o600)
        result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
        self.assertNotEqual(result.returncode,0);self.assertIn(b'BLOCKED directory required',result.stderr)

    def test_fifo_roots_refused_without_blocking(self):
        import signal
        self.home.mkdir(mode=0o700);os.mkfifo(self.home/'trusted-roots',mode=0o600)
        env=dict(os.environ,LOG=str(self.log),AF_HOME=str(self.home))
        proc=subprocess.Popen(['sh',str(self.code/'af.sh'),'enroll','--repo',str(self.repo),'--session','fresh','--transcript',str(self.transcript)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=self.base,start_new_session=True)
        try:out,err=proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.communicate();self.fail('FIFO roots blocked')
        self.assertNotEqual(proc.returncode,0);self.assertIn(b'unsafe trusted-roots',err)

    def test_base_named_trusted_roots_is_a_directory(self):
        self.home=self.base/'trusted-roots'
        for _ in range(2):
            result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
            self.assertEqual(result.returncode,0,result.stderr)

    def test_other_owner_refused_before_side_effects(self):
        from unittest.mock import patch
        self.home.mkdir(mode=0o700)
        shim=self.code/'python3'
        shim.write_text('#!'+sys.executable+'\nimport os,sys\nos.getuid=lambda: '+str(os.getuid()+1)+'\nsys.argv=sys.argv[1:]\nexec(compile(sys.stdin.read(),"<af-preflight>","exec"))\n')
        shim.chmod(0o755)
        with patch.dict(os.environ,PATH=str(self.code)+os.pathsep+os.environ.get('PATH','')):
            result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
        self.assertNotEqual(result.returncode,0);self.assertEqual(list(self.home.iterdir()),[])

    def test_public_base_refused_before_side_effects(self):
        self.home.mkdir(mode=0o755)
        result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
        self.assertNotEqual(result.returncode,0);self.assertEqual(list(self.home.iterdir()),[])

    def test_hardlinked_roots_not_modified(self):
        self.home.mkdir(mode=0o700);victim=self.base/'victim';victim.write_text('');victim.chmod(0o600);os.link(victim,self.home/'trusted-roots')
        result=self.run_af('enroll','--repo',str(self.repo),'--session','fresh','--transcript',str(self.transcript),'--approve-root')
        self.assertNotEqual(result.returncode,0);self.assertEqual(victim.read_text(),'')

    def test_symlink_base_refused_before_side_effects(self):
        victim=self.base/'victim';victim.mkdir(mode=0o700);self.home.symlink_to(victim,target_is_directory=True)
        result=self.run_af('continue','--repo',str(self.repo),'--session','fresh')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(list(victim.iterdir()),[])

    def test_enroll_refuses_to_trust_a_path_by_itself(self):
        # Naming --repo must NOT grant trust: without prior approval or --approve-root, refuse.
        r = self.run_af('enroll', '--repo', str(self.repo), '--session', 'S1',
                        '--transcript', str(self.transcript), '--host', 'codex')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(b'not an approved trusted root', r.stderr)
        self.assertFalse(self.log.exists())                 # bind-session.sh was never reached
        roots = self.home / 'trusted-roots'
        self.assertFalse(roots.exists() and str(self.repo.resolve()) in roots.read_text())

    def test_enroll_with_explicit_approval_records_and_binds(self):
        r = self.run_af('enroll', '--repo', str(self.repo), '--session', 'S1',
                        '--transcript', str(self.transcript), '--host', 'codex', '--approve-root')
        self.assertEqual(r.returncode, 0, r.stderr)
        roots = self.home / 'trusted-roots'
        self.assertEqual(roots.read_text().strip().splitlines()[-1], str(self.repo.resolve()))
        self.assertEqual(roots.stat().st_mode & 0o777, 0o600)
        call = self.last_call()
        self.assertIn('bind-session.sh', call)
        self.assertIn(str(self.home / 'registry'), call)
        self.assertIn(str(self.home / 'store-envelope'), call)
        self.assertTrue(call.rstrip().endswith(' state'))
        for d in ('registry', 'receipts', 'store-envelope'):
            self.assertEqual((self.home / d).stat().st_mode & 0o777, 0o700)

    def test_enroll_succeeds_when_root_already_approved(self):
        # A repo approved out of band (already in trusted-roots) enrolls without the flag.
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.home / 'trusted-roots').write_text(str(self.repo.resolve()) + '\n')
        (self.home / 'trusted-roots').chmod(0o600)
        r = self.run_af('enroll', '--repo', str(self.repo), '--session', 'S1',
                        '--transcript', str(self.transcript), '--host', 'codex')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('bind-session.sh', self.last_call())

    def test_checkpoint_uses_fresh_receipt_dir_and_derived_store(self):
        c1 = self.run_af('checkpoint', '--repo', str(self.repo), '--session', 'S1', stdin=b'{}')
        work1 = self._work_arg(self.last_call())
        c2 = self.run_af('checkpoint', '--repo', str(self.repo), '--session', 'S1', stdin=b'{}')
        work2 = self._work_arg(self.last_call())
        self.assertEqual((c1.returncode, c2.returncode), (0, 0))
        self.assertNotEqual(work1, work2)                       # fresh per operation
        self.assertTrue(work1.startswith(str(self.home / 'receipts')))
        self.assertIn('dispatch.sh checkpoint', self.log.read_text())
        self.assertIn('--store-leaf state', self.last_call())

    def test_resume_without_pointer_maps_to_resolve(self):
        r = self.run_af('resume', '--repo', str(self.repo), '--session', 'S2')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('dispatch.sh resolve', self.last_call())
        self.assertNotIn('--pointer', self.last_call())

    def test_resume_with_pointer_maps_to_resume(self):
        pid = 'a' * 32 + '-1-' + 'b' * 12
        r = self.run_af('resume', '--repo', str(self.repo), '--session', 'S2', '--pointer', pid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('dispatch.sh resume', self.last_call())
        self.assertIn('--pointer ' + pid, self.last_call())

    def test_missing_required_args_blocked(self):
        self.assertNotEqual(self.run_af('checkpoint', '--session', 'S1').returncode, 0)
        self.assertNotEqual(self.run_af('resume', '--repo', str(self.repo)).returncode, 0)
        self.assertNotEqual(self.run_af('bogus', '--repo', str(self.repo)).returncode, 0)

    def test_candidates_maps_to_candidates(self):
        r = self.run_af('candidates', '--repo', str(self.repo), '--session', 'S3')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('dispatch.sh candidates', self.last_call())
        self.assertIn('--store-leaf state', self.last_call())
        self.assertNotIn('--pointer', self.last_call())

    def test_continue_is_task_listing_never_resolve_or_resume(self):
        # The post-/clear entry verb only LISTS candidates; it must never auto-resume or call resolve.
        r = self.run_af('continue', '--repo', str(self.repo), '--session', 'S4')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.log.read_text()
        self.assertIn('dispatch.sh candidates', calls)
        self.assertNotIn('dispatch.sh resolve', calls)   # never auto-binds by snapshot
        self.assertNotIn('dispatch.sh resume', calls)    # binding is a separate explicit step

    def test_continue_infra_failure_is_not_an_empty_list(self):
        # If the listing operation fails (infra), continue propagates non-zero, not a fake empty page.
        stub = ("#!/bin/sh\n"
                "{ printf '%s ' \"$0\"; printf '%s ' \"$@\"; printf '\\n'; } >> \"$LOG\"\n"
                "cat >/dev/null 2>&1 || :\n"
                "echo 'BLOCKED required handoff' >&2; exit 2\n")
        (self.code / 'dispatch.sh').write_text(stub)
        (self.code / 'dispatch.sh').chmod(0o755)
        r = self.run_af('continue', '--repo', str(self.repo), '--session', 'S5')
        self.assertNotEqual(r.returncode, 0)             # surfaced, not swallowed into a task-selection fallback

    def test_continue_and_candidates_pass_match_through(self):
        for cmd in ('continue', 'candidates'):
            self.log.write_text('') if self.log.exists() else None
            r = self.run_af(cmd, '--repo', str(self.repo), '--session', 'S6', '--match', 'triage')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('dispatch.sh candidates', self.last_call())
            self.assertIn('--match triage', self.last_call())

    def test_match_rejected_for_non_listing_commands(self):
        r = self.run_af('resume', '--repo', str(self.repo), '--session', 'S7', '--match', 'x')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(b'--match only applies', r.stderr)

    def _work_arg(self, call):
        parts = call.split()
        return parts[parts.index('--work') + 1]


if __name__ == '__main__':
    unittest.main(verbosity=2)
