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
        result = v.verify(self.root, self.root/'absent')
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
        old = '---\nname: x\ndescription: Опис\nlicense: MIT\n---\nbody\n'
        new = old.replace('Опис', 'Description')
        self.assertEqual(v.description_parts(old), v.description_parts(new))
        self.assertNotEqual(v.description_parts(old), v.description_parts(new.replace('body','changed')))
        self.assertNotEqual(v.description_parts(old), v.description_parts(new.replace('MIT','Other')))

    def test_exact_alias_preserved(self):
        old = '---\nname: x\ndescription: Use "менше коду"\n---\nBody\n'
        new = '---\nname: x\ndescription: Use less code. Ukrainian compatibility alias "менше коду"\n---\nBody\n'
        v.english_coverage(old, new, [{'text':'менше коду','reason':'Original user trigger'}])
        with self.assertRaisesRegex(ValueError, 'missing original trigger'):
            v.english_coverage(old, new.replace('менше коду','less code'), [])

    def test_no_blanket_cyrillic_prose_exception(self):
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage('Залиш увесь текст.', 'Залиш увесь текст.',
                               [{'text':'Залиш увесь текст.','reason':'ignore all'}])

    def test_missing_translation_fails(self):
        with self.assertRaisesRegex(ValueError, 'undeclared Cyrillic'):
            v.english_coverage('Опис', 'Опис', [])

    def test_yaml_outer_quotes_are_not_trigger_aliases(self):
        old = '---\nname: x\ndescription: "Перевіряє зміни."\n---\nBody\n'
        v.english_coverage(old, old.replace('Перевіряє зміни.', 'Reviews changes.'), [])
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage(old, old, [{'text':'Перевіряє зміни.','reason':'wrong outer-quote exemption'}])

    def test_descriptive_quote_is_not_mistaken_for_trigger(self):
        old = '---\nname: x\ndescription: Опиши «як працює» або на тригери "приймальні критерії".\n---\nBody\n'
        new = '---\nname: x\ndescription: Describe how it works; compatibility trigger "приймальні критерії".\n---\nBody\n'
        v.english_coverage(old,new,[{'text':'приймальні критерії','reason':'Exact trigger'}])
        with self.assertRaisesRegex(ValueError,'missing original trigger'):
            v.english_coverage(old,new.replace('приймальні критерії','acceptance'),[])

    def test_original_link_fragment_and_numbered_id_are_data(self):
        old = '[next](review.md#перед-початком) Section 5а'
        new = '[next](review.md#перед-початком) Historical section ID 5а'
        literals = [{'text':'review.md#перед-початком','reason':'Original target'},
                    {'text':'5а','reason':'Original section identifier'}]
        v.english_coverage(old,new,literals)
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,new+' довільна проза',literals+[{'text':'довільна проза','reason':'not data'}])

    def test_fake_alias_cannot_be_added(self):
        with self.assertRaisesRegex(ValueError, 'unjustified'):
            v.english_coverage('Use "менше коду"', 'Alias "інше"',
                               [{'text':'інше','reason':'invented'}])


class AnchorAndTokenTests(unittest.TestCase):
    def test_duplicate_heading_suffix_and_percent_encoded_fragment(self):
        text = '# Test\n# Test\n<a id="огляд"></a>\n[second](#test-1)\n[old](#%D0%BE%D0%B3%D0%BB%D1%8F%D0%B4)\n'
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
        v.english_coverage('# Огляд\n', '<a id="огляд"></a>\n# Review\n',
                           [{'text':'<a id="огляд"></a>','reason':'Original heading fragment'}])

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
        for char in ('\u2de0','\ua640','\u1c80'):
            with self.subTest(char=char):
                with self.assertRaisesRegex(ValueError,'Cyrillic'):
                    v.english_coverage('Original',char,[])


class RefusalBoundaryTests(unittest.TestCase):
    def test_only_plain_echo_display_text_translation_allowed(self):
        old='```bash\necho "Привіт"\n```\n'
        v.machine_blocks_proof(old,'```bash\necho "Hello"\n```\n')
        for new in ['```bash\nrm -rf target\n```\n',
                    '```bash\necho "$(danger)"\n```\n',
                    '```bash\necho -n "Hello"\n```\n']:
            with self.subTest(new=new):
                with self.assertRaises(ValueError): v.machine_blocks_proof(old,new)

    def test_json_machine_keys_and_enums_frozen_on_cyrillic_line(self):
        old='```json\n{"label":"Приклад","state":"READY"}\n```\n'
        for new in [old.replace('state','status'),old.replace('READY','BLOCKED'),old.replace('Приклад','Example')]:
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
        for char in ('\ufe2e','\U0001e030'):
            with self.assertRaisesRegex(ValueError,'Cyrillic'):
                v.english_coverage('old',char,[])


class CompleteVerificationTests(unittest.TestCase):
    """Synthetic complete-tree proof of the real verify/main path, not real-baseline evidence."""
    def setUp(self):
        import shutil
        self.temp=tempfile.TemporaryDirectory(); self.home=Path(self.temp.name)
        self.base=self.home/'baseline'; self.root=self.home/'current';self.base.mkdir();self.root.mkdir()
        self.before={'doc.md':b'# \xd0\x9e\xd0\xb3\xd0\xbb\xd1\x8f\xd0\xb4\n[jump](#\xd0\xbe\xd0\xb3\xd0\xbb\xd1\x8f\xd0\xb4)\n```bash\necho "\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd1\x96\xd1\x82"\n```\n',
                     'history.md':'# Давній\nHistorical baseline.\n'.encode(),
                     'frozen.py':b'VALUE = 1\n',
                     'LICENSE.txt':b'Original notice\n',
                     'tests/unicode.py':'NAME = "огляд"\n'.encode(),
                     'provenance/research-archive.json':b'{"files":{}}'}
        for i in range(74):
            self.before[f'skills/s{i}/SKILL.md']=f'---\nname: s{i}\ndescription: English\n---\nBody {i}\n'.encode()
        self.skill='skills/s0/SKILL.md';self.before[self.skill]='---\nname: s0\ndescription: Опис\n---\nBody 0\n'.encode()
        self.guard='runtime/session-size-docker/guard.py'; oldguard,newguard=GuardTests().sources()
        self.before[self.guard]=oldguard.encode()
        for n in ('source-map.json','layout-migration.json','authorized-additions.json'):
            self.before['provenance/'+n]=json.dumps({'files':[],'adaptations':[]}).encode()
        self.write(self.base,self.before);self.seal(self.base)
        self.pin=v.digest((self.base/'release-manifest.json').read_bytes())
        shutil.copytree(self.base,self.root,dirs_exist_ok=True)
        self.changed={'doc.md':'<a id="огляд"></a>\n# Review\n[jump](#огляд)\n```bash\necho "Hello"\n```\n'.encode(),
                      self.skill:self.before[self.skill].replace('Опис'.encode(),b'Description'),
                      self.guard:newguard.encode()}
        self.history='docs/translations/en/history.md'
        self.changed[self.history]=(f'Historical translation of history.md; {v.digest(self.before["history.md"])}; {v.BASE_COMMIT}\n<a id="давній"></a>\n# Ancient\nHistorical baseline.\n').encode()
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
            if n=='doc.md': literals=[{'text':'<a id="огляд"></a>','reason':'original heading'},{'text':'огляд','reason':'original fragment'}]
            if n==self.history: literals=[{'text':'<a id="давній"></a>','reason':'original heading'}]
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

    def result(self):return v.verify(self.root,self.base)

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
        for changed in [raw.replace('echo "Hello"','rm -rf target'),raw.replace('<a id="огляд"></a>','```text\n<a id="огляд"></a>\n```')]:
            self.corrupt('doc.md',changed)
            self.assertEqual(self.result()['status'],'FAIL')
        self.corrupt('doc.md',raw)

    def test_multiline_hidden_anchor_refused_by_complete_verify(self):
        raw = (self.root/'doc.md').read_text()
        self.corrupt('doc.md',raw.replace('<a id="огляд"></a>',
                     'text `first\n<a id="огляд"></a>\nlast`'))
        result = self.result()
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('lost heading compatibility anchor:doc.md',result['issues'])

    def test_code_removal_cannot_synthesize_anchor_in_complete_verify(self):
        raw = (self.root/'doc.md').read_text()
        self.corrupt('doc.md',raw.replace('<a id="огляд"></a>',
                     '<`code`a id="огляд"></a>'))
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
        current=old.replace('<a id="огляд"></a>\n','').replace('#огляд)','#review)')
        prior=copy.deepcopy(self.records[0]['preserved_literals'])
        contracts={}
        def install(text):
            hunks=[{'start':j1,'end':j2,'before':old[i1:i2],'after':text[j1:j2]}
                   for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old,b=text,autojunk=False).get_opcodes() if tag!='equal']
            row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(text.encode()),
                 'removed_ids':[{'old_id':'огляд','new_id':'review','binding':'Review'}],
                 'changed_targets':[{'old_target':'#огляд','new_target':'#review','count':1}],
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
        current=old.replace('<a id="огляд"></a>\n','').replace('#огляд)','#review)')
        contracts={}
        def install(text):
            hunks=[{'start':j1,'end':j2,'before':old[i1:i2],'after':text[j1:j2]}
                   for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old,b=text,autojunk=False).get_opcodes() if tag!='equal']
            retained=[prior[1]]  # The exact original literal survives as body data.
            row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(text.encode()),
                 'removed_ids':[{'old_id':'огляд','new_id':'review','binding':'Review'}],
                 'changed_targets':[{'old_target':'#огляд','new_target':'#review','count':1}],
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
            install(current+'\nOriginal fragment literal: `огляд`\n')
            self.assertEqual(self.result()['status'],'PASS',self.result()['issues'])
            install(current+'\n## Example `огляд`\n')
            # Pins, inverse, current declared literals and payload all agree; only
            # the current navigation location changes this permitted data to an ID.
            self.assertEqual(self.result()['status'],'FAIL')

    def test_cli_exit_receipt_uses_real_verifier(self):
        import contextlib,io
        args=['verify_translation','--root',str(self.root),'--baseline',str(self.base)]
        stream=io.StringIO()
        with patch('sys.argv',args),contextlib.redirect_stdout(stream):
            self.assertEqual(v.main(),0)
        self.assertEqual(json.loads(stream.getvalue())['status'],'PASS')
        self.corrupt('frozen.py','changed');stream=io.StringIO()
        with patch('sys.argv',args),contextlib.redirect_stdout(stream):
            self.assertEqual(v.main(),1)
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
        source=inspect.getsource(v.verify);original=v.verify
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
            v.verify=original

    def test_anchor_full_tree_enforcement_has_attributable_mutation_kills(self):
        import inspect
        source=inspect.getsource(v.verify);original=v.verify
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
                    v.verify=original

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
        source=inspect.getsource(v.verify); original=v.verify
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
                    v.verify=original




class RealTreeRegressionTests(unittest.TestCase):
    def test_external_rebase_preserves_exact_destination(self):
        v.historical_targets('ai-factory/a.md','docs/translations/en/ai-factory/a.md',
                             '[x](../../projects/a.md)', '[x](../../../../../projects/a.md)')
        with self.assertRaises(ValueError):
            v.historical_targets('ai-factory/a.md','docs/translations/en/ai-factory/a.md',
                                 '[x](../../projects/a.md)', '[x](../../../../../projects/b.md)')

    def test_inline_shell_comments_do_not_authorize_command_changes(self):
        old = '```bash\npip install package  # встановлення\n```\n'
        v.machine_blocks_proof(old,old.replace('встановлення','installation'))
        for candidate in (old.replace('pip install','pip uninstall').replace('встановлення','installation'),
                          old.replace('package','other').replace('встановлення','installation')):
            with self.assertRaises(ValueError): v.machine_blocks_proof(old,candidate)
        with self.assertRaises(ValueError):
            v.machine_blocks_proof('```bash\nrun "# дані"\n```','```bash\nrun "# data"\n```')

    def test_exact_skill_example_description_not_yaml_machine_values(self):
        old = '```yaml\n  ---\n  name: skill-name\n  description: Опис\n  ---\n```\n'
        new = old.replace('Опис','Description')
        v.machine_blocks_proof(old,new)
        for candidate in (new.replace('skill-name','other'), new.replace('description:','permission:')):
            with self.assertRaises(ValueError): v.machine_blocks_proof(old,candidate)
        with self.assertRaises(ValueError):
            v.machine_blocks_proof('```yaml\nmode: опис\n```','```yaml\nmode: description\n```')

    def test_single_quoted_description_not_blanket_exception(self):
        old = "---\nname: x\ndescription: 'Перевіряє інтерфейс.'\n---\nBody\n"
        v.english_coverage(old,old.replace('Перевіряє інтерфейс.','Reviews the interface.'),[])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,old,[{'text':'Перевіряє інтерфейс.','reason':'not an alias'}])

    def test_post_trigger_explanation_is_translatable(self):
        old = '---\nname: x\ndescription: >\n  Коли питають "покажи ефект", або на тригер\n  /gain. Ніколи не рахує «економію».\n---\nBody\n'
        new = '---\nname: x\ndescription: Show effect; alias "покажи ефект"; /gain. Never infer savings.\n---\nBody\n'
        v.english_coverage(old,new,[{'text':'покажи ефект','reason':'Exact request'}])
        with self.assertRaisesRegex(ValueError,'missing original trigger'):
            v.english_coverage(old,new.replace('покажи ефект','show effect'),[])

    def test_protocol_labels_and_code_placeholders_are_source_bound(self):
        old = '- ФАКТ: відомості\n`<дім артефактів>/_agent-<роль>.md`'
        new = '- ФАКТ: facts\nArtifact root: <дім артефактів>'
        v.english_coverage(old,new,[{'text':'ФАКТ:','reason':'Protocol label'},
                                   {'text':'<дім артефактів>','reason':'Original placeholder'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage('довільний текст','довільний текст',
                               [{'text':'довільний текст','reason':'not protocol data'}])

    def test_cyrillic_angle_placeholder_is_not_html_tag(self):
        self.assertEqual(v.headings('### Знахідка: <коротка назва>'), ['знахідка-коротка-назва'])
        self.assertEqual(v.headings('### Finding <span>title</span>'), ['finding-title'])


class FrontmatterIdentifierTests(unittest.TestCase):
    def test_original_key_is_data_but_value_is_not(self):
        old = '---\nрозкладка: локальна структура\n---\nBody'
        new = '---\nрозкладка: local layout\n---\nBody'
        v.english_coverage(old,new,[{'text':'розкладка','reason':'Original frontmatter key'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,old,[{'text':'розкладка','reason':'Key'},
                                       {'text':'локальна структура','reason':'Not a key'}])
        with self.assertRaisesRegex(ValueError,'unjustified'):
            v.english_coverage(old,new.replace('розкладка','нова'),
                               [{'text':'нова','reason':'Invented key'}])

    def test_first_protocol_slash_label_is_supported(self):
        old = 'ФАКТ / РІШЕННЯ / ДАЛІ / ПИТАННЯ'
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
        root = MODULE.parents[1]
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
        for heading in ['## `Мірник`','## ` /команда ` — English label','## Cyrillic `слово`']:
            with self.subTest(heading=heading),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation(heading)
        self.assertIn('english-heading',v.current_navigation('## English heading')[0])

    def test_finding_angle_placeholder_regression(self):
        self.assertEqual(v.headings('### Finding: <short name>'),['finding'])
        self.assertIn('finding',v.current_navigation('### Finding: <short name>')[0])

    def test_raw_entity_and_percent_encoded_IDs_refused(self):
        for value in ['огляд','&#1086;&#1075;&#1083;&#1103;&#1076;','%D0%BE%D0%B3%D0%BB%D1%8F%D0%B4']:
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation('<a id="'+value+'"></a>')
        with self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
            v.current_navigation('<section id="огляд">Text</section>')
        for heading in ['# &#1086;&#1075;&#1083;&#1103;&#1076;','# `%D0%BE%D0%B3%D0%BB%D1%8F%D0%B4`']:
            with self.subTest(heading=heading),self.assertRaisesRegex(ValueError,'Cyrillic current section ID'):
                v.current_navigation(heading)

    def test_code_comments_do_not_create_navigation(self):
        text='```html\n<a id="огляд"></a>\n```\n<!-- <a id="огляд"></a> -->\n`<a id="огляд"></a>`\n# English'
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
        for fragment in ['огляд','%D0%BE%D0%B3%D0%BB%D1%8F%D0%B4','&#1086;&#1075;&#1083;&#1103;&#1076;']:
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
        old='<a id="огляд"></a>\n# Review\n'
        new='# Review\n'
        literal={'text':'<a id="огляд"></a>','reason':'Original compatibility heading'}
        row={'path':'doc.md','pre_anchor_sha256':v.digest(old.encode()),'current_sha256':v.digest(new.encode()),
             'removed_ids':[{'old_id':'огляд','new_id':'review','binding':'Review'}],
             'changed_targets':[],'banner_changes':[],
             'hunks':[{'start':0,'end':0,'before':'<a id="огляд"></a>\n','after':''}],
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


if __name__ == '__main__':
    unittest.main()
