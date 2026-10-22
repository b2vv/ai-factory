import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

RUNTIME=Path(os.environ.get('AF_TEST_BASE',str(Path(__file__).resolve().parents[2])))/'runtime/scanners'
spec=importlib.util.spec_from_file_location('classification_helper',RUNTIME/'container_helper.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
TOKEN='a'*64
UNSET=object()

class ClassificationIntegrationTests(unittest.TestCase):
    def execute(self,terminal_override='unchanged',report_override='unchanged',tamper=UNSET,crash=False,finding=False,trivy_override=UNSET):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'reports').mkdir();(root/'source').mkdir();(root/'source/package.json').write_text('{"devDependencies":{"a":"1"}}')
            state={'Status':'exited','Running':False,'OOMKilled':False,'Dead':False,'Error':'','ExitCode':0}
            sem={'results':[{'check_id':'fixture'}] if finding else [],'errors':[],'paths':{'scanned':['a.py']}}
            tri={'SchemaVersion':2,'Results':[{'Target':'yarn.lock','Type':'yarn','Packages':[{'Name':'a','Version':'1'}],'Vulnerabilities':[]}]}
            data={'plan.json':{'config':{'files':{'a.py':'a'*64,'yarn.lock':'b'*64},'db_snapshot':'c'*64},'mapping':{'inputs':[]}},'snapshot-before.json':{},'verified.json':{'semgrep':'sem','trivy':'tri'},'semgrep-terminal.json':[{'Id':'sem','State':dict(state)}],'trivy-terminal.json':[{'Id':'tri','State':dict(state)}]}
            if terminal_override!='unchanged':data['semgrep-terminal.json']=terminal_override
            for n,v in data.items():(root/n).write_text(json.dumps(v))
            (root/'reports/semgrep.json').write_text(json.dumps(sem if report_override=='unchanged' else report_override));(root/'reports/trivy.json').write_text(json.dumps(tri if trivy_override is UNSET else trivy_override))
            real_path=Path
            def mapped(value,*args):return root if str(value)=='/work' else real_path(value,*args)
            with patch.object(h,'Path',side_effect=mapped),patch.object(h,'budget'),patch.object(h.s,'load_manifest',return_value={}),patch.object(h.s,'validate_snapshot',return_value=(None,{})):
                if crash:code=1
                else:code=h.cli(['finalize','--host-work','/host/run','--token',TOKEN])
                artifact=root/'result-pending-cleanup.json'
                result=json.loads(artifact.read_text()) if artifact.exists() else None
                if tamper is not UNSET:artifact.write_text(json.dumps(tamper))
                try:verify_code=h.cli(['verify-result','--host-work','/host/run','--token',TOKEN])
                except (h.s.Blocked,OSError,ValueError,KeyError,TypeError,AttributeError,SystemExit):verify_code=3
            script=(RUNTIME/'scan.sh').read_text()
            start=script.index('    hrun "$@";')
            end=script.index('\nelse\n',start)
            actual_flow=script[start:end]
            harness='''
. "$1"
WORK=$2; TOKEN=$3; ENGINE_RC=$4; VERIFY_RC=$5
finish() { printf cleanup > "$WORK/cleanup-called"; exit "$1"; }
hrun() { if [ "$1" = verify-result ]; then [ "$VERIFY_RC" = 0 ] || finish 2; HRC=0; else HRC=$ENGINE_RC; fi; }
set -- finalize
'''+actual_flow
            run=subprocess.run(['sh','-c',harness,'sh',str(RUNTIME/'container_control.sh'),str(root),TOKEN,str(code),str(verify_code)],capture_output=True,timeout=5)
            self.assertTrue((root/'cleanup-called').exists(),'coordinator skipped cleanup')
            return code,run.returncode,result

    def test_terminal_shapes_finalizer_and_coordinator(self):
        bad=[None,[],{},'x',1,True,[None],[[]],['x'],[1],[{}],[{'Id':'sem','State':None}],[{'Id':'sem','State':[]}],[{'Id':'sem','State':7}],[{'Id':'sem','State':{'Status':[]}}]]
        for value in bad:
            with self.subTest(value=value):
                code,coordinator,result=self.execute(terminal_override=value)
                self.assertEqual((code,coordinator),(2,2));self.assertEqual(result['engines']['semgrep']['status'],'ERROR')

    def test_report_shapes_finalizer_and_coordinator(self):
        clean={'results':[],'errors':[],'paths':{'scanned':['a.py']}}
        bad=[None,[],{},'x',1,True]
        for field,values in [('paths',[None,[],1,'x',{'scanned':None},{'scanned':[None]},{'scanned':[{}]},{'scanned':True}]),('results',[None,{},'x',[None],[[]],[{}],[{'check_id':[]}]]),('errors',[None,{},'x'])]:
            for value in values:bad.append(dict(clean,**{field:value}))
        for value in bad:
            with self.subTest(value=value):
                code,coordinator,result=self.execute(report_override=value)
                self.assertEqual((code,coordinator),(2,2));self.assertEqual(result['engines']['semgrep']['status'],'ERROR')

    def test_unexpected_helper_exit1_without_artifact_is_error(self):
        code,coordinator,result=self.execute(crash=True)
        self.assertEqual(code,1);self.assertIsNone(result);self.assertEqual(coordinator,2)

    def test_valid_clean_and_findings_have_verified_artifact(self):
        self.assertEqual(self.execute()[:2],(0,0));self.assertEqual(self.execute(finding=True)[:2],(1,1))

    def test_bad_classification_artifact_never_authorizes_findings(self):
        for value in [None,[],1,'x',{}, {'owner_token':TOKEN,'engines':None}, {'owner_token':TOKEN,'engines':{'semgrep':None,'trivy':[]}}]:
            with self.subTest(value=value):
                self.assertEqual(self.execute(finding=True,tamper=value)[1],2)

    def test_trivy_nested_shapes_finalizer_and_coordinator(self):
        for value in [None, [], 1, 'x', {'SchemaVersion':2,'Results':None}, {'SchemaVersion':2,'Results':[None]}, {'SchemaVersion':2,'Results':[{'Target':'yarn.lock','Type':'yarn','Packages':[None]}]}, {'SchemaVersion':2,'Results':[{'Target':'yarn.lock','Type':'yarn','Packages':[{'Name':'a','Version':'1'}],'Vulnerabilities':[None]}]}]:
            with self.subTest(value=value):
                code,coordinator,result=self.execute(trivy_override=value)
                self.assertEqual((code,coordinator),(2,2));self.assertEqual(result['engines']['trivy']['status'],'ERROR')
