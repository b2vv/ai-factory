import os,json,tempfile,unittest
from pathlib import Path
import kit
ROOT=Path(__file__).resolve().parents[2]
class LayoutUpgradeTests(unittest.TestCase):
 @unittest.skipUnless(os.environ.get('AI_FACTORY_PREVIOUS_RELEASE'),'explicit previous release required; upgrade NOT_TESTED')
 def test_previous_full_layout_upgrade_noop_conflict_and_rollback(self):
  previous=Path(os.environ['AI_FACTORY_PREVIOUS_RELEASE']).resolve();oldm=json.loads((previous/'release-manifest.json').read_text());newm=json.loads((ROOT/'release-manifest.json').read_text());old_components=list(oldm['components']);new_components=list(newm['components'])
  with tempfile.TemporaryDirectory() as d:
   target=Path(d).resolve()/'fake-home'/'toolkit';p=kit.plan(previous,target,old_components);kit.apply(previous,target,old_components,p['plan_id']);old_state=kit.current(target);foreign=target/'owner-note.txt';foreign.write_text('preserve')
   old_skill=target/'collection/agents/skills/arch/tdd/SKILL.md';original=old_skill.read_bytes();old_skill.write_bytes(b'foreign edit')
   with self.assertRaises(ValueError):kit.plan(ROOT,target,new_components)
   self.assertEqual(b'foreign edit',old_skill.read_bytes());old_skill.write_bytes(original)
   upgrade=kit.plan(ROOT,target,new_components);self.assertTrue(any(e['path'].startswith('collection/') and e['after'] is None for e in upgrade['changes']));tx=kit.apply(ROOT,target,new_components,upgrade['plan_id']);self.assertEqual('NOOP',kit.plan(ROOT,target,new_components)['status']);self.assertFalse(old_skill.exists());new_skill=target/'skills/arch/tdd/SKILL.md';data=new_skill.read_bytes();new_skill.write_bytes(b'foreign after upgrade')
   with self.assertRaises(ValueError):kit.rollback_plan(target,tx['transaction'])
   new_skill.write_bytes(data);rp=kit.rollback_plan(target,tx['transaction']);kit.rollback(target,tx['transaction'],rp['plan_id']);self.assertEqual(old_state,kit.current(target));self.assertEqual('NOOP',kit.plan(previous,target,old_components)['status']);self.assertEqual(original,old_skill.read_bytes());self.assertFalse(new_skill.exists());self.assertEqual('preserve',foreign.read_text())
