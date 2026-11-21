import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

BASE=Path(os.environ.get('AF_TEST_BASE',str(Path(__file__).resolve().parents[2])))
RUNTIME=BASE/'runtime/scanners'
spec=importlib.util.spec_from_file_location('migration_helper',RUNTIME/'container_helper.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def service():
    return {'image':'test.invalid/engine@sha256:'+'a'*64,'user':str(os.getuid())+':'+str(os.getgid()),'entrypoint':['trivy'],'command':['fs'],
            'environment':{'HOME':'/tmp'},'volumes':[{'source':'/host-namespace/not-mounted-in-helper','target':'/src','read_only':True}]}


def inspect(service):
    return {'Id':'cid','Image':'sha256:local','State':{'Status':'created','Running':False},
            'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],
                          'Tmpfs':{'/tmp':'rw,noexec,nosuid,size=256m'},'NanoCpus':2000000000,'Memory':2*1024**3,'MemorySwap':2*1024**3,'PidsLimit':128},
            'Config':{'Image':service['image'],'User':service['user'],'Entrypoint':service['entrypoint'],'Cmd':service['command'],'WorkingDir':'/src','Env':['HOME=/tmp'],'Labels':{'ai-factory.run':'a'*64}},
            'Mounts':[{'Type':'bind','Source':x['source'],'Destination':x['target'],'RW':not x['read_only']} for x in service['volumes']]}


class ActualVerifierTests(unittest.TestCase):
    def test_valid_scan_inspect_real_delegate(self):
        s=service();h.verify_host_inspect(inspect(s),s,'sha256:local')

    def test_bad_scan_mounts_rejected_real_delegate(self):
        s=service()
        mutations=[lambda o:o['Mounts'][0].update(Source='/other'),lambda o:o['Mounts'][0].update(Type='volume'),lambda o:o['Mounts'][0].update(RW=True),lambda o:o['Mounts'].append(copy.deepcopy(o['Mounts'][0]))]
        for mutate in mutations:
            o=inspect(s);mutate(o)
            with self.assertRaises(h.s.Blocked):h.verify_host_inspect(o,s,'sha256:local')

    def test_legacy_local_path_check_not_weakened(self):
        s=service()
        with self.assertRaises(h.s.Blocked):h.s.verify_container(inspect(s),s,'sha256:local')

    def test_valid_updater_phase_real_delegate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();s=service();s['command']=['image','--download-db-only'];s['volumes'][0].update(source='/host-namespace/cache',target='/cache',read_only=False)
            o=inspect(s);o['HostConfig']['NetworkMode']='bridge';o['HostConfig']['Tmpfs']['/tmp']='rw,noexec,nosuid,size=1g';o['Config']['Env'].append('TRIVY_DISABLE_TELEMETRY=true')
            o['HostConfig']['LogConfig']={'Type':'local','Config':{'max-size':'1m','max-file':'1','compress':'false'}}
            for n,v in {'updater.json':{'image':s['image'],'command':s['command'],'cache':'/host-namespace/cache'},'updater-inspect.json':[o],'trivy-image.json':[{'Id':'sha256:local','Os':'linux','Architecture':'amd64','Size':1,'RepoDigests':[s['image']]}]}.items():(root/n).write_text(json.dumps(v))
            actual_path=Path
            def mapped(value,*args):return root if str(value)=='/work' else actual_path(value,*args)
            with patch.object(h,'Path',side_effect=mapped),patch.object(h,'budget'),patch.object(h.s,'load_manifest',return_value={}):
                self.assertEqual(h.cli(['update-verify','--host-work','/host/run','--token','a'*64]),0)
            self.assertEqual(json.loads((root/'updater-verified.json').read_text())['cid'],'cid')


class FinalizeTests(unittest.TestCase):
    def probe(self,kind):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'reports').mkdir();(root/'source').mkdir();(root/'source/package.json').write_text('{"devDependencies":{"a":"1"}}')
            state={'Status':'exited','Running':False,'OOMKilled':False,'Dead':False,'Error':'','ExitCode':0}
            sem={'results':[],'errors':[],'paths':{'scanned':['a.py']}}
            tri={'SchemaVersion':2,'Results':[{'Target':'yarn.lock','Type':'yarn','Packages':[{'Name':'a','Version':'1'}],'Vulnerabilities':[]}]}
            data={'plan.json':{'config':{'files':{'a.py':'a'*64,'yarn.lock':'b'*64},'db_snapshot':'c'*64},'mapping':{'inputs':[]}},'snapshot-before.json':{},'verified.json':{'semgrep':'sem','trivy':'tri'},'semgrep-terminal.json':[{'Id':'sem','State':dict(state)}],'trivy-terminal.json':[{'Id':'tri','State':dict(state)}]}
            if kind=='exit1':data['trivy-terminal.json'][0]['State']['ExitCode']=1
            if kind=='oom':data['trivy-terminal.json'][0]['State'].update(ExitCode=137,OOMKilled=True)
            if kind=='finding':sem['results']=[{'check_id':'fixture'}]
            for n,v in data.items():(root/n).write_text(json.dumps(v))
            (root/'reports/semgrep.json').write_text(json.dumps(sem))
            if kind!='exit1':(root/'reports/trivy.json').write_text('invalid-json' if kind=='invalid' else json.dumps(tri))
            actual_path=Path
            def mapped(value,*args):return root if str(value)=='/work' else actual_path(value,*args)
            with patch.object(h,'Path',side_effect=mapped),patch.object(h,'budget'),patch.object(h.s,'load_manifest',return_value={}),patch.object(h.s,'validate_snapshot',return_value=(None,{})):
                code=h.cli(['finalize','--host-work','/host/run'])
            return code,json.loads((root/'result-pending-cleanup.json').read_text())

    def test_exit1_missing_report_is_error(self):
        code,r=self.probe('exit1');self.assertEqual(code,2);self.assertEqual(r['engines']['trivy']['exit_code'],1)
    def test_invalid_json_is_error(self):self.assertEqual(self.probe('invalid')[0],2)
    def test_oom_is_error(self):self.assertEqual(self.probe('oom')[0],2)
    def test_clean_and_findings_unchanged(self):
        self.assertEqual(self.probe('clean')[0],0);self.assertEqual(self.probe('finding')[0],1)


class CleanupScopeTests(unittest.TestCase):
    def test_resistant_monitor_wait_inside_cleanup_budget(self):
        self.probe_worker("CONTROL_DISK_TIMER")

    def test_resistant_operation_timer_wait_inside_cleanup_budget(self):
        self.probe_worker("CONTROL_TIMER")

    def probe_worker(self, worker_field):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=root/'control.sh';lib.write_text((RUNTIME/'container_control.sh').read_text().replace('control_start_timer 15','control_start_timer 1'))
            script='. "$1"; cleanup_exact_intents() { :; }; control_init "$2"; sh -c \'trap "" TERM; echo ready > "$1"; sleep 4\' sh "$2/worker-ready" & CONTROL_DISK_TIMER=$!; while [ ! -f "$2/worker-ready" ]; do sleep .01; done; echo ready > "$2/ready"; control_shutdown; echo UNSAFE > "$2/continued"'
            script=script.replace('CONTROL_DISK_TIMER=$!',worker_field+'=$!')
            p=subprocess.Popen(['sh','-c',script,'sh',str(lib),tmp],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try:
                deadline=time.monotonic()+5
                while not (root/'ready').exists() and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue((root/'ready').exists());start=time.monotonic()
                p.wait(timeout=8);elapsed=time.monotonic()-start
                self.assertLess(elapsed,3,'cleanup deadline excluded monitor wait')
                self.assertEqual(p.returncode,2);self.assertFalse((root/'continued').exists())
                self.assertEqual((root/'cleanup-state').read_text(),'UNKNOWN\n')
            finally:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.communicate(timeout=2)

class NamespaceSiblingTests(unittest.TestCase):
    def test_updater_all_mount_rejections_keep_real_verifier(self):
        s=service();s['command']=['image','--download-db-only'];s['volumes'][0].update(source='/host/cache',target='/cache',read_only=False)
        valid=inspect(s);valid['HostConfig']['NetworkMode']='bridge';valid['HostConfig']['Tmpfs']['/tmp']='rw,noexec,nosuid,size=1g';valid['Config']['Env'].append('TRIVY_DISABLE_TELEMETRY=true')
        h.u.verify_updater(valid,'sha256:local',s['image'],'/host/cache',s['command'],path_identity=h.host_path)
        for field,value in [('Source','/wrong'),('Type','volume'),('RW',False),('Destination','/other')]:
            obj=copy.deepcopy(valid);obj['Mounts'][0][field]=value
            with self.subTest(field=field),self.assertRaises(h.s.Blocked):h.u.verify_updater(obj,'sha256:local',s['image'],'/host/cache',s['command'],path_identity=h.host_path)
        obj=copy.deepcopy(valid);obj['Mounts'].append(copy.deepcopy(obj['Mounts'][0]))
        with self.assertRaises(h.s.Blocked):h.u.verify_updater(obj,'sha256:local',s['image'],'/host/cache',s['command'],path_identity=h.host_path)
        with self.assertRaises(h.s.Blocked):h.u.verify_updater(valid,'sha256:local',s['image'],Path('/host/cache'),s['command'])

    def test_missing_container_bound_input_still_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'input').mkdir();config={'schema_version':1,'root':'/host/root','sanitized_inputs_reviewed':True,'files':{'a.py':'a'*64}}
            with self.assertRaises(h.s.Blocked):h.stage(config,h.plan(config,501,20),root/'stage',root/'input')

    def test_preflight_stale_db_stays_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            config={'files':{},'db_snapshot':'c'*64}
            (root/'plan.json').write_text(json.dumps({'config':config,'mapping':{'inputs':[]}}))
            def mapped(value,*args):return root if str(value)=='/work' else Path(value,*args)
            with patch.object(h,'Path',side_effect=mapped),patch.object(h,'budget'),patch.object(h.s,'load_manifest',return_value={}),patch.object(h.s,'validate_snapshot',side_effect=h.s.Blocked('DB stale')):
                with self.assertRaisesRegex(h.s.Blocked,'DB stale'):h.cli(['finalize','--host-work','/host/run'])
