import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RUNTIME=Path(os.environ.get('AF_TEST_BASE',str(Path(__file__).resolve().parents[2])))/'runtime/scanners'
spec=importlib.util.spec_from_file_location('followup_helper',RUNTIME/'container_helper.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.store=self.root/'store';self.store.mkdir();(self.store/'owner.json').write_text('{"owner":"AI Factory","schema_version":1}')
        self.token='a'*64;h.acquire_lease(self.store,self.token,{'container_name':'factory-db-'+'a'*32})
        self.cache=self.store/('download-'+self.token)/'cache';(self.cache/'db').mkdir(parents=True)
        (self.cache/'db/trivy.db').write_bytes(b'SYNTHETIC DB - NOT EXECUTED')
        now=dt.datetime.now(dt.timezone.utc);(self.cache/'db/metadata.json').write_text(json.dumps({'Version':2,'UpdatedAt':(now-dt.timedelta(hours=1)).isoformat(),'NextUpdate':(now+dt.timedelta(hours=1)).isoformat()}))
        self.m={'engines':{'trivy':{'image':'test.invalid/trivy@sha256:'+'a'*64}},'db':{'repository':'test.invalid/db@sha256:'+'b'*64,'schema':2,'max_age_hours':24}}
        files={n:h.s.sha(self.cache/n) for n in ('db/trivy.db','db/metadata.json')};self.snapshot=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        self.dest=self.store/self.snapshot;(self.dest/'db').mkdir(parents=True)
        for n in files:(self.dest/n).write_bytes((self.cache/n).read_bytes())
        (self.dest/'snapshot.json').write_text(json.dumps({'schema_version':1,'engine_image':self.m['engines']['trivy']['image'],'db_source':self.m['db']['repository'],'files':files}))
        for p in self.dest.rglob('*'):p.chmod(0o555 if p.is_dir() else 0o444)
        self.dest.chmod(0o555);self.before={str(p.relative_to(self.dest)):(h.s.sha(p),p.stat().st_mode) for p in self.dest.rglob('*') if p.is_file()}
        self.state={'Status':'exited','Running':False,'OOMKilled':False,'Dead':False,'Error':'','ExitCode':0}
        (self.store/'unrelated').write_text('do not touch')

    def tearDown(self):
        for p in self.root.rglob('*'):
            if p.is_dir():p.chmod(0o700)
        self.tmp.cleanup()

    def test_noop_removes_only_duplicate(self):
        r=h.publish(self.store,self.token,self.cache,self.m,self.state,True)
        self.assertEqual(r,{'status':'NOOP','snapshot':self.snapshot,'duplicate_removed':True})
        self.assertFalse((self.cache.parent/'staging'/self.snapshot).exists())
        self.assertEqual(self.before,{str(p.relative_to(self.dest)):(h.s.sha(p),p.stat().st_mode) for p in self.dest.rglob('*') if p.is_file()})
        self.assertEqual((self.store/'unrelated').read_text(),'do not touch');self.assertTrue((self.store/'.update-lease').exists())

    def test_duplicate_cleanup_failure_never_noop_success(self):
        with patch.object(h.u,'remove_private_tree',side_effect=OSError('cleanup failed')):
            with self.assertRaises(OSError):h.publish(self.store,self.token,self.cache,self.m,self.state,True)
        self.assertTrue((self.store/'.update-lease').exists());self.assertTrue((self.cache.parent/'staging'/self.snapshot).exists())

    def test_invalid_destination_never_removed_or_success(self):
        (self.dest/'db/trivy.db').chmod(0o644);(self.dest/'db/trivy.db').write_bytes(b'CORRUPT');(self.dest/'db/trivy.db').chmod(0o444)
        with patch.object(h.u,'remove_private_tree') as remove:
            with self.assertRaises(h.s.Blocked):h.publish(self.store,self.token,self.cache,self.m,self.state,True)
            remove.assert_not_called()
        self.assertEqual((self.dest/'db/trivy.db').read_bytes(),b'CORRUPT')

    def test_wrong_owner_never_removes(self):
        with patch.object(h.u,'remove_private_tree') as remove:
            with self.assertRaises(h.s.Blocked):h.publish(self.store,'b'*64,self.cache,self.m,self.state,True)
            remove.assert_not_called()

    def test_generated_argv_restores_proven_fs_shape(self):
        work=self.root/'work';work.mkdir();store=self.root/'other-store';store.mkdir();(store/'owner.json').write_text('{"owner":"AI Factory","schema_version":1}')
        def mapped(value,*args):
            if str(value)=='/work':return work
            if str(value)=='/store':return store
            return Path(value,*args)
        import shutil
        with patch.object(h,'Path',side_effect=mapped),patch.object(h,'budget'),patch.object(h.s,'load_manifest',return_value=self.m),patch.object(shutil,'disk_usage',return_value=SimpleNamespace(free=12*1024**3)):
            self.assertEqual(h.cli(['lease','--host-work','/host/run','--host-store','/host/store','--token','c'*64]),0)
        self.assertEqual(json.loads((work/'updater.json').read_text())['command'],['fs','--download-db-only','--db-repository',self.m['db']['repository'],'--cache-dir','/cache','--disable-telemetry'])

    def test_host_argv_matches_generated_shape(self):
        line=next(x for x in (RUNTIME/'scan.sh').read_text().splitlines() if '"$pin"' in x and '--download-db-only' in x)
        argv=shlex.split(line);self.assertEqual(argv[argv.index('$pin')+1:],['fs','--download-db-only','--db-repository','$dbpin','--cache-dir','/cache','--disable-telemetry'])
