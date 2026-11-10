import json,os,re,unittest,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class LayoutIntegrityTests(unittest.TestCase):
 def test_every_old_file_accounted_and_no_second_discoverable_tree(self):
  m=json.loads((ROOT/'provenance/layout-migration.json').read_text());self.assertEqual(350,len(m['files']));self.assertEqual(350,len({r['old_path'] for r in m['files']}))
  for r in m['files']:
   p=ROOT/r['new_path'];self.assertTrue(p.is_file())
   if r['new_sha256']:self.assertEqual(r['new_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
  skills=list(ROOT.rglob('SKILL.md'))
  sources=json.loads((ROOT/'provenance/source-map.json').read_text())['files']
  additions=json.loads((ROOT/'provenance/authorized-additions.json').read_text())['files']
  expected={row['destination'] for row in sources+additions if row['destination'].endswith('/SKILL.md')}
  self.assertEqual(expected,{str(p.relative_to(ROOT)) for p in skills})
  for name in ['constraint-driven-development','inspector-review','step-back-review']:
   self.assertTrue((ROOT/'skills'/name/'SKILL.md').is_file())
  self.assertTrue(all(p.is_relative_to(ROOT/'skills') for p in skills))
  registry=json.loads((ROOT/'provenance/skill-registry.json').read_text());ids=[b['id'] for b in registry['skills']];self.assertEqual(len(ids),len(set(ids)))
 def test_runtime_variants_and_notices_preserved_byte_for_byte(self):
  m=json.loads((ROOT/'provenance/layout-migration.json').read_text());rows={r['old_path']:r for r in m['files']}
  helpers=['onboarding/preflight.py','review/review_package.py','collection/agents/ai-factory/review/review_package.py','collection/agents/ai-factory/session-size/session_guard.py']
  for n,r in rows.items():
   if n in helpers or any(s in Path(n).name.lower() for s in ['license','-ofl','notice']):self.assertEqual(r['old_sha256'],r['new_sha256'],n)
 def test_native_successor_binds_original_and_current_portable_guard(self):
  history=json.loads((ROOT/'provenance/layout-migration.json').read_text())
  row=next(r for r in history['files'] if r['old_path']=='session-size/session_guard.py')
  proof=json.loads((ROOT/'provenance/native-handoff.json').read_text())
  self.assertEqual('16bfb6b19123548647dc713890c448e97ce39e5e27c6ebfe64d91b6c7c0c0e47',row['old_sha256'])
  self.assertEqual(row['old_sha256'],proof['portable_guard_before_sha256'])
  self.assertEqual(row['new_sha256'],proof['portable_guard_after_sha256'])
  self.assertTrue(row['transformations']);self.assertNotEqual(row['old_sha256'],row['new_sha256'])
  for path,digest in proof['files'].items():
   self.assertEqual(digest,hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
 @unittest.skipUnless(os.environ.get('AI_FACTORY_PREVIOUS_RELEASE'),'explicit previous release required; original-body comparison NOT_TESTED')
 def test_all_original_skill_bodies_only_link_targets_change(self):
  previous=Path(os.environ['AI_FACTORY_PREVIOUS_RELEASE']);m=json.loads((ROOT/'provenance/source-map.json').read_text());count=0
  normalize=lambda text:re.sub(r'\]\([^)]+\)','](LINK)',text)
  for b in m['bundles']:
   if b['status']=='INCLUDED':
    body=(ROOT/b['destination']).read_text()
    additions=json.loads((ROOT/'provenance/authorized-additions.json').read_text())
    for a in additions['adaptations']:
     if a['destination']==b['destination']:
      self.assertTrue(body.endswith(a['append']));body=body[:-len(a['append'])];self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),a['before_sha256'])
    self.assertEqual(normalize((previous/b['previous_release_destination']).read_text()),normalize(body),b['name']);count+=1
  self.assertEqual(73,count)
