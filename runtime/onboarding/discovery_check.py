#!/usr/bin/env python3
"""Offline selected-skill evidence consistency. Never probes or configures a host."""
import argparse
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import unicodedata

MAX_BYTES = 1024 * 1024
NATIVE = 'codex-skills-list-result-v1'
DECLARED = 'declared-skill-inventory-v1'
EXPECTED_KEYS = {'schema_version', 'profile', 'provider', 'method', 'response_sha256', 'cwd', 'skills'}
ENTRY_KEYS = {'name', 'path', 'enabled'}


class Invalid(ValueError):
    """A fixed public issue code, never source content or exception text."""


def require(condition, code):
    if not condition:
        raise Invalid(code)


def result():
    return dict(status='BLOCKED', profile=None, provider=None, evidence_class=None,
                expected_sha256=None, response_sha256=None, expected_count=None,
                matched_count=None, additional_skill_count=None, issues=[],
                native_discovery='NOT_TESTED', invocation='NOT_TESTED', behavior_tested=False,
                claim='Supplied response consistency only; capture authenticity, current host state and skill behavior unverified')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and not any(unicodedata.category(c) in ('Cc', 'Cs') for c in value))


def path(value, skill=False):
    if not text(value, 4096) or not value.startswith('/') or value == '/':
        return False
    parts = value.split('/')[1:]
    return all(p not in ('', '.', '..') for p in parts) and (not skill or value.endswith('/SKILL.md'))


def pairs(items):
    obj = {}
    for key, value in items:
        require(key not in obj, 'DUPLICATE_JSON_KEY')
        obj[key] = value
    return obj


def invalid_constant(_):
    raise Invalid('INVALID_JSON')


def parse(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_BYTES, 'INPUT_SIZE')
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
        pending = [(obj, 1)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 32, 'JSON_DEPTH')
            if isinstance(value, str):
                require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'INVALID_UNICODE')
            elif isinstance(value, dict):
                pending.extend((v, depth + 1) for pair in value.items() for v in pair)
            elif isinstance(value, list):
                pending.extend((v, depth + 1) for v in value)
        return obj
    except Invalid:
        raise
    except (ValueError, RecursionError, OverflowError):
        raise Invalid('INVALID_JSON') from None


def entry_valid(item):
    return (isinstance(item, dict) and ENTRY_KEYS <= set(item)
            and text(item['name'], 512) and path(item['path'], skill=True)
            and type(item['enabled']) is bool)


def expected_profile(obj):
    require(isinstance(obj, dict) and set(obj) == EXPECTED_KEYS, 'EXPECTED_SCHEMA')
    require(type(obj['schema_version']) is int and obj['schema_version'] == 1, 'EXPECTED_SCHEMA')
    supported = (obj['provider'] in ('codex', 'claude')
                 and ((obj['profile'] == DECLARED and obj['method'] == 'declared-inventory')
                      or (obj['provider'] == 'codex' and obj['profile'] == NATIVE and obj['method'] == 'skills/list')))
    require(supported, 'UNSUPPORTED_PROFILE')
    require(isinstance(obj['response_sha256'], str) and re.fullmatch('[0-9a-f]{64}', obj['response_sha256']), 'EXPECTED_SCHEMA')
    require(path(obj['cwd']), 'EXPECTED_SCHEMA')
    skills = obj['skills']
    require(isinstance(skills, list) and 1 <= len(skills) <= 100, 'EXPECTED_SKILLS')
    require(all(entry_valid(s) and set(s) == ENTRY_KEYS and s['enabled'] is True and ':' not in s['name'] for s in skills), 'EXPECTED_SKILLS')
    require(len({s['name'] for s in skills}) == len(skills)
            and len({s['path'] for s in skills}) == len(skills), 'EXPECTED_DUPLICATE')
    return obj['profile']


def normalize(response, expected, profile):
    """Profile adapters return rows only; paths in rows never become file inputs."""
    require(isinstance(response, dict), 'RESPONSE_SCHEMA')
    if profile == NATIVE:
        rows = response.get('data')
        require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict), 'RESPONSE_SCHEMA')
        row = rows[0]
        require(isinstance(row.get('errors'), list) and row['errors'] == [], 'RESPONSE_ERRORS')
    else:
        require(set(response) == {'schema_version', 'provider', 'cwd', 'skills'}, 'RESPONSE_SCHEMA')
        require(type(response['schema_version']) is int and response['schema_version'] == 1, 'RESPONSE_SCHEMA')
        require(response['provider'] == expected['provider'], 'PROVIDER_MISMATCH')
        row = response
    require(row.get('cwd') == expected['cwd'], 'CWD_MISMATCH')
    skills = row.get('skills')
    require(isinstance(skills, list) and len(skills) <= 1000, 'RESPONSE_SKILLS')
    require(all(entry_valid(s) for s in skills), 'RESPONSE_SKILLS')
    selected = {s['name'] for s in expected['skills']}
    for item in skills:
        if profile == DECLARED:
            require(set(item) <= ENTRY_KEYS | {'description'}, 'RESPONSE_SKILLS')
            require('description' not in item or isinstance(item['description'], str), 'RESPONSE_SKILLS')
        else:
            plugin = item.get('pluginId')
            require(plugin is None or (isinstance(plugin, str) and len(plugin) <= 512), 'PLUGIN_SCHEMA')
            require(item['name'] not in selected or plugin in (None, ''), 'SELECTED_PLUGIN_UNSUPPORTED')
    return skills


def compare(expected, observed):
    """Host-neutral selected-subset comparison, not isolation or native proof."""
    selected = {s['name']: s for s in expected}
    matched = 0
    issues = set()
    for name, wanted in selected.items():
        found = [s for s in observed if s['name'] == name]
        if not found:
            issues.add('MISSING_SKILL')
        elif len(found) != 1:
            issues.add('DUPLICATE_SELECTED_SKILL')
        elif found[0]['enabled'] is not True:
            issues.add('DISABLED_SKILL')
        elif found[0]['path'] != wanted['path']:
            issues.add('SKILL_PATH_MISMATCH')
        else:
            matched += 1
    return matched, sum(s['name'] not in selected for s in observed), sorted(issues)


def check(expected_raw, response_raw):
    out = result()
    try:
        for field, raw in (('expected_sha256', expected_raw), ('response_sha256', response_raw)):
            require(isinstance(raw, bytes) and len(raw) <= MAX_BYTES, 'INPUT_SIZE')
            out[field] = digest(raw)
        expected = parse(expected_raw)
        profile = expected_profile(expected)
        out.update(profile=profile, provider=expected['provider'],
                   evidence_class='DECLARED_INVENTORY' if profile == DECLARED else 'NATIVE_FORMAT_UNVERIFIED_CAPTURE')
        require(expected['response_sha256'] == out['response_sha256'], 'RESPONSE_DIGEST_MISMATCH')
        observed = normalize(parse(response_raw), expected, profile)
        matched, additional, issues = compare(expected['skills'], observed)
        out.update(status='MISMATCH' if issues else 'RESPONSE_MATCH', expected_count=len(expected['skills']),
                   matched_count=matched, additional_skill_count=additional, issues=issues)
    except Invalid as exc:
        out['issues'] = [str(exc)]
    return out


def read_input(value):
    """Read one explicit regular file; never follows a JSON-contained path."""
    require(path(value), 'INPUT_PATH')
    p = PurePosixPath(value)
    for ancestor in reversed((p, *p.parents)):
        require(not stat.S_ISLNK(os.lstat(str(ancestor)).st_mode), 'INPUT_PATH')
    before = os.lstat(value)
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES, 'INPUT_FILE')
    fd = os.open(value, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        current = os.fstat(fd)
        require(stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'INPUT_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        require(len(raw) <= MAX_BYTES and len(raw) == after.st_size
                and (current.st_size, current.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid('CLI_ARGUMENTS')


def main(argv=None):
    out = result()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--expected', required=True)
        parser.add_argument('--response', required=True)
        args = parser.parse_args(argv)
        expected_raw = read_input(args.expected)
        out['expected_sha256'] = digest(expected_raw)
        response_raw = read_input(args.response)
        out = check(expected_raw, response_raw)
    except Invalid as exc:
        out['issues'] = [str(exc)]
    except (OSError, UnicodeError, ValueError, RecursionError):
        out['issues'] = ['INPUT_UNAVAILABLE']
    print(json.dumps(out, ensure_ascii=True, sort_keys=True))
    return 0 if out['status'] == 'RESPONSE_MATCH' else 1


if __name__ == '__main__':
    sys.exit(main())
