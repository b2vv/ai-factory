import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[2] / 'runtime/scanners'
spec = importlib.util.spec_from_file_location('container_helper', HERE / 'container_helper.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.config = {'schema_version': 1, 'root': '/explicit/project', 'sanitized_inputs_reviewed': True,
                       'files': {'a.py': hashlib.sha256(b'x=1\n').hexdigest()}}
        self.store = self.root / 'store'; self.store.mkdir()
        (self.store / 'owner.json').write_text(json.dumps({'owner': 'AI Factory', 'schema_version': 1}))
        self.token = 'a' * 64
        self.intent = {'container_name': 'factory-db-' + 'b' * 32}

    def tearDown(self):
        for p in self.root.rglob('*'):
            if p.is_dir(): p.chmod(0o700)
        self.tmp.cleanup()

    def test_plan_exact_per_file(self):
        p = h.plan(self.config, 501, 20)
        self.assertEqual(p['inputs'][0]['host'], '/explicit/project/a.py')
        self.assertEqual(p['inputs'][0]['local'], '/input/000000')
        self.assertEqual(p['user'], '501:20')

    def test_path_rejections(self):
        for p in ['/a/../b', '/a//b', '/a/', '/a\nb', '/a,b', '/a/$b', '/', 'relative']:
            with self.subTest(p=p), self.assertRaises(h.s.Blocked): h.host_path(p)

    def test_input_name_rejections(self):
        for name in ['../a.py', '/a.py', '.secret.py', 'x//a.py', 'x\ta.py']:
            with self.subTest(name=name), self.assertRaises(h.s.Blocked):
                h.plan(dict(self.config, files={name: 'a'*64}), 501, 20)

    def test_uid_rejections(self):
        for uid,gid in [(0,0),(-1,0),(True,0),(501,-1)]:
            with self.assertRaises(h.s.Blocked): h.identity(uid,gid)

    def test_attestation_required(self):
        with self.assertRaises(h.s.Blocked): h.plan(dict(self.config, sanitized_inputs_reviewed=False),501,20)

    def test_stage_real_allowlist_and_coverage(self):
        inputs = self.root/'inputs'; inputs.mkdir()
        data={'a.py':b'x=1\n','package.json':b'{"devDependencies":{"x":"1.0.0"}}','yarn.lock':b'# yarn lockfile v1\n'}
        c=dict(self.config, files={n:hashlib.sha256(b).hexdigest() for n,b in data.items()}); m=h.plan(c,501,20)
        for x in m['inputs']: (inputs/Path(x['local']).name).write_bytes(data[x['name']])
        out=self.root/'stage';self.assertTrue(h.stage(c,m,out,inputs)['staged'])
        self.assertEqual({p.name for p in out.iterdir()},set(data))
        self.assertEqual((out/'a.py').stat().st_mode & 0o222,0)

    def test_stage_changed_hash(self):
        inputs=self.root/'inputs';inputs.mkdir();(inputs/'000000').write_bytes(b'changed')
        with self.assertRaises(h.s.Blocked):h.stage(self.config,h.plan(self.config,501,20),self.root/'stage',inputs)

    def test_stage_symlink(self):
        inputs=self.root/'inputs';inputs.mkdir(); target=self.root/'x';target.write_bytes(b'x=1\n');(inputs/'000000').symlink_to(target)
        with self.assertRaises(h.s.Blocked):h.stage(self.config,h.plan(self.config,501,20),self.root/'stage',inputs)

    def test_lease_collision_and_wrong_owner(self):
        h.acquire_lease(self.store,self.token,self.intent)
        with self.assertRaises(FileExistsError):h.acquire_lease(self.store,self.token,self.intent)
        with self.assertRaises(h.s.Blocked):h.check_lease(self.store,'c'*64)

    def test_owner_write_failure_retains_lease(self):
        with patch.object(h.u,'exclusive_json',side_effect=OSError('disk')):
            with self.assertRaises(OSError):h.acquire_lease(self.store,self.token,self.intent)
        self.assertTrue((self.store/'.update-lease').is_dir())
        with self.assertRaises(FileExistsError):h.acquire_lease(self.store,self.token,self.intent)

    def test_release_requires_cleanup_and_durable_result(self):
        h.acquire_lease(self.store,self.token,self.intent);r=self.root/'result.json';r.write_text('{}')
        with self.assertRaises(h.s.Blocked):h.release_lease(self.store,self.token,{'removed':False,'uncertain':True},r)
        with self.assertRaises(h.s.Blocked):h.release_lease(self.store,self.token,{'removed':True,'uncertain':False},r)
        self.assertTrue((self.store/'.update-lease').exists())
        r.write_text(json.dumps({'owner_token':self.token,'terminal':True}));h.release_lease(self.store,self.token,{'removed':True,'uncertain':False},r)
        self.assertFalse((self.store/'.update-lease').exists())

    def test_terminal_failclosed(self):
        state={'Status':'exited','Running':False,'OOMKilled':False,'Dead':False,'Error':'','ExitCode':0}
        self.assertEqual(h.terminal(state),0)
        for k,v in [('Running',True),('OOMKilled',True),('Dead',True),('Error','bad'),('ExitCode',False),('Status','created')]:
            with self.subTest(k=k), self.assertRaises(h.s.Blocked):h.terminal(dict(state,**{k:v}))
        with self.assertRaises(h.s.Blocked):h.terminal({})

    def test_publish_never_on_unknown_terminal(self):
        h.acquire_lease(self.store,self.token,self.intent)
        with patch.object(h.u,'validate_download') as validate:
            with self.assertRaises(h.s.Blocked):h.publish(self.store,self.token,self.root/'cache',{}, {},False)
            validate.assert_not_called()

    def test_actual_mount_rejected_before_delegate(self):
        with patch.object(h.s,'verify_container') as verify:
            with self.assertRaises(h.s.Blocked):h.verify_host_inspect({'Mounts':[]},{'volumes':[{'source':'/safe/file','target':'/src','read_only':True}]},'id')
            verify.assert_not_called()

    def test_inspect_does_not_canonicalize_host_namespace(self):
        obj={'Mounts':[{'Type':'bind','Source':'/host/path','Destination':'/src','RW':False}]};service={'volumes':[{'source':'/host/path','target':'/src','read_only':True}]}
        with patch.object(h.s,'verify_container') as verify:
            h.verify_host_inspect(obj,service,'id');self.assertEqual(verify.call_args.args[0]['Mounts'][0]['Source'],'/host/path');self.assertIs(verify.call_args.kwargs['path_identity'],h.host_path)
        self.assertEqual(obj['Mounts'][0]['Source'],'/host/path')

if __name__ == '__main__': unittest.main()

class PublicationTests(unittest.TestCase):
    setUp=HelperTests.setUp
    tearDown=HelperTests.tearDown
    def make_download(self):
        import datetime as dt
        h.acquire_lease(self.store,self.token,self.intent)
        cache=self.store/('download-'+self.token)/'cache';(cache/'db').mkdir(parents=True)
        (cache/'db/trivy.db').write_bytes(b'FAKE DATABASE FOR CONTRACT TEST ONLY')
        now=dt.datetime.now(dt.timezone.utc)
        (cache/'db/metadata.json').write_text(json.dumps({'Version':2,'UpdatedAt':(now-dt.timedelta(hours=1)).isoformat(),'NextUpdate':(now+dt.timedelta(hours=1)).isoformat()}))
        m={'engines':{'trivy':{'image':'test.invalid/trivy@sha256:'+'a'*64}},'db':{'repository':'test.invalid/db@sha256:'+'b'*64,'schema':2,'max_age_hours':24}}
        state={'Status':'exited','Running':False,'OOMKilled':False,'Dead':False,'Error':'','ExitCode':0}
        return cache,m,state

    def test_sealed_publication(self):
        cache,m,state=self.make_download();result=h.publish(self.store,self.token,cache,m,state,True)
        self.assertEqual(result['status'],'SNAPSHOT_CREATED');snap=self.store/result['snapshot']
        self.assertEqual(snap.stat().st_mode&0o222,0);h.s.validate_snapshot(self.store,result['snapshot'],m)
        self.assertTrue((self.store/'.update-lease').exists())

    def test_stale_never_published(self):
        cache,m,state=self.make_download();meta=cache/'db/metadata.json';obj=json.loads(meta.read_text());obj['NextUpdate']=obj['UpdatedAt'];meta.write_text(json.dumps(obj))
        with self.assertRaises(h.s.Blocked):h.publish(self.store,self.token,cache,m,state,True)
        self.assertFalse(any(p.name.isalnum() and len(p.name)==64 for p in self.store.iterdir()))

    def test_metadata_failure_retains_lease(self):
        cache,m,state=self.make_download()
        with patch.object(h.u,'exclusive_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):h.publish(self.store,self.token,cache,m,state,True)
        self.assertTrue((self.store/'.update-lease').exists())

class StoreReserveTests(unittest.TestCase):
    def test_lease_checks_store_filesystem_before_acquisition(self):
        import shutil
        from types import SimpleNamespace
        with patch.object(h,'budget'), patch.object(h.s,'load_manifest',return_value={}), patch.object(shutil,'disk_usage',return_value=SimpleNamespace(free=10*1024**3-1)), patch.object(h,'acquire_lease') as acquire:
            with self.assertRaisesRegex(h.s.Blocked,'store reserve'):
                h.cli(['lease','--host-work','/task/run','--host-store','/factory-store','--token','a'*64])
            acquire.assert_not_called()

    def test_unknown_store_space_never_acquires(self):
        import shutil
        with patch.object(h,'budget'), patch.object(h.s,'load_manifest',return_value={}), patch.object(shutil,'disk_usage',side_effect=OSError('unavailable')), patch.object(h,'acquire_lease') as acquire:
            with self.assertRaises(OSError):h.cli(['lease','--host-work','/task/run','--host-store','/factory-store','--token','a'*64])
            acquire.assert_not_called()
