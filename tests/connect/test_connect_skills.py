import os,subprocess,tempfile,unittest,shutil
from pathlib import Path
ROOT=Path(os.environ.get('AI_FACTORY_TEST_ROOT',Path(__file__).resolve().parents[2]))
class SkillLinks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.kit=self.root/'kit';self.target=self.root/'global';(self.kit/'tools').mkdir(parents=True);self.target.mkdir();self.skill=self.kit/'skills/example';self.skill.mkdir(parents=True);(self.skill/'SKILL.md').write_text('---\nname: example\ndescription: Synthetic fixture\n---\n');shutil.copyfile(ROOT/'tools/connect-skills.sh',self.kit/'tools/connect-skills.sh')
 def run_linker(self):return subprocess.run(['sh',str(self.kit/'tools/connect-skills.sh'),'--dry-run',str(self.target)],capture_output=True,text=True,timeout=5)
 def test_correct_live_link_is_already(self):
  link=self.target/'example';link.symlink_to(self.skill,target_is_directory=True);r=self.run_linker();self.assertEqual(r.returncode,0,r.stderr);self.assertIn('ALREADY  example',r.stdout);self.assertEqual(link.readlink(),self.skill)
 def test_relative_correct_link_is_already(self):
  link=self.target/'example';link.symlink_to('../kit/skills/example',target_is_directory=True);r=self.run_linker();self.assertIn('ALREADY  example',r.stdout);self.assertEqual(str(link.readlink()),'../kit/skills/example')
 def test_dangling_link_is_conflict_not_already(self):
  link=self.target/'example';old=self.root/'missing';link.symlink_to(old,target_is_directory=True);r=self.run_linker();self.assertIn('CONFLICT example',r.stdout);self.assertNotIn('ALREADY  example',r.stdout);self.assertEqual(link.readlink(),old);self.assertFalse(old.exists())
 def test_different_target_with_identical_skill_is_conflict(self):
  other=self.root/'owner-skill';shutil.copytree(self.skill,other);link=self.target/'example';link.symlink_to(other,target_is_directory=True);r=self.run_linker();self.assertIn('CONFLICT example',r.stdout);self.assertNotIn('ALREADY  example',r.stdout);self.assertEqual(link.readlink(),other)
 def test_empty_skill_target_is_conflict(self):
  other=self.root/'empty';other.mkdir();link=self.target/'example';link.symlink_to(other,target_is_directory=True);r=self.run_linker();self.assertIn('CONFLICT example',r.stdout);self.assertNotIn('ALREADY  example',r.stdout);self.assertEqual(link.readlink(),other)
 def test_new_link_remains_additive(self):
  r=self.run_linker();self.assertIn('CONNECT  example',r.stdout);self.assertFalse((self.target/'example').exists())
