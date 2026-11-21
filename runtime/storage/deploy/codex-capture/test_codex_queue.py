"""Codex v2 durable queue tests. Synthetic loopback only, no host hook/trust changes."""
import hashlib,json,os,pathlib,shutil,subprocess,sys,tempfile,threading,time,unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import codex_capture_catcher as c
from capture_queue import Queue,REDACTED

def event(text='fixture assistant',active=False,role='Stop',turn='turn'):
    e={'hook_event_name':role,'session_id':'session','turn_id':turn}
    if role=='Stop':e.update(last_assistant_message=text,stop_hook_active=active)
    else:e['prompt']=text
    return e

class Identity(unittest.TestCase):
    def test_distinct_snapshots_but_same_flag_independent_identity(self):
        a=c.freeze_event(event('one',False));b=c.freeze_event(event('one',True));d=c.freeze_event(event('two'))
        self.assertEqual(a,b);self.assertNotEqual(a[0],d[0])
        self.assertEqual(a[2],'v2/turn/assistant/'+hashlib.sha256(b'one').hexdigest())
    def test_redaction_collapse_before_disk(self):
        a=c.freeze_event(event('password: CANARY_ONE'));b=c.freeze_event(event('token: CANARY_TWO'))
        self.assertEqual(a,b);self.assertNotIn(b'CANARY',a[1]);self.assertIn(REDACTED.encode(),a[1])
    def test_changed_prompt_conflicts_same_identity(self):
        a=c.freeze_event(event('one',role='UserPromptSubmit'));b=c.freeze_event(event('two',role='UserPromptSubmit'))
        self.assertEqual(a[0],b[0]);self.assertNotEqual(a[1],b[1])
    def test_go_actual_adapter_identity_parity(self):
        storage=pathlib.Path(c.__file__).resolve().parents[2]
        if not shutil.which('go') or not (storage/'go.mod').exists():self.skipTest('Go/server source absent')
        corpus=[event(t,a,r) for t in ['plain','é <>& \u2028','password: CANARY','toKen: CANARY','token\v: plain','ſecret: plain']
                for a in [False,True] for r in ['Stop','UserPromptSubmit']]
        code='''package main
import("encoding/json";"os";"aifactory.local/storage/internal/capture")
func main(){ var events []json.RawMessage; json.NewDecoder(os.Stdin).Decode(&events); out:=[]map[string]string{}
for _,e:=range events{r,_,err:=capture.AdaptCodexSnapshotEvent(e,"project","source");if err!=nil{panic(err)};out=append(out,map[string]string{"id":r[0].MessageID,"text":r[0].Text})};json.NewEncoder(os.Stdout).Encode(out)}'''
        # Internal Go imports require a temporary directory INSIDE this module.
        # No worktree; only this synthetic runner, removed unconditionally.
        with tempfile.TemporaryDirectory(prefix='.codex-queue-parity-',dir=storage) as tmp:
            path=pathlib.Path(tmp)/'main.go';path.write_text(code)
            native=[dict(e,schema_version=2) for e in corpus]
            env=dict(os.environ,GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOFLAGS='-mod=readonly')
            proc=subprocess.run(['go','run',str(path)],cwd=storage,env=env,input=json.dumps(native),capture_output=True,text=True,timeout=60)
        self.assertEqual(proc.returncode,0,proc.stderr)
        for e,actual in zip(corpus,json.loads(proc.stdout)):
            _,raw,mid=c.freeze_event(e);frozen=json.loads(raw)
            self.assertEqual(actual['id'],mid)
            self.assertEqual(actual['text'],frozen.get('prompt',frozen.get('last_assistant_message')))
        print('Actual Go Codex adapter parity:',len(corpus),'events')

class Delivery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name).resolve();self.requests=[];self.stored={};self.code=200;self.delay=0;self.ack='2';self.wrong=False
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']));fixture.requests.append(raw)
                body=json.loads(raw);q=parse_qs(urlsplit(self.path).query)
                mid='v2/'+body['turn_id']+'/prompt'
                if body['hook_event_name']=='Stop':mid='v2/'+body['turn_id']+'/assistant/'+hashlib.sha256(body['last_assistant_message'].encode()).hexdigest()
                rid=[q['project'][0],q['source_instance'][0],body['session_id'],mid]
                # Stateful immutable-identity stub: authorization precedes replay;
                # duplicate bytes ACK without a second commit, changed body conflicts.
                code=fixture.code;committed=0
                if code==200:
                    old=fixture.stored.get(tuple(rid))
                    if old is not None and old!=body:code=409
                    elif old is None:fixture.stored[tuple(rid)]=body;committed=1
                time.sleep(fixture.delay)
                self.send_response(code)
                if fixture.ack:self.send_header('X-AF-Codex-Contract',fixture.ack)
                self.end_headers()
                try:self.wfile.write(json.dumps({'accepted':1,'committed':committed,'redactions':None,'receipts':[json.dumps(['wrong'] if fixture.wrong else rid)]}).encode())
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        cred=self.root/'credential.json';cred.write_text(json.dumps({'principal_id':'fixture','epoch':1,'secret':'AUTH_CANARY'}));cred.chmod(0o600)
        self.row={'root':str(self.root),'project':'project','source_instance':'codex-fixture','credential_file':str(cred)}
        self.mapping=self.root/'mapping.json';self.mapping.write_text(json.dumps({'projects':[self.row]}))
        self.env={k:v for k,v in os.environ.items() if not k.startswith('AF_CODEX_')}
        self.env.update(AF_CODEX_ENDPOINT=f'http://127.0.0.1:{self.server.server_port}',AF_CODEX_CATCHER_MAP=str(self.mapping),AF_CODEX_WORKER_PROJECT='project')
        self.code_runner='import sys,os;sys.path.insert(0,'+repr(str(pathlib.Path(c.__file__).parent))+');import codex_capture_catcher as c;c.ENDPOINT=os.environ["AF_CODEX_ENDPOINT"];c.main()'
    def invoke(self,e=None,mode=None):
        e=dict(e or event(),cwd=str(self.root))
        proc=subprocess.run([sys.executable,'-B','-c',self.code_runner]+(['--'+mode] if mode else []),input=json.dumps(e),env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertNotIn('AUTH_CANARY',proc.stderr);self.assertNotIn('fixture assistant',proc.stderr)
        return json.loads(proc.stderr.split('af-codex-capture ')[-1])
    def queue(self):
        return c.queue_for(self.row,self.env,'fixture')
    def due(self):
        q=self.queue();q.db.execute('UPDATE items SET next=0');q.close()
    def caller(self,body,finish=None):
        # Real SQLite queue + real loopback HTTP; only factory selects tiny cap.
        factory=c.queue_for
        def opened(*args):
            q=factory(*args);q.max_receipts=1
            if finish:
                original=q.finish
                def wrapped(item,result):
                    state=original(item,result);finish(q,item,result);return state
                q.finish=wrapped
            return q
        with patch.object(c,'queue_for',side_effect=opened),patch.object(c,'ENDPOINT',self.env['AF_CODEX_ENDPOINT']):
            result=c.deliver(self.row,self.env,body)
        self.assertFalse(result.get('error','').startswith('queue/credential failure'),result)
        return result
    def seed_pending(self,body,created=1):
        key,raw,_=c.freeze_event(body);q=self.queue()
        q.enqueue(key,raw,1);q.db.execute('UPDATE items SET created=? WHERE id=?',(created,key));q.close()
        return key
    def assert_evicted(self,result):
        self.assertEqual(result['current_state'],'receipt_evicted')
        self.assertEqual(result['delivery_confirmation'],'not_retained')
        self.assertFalse(result['delivered']);self.assertTrue(result['drained_delivered'])
        self.assertEqual(result['queue']['receipts'],1)
    def test_old_pending_ack_can_evict_its_own_receipt(self):
        current=event(turn='old');key=self.seed_pending(current)
        q=self.queue();q.db.execute('UPDATE items SET next=? WHERE id=?',(time.time()+60,key));q.close()
        self.assertTrue(self.caller(event(turn='new'))['delivered'])
        self.due();result=self.caller(current);self.assert_evicted(result)
        self.assertEqual(len(self.requests),2);self.assertEqual(len(self.stored),2)
        q=self.queue();self.assertIsNone(q.db.execute('SELECT id FROM items WHERE id=?',(key,)).fetchone());q.close()
    def test_other_worker_prunes_after_ack_before_current_state_read(self):
        current=event(turn='current');self.seed_pending(current)
        def competing_writer(q,item,result):
            # Independent connection and real ACK transaction at the exact race boundary.
            other=self.queue();other.max_receipts=1
            key,raw,_=c.freeze_event(event(turn='competitor'));other.enqueue(key,raw,1)
            claimed=other.claim();other.close()
            response=c.post_bytes(self.env['AF_CODEX_ENDPOINT'],'project','codex-fixture',{},claimed['body'])
            self.assertTrue(response.get('delivered'),response)
            def work():
                other=self.queue();other.max_receipts=1
                try:Queue.finish(other,claimed,response)
                finally:other.close()
            errors=[]
            def checked():
                try:work()
                except BaseException as exc:errors.append(exc)
            worker=threading.Thread(target=checked);worker.start();worker.join(3)
            self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
        self.assert_evicted(self.caller(current,competing_writer))
        self.assertEqual(len(self.requests),2);self.assertEqual(len(self.stored),2)
    def test_unrelated_drained_receipt_not_current_delivery(self):
        self.seed_pending(event(turn='earlier'))
        result=self.caller(event(turn='current'))
        self.assertTrue(result['drained_delivered']);self.assertFalse(result['delivered'])
        self.assertEqual(result['current_state'],'pending')
        self.assertNotIn('delivery_confirmation',result);self.assertEqual(len(self.requests),1)
    def evict_prompt(self):
        original=event('original prompt',role='UserPromptSubmit',turn='replay')
        self.assertTrue(self.caller(original)['delivered'])
        self.assertTrue(self.caller(event(turn='later'))['delivered'])
        key,_,_=c.freeze_event(original);q=self.queue()
        self.assertIsNone(q.db.execute('SELECT id FROM items WHERE id=?',(key,)).fetchone());q.close()
        return original
    def test_evicted_replay_identical_bytes_duplicate_ack_without_new_commit(self):
        original=self.evict_prompt();result=self.caller(original)
        self.assertTrue(result['delivered']);self.assertEqual(result['committed'],0)
        self.assertEqual(self.requests[0],self.requests[2]);self.assertEqual(len(self.stored),2)
        self.assertTrue(self.caller(original)['deduplicated']);self.assertEqual(len(self.requests),3)
    def test_evicted_replay_respects_revocation_and_retains_blocked_payload(self):
        original=self.evict_prompt();self.code=403;result=self.caller(original)
        self.assertEqual(result['current_state'],'blocked');self.assertFalse(result['delivered'])
        self.assertEqual(result['http_status'],403);self.assertEqual(len(self.stored),2)
        self.assertEqual(self.requests[0],self.requests[2])
        self.caller(original);self.assertEqual(len(self.requests),3)
        q=self.queue();self.assertEqual(q.status()['blocked'],1)
        key,raw,_=c.freeze_event(original)
        self.assertEqual(q.db.execute('SELECT body FROM items WHERE id=?',(key,)).fetchone()[0],raw);q.close()
    def test_evicted_changed_prompt_server_conflict_is_not_overwrite(self):
        self.evict_prompt();result=self.caller(event('changed prompt',role='UserPromptSubmit',turn='replay'))
        self.assertEqual(result['http_status'],409);self.assertEqual(result['current_state'],'blocked')
        self.assertFalse(result['delivered']);self.assertEqual(len(self.stored),2)
        self.assertNotEqual(self.requests[0],self.requests[2])
        self.assertEqual(next(v for v in self.stored.values() if v['turn_id']=='replay')['prompt'],'original prompt')
    def test_timeout_after_commit_restart_exact_replay_and_dedupe(self):
        self.delay=1.4
        result=self.invoke();self.assertTrue(result['queued']);self.assertFalse(result['delivered'])
        self.assertEqual(len(self.stored),1)
        self.delay=0;self.due();self.assertTrue(self.invoke(mode='flush')['delivered'])
        self.assertEqual(self.requests[0],self.requests[1]);self.assertEqual(len(self.stored),1)
        self.assertTrue(self.invoke()['deduplicated']);self.assertEqual(len(self.requests),2)
    def test_distinct_stops_and_continued_flag(self):
        self.invoke(event('one',False));self.assertTrue(self.invoke(event('one',True))['deduplicated'])
        self.invoke(event('two',True));self.assertEqual(len(self.stored),2);self.assertEqual(len(self.requests),2)
    def test_prompt_change_refused_locally(self):
        self.invoke(event('one',role='UserPromptSubmit'))
        result=self.invoke(event('two',role='UserPromptSubmit'))
        self.assertEqual(result['error'],'identity payload conflict');self.assertEqual(len(self.requests),1)
    def test_revoked_grant_retained_blocked(self):
        self.code=403;self.assertEqual(self.invoke()['current_state'],'blocked');self.invoke()
        self.assertEqual(len(self.requests),1);self.assertEqual(self.invoke(mode='status')['queue']['blocked'],1)
    def test_wrong_receipt_and_missing_header_retained(self):
        self.wrong=True;self.assertFalse(self.invoke()['delivered']);self.due();self.wrong=False;self.ack=None
        self.assertFalse(self.invoke(mode='flush')['delivered']);self.assertEqual(self.invoke(mode='status')['queue']['pending'],1)
    def test_worker_restarts_without_native_event(self):
        self.code=503;self.invoke()
        args=[sys.executable,'-B','-c',self.code_runner,'--worker']
        p=subprocess.Popen(args,env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        time.sleep(.15);p.terminate();p.communicate(timeout=3)
        self.code=200;self.due()
        p=subprocess.Popen(args,env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            end=time.monotonic()+4
            while time.monotonic()<end and len(self.requests)<2:time.sleep(.05)
            self.assertEqual(len(self.requests),2)
        finally:p.terminate();p.communicate(timeout=3)
        self.assertTrue(self.invoke()['deduplicated']);self.assertEqual(len(self.requests),2)
    def test_worker_requires_exact_single_project(self):
        self.env['AF_CODEX_WORKER_PROJECT']='other';self.assertIn('error',self.invoke(mode='flush'));self.assertEqual(self.requests,[])
        self.env['AF_CODEX_WORKER_PROJECT']='project'
        self.mapping.write_text(json.dumps({'projects':[self.row,{**self.row,'root':str(self.root/'nested')}]}))
        self.assertIn('error',self.invoke(mode='flush'));self.assertEqual(self.requests,[])
    def test_provider_partition_and_private_scope(self):
        self.code=503;self.invoke()
        q=self.queue();self.assertEqual(q.status()['pending'],1)
        other=Queue(q.path.parent,{'endpoint':self.env['AF_CODEX_ENDPOINT'],'project':'project','source':'codex-fixture','principal':'agent:fixture'})
        self.assertEqual(other.status()['pending'],0);other.close();q.close()
    def test_spool_redacts_and_never_persists_auth(self):
        self.code=503;self.invoke(event('token: PAYLOAD_CANARY'))
        q=self.queue();raw=q.path.read_bytes();q.close()
        self.assertNotIn(b'AUTH_CANARY',raw);self.assertNotIn(b'PAYLOAD_CANARY',raw);self.assertIn(REDACTED.encode(),raw)
    def test_parallel_same_event_single_send(self):
        self.delay=.2
        args=[sys.executable,'-B','-c',self.code_runner];data=json.dumps(dict(event(),cwd=str(self.root)))
        children=[subprocess.Popen(args,env=self.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(5)]
        for p in children:p.stdin.write(data);p.stdin.close();p.stdin=None
        results=[p.communicate(timeout=8) for p in children]
        self.assertTrue(all(p.returncode==0 for p in children));self.assertEqual(len(self.requests),1)
        self.assertTrue(all('error' not in json.loads(err.split('af-codex-capture ')[-1]) for _,err in results))
    def test_queue_full_visible_not_evicted(self):
        q=self.queue();q.max_items=0
        from unittest.mock import patch
        with patch.object(c,'queue_for',return_value=q),patch.object(c,'ENDPOINT',self.env['AF_CODEX_ENDPOINT']):
            result=c.deliver(self.row,self.env,event())
        self.assertEqual(result['error'],'queue full; turn not queued');self.assertFalse(result['queued']);self.assertEqual(self.requests,[])

if __name__=='__main__':unittest.main()
