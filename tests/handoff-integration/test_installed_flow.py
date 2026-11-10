"""Executes actual installed runtime only in disposable fake homes and Git roots."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fixture_connector',ROOT/'tools/connect-handoff.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);k=c.installer
SUMMARY=dict(goal='synthetic integration handoff',done='offline only',pending='native receipt not tested',evidence='isolated fixture',constraints='no live writes')

class InstalledFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.home=self.base/'home';self.home.mkdir()
        self.kit=self.base/'managed kit';self.pkg=self.base/'package';self.roots=[]
        for name in ['Cargo','Courses','Cassiopeia','dg']:
            root=self.base/name;root.mkdir();self.roots.append(root)
            subprocess.run(['git','init','-q',str(root)],check=True)
            subprocess.run(['git','-C',str(root),'-c','user.email=fixture@example.invalid','-c','user.name=Fixture','-c','core.hooksPath=/dev/null','commit','--allow-empty','-qm','fixture'],check=True)
        self.legacy=self.home/'.agents/ai-factory/session-size/session_guard.py';self.legacy.parent.mkdir(parents=True)
        self.legacy.write_text('# old fixture legacy\n')
        self.spec={'home':str(self.home),'managed_root':str(self.kit),'store':str(self.base/'store'),'roots':list(map(str,self.roots)),
            'profile_path':str(self.base/'native-profile.json'),'registration_root':str(self.base/'registration'),
            'hosts':['claude','codex'],'python':str(Path(sys.executable).resolve()),
            'legacy':{'path':str(self.legacy),'before_sha256':hashlib.sha256(self.legacy.read_bytes()).hexdigest()},
            'retire':[{'host':'codex','event':ev,'command':'legacy docker handoff fixture'} for ev in c.EVENTS]}
        self.codex=self.home/'.codex/hooks.json';self.codex.parent.mkdir()
        self.codex.write_text(json.dumps({'hooks':{ev:[{'hooks':[{'type':'command','command':'legacy docker handoff fixture'},{'type':'command','command':'archive fixture unchanged'}]}] for ev in c.EVENTS}}))
        self.claude=self.home/'.claude/settings.json';self.claude.parent.mkdir()
        self.claude.write_text(json.dumps({'model':'unchanged','hooks':{'SessionStart':[{'hooks':[{'type':'command','command':'status fixture unchanged'}]}]}}))
        self.original={str(p):p.read_bytes() for p in [self.codex,self.claude,self.legacy]}
        self.release('1');p=k.plan(self.pkg,self.kit);k.apply(self.pkg,self.kit,[],p['plan_id'])
    def release(self,version):
        self.pkg.mkdir(exist_ok=True)
        payload={'rules/agent-entry.md':b'fixture entry\n'}
        for name in [c.NATIVE,c.GUARD]:payload[name]=(ROOT/name).read_bytes()+('\n# synthetic fixture version '+version+'\n').encode()
        entries=[]
        for name,data in payload.items():
            p=self.pkg/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            entries.append({'path':name,'component':'core','sha256':k.digest(data)})
        manifest=k.encode({'schema_version':2,'version':version,'components':{'core':{}},'files':entries})
        (self.pkg/'release-manifest.json').write_bytes(manifest)
        (self.pkg/'checksums.sha256').write_text(''.join(k.digest(data)+'  '+name+'\n' for name,data in sorted({**payload,'release-manifest.json':manifest}.items())))
    def run_cli(self,args,payload='',token=None):
        env=dict(os.environ,HOME=str(self.home),PYTHONDONTWRITEBYTECODE='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1')
        env.pop('AI_FACTORY_HANDOFF',None)
        if token:env['AI_FACTORY_HANDOFF']=token
        p=subprocess.run(args,input=payload,capture_output=True,text=True,timeout=10,env=env)
        self.assertEqual(0,p.returncode,p.stderr);return p.stdout
    def register(self):
        p=c.plan(self.spec);return c.apply(self.spec,p['plan_id'],True)
    def test_four_project_global_legacy_flow_update_rollback(self):
        registration=self.register();commands={h:c.command(c.validate_spec(self.spec),h) for h in c.HOSTS}
        registered={str(p):p.read_bytes() for p in [self.codex,self.claude,self.legacy]}
        for root in self.roots:
            for host in c.HOSTS:
                payload={'hook_event_name':'SessionStart','session_id':'fixture-source','cwd':str(root)}
                out=self.run_cli(shlex.split(commands[host]),json.dumps(payload));self.assertIn('AI_FACTORY_NATIVE_IDENTITY',out)
                entry=self.legacy if host=='claude' else self.kit/c.NATIVE
                args=[sys.executable,'-I',str(entry),'checkpoint','--host',host,'--session','fixture-source','--cwd',str(root)]
                if host=='codex':args+=['--profile',self.spec['profile_path']]
                token=self.run_cli(args,json.dumps(SUMMARY)).strip()
                payload['session_id']='fixture-target'
                out=self.run_cli(shlex.split(commands[host]),json.dumps(payload),token);self.assertIn(SUMMARY['goal'],out)
                repeat=self.run_cli(shlex.split(commands[host]),json.dumps(payload),token);self.assertNotIn(SUMMARY['goal'],repeat)
                if host=='claude':
                    legacy=self.run_cli([sys.executable,'-I',str(self.legacy),'hook','--host','claude'],json.dumps(payload),token)
                    self.assertNotIn(SUMMARY['goal'],legacy)
        self.assertEqual(8,len(list((self.base/'store').glob('claim-*'))))
        self.assertFalse(list(self.kit.rglob('*.pyc')))
        self.assertEqual('NOOP',self.register()['status'])
        self.release('2');p=k.plan(self.pkg,self.kit);upgrade=k.apply(self.pkg,self.kit,[],p['plan_id'])
        self.assertTrue(c.verify(self.spec)['kit_changed']);self.register();self.assertFalse(c.verify(self.spec)['kit_changed'])
        self.assertEqual(registered,{str(p):p.read_bytes() for p in [self.codex,self.claude,self.legacy]})
        for host in c.HOSTS:
            payload={'hook_event_name':'SessionStart','session_id':'after-update','cwd':str(self.roots[0])}
            self.assertIn('AI_FACTORY_NATIVE_IDENTITY',self.run_cli(shlex.split(commands[host]),json.dumps(payload)))
        rp=k.rollback_plan(self.kit,upgrade['transaction']);k.rollback(self.kit,upgrade['transaction'],rp['plan_id'])
        self.assertTrue(c.verify(self.spec)['kit_changed'])
        self.assertEqual(registered,{str(p):p.read_bytes() for p in [self.codex,self.claude,self.legacy]})
        # Reconcile identity-only registration first, roll back those receipt transitions, then original registration.
        current=c.current(c.validate_spec(self.spec))
        c.rollback(self.spec,current['id'],True)
        c.rollback(self.spec,registration['transaction'],True)
        self.assertEqual(self.original,{str(p):p.read_bytes() for p in [self.codex,self.claude,self.legacy]})
        self.assertEqual(8,len(list((self.base/'store').glob('claim-*'))))
        self.assertFalse(list(self.kit.rglob('*.pyc')))

if __name__=='__main__':unittest.main()
