"""Continuation helper flow over a real Git repo and store, with one explicit CLI process test.

Demonstrates the supported post-/clear entry path without a host:
  fresh session -> receives continuation guidance (SessionStart additionalContext)
  user "continue" -> candidates lists tasks (no claim/resume)
  human picks one exact id -> resume revalidates, claims, and returns verified context.

What this still does NOT cover (kept honest): the real Claude /clear host event delivering a NEW
session id to the hook, host auto-invocation, and the Docker round-trip (exercised separately).
"""
from pathlib import Path
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
import sys, os, json, subprocess, tempfile, unittest
sys.path.insert(0, CODE)
import guard


class ContinuationFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.base = Path(self.tmp.name).resolve()
        self.store = self.base / 'store'; self.store.mkdir(mode=0o700)
        self.repo = self.base / 'repo'; self.repo.mkdir()
        self._git('init', '-q'); self._git('config', 'user.email', 't@t'); self._git('config', 'user.name', 't')
        (self.repo / 'f.txt').write_text('hi\n')
        self._git('add', '-A'); self._git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'init')

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *a):
        subprocess.run(['git', '-C', str(self.repo), *a], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def checkpoint(self, session, goal):
        summary = {f: (goal if f == 'goal' else 'x') for f in guard.FIELDS}
        return guard.checkpoint(self.store, 'claude', session, str(self.repo), summary)

    def fresh_key(self):
        key, _ = guard.identity('claude', 'fresh-after-clear', str(self.repo))
        return key

    # 1) The fresh session RECEIVES the continuation guidance on its first event.
    def test_fresh_session_receives_continue_guidance(self):
        payload = {'hook_event_name': 'SessionStart', 'session_id': 'fresh-after-clear',
                   'cwd': str(self.repo), 'transcript_path': None}
        out = guard.event(self.store, 'claude', payload)
        text = out['hookSpecificOutput']['additionalContext']
        self.assertIn('continue', text)
        self.assertIn('task-selection', text)
        self.assertIn('start fresh', text)
        self.assertIn('snapshot_mismatch', text)           # mismatch recovery is explained
        self.assertIn('--match', text)                     # paging to older tasks is reachable
        self.assertIn('never auto-resumes', text)          # the guidance explicitly forbids auto-bind

    def test_cli_candidates_then_explicit_resume(self):
        tok=self.checkpoint('source-session','process task')
        self.checkpoint('other-source','unrelated task')
        input_file=self.base/'input.json';input_file.write_text('{}')
        base=['python3',str(Path(CODE)/'entry.py'),'candidates','--root',str(self.repo),'--store',str(self.store),'--host','claude','--session','fresh-process','--input',str(input_file),'--match','process task']
        result=subprocess.run(base,capture_output=True,text=True,check=True);data=json.loads(result.stdout)
        self.assertEqual(data['result']['candidates']['items'][0]['id'],tok)
        self.assertEqual(len(data['result']['candidates']['items']),1)
        self.assertEqual(list(self.store.glob('claim-*.json')),[])
        base=base[:-2];base[2]='resume';result=subprocess.run(base+['--pointer',tok],capture_output=True,text=True,check=True)
        self.assertIn('handoff READ',json.loads(result.stdout)['result']['context'])

    def test_entry_resolve_and_candidates_reject_pointer(self):
        from types import SimpleNamespace
        import entry
        tok=self.checkpoint('source-session','explicit task')
        for mode in ['resolve','candidates']:
            args=SimpleNamespace(mode=mode,root=str(self.repo),store=str(self.store),host='claude',session='fresh-entry',pointer=tok,match=None)
            with self.subTest(mode=mode),self.assertRaises(ValueError):entry.execute(args,b'{}')
        self.assertEqual(list(self.store.glob('claim-*.json')),[])

    def test_legacy_checkpoint_is_upgraded_without_overwrite(self):
        old=self.checkpoint('source-session','legacy work')
        p=self.store/(old+'.json');data=json.loads(p.read_text());data.pop('host');p.write_text(json.dumps(data));before=p.read_bytes()
        new=self.checkpoint('source-session','legacy work')
        self.assertNotEqual(new,old);self.assertEqual(p.read_bytes(),before)
        self.assertIn('handoff READ',guard.resume(self.store,new,'claude','fresh',str(self.repo)))

    def test_other_host_is_not_a_candidate(self):
        tok = self.checkpoint('source-session', 'same root other host')
        self.assertEqual(guard.candidates(self.store,'codex','fresh',str(self.repo))['items'],[])
        with self.assertRaises(ValueError):guard.resume(self.store,tok,'codex','fresh',str(self.repo))

    # 2) The selected task actually REACHES resume: list -> pick -> revalidate -> claim -> resume.
    def test_selected_task_reaches_resume(self):
        tok = self.checkpoint('source-session', 'wire triage to research shared path')
        # candidates lists it WITHOUT writing any claim or advancing any state.
        r = guard.candidates(self.store, 'claude', 'fresh-after-clear', str(self.repo))
        self.assertEqual([c['id'] for c in r['items']], [tok])
        self.assertEqual(r['items'][0]['status'], 'resumable')
        self.assertEqual(list(self.store.glob('claim-*.json')), [])
        self.assertFalse((self.store / ('session-' + self.fresh_key() + '.json')).exists())  # fresh state untouched
        picked = r['items'][0]['id']                                 # the human's explicit choice
        ctx = guard.resume(self.store, picked, 'claude', 'fresh-after-clear', str(self.repo))
        self.assertIn('handoff READ', ctx)
        self.assertIn('wire triage to research', ctx)
        self.assertTrue((self.store / ('claim-' + picked + '.json')).exists())  # claim written at resume
        depth_after = json.loads((self.store / ('session-' + self.fresh_key() + '.json')).read_text())['depth']
        # idempotent: the same fresh session asking again is a NOOP (no re-advance), not a double resume.
        again = guard.resume(self.store, picked, 'claude', 'fresh-after-clear', str(self.repo))
        self.assertEqual(again, '')  # NOOP: no new context, no error
        self.assertEqual(json.loads((self.store / ('session-' + self.fresh_key() + '.json')).read_text())['depth'], depth_after)

    # 3) An unrelated but snapshot-matching checkpoint is offered, never silently auto-bound.
    def test_unrelated_match_is_offered_not_autoresumed(self):
        tok = self.checkpoint('source-session', 'unrelated earlier task')
        r = guard.candidates(self.store, 'claude', 'fresh-after-clear', str(self.repo))
        self.assertEqual([c['id'] for c in r['items']], [tok])
        # Nothing bound: no claim, no advanced state for the fresh session.
        self.assertEqual(list(self.store.glob('claim-*.json')), [])
        self.assertFalse((self.store / ('session-' + self.fresh_key() + '.json')).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
