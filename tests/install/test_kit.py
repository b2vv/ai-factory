import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('kit',Path(__file__).resolve().parents[2]/'tools/kit.py')
k=importlib.util.module_from_spec(spec);spec.loader.exec_module(k)

class KitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.src=self.base/'release';self.src.mkdir()
        self.root=self.base/'fake-home'/'toolkit'
        self.release({'docs/a.md':'one','optional/x.md':'optional'})

    def release(self, files, version='1'):
        # Only disposable fixture files, not a real installation.
        for p in self.src.rglob('*'):
            if p.is_file():p.unlink()
        entries=[]
        for name,text in files.items():
            p=self.src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            entries.append({'path':name,'sha256':k.digest(p.read_bytes()),'component':'optional' if name.startswith('optional/') else 'core'})
        (self.src/'release-manifest.json').write_bytes(k.encode({'schema_version':2,'version':version,'components':{'core':{},'optional':{}},'files':entries}))
        (self.src/'checksums.sha256').write_text(''.join(k.digest(p.read_bytes())+'  '+str(p.relative_to(self.src))+'\n' for p in sorted(self.src.rglob('*')) if p.is_file()))

    def apply(self,components=()):
        p=k.plan(self.src,self.root,components)
        return k.apply(self.src,self.root,components,p['plan_id'])

    def restore(self,tx):
        p=k.rollback_plan(self.root,tx)
        return k.rollback(self.root,tx,p.get('plan_id'))

    def test_plan_no_writes_and_optional_selection(self):
        p=k.plan(self.src,self.root)
        self.assertFalse(self.root.exists());self.assertNotIn('optional/x.md',p['files'])
        self.assertIn('optional/x.md',k.plan(self.src,self.root,['optional'])['files'])

    def test_install_repeat_noop(self):
        result=self.apply();self.assertEqual('APPLIED',result['status'])
        self.assertEqual('one',(self.root/'docs/a.md').read_text())
        self.assertEqual('NOOP',self.apply()['status'])

    def test_update_then_rollback_restores_managed_preserves_foreign(self):
        self.apply();(self.root/'personal.txt').write_text('owner')
        self.release({'docs/a.md':'two','docs/b.md':'new'},'2')
        tx=self.apply()['transaction'];self.assertEqual('two',(self.root/'docs/a.md').read_text())
        self.restore(tx);self.assertEqual('one',(self.root/'docs/a.md').read_text())
        self.assertFalse((self.root/'docs/b.md').exists());self.assertEqual('owner',(self.root/'personal.txt').read_text())
        self.assertEqual('NOOP',self.restore(tx)['status'])

    def test_removal_and_optional_component_rollback(self):
        self.apply(['optional']);self.release({'docs/b.md':'new'},'2')
        tx=self.apply()['transaction'];self.assertFalse((self.root/'docs/a.md').exists())
        self.assertFalse((self.root/'optional/x.md').exists())
        self.restore(tx);self.assertEqual('one',(self.root/'docs/a.md').read_text())
        self.assertTrue((self.root/'optional/x.md').exists())

    def test_local_edit_blocks_update(self):
        self.apply();(self.root/'docs/a.md').write_text('owner edit')
        self.release({'docs/a.md':'two'},'2')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        self.assertEqual('owner edit',(self.root/'docs/a.md').read_text())

    def test_unmanaged_collision_even_identical(self):
        p=self.root/'docs/a.md';p.parent.mkdir(parents=True);p.write_text('one')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        self.assertFalse((self.root/k.STATE).exists())

    def test_stale_plan_and_race_before_write_preserved(self):
        self.apply();self.release({'docs/a.md':'two'},'2');p=k.plan(self.src,self.root)
        (self.root/'docs/a.md').write_text('owner')
        with self.assertRaises(ValueError):k.apply(self.src,self.root,[],p['plan_id'])
        (self.root/'docs/a.md').write_text('one');p=k.plan(self.src,self.root)
        orig=k.guarded_write
        def raced(path,*args):
            if path.name=='a.md':path.write_text('concurrent')
            return orig(path,*args)
        with patch.object(k,'guarded_write',side_effect=raced):
            with self.assertRaises(ValueError):k.apply(self.src,self.root,[],p['plan_id'])
        self.assertEqual('concurrent',(self.root/'docs/a.md').read_text())
        with self.assertRaises(ValueError):k.rollback_plan(self.root,k.pending(self.root))

    def test_partial_apply_can_rollback(self):
        self.apply();self.release({'docs/a.md':'two','docs/b.md':'new'},'2')
        orig=k.guarded_write;calls=[]
        def fail(path,*args):
            calls.append(path)
            if len(calls)==2:raise OSError('fixture injected IO failure')
            return orig(path,*args)
        with patch.object(k,'guarded_write',side_effect=fail):
            with self.assertRaises(OSError):self.apply()
        tx=k.pending(self.root);self.assertIsNotNone(tx)
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        self.restore(tx);self.assertEqual('one',(self.root/'docs/a.md').read_text())
        self.assertIsNone(k.pending(self.root))

    def test_crash_after_publication_before_receipt_progress(self):
        self.apply();self.release({'docs/a.md':'two'},'2');orig=k.guarded_write
        def fail(path,*args):orig(path,*args);raise OSError('after write')
        with patch.object(k,'guarded_write',side_effect=fail):
            with self.assertRaises(OSError):self.apply()
        self.restore(k.pending(self.root));self.assertEqual('one',(self.root/'docs/a.md').read_text())

    def test_rollback_concurrent_change_and_corrupt_backup_block(self):
        self.apply();self.release({'docs/a.md':'two'},'2');tx=self.apply()['transaction']
        (self.root/'docs/a.md').write_text('later')
        with self.assertRaises(ValueError):k.rollback_plan(self.root,tx)
        (self.root/'docs/a.md').write_text('two')
        (self.root/k.STATE/'objects'/k.digest(b'one')).write_text('broken')
        with self.assertRaises(ValueError):k.rollback_plan(self.root,tx)
        self.assertEqual('two',(self.root/'docs/a.md').read_text())

    def test_rollback_only_latest_and_receipt_integrity(self):
        first=self.apply()['transaction'];self.release({'docs/a.md':'two'},'2');second=self.apply()['transaction']
        with self.assertRaises(ValueError):k.rollback_plan(self.root,first)
        p=self.root/k.STATE/'receipts'/(second+'.json');obj=json.loads(p.read_text());obj['before']['version']='tamper';p.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):k.rollback_plan(self.root,second)

    def test_symlink_escape_hardlink_and_parent_file_block(self):
        for name in ['../escape','/absolute','.env','.ssh/id','a/../b',k.STATE+'/installed.json']:
            with self.assertRaises(ValueError):k.relative(name)
        self.root.parent.mkdir();self.root.symlink_to(self.src)
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        self.root.unlink();self.root.mkdir();(self.root/'docs').write_text('parent file')
        with self.assertRaises((ValueError,OSError)):k.plan(self.src,self.root)
        (self.root/'docs').unlink();(self.root/'docs').mkdir();os.link(self.src/'docs/a.md',self.root/'docs/a.md')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)

    def test_release_tamper_extra_and_symlink_block(self):
        (self.src/'docs/a.md').write_text('changed')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        self.release({'a':'a'});(self.src/'extra').write_text('unlisted')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)
        (self.src/'extra').unlink();(self.src/'extra').symlink_to(self.src/'a')
        with self.assertRaises(ValueError):k.plan(self.src,self.root)

    def test_lock_contention(self):
        with k.lock(self.root):
            with self.assertRaises(BlockingIOError):self.apply()
        self.assertFalse((self.root/'docs/a.md').exists())

    def test_install_rollback_exact_files_only(self):
        tx=self.apply()['transaction'];(self.root/'docs/foreign.md').write_text('keep')
        self.restore(tx);self.assertFalse((self.root/'docs/a.md').exists())
        self.assertTrue((self.root/'docs/foreign.md').exists())

    def test_cli_default_and_mutations_without_execute_are_readonly(self):
        for action in [[],['install'],['update']]:
            result=subprocess.run([sys.executable,'-B',str(Path(k.__file__)),*action,'--package',str(self.src),'--root',str(self.root)],capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stdout);self.assertFalse(self.root.exists())
        result=subprocess.run([sys.executable,'-B',str(Path(k.__file__)),'install','--execute','--package',str(self.src),'--root',str(self.root)],capture_output=True,text=True)
        self.assertEqual(1,result.returncode);self.assertFalse(self.root.exists())

    def test_cli_install_update_rollback(self):
        def cli(*args):
            r=subprocess.run([sys.executable,'-B',str(Path(k.__file__)),*args,'--root',str(self.root)],capture_output=True,text=True)
            self.assertEqual(0,r.returncode,r.stdout);return json.loads(r.stdout)
        p=cli('plan','--package',str(self.src))
        a=cli('install','--package',str(self.src),'--execute','--exclusive-window','--plan-id',p['plan_id'])
        p=cli('rollback','--transaction',a['transaction'])
        cli('rollback','--transaction',a['transaction'],'--execute','--exclusive-window','--plan-id',p['plan_id'])
        self.assertFalse((self.root/'docs/a.md').exists())

    def test_interrupted_rollback_resume(self):
        self.apply();self.release({'docs/a.md':'two','docs/b.md':'new'},'2');tx=self.apply()['transaction']
        original=k.atomic
        def fail(path,*args,**kwargs):
            original(path,*args,**kwargs)
            if path.name=='installed.json':raise OSError('crash after restored state')
        with patch.object(k,'atomic',side_effect=fail):
            with self.assertRaises(OSError):self.restore(tx)
        self.assertEqual(tx,k.pending(self.root))
        self.restore(tx);self.assertEqual('one',(self.root/'docs/a.md').read_text())
        self.assertIsNone(k.pending(self.root))

    def test_git_metadata_excluded_from_source_payload(self):
        (self.src/'.git').mkdir();(self.src/'.git'/'config').write_text('fixture metadata')
        self.apply();self.assertFalse((self.root/'.git').exists())

    def test_actual_release_install_repeat_rollback(self):
        release=Path(__file__).resolve().parents[2]
        components=['planning','review','session-guard','graphify']
        p=k.plan(release,self.root,components)
        a=k.apply(release,self.root,components,p['plan_id'])
        self.assertEqual('NOOP',k.plan(release,self.root,components)['status'])
        for name,signature in p['files'].items():
            self.assertEqual(signature,k.signature(self.root/name))
        self.assertTrue((self.root/'runtime/session-size/session_guard.py').is_file())
        self.restore(a['transaction'])
        for name in p['files']:self.assertFalse((self.root/name).exists())

if __name__=='__main__':unittest.main(verbosity=2)
