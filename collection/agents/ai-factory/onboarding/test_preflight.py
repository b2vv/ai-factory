import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from preflight import inspect, safe_path, route, load_manifest


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, name, content=''):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_clean_new_repository(self):
        result = inspect(self.root, {})
        self.assertTrue(result['read_only'])
        self.assertEqual(result['commands_executed'], 0)
        self.assertFalse(result['instructions'][0]['detected'])
        self.assertEqual(result['routing']['primary_task_records'], 1)

    def test_partial_existing_rules_configurable_paths(self):
        self.write('custom/RULES.md', 'Local contracts govern acceptance')
        self.write('planning/tasks.md')
        result = inspect(self.root, {'instructions': ['custom/RULES.md'], 'workflow': ['planning/tasks.md']})
        self.assertTrue(result['instructions'][0]['detected'])
        self.assertTrue(result['workflow'][0]['detected'])
        self.assertFalse(result['instructions'][0]['configured'])
        self.assertFalse(result['instructions'][0]['behavior_tested'])

    def test_missing_shared_skill(self):
        result = inspect(self.root, {'skills': [{'name': 'pattern-review', 'source': 'shared', 'path': 'pattern-review/SKILL.md'}]})
        self.assertEqual(result['skills'][0]['status'], 'BLOCKED')

    def test_explicit_shared_skill_root_only(self):
        with tempfile.TemporaryDirectory() as shared:
            Path(shared, 'SKILL.md').write_text('fixture')
            result = inspect(self.root, {'skills': [{'name': 'fixture', 'source': 'shared', 'path': 'SKILL.md'}]}, shared)
            self.assertTrue(result['skills'][0]['detected'])
            self.assertFalse(result['skills'][0]['behavior_tested'])

    def test_declared_contract_code_conflict(self):
        result = inspect(self.root, {'conflicts': [{'id': 'acceptance-v-code'}]})
        self.assertEqual(result['declared_conflicts'][0]['status'], 'BLOCKED')
        self.assertIn('does not authorize', result['declared_conflicts'][0]['reason'])

    def test_stale_and_unavailable_crg(self):
        for declaration in ({'declared_freshness': 'stale'}, {'declared_availability': 'unavailable'}):
            result = inspect(self.root, {'integrations': [dict(name='crg', **declaration)]})
            self.assertEqual(result['integrations'][0]['status'], 'BLOCKED')

    def test_config_file_is_not_runtime_evidence(self):
        self.write('.mcp.json', 'NOT JSON; MUST NOT BE READ')
        result = inspect(self.root, {'integrations': [{'name': 'crg', 'config_paths': ['.mcp.json'], 'declared_availability': 'available', 'declared_freshness': 'fresh'}]})
        integration = result['integrations'][0]
        self.assertTrue(integration['detected'])
        self.assertEqual(integration['status'], 'UNKNOWN')
        self.assertFalse(integration['configured'])
        self.assertFalse(integration['behavior_tested'])

    def test_small_test_helper_routes_pattern(self):
        result = route({'mode': 'small', 'test_helper': True})
        self.assertEqual(result['pattern_review'], 'ASSESS')
        self.assertEqual(result['primary_task_records'], 1)
        self.assertIn('required repo gates', result['checks'])

    def test_ui_copy_is_not_automatic_na(self):
        self.assertTrue(route({'ui_copy': True})['ui_design'].startswith('ASSESS'))

    def test_plain_docs_typo_does_not_force_pattern(self):
        self.assertTrue(route({})['pattern_review'].startswith('N/A'))

    def test_duplicate_completed_handoff(self):
        result = route({'completed_handoff': True})
        self.assertEqual(result['mode'], 'resume_verify_completion')
        self.assertIn('do not duplicate', result['resume'])

    def test_reject_paths(self):
        for path in ('../outside', '/tmp/outside', '.env', '.env.local', '.envrc', '.envprod', 'credentials.json', '.aws/config', '.ssh/config', '.git/config'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(self.root, path)

    def test_reject_symlink_and_parent_symlink(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                safe_path(self.root, 'escape/package.json')
        self.write('actual.md')
        (self.root / 'link.md').symlink_to(self.root / 'actual.md')
        with self.assertRaises(ValueError):
            safe_path(self.root, 'link.md')

    def test_command_inventory_no_execution_or_value_output(self):
        command = 'rm -rf important && echo DO_NOT_LEAK'
        self.write('package.json', json.dumps({'scripts': {'reset': command}}))
        result = inspect(self.root, {})
        self.assertEqual(result['commands'][0]['name'], 'reset')
        self.assertIn('deletion', result['commands'][0]['side_effect_indicators'])
        self.assertNotIn('DO_NOT_LEAK', json.dumps(result))
        self.assertEqual(result['commands_executed'], 0)

    def test_negative_no_effect_matches_does_not_mean_safe(self):
        self.write('package.json', json.dumps({'scripts': {'verify': 'node opaque.js'}}))
        result = inspect(self.root, {})
        self.assertEqual(result['commands'][0]['status'], 'UNKNOWN')
        self.assertIn('No command is certified safe', result['commands'][0]['reason'])

    def test_make_prerequisite_effects_need_manual_review(self):
        self.write('Makefile', 'check: reset\n\ttool verify\nreset:\n\tdocker compose down -v\n')
        result = inspect(self.root, {})
        self.assertEqual(result['commands'][0]['name'], 'check')
        self.assertIn('services_or_containers', result['commands'][0]['side_effect_indicators'])

    def test_invalid_command_json_is_blocked(self):
        self.write('package.json', '{invalid')
        self.assertEqual(inspect(self.root, {})['commands'][0]['status'], 'BLOCKED')

    def test_inventory_does_not_change_files(self):
        path = self.write('package.json', '{}')
        before = path.read_bytes()
        inspect(self.root, {})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['package.json'])

    def test_manifest_typo_or_false_string_rejected(self):
        for manifest in ({'scop': {}}, {'scope': {'test_helper': 'false'}}, {'skills': 'not-a-list'}, {'integrations': [{'name': 'crg', 'declared_freshness': 'probably'}]}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                inspect(self.root, manifest)

    def test_invalid_package_shape_blocked(self):
        for value in ([], {'scripts': []}, {'scripts': {'check': 3}}):
            self.write('package.json', json.dumps(value))
            self.assertEqual(inspect(self.root, {})['commands'][0]['status'], 'BLOCKED')

    def test_external_manifest_does_not_require_repo_write(self):
        with tempfile.TemporaryDirectory() as external:
            manifest = Path(external).resolve() / 'manifest.json'
            manifest.write_text('{"instructions":["AGENTS.md"]}')
            result = inspect(self.root, load_manifest(self.root, str(manifest)))
            self.assertFalse(result['instructions'][0]['detected'])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_external_manifest_does_not_grant_external_inventory(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external).resolve()
            manifest = outside / 'manifest.json'
            manifest.write_text(json.dumps({'instructions': [str(outside / 'AGENTS.md')]}))
            result = inspect(self.root, load_manifest(self.root, str(manifest)))
            self.assertEqual(result['instructions'][0]['status'], 'BLOCKED')

    def test_external_manifest_secrets_symlinks_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external).resolve()
            real = outside / 'manifest.json'
            real.write_text('{}')
            alias = outside / 'alias.json'
            alias.symlink_to(real)
            private = outside / '.env.json'
            private.write_text('{}')
            directory_alias = outside / 'alias-dir'
            directory_alias.symlink_to(outside, target_is_directory=True)
            for candidate in (alias, private, directory_alias / 'manifest.json', outside / '..' / outside.name / 'manifest.json'):
                with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                    load_manifest(self.root, str(candidate))

    def test_external_env_prefix_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external).resolve()
            for name in ('.envrc', '.envprod'):
                manifest = outside / name
                manifest.write_text('{}')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    load_manifest(self.root, str(manifest))

    def host(self, **extra):
        return dict(host='codex-local', session='fixture-1', **extra)

    def test_discovery_independent_of_native_tools_and_file_presence(self):
        result = inspect(self.root, {'hosts': [self.host(discovered_skills=['fixture'], discovery_evidence='session inventory', native_tools=[])]})
        host = result['hosts'][0]
        self.assertEqual(host['discovery'], 'DECLARED')
        self.assertEqual(host['declared_native_tools'], [])
        self.assertEqual(host['invocation'], 'NOT_TESTED')
        self.assertEqual(host['review']['status'], 'BLOCKED')

    def test_codex_claude_file_fallback_same_contract(self):
        skill = self.write('custom/review/SKILL.md', 'Review independently and retain evidence')
        hosts = [dict(host=name, session='fixture-1', review={'path': 'custom/review/SKILL.md'}) for name in ('codex-local', 'claude-local')]
        result = inspect(self.root, {'hosts': hosts})
        for host in result['hosts']:
            self.assertEqual(host['review']['status'], 'FILE_FALLBACK')
            self.assertEqual(host['review']['path'], str(skill))
            self.assertEqual(host['discovery'], 'UNKNOWN')
            self.assertFalse(host['behavior_tested'])

    def test_review_missing_empty_directory_or_unsafe_is_blocked(self):
        self.write('empty/SKILL.md')
        (self.root / 'directory' / 'SKILL.md').mkdir(parents=True)
        for path in ('missing/SKILL.md', 'empty/SKILL.md', 'directory/SKILL.md', '../SKILL.md', '.env/SKILL.md'):
            result = inspect(self.root, {'hosts': [self.host(review={'path': path})]})
            self.assertEqual(result['hosts'][0]['review']['status'], 'BLOCKED')

    def model(self, **extra):
        model = dict(host='codex-local', session='fixture-1', role='reviewer', candidate='fixture-model', catalog=['fixture-model'], catalog_evidence='session catalog')
        model.update(extra)
        return model

    def test_model_candidate_entitlement_budget_separate(self):
        result = inspect(self.root, {'hosts': [self.host()], 'models': [self.model()]})['model_roles'][0]
        self.assertEqual(result['candidate_status'], 'LISTED')
        self.assertEqual(result['entitlement'], 'unknown')
        self.assertEqual(result['budget'], 'unknown')
        self.assertEqual(result['status'], 'UNBOUND')
        result = inspect(self.root, {'hosts': [self.host()], 'models': [self.model(entitlement='available', budget='approved')]})['model_roles'][0]
        self.assertEqual(result['status'], 'VALIDATED_DECLARATION')
        self.assertFalse(result['behavior_tested'])

    def test_unavailable_candidate_and_cross_host_session_never_bind(self):
        for override, status in (({'candidate': 'missing'}, 'MISSING'), ({'host': 'other-host'}, 'SESSION_UNKNOWN'), ({'session': 'old-session'}, 'SESSION_UNKNOWN'), ({'catalog_evidence': ''}, 'CATALOG_UNKNOWN')):
            model = self.model(entitlement='available', budget='approved', **override)
            result = inspect(self.root, {'hosts': [self.host()], 'models': [model]})['model_roles'][0]
            self.assertEqual(result['status'], 'UNBOUND')
            self.assertEqual(result['candidate_status'], status)

    def test_idempotent_additive_plan_and_conflicting_existing_file(self):
        desired = b'one adapter\n'
        manifest = {'adapter_files': [{'path': 'docs/adapter.md', 'sha256': hashlib.sha256(desired).hexdigest()}]}
        before = inspect(self.root, manifest)
        self.assertEqual(before['adapter_plan'][0]['status'], 'PROPOSE_ADD')
        self.assertEqual(before, inspect(self.root, manifest))
        self.assertEqual(list(self.root.iterdir()), [])
        self.write('docs/adapter.md', desired.decode())
        self.assertEqual(inspect(self.root, manifest)['adapter_plan'][0]['status'], 'NOOP')
        self.write('docs/adapter.md', 'concurrent edit')
        self.assertEqual(inspect(self.root, manifest)['adapter_plan'][0]['status'], 'BLOCKED')
        self.assertEqual((self.root / 'docs/adapter.md').read_text(), 'concurrent edit')

    def test_native_inventory_unknown_differs_from_explicit_empty(self):
        host = self.host()
        host.pop('native_tools', None)
        result = inspect(self.root, {'hosts': [host]})['hosts'][0]
        self.assertEqual(result['native_tool_inventory'], 'UNKNOWN')
        self.assertIsNone(result['declared_native_tools'])
        host['native_tools'] = []
        result = inspect(self.root, {'hosts': [host]})['hosts'][0]
        self.assertEqual(result['native_tool_inventory'], 'DECLARED')
        self.assertEqual(result['declared_native_tools'], [])

    def test_adapter_beneath_file_is_blocked(self):
        self.write('docs', 'existing user file')
        manifest = {'adapter_files': [{'path': 'docs/adapter.md', 'sha256': hashlib.sha256(b'new').hexdigest()}]}
        self.assertEqual(inspect(self.root, manifest)['adapter_plan'][0]['status'], 'BLOCKED')
        self.assertEqual((self.root / 'docs').read_text(), 'existing user file')

    def test_invalid_extension_schema(self):
        invalid = [
            {'hosts': [self.host(), self.host()]},
            {'hosts': [self.host(discovered_skills=True)]},
            {'models': [self.model(entitlement=True)]},
            {'models': [self.model(catalog='model')]},
            {'models': [self.model(role='unknown-role')]},
            {'adapter_files': [{'path': 'x', 'sha256': 'invalid'}]},
        ]
        for manifest in invalid:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                inspect(self.root, manifest)


if __name__ == '__main__':
    unittest.main()
