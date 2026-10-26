"""Negative structural proofs; semantic translation review remains independent."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / 'tools' / 'verify_translation.py'
# tests/collection -> repository root is parents[2].
spec = importlib.util.spec_from_file_location('factory_verify_translation', MODULE)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

import os
HISTORY_ROOT = Path(os.environ['AI_FACTORY_HISTORY_BASELINE'])
v.configure_history(HISTORY_ROOT)
history_literal = v.history_literal


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        raw = b'unchanged\n'; (self.root/'a').write_bytes(raw)
        m = json.dumps({'files':[{'path':'a','sha256':v.digest(raw)}]}).encode()
        (self.root/'release-manifest.json').write_bytes(m)
        self.manifest_hash = v.digest(m)
        (self.root/'checksums.sha256').write_text(v.digest(raw)+'  a\n'+self.manifest_hash+'  release-manifest.json\n')
        self.patch = patch.object(v, 'BASE_MANIFEST', self.manifest_hash)
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_complete_baseline_is_read(self):
        self.assertEqual(v.load_baseline(self.root)['a'], b'unchanged\n')

    def test_changed_payload_rejected_even_when_checksums_rewritten(self):
        (self.root/'a').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'payload mismatch'):
            v.load_baseline(self.root)

    def test_manifest_identity_not_mutable_provenance(self):
        (self.root/'release-manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            v.load_baseline(self.root)

    def test_extra_baseline_file_rejected(self):
        (self.root/'extra').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            v.load_baseline(self.root)

    def test_missing_baseline_is_blocked(self):
        result = v.verify_historical(self.root, self.root/'absent')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertNotEqual(result['status'], 'PASS')

    def test_symlink_component_and_dangling_symlink_rejected(self):
        (self.root/'alias').symlink_to(self.root/'a')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            v.regular(self.root, 'alias')
        (self.root/'dangling').symlink_to(self.root/'missing')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            v.inventory(self.root)

    def test_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            v.regular(self.root, '../outside')

    def test_checksum_inventory_is_exact(self):
        with (self.root/'checksums.sha256').open('a') as f:
            f.write('0'*64+'  fabricated\n')
        with self.assertRaisesRegex(ValueError, 'closure mismatch'):
            v.load_baseline(self.root)


class DescriptionTests(unittest.TestCase):
    def test_description_only_allows_english_text(self):
        old = history_literal('tests', 8, '9bdeca7bed58dc2c6cc68fe9a9a7239f9f71cea0ddae98bd77b0ae1823c63669')
        new = old.replace(history_literal('tests', 63, '2302145027357a89d84e69ce23892afc6a6e336a18e781e5e99662f23387ee18'), 'Description')
        self.assertEqual(v.description_parts(old), v.description_parts(new))
        self.assertNotEqual(v.description_parts(old), v.description_parts(new.replace('body','changed')))
        self.assertNotEqual(v.description_parts(old), v.description_parts(new.replace('MIT','Other')))

    def test_exact_alias_preserved(self):
        old = history_literal('tests', 9, 'd0218e39008db1ceff1b89150233884b439a899bcf9b269323217196737daafe')
        new = history_literal('tests', 10, '1ba2cfd2667acabdc9501c7e856911bacdd5ed5a6786ae21bbeb96b421246143')
        v.english_coverage(old, new, [{'text':history_literal('tests', 640, 'f7cf45de51b1517dfba8aa57159485cab2c0579a528550ce2c15a05789afd617'),'reason':'Original user trigger'}])
        with self.assertRaisesRegex(ValueError, 'missing original trigger'):
            v.english_coverage(old, new.replace(history_literal('tests', 642, 'f7cf45de51b1517dfba8aa57159485cab2c0579a528550ce2c15a05789afd617'),'less code'), [])

    def test_no_blanket_cyrillic_prose_exception(self):
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage(history_literal('tests', 280, 'af48ca2d110cfc589a6dfd3c950c5e837f182a92419bcc1b20966103828fa114'), history_literal('tests', 281, 'af48ca2d110cfc589a6dfd3c950c5e837f182a92419bcc1b20966103828fa114'),
                               [{'text':history_literal('tests', 861, 'af48ca2d110cfc589a6dfd3c950c5e837f182a92419bcc1b20966103828fa114'),'reason':'ignore all'}])

    def test_missing_translation_fails(self):
        with self.assertRaisesRegex(ValueError, 'undeclared Cyrillic'):
            v.english_coverage(history_literal('tests', 283, '2302145027357a89d84e69ce23892afc6a6e336a18e781e5e99662f23387ee18'), history_literal('tests', 284, '2302145027357a89d84e69ce23892afc6a6e336a18e781e5e99662f23387ee18'), [])

    def test_yaml_outer_quotes_are_not_trigger_aliases(self):
        old = history_literal('tests', 11, '0f217944d0b712250cbaa0b6a26e23084175f430450eb1a2d0b2e7e51c2f0b84')
        v.english_coverage(old, old.replace(history_literal('tests', 285, 'b39e648607bfa54c5a28579c6c7fa3d7ec4f836abcd1707bb4721a4e1308af13'), 'Reviews changes.'), [])
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage(old, old, [{'text':history_literal('tests', 865, 'b39e648607bfa54c5a28579c6c7fa3d7ec4f836abcd1707bb4721a4e1308af13'),'reason':'wrong outer-quote exemption'}])

    def test_descriptive_quote_is_not_mistaken_for_trigger(self):
        old = history_literal('tests', 12, 'a3088fb5f24f4538f26f8dcdf9073a0df9b42f1e36024deaf61386ac4e99b46f')
        new = history_literal('tests', 13, 'af19a6e1361a36e79a510c3ed103d35a8432f3926db16348a9977694018e70b9')
        v.english_coverage(old,new,[{'text':history_literal('tests', 646, '26ec6a701185ee7b2aeb6dcc57500df38af335144ec7bc3f0e28ec545d5a83e4'),'reason':'Exact trigger'}])
        with self.assertRaisesRegex(ValueError,'missing original trigger'):
            v.english_coverage(old,new.replace(history_literal('tests', 648, '26ec6a701185ee7b2aeb6dcc57500df38af335144ec7bc3f0e28ec545d5a83e4'),'acceptance'),[])

    def test_original_link_fragment_and_numbered_id_are_data(self):
        old = history_literal('tests', 14, '40f8a8d218ac0b351fdcf5a33be54faf8033c43102288f05a3723f1b9686ee4e')
        new = history_literal('tests', 15, 'eeda0349b2dd01ca56ec1117121ba9b8465998d12b37e9a8c426097834f8961d')
        literals = [{'text':history_literal('tests', 291, '5509c528f792ce56c023826defb87605af0da5f71239ab12e8dc0042c848353c'),'reason':'Original target'},
                    {'text':history_literal('tests', 295, 'dd93b3c3a804db3ec501d4c05dc4acbf3ae75dbbe0eaab0db149af2637e839f5'),'reason':'Original section identifier'}]
        v.english_coverage(old,new,literals)
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,new+history_literal('tests', 650, '9b3171ba7b58f5181fbc7e407d757ac105640d59726d753c539f0a2baae15068'),literals+[{'text':history_literal('tests', 1022, 'ca1a40589d6367fd722e9873032ea6b583bef26720afdd0c66efe08f51299a52'),'reason':'not data'}])

    def test_fake_alias_cannot_be_added(self):
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage(history_literal('tests', 299, '244ccc8a1f8f68467ebd5e2455153771c33dc67a614d257fc8b51b3f7d250b12'), history_literal('tests', 300, '5b885e8b7d9f0ee6b2ad741ce1b8c54b8c290c7aa9c8d2934f343b01ca996a4b'),
                               [{'text':history_literal('tests', 869, '6186abda14a2a7534091602a5f6ee025cf237e105265dfcca15346574e8287d2'),'reason':'invented'}])


class AnchorAndTokenTests(unittest.TestCase):
    def test_duplicate_heading_suffix_and_percent_encoded_fragment(self):
        text = history_literal('tests', 16, 'ca1738a1bea1d0d9472c689a5a5f8335e99d3ec6be5ed156642422dfba361991')
        self.assertEqual(v.check_fragments('x.md', text, {'x.md':text.encode()}), [])
        broken = text.replace('#test-1)', '#test-2)')
        self.assertTrue(v.check_fragments('x.md', broken, {'x.md':broken.encode()}))

    def test_explicit_collision_fails(self):
        text = '# Test\n<a id="test"></a>\n'
        self.assertIn('anchor_collision', v.check_fragments('x.md', text, {'x.md':text.encode()}))

    def test_case_sensitive_fragment(self):
        text = '# Test\n[bad](#Test)\n'
        self.assertTrue(v.check_fragments('x.md', text, {'x.md':text.encode()}))

    def test_original_compatibility_anchor_permitted_but_not_arbitrary_text(self):
        v.english_coverage(history_literal('tests', 68, 'a879dce27422df5bcacec13465bbef721140743599032fd116e67769f8167684'), history_literal('tests', 69, '8aca012e0706db95bcf81108bff85af70050521415cb72864e99f62315351d83'),
                           [{'text':history_literal('tests', 657, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),'reason':'Original heading fragment'}])

    def test_changed_command_id_url_detected(self):
        text = '`git status` https://example.test/x ' + 'a'*40
        for changed in [text.replace('git status','git reset'),text.replace('/x','/y'),text.replace('a'*40,'b'*40)]:
            self.assertNotEqual(v.machine_tokens(text), v.machine_tokens(changed))


class GuardTests(unittest.TestCase):
    def sources(self):
        lines = ['\n'] * 408
        lines[0] = 'def sample(values):\n'
        for row in v.GUARD_TARGETS:
            lines[row['line']-1] = '    values['+str(row['line'])+'] = '+repr(row['original'])+'\n'
        old = ''.join(lines)
        for row in v.GUARD_TARGETS:
            suffix = ' ' if row['original'].endswith(' ') else ''
            lines[row['line']-1] = '    values['+str(row['line'])+'] = '+repr(row['preserved_prefix']+' English diagnostic.'+suffix)+'\n'
        return old, ''.join(lines)

    def test_all_nineteen_only_literal_translation(self):
        v.guard_proof(*self.sources())

    def test_prefix_change_rejected(self):
        old,new = self.sources()
        with self.assertRaises(ValueError):
            v.guard_proof(old,new.replace('STATE_IO:', 'OTHER_CODE:'))

    def test_trailing_separator_rejected(self):
        old,new = self.sources()
        with self.assertRaisesRegex(ValueError, 'separator'):
            v.guard_proof(old,new.replace("SNAPSHOT_CHECK_FAILED: English diagnostic. '","SNAPSHOT_CHECK_FAILED: English diagnostic.'"))

    def test_key_condition_call_field_comment_and_concatenation_rejected(self):
        old,new = self.sources()
        mutations = [new.replace('values[382]','values[383]'),
                     new+'    if True: return 1\n', new+'    danger()\n',
                     new+'    values.field = 1\n',new+'# changed comment\n',
                     new.replace("'STATE_IO: English diagnostic.'", "'STATE_IO: English diagnostic.' + str(values)")]
        for changed in mutations:
            with self.subTest(delta=changed[-80:]):
                with self.assertRaises(ValueError):
                    v.guard_proof(old,changed)

    def test_untranslated_diagnostic_rejected(self):
        old,new=self.sources()
        with self.assertRaisesRegex(ValueError, 'untranslated'):
            v.guard_proof(old,old)


class HistoricalAndMetadataTests(unittest.TestCase):
    def test_historical_relative_rebase_same_target(self):
        v.historical_targets('docs/old.md','docs/translations/en/docs/old.md',
                             '[guide](../rules/a.md)\n[self](#old)',
                             '[guide](../../../../rules/a.md)\n[self](#old)')
        with self.assertRaisesRegex(ValueError, 'destination'):
            v.historical_targets('docs/old.md','docs/translations/en/docs/old.md',
                                 '[guide](../rules/a.md)', '[guide](../../../../rules/b.md)')

    def metadata(self):
        before={}; data={}; allowed={'doc.md':{}}
        for filename in ('source-map.json','layout-migration.json','authorized-additions.json'):
            obj={'files':[{'destination':'doc.md','source_sha256':'immutable','sha256':v.digest(b'old'),
                           'transformations':['historical']}], 'origin':'pinned'}
            if filename == 'authorized-additions.json':
                obj['adaptations']=[]
            name='provenance/'+filename
            before[name]=json.dumps(obj).encode()
            obj['files'][0]['sha256']=v.digest(b'new')
            obj['files'][0]['transformations'].append('English translation')
            data[name]=json.dumps(obj).encode()
        data['doc.md']=b'new'
        return before,data,allowed

    def test_metadata_current_digest_and_append_only_note(self):
        v.metadata_proof(*self.metadata())

    def test_metadata_source_identity_cannot_be_reblessed(self):
        before,data,allowed=self.metadata()
        n='provenance/source-map.json';o=json.loads(data[n]);o['files'][0]['source_sha256']='rewritten';data[n]=json.dumps(o).encode()
        with self.assertRaisesRegex(ValueError,'historical identity'):
            v.metadata_proof(before,data,allowed)

    def test_metadata_prior_transformation_cannot_be_removed(self):
        before,data,allowed=self.metadata()
        n='provenance/source-map.json';o=json.loads(data[n]);o['files'][0]['transformations']=['replacement'];data[n]=json.dumps(o).encode()
        with self.assertRaisesRegex(ValueError,'historical transformation'):
            v.metadata_proof(before,data,allowed)

    def test_extended_cyrillic_is_not_coverage_bypass(self):
        for char in (history_literal('tests', 83, '400b3bbbbdde3d5c0cc7477f1c813aacff5d24901d13a0871f6236be1448a10f'),history_literal('tests', 84, '92fb755743ca51d864314a1365a10229ce75fa34c3bfb4f3a6714c997b2c38d9'),history_literal('tests', 85, '963dd7d0b94ca78c4407f478d46e24737492d63a5ae890f68c7b9dc05635e918')):
            with self.subTest(char=char):
                with self.assertRaisesRegex(ValueError,'Cyrillic'):
                    v.english_coverage('Original',char,[])


class RefusalBoundaryTests(unittest.TestCase):
    def test_only_plain_echo_display_text_translation_allowed(self):
        old=history_literal('tests', 23, '759fd23e8fddf691f876ee329cce9757badd38c3bf309dd6c2f861c197120490')
        v.machine_blocks_proof(old,'```bash\necho "Hello"\n```\n')
        for new in ['```bash\nrm -rf target\n```\n',
                    '```bash\necho "$(danger)"\n```\n',
                    '```bash\necho -n "Hello"\n```\n']:
            with self.subTest(new=new):
                with self.assertRaises(ValueError): v.machine_blocks_proof(old,new)

    def test_json_machine_keys_and_enums_frozen_on_cyrillic_line(self):
        old=history_literal('tests', 24, 'd8a6539b53236b177ccae918436553bfba39ad18a6a451ebde3c68f14f085470')
        for new in [old.replace('state','status'),old.replace('READY','BLOCKED'),old.replace(history_literal('tests', 344, '81e4832cdd84e1f5dd193dc4ae9c384e932d07fcaff67b7f0b4720894ac1e60b'),'Example')]:
            with self.assertRaisesRegex(ValueError,'machine data'):
                v.machine_blocks_proof(old,new)

    def test_code_comment_and_inline_anchor_are_not_rendered(self):
        for hidden in ['```text\n<a id="old"></a>\n```',
                       '<!--\n<a id="old"></a>\n-->',
                       '`<a id="old"></a>`',
                       '    <a id="old"></a>']:
            text=hidden+'\n[link](#old)\n'
            with self.subTest(hidden=hidden):
                self.assertTrue(v.check_fragments('x.md',text,{'x.md':text.encode()}))

    def test_fence_delimiter_and_length_must_match(self):
        for close in ['```','~~~~']:
            text='````text\n'+close+'\n<a id="old"></a>\n````\n[link](#old)\n'
            with self.subTest(close=close):
                self.assertTrue(v.check_fragments('x.md',text,{'x.md':text.encode()}))
        text='~~~~text\n```\n# Hidden\n~~~~\n# Visible\n'
        self.assertEqual(v.headings(text),['visible'])

    def test_remaining_cyrillic_blocks_rejected(self):
        for char in (history_literal('tests', 96, '9770f13b69a46ef10814c733cd8590d6ce9a2100dad3d31dcdc284a1c6807617'),history_literal('tests', 97, 'c9172689221b5285e81cecdf0b27e6c9f764bad7cd31bdb4c60254328109b8ce')):
            with self.assertRaisesRegex(ValueError,'Cyrillic'):
                v.english_coverage('old',char,[])


class CompleteVerificationTests(unittest.TestCase):
    """Synthetic complete-tree proof of the real verify/main path, not real-baseline evidence."""
    def setUp(self):
        import shutil
        self.temp=tempfile.TemporaryDirectory(); self.home=Path(self.temp.name)
        self.base=self.home/'baseline'; self.root=self.home/'current';self.base.mkdir();self.root.mkdir()
        self.before={'doc.md':history_literal('tests_bytes', 3, 'd96fc07f239fefd6d942fba48918c2866421c0da7f19c552110e81e073d0e1dd'),
                     'history.md':history_literal('tests', 674, '766f4172759eca32d6876179fcf02fee33ee1a7366b43446591784bcbdff1324').encode(),
                     'frozen.py':b'VALUE = 1\n',
                     'LICENSE.txt':b'Original notice\n',
                     'tests/unicode.py':history_literal('tests', 675, '5730bb0110ba0f89c0cc09321d244cf7082e762e85bf8350851b27829750741d').encode(),
                     'provenance/research-archive.json':b'{"files":{}}'}
        for i in range(74):
            self.before[f'skills/s{i}/SKILL.md']=f'---\nname: s{i}\ndescription: English\n---\nBody {i}\n'.encode()
        self.skill='skills/s0/SKILL.md';self.before[self.skill]=history_literal('tests', 349, 'a18d49f38dd82a4fc6ed4b52d051934672f6166572188dc07abc17ba98881a19').encode()
        self.guard='runtime/session-size-docker/guard.py'; oldguard,newguard=GuardTests().sources()
        self.before[self.guard]=oldguard.encode()
        for n in ('source-map.json','layout-migration.json','authorized-additions.json'):
            self.before['provenance/'+n]=json.dumps({'files':[],'adaptations':[]}).encode()
        self.write(self.base,self.before);self.seal(self.base)
        self.pin=v.digest((self.base/'release-manifest.json').read_bytes())
        shutil.copytree(self.base,self.root,dirs_exist_ok=True)
        self.changed={'doc.md':history_literal('tests', 679, '4aa1aebec0a84423a55e120a4cfbf7b29f1b81db954e69469773c5c747793436').encode(),
                      self.skill:self.before[self.skill].replace(history_literal('tests', 891, '2302145027357a89d84e69ce23892afc6a6e336a18e781e5e99662f23387ee18').encode(),b'Description'),
                      self.guard:newguard.encode()}
        self.history='docs/translations/en/history.md'
        self.changed[self.history]=(f"Historical translation of history.md; {v.digest(self.before['history.md'])}; {v.BASE_COMMIT}{history_literal('tests', 682, '2d3f7fb660d7738e5ad404fdd4e624e17830975beac660c227d2003769634f37')}").encode()
        self.write(self.root,self.changed)
        self.allowed=[{'path':n,'operation':'modify','class':cls} for n,cls in
                      [('doc.md','current_docs'),(self.skill,'skills'),(self.guard,'guard_diagnostics_only')]]
        self.allowed.append({'path':self.history,'operation':'create','class':'historical_translation','original':'history.md'})
        self.allowed += [{'path':n,'operation':'modify','class':'derived_metadata'} for n in
                         ['release-manifest.json','checksums.sha256','provenance/source-map.json','provenance/layout-migration.json','provenance/authorized-additions.json']]
        self.allowed.append({'path':'provenance/english-translations.json','operation':'create','class':'translation_contract_or_test'})
        self.records=[]
        for row in self.allowed[:4]:
            n=row['path']; literals=[]
            if n=='doc.md': literals=[{'text':history_literal('tests', 898, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),'reason':'original heading'},{'text':history_literal('tests', 902, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),'reason':'original fragment'}]
            if n==self.history: literals=[{'text':history_literal('tests', 906, 'd1f5f54f14926a4a22e91beb98ee7e92d7f971a51ad519f17b94b3a9d66db014'),'reason':'original heading'}]
            rec={'path':n,'class':row['class'],'base_sha256':None if n==self.history else v.digest(self.before[n]),'sha256':v.digest((self.root/n).read_bytes()),'preserved_literals':literals}
            if n==self.history:rec.update(original='history.md',original_sha256=v.digest(self.before['history.md']))
            self.records.append(rec)
        self.save_records();self.seal(self.root)
        self.patches=[patch.object(v,'BASE_MANIFEST',self.pin),patch.object(v,'ALLOWLIST',self.allowed),patch.object(v,'DESCRIPTION_PATHS',[self.skill])]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def write(self,root,data):
        for n,raw in data.items():
            p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

    def seal(self,root):
        names=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name not in ('release-manifest.json','checksums.sha256'))
        manifest={'version':'fixture','files':[{'path':n,'sha256':v.digest((root/n).read_bytes()),'component':'core'} for n in names]}
        raw=json.dumps(manifest).encode();(root/'release-manifest.json').write_bytes(raw)
        checks={r['path']:r['sha256'] for r in manifest['files']};checks['release-manifest.json']=v.digest(raw)
        (root/'checksums.sha256').write_text(''.join(checks[n]+'  '+n+'\n' for n in sorted(checks)))

    def save_records(self):
        (self.root/'provenance/english-translations.json').write_text(json.dumps({'schema_version':1,'baseline_commit':v.BASE_COMMIT,'records':self.records}))

    def corrupt(self,name,text,update_record=True):
        (self.root/name).write_text(text)
        if update_record:
            for r in self.records:
                if r['path']==name:r['sha256']=v.digest((self.root/name).read_bytes())
            self.save_records()
        self.seal(self.root)

    def result(self):return v.verify_historical(self.root,self.base)

    def test_complete_valid_tree_pass_and_all_74_outcomes(self):
        result=self.result();self.assertEqual(result['status'],'PASS',result['issues']);self.assertEqual(len(result['skills']),74)
        self.assertEqual(result['skills'][0]['status'],'AUTHORIZED_TRANSLATION')

    def test_frozen_file_and_original_history_and_license_refused(self):
        for n in ['frozen.py','history.md','LICENSE.txt','tests/unicode.py']:
            with self.subTest(path=n):
                raw=(self.root/n).read_bytes();self.corrupt(n,'changed')
                result=self.result();self.assertEqual(result['status'],'FAIL');self.assertIn('frozen_file_changed:'+n,result['issues'])
                (self.root/n).write_bytes(raw);self.seal(self.root)

    def test_new_out_of_scope_file_refused(self):
        (self.root/'extra.py').write_text('new')
        self.seal(self.root)
        self.assertIn('unexpected_file:extra.py',self.result()['issues'])

    def test_missing_expected_file_refused(self):
        (self.root/'frozen.py').unlink();self.seal(self.root)
        self.assertIn('missing_file:frozen.py',self.result()['issues'])

    def test_changed_description_body_refused(self):
        self.corrupt(self.skill,(self.root/self.skill).read_text().replace('Body 0','Wrong body'))
        self.assertTrue(any('description-only' in x for x in self.result()['issues']))

    def test_missing_translation_refused_in_verify(self):
        self.corrupt(self.skill,self.before[self.skill].decode())
        self.assertTrue(any('Cyrillic' in x for x in self.result()['issues']))

    def test_changed_command_and_hidden_anchor_refused_in_verify(self):
        raw=(self.root/'doc.md').read_text()
        for changed in [raw.replace('echo "Hello"','rm -rf target'),raw.replace(history_literal('tests', 393, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),history_literal('tests', 394, 'd36f6f03fdd1ad14c47d451f1396107e8ab55e1c5ce6f89952efe1764df4542e'))]:
            self.corrupt('doc.md',changed)
            self.assertEqual(self.result()['status'],'FAIL')
        self.corrupt('doc.md',raw)

    def test_multiline_hidden_anchor_refused_by_complete_verify(self):
        raw = (self.root/'doc.md').read_text()
        self.corrupt('doc.md',raw.replace(history_literal('tests', 397, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),
                     history_literal('tests', 398, 'b4749131d105f591b65ac4fef8d511ee2ec7082835d137d77d3af5baf7b2296d')))
        result = self.result()
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('lost heading compatibility anchor:doc.md',result['issues'])

    def test_code_removal_cannot_synthesize_anchor_in_complete_verify(self):
        raw = (self.root/'doc.md').read_text()
        self.corrupt('doc.md',raw.replace(history_literal('tests', 401, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),
                     history_literal('tests', 402, '555c9ebe8065f17a4978cfda4f27909f9a0390108a3dc4384e156038ad389fad')))
        result = self.result()
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('lost heading compatibility anchor:doc.md',result['issues'])

    def test_code_removal_cannot_synthesize_link_in_complete_verify(self):
        raw = (self.root/'doc.md').read_text()
        self.corrupt('doc.md',raw + '\n[x]`code`(#missing)\n')
        result = self.result()
        self.assertEqual(result['status'],'PASS',result['issues'])

    def test_stale_source_hash_and_missing_provenance_row_refused(self):
        self.records[0]['base_sha256']='0'*64;self.save_records();self.seal(self.root)
        self.assertIn('provenance_base_hash:doc.md',self.result()['issues'])
        self.records.pop();self.save_records();self.seal(self.root)
        self.assertIn('provenance_scope',self.result()['issues'])

    def test_wrong_historical_mapping_and_banner_refused(self):
        self.records[-1]['original']='frozen.py';self.save_records();self.seal(self.root)
        self.assertIn('historical_mapping:'+self.history,self.result()['issues'])
        self.corrupt(self.history,'# Ancient\n')
        self.assertIn('historical_banner:'+self.history,self.result()['issues'])

    def test_payload_and_checksum_closure_refused(self):
        (self.root/'frozen.py').write_text('not sealed')
        self.assertEqual(self.result()['status'],'FAIL')
        self.assertTrue(any('invalid_tree' in x for x in self.result()['issues']))
        self.seal(self.root);(self.root/'checksums.sha256').write_text('wrong')
        self.assertEqual(self.result()['status'],'FAIL')

    def test_guard_condition_refused_in_verify(self):
        self.corrupt(self.guard,(self.root/self.guard).read_text()+'    if True: return None\n')
        result=self.result();self.assertEqual(result['status'],'FAIL');self.assertTrue(any('guard behavior' in x for x in result['issues']))

    def test_all_skill_outcomes_retained_on_early_failure(self):
        (self.root/'checksums.sha256').write_text('wrong')
        result=self.result();self.assertEqual(result['status'],'FAIL');self.assertEqual(len(result['skills']),74)

    def test_cleanup_full_verifier_integration_preserves_other_guards(self):
        import difflib
        old=(self.root/'doc.md').read_text()
        new=old.replace('echo "Hello"','echo "Hello"  # Selected project root')
        hunks=[{'start':j1,'end':j2,'before':old[i1:i2],'after':new[j1:j2]}
               for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old,b=new,autojunk=False).get_opcodes() if tag!='equal']
        contract={'doc.md':{'before_sha256':v.digest(old.encode()),'proposed_sha256':v.digest(new.encode()),
                            'historical_original':False,'hunks':hunks}}
        self.corrupt('doc.md',new)
        with patch.object(v,'CLEANUP_FILES',contract):
            self.assertEqual(self.result()['status'],'PASS',self.result()['issues'])
            self.corrupt('doc.md',new.replace('echo "Hello"','echo "Changed"'))
            self.assertEqual(self.result()['status'],'FAIL')
            self.corrupt('doc.md',new)
            self.corrupt('frozen.py','changed')
            self.assertIn('frozen_file_changed:frozen.py',self.result()['issues'])

    def test_anchor_full_verifier_composition_and_current_tree_guard(self):
        import difflib,copy
        old=(self.root/'doc.md').read_text()
        current=old.replace(history_literal('tests', 724, '3ebc469282cb3edc2a32e0be9dab761a201e76b4d766130b9040b55b89b34d86'),'').replace(history_literal('tests', 149, 'df9096e26d8f23d09e1e8a955223d8aaec39bd02c5110c0a3d60d5a6d9a8d3a6'),'#review)')
        prior=copy.deepcopy(self.records[0]['preserved_literals'])
        contracts={}
        def install(text):
            hunks=[{'start':j1,'end':j2,'before':old[i1:i2],'after':text[j1:j2]}
                   for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old,b=text,autojunk=False).get_opcodes() if tag!='equal']
            row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(text.encode()),
                 'removed_ids':[{'old_id':history_literal('tests', 925, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),'new_id':'review','binding':'Review'}],
                 'changed_targets':[{'old_target':history_literal('tests', 931, '1d18a628554bf375fd7f873f9805d8c3179f83eae140cd01f7d653296d8ab503'),'new_target':'#review','count':1}],
                 'banner_changes':[],'hunks':hunks,
                 'removed_preserved_literals':[{'index':i,'record':r} for i,r in enumerate(prior)],
                 'pre_literals_sha256':v.canonical_records_digest(prior),'current_literals_sha256':v.canonical_records_digest([])}
            contracts['doc.md']=row
            self.records[0]['preserved_literals']=[]
            self.corrupt('doc.md',text)
            provenance=json.loads((self.root/'provenance/english-translations.json').read_text())
            provenance['anchor_migration']={'pre_anchor_commit':v.ANCHOR_COMMIT,'pre_anchor_manifest_sha256':v.ANCHOR_MANIFEST,
                                           'files':[{k:x for k,x in row.items() if k!='hunks'}]}
            (self.root/'provenance/english-translations.json').write_text(json.dumps(provenance))
            self.seal(self.root)
        excluded=[n for n in self.before if n.endswith('.md') and n!='doc.md']+[self.history]
        with patch.object(v,'ANCHOR_FILES',contracts),patch.object(v,'MAINTAINED_MARKDOWN',['doc.md']),patch.object(v,'ANCHOR_EXCLUDED_MARKDOWN',excluded):
            install(current)
            self.assertEqual(self.result()['status'],'PASS',self.result()['issues'])
            # Even a self-consistent inverse/provenance contract cannot turn a bad
            # actual destination into a successful current navigation proof.
            install(current.replace('#review)','#missing)'))
            self.assertEqual(self.result()['status'],'FAIL')
            install(current)
            self.records[0]['preserved_literals']=prior;self.save_records();self.seal(self.root)
            self.assertEqual(self.result()['status'],'FAIL')
            install(current)
            self.corrupt('frozen.py','changed')
            self.assertIn('frozen_file_changed:frozen.py',self.result()['issues'])

    def test_anchor_declared_literal_in_body_passes_but_native_heading_fails(self):
        import difflib,copy
        old=(self.root/'doc.md').read_text();prior=copy.deepcopy(self.records[0]['preserved_literals'])
        current=old.replace(history_literal('tests', 739, '3ebc469282cb3edc2a32e0be9dab761a201e76b4d766130b9040b55b89b34d86'),'').replace(history_literal('tests', 151, 'df9096e26d8f23d09e1e8a955223d8aaec39bd02c5110c0a3d60d5a6d9a8d3a6'),'#review)')
        contracts={}
        def install(text):
            hunks=[{'start':j1,'end':j2,'before':old[i1:i2],'after':text[j1:j2]}
                   for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old,b=text,autojunk=False).get_opcodes() if tag!='equal']
            retained=[prior[1]]  # The exact original literal survives as body data.
            row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(text.encode()),
                 'removed_ids':[{'old_id':history_literal('tests', 940, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),'new_id':'review','binding':'Review'}],
                 'changed_targets':[{'old_target':history_literal('tests', 946, '1d18a628554bf375fd7f873f9805d8c3179f83eae140cd01f7d653296d8ab503'),'new_target':'#review','count':1}],
                 'banner_changes':[],'heading_changes':[],'hunks':hunks,
                 'removed_preserved_literals':[{'index':0,'record':prior[0]}],
                 'pre_literals_sha256':v.canonical_records_digest(prior),'current_literals_sha256':v.canonical_records_digest(retained)}
            contracts['doc.md']=row;self.records[0]['preserved_literals']=retained
            self.corrupt('doc.md',text)
            provenance=json.loads((self.root/'provenance/english-translations.json').read_text())
            provenance['anchor_migration']={'pre_anchor_commit':v.ANCHOR_COMMIT,'pre_anchor_manifest_sha256':v.ANCHOR_MANIFEST,
                                           'files':[{k:x for k,x in row.items() if k!='hunks'}]}
            (self.root/'provenance/english-translations.json').write_text(json.dumps(provenance));self.seal(self.root)
        excluded=[n for n in self.before if n.endswith('.md') and n!='doc.md']+[self.history]
        with patch.object(v,'ANCHOR_FILES',contracts),patch.object(v,'MAINTAINED_MARKDOWN',['doc.md']),patch.object(v,'ANCHOR_EXCLUDED_MARKDOWN',excluded):
            install(current+history_literal('tests', 746, 'd3bd347a85eb079f764b45799c517f46f238fb7cc4aacf8f4020be9a8e538c0e'))
            self.assertEqual(self.result()['status'],'PASS',self.result()['issues'])
            install(current+history_literal('tests', 749, '6f02f156e371f3336ac6a72fe3a2a1a3bd647258cee902b987614fa4dec0d8e6'))
            # Pins, inverse, current declared literals and payload all agree; only
            # the current navigation location changes this permitted data to an ID.
            self.assertEqual(self.result()['status'],'FAIL')

    def test_cli_exit_receipt_uses_real_verifier(self):
        import contextlib,io
        args=['verify_translation','--root',str(self.root),'--baseline',str(self.base)]
        stream=io.StringIO()
        with patch('sys.argv',args),contextlib.redirect_stdout(stream):
            self.assertEqual(v.historical_main(),0)
        self.assertEqual(json.loads(stream.getvalue())['status'],'PASS')
        self.corrupt('frozen.py','changed');stream=io.StringIO()
        with patch('sys.argv',args),contextlib.redirect_stdout(stream):
            self.assertEqual(v.historical_main(),1)
        self.assertEqual(json.loads(stream.getvalue())['status'],'FAIL')


class MutationSensitivityTests(unittest.TestCase):
    """Independent removals must make the mapped full-tree negative fail.

These kills supplement semantic review; they do not prove all mutants are covered.
Each mutant disables one enforcement statement without changing fixtures or expectations.
"""
    CASES = [
        ("issues.append('unexpected_file:' + n)", 'test_new_out_of_scope_file_refused'),
        ("issues.append('frozen_file_changed:' + n)", 'test_frozen_file_and_original_history_and_license_refused'),
        ("issues.extend('missing_file:' + n for n in sorted(expected - found))", 'test_missing_expected_file_refused'),
        ("issues.append('provenance_scope')", 'test_stale_source_hash_and_missing_provenance_row_refused'),
        ("issues.append('provenance_base_hash:' + n)", 'test_stale_source_hash_and_missing_provenance_row_refused'),
        ("issues.append('historical_mapping:' + n)", 'test_wrong_historical_mapping_and_banner_refused'),
        ("issues.append('historical_banner:' + n)", 'test_wrong_historical_mapping_and_banner_refused'),
    ]

    def test_cleanup_enforcement_has_attributable_full_tree_mutation_kill(self):
        import inspect
        source=inspect.getsource(v.verify_historical);original=v.verify_historical
        statement='structural_data = cleanup_content_proof(before, anchor_restored)'
        self.assertEqual(source.count(statement),1)
        mutant=source.replace(statement,'structural_data = dict(data)')
        try:
            exec(compile(mutant,'<synthetic-cleanup-guard-mutation>','exec'),v.__dict__)
            result=unittest.TestResult()
            CompleteVerificationTests('test_cleanup_full_verifier_integration_preserves_other_guards').run(result)
            self.assertGreater(len(result.failures),0,'SURVIVED: cleanup enforcement')
            self.assertEqual(result.errors,[],'Mutation must fail a mapped assertion, not crash')
        finally:
            v.verify_historical=original

    def test_anchor_full_tree_enforcement_has_attributable_mutation_kills(self):
        import inspect
        source=inspect.getsource(v.verify_historical);original=v.verify_historical
        cases=[('anchor_restored = anchor_content_proof(data)','anchor_restored = dict(data)'),
               ('current_tree_navigation_proof(data)','pass  # disabled current navigation'),
               ('restored_literals = anchor_provenance_proof(data, provenance)','restored_literals = {}')]
        for statement,replacement in cases:
            with self.subTest(statement=statement):
                self.assertEqual(source.count(statement),1)
                try:
                    exec(compile(source.replace(statement,replacement),'<synthetic-anchor-enforcement-mutation>','exec'),v.__dict__)
                    result=unittest.TestResult()
                    CompleteVerificationTests('test_anchor_full_verifier_composition_and_current_tree_guard').run(result)
                    self.assertGreater(len(result.failures),0,'SURVIVED: '+statement)
                    self.assertEqual(result.errors,[],'Mutation must fail a mapped assertion, not crash')
                finally:
                    v.verify_historical=original

    def test_current_ID_policy_and_resolution_have_independent_full_tree_mutation_kills(self):
        import inspect
        cases=[('current_navigation',
                lambda source:source.replace('CYRILLIC.search(', '(lambda _value: False)('),
                'test_anchor_declared_literal_in_body_passes_but_native_heading_fails'),
               ('current_tree_navigation_proof',
                lambda source:source.replace('if fragment not in target_ids:', 'if False:  # disabled resolution'),
                'test_anchor_full_verifier_composition_and_current_tree_guard')]
        for name,mutate,test_name in cases:
            original=getattr(v,name);source=inspect.getsource(original);changed=mutate(source)
            with self.subTest(guard=name):
                self.assertNotEqual(source,changed)
                try:
                    exec(compile(changed,'<independent-navigation-policy-mutation>','exec'),v.__dict__)
                    result=unittest.TestResult();CompleteVerificationTests(test_name).run(result)
                    self.assertGreater(len(result.failures),0,'SURVIVED: '+name)
                    self.assertEqual(result.errors,[],'Independent guard must fail intended assertion, not crash')
                finally:
                    setattr(v,name,original)

    def test_full_tree_guards_have_attributable_mutation_kills(self):
        import inspect
        source=inspect.getsource(v.verify_historical); original=v.verify_historical
        for statement,test_name in self.CASES:
            with self.subTest(statement=statement):
                self.assertEqual(source.count(statement),1)
                mutated=source.replace(statement,'pass  # intentionally disabled by mutation fixture')
                try:
                    exec(compile(mutated,'<synthetic-guard-mutation>','exec'),v.__dict__)
                    result=unittest.TestResult()
                    CompleteVerificationTests(test_name).run(result)
                    self.assertGreater(len(result.failures),0,
                                       'SURVIVED: '+statement+'; errors='+repr(result.errors))
                    self.assertEqual(result.errors,[], 'Mutation must fail the intended assertion, not crash')
                finally:
                    v.verify_historical=original




class RealTreeRegressionTests(unittest.TestCase):
    def test_external_rebase_preserves_exact_destination(self):
        v.historical_targets('ai-factory/a.md','docs/translations/en/ai-factory/a.md',
                             '[x](../../projects/a.md)', '[x](../../../../../projects/a.md)')
        with self.assertRaises(ValueError):
            v.historical_targets('ai-factory/a.md','docs/translations/en/ai-factory/a.md',
                                 '[x](../../projects/a.md)', '[x](../../../../../projects/b.md)')

    def test_inline_shell_comments_do_not_authorize_command_changes(self):
        old = history_literal('tests', 31, '990e2a19dbbc0ddf6a7168bdbed972941741e540920a42c01210e80dbeba6931')
        v.machine_blocks_proof(old,old.replace(history_literal('tests', 509, '521d83be9304146af0ad4c4aa5bfe97203ea8b0b58c58a8962561cb0426302a5'),'installation'))
        for candidate in (old.replace('pip install','pip uninstall').replace(history_literal('tests', 511, '521d83be9304146af0ad4c4aa5bfe97203ea8b0b58c58a8962561cb0426302a5'),'installation'),
                          old.replace('package','other').replace(history_literal('tests', 513, '521d83be9304146af0ad4c4aa5bfe97203ea8b0b58c58a8962561cb0426302a5'),'installation')):
            with self.assertRaises(ValueError): v.machine_blocks_proof(old,candidate)
        with self.assertRaises(ValueError):
            v.machine_blocks_proof(history_literal('tests', 515, 'a479821d5041afe75e415e2e5b198d3fb319e1dcb5b0818a6c5b83fcbfcecdf3'),'```bash\nrun "# data"\n```')

    def test_exact_skill_example_description_not_yaml_machine_values(self):
        old = history_literal('tests', 32, 'f31fbadf013c90436c5b16bc0a8fd34be9c51536f4cfe190b50875ab022eb248')
        new = old.replace(history_literal('tests', 179, '2302145027357a89d84e69ce23892afc6a6e336a18e781e5e99662f23387ee18'),'Description')
        v.machine_blocks_proof(old,new)
        for candidate in (new.replace('skill-name','other'), new.replace('description:','permission:')):
            with self.assertRaises(ValueError): v.machine_blocks_proof(old,candidate)
        with self.assertRaises(ValueError):
            v.machine_blocks_proof(history_literal('tests', 521, 'a93bf39a33f312158a888cb7999f85e8a20a27c6ec3233528c13d92e7975e7bd'),'```yaml\nmode: description\n```')

    def test_single_quoted_description_not_blanket_exception(self):
        old = history_literal('tests', 33, 'c2d1e86a287f84ca6c01c8132387c78c5360e6094afa39eff862ca9ca690dbdc')
        v.english_coverage(old,old.replace(history_literal('tests', 523, '8413daa02ff81043c045cef0e164bbafe9dce72b7755aff1b3095db088a5c6bf'),'Reviews the interface.'),[])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,old,[{'text':history_literal('tests', 965, '8413daa02ff81043c045cef0e164bbafe9dce72b7755aff1b3095db088a5c6bf'),'reason':'not an alias'}])

    def test_post_trigger_explanation_is_translatable(self):
        old = history_literal('tests', 34, '46897f329877130f44feed5b8b35645cbd7b2e9736e072979b941e149eebb657')
        new = history_literal('tests', 35, '6b6c3e5335cc664451d0182ac4eb033a6fc02182696d5ecfbe600da3a65ad5a3')
        v.english_coverage(old,new,[{'text':history_literal('tests', 756, 'aee34723603ca53981c1f3ed6daba6978a2d2b37654de70f7559a2f93a347d33'),'reason':'Exact request'}])
        with self.assertRaisesRegex(ValueError,'missing original trigger'):
            v.english_coverage(old,new.replace(history_literal('tests', 758, 'aee34723603ca53981c1f3ed6daba6978a2d2b37654de70f7559a2f93a347d33'),'show effect'),[])

    def test_protocol_labels_and_code_placeholders_are_source_bound(self):
        old = history_literal('tests', 36, '667e3e247486d8b4fe51df1624c3365696a74344d0bbaf1ca9594118a7c569ec')
        new = history_literal('tests', 37, '9dcb3bdf45ba2c392417d2e2515dc887eb772389f2a121310ad8b4896445e600')
        v.english_coverage(old,new,[{'text':history_literal('tests', 762, '96f9fca509ce98dad38e27d94072b635e9bf28bf5e9643a63e771fdcf2ccd360'),'reason':'Protocol label'},
                                   {'text':history_literal('tests', 766, '6c5834150edf780473fd93989bc206b8455aad7f395710ad91b49d88da2cfb03'),'reason':'Original placeholder'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(history_literal('tests', 528, '51e0fc44b8977482bc7a5f87c78a661cf0ae4616315de018c0da3da1f016aba4'),history_literal('tests', 529, '51e0fc44b8977482bc7a5f87c78a661cf0ae4616315de018c0da3da1f016aba4'),
                               [{'text':history_literal('tests', 969, '51e0fc44b8977482bc7a5f87c78a661cf0ae4616315de018c0da3da1f016aba4'),'reason':'not protocol data'}])

    def test_cyrillic_angle_placeholder_is_not_html_tag(self):
        self.assertEqual(v.headings(history_literal('tests', 530, '8e76c750b7f201518b4302a99ab4c4d0ba2bc96ecc4804773e69bd0eb346fb46')), [history_literal('tests', 531, '97f2b2534d48ecc5628f54cb09c66a17e5c05a339e23112eba46e218c2154aa4')])
        self.assertEqual(v.headings('### Finding <span>title</span>'), ['finding-title'])


class FrontmatterIdentifierTests(unittest.TestCase):
    def test_original_key_is_data_but_value_is_not(self):
        old = history_literal('tests', 38, '51df1abb0f253e2c41c8b57521860dc9afbc4b177f3dcbb23d45ecc349dfcc4d')
        new = history_literal('tests', 39, 'f2c07dbbaaeab54091624e2d38b8ae10c2b04413b75f66d9415ca622e44b2366')
        v.english_coverage(old,new,[{'text':history_literal('tests', 770, '037fabde956282bdb2f32d739acd593efc9f5863ac0ceb4d3db782f6fa040765'),'reason':'Original frontmatter key'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,old,[{'text':history_literal('tests', 973, '037fabde956282bdb2f32d739acd593efc9f5863ac0ceb4d3db782f6fa040765'),'reason':'Key'},
                                       {'text':history_literal('tests', 977, '3356a1c06695574179c1c3f321d477d0b418e74941e66ec0d7a1a2352f3e06af'),'reason':'Not a key'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,new.replace(history_literal('tests', 772, '037fabde956282bdb2f32d739acd593efc9f5863ac0ceb4d3db782f6fa040765'),history_literal('tests', 773, '1fa1af3ae83aebacc171be622a64d17909fae4fafbd9551c694db34d5e4c3faf')),
                               [{'text':history_literal('tests', 981, '1fa1af3ae83aebacc171be622a64d17909fae4fafbd9551c694db34d5e4c3faf'),'reason':'Invented key'}])

    def test_first_protocol_slash_label_is_supported(self):
        old = history_literal('tests', 40, 'd61ee57fb0e2fd2de47a82413c362565c7c18091e1af5116f1a126b710e6d782')
        v.english_coverage(old,old,[{'text':x,'reason':'Original protocol label'}
                                   for x in old.split(' / ')])


class MultilineInlineCodeTests(unittest.TestCase):
    def test_multiline_hidden_anchor_does_not_resolve(self):
        for span in ('text `first\n<a id="old"></a>\nlast`',
                     'text ``first `\n<a id="old"></a>\nlast``'):
            text = span + '\n[link](#old)'
            with self.subTest(span=span):
                self.assertEqual(v.check_fragments('x.md',text,{'x.md':text.encode()}),
                                 ['unresolved_fragment:#old'])

    def test_unmatched_and_different_length_runs_stay_literal(self):
        for text in ('text `first\n<a id="old"></a>',
                     'text ``first\n<a id="old"></a>\nlast`'):
            with self.subTest(text=text):
                self.assertIn('old',v.anchors(text)[0])

    def test_blank_line_ends_inline_code_paragraph(self):
        text = 'text `first\n\n<a id="old"></a>\nlast`'
        self.assertIn('old',v.anchors(text)[0])

    def test_hidden_heading_is_not_an_implicit_anchor(self):
        self.assertEqual(v.headings('text `first\n# Hidden\nlast`\n# Visible `code`'),
                         ['visible-code'])

    def test_span_mask_cannot_synthesize_link_or_anchor(self):
        self.assertEqual(v.markdown_targets('[x]`code`(#missing)'),[])
        self.assertNotIn('old',v.anchors('<`code`a id="old"></a>')[0])
        text = '<`code`a id="old"></a>\n[real](#old)'
        self.assertEqual(v.check_fragments('x.md',text,{'x.md':text.encode()}),
                         ['unresolved_fragment:#old'])

    def test_multiline_link_example_is_not_real_target(self):
        self.assertEqual(v.markdown_targets('text `first\n[x](#hidden)\nlast`'),[])


class CleanupProofTests(unittest.TestCase):
    """Exact reviewed cleanup is an additional proof, never a legacy-test replacement."""
    def current_content(self):
        root = HISTORY_ROOT
        return {n:(v.restore_anchor(n,(root/n).read_bytes()) if n in v.ANCHOR_FILES else (root/n).read_bytes())
                for n in v.CLEANUP_FILES}

    def test_all_nine_fixed_content_hashes_and_reconstruction(self):
        data = self.current_content()
        before = {n:v.restore_cleanup(n, raw) for n,raw in data.items()}
        restored = v.cleanup_content_proof(before, data)
        for path, contract in v.CLEANUP_FILES.items():
            self.assertEqual(v.digest(data[path]), contract['proposed_sha256'])
            self.assertEqual(v.digest(restored[path]), contract['before_sha256'])
        self.assertEqual(len(data),9)
        self.assertEqual(sum(r['removed_clickable_occurrences'] for r in v.CLEANUP_FILES.values()),73)
        self.assertEqual(len(v.ALLOWLIST),114)

    def test_unrelated_public_or_internal_link_removal_or_replacement_rejected(self):
        path = 'ai-factory/feature-lifecycle.md'
        raw = self.current_content()[path]
        # Actual accepted links, selected from the document itself; this does not
        # manufacture an absent target and mistake a no-op for a negative.
        links = v.markdown_targets(raw.decode())
        self.assertTrue(links)
        target = links[0]
        for new in [raw.decode().replace(']('+target+')',']',1),
                    raw.decode().replace(']('+target+')','](https://wrong.example/)',1),
                    raw.decode()+'\n[extra](https://wrong.example/)\n']:
            self.assertNotEqual(new.encode(),raw)
            with self.subTest(change=new[-80:]),self.assertRaisesRegex(ValueError,'cleanup proposed content'):
                v.restore_cleanup(path,new.encode())

    def test_narrative_or_retained_source_label_deletion_rejected(self):
        path='ai-factory/repo-evidence.md'; raw=self.current_content()[path]
        text=raw.decode()
        for fragment in ['generic-ui','QnA']:
            self.assertIn(fragment,text)
            changed=text.replace(fragment,'',1)
            with self.subTest(fragment=fragment),self.assertRaisesRegex(ValueError,'cleanup proposed content'):
                v.restore_cleanup(path,changed.encode())
        with self.assertRaisesRegex(ValueError,'cleanup proposed content'):
            v.restore_cleanup(path,'\n'.join(text.splitlines()[1:]).encode())

    def test_shell_suffix_flags_and_authorization_placeholder_rejected(self):
        path='ai-factory/roadmap.md';raw=self.current_content()[path]
        for old,new in [('claude mcp add','claude mcp remove'),
                        ('--transport http','--transport sse'),
                        ('Bearer <token>','Bearer replaced')]:
            self.assertIn(old,raw.decode())
            with self.subTest(delta=old),self.assertRaisesRegex(ValueError,'cleanup proposed content'):
                v.restore_cleanup(path,raw.replace(old.encode(),new.encode(),1))

    def test_false_historical_banner_rejected(self):
        for path in ['docs/translations/en/ai-factory/repo-evidence.md',
                     'docs/translations/en/docs/guides/obsidian-cheatsheet.md']:
            raw=self.current_content()[path]
            statement=b'The sealed original remains unchanged; the in-repository historical document has a separately recorded local-project reference cleanup.'
            self.assertIn(statement,raw)
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'cleanup proposed content'):
                v.restore_cleanup(path,raw.replace(statement,b'The current original remains unchanged.'))

    def test_wrong_original_baseline_rejected(self):
        data=self.current_content();before={n:v.restore_cleanup(n,raw) for n,raw in data.items()}
        for path,contract in v.CLEANUP_FILES.items():
            if contract['historical_original']:
                mutated=dict(before);mutated[path]+=b'changed original'
                with self.subTest(path=path),self.assertRaisesRegex(ValueError,'original baseline mismatch'):
                    v.cleanup_content_proof(mutated,data)

    def test_missing_cleanup_file_rejected(self):
        data=self.current_content();before={n:v.restore_cleanup(n,raw) for n,raw in data.items()}
        data.pop(next(iter(data)))
        with self.assertRaisesRegex(ValueError,'cleanup missing file'):
            v.cleanup_content_proof(before,data)

    def test_reconstruction_hunk_and_source_digest_are_independently_checked(self):
        import copy
        path='ai-factory/crg.md';raw=self.current_content()[path]
        contracts=copy.deepcopy(v.CLEANUP_FILES)
        contracts[path]['hunks'][0]['after']+='wrong'
        with patch.object(v,'CLEANUP_FILES',contracts),self.assertRaisesRegex(ValueError,'operation mismatch'):
            v.restore_cleanup(path,raw)
        contracts=copy.deepcopy(v.CLEANUP_FILES);contracts[path]['before_sha256']='0'*64
        with patch.object(v,'CLEANUP_FILES',contracts),self.assertRaisesRegex(ValueError,'reconstructed source mismatch'):
            v.restore_cleanup(path,raw)

    def metadata_fixture(self):
        """Small source-bound fixture, separate from real immutable baseline proof."""
        source='doc.md';target='../../projects/example/source.md'
        removed={'file':source,'target':target,'reason':'Historical attribution'}
        retained={'file':source,'target':'https://example.test/docs','reason':'Public documentation'}
        before={source:('[source]('+target+')\n[public](https://example.test/docs)\n').encode()}
        data={source:b'source\n[public](https://example.test/docs)\n'}
        contracts={}
        for path,key in [('provenance/link-exceptions.json','references'),('provenance/source-map.json','links')]:
            old={key:[removed,retained],'policy':'unchanged'};new={key:[retained],'policy':'unchanged'}
            before[path]=json.dumps(old).encode();data[path]=json.dumps(new).encode()
            contracts[path]={'key':key,'before_records_sha256':v.canonical_records_digest(old[key]),
                             'after_records_sha256':v.canonical_records_digest(new[key]),
                             'removed_records_sha256':v.canonical_records_digest([removed]),
                             'removed_records':1,'retained_records':1}
            if key=='references':contracts[path].update(before_sha256=v.digest(before[path]),proposed_sha256=v.digest(data[path]))
        return before,data,contracts

    def test_metadata_exact_deletion_and_canonicalization(self):
        before,data,contracts=self.metadata_fixture()
        with patch.object(v,'CLEANUP_FILES',{'doc.md':{}}),patch.object(v,'CLEANUP_METADATA',contracts):
            result=v.cleanup_metadata_proof(before,data)
        self.assertEqual(set(result),set(contracts))
        records=[{'z':'value','a':'literal'}]
        self.assertEqual(v.canonical_records_digest(records),hashlib.sha256(b'[{"a": "literal", "z": "value"}]').hexdigest())

    def test_extra_metadata_deletion_or_changed_record_rejected(self):
        before,data,contracts=self.metadata_fixture()
        for path,contract in contracts.items():
            for replacement in ([],[{'file':'doc.md','target':'https://changed.example/'}]):
                changed=dict(data);obj=json.loads(data[path]);obj[contract['key']]=replacement;changed[path]=json.dumps(obj).encode()
                with patch.object(v,'CLEANUP_FILES',{'doc.md':{}}),patch.object(v,'CLEANUP_METADATA',contracts),self.subTest(path=path),self.assertRaisesRegex(ValueError,'retained records mismatch'):
                    v.cleanup_metadata_proof(before,changed)

    def test_removed_digest_and_baseline_array_are_not_mutable_provenance(self):
        import copy
        before,data,contracts=self.metadata_fixture()
        for field in ['before_records_sha256','removed_records_sha256']:
            altered=copy.deepcopy(contracts);altered['provenance/link-exceptions.json'][field]='0'*64
            with patch.object(v,'CLEANUP_FILES',{'doc.md':{}}),patch.object(v,'CLEANUP_METADATA',altered),self.subTest(field=field),self.assertRaises(ValueError):
                v.cleanup_metadata_proof(before,data)

    def test_metadata_removal_requires_original_source_occurrence_and_removed_target(self):
        before,data,contracts=self.metadata_fixture()
        for old,new in [(b'no original link',data['doc.md']),
                        (before['doc.md'],before['doc.md'])]:
            source=dict(before);current=dict(data);source['doc.md']=old;current['doc.md']=new
            with patch.object(v,'CLEANUP_FILES',{'doc.md':{}}),patch.object(v,'CLEANUP_METADATA',contracts),self.subTest(old=old),self.assertRaisesRegex(ValueError,'occurrence|still present'):
                v.cleanup_metadata_proof(source,current)
        with patch.object(v,'CLEANUP_FILES',{}),patch.object(v,'CLEANUP_METADATA',contracts),self.assertRaisesRegex(ValueError,'outside content scope'):
            v.cleanup_metadata_proof(before,data)

    def test_cleanup_metadata_cannot_change_retained_policy(self):
        before,data,contracts=self.metadata_fixture();path='provenance/link-exceptions.json'
        changed=dict(data);obj=json.loads(data[path]);obj['policy']='weakened';changed[path]=json.dumps(obj).encode()
        with patch.object(v,'CLEANUP_FILES',{'doc.md':{}}),patch.object(v,'CLEANUP_METADATA',contracts),self.assertRaisesRegex(ValueError,'link exceptions bytes mismatch'):
            v.cleanup_metadata_proof(before,changed)


class AnchorNavigationTests(unittest.TestCase):
    def test_native_heading_code_literals_are_real_IDs(self):
        for heading in [history_literal('tests', 206, '681331f68e715882ea8cb0a9022658763d9081ed7c227bc0a4660b3e23286bfd'),history_literal('tests', 207, '34aec7eefe59b3dc857c1c6e8ea2e5ef3506eb6f3d837d851f1ee935322fad2d'),history_literal('tests', 208, 'af870719ce86b8c33d871c0d9a702f14d040928aa54d472d06e156ba414ae882')]:
            with self.subTest(heading=heading),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation(heading)
        self.assertIn('english-heading',v.current_navigation('## English heading')[0])

    def test_finding_angle_placeholder_regression(self):
        self.assertEqual(v.headings('### Finding: <short name>'),['finding'])
        self.assertIn('finding',v.current_navigation('### Finding: <short name>')[0])

    def test_raw_entity_and_percent_encoded_IDs_refused(self):
        for value in [history_literal('tests', 211, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),history_literal('tests', 212, '2c7c805d7a141cd9210f8aef69f8ae2e442742ede6c0f1e4d36b44b691dab6fe'),history_literal('tests', 213, '95d91ea1391493e366159b7dd817590287bb67391d2db9a1537b2572cf0e9534')]:
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation('<a id="'+value+'"></a>')
        with self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
            v.current_navigation(history_literal('tests', 593, 'a0e783988ca29ea9f6e137239739ae7bab5dfeb3c720131f30e9bb97dc9a63b1'))
        for heading in [history_literal('tests', 214, '7ff535ca82a19db1eb2216cdfcbdd9c050e2dc8b05618ade7a99dcab87f9bd6c'),history_literal('tests', 215, 'cdfbc8005a0c2a1dd95e229f5c7dcfaae7a1af70df597cc6185bf010fc095b2a')]:
            with self.subTest(heading=heading),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation(heading)

    def test_code_comments_do_not_create_navigation(self):
        text=history_literal('tests', 53, 'f7187a7e6dc5cf9729181601a2a34e04bcd8cf4598c718601ba6833af32f30c7')
        self.assertEqual(v.current_navigation(text)[0],{'english'})

    def test_unsupported_active_navigation_fails_closed(self):
        for text in ['[label]: #heading\n[label]', '<a href="#heading">label</a>',
                     'Setext heading\n==============', 'Setext heading\n--------------']:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'unsupported active'):
                v.current_navigation(text)

    def test_frontmatter_and_horizontal_rules_are_not_setext(self):
        text='---\nname: fixture\n---\n# Heading\n\n---\n\nText'
        self.assertEqual(v.current_navigation(text)[0],{'heading'})
        self.assertEqual(v.current_navigation(text.replace('\n','\r\n'))[0],{'heading'})

    def test_duplicate_heading_suffix_and_explicit_collision(self):
        self.assertEqual(v.current_navigation('# Same\n# Same')[0],{'same','same-1'})
        for text in ['# Same\n<a id="same"></a>', '<a id="x"></a>\n<div id="x"></div>']:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'current anchor collision'):
                v.current_navigation(text)

    def nav(self,data):
        with patch.object(v,'ANCHOR_FILES',{'a.md':{'removed_ids':[]}}),patch.object(v,'MAINTAINED_MARKDOWN',['a.md','b.md']),patch.object(v,'ANCHOR_EXCLUDED_MARKDOWN',[]):
            return v.current_tree_navigation_proof(data)

    def test_actual_cross_file_fragment_resolution(self):
        data={'a.md':b'# A\n[b](b.md#target)','b.md':b'# Target'}
        self.nav(data)
        for target in ['b.md#missing','missing.md#target','b.md#Target']:
            bad=dict(data);bad['a.md']=('# A\n[b]('+target+')').encode()
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'current fragment'):
                self.nav(bad)

    def test_current_fragment_cyrillic_and_encodings_refused(self):
        for fragment in [history_literal('tests', 227, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),history_literal('tests', 228, '95d91ea1391493e366159b7dd817590287bb67391d2db9a1537b2572cf0e9534'),history_literal('tests', 229, '2c7c805d7a141cd9210f8aef69f8ae2e442742ede6c0f1e4d36b44b691dab6fe')]:
            data={'a.md':('# A\n[b](b.md#'+fragment+')').encode(),'b.md':b'# Target'}
            with self.subTest(fragment=fragment),self.assertRaisesRegex(ValueError,'Cyrillic current internal fragment'):
                self.nav(data)

    def test_missing_or_extra_maintained_file_refused(self):
        for data in [{'a.md':b'# A'},{'a.md':b'# A','b.md':b'# B','c.md':b'# C'}]:
            with self.subTest(paths=list(data)),self.assertRaisesRegex(ValueError,'maintained Markdown inventory'):
                self.nav(data)

    def test_actual_tree_not_reconstructed_target_tree(self):
        data={'a.md':b'# A\n[b](b.md#old)','b.md':b'# New'}
        with self.assertRaisesRegex(ValueError,'current fragment unresolved'):
            self.nav(data)
        self.nav({'a.md':b'# A\n[b](b.md#new)','b.md':b'# New'})

    def test_malformed_navigation_escapes_refused(self):
        for value in ['bad%GG','bad%','%FF']:
            with self.subTest(value=value),self.assertRaises((ValueError,UnicodeError)):
                v.navigation_decode(value)


class AnchorContractTests(unittest.TestCase):
    def fixture(self):
        old=history_literal('tests', 55, '8aca012e0706db95bcf81108bff85af70050521415cb72864e99f62315351d83')
        new='# Review\n'
        literal={'text':history_literal('tests', 237, 'bb37d3d0b4af243fa8b14fa278483634a88c5691e4f1debf483f15b630b92ecd'),'reason':'Original compatibility heading'}
        row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(new.encode()),
             'removed_ids':[{'old_id':history_literal('tests', 817, '0e7777fe6175c42dc95b22c8b7037eb6560f3ba27ab5ee49b508eb8865b7336e'),'new_id':'review','binding':'Review'}],
             'changed_targets':[],'banner_changes':[],
             'hunks':[{'start':0,'end':0,'before':history_literal('tests', 824, '3ebc469282cb3edc2a32e0be9dab761a201e76b4d766130b9040b55b89b34d86'),'after':''}],
             'removed_preserved_literals':[{'index':0,'record':literal}],
             'pre_literals_sha256':v.canonical_records_digest([literal]),
             'current_literals_sha256':v.canonical_records_digest([])}
        data={'doc.md':new.encode()}
        provenance={'records':[{'path':'doc.md','preserved_literals':[]}],
                    'anchor_migration':{'pre_anchor_commit':v.ANCHOR_COMMIT,'pre_anchor_manifest_sha256':v.ANCHOR_MANIFEST,
                                        'files':[{k:x for k,x in row.items() if k!='hunks'}]}}
        return old,data,row,provenance

    def test_exact_inverse_and_source_bound_literal_reconstruction(self):
        old,data,row,provenance=self.fixture()
        with patch.object(v,'ANCHOR_FILES',{'doc.md':row}):
            self.assertEqual(v.anchor_content_proof(data)['doc.md'],old.encode())
            self.assertEqual(v.anchor_provenance_proof(data,provenance)['doc.md'],[row['removed_preserved_literals'][0]['record']])

    def test_current_prose_public_link_command_and_anchor_mutations_refused(self):
        old,data,row,provenance=self.fixture()
        for content in ['# Altered\n', '# Review\n[extra](https://example.test)', '# Review\n`danger`', old]:
            with patch.object(v,'ANCHOR_FILES',{'doc.md':row}),self.subTest(content=content),self.assertRaisesRegex(ValueError,'anchor current bytes mismatch'):
                v.anchor_content_proof({'doc.md':content.encode()})

    def test_missing_mapped_file_refused(self):
        old,data,row,provenance=self.fixture()
        with patch.object(v,'ANCHOR_FILES',{'doc.md':row,'second.md':row}),self.assertRaisesRegex(ValueError,'missing mapped file'):
            v.anchor_content_proof(data)

    def test_wrong_preanchor_pin_and_operation_refused(self):
        import copy
        old,data,row,provenance=self.fixture()
        for field,value in [('pre_anchor_sha256','0'*64),('hunks',[{'start':0,'end':0,'before':'wrong','after':'unexpected'}])]:
            changed=copy.deepcopy(row);changed[field]=value
            with patch.object(v,'ANCHOR_FILES',{'doc.md':changed}),self.subTest(field=field),self.assertRaisesRegex(ValueError,'anchor pre-source|anchor operation'):
                v.anchor_content_proof(data)

    def test_provenance_cannot_define_its_own_migration(self):
        import copy
        old,data,row,provenance=self.fixture()
        for mutate in [lambda p:p['anchor_migration'].update(pre_anchor_commit='0'*40),
                       lambda p:p['anchor_migration']['files'][0]['removed_ids'].clear(),
                       lambda p:p.pop('anchor_migration')]:
            changed=copy.deepcopy(provenance);mutate(changed)
            with patch.object(v,'ANCHOR_FILES',{'doc.md':row}),self.assertRaisesRegex(ValueError,'anchor provenance contract'):
                v.anchor_provenance_proof(data,changed)

    def test_stale_extra_or_changed_current_literal_refused(self):
        import copy
        old,data,row,provenance=self.fixture()
        for literals in [[row['removed_preserved_literals'][0]['record']],[{'text':'new','reason':'invented'}]]:
            changed=copy.deepcopy(provenance);changed['records'][0]['preserved_literals']=literals
            with patch.object(v,'ANCHOR_FILES',{'doc.md':row}),self.assertRaisesRegex(ValueError,'current literal inventory'):
                v.anchor_provenance_proof(data,changed)

    def test_original_literal_digest_checked_independently(self):
        old,data,row,provenance=self.fixture();row['pre_literals_sha256']='0'*64
        provenance['anchor_migration']['files'][0]['pre_literals_sha256']='0'*64
        with patch.object(v,'ANCHOR_FILES',{'doc.md':row}),self.assertRaisesRegex(ValueError,'original literal inventory'):
            v.anchor_provenance_proof(data,provenance)

    def test_out_of_range_literal_index_refused(self):
        old,data,row,provenance=self.fixture();row['removed_preserved_literals'][0]['index']=2
        with patch.object(v,'ANCHOR_FILES',{'doc.md':row}),self.assertRaisesRegex(ValueError,'literal removal index'):
            v.anchor_provenance_proof(data,provenance)




# Current-tree migration tests supplement, rather than replace, the 107 historical obligations.
class AuthenticatedHistoryTests(unittest.TestCase):
    def test_history_complete_closure_and_missing_input(self):
        self.assertEqual(len(v.load_history(HISTORY_ROOT)),489)
        result=v.verify(MODULE.parents[1],Path('/nonexistent'))
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['issues'],['history_baseline_required'])

    def test_literal_selector_and_hash_are_both_required(self):
        with self.assertRaises(ValueError):v.history_literal('unknown',0,'0'*64)
        with self.assertRaises(ValueError):v.history_literal('tests',-1,'0'*64)
        with self.assertRaises(ValueError):v.history_literal('tests',0,'0'*64)

    def test_historical_assignments_never_execute_code(self):
        for source in ['GUARD_TARGETS = danger()', 'GUARD_TARGETS = {}\nGUARD_TARGETS = {}', 'GUARD_TARGETS: dict = {}']:
            with self.assertRaises(ValueError):v.history_assignment(source,'GUARD_TARGETS')
        with self.assertRaises(ValueError):v.history_assignment('other = {}','other')

    def test_language_audit_checks_decoded_and_raw_historical_probe(self):
        probe=next(value for value in v.HISTORY_LITERALS['tests'] if v.CYRILLIC.search(value))
        for value in [probe, json.dumps(probe,ensure_ascii=True), ''.join('&#'+str(ord(c))+';' for c in probe)]:
            with self.assertRaisesRegex(ValueError,'current language'):
                v.current_language_proof({'probe.md':value.encode()}, {})
        v.current_language_proof({'probe.md':'English café naive'.encode()}, {})

    def test_unknown_binary_and_encoded_path_rejected(self):
        with self.assertRaisesRegex(ValueError,'binary'):
            v.current_language_proof({'unknown.bin':b'\xff'}, {})
        probe=next(value for value in v.HISTORY_LITERALS['tests'] if v.CYRILLIC.search(value))
        with self.assertRaisesRegex(ValueError,'language path'):
            v.current_language_proof({probe:b'English'}, {})

    def test_wrong_history_manifest_and_payload_are_not_rebased(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'history';shutil.copytree(HISTORY_ROOT,root)
            name='README.md';(root/name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'payload mismatch'):v.load_history(root)
            manifest=json.loads((root/'release-manifest.json').read_text())
            for row in manifest['files']:
                if row['path']==name:row['sha256']=v.digest(b'changed')
            (root/'release-manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'manifest identity'):v.load_history(root)

    def test_history_archive_extras_are_authenticated(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'history';shutil.copytree(HISTORY_ROOT,root)
            name=next(iter(json.loads((root/'provenance/research-archive.json').read_text())['files']))
            (root/name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'archive mismatch'):v.load_history(root)

class CurrentResidualProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=MODULE.parents[1]
        cls.original=Path(os.environ['AI_FACTORY_TRANSLATION_BASELINE'])
        cls.history=v.load_history(HISTORY_ROOT)
        cls.data={name:v.regular(cls.root,name) for name in v.inventory(cls.root)}
        cls.archive=set(json.loads(cls.history['provenance/research-archive.json'])['files'])
        cls.source_data=dict(cls.data)
        cls.source_data.update({name:cls.history[name] for name in cls.archive})
        cls.distribution_data={name:raw for name,raw in cls.source_data.items() if name not in cls.archive}

    def package(self,data):
        data=dict(data);manifest=json.loads(data['release-manifest.json'])
        for row in manifest['files']:row['sha256']=v.digest(data[row['path']])
        data['release-manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
        checks={row['path']:row['sha256'] for row in manifest['files']}
        checks['release-manifest.json']=v.digest(data['release-manifest.json'])
        data['checksums.sha256']=''.join(checks[name]+'  '+name+'\n' for name in sorted(checks)).encode()
        return data

    def run_tree(self,data):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw in data.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            return v.verify(root,self.original,HISTORY_ROOT)

    def test_complete_current_tree_and_all_skills(self):
        result=v.verify(self.root,self.original,HISTORY_ROOT)
        self.assertEqual(result['status'],'PASS',result['issues'])
        self.assertEqual(result['current_language'],'PASS')
        self.assertEqual(len(result['skills']),74)
        self.assertEqual(result['current_files'],len(self.data))
        self.assertEqual(result['current_inventory_mode'],'source' if len(self.data)==490 else 'distribution')

    def test_changed_current_content_cannot_rebless_its_manifest(self):
        data=dict(self.data);data['README.md']+=b'\nUnreviewed English edit.\n'
        result=self.run_tree(self.package(data))
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('residual content binding:README.md',result['issues'][0])

    def test_contract_identity_and_undeclared_fields_are_rejected(self):
        data=dict(self.data);contract=json.loads(data[v.CONTRACT_PATH]);contract['invented']='not authorized'
        data[v.CONTRACT_PATH]=json.dumps(contract).encode()
        result=self.run_tree(self.package(data));self.assertEqual(result['status'],'FAIL')
        self.assertIn('contract identity',result['issues'][0])
        # Independent schema check even when an isolated fixture pins new bytes.
        with patch.object(v,'CONTRACT_SHA256',v.digest(data[v.CONTRACT_PATH])):
            result=self.run_tree(self.package(data));self.assertEqual(result['status'],'FAIL')
            self.assertIn('contract schema',result['issues'][0])

    def test_omitted_and_swapped_historical_commitments_rejected(self):
        name='provenance/english-translations.json'
        for operation in ('remove','swap'):
            data=dict(self.data);meta=json.loads(data[name])
            row=next(row for row in meta['records'] if len(row['historical_literals']['records'])>1)
            records=row['historical_literals']['records']
            if operation=='remove':records.pop()
            else:records[0],records[1]=records[1],records[0]
            data[name]=json.dumps(meta).encode()
            result=self.run_tree(self.package(data));self.assertEqual(result['status'],'FAIL')
            self.assertIn('residual metadata projection',result['issues'][0])

    def test_original_source_identity_cannot_be_rewritten(self):
        name='provenance/english-translations.json';data=dict(self.data);meta=json.loads(data[name])
        meta['records'][0]['base_sha256']='0'*64;data[name]=json.dumps(meta).encode()
        result=self.run_tree(self.package(data));self.assertEqual(result['status'],'FAIL')
        self.assertIn('residual metadata projection',result['issues'][0])

    def test_frozen_file_and_extra_file_are_rejected(self):
        for name,raw in [('AGENTS.md',self.data['AGENTS.md']+b'\nChanged.'),('extra.txt',b'Unexpected')]:
            data=dict(self.data);data[name]=raw
            result=self.run_tree(self.package(data));self.assertEqual(result['status'],'FAIL')
            self.assertIn('residual',result['issues'][0])

    def test_current_language_gate_is_wired_before_history_restoration(self):
        probe=next(value for value in v.HISTORY_LITERALS['tests'] if v.CYRILLIC.search(value) and value.isalpha() and len(value)<12)
        data=dict(self.data);data['README.md']+=('\n'+probe+'\n').encode();data=self.package(data)
        # Neutralize only the independent exact-byte inverse gate to isolate language.
        with patch.object(v,'residual_content_proof',lambda current,history:dict(history)):
            result=self.run_tree(data);self.assertEqual(result['status'],'FAIL')
            self.assertIn('current language text:README.md',result['issues'][0])
            # This is the targeted guard-removal mutant: expected language rejection disappears.
            with patch.object(v,'current_language_proof',lambda current,history:None):
                mutant=self.run_tree(data);self.assertEqual(mutant['status'],'PASS',mutant['issues'])

    def test_contract_gate_is_wired_before_history_restoration(self):
        data=dict(self.data);data['README.md']+=b'\nUnreviewed English edit.\n';data=self.package(data)
        result=self.run_tree(data);self.assertEqual(result['status'],'FAIL')
        self.assertIn('residual content binding',result['issues'][0])
        with patch.object(v,'residual_content_proof',lambda current,history:dict(history)):
            mutant=self.run_tree(data);self.assertEqual(mutant['status'],'PASS',mutant['issues'])

    def test_wrong_history_blocks_complete_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            result=v.verify(self.root,self.original,Path(directory))
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['issues'],['history_unavailable_or_invalid'])

    def test_byte_and_named_escape_values_are_scanned(self):
        probe=next(value for value in v.HISTORY_LITERALS['tests'] if v.CYRILLIC.search(value) and value.isalpha() and len(value)<12)
        import unicodedata
        byte_source=('value = '+repr(probe.encode())).encode()
        named=''.join('\\'+'N{'+unicodedata.name(c)+'}' for c in probe)
        for data in [{'probe.py':byte_source},{'probe.txt':named.encode()}]:
            with self.assertRaisesRegex(ValueError,'current language'):
                v.current_language_proof(data,{})

    def test_exact_distribution_full_proof_passes(self):
        result=self.run_tree(self.distribution_data)
        self.assertEqual(result['status'],'PASS',result['issues'])
        self.assertEqual(result['current_inventory_mode'],'distribution')
        self.assertEqual(result['current_files'],460)
        self.assertEqual(len(result['skills']),74)
        source=self.run_tree(self.source_data)
        self.assertEqual(source['status'],'PASS',source['issues'])
        self.assertEqual(source['current_inventory_mode'],'source')
        self.assertEqual(source['current_files'],490)

    def test_partial_archive_deletion_is_not_distribution(self):
        data=dict(self.source_data);data.pop(sorted(self.archive)[0])
        with self.assertRaisesRegex(ValueError,'residual current inventory'):
            v.current_inventory_mode(data,self.history)
        self.assertEqual(self.run_tree(data)['status'],'FAIL')

    def test_distribution_missing_ordinary_payload_is_refused(self):
        data=dict(self.distribution_data);data.pop('README.md')
        with self.assertRaisesRegex(ValueError,'residual current inventory'):
            v.current_inventory_mode(data,self.history)
        self.assertEqual(self.run_tree(data)['status'],'FAIL')

    def test_source_changed_archive_is_refused(self):
        data=dict(self.source_data);name=next(name for name in sorted(self.archive) if name.endswith('.md'));data[name]+=b'\nUnreviewed archive edit.\n'
        result=self.run_tree(data);self.assertEqual(result['status'],'FAIL')
        self.assertIn('residual unchanged file:',result['issues'][0])


if __name__ == '__main__':
    unittest.main()
