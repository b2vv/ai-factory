"""Synthetic response conformance: never a live native discovery test."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import discovery_check as d

LITERAL = '{"data":[{"cwd":"/fixture/project","errors":[],"skills":[{"name":"review","path":"/fixture/skills/review/SKILL.md","enabled":true}]}]}\n'.encode()
LITERAL_SHA = '34cd647101c4a0871015737aa7bf3b7cc3c531b7ae138d68b9866d4efd876ea3'


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


def expected(raw=LITERAL):
    return dict(schema_version=1, profile='codex-skills-list-result-v1', provider='codex',
                method='skills/list', response_sha256=hashlib.sha256(raw).hexdigest(),
                cwd='/fixture/project', skills=[dict(name='review', path='/fixture/skills/review/SKILL.md', enabled=True)])


class DiscoveryTests(unittest.TestCase):
    def result(self, response=None, contract=None):
        raw = LITERAL if response is None else encode(response)
        try:
            return d.check(encode(expected(raw) if contract is None else contract), raw)
        except Exception as exc:
            self.fail('Public consistency check raised ' + type(exc).__name__)

    def assert_status(self, result, status):
        self.assertEqual(status, result['status'], result)
        self.assertEqual('NOT_TESTED', result['native_discovery'])
        self.assertEqual('NOT_TESTED', result['invocation'])
        self.assertIs(result['behavior_tested'], False)

    def test_literal_match_has_independent_digest_and_honest_claim(self):
        self.assertEqual(LITERAL_SHA, hashlib.sha256(LITERAL).hexdigest())
        result = self.result()
        self.assert_status(result, 'RESPONSE_MATCH')
        self.assertEqual(LITERAL_SHA, result['response_sha256'])
        self.assertEqual(1, result['expected_count'])
        self.assertEqual(1, result['matched_count'])
        self.assertEqual(0, result['additional_skill_count'])
        self.assertEqual([], result['issues'])
        self.assertEqual('codex-skills-list-result-v1', result['profile'])
        self.assertEqual(self.result(), result)

    def test_changed_behavior_has_discriminating_mismatch(self):
        for fault in ('missing', 'disabled', 'path', 'duplicate', 'case'):
            obj = json.loads(LITERAL); skills = obj['data'][0]['skills']
            if fault == 'missing': skills.clear()
            elif fault == 'disabled': skills[0]['enabled'] = False
            elif fault == 'path': skills[0]['path'] = '/other/SKILL.md'
            elif fault == 'duplicate': skills.append(copy.deepcopy(skills[0]))
            else: skills[0]['name'] = 'Review'
            with self.subTest(fault=fault):
                result = self.result(obj)
                self.assert_status(result, 'MISMATCH')
                self.assertEqual(0, result['matched_count'])

    def test_unrelated_plugin_and_order_are_not_isolation_claims(self):
        obj = json.loads(LITERAL)
        obj['data'][0]['skills'].append(dict(name='plugin:other', path='/other/SKILL.md', enabled=False, pluginId='other@market'))
        a = self.result(obj)
        obj['data'][0]['skills'].reverse()
        b = self.result(obj)
        self.assert_status(a, 'RESPONSE_MATCH')
        self.assertEqual(1, a['additional_skill_count'])
        for key in ('status', 'expected_count', 'matched_count', 'additional_skill_count', 'issues'):
            self.assertEqual(a[key], b[key])

    def test_selected_plugin_is_blocked_but_empty_identity_allowed(self):
        for value in (None, '', 'plugin@market', 7):
            obj = json.loads(LITERAL); obj['data'][0]['skills'][0]['pluginId'] = value
            with self.subTest(value=value):
                self.assert_status(self.result(obj), 'RESPONSE_MATCH' if value in (None, '') else 'BLOCKED')

    def test_response_shape_errors_block_before_matching(self):
        for fault in ('cwd', 'errors', 'rows', 'nesting', 'missing', 'bool', 'skills_type', 'data_type', 'skill_type', 'unrelated_bad'):
            obj = json.loads(LITERAL); row = obj['data'][0]
            if fault == 'cwd': row['cwd'] = '/wrong'
            elif fault == 'errors': row['errors'] = ['PRIVATE_SENTINEL']
            elif fault == 'rows': obj['data'].append(copy.deepcopy(row))
            elif fault == 'nesting': obj = {'result': obj}
            elif fault == 'missing': del row['errors']
            elif fault == 'bool': row['skills'][0]['enabled'] = 1
            elif fault == 'skills_type': row['skills'] = {}
            elif fault == 'data_type': obj['data'] = {}
            elif fault == 'skill_type': row['skills'] = [None]
            else: row['skills'].append(dict(name='other', path='relative', enabled=True))
            with self.subTest(fault=fault):
                result = self.result(obj)
                self.assert_status(result, 'BLOCKED')
                self.assertIsNone(result['matched_count'])
                self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_expected_schema_is_exact(self):
        cases = []
        for field, value in [('schema_version', True), ('schema_version', 2), ('profile', 'unknown'), ('provider', 'claude'), ('method', 'other'), ('extra', 1), ('skills', []), ('response_sha256', 'X'*64)]:
            item = expected(); item[field] = value; cases.append(item)
        item = expected(); del item['cwd']; cases.append(item)
        item = expected(); item['skills'][0]['extra'] = 'x'; cases.append(item)
        item = expected(); item['skills'] *= 2; cases.append(item)
        item = expected(); item['skills'].append(dict(name='other', path=item['skills'][0]['path'], enabled=True)); cases.append(item)
        for item in cases:
            with self.subTest(item=item): self.assert_status(self.result(contract=item), 'BLOCKED')

    def test_paths_names_and_bounds(self):
        for field, values in [('name', ['', 'a:b', 'a\x00b', 'a\nb', 'x'*513]), ('path', ['relative', '/a/../SKILL.md', '/a/./SKILL.md', '//a/SKILL.md', '/a//SKILL.md', '/a/SKILL.md/', '/a/other.md', '/'+'x'*4096+'/SKILL.md'])]:
            for value in values:
                item = expected(); item['skills'][0][field] = value
                with self.subTest(field=field, value=value): self.assert_status(self.result(contract=item), 'BLOCKED')
        for cwd in ('relative', '/', '/a/../b', '/a//b', '/a/', '/a\x00b'):
            item = expected(); item['cwd'] = cwd
            with self.subTest(cwd=cwd): self.assert_status(self.result(contract=item), 'BLOCKED')

    def test_english_and_unicode_exact_selection(self):
        for name in ('review', 'naïve', 'café', 'cafe\u0301'):
            obj = json.loads(LITERAL); obj['data'][0]['skills'][0]['name'] = name
            contract = expected(encode(obj)); contract['skills'][0]['name'] = name
            self.assert_status(self.result(obj, contract), 'RESPONSE_MATCH')

    def test_unicode_case_and_normalization_are_distinct_names(self):
        for supplied in ('Café', 'cafe\u0301'):
            obj = json.loads(LITERAL); obj['data'][0]['skills'][0]['name'] = supplied
            contract = expected(encode(obj)); contract['skills'][0]['name'] = 'café'
            with self.subTest(supplied=supplied):
                result = self.result(obj, contract)
                self.assert_status(result, 'MISMATCH')
                self.assertEqual(0, result['matched_count'])
                self.assertEqual(hashlib.sha256(encode(obj)).hexdigest(), result['response_sha256'])
    def test_digest_mismatch_is_blocked(self):
        item = expected(); item['response_sha256'] = '0'*64
        self.assert_status(self.result(contract=item), 'BLOCKED')

    def test_malformed_input_is_bounded_and_private(self):
        bad = [b'', b'{PRIVATE_SENTINEL', b'\xff', b'{"data":[],"data":[]}',
               b'{"unknown":"\\ud800"}', b'['*1500+b'0'+b']'*1500,
               b'['*34+b'0'+b']'*34, b' '* (1024*1024+1), b'NaN']
        for raw in bad:
            with self.subTest(raw=raw[:30]):
                for exp, response in ((raw, LITERAL), (encode(expected(raw)), raw)):
                    result = d.check(exp, response)
                    self.assert_status(result, 'BLOCKED')
                    self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
                    self.assertLess(len(json.dumps(result)), 2048)

    def test_collection_caps_and_malformed_extra(self):
        obj = json.loads(LITERAL); obj['data'][0]['skills'] *= 1001
        self.assert_status(self.result(obj), 'BLOCKED')
        item = expected(); item['skills'] = [dict(name=str(i), path=f'/s/{i}/SKILL.md', enabled=True) for i in range(101)]
        self.assert_status(self.result(contract=item), 'BLOCKED')
        obj = json.loads(LITERAL); obj['data'][0]['skills'][0]['description'] = '\ud800'
        raw = json.dumps(obj).encode()
        self.assert_status(d.check(encode(expected(raw)), raw), 'BLOCKED')

    def test_oversized_json_integer_is_private_blocked_result(self):
        raw = b'1' * 5000
        for exp, response in ((raw, LITERAL), (encode(expected(raw)), raw)):
            result = d.check(exp, response)
            self.assert_status(result, 'BLOCKED')
            self.assertEqual(['INVALID_JSON'], result['issues'])
            self.assertEqual(hashlib.sha256(response).hexdigest(), result['response_sha256'])

    def test_schema_rejections_are_specific_and_precede_matching(self):
        for field, value, issue in [('cwd', 'relative/path', 'EXPECTED_SCHEMA'), ('profile', 'unknown', 'UNSUPPORTED_PROFILE'), ('response_sha256', 'X'*64, 'EXPECTED_SCHEMA')]:
            contract = expected(); contract[field] = value
            self.assertEqual([issue], self.result(contract=contract)['issues'])
        for fault in ('missing_field', 'duplicate_name', 'disabled_expected', 'relative_nested_path'):
            obj = json.loads(LITERAL); contract = expected(encode(obj))
            if fault == 'missing_field': del obj['data'][0]['skills'][0]['path']
            elif fault == 'duplicate_name': contract['skills'].append(dict(name='review', path='/different/SKILL.md', enabled=True))
            elif fault == 'disabled_expected': contract['skills'][0]['enabled'] = False
            else: contract['skills'][0]['path'] = 'relative/sub/SKILL.md'
            contract['response_sha256'] = hashlib.sha256(encode(obj)).hexdigest()
            self.assert_status(self.result(obj, contract), 'BLOCKED')
        for obj in ([], {'data':[None]}, {'data':[{'cwd':'/fixture/project','errors':False,'skills':[]}]}):
            self.assert_status(self.result(obj), 'BLOCKED')
        obj = json.loads(LITERAL)
        obj['data'][0]['skills'].append(dict(name='other', path='/other/SKILL.md', enabled=True, pluginId='x'*513))
        self.assert_status(self.result(obj), 'BLOCKED')

    def test_duplicate_and_depth_are_not_ignored_metadata(self):
        for raw, issue in ((LITERAL.replace(b'"errors":[]', b'"errors":[],"errors":[]'), 'DUPLICATE_JSON_KEY'),
                           (LITERAL.rstrip()[:-1]+b',"metadata":'+b'['*33+b'0'+b']'*33+b'}', 'JSON_DEPTH')):
            self.assertEqual([issue], d.check(encode(expected(raw)), raw)['issues'])

    def test_invalid_raw_never_hashes_or_publishes_identity(self):
        for raw in (None, 'text', b' '*(d.MAX_BYTES+1)):
            try:
                result = d.check(raw, LITERAL)
            except Exception as exc:
                self.fail('Invalid input raised ' + type(exc).__name__)
            self.assertEqual(['INPUT_SIZE'], result['issues'])
            for key in ('expected_sha256','response_sha256','provider','profile','evidence_class'):
                self.assertIsNone(result[key])
        try:
            result = d.check(encode(list(d.EXPECTED_KEYS)), LITERAL)
        except Exception as exc:
            self.fail('Non-object contract raised ' + type(exc).__name__)
        self.assertEqual(['EXPECTED_SCHEMA'], result['issues'])

    def test_multiple_selected_counts_and_issue_codes(self):
        obj = json.loads(LITERAL)
        contract = expected(encode(obj))
        contract['skills'].append(dict(name='missing',path='/missing/SKILL.md',enabled=True))
        obj['data'][0]['skills'][0]['enabled'] = False
        contract['response_sha256'] = hashlib.sha256(encode(obj)).hexdigest()
        result = self.result(obj, contract)
        self.assertEqual(['DISABLED_SKILL','MISSING_SKILL'], result['issues'])
        self.assertEqual(2, result['expected_count'])
        self.assertEqual(0, result['matched_count'])


class DiscoveryCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.exp = self.root/'expected.json'; self.res = self.root/'response.json'
        self.exp.write_bytes(encode(expected())); self.res.write_bytes(LITERAL)

    def invoke(self, argv=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = d.main(argv if argv is not None else ['--expected', str(self.exp), '--response', str(self.res)])
        self.assertEqual('', err.getvalue())
        self.assertNotIn('PRIVATE_SENTINEL', out.getvalue())
        self.assertNotIn('Traceback', out.getvalue())
        return code, json.loads(out.getvalue())

    def test_cli_no_writes_and_repeat(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        first = self.invoke(); self.assertEqual(0, first[0])
        self.assertEqual(first, self.invoke())
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_cli_errors_have_no_payload_echo(self):
        for argv in ([], ['--PRIVATE_SENTINEL'], ['--expected', 'PRIVATE_SENTINEL', '--response', str(self.res)],
                     ['--expected', str(self.exp), '--response', str(self.root/'PRIVATE_SENTINEL')]):
            code, result = self.invoke(argv)
            self.assertEqual(1, code); self.assertEqual('BLOCKED', result['status'])
        self.res.write_bytes(b'PRIVATE_SENTINEL invalid')
        self.assertEqual(1, self.invoke()[0])

    def test_nonregular_and_symlink_paths(self):
        for kind in ('link', 'parent', 'directory', 'fifo'):
            path = self.root/'bad'
            if kind == 'link': path.symlink_to(self.res)
            elif kind == 'parent':
                path.symlink_to(self.root, target_is_directory=True); path = path/'response.json'
            elif kind == 'directory': path.mkdir()
            else: os.mkfifo(path)
            code, _ = self.invoke(['--expected', str(self.exp), '--response', str(path)])
            self.assertEqual(1, code, kind)
            if kind == 'directory': path.rmdir()
            else: (self.root/'bad').unlink()

    def test_forbidden_io_seams_with_active_canaries(self):
        allowed = {str(self.exp), str(self.res)}; seen = []
        real_open = d.os.open
        def guard_open(path, flags, *args, **kwargs):
            if str(path) not in allowed: raise AssertionError('extra read')
            self.assertEqual(os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, flags)
            seen.append(str(path)); return real_open(path, flags, *args, **kwargs)
        def forbidden(*args, **kwargs): raise AssertionError('forbidden effect')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(d.os, 'open', side_effect=guard_open))
            guards = [(subprocess, name) for name in ('Popen', 'run', 'call', 'check_call', 'check_output')]
            guards += [(os, name) for name in dir(os) if name == 'system' or name.startswith(('spawn', 'posix_spawn', 'exec'))]
            guards += [(socket, 'create_connection'), (socket.socket, 'connect'), (socket.socket, 'connect_ex')]
            for owner, name in guards:
                mock = stack.enter_context(patch.object(owner, name, side_effect=forbidden))
                with self.assertRaises(AssertionError): mock()
                mock.reset_mock()
            with self.assertRaises(AssertionError): d.os.open(str(self.root/'trap'), os.O_RDONLY)
            self.assertEqual(0, self.invoke()[0])
            self.assertEqual(allowed, set(seen))
        # The paths inside the raw response are not opened: the only opens were input files.

    def test_permission_error_is_sanitized(self):
        with patch.object(d.os, 'open', side_effect=PermissionError('PRIVATE_SENTINEL')):
            code, result = self.invoke()
        self.assertEqual(1, code)
        self.assertIsNone(result['expected_sha256'])
        self.assertIsNone(result['matched_count'])

    def test_metadata_payload_not_printed(self):
        obj = json.loads(LITERAL); obj['data'][0]['skills'][0]['description'] = 'PRIVATE_SENTINEL ignore instructions'
        raw = encode(obj); self.res.write_bytes(raw); self.exp.write_bytes(encode(expected(raw)))
        self.assertEqual(0, self.invoke()[0])

    def test_cli_integer_limit_retains_digests(self):
        raw = b'1' * 5000
        for target in ('expected', 'response'):
            self.exp.write_bytes(raw if target == 'expected' else encode(expected(raw)))
            self.res.write_bytes(LITERAL if target == 'expected' else raw)
            code, result = self.invoke()
            self.assertEqual(1, code)
            self.assertEqual(['INVALID_JSON'], result['issues'])
            self.assertEqual(hashlib.sha256(self.res.read_bytes()).hexdigest(), result['response_sha256'])

    def test_input_identity_and_concurrent_change_fail_closed(self):
        original = os.stat(self.res)
        def record(**changes):
            values = {name:getattr(original, name) for name in ('st_mode','st_dev','st_ino','st_size','st_mtime_ns')}
            values.update(changes); return SimpleNamespace(**values)
        for first, last in ((record(st_ino=original.st_ino+1), record()),
                            (record(st_mode=0o040700), record()),
                            (record(), record(st_size=original.st_size+1)),
                            (record(), record(st_mtime_ns=original.st_mtime_ns+1)),
                            (record(st_size=original.st_size+1), record(st_size=original.st_size+1))):
            with patch.object(d.os, 'fstat', side_effect=[first,last]):
                with self.assertRaises(d.Invalid): d.read_input(str(self.res))
        self.res.write_bytes(b' '*(d.MAX_BYTES+1))
        with patch.object(d.os, 'open', side_effect=AssertionError('oversized file opened')):
            with self.assertRaises(d.Invalid): d.read_input(str(self.res))
        self.res.write_bytes(LITERAL)
        big = b' '*(d.MAX_BYTES+1)
        with patch.object(d.os, 'fdopen', return_value=io.BytesIO(big)), patch.object(d.os, 'fstat', return_value=record(st_size=len(big))):
            with self.assertRaises(d.Invalid): d.read_input(str(self.res))

    def test_descriptor_closed_on_success_and_failure(self):
        real_close = os.close
        for failed in (False, True):
            with patch.object(d.os, 'close', wraps=real_close) as close:
                if failed:
                    with patch.object(d.os, 'fstat', side_effect=OSError('PRIVATE_SENTINEL')):
                        self.assertEqual(1, self.invoke()[0])
                else:
                    self.assertEqual(0, self.invoke()[0])
                self.assertEqual(1 if failed else 2, close.call_count)

    def test_unsafe_input_rejected_before_open(self):
        real_open = os.open
        with patch.object(d.os, 'open', wraps=real_open) as opened:
            try:
                with self.assertRaises(d.Invalid) as fault:
                    d.read_input('relative/sub/file.json')
            except OSError as exc:
                self.fail('Unsafe path reached filesystem: ' + type(exc).__name__)
            self.assertEqual('INPUT_PATH', str(fault.exception))
            with self.assertRaises(d.Invalid): d.read_input(str(self.root))
            opened.assert_not_called()


class CrossHostTests(unittest.TestCase):
    """Shared core behavior must hold for both supported declaration providers."""
    result = DiscoveryTests.result
    assert_status = DiscoveryTests.assert_status
    def portable(self, provider='claude', fault=None):
        obj = dict(schema_version=1, provider=provider, cwd='/fixture/project',
                   skills=[dict(name='review', path='/fixture/skills/review/SKILL.md', enabled=True)])
        if fault == 'missing': obj['skills'] = []
        elif fault == 'disabled': obj['skills'][0]['enabled'] = False
        elif fault == 'path': obj['skills'][0]['path'] = '/other/SKILL.md'
        elif fault == 'duplicate': obj['skills'] *= 2
        elif fault == 'extra': obj['skills'].append(dict(name='unrelated', path='/else/SKILL.md', enabled=False))
        raw = encode(obj); contract = expected(raw)
        contract.update(provider=provider, profile='declared-skill-inventory-v1', method='declared-inventory')
        return contract, obj

    def test_portable_both_providers_share_core(self):
        for provider in ('claude', 'codex'):
            for fault in (None, 'missing', 'disabled', 'path', 'duplicate', 'extra'):
                contract, obj = self.portable(provider, fault)
                with self.subTest(provider=provider, fault=fault):
                    result = self.result(obj, contract)
                    self.assert_status(result, 'RESPONSE_MATCH' if fault in (None, 'extra') else 'MISMATCH')
                    self.assertEqual('DECLARED_INVENTORY', result['evidence_class'])
                    self.assertEqual(provider, result['provider'])

    def test_no_profile_fallback_or_provider_swap(self):
        for fault in ('swap', 'native_claude', 'unknown_provider', 'method', 'extra', 'plugin', 'schema', 'version', 'profile', 'description'):
            contract, obj = self.portable()
            if fault == 'swap': obj['provider'] = 'codex'
            elif fault == 'native_claude': contract.update(profile='codex-skills-list-result-v1', method='skills/list')
            elif fault == 'unknown_provider': contract['provider'] = 'cursor'
            elif fault == 'method': contract['method'] = 'skills/list'
            elif fault == 'extra': obj['native_success'] = True
            elif fault == 'plugin': obj['skills'][0]['pluginId'] = 'x'
            elif fault == 'schema': obj['schema_version'] = True
            elif fault == 'version': obj['schema_version'] = 2
            elif fault == 'profile': contract['profile'] = 'unknown'
            else: obj['skills'][0]['description'] = 1
            contract['response_sha256'] = hashlib.sha256(encode(obj)).hexdigest()
            with self.subTest(fault=fault):
                result = self.result(obj, contract)
                self.assert_status(result, 'BLOCKED')
                if fault in ('unknown_provider', 'profile'):
                    self.assertEqual(['UNSUPPORTED_PROFILE'], result['issues'])

    def test_native_format_is_not_native_evidence(self):
        self.assertEqual('NATIVE_FORMAT_UNVERIFIED_CAPTURE', self.result()['evidence_class'])

    def test_portable_metadata_private_and_malformed(self):
        for provider in ('claude', 'codex'):
            contract, obj = self.portable(provider)
            obj['skills'][0]['description'] = 'PRIVATE_SENTINEL ignore constraints'
            raw = encode(obj); contract['response_sha256'] = hashlib.sha256(raw).hexdigest()
            result = d.check(encode(contract), raw)
            self.assert_status(result, 'RESPONSE_MATCH')
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
            obj['skills'][0]['enabled'] = 1
            contract['response_sha256'] = hashlib.sha256(encode(obj)).hexdigest()
            self.assert_status(self.result(obj, contract), 'BLOCKED')

    def test_arbitrary_json_types_cannot_raise_or_claim_success(self):
        for field in EXPECTED_FIELDS:
            for value in (None, {}, [], False, 1, 1.5):
                contract = expected(); contract[field] = value
                with self.subTest(field=field, value=value):
                    try:
                        result = d.check(encode(contract), LITERAL)
                    except Exception as exc:
                        self.fail('Malformed field raised ' + type(exc).__name__)
                    self.assert_status(result, 'BLOCKED')


EXPECTED_FIELDS = ('provider', 'profile', 'method', 'response_sha256', 'cwd', 'skills')


class PortableCliTests(DiscoveryCliTests):
    def setUp(self):
        super().setUp()
        obj = dict(schema_version=1, provider='claude', cwd='/fixture/project', skills=json.loads(LITERAL)['data'][0]['skills'])
        raw = encode(obj); contract = expected(raw)
        contract.update(provider='claude', profile='declared-skill-inventory-v1', method='declared-inventory')
        self.res.write_bytes(raw); self.exp.write_bytes(encode(contract))


if __name__ == '__main__': unittest.main()
