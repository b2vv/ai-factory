"""Stateful daemon fixtures: no real Docker, host registration or product access."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
CODE=Path(__file__).resolve().parents[2]/'runtime/session-size-docker'
FAKE=r'''#!/usr/bin/env python3
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
a=sys.argv[1:];base=Path(os.environ['DAEMON_STATE']);fault=os.environ.get('DAEMON_FAULT','')
if a[0]=='late':
 time.sleep(7.2);Path(a[1]).write_text(a[2]);sys.exit(0)
with (base/'calls').open('a') as f:f.write(json.dumps(a)+'\n')
def target(x):
 if len(x)==64 and all(c in 'abcdef0123456789' for c in x):return base/x
 return base/hashlib.sha256(x.encode()).hexdigest()
if a[0]=='create':
 name=a[a.index('--name')+1];cid=hashlib.sha256(name.encode()).hexdigest();p=base/cid
 if fault=='createfail' or (fault=='validatorfail' and 'validator' in name):sys.exit(1)
 data={'args':a,'name':name,'id':cid,'labels':dict(v.split('=',1) for i,v in enumerate(a) if i and a[i-1]=='--label')}
 if fault=='replacement':data['labels']['ai-factory.invocation']='foreign'
 if fault=='late':
  subprocess.Popen([sys.executable,__file__,'late',str(p),json.dumps(data)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);time.sleep(30)
 p.write_text(json.dumps(data));print(cid)
elif a[0]=='ps':
 owner=a[a.index('--filter')+1].split('=',2)[2]
 for p in base.iterdir():
  if len(p.name)==64:
   d=json.loads(p.read_text())
   if d['labels']['ai-factory.invocation']==owner:print(d['id']+'|'+d['name']+'|'+owner)
elif a[0]=='inspect':
 if '--format' in a and 'ai-factory.invocation' in a[a.index('--format')+1]:
  for name in a[a.index('--format')+2:]:
   p=target(name)
   if p.exists():
    d=json.loads(p.read_text());print(d['id']+'|/'+d['name']+'|'+d['labels']['ai-factory.invocation'])
  sys.exit(0)
 p=target(a[-1])
 if not p.exists():sys.exit(1)
 d=json.loads(p.read_text());c=d['args'];fmt=a[a.index('--format')+1] if '--format' in a else ''
 if 'ai-factory.invocation' in fmt:print(d['id']+'|'+d['labels']['ai-factory.invocation'])
 elif 'NanoCpus' in fmt:
  image=c[c.index('--entrypoint')+2];uid=c[c.index('--user')+1]
  print('created|'+image+'|'+uid+'|none|true|false|2000000000|2147483648|2147483648|128|["ALL"]|["no-new-privileges"]|rw,noexec,nosuid,size=268435456|python3|0|0|0|0||private')
 elif 'range .Mounts' in fmt:
  for i,x in enumerate(c):
   if x=='--mount':
    m=c[i+1];v=dict(z.split('=',1) for z in m.split(',') if '=' in z);print('bind|'+v['src']+'|'+v['dst']+'|'+('false' if 'readonly' in m else 'true'))
 elif 'range .Config.Env' in fmt:
  for v in [c[i+1] for i,x in enumerate(c) if x=='--env']+['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','SEMGREP_IN_DOCKER=1','SEMGREP_USER_AGENT_APPEND=Docker','PYTHONIOENCODING=utf8','PYTHONUNBUFFERED=1']:print(v)
 elif 'ExitCode' in fmt:print('exited|0|false|false')
 else:print('[{}]')
elif a[0]=='start':
 if fault=='hang':time.sleep(30)
 if fault=='startfail':sys.exit(1)
 d=json.loads(target(a[-1]).read_text())
 print('VALID' if 'validator' in d['name'] else json.dumps({'status':'OK','result':{'checkpoint_id':'a'*32+'-1-'+'b'*12}}))
elif a[0]=='rm':
 if fault=='cleanupfail':sys.exit(1)
 for cid in a[2:]:
  p=target(cid);p.unlink();print(cid)
else:sys.exit(2)
'''
class StatefulLifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve()
  for n in ['repo','store','work','bin','daemon']:(self.p/n).mkdir()
  (self.p/'bin/docker').write_text(FAKE);(self.p/'bin/docker').chmod(0o700)
 def tearDown(self):self.tmp.cleanup()
 def launch(self,fault='',offset=0,work='work',extra=None,host='codex'):
  env=dict(os.environ,PATH=str(self.p/'bin')+':'+os.environ['PATH'],DAEMON_STATE=str(self.p/'daemon'),DAEMON_FAULT=fault,AF16_EVENT_STARTED=str(int(time.time())-offset))
  env.pop('AI_FACTORY_HANDOFF',None)
  if extra:env.update(extra)
  cmd=['sh',str(CODE/'dispatch.sh'),'checkpoint','--root',str(self.p/'repo'),'--store',str(self.p/'store'),'--work',str(self.p/work),'--host',host,'--session','synthetic']
  return subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 def objects(self):return [x for x in (self.p/'daemon').iterdir() if len(x.name)==64]
 def finish(self,p):return p.communicate(b'{}',timeout=12)
 def test_rejected_work_preserves_existing_files(self):
  sentinel=self.p/"work/parser-projection.tmp";sentinel.write_text("preserve")
  p=self.launch();self.finish(p);self.assertNotEqual(p.returncode,0);self.assertEqual(sentinel.read_text(),"preserve");self.assertEqual(self.objects(),[])
 def test_cleanup_batches_both_targets_before_reserve_expires(self):
  import shlex
  clock=self.p/'clock';clock.write_text('0')
  script = """set -eu
work=$1;code=$2;clock=$3
name=ai-factory-codex-worker-fixture;validator=ai-factory-codex-validator-fixture
created=1;validator_created=1;active=;timer=;cleanup_end=2
worker_id=$(printf '%064d' 1);validator_id=$(printf '%064d' 2)
date() { cat "$clock"; }
run() {
 case "$2" in
 ps)
  [ "$6" = "label=ai-factory.invocation=$name" ]
  printf '%s|%s|%s\n' "$worker_id" "$name" "$name" "$validator_id" "$validator" "$name"
  printf 1 > "$clock";;
 rm)
  [ "$4" = "$worker_id" ] && [ "$5" = "$validator_id" ]
  printf '%s\n' "$worker_id" "$validator_id"
  printf 2 > "$clock";;
 *) return 2;;
 esac
}
. "$code/cleanup.sh"
cleanup
"""
  result=subprocess.run(['sh','-c',script,'fixture',str(self.p/'work'),str(CODE),str(clock)],capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads((self.p/'work/cleanup-status.json').read_text())['status'],'REMOVED')
 def test_parser_names_for_both_hosts(self):
  fake=Path(__file__).parent/'fake_selector.py'
  wrapper="#!/usr/bin/env python3\nimport sys,os,runpy\nfrom pathlib import Path\nif sys.argv[1]=='create':Path(os.environ['NAME_RECORD']).write_text(sys.argv[sys.argv.index('--name')+1])\nrunpy.run_path("+repr(str(fake))+",run_name='__main__')\n"
  (self.p/'bin/docker').write_text(wrapper)
  for host in ['codex','claude']:
   work=self.p/('parser-'+host);work.mkdir()
   env=dict(os.environ,PATH=str(self.p/'bin')+':'+os.environ['PATH'],FAKE_STATE=str(self.p/'parser-state'),NAME_RECORD=str(self.p/'parser-name'),AF16_EVENT_STARTED=str(int(time.time())))
   result=subprocess.run(['sh',str(CODE/'session-key.sh'),host,str(work)],input=json.dumps({'hook_event_name':'SessionStart','session_id':'synthetic','cwd':str(self.p/'repo')}).encode(),capture_output=True,env=env,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr);self.assertRegex((self.p/'parser-name').read_text(),'^ai-factory-'+host+'-parser-[A-Za-z0-9]+$')
   self.assertEqual(list(work.glob('*.tmp')),[]);self.assertEqual(json.loads((work/'cleanup-status.json').read_text())['status'],'REMOVED')
 def test_claude_names_and_cleanup(self):
  p=self.launch(host='claude');out,err=self.finish(p);self.assertEqual(p.returncode,0,err);self.assertEqual(self.objects(),[])
  creates=[json.loads(x) for x in (self.p/'daemon/calls').read_text().splitlines() if json.loads(x)[0]=='create']
  for c in creates:self.assertRegex(c[c.index('--name')+1],r'^ai-factory-claude-(worker|validator)-[A-Za-z0-9]+$')
 def test_success_state_and_metadata(self):
  p=self.launch(extra={'cleanup_done':'1','cleanup_rc':'0','command_limit':'0'});out,err=self.finish(p);self.assertEqual(p.returncode,0,err);self.assertEqual(self.objects(),[])
  creates=[json.loads(x) for x in (self.p/'daemon/calls').read_text().splitlines() if json.loads(x)[0]=='create']
  self.assertEqual(len(creates),2)
  for c in creates:self.assertIn('com.docker.compose.project=ai-factory',c);self.assertIn('com.docker.compose.config-hash=ai-factory-ephemeral-v1',c);self.assertIn('com.docker.compose.oneoff=False',c);self.assertRegex(c[c.index('--name')+1],r'^ai-factory-codex-(worker|validator)-[A-Za-z0-9]+$')
  self.assertEqual(json.loads((self.p/'work/cleanup-status.json').read_text())['status'],'REMOVED');self.assertTrue((self.p/'work/result.json').exists())
 def test_delayed_create_is_reconciled(self):
  p=self.launch('late');self.finish(p);self.assertNotEqual(p.returncode,0);self.assertEqual(self.objects(),[]);self.assertEqual(json.loads((self.p/'work/cleanup-status.json').read_text())['status'],'REMOVED')
 def test_errors_and_timeout(self):
  for fault in ['createfail','startfail','validatorfail','hang','cleanupfail','replacement']:
   with self.subTest(fault=fault):
    # Short original budget makes every timeout case bounded and deterministic.
    w='work-'+fault;(self.p/w).mkdir();p=self.launch(fault,5,w);self.finish(p);self.assertNotEqual(p.returncode,0)
    if fault not in ['cleanupfail','replacement']:self.assertEqual(self.objects(),[])
    else:
     self.assertTrue(self.objects());self.assertEqual(json.loads((self.p/w/'cleanup-status.json').read_text())['status'],'UNRESOLVED')
     for f in self.objects():f.unlink()
 def test_signal_cleans_existing_container(self):
  p=self.launch('hang');p.stdin.write(b'{}');p.stdin.close();p.stdin=None
  until=time.monotonic()+3
  while time.monotonic()<until:
   if (self.p/'daemon/calls').exists() and '"start"' in (self.p/'daemon/calls').read_text():break
   time.sleep(.02)
  p.terminate();p.communicate(timeout=10);self.assertEqual(self.objects(),[])
 def test_parallel_invocations_do_not_collide(self):
  (self.p/'work2').mkdir();a=self.launch();b=self.launch(work='work2');self.finish(a);self.finish(b)
  self.assertEqual((a.returncode,b.returncode),(0,0));self.assertEqual(self.objects(),[])
  calls=[json.loads(x) for x in (self.p/'daemon/calls').read_text().splitlines()];names=[c[c.index('--name')+1] for c in calls if c[0]=='create'];self.assertEqual(len(set(names)),4)
if __name__=='__main__':unittest.main(verbosity=2)
