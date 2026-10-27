"""Fresh-machine component closure and lifecycle, in an isolated fake home."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
import kit
ROOT=Path(__file__).resolve().parents[2]
class SessionComponent(unittest.TestCase):
 def test_clean_install_includes_cleanup_and_runs_lifecycle(self):
  manifest=json.loads((ROOT/'release-manifest.json').read_text())
  entries=[e for e in manifest['files'] if e['component']=='session-guard-docker']
  self.assertIn('runtime/session-size-docker/cleanup.sh',{e['path'] for e in entries})
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp).resolve();package=base/'package';package.mkdir();target=base/'fake-home/toolkit'
   for e in entries:
    p=package/e['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/e['path']).read_bytes())
   m={'schema_version':2,'version':'fixture','components':{'core':{},'session-guard-docker':{}},'files':entries}
   (package/'release-manifest.json').write_bytes(kit.encode(m))
   checks={e['path']:kit.digest((package/e['path']).read_bytes()) for e in entries};checks['release-manifest.json']=kit.digest((package/'release-manifest.json').read_bytes())
   (package/'checksums.sha256').write_text(''.join(checks[n]+'  '+n+'\n' for n in sorted(checks)))
   plan=kit.plan(package,target,['session-guard-docker']);self.assertFalse(target.exists())
   kit.apply(package,target,['session-guard-docker'],plan['plan_id']);self.assertEqual(kit.plan(package,target,['session-guard-docker'])['status'],'NOOP')
   spec=importlib.util.spec_from_file_location('installed_lifecycle',ROOT/'tests/session-size-docker/test_lifecycle_state.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.CODE=target/'runtime/session-size-docker'
   suite=unittest.TestSuite(mod.StatefulLifecycle(n) for n in ['test_success_state_and_metadata','test_delayed_create_is_reconciled','test_parallel_invocations_do_not_collide'])
   result=unittest.TestResult();suite.run(result);self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
if __name__=='__main__':unittest.main()
