import json,tempfile,unittest
from pathlib import Path
import kit,verify_collection

ROOT=Path(__file__).resolve().parent.parent
class FullCollectionTests(unittest.TestCase):
    def test_inventory_and_checksums(self):
        self.assertEqual([],verify_collection.verify(ROOT)['issues'])
        m,files,_=kit.payload(ROOT,['collection'])
        for r in json.loads((ROOT/'collection/manifest.json').read_text())['files']:
            self.assertEqual(r['sha256'],kit.digest(files[r['destination']]))
    def test_restricted_and_external_not_present(self):
        m=json.loads((ROOT/'collection/manifest.json').read_text())
        self.assertEqual({'shared'},{b['group'] for b in m['bundles']})
        self.assertNotIn('host_dependencies',m)
        self.assertFalse(any((ROOT/x).exists() and any((ROOT/x).rglob('SKILL.md')) for x in ['collection/external','collection/project-skills']))
        for b in m['bundles']:
            self.assertEqual(b['status']=='INCLUDED',(ROOT/b['destination']).is_file())
    def test_full_tree_install_repeat_edit_guard_restore(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d).resolve()/'fake-home'/'toolkit';p=kit.plan(ROOT,dest,['collection'])
            self.assertFalse(dest.exists())
            tx=kit.apply(ROOT,dest,['collection'],p['plan_id'])
            self.assertEqual('NOOP',kit.plan(ROOT,dest,['collection'])['status'])
            self.assertEqual([],verify_collection.verify(dest)['issues'])
            foreign=dest/'owner-note.txt';foreign.write_text('preserve')
            target=dest/'collection/agents/skills/arch/tdd/SKILL.md';original=target.read_bytes();target.write_bytes(b'owner edit')
            with self.assertRaises(ValueError):kit.rollback_plan(dest,tx['transaction'])
            target.write_bytes(original)
            rp=kit.rollback_plan(dest,tx['transaction']);kit.rollback(dest,tx['transaction'],rp['plan_id'])
            self.assertEqual('preserve',foreign.read_text());self.assertFalse(target.exists())
    def test_nested_collision_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d).resolve()/'fake-home'/'toolkit';p=dest/'collection/agents/skills/arch/tdd/SKILL.md';p.parent.mkdir(parents=True);p.write_text('owner')
            with self.assertRaises(ValueError):kit.plan(ROOT,dest,['collection'])
            self.assertEqual('owner',p.read_text());self.assertFalse((dest/kit.STATE).exists())
    def test_variants_never_flattened(self):
        m=json.loads((ROOT/'collection/manifest.json').read_text());d=[b['destination'] for b in m['bundles']]
        self.assertEqual(len(d),len(set(d)))
        variants=[b for b in m['bundles'] if b['name']=='skill-creator' and b['group']=='shared']
        self.assertEqual(2,len(variants));self.assertNotEqual(variants[0]['destination'],variants[1]['destination'])
