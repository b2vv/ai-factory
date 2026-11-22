"""Synthetic-only durability, private spool and transport fault tests; no live archive."""
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_bridge as bridge
from capture_queue import Queue, canonical_body, REDACTED, deadline, DeadlineExpired, contains_credential

SCOPE = {'endpoint':'http://127.0.0.1:8780','project':'fixture','source':'fixture','principal':'agent:fixture'}

def records(suffix='1', text='fixture answer'):
    return [{'type':'user','uuid':'U'+suffix,'parentUuid':'','sessionId':'S',
             'message':{'role':'user','content':[{'type':'text','text':'fixture prompt'}]}},
            {'type':'assistant','uuid':'A'+suffix,'parentUuid':'U'+suffix,'sessionId':'S',
             'message':{'role':'assistant','content':[{'type':'text','text':text}]}}]


def parallel(root, number, output):
    try:
        q = Queue(root,SCOPE)
        key,body = canonical_body(records(str(number)))
        q.enqueue(key,body,2)
        item = q.claim()
        output.put(item['id'] if item else None)
        q.close()
    except Exception as e:
        output.put(type(e).__name__ + ': ' + str(e))


def parallel_receipts(root, number, output):
    try:
        q=Queue(root,SCOPE,max_receipts=3)
        for i in range(10):
            key,body=canonical_body(records('worker'+str(number)+'turn'+str(i)))
            q.enqueue(key,body,2)
            row=q.claim()
            if row:q.finish(row,{'delivered':True})
        q.close();output.put('ok')
    except Exception as exc:output.put(type(exc).__name__)


class Spool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()/'queue'
        self.q = Queue(self.root,SCOPE)
        self.addCleanup(self.q.close)
        self.key,self.body = canonical_body(records())

    def test_restart_durable_exact_payload_and_receipt(self):
        self.q.enqueue(self.key,self.body,2)
        other = Queue(self.root,SCOPE)
        self.addCleanup(other.close)
        item = other.claim()
        self.assertEqual(item['body'],self.body)
        other.finish(item,{'delivered':True})
        self.assertEqual(self.q.enqueue(self.key,self.body,2),'done')
        self.assertIsNone(self.q.claim())
        self.assertEqual(self.q.db.execute('SELECT body FROM items').fetchone()[0],None)

    def test_crash_after_claim_consumes_attempt_and_lease(self):
        self.q.enqueue(self.key,self.body,2)
        first=self.q.claim(now=100)
        self.assertIsNone(self.q.claim(now=159))
        second=self.q.claim(now=161)
        self.assertEqual(second['body'],first['body'])
        self.assertEqual(second['attempts'],2)
        self.q.finish(first,{'delivered':True},now=162)
        self.assertEqual(self.q.status()['pending'],1) # stale worker cannot ACK new claim
        self.q.finish(second,{'delivered':True},now=163)
        self.assertEqual(self.q.status()['receipts'],1)

    def test_actual_process_death_during_transaction_rolls_back(self):
        self.q.enqueue(self.key,self.body,2)
        code="import sqlite3,os; c=sqlite3.connect(%r); c.execute('BEGIN IMMEDIATE'); c.execute('DELETE FROM items'); os._exit(9)" % str(self.q.path)
        proc=subprocess.run([sys.executable,'-c',code])
        self.assertEqual(proc.returncode,9)
        self.assertEqual(self.q.status()['pending'],1)

    def test_attempt_ceiling_survives_repeated_crashes(self):
        self.q.max_attempts=2
        self.q.enqueue(self.key,self.body,2)
        self.q.claim(now=0); self.q.claim(now=61)
        self.assertIsNone(self.q.claim(now=122))
        self.assertEqual(self.q.status()['blocked'],1)

    def test_parallel_enqueue_claim_no_double_claim(self):
        ctx=multiprocessing.get_context('fork'); output=ctx.Queue()
        children=[ctx.Process(target=parallel,args=(str(self.root),i,output)) for i in range(8)]
        for p in children:p.start()
        for p in children:p.join(5);self.assertEqual(p.exitcode,0)
        claims=[output.get(timeout=2) for _ in children]
        self.assertEqual(len(set(claims)),8)
        self.assertTrue(all(isinstance(c,str) and len(c)==64 for c in claims), claims)
        self.assertEqual(self.q.status()['pending'],8)

    def test_parallel_same_turn_deduplicates(self):
        ctx=multiprocessing.get_context('fork'); output=ctx.Queue()
        children=[ctx.Process(target=parallel,args=(str(self.root),1,output)) for _ in range(6)]
        for p in children:p.start()
        for p in children:p.join(5);self.assertEqual(p.exitcode,0)
        claims=[output.get(timeout=2) for _ in children]
        self.assertEqual(sum(c is not None for c in claims),1,claims)
        self.assertEqual(self.q.status()['pending'],1)

    def test_full_no_eviction_or_overwrite(self):
        self.q.max_items=1
        self.q.enqueue(self.key,self.body,2)
        key,body=canonical_body(records('2'))
        with self.assertRaisesRegex(ValueError,'queue full'):self.q.enqueue(key,body,2)
        self.assertEqual(self.q.status()['pending'],1)
        with self.assertRaisesRegex(ValueError,'conflict'):self.q.enqueue(self.key,b'changed',2)
        self.assertEqual(self.q.claim()['body'],self.body)

    def test_payload_and_receipt_limits(self):
        self.q.max_bytes=1
        with self.assertRaisesRegex(ValueError,'queue full'):self.q.enqueue(self.key,self.body,2)
        self.q.max_bytes=100000
        self.q.enqueue(self.key,self.body,2)
        self.q.finish(self.q.claim(),{'delivered':True})
        self.q.max_receipts=1
        key,body=canonical_body(records('2'))
        self.assertEqual(self.q.enqueue(key,body,2),'pending')
        self.assertEqual(self.q.enqueue(self.key,self.body,2),'done')
        self.q.finish(self.q.claim(),{'delivered':True})
        self.assertEqual(self.q.status()['receipts'],1)
        self.assertEqual(self.q.status()['receipts_pruned'],1)

    def test_parallel_receipt_trim_preserves_counts(self):
        ctx=multiprocessing.get_context('fork');output=ctx.Queue()
        workers=[ctx.Process(target=parallel_receipts,args=(str(self.root),i,output)) for i in range(4)]
        for p in workers:p.start()
        for p in workers:p.join(10);self.assertEqual(p.exitcode,0)
        self.assertEqual([output.get(timeout=1) for _ in workers],['ok']*4)
        self.assertEqual(self.q.status()['pending'],0)
        self.assertEqual(self.q.status()['receipts'],3)
        self.assertEqual(self.q.status()['receipts_pruned'],37)

    def test_process_death_rolls_back_trim_and_counter(self):
        self.q.enqueue(self.key,self.body,2);self.q.finish(self.q.claim(),{'delivered':True})
        code="import sqlite3,os; c=sqlite3.connect(%r); c.execute('BEGIN IMMEDIATE'); c.execute(\"DELETE FROM items WHERE state='done'\"); c.execute('UPDATE receipt_stats SET pruned=pruned+1'); os._exit(9)" % str(self.q.path)
        proc=subprocess.run([sys.executable,'-c',code]);self.assertEqual(proc.returncode,9)
        self.assertEqual(self.q.status()['receipts'],1)
        self.assertEqual(self.q.status()['receipts_pruned'],0)

    def test_done_receipts_do_not_consume_pending_capacity(self):
        self.q.max_items=1;self.q.max_receipts=7
        self.q.enqueue(self.key,self.body,2);self.q.finish(self.q.claim(),{'delivered':True})
        key,body=canonical_body(records('fresh'))
        self.assertEqual(self.q.enqueue(key,body,2),'pending')
        self.assertEqual(self.q.status()['receipt_limit'],7)
        self.assertEqual(self.q.status()['receipts'],1)
        with self.assertRaisesRegex(ValueError,'queue full'):
            self.q.enqueue(*canonical_body(records('overflow')),2)

    def test_receipt_created_tie_uses_identity_order(self):
        for key in ['c','b','a']:
            self.q.db.execute("INSERT INTO items(id,digest,count,state,created) VALUES(?, 'hash',2,'done',1)",(key,))
        self.q.max_receipts=2
        self.q.enqueue(self.key,self.body,2)
        self.assertEqual([r[0] for r in self.q.db.execute("SELECT id FROM items WHERE state='done' ORDER BY id")],['b','c'])

    def test_receipt_limit_rejects_invalid_config(self):
        for cap in [0, -1, True, 1.5, '2']:
            with self.assertRaisesRegex(ValueError, 'positive receipt'):
                Queue(self.root, SCOPE, max_receipts=cap)

    def test_receipt_long_run_restart_and_replay(self):
        self.q.max_receipts=3
        sizes=[]
        first=None
        for i in range(1100):
            key,body=canonical_body(records(str(i)))
            if i==0:first=(key,body)
            self.q.enqueue(key,body,2)
            self.q.finish(self.q.claim(),{'delivered':True})
            self.assertLessEqual(self.q.status()['receipts'],3)
            if i in (99,1099):sizes.append(self.q.path.stat().st_size)
        self.assertLessEqual(sizes[1],sizes[0]+8192)
        self.assertEqual(self.q.status()['receipts_pruned'],1097)
        other=Queue(self.root,SCOPE,max_receipts=3)
        self.addCleanup(other.close)
        self.assertEqual(other.status()['receipts_pruned'],1097)
        self.assertEqual(other.enqueue(first[0],first[1],2),'pending')
        self.assertEqual(other.claim()['body'],first[1])

    def test_trim_never_deletes_blocked_pending_or_lease(self):
        self.q.max_receipts=1
        protected=[]
        for i in range(3):
            key,body=canonical_body(records('protected'+str(i)))
            self.q.enqueue(key,body,2);protected.append(key)
        blocked=self.q.claim();self.q.finish(blocked,{'http_status':403})
        leased=self.q.claim()
        for i in range(4):
            key,body=canonical_body(records('done'+str(i)))
            self.q.enqueue(key,body,2)
            # Production finish still enforces exact live claim lease.
            self.q.db.execute("UPDATE items SET lease='fixture' WHERE id=?",(key,))
            self.q.finish({'id':key,'lease':'fixture','attempts':1},{'delivered':True})
        for key in protected:
            self.assertIsNotNone(self.q.db.execute('SELECT body FROM items WHERE id=?',(key,)).fetchone()[0])
        self.assertEqual(self.q.status()['blocked'],1)
        self.assertEqual(self.q.status()['pending'],2)
        self.assertEqual(self.q.status()['receipts'],1)
        self.assertEqual(self.q.db.execute('SELECT lease FROM items WHERE id=?',(leased['id'],)).fetchone()[0],leased['lease'])

    def test_trim_counter_and_ack_rollback_together(self):
        self.q.max_receipts=1
        for i in range(2):
            key,body=canonical_body(records(str(i)))
            self.q.enqueue(key,body,2)
            row=self.q.claim()
            if i==0:self.q.finish(row,{'delivered':True})
        # A real SQLite failure after deletion must roll back ACK and trim.
        self.q.db.execute("CREATE TRIGGER reject_stats BEFORE UPDATE ON receipt_stats BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.q.finish(row,{'delivered':True})
        self.assertEqual(self.q.status()['receipts'],1)
        self.assertEqual(self.q.status()['pending'],1)
        self.assertEqual(self.q.status()['receipts_pruned'],0)
        self.assertEqual(self.q.db.execute('SELECT lease FROM items WHERE id=?',(row['id'],)).fetchone()[0],row['lease'])

    def test_legacy_schema_upgrade_and_prune(self):
        self.q.db.execute('DROP TABLE receipt_stats')
        for i in range(4):
            self.q.db.execute("INSERT INTO items(id,digest,count,state,created) VALUES(?, 'hash',2,'done',?)",(str(i),i))
        other=Queue(self.root,SCOPE,max_receipts=2);self.addCleanup(other.close)
        other.enqueue(self.key,self.body,2)
        self.assertEqual(other.status()['receipts'],2)
        self.assertEqual(other.status()['receipts_pruned'],2)
        self.assertEqual([x[0] for x in other.db.execute("SELECT id FROM items WHERE state='done' ORDER BY id")],['2','3'])

    def test_route_and_principal_isolation(self):
        self.q.enqueue(self.key,self.body,2)
        for field in SCOPE:
            other=Queue(self.root,{**SCOPE,field:'other'})
            self.assertIsNone(other.claim());other.close()
        self.assertEqual(self.q.status()['pending'],1)

    def test_4xx_blocked_and_explicit_remediation(self):
        for code in (400,401,403,404,409,413,422):
            key,body=canonical_body(records(str(code)))
            self.q.enqueue(key,body,2)
            item=self.q.claim()
            self.assertEqual(self.q.finish(item,{'http_status':code}),'blocked')
            self.assertIsNone(self.q.claim())
        self.assertEqual(self.q.status()['blocked'],7)
        self.assertEqual(self.q.retry_blocked(),7)
        self.assertEqual(self.q.status()['pending'],7)

    def test_408_429_5xx_and_transport_backoff(self):
        for i,result in enumerate(({'http_status':408},{'http_status':429},{'http_status':503},{'error':'timeout'})):
            key,body=canonical_body(records(str(i)))
            self.q.enqueue(key,body,2)
            item=self.q.claim(now=0)
            self.assertEqual(self.q.finish(item,result,now=0),'pending')
        self.assertIsNone(self.q.claim(now=4))
        self.assertIsNotNone(self.q.claim(now=5))

    def test_private_modes_and_symlink_refusal(self):
        self.assertEqual(self.root.stat().st_mode & 0o777,0o700)
        self.assertEqual(self.q.path.stat().st_mode & 0o777,0o600)
        alias=self.root.parent/'alias';alias.symlink_to(self.root)
        with self.assertRaises(ValueError):Queue(alias,SCOPE)
        os.chmod(self.root,0o755)
        with self.assertRaises(ValueError):Queue(self.root,SCOPE)
        os.chmod(self.root,0o700)
        os.chmod(self.q.path,0o644)
        with self.assertRaises(ValueError):Queue(self.root,SCOPE)

    def test_hardlink_refusal(self):
        os.link(self.q.path,self.root/'linked')
        with self.assertRaises(ValueError):Queue(self.root,SCOPE)

    def test_payload_corruption_blocked(self):
        self.q.enqueue(self.key,self.body,2)
        self.q.db.execute("UPDATE items SET body=X'00'")
        self.assertIsNone(self.q.claim())
        self.assertEqual(self.q.status()['blocked'],1)

    def test_busy_database_bounded(self):
        lock=sqlite3.connect(self.q.path)
        lock.execute('BEGIN IMMEDIATE')
        start=time.monotonic()
        try:
            with self.assertRaises(sqlite3.OperationalError):self.q.enqueue(self.key,self.body,2)
        finally:lock.rollback();lock.close()
        self.assertLess(time.monotonic()-start,1.5)
        self.assertEqual(self.q.status()['pending'],0)

    def held_lock(self, seconds):
        ready=threading.Event()
        def hold():
            conn=sqlite3.connect(self.q.path);conn.execute('BEGIN IMMEDIATE');ready.set()
            time.sleep(seconds);conn.rollback();conn.close()
        thread=threading.Thread(target=hold);thread.start();self.assertTrue(ready.wait(2))
        self.addCleanup(thread.join)
        return thread

    def test_waits_for_precommit_lock_then_enqueues_once(self):
        thread=self.held_lock(.3);start=time.monotonic()
        self.assertEqual('pending',self.q.enqueue(self.key,self.body,2));thread.join()
        self.assertGreater(time.monotonic()-start,.2)
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM items').fetchone()[0],1)

    def test_constructor_schema_waits_for_held_lock(self):
        thread=self.held_lock(.3)
        other=Queue(self.root,SCOPE);self.addCleanup(other.close);thread.join()
        self.assertEqual('pending',other.enqueue(self.key,self.body,2))

    def test_contention_wait_clamps_to_enclosing_deadline(self):
        thread=self.held_lock(.5);start=time.monotonic()
        with self.assertRaises((sqlite3.OperationalError,DeadlineExpired)):
            with deadline(.15):self.q.enqueue(self.key,self.body,2)
        self.assertLess(time.monotonic()-start,.4);thread.join()
        self.assertEqual(self.q.status()['pending'],0)

    def test_error_after_commit_does_not_replay_or_mask(self):
        real=self.q.db
        class Ambiguous:
            commits=0
            @property
            def in_transaction(self):return real.in_transaction
            def execute(inner,sql,args=()):
                result=real.execute(sql,args)
                if sql=='COMMIT':
                    inner.commits+=1
                    raise sqlite3.OperationalError('simulated outcome unknown')
                return result
        proxy=Ambiguous();self.q.db=proxy
        try:
            with self.assertRaisesRegex(sqlite3.OperationalError,'outcome unknown'):
                self.q.enqueue(self.key,self.body,2)
            self.assertEqual(proxy.commits,1)
            self.assertEqual(real.execute('SELECT count(*) FROM items').fetchone()[0],1)
        finally:self.q.db=real

    def test_deleted_journal_race_is_safe_but_database_absence_is_not(self):
        import capture_queue as module
        from unittest.mock import patch
        original=module.private_path
        def deleted(path,directory=False):
            if str(path).endswith('-journal'):raise FileNotFoundError('concurrent commit removed journal')
            return original(path,directory)
        with patch.object(module,'private_path',side_effect=deleted):
            q=Queue(self.root,SCOPE);q.close()
        def missing_db(path,directory=False):
            if str(path).endswith('.sqlite3'):raise FileNotFoundError('missing database')
            return original(path,directory)
        with patch.object(module,'private_path',side_effect=missing_db):
            with self.assertRaises(FileNotFoundError):Queue(self.root,SCOPE)

    def test_unlinked_journal_zero_link_stat_requires_confirmed_absence(self):
        import capture_queue as module
        from unittest.mock import patch
        original=module.private_path
        def zero_links(path,directory=False):
            if str(path).endswith('-journal'):raise ValueError('nonprivate queue path')
            return original(path,directory)
        with patch.object(module,'private_path',side_effect=zero_links):
            q=Queue(self.root,SCOPE);q.close()  # no journal: lstat raced unlink
            journal=Path(str(self.q.path)+'-journal');journal.write_bytes(b'unsafe');journal.chmod(0o644)
            try:
                with self.assertRaises(ValueError):Queue(self.root,SCOPE)
            finally:journal.unlink()

    def test_joined_redaction_and_private_payload(self):
        recs=records(text='safe')
        recs[1]['message']['content']=[{'type':'text','text':'password'},{'type':'text','text':': should-not-persist'}]
        key,body=canonical_body(recs)
        self.assertNotIn(b'should-not-persist',body)
        self.assertIn(REDACTED.encode(),body)
        self.q.enqueue(key,body,2)
        self.assertNotIn(b'should-not-persist',self.q.path.read_bytes())
        self.assertNotIn('body',self.q.status())

    def test_transport_connection_refused_retains_exact_body(self):
        self.q.enqueue(self.key,self.body,2)
        item=self.q.claim(now=0)
        def refused(*args,**kwargs):raise ConnectionRefusedError()
        result=bridge.post_body('http://127.0.0.1:8780','fixture','fixture',{},item['body'],2,opener=refused)
        self.assertFalse(result.get('delivered',False))
        self.q.finish(item,result,now=0)
        self.assertEqual(self.q.claim(now=5)['body'],self.body)

    def test_completed_payload_removed_from_database(self):
        key,body=canonical_body(records(text='distinct-private-message-canary'))
        self.q.enqueue(key,body,2)
        self.q.finish(self.q.claim(),{'delivered':True})
        self.assertNotIn(b'distinct-private-message-canary',self.q.path.read_bytes())

    def test_go_sanitizer_boundary_and_fold_regressions(self):
        for text in ('toKen: value','paſſword: value','token\n: value','token\f: value'):
            self.assertTrue(contains_credential(text),repr(text))
        for text in ('token\v: value','apİ_key: value','apı_key: value','ſecret: value'):
            self.assertFalse(contains_credential(text),repr(text))

    def test_nested_wall_deadline(self):
        start=time.monotonic()
        with self.assertRaises(DeadlineExpired):
            with deadline(.1):
                with deadline(1):time.sleep(1)
        self.assertLess(time.monotonic()-start,1.5)
        self.assertEqual(self.q.status()['pending'],0)


class Loopback(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.requests=[];self.stored={};self.delay=0;self.response=200;self.bad=False;self.wrong_receipts=False;self.redirect=None
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                fixture.requests.append(body)
                recs=list(map(json.loads,body.splitlines()))
                for r in recs:fixture.stored[(r['sessionId'],r['uuid'])]=r
                query=parse_qs(urlsplit(self.path).query)
                receipts=[json.dumps([query['project'][0],query['source_instance'][0],r['sessionId'],r['uuid']]) for r in recs]
                if fixture.wrong_receipts:receipts=['["wrong-project"]']
                time.sleep(fixture.delay)
                self.send_response(fixture.response)
                if fixture.redirect:self.send_header('Location',fixture.redirect)
                self.end_headers()
                try:self.wfile.write(json.dumps({'accepted':0 if fixture.bad else len(recs),'committed':len(recs),'receipts':receipts}).encode())
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.credential=self.root/'credential.json'
        self.credential.write_text(json.dumps({'principal_id':'fixture','epoch':1,'secret':'SYNTHETIC-CREDENTIAL'}));self.credential.chmod(0o600)
        self.transcript=self.root/'transcript'
        self.transcript.write_text('\n'.join(json.dumps(r) for r in records()))
        self.env={k:v for k,v in os.environ.items() if not k.startswith('AF_CAPTURE_')}
        self.env.update(AF_CAPTURE_ENDPOINT=f'http://127.0.0.1:{self.server.server_port}',AF_CAPTURE_PROJECT='fixture',AF_CAPTURE_SOURCE='fixture',AF_CAPTURE_AGENT_CREDENTIAL_FILE=str(self.credential),AF_CAPTURE_READ_ATTEMPTS='1')
        self.scope={**SCOPE,'endpoint':self.env['AF_CAPTURE_ENDPOINT']}

    def invoke(self,mode=None):
        args=[sys.executable,'-I','-B',str(Path(bridge.__file__))]+(['--'+mode] if mode else [])
        start=time.monotonic()
        proc=subprocess.run(args,env=self.env,input=json.dumps({'hook_event_name':'Stop','session_id':'S','transcript_path':str(self.transcript)}),text=True,capture_output=True,timeout=10)
        self.assertEqual(proc.returncode,0)
        self.assertLess(time.monotonic()-start,9)
        self.assertNotIn('SYNTHETIC-CREDENTIAL',proc.stderr)
        self.assertNotIn('fixture answer',proc.stderr)
        return json.loads(proc.stderr.split('af-claude-capture ')[-1])

    def due_now(self):
        q=Queue(self.root/'capture-queue',self.scope)
        q.db.execute('UPDATE items SET next=0');q.close()

    def test_hook_only_enqueues_while_worker_alive(self):
        q=Queue(self.root/'capture-queue',self.scope)
        heartbeat=str(q.path)+'.worker';q.close()
        fd=os.open(heartbeat,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
        first=self.invoke()
        self.assertEqual('deferred_to_worker',first['delivery']);self.assertTrue(first['queued'])
        self.assertEqual([],self.requests)
        os.utime(heartbeat,(0,0))  # a stale heartbeat: the hook sends itself again
        second=self.invoke()
        self.assertNotIn('delivery',second);self.assertTrue(second['delivered']);self.assertEqual(1,len(self.requests))

    def test_worker_cycle_refreshes_heartbeat(self):
        q=Queue(self.root/'capture-queue',self.scope)
        bridge.IN_WORKER=True
        try:
            env={**self.env}
            from unittest.mock import patch
            with patch.dict(os.environ,env,clear=True):bridge.run('flush',quiet_idle=True)
        finally:
            bridge.IN_WORKER=False
        self.assertTrue(bridge.worker_alive(q));q.close()

    def test_timeout_after_commit_replay_exact_after_restart(self):
        self.delay=bridge.POST_SOCKET_TIMEOUT+.4  # longer than the client waits
        first=self.invoke()
        self.assertFalse(first['delivered']);self.assertTrue(first['queued'])
        self.assertEqual(len(self.stored),2)
        self.delay=0;self.due_now()
        second=self.invoke('flush')
        self.assertTrue(second['delivered'])
        self.assertEqual(self.requests[0],self.requests[1])
        self.assertEqual(len(self.stored),2)
        self.assertTrue(self.invoke()['deduplicated'])
        self.assertEqual(len(self.requests),2)

    def direct_hook(self, drain=None):
        from unittest.mock import patch
        event=json.dumps({'hook_event_name':'Stop','session_id':'S','transcript_path':str(self.transcript)})
        original=bridge.drain
        def factory(root,scope):return Queue(root,scope,max_receipts=1)
        with patch.dict(os.environ,self.env,clear=True), patch.object(bridge,'Queue',side_effect=factory), patch.object(sys,'stdin',io.StringIO(event)), patch.object(bridge,'emit_status'), patch.object(bridge,'drain',side_effect=drain or original):
            return bridge.run()

    def test_current_receipt_self_evicted_reports_unavailable(self):
        q=Queue(self.root/'capture-queue',self.scope,max_receipts=1)
        key,body=canonical_body(records('newer'))
        q.enqueue(key,body,2);q.finish(q.claim(),{'delivered':True})
        key,body=canonical_body([json.loads(bridge.to_line(r)) for r in bridge.select_turn(records(), 'S')[:2]])
        q.enqueue(key,body,2);q.db.execute('UPDATE items SET created=0 WHERE id=?',(key,));q.close()
        result=self.direct_hook()
        self.assertNotIn('error',result)
        self.assertEqual(result['current_state'],'receipt_evicted')
        self.assertEqual(result['delivery_confirmation'],'not_retained')
        self.assertFalse(result['delivered']);self.assertTrue(result['drained_delivered'])
        self.assertEqual(len(self.stored),2)

    def test_other_worker_eviction_before_current_read(self):
        original=bridge.drain
        errors=[]
        def race(*args):
            result=original(*args)
            def worker():
                try:
                    q=Queue(self.root/'capture-queue',self.scope,max_receipts=1)
                    key,body=canonical_body(records('later'))
                    q.enqueue(key,body,2);q.finish(q.claim(),{'delivered':True});q.close()
                except Exception as exc:errors.append(exc)
            thread=threading.Thread(target=worker);thread.start();thread.join(3)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            return result
        result=self.direct_hook(race)
        self.assertEqual(result['current_state'],'receipt_evicted')
        self.assertFalse(result['delivered']);self.assertTrue(result['drained_delivered'])
        self.assertNotIn('error',result)

    def test_older_item_ack_not_current_delivery(self):
        q=Queue(self.root/'capture-queue',self.scope,max_receipts=1)
        key,body=canonical_body(records('older'));q.enqueue(key,body,2);q.close()
        result=self.direct_hook()
        self.assertTrue(result['drained_delivered']);self.assertFalse(result['delivered'])
        self.assertEqual(result['current_state'],'pending')
        self.assertNotIn('delivery_confirmation',result)

    def test_evicted_claude_replay_identical_and_server_dedup(self):
        self.assertTrue(self.invoke()['delivered'])
        original=self.requests[0]
        q=Queue(self.root/'capture-queue',self.scope,max_receipts=1)
        key,body=canonical_body(records('replacement'))
        q.enqueue(key,body,2);q.finish(q.claim(),{'delivered':True});q.close()
        self.assertTrue(self.invoke()['delivered'])
        self.assertEqual(self.requests,[original,original]);self.assertEqual(len(self.stored),2)

    def test_offline_queue_then_flush_without_new_hook(self):
        self.response=503
        first=self.invoke();self.assertFalse(first['delivered'])
        self.response=200;self.due_now()
        self.assertTrue(self.invoke('flush')['delivered'])
        self.assertEqual(self.requests[0],self.requests[1])

    def test_invalid_ack_retained(self):
        self.bad=True
        self.assertFalse(self.invoke()['delivered'])
        self.assertEqual(self.invoke('status')['queue']['pending'],1)

    def test_wrong_identity_ack_retained(self):
        self.wrong_receipts=True
        self.assertFalse(self.invoke()['delivered'])
        self.assertEqual(self.invoke('status')['queue']['pending'],1)

    def test_redirect_never_followed(self):
        self.response=302;self.redirect=f'http://127.0.0.1:{self.server.server_port}/credential-leak'
        self.assertFalse(self.invoke()['delivered'])
        self.assertEqual(len(self.requests),1)

    def test_status_fifo_never_blocks_hook(self):
        fifo=self.root/'status-fifo';os.mkfifo(fifo)
        self.env['AF_CAPTURE_STATUS_FILE']=str(fifo)
        start=time.monotonic()
        self.assertTrue(self.invoke()['delivered'])
        self.assertLess(time.monotonic()-start,2)

    def test_status_symlink_is_not_followed(self):
        target=self.root/'log';target.write_text('unchanged')
        link=self.root/'log-link';link.symlink_to(target)
        self.env['AF_CAPTURE_STATUS_FILE']=str(link)
        self.assertTrue(self.invoke()['delivered'])
        self.assertEqual(target.read_text(),'unchanged')

    def test_denial_not_retried_on_next_hook(self):
        self.response=403
        self.assertEqual(self.invoke()['current_state'],'blocked')
        self.invoke()
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.invoke('status')['queue']['blocked'],1)

    def test_worker_recovers_without_further_hook(self):
        self.response=503;self.invoke()
        self.response=200;self.due_now()
        proc=subprocess.Popen([sys.executable,'-I','-B',str(Path(bridge.__file__)),'--worker'],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            end=time.monotonic()+5
            while time.monotonic()<end:
                if len(self.requests)>=2:break
                time.sleep(.05)
            self.assertEqual(len(self.requests),2)
        finally:proc.terminate();proc.communicate(timeout=3)
        self.assertEqual(self.invoke('status')['queue']['receipts'],1)

if __name__=='__main__':unittest.main()
