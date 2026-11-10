"""Isolated native integration fixtures. No live host, Docker, archive, or transcripts."""
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

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_fixture', ROOT/'runtime/session-size/native.py')
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)
g = n.guard
SUMMARY = dict(goal='synthetic recovery goal', done='fixture passed', pending='human review', evidence='fixture-only', constraints='no live mutation')


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.base = Path(self.tmp.name).resolve()
        self.roots=[]
        for name in ['Cargo','Courses','Cassiopeia','dg']:
            root=self.base/name;root.mkdir();self.roots.append(root)
            subprocess.run(['git','init','-q',str(root)],check=True)
            subprocess.run(['git','-C',str(root),'-c','user.email=fixture@example.invalid','-c','user.name=Fixture',
                            '-c','core.hooksPath=/dev/null','commit','--allow-empty','-qm','fixture'],check=True)
        self.store=self.base/'store';self.profile=self.base/'profile.json'
        self.data={'schema':1,'managed_root':str(ROOT),'store':str(self.store),'roots':list(map(str,self.roots))}
        self.profile.write_text(json.dumps(self.data));self.profile.chmod(0o600)
    def tearDown(self):self.tmp.cleanup()
    def payload(self,root=None,sid='source',ev='SessionStart'):
        return {'hook_event_name':ev,'session_id':sid,'cwd':str(root or self.roots[0])}
    def call(self,*args,input=''):
        return subprocess.run([sys.executable,'-I',str(ROOT/'runtime/session-size/native.py'),*args,
            '--profile',str(self.profile),'--host','claude'],input=input,text=True,capture_output=True,timeout=10)
    def test_four_roots_two_hosts_share_implementation_store(self):
        for root in self.roots:
            for host in ['claude','codex']:
                out=n.event(self.profile,host,self.payload(root));text=json.dumps(out)
                self.assertIn('AI_FACTORY_NATIVE_IDENTITY',text);self.assertIn('native.py',text)
                self.assertIn('--profile',text);self.assertNotIn('docker',text.lower());self.assertNotIn('--store',text)
        self.assertEqual(8,len(list(self.store.glob('session-*.json'))))
    def test_checkpoint_resume_and_repeat(self):
        p=self.call('checkpoint','--session','source','--cwd',str(self.roots[0]),input=json.dumps(SUMMARY))
        self.assertEqual(0,p.returncode,p.stderr);token=p.stdout.strip()
        out=n.event(self.profile,'claude',self.payload(sid='fresh'),token)
        self.assertIn(SUMMARY['goal'],json.dumps(out))
        again=n.event(self.profile,'claude',self.payload(sid='fresh'),token)
        self.assertNotIn(SUMMARY['goal'],json.dumps(again));self.assertEqual(1,len(list(self.store.glob('claim-*.json'))))
    def test_same_target_noop_after_drift_expiry(self):
        token=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        g.resume(self.store,token,'claude','fresh',self.roots[0])
        (self.roots[0]/'new').write_text('changed')
        with patch.object(g.time,'time',return_value=time.time()+g.TTL+100):
            self.assertEqual('',g.resume(self.store,token,'claude','fresh',self.roots[0]))
    def test_stop_never_claims(self):
        token=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        self.assertIn('DEFERRED',json.dumps(n.event(self.profile,'claude',self.payload(sid='fresh',ev='Stop'),token)))
        self.assertFalse(list(self.store.glob('claim-*')))
        self.assertIn(SUMMARY['goal'],json.dumps(n.event(self.profile,'claude',self.payload(sid='fresh'),token)))
    def test_unenrolled_no_monitor_and_explicit_blocks(self):
        self.data['roots']=list(map(str,self.roots[1:]));self.profile.write_text(json.dumps(self.data))
        self.assertEqual({},n.event(self.profile,'claude',self.payload()))
        with self.assertRaises(ValueError):n.event(self.profile,'claude',self.payload(),'a'*32+'-1-'+'b'*12)
        p=self.call('checkpoint','--session','source','--cwd',str(self.roots[0]),input=json.dumps(SUMMARY))
        self.assertNotEqual(0,p.returncode);self.assertFalse(self.store.exists())
    def test_alternate_store_and_invalid_identity_before_write(self):
        for sid in ['',123,'bad;identity','x'*257]:
            with self.assertRaises(ValueError):n.event(self.profile,'claude',self.payload(sid=sid))
        with self.assertRaises(ValueError):n.event(self.profile,'claude',self.payload(),store=self.base/'other')
        self.assertFalse(self.store.exists())
    def test_profiles_duplicate_keys_roots_paths_rejected(self):
        self.profile.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):n.load_profile(self.profile)
        self.data['roots']*=2;self.profile.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):n.load_profile(self.profile)
        self.profile.unlink();self.profile.symlink_to(self.base/'missing')
        with self.assertRaises(ValueError):n.load_profile(self.profile)
        self.assertFalse(self.store.exists())
    def test_no_transcript_reads_or_denial_bypass(self):
        payload=self.payload();payload['transcript_path']=str(self.base/'denied-transcript')
        original=Path.lstat
        def denied(path,*args,**kwargs):
            if str(path)==payload['transcript_path']:raise PermissionError('fixture')
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',denied):
            out=n.event(self.profile,'claude',payload)
        self.assertIn('UNKNOWN',json.dumps(out));self.assertFalse(Path(payload['transcript_path']).exists())
    def test_malformed_payload_no_private_echo(self):
        p=self.call('hook',input='{"private_value":"dont-echo-this",')
        self.assertEqual(0,p.returncode);self.assertIn('BLOCKED',p.stdout);self.assertNotIn('dont-echo-this',p.stdout+p.stderr)
        self.assertFalse(self.store.exists())
    def test_direct_guard_cli_requires_same_profile(self):
        guard=ROOT/'runtime/session-size/session_guard.py'
        p=subprocess.run([sys.executable,'-I',str(guard),'checkpoint','--host','claude','--store',str(self.store)],input='{}',capture_output=True,text=True)
        self.assertNotEqual(0,p.returncode);self.assertFalse(self.store.exists())
        p=subprocess.run([sys.executable,'-I',str(guard),'checkpoint','--host','claude','--profile',str(self.profile),
                          '--session','source','--cwd',str(self.roots[0])],input=json.dumps(SUMMARY),capture_output=True,text=True)
        self.assertEqual(0,p.returncode,p.stderr);self.assertTrue((self.store/(p.stdout.strip()+'.json')).exists())
    def test_expiry_refresh_and_claimed_pointer_new_generation(self):
        now=time.time()
        with patch.object(g.time,'time',return_value=now):a=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        before=(self.store/(a+'.json')).read_bytes()
        with patch.object(g.time,'time',return_value=now+g.TTL):self.assertEqual(a,g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY))
        with patch.object(g.time,'time',return_value=now+g.TTL+0.001):b=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        self.assertNotEqual(a,b);self.assertEqual(before,(self.store/(a+'.json')).read_bytes())
        with patch.object(g.time,'time',return_value=now+g.TTL+1):
            g.resume(self.store,b,'claude','new',self.roots[0]);c=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        self.assertNotEqual(b,c)
    def test_escaped_record_and_context_budgets_before_claim(self):
        summary={k:'\x01'*1600 for k in g.FIELDS}
        with self.assertRaisesRegex(ValueError,'read limit'):g.checkpoint(self.store,'claude','source',self.roots[0],summary)
        self.assertFalse(list(self.store.glob('*.json')))
        token=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY)
        key,_=g.identity('claude','fresh',self.roots[0]);_,state=g.state_for(self.store,key)
        with self.assertRaisesRegex(ValueError,'delivery limit'):
            g.resume_locked(self.store,token,'claude','fresh',self.roots[0],key,state,identity_text='x'*17000)
        self.assertFalse(list(self.store.glob('claim-*')));self.assertFalse((self.store/('session-'+key+'.json')).exists())
    def test_maximum_unicode_summary_roundtrips_cli(self):
        summary={k:'🌿'*1600 for k in g.FIELDS}
        p=self.call('checkpoint','--session','source','--cwd',str(self.roots[0]),input=json.dumps(summary,ensure_ascii=False))
        self.assertEqual(0,p.returncode,p.stderr)
        token=p.stdout.strip();self.assertLessEqual((self.store/(token+'.json')).stat().st_size,g.MAX_RECORD_BYTES)
        self.assertIn('🌿',json.dumps(n.event(self.profile,'claude',self.payload(sid='fresh'),token),ensure_ascii=False))
    def test_malformed_profile_type_and_pending_update(self):
        self.data['schema']=True;self.profile.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):n.load_profile(self.profile)
        self.data['schema']=1;self.profile.write_text(json.dumps(self.data))
        original=Path.exists
        def pending(path):
            return True if path == ROOT/'.ai-factory-state/pending.json' else original(path)
        with patch.object(Path,'exists',pending),self.assertRaisesRegex(ValueError,'update pending'):
            n.load_profile(self.profile)
        self.assertFalse(self.store.exists())
    def test_record_reader_boundary(self):
        self.store.mkdir(mode=0o700)
        target=self.store/'boundary.json'
        obj={'x':'x'*(g.MAX_RECORD_BYTES-len((json.dumps({'x':''},indent=2)+'\n').encode()))}
        g.atomic(target,obj);self.assertEqual(g.MAX_RECORD_BYTES,target.stat().st_size);self.assertEqual(obj,g.read_json(target))
        before=target.read_bytes();obj['x']+='x'
        with self.assertRaises(ValueError):g.atomic(target,obj)
        self.assertEqual(before,target.read_bytes())
    def test_incompatible_guard_api_blocks_before_state(self):
        for value in [None,True,2]:
            with patch.object(g,'HANDOFF_API',value),self.assertRaisesRegex(ValueError,'incompatible'):
                n.event(self.profile,'claude',self.payload())
        with patch.object(g,'resume',None),self.assertRaisesRegex(ValueError,'incompatible'):
            n.load_profile(self.profile)
        self.assertFalse(self.store.exists())
    def test_threshold_only_event_has_exact_profile_command(self):
        payload=self.payload(ev='PostToolUse')
        transcript=self.base/'synthetic-size-only'
        with transcript.open('wb') as f:f.truncate(g.LIMIT)
        payload['transcript_path']=str(transcript)
        out=n.event(self.profile,'claude',payload)
        text=json.dumps(out)
        self.assertIn('INCOMPLETE',text);self.assertIn(str(self.profile),text);self.assertIn('--profile',text)
        self.assertNotIn('--store',text);self.assertNotIn('docker',text.lower())
    def test_incompatible_exception_type_cli_is_bounded(self):
        directory=self.base/'incompatible/runtime/session-size';directory.mkdir(parents=True)
        (directory/'native.py').write_bytes((ROOT/'runtime/session-size/native.py').read_bytes())
        (directory/'session_guard.py').write_text('HANDOFF_API = 2\nLockBusy = 17\n')
        p=subprocess.run([sys.executable,'-I',str(directory/'native.py'),'checkpoint','--profile',str(self.profile),'--host','claude',
            '--session','source','--cwd',str(self.roots[0])],input=json.dumps(SUMMARY),text=True,capture_output=True)
        self.assertEqual(1,p.returncode);self.assertIn('BLOCKED',p.stderr);self.assertNotIn('Traceback',p.stderr)
        self.assertFalse(self.store.exists())
    def test_isolated_cli_never_writes_runtime_bytecode(self):
        installed=self.base/'installed';directory=installed/'runtime/session-size';directory.mkdir(parents=True)
        for name in ['native.py','session_guard.py']:(directory/name).write_bytes((ROOT/'runtime/session-size'/name).read_bytes())
        profile=self.base/'isolated-profile.json';data=dict(self.data,managed_root=str(installed));profile.write_text(json.dumps(data))
        for name in ['native.py','session_guard.py']:
            p=subprocess.run([sys.executable,'-I',str(directory/name),'checkpoint','--profile',str(profile),'--host','claude',
                '--session','source','--cwd',str(self.roots[0])],input=json.dumps(SUMMARY),capture_output=True,text=True)
            self.assertEqual(0,p.returncode,p.stderr)
            self.assertFalse(list(installed.rglob('*.pyc')))
    def test_partial_state_never_replayed(self):
        token=g.checkpoint(self.store,'claude','source',self.roots[0],SUMMARY);original=g.atomic
        def fail(path,obj):
            if path.name.startswith('claim-'):raise OSError('fixture')
            original(path,obj)
        with patch.object(g,'atomic',fail),self.assertRaises(OSError):g.resume(self.store,token,'claude','fresh',self.roots[0])
        with self.assertRaisesRegex(ValueError,'partial resume'):g.resume(self.store,token,'claude','fresh',self.roots[0])
        self.assertFalse(list(self.store.glob('claim-*')))

if __name__=='__main__':unittest.main()
