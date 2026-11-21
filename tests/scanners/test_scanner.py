"""Synthetic unit/mock contracts only. No scanner, Docker, network or product invocation."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/scanners'))
import scanner as s
import update_db as u


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='factory-scanner-test-')
        self.base = Path(self.temp.name).resolve()
        self.here = self.base / 'kit/runtime/scanners'
        shutil.copytree(s.HERE, self.here)
        self.here_patch = patch.object(s, 'HERE', self.here); self.here_patch.start()
        self.root = self.base / 'product'; self.root.mkdir()
        (self.root / 'sample.js').write_text('const answer = 42;\n')
        s.write_json(self.root / 'package.json', {'dependencies': {'prod-synthetic': '1.0.0'},
                     'devDependencies': {'dev-synthetic': '1.0.0'}})
        (self.root / 'yarn.lock').write_text('# yarn lockfile v1\n\nprod-synthetic@1.0.0:\n  version "1.0.0"\n\ndev-synthetic@1.0.0:\n  version "1.0.0"\n')
        self.m = s.read_json(self.here / 'manifest.json')
        for name, e in self.m['engines'].items():
            # Test-only fake pins; never published in the runtime manifest.
            e.update(image='test.invalid/' + name + '@sha256:' + 'a' * 64,
                     platform='linux/arm64', version='synthetic', provenance_review='ACCEPTED',
                     license_review='ACCEPTED', review_evidence='synthetic test only')
        self.m['db'].update(repository='test.invalid/db@sha256:' + 'b' * 64,
                            license_review='ACCEPTED', review_evidence='synthetic test only')
        self.store = self.base / 'db-store'; u.initialize(self.store)
        self.snap = self.make_snapshot()
        self.config = {'schema_version': 1, 'sanitized_inputs_reviewed': True, 'root': str(self.root),
                       'reports': str(self.base / 'reports'), 'files': {p.name: s.sha(p) for p in self.root.iterdir()},
                       'db_store': str(self.store), 'db_snapshot': self.snap.name}

    def tearDown(self):
        self.here_patch.stop()
        for p in self.base.rglob('*'):
            if p.is_dir() and not p.is_symlink(): p.chmod(0o700)
        self.temp.cleanup()

    def make_snapshot(self, age=1, version=2, next_hours=2):
        stage = self.store / 'stage'; (stage / 'db').mkdir(parents=True)
        (stage / 'db/trivy.db').write_bytes(b'NOT A REAL DB: synthetic bytes for hash validation only')
        now = dt.datetime.now(dt.timezone.utc)
        s.write_json(stage / 'db/metadata.json', {'Version': version,
                     'UpdatedAt': (now - dt.timedelta(hours=age)).isoformat(),
                     'NextUpdate': (now + dt.timedelta(hours=next_hours)).isoformat()})
        files = {n: s.sha(stage / n) for n in ('db/trivy.db', 'db/metadata.json')}
        identity = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        s.write_json(stage / 'snapshot.json', {'schema_version': 1, 'engine_image': self.m['engines']['trivy']['image'],
                     'db_source': self.m['db']['repository'], 'files': files})
        target = self.store / identity; stage.rename(target)
        for p in target.rglob('*'): p.chmod(0o555 if p.is_dir() else 0o444)
        target.chmod(0o555)
        return target

    def semgrep(self, finding=False):
        return {'results': [{'check_id': 'synthetic'}] if finding else [], 'errors': [],
                'paths': {'scanned': ['/src/sample.js']}}

    def test_official_image_service_env_exact_values(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        expected = {'SEMGREP_IN_DOCKER': '1', 'SEMGREP_USER_AGENT_APPEND': 'Docker',
                    'PYTHONIOENCODING': 'utf8', 'DOCKER_OTEL_RESOURCE_ATTRIBUTES': '',
                    'DD_SERVICE': '', 'TSAN_OPTIONS': ''}
        for key, value in expected.items():
            self.assertEqual(service['environment'].get(key), value)
        self.assertTrue(set(expected).isdisjoint(s.SAFE_IMAGE_ENV))
        actual = self.obj(service)
        actual['Config']['Env'] += ['PATH=/usr/bin', 'PYTHONUNBUFFERED=1']
        s.verify_container(actual, service, 'sha256:local')
        self.assertEqual(service['network_mode'], 'none')
        self.assertEqual(service['environment']['SEMGREP_SEND_METRICS'], 'off')
        self.assertEqual(service['environment']['SEMGREP_ENABLE_VERSION_CHECK'], '0')

    def test_official_image_env_wrong_values_rejected(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        wrong = {'SEMGREP_IN_DOCKER': '', 'SEMGREP_USER_AGENT_APPEND': 'host',
                 'PYTHONIOENCODING': 'latin1', 'DOCKER_OTEL_RESOURCE_ATTRIBUTES': 'vcs.ref.head.name=release-1.181.0',
                 'DD_SERVICE': 'semgrep-core', 'TSAN_OPTIONS': 'exitcode=0 report_signal_unsafe=0'}
        for key, value in wrong.items():
            with self.subTest(key=key):
                actual = self.obj(service)
                actual['Config']['Env'] = [x for x in actual['Config']['Env'] if not x.startswith(key + '=')]
                actual['Config']['Env'].append(key + '=' + value)
                with self.assertRaises(s.Blocked): s.verify_container(actual, service, 'sha256:local')

    def test_official_image_env_missing_values_rejected(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        for key in ('SEMGREP_IN_DOCKER', 'SEMGREP_USER_AGENT_APPEND', 'PYTHONIOENCODING',
                    'DOCKER_OTEL_RESOURCE_ATTRIBUTES', 'DD_SERVICE', 'TSAN_OPTIONS'):
            with self.subTest(key=key):
                actual = self.obj(service)
                actual['Config']['Env'] = [x for x in actual['Config']['Env'] if not x.startswith(key + '=')]
                with self.assertRaises(s.Blocked): s.verify_container(actual, service, 'sha256:local')

    def test_official_image_env_unrelated_extras_rejected(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        for extra in ('SEMGREP_APP_TOKEN=synthetic', 'OTEL_EXPORTER_OTLP_ENDPOINT=http://invalid', 'UNRELATED='):
            actual = self.obj(service); actual['Config']['Env'].append(extra)
            with self.assertRaises(s.Blocked): s.verify_container(actual, service, 'sha256:local')

    def test_ce_only_invocation_contract(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        self.assertEqual(service['command'][:2], ['scan', '--oss-only'])
        self.assertNotIn('--error', service['command'])
        self.assertNotIn('--pro', service['command'])
        self.assertEqual(service['command'][service['command'].index('--config') + 1], '/rules')

    def test_actual_ce_argv_drift_rejected(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        for mutation in ('remove-oss', 'pro', 'ci'):
            actual = self.obj(service)
            actual['Config']['Cmd'] = list(service['command'])
            if mutation == 'remove-oss': actual['Config']['Cmd'].remove('--oss-only')
            elif mutation == 'pro': actual['Config']['Cmd'].append('--pro')
            else: actual['Config']['Cmd'][0] = 'ci'
            with self.assertRaises(s.Blocked): s.verify_container(actual, service, 'sha256:local')

    def trivy(self, finding=False):
        return {'SchemaVersion': 2, 'Results': [{'Target': 'yarn.lock', 'Type': 'yarn',
                  'Packages': [{'Name': 'prod-synthetic', 'Version': '1.0.0'}, {'Name': 'dev-synthetic', 'Version': '1.0.0'}],
                  'Vulnerabilities': [{'VulnerabilityID': 'SYNTHETIC-NOT-AN-ADVISORY', 'PkgName': 'dev-synthetic', 'InstalledVersion': '1.0.0'}] if finding else []}]}

    def obj(self, service):
        return {'Image': 'sha256:local', 'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True,
                'CapDrop': service.get('cap_drop', []), 'SecurityOpt': service.get('security_opt', []),
                'Tmpfs': dict(v.split(':', 1) for v in service.get('tmpfs', [])),
                'NanoCpus': 2000000000, 'Memory': 2 * 1024**3, 'MemorySwap': 2 * 1024**3, 'PidsLimit': 128},
                'Config': {'Image': service['image'], 'User': service['user'], 'Entrypoint': service['entrypoint'],
                           'Cmd': service['command'], 'WorkingDir': '/src',
                           'Env': [k + '=' + v for k, v in service['environment'].items()]},
                'Mounts': [{'Type': 'bind', 'Source': v['source'], 'Destination': v['target'],
                            'RW': not v['read_only']} for v in service['volumes']]}

    def test_unresolved_pins_block_without_docker(self):
        with patch.object(s, 'docker_call') as docker:
            unresolved=copy.deepcopy(self.m);unresolved['engines']['trivy']['image']=None
            s.write_json(self.here / 'manifest.json',unresolved)
            with self.assertRaises(s.Blocked): s.load_manifest(self.here / 'manifest.json')
            docker.assert_not_called()

    def test_manifest_review_and_immutable_pin_required(self):
        for field, value in [('image', 'test:latest'), ('provenance_review', 'PENDING'), ('platform', None)]:
            m = copy.deepcopy(self.m); m['engines']['trivy'][field] = value
            p = self.base / 'manifest.json'; s.write_json(p, m)
            with self.assertRaises(s.Blocked): s.load_manifest(p)

    def test_compose_plugin_staged_hash_bound_without_execution(self):
        plugin=self.base/'authored-compose';plugin.write_bytes(b'fixture not executed');plugin.chmod(0o500)
        self.config['compose_plugin']={'path':str(plugin),'sha256':s.sha(plugin)}
        home=self.base/'home';home.mkdir()
        with patch.object(subprocess,'run') as run:
            s.stage_compose_plugin(self.config,home);run.assert_not_called()
        staged=home/'cli-plugins/docker-compose'
        self.assertEqual(staged.read_bytes(),plugin.read_bytes());self.assertEqual(staged.stat().st_mode&0o777,0o500)
        self.assertEqual(s.read_json(home/'config.json'),{'cliPluginsExtraDirs':[str(staged.parent)]})

    def test_compose_plugin_invalid_pin_and_paths_block(self):
        plugin=self.base/'authored-compose';plugin.write_bytes(b'fixture');plugin.chmod(0o500)
        self.config['compose_plugin']={'path':str(plugin),'sha256':s.sha(plugin)}
        plugin.chmod(0o700);plugin.write_bytes(b'drift')
        with self.assertRaises(s.Blocked):s.prepare(self.config,self.m)
        self.config['compose_plugin']['sha256']=s.sha(plugin);plugin.chmod(0o400)
        with self.assertRaises(s.Blocked):s.compose_plugin(self.config)
        plugin.chmod(0o500);link=self.base/'plugin-link';link.symlink_to(plugin);self.config['compose_plugin']['path']=str(link)
        with self.assertRaises(s.Blocked):s.compose_plugin(self.config)
        self.config['compose_plugin']['path']=str(plugin);os.link(plugin,self.base/'hardlink')
        with self.assertRaises(s.Blocked):s.compose_plugin(self.config)

    def test_compose_plugin_optional_no_config_written(self):
        home=self.base/'home';home.mkdir();s.stage_compose_plugin(self.config,home)
        self.assertEqual(list(home.iterdir()),[])

    def test_prepare_is_read_only(self):
        with patch.object(s, 'docker_call') as docker:
            self.assertEqual(s.prepare(self.config, self.m)[0], self.root)
            self.assertFalse(Path(self.config['reports']).exists()); docker.assert_not_called()

    def test_source_hash_change_blocks(self):
        (self.root / 'sample.js').write_text('changed')
        with self.assertRaises(s.Blocked): s.prepare(self.config, self.m)

    def test_source_file_symlink_blocks(self):
        p = self.root / 'sample.js'; p.unlink(); p.symlink_to(self.here / 'scanner.py')
        with self.assertRaises(s.Blocked): s.source_files(self.config)

    def test_source_parent_symlink_blocks(self):
        link = self.base / 'linked'; link.symlink_to(self.root, target_is_directory=True)
        self.config['root'] = str(link)
        with self.assertRaises(s.Blocked): s.source_files(self.config)

    def test_source_hardlink_blocks(self):
        os.link(self.root / 'sample.js', self.base / 'duplicate')
        with self.assertRaises(s.Blocked): s.source_files(self.config)

    def test_hidden_and_sensitive_files_block(self):
        for name in ['.env', '../outside.js', 'secrets.js', 'node_modules/.cache/key.js']:
            config = copy.deepcopy(self.config); config['files'][name] = 'a' * 64
            with self.assertRaises(s.Blocked): s.source_files(config)

    def test_reports_overlap_and_existing_block(self):
        self.config['reports'] = str(self.root / 'reports')
        with self.assertRaises(s.Blocked): s.prepare(self.config, self.m)
        self.config['reports'] = str(self.base)
        with self.assertRaises(s.Blocked): s.prepare(self.config, self.m)

    def test_snapshot_fresh_schema_and_immutable(self):
        s.validate_snapshot(self.store, self.snap.name, self.m)
        for kwargs in [{'age': 25}, {'age': -1}, {'version': 1}, {'next_hours': -0.1}]:
            bad = self.make_snapshot(**kwargs)
            with self.assertRaises(s.Blocked): s.validate_snapshot(self.store, bad.name, self.m)
        (self.snap / 'db/trivy.db').chmod(0o644)
        with self.assertRaises(s.Blocked): s.validate_snapshot(self.store, self.snap.name, self.m)

    def test_snapshot_hash_corruption_blocks(self):
        p = self.snap / 'db/trivy.db'; p.chmod(0o644); p.write_bytes(b'changed'); p.chmod(0o444)
        with self.assertRaises(s.Blocked): s.validate_snapshot(self.store, self.snap.name, self.m)

    def test_snapshot_symlink_and_extra_file_block(self):
        self.snap.chmod(0o755); p = self.snap / 'unexpected'; p.symlink_to(self.root)
        with self.assertRaises(s.Blocked): s.validate_snapshot(self.store, self.snap.name, self.m)
        p.unlink(); p.write_text('extra'); p.chmod(0o444); self.snap.chmod(0o555)
        with self.assertRaises(s.Blocked): s.validate_snapshot(self.store, self.snap.name, self.m)

    def test_store_owner_and_git_blocks(self):
        s.write_json(self.store / 'owner.json', {'owner': 'other'})
        with self.assertRaises(s.Blocked): s.store_root(self.store)
        (self.base / '.git').mkdir()
        with self.assertRaises(s.Blocked): u.initialize(self.base / 'other-store')

    def assert_compose_security(self, service):
        self.assertEqual(service.get('cap_drop'), ['ALL'])
        self.assertEqual(service.get('security_opt'), ['no-new-privileges:true'])
        # Template must keep the approved bound, independently of inspect fixtures.
        self.assertEqual(service.get('tmpfs'), ['/tmp:rw,noexec,nosuid,size=256m'])

    def test_compose_security_mutations_are_detected(self):
        original = s.read_json(self.here / 'compose.yaml')
        for name in original['services']:
            for field, replacement in [('cap_drop', []), ('cap_drop', ['NET_RAW']),
                                       ('security_opt', []), ('security_opt', ['seccomp=unconfined']),
                                       ('tmpfs', []), ('tmpfs', ['/tmp:rw,exec,suid,size=4g'])]:
                for remove in [False, True]:
                    with self.subTest(service=name, field=field, remove=remove, value=replacement):
                        changed = copy.deepcopy(original)
                        if remove: changed['services'][name].pop(field)
                        else: changed['services'][name][field] = replacement
                        s.write_json(self.here / 'compose.yaml', changed)
                        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services'][name]
                        with self.assertRaises(AssertionError): self.assert_compose_security(service)
                        with self.assertRaises(s.Blocked): s.verify_container(self.obj(service), service, 'sha256:local')
        s.write_json(self.here / 'compose.yaml', original)

    def test_actual_tmpfs_guards_for_scan_and_updater(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['trivy']
        bad = [None, {}, {'/tmp': None}, {'/tmp': ''}, {'/extra': 'rw,noexec,nosuid,size=256m'}]
        for value in ['rw,exec,suid,size=4g', 'rw,nosuid,size=256m', 'rw,noexec,size=256m',
                      'rw,noexec,nosuid', 'rw,noexec,nosuid,size=0', 'rw,noexec,nosuid,size=4g',
                      'rw,noexec,nosuid,size=1073741825', 'rw,noexec,nosuid,size=-1',
                      'rw,noexec,nosuid,size=50%', 'rw,noexec,nosuid,size=1.5m',
                      'rw,noexec,nosuid,size=256m,size=1m', 'rw,noexec,nosuid,exec,size=1m',
                      'rw,noexec,nosuid,suid,size=1m', 'rw,noexec,nosuid,noexec,size=1m']:
            bad.append({'/tmp': value})
        good = [{'/tmp': value} for value in ['rw,noexec,nosuid,size=256m',
                'nosuid,size=268435456,noexec,rw', ' rw, noexec,nosuid,nodev,size=256M ',
                'rw,noexec,nosuid,size=262144k', 'rw,noexec,nosuid,size=1']]
        for updater in [False, True]:
            for accepted, cases in [(True, good), (False, bad)]:
                for tmpfs in cases:
                    with self.subTest(updater=updater, accepted=accepted, tmpfs=tmpfs):
                        obj = self.obj(service); obj['HostConfig']['Tmpfs'] = tmpfs
                        if updater:
                            obj['HostConfig']['NetworkMode'] = 'bridge'
                            obj['Mounts'] = [{'Type': 'bind', 'Source': str(self.store), 'Destination': '/cache', 'RW': True}]
                            verify = lambda: u.verify_updater(obj, 'sha256:local', service['image'], self.store, service['command'])
                        else:
                            verify = lambda: s.verify_container(obj, service, 'sha256:local')
                        if accepted: verify()
                        else:
                            with self.assertRaises(s.Blocked): verify()

    def test_updater_scratch_1g_only_scan_stays_256(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['trivy']
        self.assertEqual(service['tmpfs'], ['/tmp:rw,noexec,nosuid,size=256m'])
        for size in ('268435457', '1g', '1073741824', '1048576k'):
            obj=self.obj(service);obj['HostConfig']['Tmpfs']={'/tmp':'rw,noexec,nosuid,size='+size}
            with self.assertRaises(s.Blocked):s.verify_container(obj,service,'sha256:local')
            obj['HostConfig']['NetworkMode']='bridge'
            obj['Mounts']=[{'Type':'bind','Source':str(self.store),'Destination':'/cache','RW':True}]
            u.verify_updater(obj,'sha256:local',service['image'],self.store,service['command'])
        for value in ('rw,noexec,nosuid,size=1073741825','rw,noexec,nosuid,size=2g',
                      'rw,exec,nosuid,size=1g','rw,noexec,suid,size=1g',
                      'rw,noexec,nosuid,size=1g,size=256m'):
            obj['HostConfig']['Tmpfs']={'/tmp':value}
            with self.assertRaises(s.Blocked):u.verify_updater(obj,'sha256:local',service['image'],self.store,service['command'])

    def test_scan_resource_bounds_and_actual_drift(self):
        for name, service in s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services'].items():
            self.assertEqual((service['cpus'],service['mem_limit'],service['memswap_limit'],service['pids_limit']), (2,'2g','2g',128))
            self.assertEqual(service['tmpfs'], ['/tmp:rw,noexec,nosuid,size=256m'])
            s.verify_container(self.obj(service),service,'sha256:local')
            for key in ('NanoCpus','Memory','MemorySwap','PidsLimit'):
                for value in (None,0,1,4*1024**3):
                    obj=self.obj(service);obj['HostConfig'][key]=value
                    with self.subTest(engine=name,key=key,value=value), self.assertRaises(s.Blocked):
                        s.verify_container(obj,service,'sha256:local')

    def test_compose_has_offline_readonly_contract(self):
        doc = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)
        for name, service in doc['services'].items():
            self.assert_compose_security(service)
            self.assertEqual(service['network_mode'], 'none'); self.assertEqual(service['pull_policy'], 'never')
            self.assertTrue(service['read_only'])
            self.assertEqual([v['target'] for v in service['volumes'] if not v['read_only']], ['/reports'])
            self.assertNotIn('docker.sock', json.dumps(service))
            s.verify_container(self.obj(service), service, 'sha256:local')
        command = doc['services']['trivy']['command']
        for flag in ['--include-dev-deps', '--list-all-pkgs', '--skip-db-update', '--skip-java-db-update',
                     '--offline-scan', '--disable-telemetry']: self.assertIn(flag, command)
        self.assertEqual(command[command.index('--cache-backend') + 1], 'memory')

    def test_actual_mount_network_image_env_tampering_blocks(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['semgrep']
        mutations = [lambda o: o['Mounts'].append({'Type': 'volume', 'Destination': '/extra'}),
                     lambda o: o['Mounts'][0].update(RW=True),
                     lambda o: o['HostConfig'].update(NetworkMode='host'),
                     lambda o: o.update(Image='wrong'),
                     lambda o: o['Config']['Env'].append('TOKEN=untrusted'),
                     lambda o: o['Config'].update(Cmd=['other'])]
        for mutate in mutations:
            obj = self.obj(service); mutate(obj)
            with self.assertRaises(s.Blocked): s.verify_container(obj, service, 'sha256:local')

    def test_mock_positive_clean_error_results(self):
        for name, fixture in [('semgrep', self.semgrep), ('trivy', self.trivy)]:
            for finding in [True, False]:
                self.assertEqual(s.classify(name, fixture(finding), 0, self.config['files'], self.root),
                                 'FINDINGS' if finding else 'CLEAN')
            self.assertEqual(s.classify(name, fixture(), 7, self.config['files'], self.root), 'ERROR')
            self.assertEqual(s.classify(name, {}, 0, self.config['files'], self.root), 'ERROR')

    def test_missing_coverage_not_clean(self):
        report = self.semgrep(); report['paths']['scanned'] = []
        self.assertEqual(s.classify('semgrep', report, 0, self.config['files'], self.root), 'ERROR')
        report = self.trivy(); report['Results'][0]['Packages'] = [{'Name': 'prod-synthetic', 'Version': '1.0.0'}]
        self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')
        report['Results'] = []
        self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')

    def test_nested_rules_stage_exact_allowlist_and_baseline(self):
        n = 'semgrep-rules/nested/synthetic.yaml'
        p = self.here / 'rules' / n; p.parent.mkdir(parents=True)
        p.write_text('rules: []\n')
        self.m['rules']['files'][n] = s.sha(p)
        (p.parent / 'unlisted.yaml').write_text('not selected')
        out = self.base / 'staged'; out.mkdir()
        s.stage_rules(self.m, out)
        self.assertEqual(set(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()),
                         set(self.m['rules']['files']))
        self.assertEqual(s.rules_files(self.m, out), self.m['rules']['files'])
        self.assertEqual((out / n).stat().st_mode & 0o777, 0o444)
        command = s.render(self.m, self.root, out, self.snap, self.base)['services']['semgrep']['command']
        self.assertEqual(command[command.index('--config') + 1], '/rules')
        del self.m['rules']['files']['baseline.yaml']
        self.assertEqual(s.rules_files(self.m), {n: s.sha(p)})

    def test_rules_unsafe_paths_links_and_hashes_block(self):
        for n in ('../outside.yaml', '/outside.yaml', 'other/rule.yaml',
                  'semgrep-rules/../baseline.yaml', 'semgrep-rules/.hidden/a.yaml',
                  'semgrep-rules/a.txt', 'semgrep-rules//a.yaml'):
            with self.subTest(path=n):
                m = copy.deepcopy(self.m); m['rules']['files'] = {n: 'a' * 64}
                with self.assertRaises(s.Blocked): s.rules_files(m)
        p = self.here / 'rules/semgrep-rules/a.yml'; p.parent.mkdir()
        p.write_text('rules: []\n'); self.m['rules']['files'] = {'semgrep-rules/a.yml': s.sha(p)}
        p.write_text('changed')
        with self.assertRaises(s.Blocked): s.rules_files(self.m)
        p.unlink(); p.symlink_to(self.here / 'rules/baseline.yaml')
        with self.assertRaises(s.Blocked): s.rules_files(self.m)
        p.unlink(); os.link(self.here / 'rules/baseline.yaml', p)
        with self.assertRaises(s.Blocked): s.rules_files(self.m)
        p.unlink(); p.parent.rmdir()
        p.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(s.Blocked): s.rules_files(self.m)

    def test_staged_rule_suffixes_are_discoverable(self):
        for suffix in ('.yaml', '.yml'):
            name = 'semgrep-rules/nested/rule' + suffix
            path = self.here / 'rules' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('rules: []\n')
            self.m['rules']['files'][name] = s.sha(path)
        out = self.base / 'discovery'; out.mkdir()
        s.stage_rules(self.m, out)
        staged = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
        discovered = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p.suffix in ('.yaml', '.yml')}
        self.assertEqual(staged, discovered)
        self.assertEqual(discovered, set(self.m['rules']['files']))
        self.assertEqual(json.loads((out / 'baseline.yaml').read_text())['rules'][0]['id'],
                         json.loads((self.here / 'rules/baseline.yaml').read_text())['rules'][0]['id'])

    def test_json_named_directory_rules_fail_closed(self):
        for name in ('baseline.json', 'semgrep-rules/nested/rule.json'):
            path = self.here / 'rules' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"rules": []}')
            m = copy.deepcopy(self.m); m['rules']['files'] = {name: s.sha(path)}
            with self.assertRaises(s.Blocked): s.rules_files(m)

    def test_rules_hash_change_blocks(self):
        (self.here / 'rules/baseline.yaml').write_text('{}')
        with self.assertRaises(s.Blocked): s.rules_files(self.m)

    def test_mock_full_scan_never_exposes_product_mount(self):
        services = {}; calls = []
        def fake(prefix, args, env, timeout=600):
            calls.append(args)
            self.assertEqual(set(env), {'PATH', 'HOME', 'DOCKER_CONFIG', 'COMPOSE_DISABLE_ENV_FILE'})
            self.assertNotIn(str(self.root), json.dumps(args))
            if args[:2] == ['image', 'inspect']:
                return subprocess.CompletedProcess(args, 0, json.dumps([{'RepoDigests': [args[2]], 'Id': 'sha256:local', 'Os': 'linux', 'Architecture': 'arm64'}]), '')
            if args[0] == 'compose':
                doc = json.loads(Path(args[args.index('-f') + 1]).read_text()); services.update(doc['services'])
                if 'ps' in args:
                    return subprocess.CompletedProcess(args, 0, ('a' if args[-1] == 'semgrep' else 'b') * 64, '')
                return subprocess.CompletedProcess(args, 0, '', '')
            if args[:2] == ['start', '--attach']:
                name = 'semgrep' if args[2].startswith('a') else 'trivy'
                service = services[name]
                mounts = {v['target']: Path(v['source']) for v in service['volumes']}
                self.assertNotEqual(mounts['/src'], self.root)
                self.assertEqual(set(p.name for p in mounts['/src'].iterdir()), set(self.config['files']))
                s.write_json(mounts['/reports'] / (name + '.json'), self.semgrep() if name == 'semgrep' else self.trivy(True))
                return subprocess.CompletedProcess(args, 0, '', '')
            if args[:2] == ['inspect', '--format']:
                return subprocess.CompletedProcess(args, 0, json.dumps({'Running': False, 'ExitCode': 0}), '')
            if args[0] == 'inspect':
                name = 'semgrep' if args[1].startswith('a') else 'trivy'
                return subprocess.CompletedProcess(args, 0, json.dumps([self.obj(services[name])]), '')
            self.fail('unexpected docker operation ' + str(args))
        with patch.object(s, 'docker_call', side_effect=fake):
            result = s.run_scan(self.config, self.m, Path('/synthetic/socket'))
        self.assertEqual(result['status'], 'FINDINGS')
        self.assertTrue((self.base / 'reports/result.json').exists())
        self.assertTrue(any('down' in a for a in calls))
        self.assertFalse(any(a[0] in ('pull', 'build', 'run') for a in calls))

    def test_updater_resource_drift_rejected(self):
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['trivy']
        command = ['fs', '--download-db-only']
        obj = self.obj(service); obj['HostConfig']['NetworkMode'] = 'bridge'
        obj['Config']['Cmd'] = command
        obj['Mounts'] = [{'Type':'bind','Source':str(self.store),'Destination':'/cache','RW':True}]
        for key in ('NanoCpus', 'Memory', 'MemorySwap', 'PidsLimit'):
            for value in (None, 0, 9999999999):
                altered = copy.deepcopy(obj); altered['HostConfig'][key] = value
                with self.subTest(key=key, value=value):
                    with self.assertRaises(s.Blocked):
                        u.verify_updater(altered, 'sha256:local', service['image'], self.store, command)

    def test_updater_capture_separate_streams(self):
        result = u.docker_call([sys.executable], ['-c', 'import sys;print("out");print("err",file=sys.stderr)'], {}, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'out\n'); self.assertEqual(result.stderr, 'err\n')

    def test_updater_output_and_time_caps(self):
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream), patch.object(u, 'OUTPUT_BYTES', 100):
                with self.assertRaises(s.Blocked):
                    u.docker_call([sys.executable], ['-c', 'import sys;sys.' + stream + '.write("x"*101)'], {}, timeout=5)
        with self.assertRaises(s.Blocked):
            u.docker_call([sys.executable], ['-c', 'import time;time.sleep(5)'], {}, timeout=0.05)
        with patch.object(u.subprocess, 'Popen') as spawn:
            with self.assertRaises(s.Blocked): u.docker_call([], [], {}, timeout=0)
            spawn.assert_not_called()

    def test_updater_contract_has_only_cache_mount(self):
        command = ['fs', '--download-db-only']
        service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['trivy']
        obj = self.obj(service)
        obj['HostConfig']['NetworkMode'] = 'bridge'
        obj['Config']['Cmd'] = command
        obj['Mounts'] = [{'Type': 'bind', 'Source': str(self.store), 'Destination': '/cache', 'RW': True}]
        u.verify_updater(obj, 'sha256:local', service['image'], self.store, command)
        obj['Mounts'].append({'Type': 'bind', 'Source': str(self.root), 'Destination': '/src', 'RW': False})
        with self.assertRaises(s.Blocked): u.verify_updater(obj, 'sha256:local', service['image'], self.store, command)


    def mock_update(self, attack=None, command_fault=None):
        state = {}; timeouts = []
        def fake(prefix, args, env, timeout=600):
            if args[:2] == ['rm', '--force']:
                self.assertEqual(timeout, 15)
            else:
                self.assertGreater(timeout, 0); self.assertLessEqual(timeout, u.UPDATE_SECONDS)
                if timeouts: self.assertLessEqual(timeout, timeouts[-1])
                timeouts.append(timeout)
            self.assertNotIn(str(self.root), json.dumps(args))
            self.assertEqual(set(env), {'PATH', 'HOME', 'DOCKER_CONFIG'})
            if command_fault is not None:
                override = command_fault(args)
                if override is not None: return override
            if args[:2] == ['image', 'inspect']:
                out = [{'Id': 'sha256:local', 'RepoDigests': [args[2]], 'Os': 'linux', 'Architecture': 'arm64'}]
            elif args[0] == 'create':
                mount = args[args.index('--mount') + 1]
                state['cache'] = Path(mount.split('src=')[1].split(',dst=')[0])
                state['command'] = args[args.index(self.m['engines']['trivy']['image']) + 1:]
                self.assertEqual(args.count('--mount'), 1)
                self.assertIn('--download-db-only', state['command'])
                self.assertEqual(args[args.index('--tmpfs')+1], '/tmp:rw,noexec,nosuid,size=1g')
                for flag, value in [('--cpus','2'),('--memory','2g'),('--memory-swap','2g'),('--pids-limit','128')]:
                    self.assertEqual(args[args.index(flag)+1], value)
                self.assertGreater(timeout, 0); self.assertLessEqual(timeout, u.UPDATE_SECONDS)
                self.assertEqual(args[args.index('--pull') + 1], 'never')
                out = None
            elif args[:2] == ['start', '--attach']:
                cache = state['cache']; (cache / 'db').mkdir()
                (cache / 'db/trivy.db').write_bytes(b'another synthetic database')
                now = dt.datetime.now(dt.timezone.utc)
                s.write_json(cache / 'db/metadata.json', {'Version': 2, 'UpdatedAt': now.isoformat(),
                             'NextUpdate': (now + dt.timedelta(hours=2)).isoformat()})
                if attack is not None:
                    attack(cache)
                out = None
            elif args[:2] == ['inspect', '--format']:
                out = {'Running': False, 'ExitCode': 0}
            elif args[0] == 'inspect':
                service = s.render(self.m, self.root, self.here / 'rules', self.snap, self.base)['services']['trivy']
                obj = self.obj(service); obj['HostConfig']['NetworkMode'] = 'bridge'
                obj['Config']['Cmd'] = state['command']
                obj['Mounts'] = [{'Type': 'bind', 'Source': str(state['cache']), 'Destination': '/cache', 'RW': True}]
                out = [obj]
            elif args[:2] == ['rm', '--force']:
                out = None
            else:
                self.fail(str(args))
            return subprocess.CompletedProcess(args, 0, json.dumps(out) if out is not None else '', '')
        with patch.object(u, 'docker_call', side_effect=fake):
            return u.update(self.store, self.m, Path('/synthetic/socket'))

    def test_updater_primary_cleanup_uncertainty_retains_cache(self):
        for primary in (s.Blocked('PRIMARY inspection'), KeyboardInterrupt('PRIMARY cancellation'),
                        subprocess.TimeoutExpired('start', 1)):
            for cleanup_kind in ('timeout', 'nonzero', 'success'):
                with self.subTest(primary=type(primary).__name__, cleanup=cleanup_kind):
                    def fault(args):
                        if args[:2] == ['start', '--attach']: raise primary
                        if args[:2] == ['rm', '--force']:
                            if cleanup_kind == 'timeout': raise subprocess.TimeoutExpired('rm',15)
                            if cleanup_kind == 'nonzero': return subprocess.CompletedProcess(args,1,'','cleanup diagnostic')
                    before = set(self.store.glob('[0-9a-f]' * 64))
                    with self.assertRaises(u.UpdateFailure) as caught: self.mock_update(command_fault=fault)
                    failure = caught.exception
                    self.assertIs(failure.primary, primary)
                    self.assertTrue(failure.audit['container_name'].startswith('factory-db-'))
                    self.assertEqual(Path(failure.audit['cache']).exists(), cleanup_kind != 'success')
                    self.assertEqual(failure.audit['removal_uncertain'], cleanup_kind != 'success')
                    self.assertEqual(set(self.store.glob('[0-9a-f]' * 64)), before)
                    self.assertTrue((Path(failure.audit['receipts'])/'result.json').is_file())
                    self.assertTrue(any(x['argv'][-2] == '--attach' for x in failure.audit['commands'] if len(x['argv'])>=2))

    def test_updater_unknown_create_retains_identity(self):
        primary = subprocess.TimeoutExpired('create',1)
        def fault(args):
            if args[0]=='create': raise primary
            if args[:2]==['rm','--force']: return subprocess.CompletedProcess(args,1,'','unknown removal')
        with self.assertRaises(u.UpdateFailure) as caught:self.mock_update(command_fault=fault)
        a=caught.exception.audit
        self.assertIs(caught.exception.primary,primary)
        self.assertIsNone(a['container_id'])
        self.assertTrue(Path(a['cache']).exists())
        self.assertTrue(a['removal_uncertain'])

    def test_updater_receipt_failures_preserve_primary_and_cleanup(self):
        for point in ('command', 'result', 'resource'):
            primary=s.Blocked('PRIMARY retained'); writes=[]; real=u.write_receipt
            def write(path,value):
                writes.append(path.name)
                if path.name.startswith(point): raise OSError('receipt failure '+point)
                return real(path,value)
            def fault(args):
                if args[:2]==['start','--attach']: raise primary
            with patch.object(u,'write_receipt',side_effect=write):
                with self.assertRaises(u.UpdateFailure) as caught:self.mock_update(command_fault=fault)
            a=caught.exception.audit
            if point=='result':self.assertIs(caught.exception.primary,primary)
            self.assertEqual(a['status'],'ERROR')
            self.assertTrue(any(point in n for n in writes))
            if point=='resource':self.assertFalse(a['removal_uncertain'])

    def test_updater_cleanup_receipt_failure_is_conservative(self):
        primary=s.Blocked('PRIMARY start');real=u.write_receipt
        def write(path,value):
            if isinstance(value,dict) and value.get('argv',[])[-3:-1]==['rm','--force']:
                raise OSError('cleanup receipt failure')
            return real(path,value)
        def fault(args):
            if args[:2]==['start','--attach']:raise primary
        with patch.object(u,'write_receipt',side_effect=write):
            with self.assertRaises(u.UpdateFailure) as caught:self.mock_update(command_fault=fault)
        self.assertIs(caught.exception.primary,primary)
        self.assertTrue(caught.exception.audit['removal_uncertain'])
        self.assertTrue(Path(caught.exception.audit['cache']).exists())
        self.assertTrue(caught.exception.audit['persistence_errors'])

    def test_updater_summary_write_failure_without_primary_nonzero(self):
        with patch.object(u,'_update',return_value={'status':'NOOP','snapshot':'synthetic'}), \
             patch.object(u,'write_receipt',side_effect=OSError('summary failure')):
            with self.assertRaises(u.UpdateFailure) as caught:u.update(self.store,self.m,Path('/synthetic/socket'))
        self.assertIsInstance(caught.exception.primary,OSError)
        self.assertEqual(caught.exception.audit['result']['status'],'NOOP')
        self.assertEqual(caught.exception.audit['status'],'ERROR')

    def test_updater_bounded_prefixes_on_nonzero_timeout_limit(self):
        r=u.docker_call([sys.executable],['-u','-c','import sys;print("detail",file=sys.stderr);sys.exit(7)'],{},timeout=5)
        self.assertEqual(r.command_receipt['exit'],7)
        self.assertEqual(r.command_receipt['stderr'],'detail\n')
        for mode in ('timeout','limit'):
            script='import sys,time;sys.stderr.write("diagnostic-prefix-and-more");sys.stderr.flush();time.sleep(5)'
            with patch.object(u,'OUTPUT_BYTES',10 if mode=='limit' else 100):
                with self.assertRaises(s.Blocked) as caught:
                    u.docker_call([sys.executable],['-u','-c',script],{},timeout=.2)
            a=caught.exception.command_receipt
            self.assertTrue(a['stderr'].startswith('diagnostic'))
            self.assertLessEqual(len(a['stderr'].encode()),10 if mode=='limit' else 100)
            self.assertEqual(a['stderr_truncated'],mode=='limit')
            self.assertFalse(a['capture_complete'])

    def test_updater_cancel_keeps_already_captured_prefix(self):
        real=u.selectors.DefaultSelector;primary=KeyboardInterrupt('cancel')
        class InterruptAfterRead:
            def __init__(self):self.inner=real();self.calls=0
            def register(self,*a):return self.inner.register(*a)
            def unregister(self,*a):return self.inner.unregister(*a)
            def get_map(self):return self.inner.get_map()
            def close(self):return self.inner.close()
            def select(self,*a):
                if self.calls:raise primary
                events=self.inner.select(*a)
                if events:self.calls+=1
                return events
        with patch.object(u.selectors,'DefaultSelector',InterruptAfterRead):
            with self.assertRaises(KeyboardInterrupt) as caught:
                u.docker_call([sys.executable],['-u','-c','import sys,time;print("before-cancel",file=sys.stderr);time.sleep(5)'],{},timeout=5)
        self.assertIs(caught.exception,primary)
        self.assertIn('before-cancel',primary.command_receipt['stderr'])
        self.assertFalse(primary.command_receipt['capture_complete'])

    def test_updater_cleanup_failure_without_primary_blocks_publish(self):
        def fault(args):
            if args[:2]==['rm','--force']:return subprocess.CompletedProcess(args,1,'','removal failed')
        before=set(self.store.glob('[0-9a-f]' * 64))
        with self.assertRaises(u.UpdateFailure) as caught:self.mock_update(command_fault=fault)
        self.assertTrue(caught.exception.audit['work_retained'])
        self.assertEqual(set(self.store.glob('[0-9a-f]' * 64)),before)
        self.assertIn('removal failed',caught.exception.audit['commands'][-1]['stderr'])

    def test_updater_local_cleanup_failure_keeps_primary(self):
        primary=s.Blocked('PRIMARY start')
        def fault(args):
            if args[:2]==['start','--attach']:raise primary
        with patch.object(u,'remove_private_tree',side_effect=OSError('local cleanup failure')):
            with self.assertRaises(u.UpdateFailure) as caught:self.mock_update(command_fault=fault)
        self.assertIs(caught.exception.primary,primary)
        self.assertFalse(caught.exception.audit['removal_uncertain'])
        self.assertTrue(caught.exception.audit['work_retained'])
        self.assertTrue(Path(caught.exception.audit['cache']).exists())

    def test_updater_cli_emits_resource_and_primary_failure(self):
        import io
        from contextlib import redirect_stdout
        audit={'container_name':'factory-db-synthetic','container_id':None,
               'removal_uncertain':True,'cache':'/synthetic/cache','cleanup_errors':['rm timeout']}
        failure=u.UpdateFailure(KeyboardInterrupt('PRIMARY cancel'),audit)
        output=io.StringIO()
        with patch.object(sys,'argv',['update_db.py','update','--store',str(self.store),'--socket','/synthetic/socket','--execute','--network-authorized']), \
             patch.object(s,'load_manifest',return_value=self.m), patch.object(u,'update',side_effect=failure), redirect_stdout(output):
            code=u.main()
        result=json.loads(output.getvalue())
        self.assertNotEqual(code,0)
        self.assertEqual(result['diagnostics']['container_name'],'factory-db-synthetic')
        self.assertIn('PRIMARY cancel',result['reason'])

    def test_mock_updater_publishes_immutable_snapshot_without_source(self):
        result = self.mock_update()
        self.assertEqual(result['status'], 'SNAPSHOT_CREATED')
        s.validate_snapshot(self.store, result['snapshot'], self.m)

    def test_updater_unpinned_db_never_calls_docker(self):
        self.m['db']['repository'] = None
        with patch.object(s, 'docker_call') as docker:
            with self.assertRaises(s.Blocked): u.update(self.store, self.m, Path('/synthetic/socket'))
            docker.assert_not_called()


    def test_download_closure_rejected_without_external_byte_or_mode_changes(self):
        victim = self.base / 'owner-file'; victim.write_bytes(b'OWNER BYTES\n'); victim.chmod(0o440)
        before = victim.read_bytes(), victim.stat().st_mode
        outside_dir = self.base / 'owner-dir'; outside_dir.mkdir(); outside_dir.chmod(0o550)
        dir_mode = outside_dir.stat().st_mode
        def required_hardlink(cache):
            (cache / 'db/trivy.db').unlink(); os.link(victim, cache / 'db/trivy.db')
        def readonly_extra_with_hardlink(cache):
            d = cache / 'extra'; d.mkdir(); os.link(victim, d / 'owner'); d.chmod(0o550)
        attacks = [lambda cache: (cache / 'snapshot.json').symlink_to(victim),
                   lambda cache: os.link(victim, cache / 'snapshot.json'),
                   required_hardlink,
                   lambda cache: (cache / 'extra').symlink_to(outside_dir, target_is_directory=True),
                   lambda cache: os.mkfifo(cache / 'db/extra'),
                   readonly_extra_with_hardlink]
        for attack in attacks:
            with self.subTest(attack=attack):
                with patch.object(u, 'exclusive_json', wraps=u.exclusive_json) as metadata:
                    with self.assertRaises(s.Blocked): self.mock_update(attack)
                    metadata.assert_not_called()
                self.assertEqual((victim.read_bytes(), victim.stat().st_mode), before)
                self.assertEqual(outside_dir.stat().st_mode, dir_mode)
                self.assertEqual(victim.stat().st_nlink, 1)
                self.assertEqual(list(self.store.glob('update-*')), [])

    def test_required_download_special_file_and_symlink_rejected(self):
        def fifo(cache):
            (cache / 'db/trivy.db').unlink(); os.mkfifo(cache / 'db/trivy.db')
        def link(cache):
            (cache / 'db/trivy.db').unlink(); (cache / 'db/trivy.db').symlink_to(self.snap / 'db/trivy.db')
        for attack in (fifo, link):
            with self.assertRaises(s.Blocked): self.mock_update(attack)

    def test_metadata_creation_is_exclusive_and_does_not_follow_links(self):
        victim = self.base / 'victim'; victim.write_bytes(b'UNCHANGED'); victim.chmod(0o440)
        path = self.base / 'snapshot.json'; path.symlink_to(victim)
        with self.assertRaises(FileExistsError): u.exclusive_json(path, {'files': {}})
        self.assertEqual(victim.read_bytes(), b'UNCHANGED')
        self.assertEqual(victim.stat().st_mode & 0o777, 0o440)
        path.unlink(); os.link(victim, path)
        with self.assertRaises(FileExistsError): u.exclusive_json(path, {})
        self.assertEqual(victim.read_bytes(), b'UNCHANGED')
        self.assertEqual(victim.stat().st_mode & 0o777, 0o440)

    def test_trivy_malformed_collections_and_entries_are_error(self):
        values = [{}, '', False, 0, 'findings', [None], ['item'], [{}]]
        for field in ('Packages', 'Vulnerabilities'):
            for value in values:
                with self.subTest(field=field, value=value):
                    report = self.trivy(); report['Results'][0][field] = value
                    self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')
        for value in [None, {}, '', 1, []]:
            report = self.trivy(); report['Results'] = [value]
            self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')
        for field, value in [('Target', None), ('Type', []), ('Packages', None)]:
            report = self.trivy(); report['Results'][0][field] = value
            self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')
        for field in ('Name', 'Version'):
            report = self.trivy(); report['Results'][0]['Packages'][0][field] = []
            self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')
        for field in ('VulnerabilityID', 'PkgName', 'InstalledVersion'):
            report = self.trivy(True); report['Results'][0]['Vulnerabilities'][0][field] = 0
            self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')

    def test_trivy_optional_vulnerabilities_but_required_inventory(self):
        for value in [None, []]:
            report = self.trivy(); report['Results'][0]['Vulnerabilities'] = value
            self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'CLEAN')
        report = self.trivy(); del report['Results'][0]['Vulnerabilities']
        self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'CLEAN')
        del report['Results'][0]['Packages']
        self.assertEqual(s.classify('trivy', report, 0, self.config['files'], self.root), 'ERROR')


if __name__ == '__main__':
    unittest.main()
