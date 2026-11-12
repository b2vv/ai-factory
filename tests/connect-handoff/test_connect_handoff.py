import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
spec = importlib.util.spec_from_file_location('connector', TOOLS / 'connect-handoff.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
k = c.installer


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.package = self.base / 'release'
        self.root = self.base / 'managed kit ; literal'
        self.roots = []
        for name in ['Cargo', 'Courses', 'Cassiopeia', 'dg']:
            root = self.base / name
            (root / '.git').mkdir(parents=True)
            self.roots.append(str(root))
        self.spec = {'home': str(self.home), 'managed_root': str(self.root), 'store': str(self.base / 'store'),
                     'roots': self.roots, 'profile_path': str(self.base / "profile ' quoted.json"),
                     'registration_root': str(self.base / 'registration'), 'hosts': ['claude', 'codex'],
                     'python': str(Path(sys.executable).resolve())}
        self.release()
        self.install()

    def release(self, version='1', native=True, marker=True):
        if self.package.exists():
            for file in self.package.rglob('*'):
                if file.is_file():
                    file.unlink()
        payload = {'rules/agent-entry.md': 'entry', c.GUARD: '# canonical guard\n'}
        if native:
            payload[c.NATIVE] = ('HANDOFF_API = 1\n' if marker else '') + 'def load_profile(p): pass\ndef event(*a, **kw): pass\ndef main(argv=None): pass\n'
        entries = []
        for name, text in payload.items():
            file = self.package / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text + '# version ' + version + '\n')
            entries.append({'path': name, 'sha256': k.digest(file.read_bytes()), 'component': 'core'})
        manifest = self.package / 'release-manifest.json'
        manifest.write_bytes(k.encode({'schema_version': 2, 'version': version, 'components': {'core': {}}, 'files': entries}))
        (self.package / 'checksums.sha256').write_text(''.join(k.digest(p.read_bytes()) + '  ' + str(p.relative_to(self.package)) + '\n' for p in sorted(self.package.rglob('*')) if p.is_file()))

    def install(self):
        p = k.plan(self.package, self.root)
        return k.apply(self.package, self.root, [], p['plan_id'])

    def apply(self):
        p = c.plan(self.spec)
        return c.apply(self.spec, p['plan_id'], True)

    def config(self, host='claude'):
        return self.home / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')

    def seed(self, obj, host='claude', mode=0o640):
        file = self.config(host)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(json.dumps(obj, indent=4).encode())
        file.chmod(mode)
        return file

    def snapshot(self):
        return {str(p.relative_to(self.base)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in self.base.rglob('*') if p.is_file()}

    def test_read_only_apply_repeat_noop_and_exact_rollback(self):
        old = {'theme': 'dark', 'hooks': {'Stop': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': 'archive'}, {'type': 'command', 'command': 'status'}]}]}}
        f = self.seed(old)
        old_bytes, old_mode = f.read_bytes(), stat.S_IMODE(f.stat().st_mode)
        before = self.snapshot()
        p = c.plan(self.spec)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(Path(self.spec['registration_root']).exists())
        tx = c.apply(self.spec, p['plan_id'], True)['transaction']
        self.assertEqual('VERIFIED', c.verify(self.spec)['status'])
        after = self.snapshot()
        self.assertEqual('NOOP', self.apply()['status'])
        self.assertEqual(after, self.snapshot())
        obj = json.loads(f.read_bytes())
        self.assertEqual(old['hooks']['Stop'][0], obj['hooks']['Stop'][0])
        self.assertEqual('dark', obj['theme'])
        c.rollback(self.spec, tx, True)
        self.assertEqual((old_bytes, old_mode), (f.read_bytes(), stat.S_IMODE(f.stat().st_mode)))
        self.assertFalse(Path(self.spec['profile_path']).exists())
        self.assertFalse(self.config('codex').exists())
        after = self.snapshot()
        self.assertEqual('NOOP', c.rollback(self.spec, tx, True)['status'])
        self.assertEqual(after, self.snapshot())

    def test_retire_exact_only_preserves_mixed_archive(self):
        handlers = [{'type': 'command', 'command': 'docker handoff exact'}, {'type': 'command', 'command': 'docker archive'}, {'type': 'command', 'command': 'status'}]
        self.seed({'hooks': {'Stop': [{'matcher': '*', 'hooks': handlers}]}, 'trusted_hash': 'do not change'})
        self.spec['retire'] = [{'host': 'claude', 'event': 'Stop', 'command': 'docker handoff exact'}]
        self.apply()
        obj = json.loads(self.config().read_bytes())
        self.assertEqual(handlers[1:], obj['hooks']['Stop'][0]['hooks'])
        self.assertEqual('do not change', obj['trusted_hash'])
        self.assertEqual('NOOP', self.apply()['status'])

    def test_upgrade_stable_commands_and_component_omission(self):
        self.apply()
        old = self.config().read_bytes()
        self.release('2')
        kit_tx = self.install()['transaction']
        self.assertTrue(c.verify(self.spec)['kit_changed'])
        self.apply()  # receipt rebind only
        self.assertEqual(old, self.config().read_bytes())
        self.assertFalse(c.verify(self.spec)['kit_changed'])
        rp = k.rollback_plan(self.root, kit_tx)
        k.rollback(self.root, kit_tx, rp['plan_id'])
        self.assertTrue(c.verify(self.spec)['kit_changed'])
        self.assertEqual(old, self.config().read_bytes())
        self.release('3', native=False)
        self.install()
        with self.assertRaises(ValueError): c.verify(self.spec)

    def test_command_quoting_and_all_events(self):
        p = c.plan(self.spec)
        self.assertEqual(8, len(p['commands']))
        for entry in p['commands']:
            args = shlex.split(entry['command'])
            self.assertEqual([self.spec['python'], '-I', '-B', str(self.root / c.NATIVE), 'hook', '--profile', self.spec['profile_path'], '--host', entry['host']], args)

    def test_exact_old_command_upgrade(self):
        self.apply()
        old = json.loads(self.config().read_bytes())
        # Explicit new interpreter path represents a reviewed new registration.
        interpreter = self.base / 'reviewed-python'
        interpreter.write_bytes(Path(self.spec['python']).read_bytes())
        interpreter.chmod(0o755)
        self.spec['python'] = str(interpreter)
        self.apply()
        new = json.loads(self.config().read_bytes())
        for event in c.EVENTS:
            self.assertEqual(1, len(new['hooks'][event]))
            self.assertNotEqual(old['hooks'][event], new['hooks'][event])

    def test_legacy_hash_guard_and_restore(self):
        legacy = self.home / '.agents/ai-factory/session-size/session_guard.py'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b'old exact legacy\n')
        legacy.chmod(0o640)
        self.spec['legacy'] = {'path': str(legacy), 'before_sha256': k.digest(legacy.read_bytes())}
        tx = self.apply()['transaction']
        self.assertIn(b'DEFAULT_STORE', legacy.read_bytes())
        self.assertIn(b'sys.dont_write_bytecode = True', legacy.read_bytes())
        self.assertLess(legacy.read_bytes().index(b'sys.dont_write_bytecode = True'), legacy.read_bytes().index(b'_spec.loader.exec_module(_native)'))
        self.assertIn(b'_native.event(_PROFILE', legacy.read_bytes())
        self.assertEqual('NOOP', self.apply()['status'])
        c.rollback(self.spec, tx, True)
        self.assertEqual(b'old exact legacy\n', legacy.read_bytes())
        self.assertEqual(0o640, stat.S_IMODE(legacy.stat().st_mode))
        self.spec['legacy']['before_sha256'] = '0' * 64
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_before_drift_and_profile_drift_block(self):
        f = self.seed({'untouched': True})
        p = c.plan(self.spec)
        f.write_text('{}')
        with self.assertRaises(ValueError): c.apply(self.spec, p['plan_id'], True)
        self.apply()
        Path(self.spec['profile_path']).write_text('{}')
        with self.assertRaises(ValueError): c.verify(self.spec)
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_pending_kit_and_api_missing_block(self):
        state = self.root / k.STATE
        k.atomic(state / 'pending.json', k.encode({'id': '0' * 32}))
        with self.assertRaises(ValueError): c.plan(self.spec)
        (state / 'pending.json').unlink()
        self.release('2', marker=False)
        self.install()
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_duplicate_json_unknown_structure_and_duplicate_commands(self):
        f = self.seed({})
        for raw in [b'{"hooks":{},"hooks":{}}', b'{"hooks":[]}', b'{"hooks":{"Stop":[{"unknown":1,"hooks":[]}]}}']:
            f.write_bytes(raw)
            with self.assertRaises(ValueError): c.plan(self.spec)
        handler = {'type': 'command', 'command': 'old'}
        self.seed({'hooks': {'Stop': [{'hooks': [handler, handler]}]}})
        self.spec['retire'] = [{'host': 'claude', 'event': 'Stop', 'command': 'old'}]
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_symlink_hardlink_overlap_and_private_state(self):
        f = self.seed({})
        target = self.base / 'target'
        target.write_text('{}')
        f.unlink()
        f.symlink_to(target)
        with self.assertRaises(ValueError): c.plan(self.spec)
        f.unlink()
        os.link(target, f)
        with self.assertRaises(ValueError): c.plan(self.spec)
        f.unlink()
        for key, value in [('profile_path', str(self.root / 'profile')), ('registration_root', str(self.home / '.claude' / 'registration')), ('store', self.roots[0]), ('profile_path', self.spec['registration_root'])]:
            spec = copy.deepcopy(self.spec)
            spec[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): c.plan(spec)
        self.apply()
        root = Path(self.spec['registration_root'])
        self.assertEqual(0o700, stat.S_IMODE(root.stat().st_mode))
        for file in (root / k.STATE).rglob('*'):
            if file.is_file(): self.assertEqual(0o600, stat.S_IMODE(file.stat().st_mode))
        root.chmod(0o755)
        with self.assertRaises(ValueError): c.verify(self.spec)

    def test_crash_after_each_target_and_recover_unjournaled_write(self):
        legacy = self.home / '.agents/ai-factory/session-size/session_guard.py'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b'previous')
        self.spec['legacy'] = {'path': str(legacy), 'before_sha256': k.digest(legacy.read_bytes())}
        originals = {str(legacy): legacy.read_bytes()}
        real = k.guarded_write
        for fail_after in range(1, 5):
            calls = []
            def crash(*args):
                real(*args)
                calls.append(args[0])
                if len(calls) == fail_after:
                    raise OSError('simulated death after publication before journal')
            with patch.object(k, 'guarded_write', side_effect=crash):
                with self.assertRaises(OSError): self.apply()
            state = Path(self.spec['registration_root']) / k.STATE
            txid = k.read_json(state / 'pending.json')['id']
            with self.assertRaises(ValueError): c.plan(self.spec)
            with self.assertRaises(ValueError): self.apply()
            c.rollback(self.spec, txid, True)
            self.assertEqual(b'previous', legacy.read_bytes())
            self.assertFalse(self.config().exists())
            self.assertFalse(self.config('codex').exists())
            self.assertFalse(Path(self.spec['profile_path']).exists())

    def test_rollback_drift_is_all_targets_preflight(self):
        tx = self.apply()['transaction']
        f = self.config()
        f.write_bytes(f.read_bytes() + b' ')
        before = self.snapshot()
        with self.assertRaises(ValueError): c.rollback(self.spec, tx, True)
        self.assertEqual(before, self.snapshot())

    def test_journal_boundary_crashes_and_rollback_completion_crash(self):
        real = k.write_tx
        for phase in ('PREPARED', 'current', 'APPLIED'):
            fired = []
            def crash(path, value):
                real(path, value)
                match = path.name == 'current.json' if phase == 'current' else path.parent.name == 'receipts' and value['status'] == phase
                if match and not fired:
                    fired.append(True)
                    raise OSError('journal boundary crash')
            with patch.object(k, 'write_tx', side_effect=crash):
                with self.assertRaises(OSError): self.apply()
            state = Path(self.spec['registration_root']) / k.STATE
            receipts = [k.read_tx(p) for p in (state / 'receipts').glob('*.json')]
            tx = next(r['id'] for r in receipts if r['status'] != 'ROLLED_BACK')
            with self.assertRaises(ValueError): c.plan(self.spec)
            def rollback_crash(path, value):
                real(path, value)
                if value.get('status') == 'ROLLED_BACK':
                    raise OSError('rollback completion crash')
            with patch.object(k, 'write_tx', side_effect=rollback_crash):
                with self.assertRaises(OSError): c.rollback(self.spec, tx, True)
            c.rollback(self.spec, tx, True)
            self.assertFalse((state / 'pending.json').exists())
            self.assertFalse(self.config().exists())

    def test_kit_identity_and_interpreter_drift_bound_to_plan(self):
        interpreter = self.base / 'python-fixed'
        interpreter.write_bytes(Path(self.spec['python']).read_bytes())
        interpreter.chmod(0o755)
        self.spec['python'] = str(interpreter)
        planned = c.plan(self.spec)
        self.release('2')
        self.install()
        with self.assertRaises(ValueError): c.apply(self.spec, planned['plan_id'], True)
        self.apply()
        interpreter.write_bytes(interpreter.read_bytes() + b'changed')
        with self.assertRaises(ValueError): c.verify(self.spec)
        self.assertEqual('PLANNED', c.plan(self.spec)['status'])

    def test_invalid_receipt_and_missing_guard_block(self):
        installed = k.current(self.root)
        receipt = self.root / k.STATE / 'receipts' / (installed['latest'] + '.json')
        raw = receipt.read_bytes()
        receipt.write_bytes(raw.replace(b'APPLIED', b'BROKEN!'))
        with self.assertRaises(ValueError): c.plan(self.spec)
        receipt.write_bytes(raw)
        (self.root / c.GUARD).unlink()
        with self.assertRaises(ValueError): c.plan(self.spec)

    def test_local_project_and_config_toml_bytes_never_written(self):
        protected = []
        for root in map(Path, self.roots):
            for name in ('.claude/settings.json', '.codex/hooks.json', '.codex/config.toml'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'foreign project archive and trust sentinel')
                protected.append(path)
        global_toml = self.home / '.codex/config.toml'
        global_toml.parent.mkdir(parents=True, exist_ok=True)
        global_toml.write_bytes(b'foreign global trust sentinel')
        protected.append(global_toml)
        before = {str(p): p.read_bytes() for p in protected}
        tx = self.apply()['transaction']
        c.verify(self.spec)
        c.rollback(self.spec, tx, True)
        self.assertEqual(before, {str(p): p.read_bytes() for p in protected})

    def test_legacy_arbitrary_hash_target_forbidden(self):
        target = self.base / 'unrelated.py'
        target.write_bytes(b'not authorized')
        self.spec['legacy'] = {'path': str(target), 'before_sha256': k.digest(target.read_bytes())}
        with self.assertRaises(ValueError): c.plan(self.spec)
        self.assertEqual(b'not authorized', target.read_bytes())

    def test_large_unrelated_config_blocks_before_any_publication(self):
        file = self.seed({'unrelated': 'x' * 800_000})
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'receipt exceeds'):
            c.plan(self.spec)
        with self.assertRaisesRegex(ValueError, 'receipt exceeds'):
            c.apply(self.spec, '0' * 64, True)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(Path(self.spec['registration_root']).exists())
        self.assertEqual(800_000, len(json.loads(file.read_bytes())['unrelated']))

    def test_receipt_budget_exact_boundary_includes_integrity_and_rollback(self):
        self.seed({'unrelated': 'preserve'})
        planned = c.plan(self.spec)
        tx = c.prepare_transaction(planned, '0' * 32)
        all_applied = [entry['path'] for entry in planned['changes']]
        maximum = len(c.receipt_bytes({**tx, 'applied': all_applied, 'status': 'ROLLED_BACK'}))
        self.assertGreater(maximum, len(c.receipt_bytes(tx)))
        before = self.snapshot()
        with patch.object(k, 'MAX', maximum - 1):
            with self.assertRaisesRegex(ValueError, 'receipt exceeds'): c.plan(self.spec)
            with self.assertRaisesRegex(ValueError, 'receipt exceeds'): c.apply(self.spec, planned['plan_id'], True)
        self.assertEqual(before, self.snapshot())
        with patch.object(k, 'MAX', maximum):
            txid = self.apply()['transaction']
            self.assertEqual('VERIFIED', c.verify(self.spec)['status'])
            c.rollback(self.spec, txid, True)
            receipt = Path(self.spec['registration_root']) / k.STATE / 'receipts' / (txid + '.json')
            self.assertEqual(maximum, receipt.stat().st_size)
            self.assertEqual('ROLLED_BACK', k.read_tx(receipt)['status'])

    def test_repeated_rebinding_receipts_have_no_recursive_history_growth(self):
        self.apply()
        sizes = []
        for version in ('2', '3', '4', '5'):
            self.release(version)
            self.install()
            tx = self.apply()['transaction']
            state = Path(self.spec['registration_root']) / k.STATE
            receipt = state / 'receipts' / (tx + '.json')
            sizes.append(receipt.stat().st_size)
            obj = k.read_tx(receipt)
            self.assertNotIn('prior', obj['plan']['prior'])
            self.assertNotIn('plan', obj['plan']['prior'])
            self.assertNotIn('prior', k.read_tx(state / 'current.json'))
            c.verify(self.spec)
        self.assertEqual(1, len(set(sizes)))

    def test_empty_unowned_hook_groups_survive_retirement_upgrade_and_rollback(self):
        original = {'hooks': {'Stop': [
            {'hooks': []},
            {'matcher': 'unrelated-empty', 'hooks': []},
            {'hooks': [{'type': 'command', 'command': 'retire-exact'}]},
            {'matcher': 'mixed', 'hooks': [{'type': 'command', 'command': 'archive'}, {'type': 'command', 'command': 'retire-mixed'}]},
        ]}, 'unrelated': {'number': 1.25}}
        file = self.seed(original)
        raw = file.read_bytes()
        self.spec['retire'] = [{'host': 'claude', 'event': 'Stop', 'command': name} for name in ('retire-exact', 'retire-mixed')]
        tx = self.apply()['transaction']
        expected = [original['hooks']['Stop'][0], original['hooks']['Stop'][1], {'matcher': 'mixed', 'hooks': [{'type': 'command', 'command': 'archive'}]}]
        self.assertEqual(expected, json.loads(file.read_bytes())['hooks']['Stop'][:-1])
        after = file.read_bytes()
        self.assertEqual('NOOP', self.apply()['status'])
        self.assertEqual(after, file.read_bytes())
        c.rollback(self.spec, tx, True)
        self.assertEqual(raw, file.read_bytes())

    def test_nonfinite_and_precision_changing_numbers_fail_closed(self):
        file = self.seed({})
        for number in ('1e400', '-1e400', '1e-400', '0.12345678901234567890123456789', '1.0000000000000001'):
            raw = ('{"unrelated":' + number + '}').encode()
            file.write_bytes(raw)
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, 'JSON number'):
                c.plan(self.spec)
            self.assertEqual(raw, file.read_bytes())
            self.assertFalse(Path(self.spec['registration_root']).exists())
        file.write_bytes(b'{"unrelated":[0.125,1e20,-0.0,123456789012345678901234567890]}')
        tx = self.apply()['transaction']
        self.assertEqual([0.125, 1e20, -0.0, 123456789012345678901234567890], json.loads(file.read_bytes())['unrelated'])
        c.rollback(self.spec, tx, True)

    def test_store_preflight_rejects_file_and_nonprivate_without_writes(self):
        store = Path(self.spec['store'])
        store.write_bytes(b'foreign file')
        before = self.snapshot()
        with self.assertRaises(ValueError): c.plan(self.spec)
        with self.assertRaises(ValueError): c.apply(self.spec, '0' * 64, True)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(Path(self.spec['registration_root']).exists())
        store.unlink()
        store.mkdir(mode=0o755)
        before = self.snapshot()
        with self.assertRaises(ValueError): c.plan(self.spec)
        with self.assertRaises(ValueError): c.apply(self.spec, '0' * 64, True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(0o755, stat.S_IMODE(store.stat().st_mode))
        self.assertFalse(Path(self.spec['registration_root']).exists())

    def test_private_or_absent_store_accepted_without_creation_or_chmod(self):
        store = Path(self.spec['store'])
        self.apply()
        self.assertEqual('VERIFIED', c.verify(self.spec)['status'])
        self.assertFalse(store.exists())
        store.mkdir(mode=0o700)
        sentinel = store / 'untouched'
        sentinel.write_bytes(b'private history')
        before = (store.stat().st_mode, sentinel.read_bytes(), sentinel.stat().st_mode)
        self.assertEqual('NOOP', self.apply()['status'])
        self.assertEqual('VERIFIED', c.verify(self.spec)['status'])
        self.assertEqual(before, (store.stat().st_mode, sentinel.read_bytes(), sentinel.stat().st_mode))
        store.chmod(0o755)
        with self.assertRaises(ValueError): c.verify(self.spec)
        self.assertEqual(0o755, stat.S_IMODE(store.stat().st_mode))

    def test_isolated_cli_help_and_plan_create_no_bytecode(self):
        copied = self.base / 'copied-tools'
        copied.mkdir()
        for name in ('connect-handoff.py', 'kit.py', 'connect-project.py'):
            (copied / name).write_bytes((TOOLS / name).read_bytes())
        specification = self.base / 'spec.json'
        specification.write_bytes(k.encode(self.spec))
        before = self.snapshot()
        for args in (['--help'], ['plan', '--spec', str(specification)]):
            result = subprocess.run([sys.executable, '-I', str(copied / 'connect-handoff.py'), *args], capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr.decode())
            self.assertFalse(list(copied.rglob('*.pyc')))
            self.assertFalse(list(copied.rglob('__pycache__')))
            self.assertEqual(before, self.snapshot())

    def test_explicit_reconcile_only_autocompact_preserves_bytes(self):
        self.apply()
        target = self.home / '.claude/settings.json'
        doc = json.loads(target.read_bytes()); doc['autoCompactWindow'] = 600000
        raw = json.dumps(doc, indent=3).encode(); target.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'registered file drift'): c.plan(self.spec)
        sha = k.digest(raw)
        p = c.plan(self.spec, sha)
        self.assertEqual('PLANNED', p['status']); self.assertEqual([], p['changes'])
        with self.assertRaises(ValueError): c.apply(self.spec, p['plan_id'], True, '0'*64)
        result = c.apply(self.spec, p['plan_id'], True, sha)
        self.assertEqual('APPLIED', result['status'])
        self.assertEqual(raw, target.read_bytes())
        self.assertEqual('VERIFIED', c.verify(self.spec)['status'])
        self.assertEqual('NOOP', c.plan(self.spec)['status'])
        c.rollback(self.spec, result['transaction'], True)
        self.assertEqual(raw, target.read_bytes())
        with self.assertRaisesRegex(ValueError, 'registered file drift'): c.verify(self.spec)

    def test_reconcile_rejects_boolean_numeric_permission_drift(self):
        target = self.home / '.claude/settings.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'permissions': {'flag': True}}))
        self.apply()
        doc = json.loads(target.read_bytes())
        doc['autoCompactWindow'] = 600000
        doc['permissions']['flag'] = 1
        target.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): c.plan(self.spec, k.digest(target.read_bytes()))

    def test_reconcile_rejects_other_drift_and_stale_hash(self):
        self.apply()
        target = self.home / '.claude/settings.json'
        baseline = json.loads(target.read_bytes())
        for extra in [{'permissions': {'defaultMode': 'bypassPermissions'}}, {'hooks': {}}, {'autoCompactWindow': 500000}]:
            doc = dict(baseline); doc['autoCompactWindow'] = 600000; doc.update(extra)
            target.write_text(json.dumps(doc))
            with self.assertRaises(ValueError): c.plan(self.spec, k.digest(target.read_bytes()))
        doc = dict(baseline); doc['autoCompactWindow'] = 600000; target.write_text(json.dumps(doc))
        sha = k.digest(target.read_bytes()); p = c.plan(self.spec, sha)
        target.write_text(json.dumps(doc, indent=1))
        with self.assertRaises(ValueError): c.apply(self.spec, p['plan_id'], True, sha)

    def test_wrong_plan_and_exclusive_required(self):
        before = self.snapshot()
        with self.assertRaises(ValueError): c.apply(self.spec, '0' * 64, True)
        with self.assertRaises(ValueError): c.apply(self.spec, c.plan(self.spec)['plan_id'])
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
