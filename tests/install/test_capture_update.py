"""Disposable actual-connector fixtures; no host settings or credentials used."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
k=load('capture_update_fixture_kit',ROOT/'tools/kit.py')
u=load('capture_update_fixture',ROOT/'tools/capture_update.py')

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.pkg=self.base/'release';self.pkg.mkdir()
        self.home=self.base/'home';self.home.mkdir();self.root=self.home/'kit'
        self.private=self.base/'private';self.private.mkdir(mode=0o700)
        self.project=self.base/'project';self.project.mkdir()
        subprocess.run(['/usr/bin/git','init','-q',str(self.project)],check=True)
        self.credential=self.private/'agent.json';self.credential.write_text('{}');self.credential.chmod(0o600)
        self.spec={'schema':1,'home':str(self.home),'managed_root':str(self.root),
            'registration_root':str(self.private/'registration'),'mapping_path':str(self.private/'registration/map.json'),
            'python':str(Path(sys.executable).resolve()),'projects':[{'root':str(self.project),
            'project':'11111111-1111-4111-8111-111111111111','source_instance':'claude-fixture',
            'credential_file':str(self.credential),'queue_dir':str(self.private/'queue'),'status_file':str(self.private/'status.log')}]}
        self.sp=self.private/'spec.json';self.save_spec()
        self.release('1',dispatcher=False)
        p=k.plan(self.pkg,self.root,[]);k.apply(self.pkg,self.root,[],p['plan_id'])
        self.release('2')
    def save_spec(self):
        self.sp.write_bytes(k.encode(self.spec));self.sp.chmod(0o600)
    def release(self,version,dispatcher=True):
        shutil.rmtree(self.pkg);self.pkg.mkdir()
        names=['tools/kit.py','tools/capture_update.py','tools/connect-capture.py','tools/connect-project.py',
               'runtime/storage/deploy/capture-bridge/capture_bridge.py',
               'runtime/storage/deploy/capture-bridge/capture_queue.py',
               'runtime/storage/deploy/capture-bridge/claude_capture_dispatcher.py']
        if not dispatcher:names.remove(u.DISPATCHER)
        files={n:(ROOT/n).read_bytes() for n in names};files['rules/agent-entry.md']=b'fixture';files['docs/version.md']=version.encode()
        entries=[]
        for n,raw in files.items():
            p=self.pkg/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            entries.append({'path':n,'sha256':k.digest(raw),'component':'core'})
        (self.pkg/'release-manifest.json').write_bytes(k.encode({'schema_version':2,'version':version,'components':{'core':{}},'files':entries}))
        (self.pkg/'checksums.sha256').write_text(''.join(k.digest(p.read_bytes())+'  '+str(p.relative_to(self.pkg))+'\n' for p in sorted(self.pkg.rglob('*')) if p.is_file()))
    def plan(self,spec=True):return u.plan(k,self.pkg,self.root,[],self.sp if spec else None)
    def apply(self,spec=True):
        p=self.plan(spec);return u.apply(k,self.pkg,self.root,[],self.sp if spec else None,p['plan_id'],True)
    def rollback(self,tx):
        p=u.rollback_plan(k,self.root,tx);return u.rollback(k,self.root,tx,p.get('plan_id'),True)
    def test_capture_from_another_kit_for_a_bound_home_is_refused(self):  # T15 A17
        d=self.home/'.agents/.ai-factory-instructions';d.mkdir(parents=True);d.chmod(0o700)
        first=self.home/'first-kit';(d/'owner.json').write_bytes(k.encode({'schema':1,'root':str(first)}));(d/'owner.json').chmod(0o600)
        with self.assertRaises(ValueError) as cm:self.plan()
        reason=k.blocked_reason(cm.exception)
        self.assertTrue(reason.startswith('HOME_BOUND_TO_ANOTHER_KIT'),reason);self.assertIn(str(first),reason)
        self.assertFalse((self.home/'.claude/settings.json').exists())
    def test_explicit_registration_normal_update_and_idempotence(self):
        self.assertFalse(u.active(k,self.root));r=self.apply();self.assertEqual('APPLIED',r['status'])
        self.assertTrue(u.active(k,self.root));self.assertEqual('NOOP',self.plan(False)['status'])
        self.release('3');p=self.plan(False);self.assertEqual('PLANNED',p['status'])
        r=self.apply(False);self.assertEqual('APPLIED',r['status']);self.assertEqual('NOOP',self.plan(False)['status'])
    def test_stale_spec_or_host_plan_has_no_mutations(self):
        p=self.plan();self.spec['projects'][0]['source_instance']='changed';self.save_spec()
        with self.assertRaises(ValueError):u.apply(k,self.pkg,self.root,[],self.sp,p['plan_id'],True)
        self.assertEqual('1',k.current(self.root)['version']);self.assertFalse((self.root/k.STATE/u.PENDING).exists())
    def test_registered_spec_is_pinned_not_followed(self):
        self.apply();self.spec['projects'][0]['source_instance']='changed';self.save_spec()
        self.assertEqual('NOOP',self.plan(False)['status'])
        with self.assertRaises(ValueError):self.plan(True)  # Explicit scope migration remains separately reviewed.
    def test_package_tamper_blocks_before_candidate_import(self):
        (self.pkg/u.CONNECTOR).write_text("raise RuntimeError('must not import')")
        with self.assertRaises(ValueError):self.plan()
    def test_postkit_failure_is_blocked_and_recoverable(self):
        real=u.connector;calls=[0]
        def fail_after(*a,**kw):
            mod=real(*a,**kw)
            if kw or len(a)>3:
                def fail(*args,**kwargs):raise ValueError('injected')
                mod.apply=fail
            return mod
        p=self.plan()
        with patch.object(u,'connector',side_effect=fail_after):
            r=u.apply(k,self.pkg,self.root,[],self.sp,p['plan_id'],True)
        self.assertEqual('BLOCKED',r['status']);self.assertEqual('2',k.current(self.root)['version'])
        with self.assertRaises(ValueError):self.plan()
        self.assertEqual('ROLLED_BACK',self.rollback(r['transaction'])['status'])
        self.assertEqual('1',k.current(self.root)['version'])
    def test_combined_rollback_restores_host_and_registration_before_kit(self):
        r=self.apply();self.assertTrue((self.home/'.claude/settings.json').exists())
        self.rollback(r['transaction']);self.assertFalse((self.home/'.claude/settings.json').exists())
        self.assertFalse((self.root/k.STATE/u.REG).exists());self.assertEqual('1',k.current(self.root)['version'])
        self.assertEqual('NOOP',self.rollback(r['transaction'])['status'])
    def test_crash_after_kit_commit_before_result_save_recovers(self):
        p=self.plan();real=k.apply
        def crash(*a,**kw):
            real(*a,**kw);raise KeyboardInterrupt()
        with patch.object(k,'apply',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):u.apply(k,self.pkg,self.root,[],self.sp,p['plan_id'],True)
        ident=k.read_json(self.root/k.STATE/u.PENDING)['id']
        self.assertEqual('ROLLED_BACK',self.rollback(ident)['status']);self.assertEqual('1',k.current(self.root)['version'])
    def test_crash_after_connector_commit_before_result_save_recovers(self):
        p=self.plan();real=u.connector
        def load(*a,**kw):
            mod=real(*a,**kw)
            if len(a)>3:
                apply=mod.apply
                def crash(*a,**kw):
                    apply(*a,**kw);raise KeyboardInterrupt()
                mod.apply=crash
            return mod
        with patch.object(u,'connector',side_effect=load):
            with self.assertRaises(KeyboardInterrupt):u.apply(k,self.pkg,self.root,[],self.sp,p['plan_id'],True)
        ident=k.read_json(self.root/k.STATE/u.PENDING)['id']
        self.assertEqual('ROLLED_BACK',self.rollback(ident)['status']);self.assertFalse((self.home/'.claude/settings.json').exists())
    def test_completed_rollback_pending_marker_cleanup_is_guarded(self):
        r=self.apply();ident=r['transaction'];self.rollback(ident)
        k.atomic(self.root/k.STATE/u.PENDING,k.encode({'id':ident}))
        self.assertEqual('NOOP',self.rollback(ident)['status']);self.assertFalse((self.root/k.STATE/u.PENDING).exists())
    def test_unrelated_host_edit_blocks_rollback(self):
        r=self.apply();p=self.home/'.claude/settings.json';d=json.loads(p.read_text());d['owner']='new';p.write_bytes(k.encode(d))
        with self.assertRaises(ValueError):self.rollback(r['transaction'])
    def test_public_does_not_expose_connector_backups(self):
        p=self.plan();pub=json.dumps(u.public(p));self.assertNotIn('"bytes"',pub);self.assertNotIn('"_capture"',pub)
        r=self.apply();pub=json.dumps(u.public(u.rollback_plan(k,self.root,r['transaction'])));self.assertNotIn('backups',pub);self.assertNotIn('"bytes"',pub)
    def test_cli_auto_reconciles_and_unknown_capture_not_activated(self):
        cmd=[sys.executable,str(ROOT/'tools/kit.py'),'update','--package',str(self.pkg),'--root',str(self.root)]
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        self.assertNotIn('capture',json.loads(r.stdout));self.assertFalse((self.home/'.claude/settings.json').exists())
        r=subprocess.run(cmd+['--capture-spec',str(self.sp)],capture_output=True,text=True);p=json.loads(r.stdout)
        r=subprocess.run(cmd+['--capture-spec',str(self.sp),'--execute','--exclusive-window','--plan-id',p['plan_id']],capture_output=True,text=True)
        self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertEqual('APPLIED',json.loads(r.stdout)['status'])
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual('NOOP',json.loads(r.stdout)['status'])

if __name__=='__main__':unittest.main()
