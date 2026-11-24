import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
s = importlib.util.spec_from_file_location('capture_connector', ROOT/'tools/connect-capture.py')
c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
k = c.installer


class Connector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve(); self.home = self.base/'home'; self.home.mkdir()
        self.root = self.base/'kit'; self.package = self.base/'package'; self.reg = self.base/'registration'
        self.private = self.base/'private'; self.private.mkdir(mode=0o700)
        self.projects=[]
        for i,n in enumerate(['project-c','project-b','project-d','project-a'],1):
            p=self.base/n;p.mkdir();subprocess.run(['/usr/bin/git','init','-q',str(p)],check=True)
            cred=self.private/(n+'.json');cred.write_text('{}');cred.chmod(0o600)
            self.projects.append({'root':str(p),'project':f'00000000-0000-4000-8000-{i:012d}', 'source_instance':'claude-'+n,
                                  'credential_file':str(cred),'queue_dir':str(self.private/'capture-queue'),'status_file':str(self.private/(n+'.log'))})
        self.spec={'schema':1,'home':str(self.home),'managed_root':str(self.root),'registration_root':str(self.reg),
                   'mapping_path':str(self.reg/'mapping.json'),'python':str(Path(sys.executable).resolve()),'projects':self.projects,'retire':[]}
        self.global_path=self.home/'.claude/settings.json';self.global_path.parent.mkdir();self.global_path.write_text('{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo unrelated"}]}]},"theme":"dark"}\n')
        self.release();self.install()
        for row in self.projects:
            p=Path(row['root'])/'.claude/settings.local.json';p.parent.mkdir()
            cmd=' '.join(shlex.quote(x) for x in [f'AF_CAPTURE_ENDPOINT=http://127.0.0.1:8780',f"AF_CAPTURE_PROJECT={row['project']}",f"AF_CAPTURE_SOURCE={row['source_instance']}",f"AF_CAPTURE_AGENT_CREDENTIAL_FILE={row['credential_file']}",'sh',str(self.root/'runtime/storage/deploy/capture-bridge/claude-code-stop-hook.sh')])
            hook={'type':'command','command':cmd,'timeout':15};p.write_bytes(k.encode({'permissions':{'allow':['Read']},'hooks':{'Stop':[{'hooks':[hook,{'type':'command','command':'echo keep'}]}]}}))
            self.spec['retire'].append({'path':str(p),'command':cmd,'hook_sha256':k.digest(k.encode(hook))})

    def release(self, dispatcher=True):
        payload={'rules/agent-entry.md':'entry',c.BRIDGE:'# bridge',c.QUEUE:'# queue'}
        if dispatcher:payload[c.DISPATCH]='CAPTURE_DISPATCH_API = 1\n'
        elif (self.package/c.DISPATCH).exists():(self.package/c.DISPATCH).unlink()
        entries=[]
        for n,t in payload.items():
            p=self.package/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t);entries.append({'path':n,'sha256':k.digest(p.read_bytes()),'component':'core'})
        (self.package/'release-manifest.json').write_bytes(k.encode({'schema_version':2,'version':'test','components':{'core':{}},'files':entries}))
        (self.package/'checksums.sha256').write_text(''.join(k.digest((self.package/n).read_bytes())+'  '+n+'\n' for n in sorted([e['path'] for e in entries]+['release-manifest.json'])))

    def install(self):
        p=k.plan(self.package,self.root);k.apply(self.package,self.root,[],p['plan_id'])

    def apply(self):
        p=c.plan(self.spec);return c.apply(self.spec,p['plan_id'],True)

    def test_four_migration_preserves_unrelated_and_idempotent(self):
        result=self.apply();self.assertEqual(result['status'],'APPLIED');self.assertEqual(c.plan(self.spec)['status'],'NOOP')
        doc=json.loads(self.global_path.read_text());self.assertEqual(doc['theme'],'dark');self.assertEqual(len(doc['hooks']['Stop']),2)
        for row in self.projects:
            d=json.loads((Path(row['root'])/'.claude/settings.local.json').read_text());self.assertEqual(d['permissions'],{'allow':['Read']});self.assertEqual(d['hooks']['Stop'][0]['hooks'],[{'type':'command','command':'echo keep'}])
        self.assertEqual(c.verify(self.spec)['status'],'VERIFIED')
        self.assertEqual(c.find_transaction(self.spec,result['plan_id']),result['transaction'])
        self.assertEqual(os.stat(self.reg/'mapping.json').st_mode&0o777,0o600)

    def test_shared_settings_pins_only_own_hook_and_permissions(self):
        # C6: other tools and the owner edit the shared settings file; only our hook and the permissions are pinned.
        self.apply(); saved=self.global_path.read_bytes()
        doc=json.loads(saved);doc['theme']='light';doc['hooks']['Stop'].append({'hooks':[{'type':'command','command':'echo other'}]})
        raw=json.dumps(doc,indent=3).encode();self.global_path.write_bytes(raw)
        self.assertEqual('NOOP',c.plan(self.spec)['status']);self.assertEqual('VERIFIED',c.verify(self.spec)['status'])
        self.assertEqual(raw,self.global_path.read_bytes())
        doc['permissions']={'defaultMode':'bypassPermissions'};self.global_path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'registered permissions drift'):c.plan(self.spec)
        doc=json.loads(saved);doc['hooks']['Stop']=[g for g in doc['hooks']['Stop'] if 'echo unrelated' in json.dumps(g)]
        self.global_path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'registered hook drift'):c.verify(self.spec)

    def test_record_without_permissions_pin_recovers_it_from_receipts(self):
        self.apply();cur=self.reg/k.STATE/'current.json'
        rec=k.read_tx(cur);rec.pop('permissions');k.write_tx(cur,rec)
        doc=json.loads(self.global_path.read_text());doc['theme']='light';self.global_path.write_text(json.dumps(doc))
        self.assertEqual('PLANNED',c.plan(self.spec)['status'])  # the next apply writes the pin
        doc['permissions']={'allow':['Bash']};self.global_path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'registered permissions drift'):c.plan(self.spec)

    def test_two_phase_global_then_retirement_only_reconcile(self):
        retire = self.spec['retire']; self.spec['retire'] = []
        self.apply()
        for item in retire:
            self.assertIn(item['command'], Path(item['path']).read_text())
        self.spec['retire'] = retire
        p = c.plan(self.spec)
        self.assertEqual([e['path'] for e in p['changes']], sorted(e['path'] for e in retire))
        c.apply(self.spec, p['plan_id'], True)
        self.assertEqual(c.plan(self.spec)['status'], 'NOOP')
        self.assertEqual(len(json.loads(self.global_path.read_text())['hooks']['Stop']), 2)
        self.spec['retire'] = []
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_rollback_restores_exact_bytes(self):
        names=c.target_baselines(self.spec);before={n:Path(n).read_bytes() if Path(n).exists() else None for n in names}
        tx=self.apply()['transaction'];p=c.rollback_plan(self.spec,tx);c.rollback(self.spec,tx,p['plan_id'],True)
        for n,v in before.items():self.assertEqual(Path(n).read_bytes() if Path(n).exists() else None,v)
        p=c.rollback_plan(self.spec,tx);self.assertEqual(c.rollback(self.spec,tx,p['plan_id'],True)['status'],'NOOP')

    def test_partial_failure_retains_pending_and_guarded_rollback(self):
        original=k.guarded_write;calls=[]
        def failure(*args):
            calls.append(str(args[0]))
            if len(calls)==3:raise OSError('fixture interruption')
            return original(*args)
        p=c.plan(self.spec)
        with patch.object(k,'guarded_write',side_effect=failure):
            with self.assertRaises(OSError):c.apply(self.spec,p['plan_id'],True)
        self.assertEqual(calls[:2],[self.spec['mapping_path'],str(self.global_path)])
        with self.assertRaises(ValueError):c.plan(self.spec)
        tx=c.find_transaction(self.spec,p['plan_id']);self.assertIsNotNone(tx)
        rp=c.rollback_plan(self.spec,tx);c.rollback(self.spec,tx,rp['plan_id'],True)
        self.assertEqual(c.plan(self.spec)['status'],'PLANNED')

    def test_concurrent_change_blocks_no_overwrite(self):
        p=c.plan(self.spec);self.global_path.write_text('{"theme":"changed"}')
        with self.assertRaises(ValueError):c.apply(self.spec,p['plan_id'],True)
        self.assertEqual(json.loads(self.global_path.read_text()),{'theme':'changed'})

    def test_rollback_foreign_edit_blocks(self):
        tx=self.apply()['transaction'];self.global_path.write_text('{"theme":"changed"}')
        with self.assertRaises(ValueError):c.rollback_plan(self.spec,tx)

    def test_exact_retirement_proof_not_arbitrary_command(self):
        p=Path(self.spec['retire'][0]['path']);d=json.loads(p.read_text());h=d['hooks']['Stop'][0]['hooks'][0];h['command']='echo foreign';p.write_bytes(k.encode(d));self.spec['retire'][0].update(command=h['command'],hook_sha256=k.digest(k.encode(h)))
        with self.assertRaises(ValueError):c.plan(self.spec)

    def test_legacy_queue_mismatch_blocks(self):
        self.spec['projects'][0]['queue_dir']=str(self.private/'different')
        with self.assertRaises(ValueError):c.plan(self.spec)

    def test_no_dispatcher_preview_allowed_apply_blocked(self):
        self.release(dispatcher=False);self.install();p=c.plan(self.spec)
        with self.assertRaises(ValueError):c.apply(self.spec,p['plan_id'],True)

    def test_duplicate_root_unknown_schema_symlink_blocks(self):
        for change in ['duplicate','schema','symlink']:
            spec=copy.deepcopy(self.spec)
            if change=='duplicate':spec['projects'][1]['root']=spec['projects'][0]['root']
            elif change=='schema':spec['projects'][0]['extra']='bad'
            else:
                link=self.base/'link';link.symlink_to(self.projects[0]['root']);spec['projects'][0]['root']=str(link)
            with self.assertRaises(ValueError):c.plan(spec)

    def test_scope_change_after_registration_requires_explicit_review(self):
        self.apply();spec=copy.deepcopy(self.spec);spec['projects'][0]['source_instance']='changed'
        with self.assertRaises(ValueError):c.plan(spec)

    def test_private_mapping_and_status_required(self):
        p=Path(self.projects[0]['status_file']);p.write_text('');p.chmod(0o644)
        with self.assertRaises(ValueError):c.plan(self.spec)

    def test_registration_lock_blocks_parallel_writer(self):
        p=c.plan(self.spec); self.reg.mkdir(mode=0o700)
        with k.lock(self.reg):
            with self.assertRaises(BlockingIOError):c.apply(self.spec,p['plan_id'],True)
        self.assertEqual(c.plan(self.spec)['status'],'PLANNED')

    def test_crash_after_receipt_before_pending_is_recoverable(self):
        p=c.plan(self.spec); original=k.atomic
        def fail(path,*args,**kwargs):
            if Path(path).name=='pending.json':raise OSError('fixture crash')
            return original(path,*args,**kwargs)
        with patch.object(k,'atomic',side_effect=fail):
            with self.assertRaises(OSError):c.apply(self.spec,p['plan_id'],True)
        tx=c.find_transaction(self.spec,p['plan_id']);self.assertIsNotNone(tx)
        rp=c.rollback_plan(self.spec,tx);c.rollback(self.spec,tx,rp['plan_id'],True)
        self.assertEqual(c.plan(self.spec)['status'],'PLANNED')

    def test_cli_summary_hides_encoded_settings(self):
        p=c.plan(self.spec);s=json.dumps(c.summary(p));self.assertNotIn('bytes',s);self.assertNotIn('echo unrelated',s);self.assertNotIn('credential_file',s)


if __name__=='__main__':unittest.main()
