"""Unambiguous auto-resume (guard.resolve) and prescriptive handoff diagnostics.

Fixture-level only: exercises the Python resolution/diagnostic logic with synthetic
store records. It does not prove native-agent delivery or the Docker round-trip.
"""
from pathlib import Path
CODE = str(Path(__file__).resolve().parents[2] / 'runtime/session-size-docker')
import sys, json, time, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, CODE)
import guard, validate


SNAP = {'root': '/fixture', 'branch': 'main', 'head': 'abc123', 'dirty': False,
        'dirty_entries': 0, 'fingerprint': 'f'}


class Resolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.store = Path(self.tmp.name).resolve()
        self.store.chmod(0o700)
        self.mykey = 'd' * 32          # the resuming (fresh) session's identity key
        self.srckey = 'a' * 32         # a different, source session's key

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, key, gen, complete=True, snap=None, created=None, depth=0):
        token = '%s-%d-%s' % (key, gen, 'c' * 12)
        obj = {'id': token, 'host': 'codex', 'complete': complete,
               'created': time.time() if created is None else created,
               'depth': depth, 'snapshot': SNAP if snap is None else snap,
               'summary': {f: 'synthetic approved summary' for f in guard.FIELDS}}
        (self.store / (token + '.json')).write_text(json.dumps(obj))
        return token

    def resolve(self):
        with patch.object(guard, 'identity', return_value=(self.mykey, '/fixture')), \
             patch.object(guard, 'snapshot', return_value=SNAP):
            return guard.resolve(self.store, 'codex', 'fresh-session', '/fixture')

    # --- the three outcomes the user specified -------------------------------
    def assert_good_selected_with_bad(self,field,value):
        good=self.write(self.srckey,1);bad=self.write('b'*32,1)
        path=self.store/(bad+'.json');obj=json.loads(path.read_text());obj[field]=value;path.write_text(json.dumps(obj))
        self.assertIn('handoff READ',self.resolve())
        self.assertTrue((self.store/('claim-'+good+'.json')).exists())
        self.assertFalse((self.store/('claim-'+bad+'.json')).exists())

    def test_valid_candidate_survives_mismatched_id_peer(self):
        self.assert_good_selected_with_bad('id','wrong')

    def test_valid_candidate_survives_future_dated_peer(self):
        self.assert_good_selected_with_bad('created',time.time()+120)

    def test_invalid_record_filters(self):
        from copy import deepcopy
        token=self.write(self.srckey,1);p=self.store/(token+'.json');base=json.loads(p.read_text())
        for field,value in [('id','wrong'),('host','claude'),('complete',False),('created',time.time()+3600)]:
            obj=deepcopy(base);obj[field]=value;p.write_text(json.dumps(obj))
            with self.subTest(field=field),self.assertRaises(ValueError):self.resolve()
        base['id']='malformed';p.write_text(json.dumps(base));p.rename(p.with_name('malformed.json'))
        with self.assertRaisesRegex(ValueError,'no resumable checkpoint'):self.resolve()

    def test_unique_match_auto_resumes(self):
        token = self.write(self.srckey, 1)
        ctx = self.resolve()
        self.assertIn('handoff READ', ctx)
        self.assertIn('synthetic approved summary', ctx)
        # A claim and advanced session state were written for the fresh identity.
        self.assertTrue((self.store / ('claim-' + token + '.json')).exists())
        self.assertEqual(json.loads((self.store / ('session-' + self.mykey + '.json')).read_text())['resumed'], token)

    def test_other_host_excluded(self):
        token=self.write(self.srckey,1)
        p=self.store/(token+'.json');obj=json.loads(p.read_text());obj['host']='claude';p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'no resumable checkpoint'):self.resolve()

    def test_zero_matches_asks_not_invents(self):
        self.write(self.srckey, 1, complete=False)   # incomplete draft never qualifies
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_multiple_matches_are_ambiguous(self):
        self.write(self.srckey, 1)
        self.write('b' * 32, 1)
        with self.assertRaisesRegex(ValueError, 'ambiguous resumable checkpoints'):
            self.resolve()

    # --- safety filters: each must EXCLUDE the candidate (=> zero => ask) -----
    def test_same_session_checkpoint_excluded(self):
        self.write(self.mykey, 1)      # the fresh session's own checkpoint
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_snapshot_mismatch_excluded(self):
        self.write(self.srckey, 1, snap={'root': '/fixture', 'head': 'different'})
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_expired_excluded(self):
        self.write(self.srckey, 1, created=0)
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_maxdepth_excluded(self):
        self.write(self.srckey, 1, depth=guard.MAX_DEPTH)
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_foreign_claim_excluded(self):
        token = self.write(self.srckey, 1)
        (self.store / ('claim-' + token + '.json')).write_text(json.dumps({'target': 'e' * 32}))
        with self.assertRaisesRegex(ValueError, 'no resumable checkpoint'):
            self.resolve()

    def test_latest_is_never_auto_selected(self):
        # Two valid completed checkpoints at different times -> still ambiguous, never "latest".
        self.write(self.srckey, 1, created=time.time() - 100)
        self.write('b' * 32, 1, created=time.time())
        with self.assertRaisesRegex(ValueError, 'ambiguous resumable checkpoints'):
            self.resolve()


class Candidates(unittest.TestCase):
    """Read-only task-selection listing: the fallback when resolve can't auto-bind.

    Fixture-level only — exercises the (host, root) anchoring, safety filters and reporting.
    Does not prove native delivery or the Docker round-trip."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.store = Path(self.tmp.name).resolve()
        self.store.chmod(0o700)
        self.mykey = 'd' * 32
        self.srckey = 'a' * 32

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, key, gen, complete=True, snap=None, created=None, depth=0, goal='synthetic approved summary'):
        token = '%s-%d-%s' % (key, gen, 'c' * 12)
        summary = {f: 'synthetic approved summary' for f in guard.FIELDS}
        summary['goal'] = goal
        obj = {'id': token, 'host': 'codex', 'complete': complete,
               'created': time.time() if created is None else created,
               'depth': depth, 'snapshot': SNAP if snap is None else snap, 'summary': summary}
        (self.store / (token + '.json')).write_text(json.dumps(obj))
        return token

    def candidates(self, current=None, match=None):
        with patch.object(guard, 'identity', return_value=(self.mykey, '/fixture')), \
             patch.object(guard, 'snapshot', return_value=current or SNAP):
            return guard.candidates(self.store, 'codex', 'fresh-session', '/fixture', match)

    def items(self, **kw):
        return self.candidates(**kw)['items']

    def test_invalid_and_future_record_filters(self):
        from copy import deepcopy
        token=self.write(self.srckey,1);p=self.store/(token+'.json');base=json.loads(p.read_text())
        for field,value in [('id','wrong'),('host','claude'),('created','not a number'),('created',time.time()+3600)]:
            obj=deepcopy(base);obj[field]=value;p.write_text(json.dumps(obj))
            with self.subTest(field=field):self.assertEqual(self.items(),[])
        base['id']='malformed';p.write_text(json.dumps(base));p.rename(p.with_name('malformed.json'));self.assertEqual(self.items(),[])

    def test_lists_completed_checkpoint_with_gist(self):
        token = self.write(self.srckey, 1, goal='add country label to profile')
        r = self.candidates()
        self.assertEqual(r['total'], 1)
        self.assertEqual([c['id'] for c in r['items']], [token])
        self.assertEqual(r['items'][0]['goal'], 'add country label to profile')
        self.assertTrue(r['items'][0]['snapshot_matches'])
        self.assertEqual(r['items'][0]['status'], 'resumable')

    def test_snapshot_drift_is_reported_as_nonresumable_not_dropped(self):
        # Same root, different state (e.g. mtimes changed after /clear): offered, flagged, NOT a dead-end
        # pick -- resume on it still raises SNAPSHOT_MISMATCH (recovery), proven separately below.
        self.write(self.srckey, 1, snap={**SNAP, 'fingerprint': 'different'})
        it = self.items()
        self.assertEqual(len(it), 1)
        self.assertFalse(it[0]['snapshot_matches'])
        self.assertEqual(it[0]['status'], 'snapshot_mismatch')

    def test_mismatch_item_cannot_be_resumed_without_reconcile(self):
        # Human may SEE a snapshot_mismatch item, but selecting it does not bypass the guard.
        tok = self.write(self.srckey, 1, snap={**SNAP, 'head': 'different'})
        with patch.object(guard, 'identity', return_value=(self.mykey, '/fixture')), \
             patch.object(guard, 'snapshot', return_value=SNAP):
            with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
                guard.resume(self.store, tok, 'codex', 'fresh-session', '/fixture')

    def test_different_root_excluded(self):
        self.write(self.srckey, 1, snap={**SNAP, 'root': '/other'})
        self.assertEqual(self.items(), [])

    def test_lists_multiple_newest_first_for_display_only(self):
        old = self.write(self.srckey, 1, created=time.time() - 100)
        new = self.write('b' * 32, 1, created=time.time())
        self.assertEqual([c['id'] for c in self.items()], [new, old])  # display order; human still picks

    def test_unrelated_but_snapshot_matching_is_listed_not_autobound(self):
        # A checkpoint whose snapshot matches the current tree but is an UNRELATED task must still be
        # offered as a choice, never auto-resumed. candidates only lists; it writes no claim/state.
        tok = self.write(self.srckey, 1, goal='totally unrelated old task')
        r = self.candidates()
        self.assertEqual([c['id'] for c in r['items']], [tok])
        self.assertFalse((self.store / ('claim-' + tok + '.json')).exists())  # no claim written
        self.assertFalse((self.store / ('session-' + self.mykey + '.json')).exists())  # no state advanced

    def test_parallel_sessions_sharing_a_root_are_all_listed(self):
        a = self.write(self.srckey, 1, created=time.time() - 5)
        b = self.write('b' * 32, 1, created=time.time() - 3)
        c = self.write('c' * 32, 1, created=time.time() - 1)
        r = self.candidates()
        self.assertEqual(r['total'], 3)
        self.assertEqual(set(x['id'] for x in r['items']), {a, b, c})  # human disambiguates, not recency

    def test_own_session_checkpoint_excluded(self):
        self.write(self.mykey, 1)
        self.assertEqual(self.items(), [])

    def test_incomplete_draft_excluded(self):
        self.write(self.srckey, 1, complete=False)
        self.assertEqual(self.items(), [])

    def test_expired_excluded(self):
        self.write(self.srckey, 1, created=0)
        self.assertEqual(self.items(), [])

    def test_maxdepth_excluded(self):
        self.write(self.srckey, 1, depth=guard.MAX_DEPTH)
        self.assertEqual(self.items(), [])

    def test_foreign_claim_excluded_but_own_claim_kept(self):
        token = self.write(self.srckey, 1)
        claim = self.store / ('claim-' + token + '.json')
        claim.write_text(json.dumps({'target': 'e' * 32}))
        self.assertEqual(self.items(), [])
        claim.write_text(json.dumps({'target': self.mykey}))  # already ours -> still offerable
        self.assertEqual([c['id'] for c in self.items()], [token])

    def test_goal_is_sanitized(self):
        self.write(self.srckey, 1, goal='token=abcdefghijklmnopqrstuvwxyz012345 trailing')
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz012345', self.items()[0]['goal'])

    def test_page_bounded_but_total_reported_and_match_reaches_older(self):
        # More than one page of eligible tasks: the page is bounded, total is honest, and an older
        # task outside the newest page is reachable by --match (never auto-selected).
        older = self.write(self.srckey, 1, created=time.time() - 10_000, goal='wire triage to research')
        for i in range(2, guard.CANDIDATE_LIMIT + 5):
            self.write('%032x' % i, 1, created=time.time() - i, goal='unrelated %d' % i)
        r = self.candidates()
        self.assertEqual(r['returned'], guard.CANDIDATE_LIMIT)
        self.assertEqual(r['total'], guard.CANDIDATE_LIMIT + 4)
        self.assertNotIn(older, [c['id'] for c in r['items']])  # pushed off the newest page
        m = self.candidates(match='triage to research')  # ...but reachable by match
        self.assertEqual([c['id'] for c in m['items']], [older])
        self.assertEqual(self.candidates(match=older[:8])['items'][0]['id'], older)  # or by id prefix

    def test_empty_is_not_an_error(self):
        r = self.candidates()
        self.assertEqual((r['total'], r['items']), (0, []))  # no raise: caller offers "start fresh"


class Diagnostics(unittest.TestCase):
    def one(self, msg):
        return guard.handoff_diagnostic(ValueError(msg))

    def test_incomplete_checkpoint_forbids_inventing_a_task(self):
        text = self.one('handoff incomplete')
        self.assertIn('INCOMPLETE_CHECKPOINT', text)
        self.assertIn('not a resumable handoff', text)
        self.assertIn('Git history', text)        # explicitly forbids inferring from Git
        self.assertIn('one clear question', text)  # explicitly tells the agent to ask

    def test_no_resumable_and_ambiguous_tell_the_agent_to_ask(self):
        no = self.one('no resumable checkpoint for this identity')
        self.assertIn('NO_RESUMABLE_CHECKPOINT', no)
        self.assertIn('Git history', no)
        self.assertIn('one clear question', no)
        amb = self.one('ambiguous resumable checkpoints for this identity')
        self.assertIn('AMBIGUOUS_CHECKPOINTS', amb)
        self.assertIn('which exact checkpoint ID', amb)

    def test_invalid_id_tells_to_ask_for_exact_id(self):
        text = self.one('explicit handoff ID required')
        self.assertIn('INVALID_CHECKPOINT_ID', text)
        self.assertIn('ask the user', text.lower())

    def test_diagnostics_never_echo_rejected_value(self):
        self.assertNotIn('PRIVATE_SENTINEL', self.one('PRIVATE_SENTINEL'))


class ValidatorMode(unittest.TestCase):
    def test_each_candidates_schema_guard(self):
        from copy import deepcopy
        item={'id':'a'*32+'-1-'+'c'*12,'created':1.0,'snapshot_matches':True,'status':'resumable','goal':'task'}
        good={'status':'OK','result':{'candidates':{'total':1,'returned':1,'items':[item]}}}
        bad=[]
        for field,value in [('total',True),('total',-1),('returned',True),('returned',0),('items',{})]:
            obj=deepcopy(good);obj['result']['candidates'][field]=value
            if field=='items':obj['result']['candidates'].update(total=0,returned=0)
            bad.append(obj)
        for where in ['result','counts','item']:
            obj=deepcopy(good)
            target=obj['result'] if where=='result' else obj['result']['candidates'] if where=='counts' else obj['result']['candidates']['items'][0]
            target['extra']='not allowed';bad.append(obj)
        for field,value in [('id',1),('created',True),('snapshot_matches',1),('status','other'),('goal',{}),('goal','x'*513)]:
            obj=deepcopy(good);row=obj['result']['candidates']['items'][0];row[field]=value
            if field=='status':row['snapshot_matches']=False
            bad.append(obj)
        for obj in bad:
            with self.subTest(obj=obj),self.assertRaises(ValueError):validate.validate('candidates',obj)

    def test_resolve_result_shape_accepted(self):
        validate.validate('resolve', {'status': 'OK', 'result': {'context': 'ok'}})
        with self.assertRaises(ValueError):
            validate.validate('resolve', {'status': 'OK', 'result': {'checkpoint_id': 'x'}})

    def test_candidates_result_shape(self):
        good = {'id': 'a' * 32 + '-1-' + 'c' * 12, 'created': 1.0,
                'snapshot_matches': True, 'status': 'resumable', 'goal': 'do the thing'}
        def env(items, total=None):
            return {'status': 'OK', 'result': {'candidates':
                    {'total': len(items) if total is None else total, 'returned': len(items), 'items': items}}}
        validate.validate('candidates', env([good]))
        validate.validate('candidates', env([]))
        validate.validate('candidates', env([good], total=20))  # page of 1, 20 exist
        with self.assertRaises(ValueError):  # old flat list shape rejected
            validate.validate('candidates', {'status': 'OK', 'result': {'candidates': [good]}})
        with self.assertRaises(ValueError):  # over the page bound
            validate.validate('candidates', env([good] * (validate.CAND_MAX + 1)))
        with self.assertRaises(ValueError):  # returned > total
            validate.validate('candidates', {'status': 'OK', 'result': {'candidates': {'total': 0, 'returned': 1, 'items': [good]}}})
        with self.assertRaises(ValueError):  # malformed id
            validate.validate('candidates', env([{**good, 'id': 'nope'}]))
        with self.assertRaises(ValueError):  # status must agree with snapshot_matches
            validate.validate('candidates', env([{**good, 'status': 'snapshot_mismatch'}]))
        with self.assertRaises(ValueError):  # bad status value
            validate.validate('candidates', env([{**good, 'status': 'maybe'}]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
