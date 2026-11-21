"""Structural reference checks only; no claim about model selection or recipe execution."""
import copy
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
BASE = 'skills/arch/code-review/references/languages/'
NAMES = ('index.md', 'typescript.md', 'php.md', 'python.md', 'rust.md', 'go.md',
         'frameworks/react.md', 'frameworks/laravel.md', 'frameworks/django.md',
         'frameworks/fastapi.md')
EXPECTED = {BASE + name for name in NAMES}
ORIGINS = 'provenance/language-reference-origins.json'
TEST = 'tests/collection/test_language_references.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root):
    """Check bounded local documents, inventory and provenance, without following external URLs."""
    root = Path(root).resolve()
    issues = []
    actual = {p.relative_to(root).as_posix() for p in (root / BASE).rglob('*')
              if p.is_file() or p.is_symlink()}
    if actual != EXPECTED:
        issues.append('inventory')
    for name in sorted(EXPECTED):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            issues.append('unsafe-or-missing:' + name)
            continue
        limit = 8192 if name == BASE + 'index.md' else 10240 if '/frameworks/' in name else 12288
        if not 0 < path.stat().st_size <= limit:
            issues.append('budget:' + name)
            continue
        for raw in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            target = unquote(raw.split('#', 1)[0])
            if not target or target.startswith(('https://', 'mailto:')):
                continue
            dest = path.parent / target
            if (Path(target).is_absolute() or ':' in target or '\\' in target or
                    not dest.resolve().is_relative_to(root) or not dest.is_file()):
                issues.append('link:' + name)
    try:
        origins = json.loads((root / ORIGINS).read_text())
        rows = origins['records']
        if origins['schema_version'] != 1 or not isinstance(rows, list):
            raise ValueError('schema')
        destinations = [r['destination'] for r in rows]
        if len(destinations) != len(EXPECTED) or set(destinations) != EXPECTED:
            issues.append('origins-inventory')
        for row in rows:
            name = row['destination']
            if name not in EXPECTED:
                continue
            path = root / name
            if not path.is_file() or row['sha256'] != digest(path):
                issues.append('origin-digest:' + name)
            if row['origin_kind'] != 'owner-authored' or not row['conceptual_sources'] or not row['adaptation_notes']:
                issues.append('origin-fields:' + name)
        manifest = json.loads((root / 'release-manifest.json').read_text())['files']
        for name in sorted(EXPECTED | {ORIGINS, TEST}):
            matches = [r for r in manifest if r['path'] == name]
            component = 'skills' if name in EXPECTED else 'core'
            if (len(matches) != 1 or matches[0]['component'] != component or
                    not (root / name).is_file() or matches[0]['sha256'] != digest(root / name)):
                issues.append('manifest:' + name)
    except (OSError, ValueError, KeyError, TypeError):
        issues.append('metadata')
    return issues


class LanguageReferencesTests(unittest.TestCase):
    def test_repository_inventory_links_origins_and_packaging(self):
        self.assertEqual([], validate(ROOT))


class StructuralNegativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in EXPECTED | {TEST}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture\n')
        # A complete navigation index and a backlink are valid, not eager loading.
        (self.root / BASE / 'index.md').write_text('\n'.join('[ref](' + n + ')' for n in NAMES))
        (self.root / BASE / 'frameworks/react.md').write_text('[index](../index.md)\n')
        self.origins = dict(schema_version=1, records=[dict(destination=n,
            sha256=digest(self.root / n), origin_kind='owner-authored',
            conceptual_sources=[dict(path='synthetic')], adaptation_notes='Synthetic fixture')
            for n in sorted(EXPECTED)])
        self.save()

    def save(self):
        path = self.root / ORIGINS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.origins))
        files = [dict(path=n, sha256=digest(self.root / n),
                      component='skills' if n in EXPECTED else 'core')
                 for n in sorted(EXPECTED | {ORIGINS, TEST}) if (self.root / n).is_file()]
        (self.root / 'release-manifest.json').write_text(json.dumps(dict(files=files)))

    def test_all_framework_links_and_backlink_are_valid(self):
        self.assertEqual([], validate(self.root))

    def test_removed_target(self):
        (self.root / BASE / 'php.md').unlink()
        self.assertIn('inventory', validate(self.root))

    def test_escaping_link(self):
        (self.root / BASE / 'php.md').write_text('[bad](../../../../../../outside.md)')
        self.assertIn('link:' + BASE + 'php.md', validate(self.root))

    def test_absolute_link(self):
        (self.root / BASE / 'php.md').write_text('[bad](/etc/passwd)')
        self.assertIn('link:' + BASE + 'php.md', validate(self.root))

    def test_missing_origin(self):
        self.origins['records'].pop()
        self.save()
        self.assertIn('origins-inventory', validate(self.root))

    def test_duplicate_origin(self):
        self.origins['records'].append(copy.deepcopy(self.origins['records'][0]))
        self.save()
        self.assertIn('origins-inventory', validate(self.root))

    def test_wrong_origin_digest(self):
        row = self.origins['records'][0]
        row['sha256'] = '0' * 64
        self.save()
        self.assertIn('origin-digest:' + row['destination'], validate(self.root))

    def test_extra_unrecorded_payload(self):
        (self.root / BASE / 'extra.md').write_text('not recorded')
        self.assertIn('inventory', validate(self.root))

    def test_oversize_document(self):
        (self.root / BASE / 'go.md').write_bytes(b'x' * 12289)
        self.assertIn('budget:' + BASE + 'go.md', validate(self.root))

    def test_wrong_component(self):
        path = self.root / 'release-manifest.json'
        m = json.loads(path.read_text())
        next(r for r in m['files'] if r['path'] == ORIGINS)['component'] = 'skills'
        path.write_text(json.dumps(m))
        self.assertIn('manifest:' + ORIGINS, validate(self.root))

    def test_unknown_origin_kind(self):
        row = self.origins['records'][0]
        row['origin_kind'] = 'upstream-copy'
        self.save()
        self.assertIn('origin-fields:' + row['destination'], validate(self.root))

    def test_empty_document(self):
        (self.root / BASE / 'go.md').write_bytes(b'')
        self.assertIn('budget:' + BASE + 'go.md', validate(self.root))

    def test_index_and_framework_budgets(self):
        for name, limit in [('index.md', 8192), ('frameworks/react.md', 10240)]:
            with self.subTest(name=name):
                (self.root / BASE / name).write_bytes(b'x' * (limit + 1))
                self.assertIn('budget:' + BASE + name, validate(self.root))

    def test_missing_file_reports_unsafe_and_manifest(self):
        name = BASE + 'go.md'
        (self.root / name).unlink()
        try:
            issues = validate(self.root)
        except Exception as exc:
            self.fail('Missing document must return issues, not raise ' + type(exc).__name__)
        self.assertIn('unsafe-or-missing:' + name, issues)
        self.assertIn('manifest:' + name, issues)

    def test_symlink_to_internal_file_rejected(self):
        name = BASE + 'go.md'
        target = self.root / 'target.md'
        target.write_text('fixture\n')
        (self.root / name).unlink()
        (self.root / name).symlink_to(target)
        self.assertIn('unsafe-or-missing:' + name, validate(self.root))

    def test_parent_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            parent = self.root / BASE / 'frameworks'
            for p in parent.iterdir():
                Path(external, p.name).write_bytes(p.read_bytes())
                p.unlink()
            parent.rmdir()
            parent.symlink_to(external, target_is_directory=True)
            self.assertIn('unsafe-or-missing:' + BASE + 'frameworks/react.md', validate(self.root))

    def test_absolute_internal_link_rejected(self):
        path = self.root / BASE / 'go.md'
        path.write_text('[absolute](' + str(self.root / BASE / 'php.md') + ')')
        self.assertIn('link:' + BASE + 'go.md', validate(self.root))

    def test_encoded_escape_link_rejected(self):
        (self.root / BASE / 'go.md').write_text('[bad](%2Fetc%2Fpasswd)')
        self.assertIn('link:' + BASE + 'go.md', validate(self.root))

    def test_special_local_link_names_rejected(self):
        for target in ['foo:bar.md', 'foo\\bar.md']:
            with self.subTest(target=target):
                (self.root / BASE / target).write_text('fixture')
                (self.root / BASE / 'go.md').write_text('[bad](' + target + ')')
                self.assertIn('link:' + BASE + 'go.md', validate(self.root))

    def test_missing_local_link_rejected(self):
        (self.root / BASE / 'go.md').write_text('[bad](absent.md)')
        self.assertIn('link:' + BASE + 'go.md', validate(self.root))

    def test_fragment_and_external_links_are_navigation(self):
        path = self.root / BASE / 'go.md'
        path.write_text('[section](#section) [remote](https://example.invalid/doc) [mail](mailto:review@example.invalid)')
        next(r for r in self.origins['records'] if r['destination'] == BASE + 'go.md')['sha256'] = digest(path)
        self.save()
        self.assertEqual([], validate(self.root))

    def test_schema_version_rejected(self):
        self.origins['schema_version'] = 2
        self.save()
        self.assertIn('metadata', validate(self.root))

    def test_records_type_rejected(self):
        self.origins['records'] = {}
        self.save()
        self.assertIn('metadata', validate(self.root))

    def test_missing_metadata_rejected(self):
        (self.root / ORIGINS).unlink()
        self.assertIn('metadata', validate(self.root))

    def test_malformed_metadata_rejected(self):
        (self.root / ORIGINS).write_text('{')
        self.assertIn('metadata', validate(self.root))

    def test_origin_missing_source_or_notes_rejected(self):
        row = self.origins['records'][0]
        for key, empty in [('conceptual_sources', []), ('adaptation_notes', '')]:
            with self.subTest(key=key):
                original = row[key]
                row[key] = empty
                self.save()
                self.assertIn('origin-fields:' + row['destination'], validate(self.root))
                row[key] = original

    def test_manifest_duplicate_missing_and_hash(self):
        path = self.root / 'release-manifest.json'
        original = json.loads(path.read_text())
        name = ORIGINS
        for defect in ['duplicate', 'missing', 'hash']:
            with self.subTest(defect=defect):
                m = copy.deepcopy(original)
                row = next(r for r in m['files'] if r['path'] == name)
                if defect == 'duplicate':
                    m['files'].append(copy.deepcopy(row))
                elif defect == 'missing':
                    m['files'].remove(row)
                else:
                    row['sha256'] = '0' * 64
                path.write_text(json.dumps(m))
                try:
                    issues = validate(self.root)
                except Exception as exc:
                    self.fail('Manifest validation must return issues, not raise ' + type(exc).__name__)
                self.assertIn('manifest:' + name, issues)

    def test_relative_link_to_existing_external_file(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'outside.md'
            target.write_text('outside')
            path = self.root / BASE / 'go.md'
            path.write_text('[bad](' + os.path.relpath(target, path.parent) + ')')
            self.assertIn('link:' + BASE + 'go.md', validate(self.root))

    def test_encoded_internal_link_resolves(self):
        target = self.root / 'with space.md'
        target.write_text('fixture')
        path = self.root / BASE / 'go.md'
        path.write_text('[valid](../../../../../with%20space.md)')
        next(r for r in self.origins['records'] if r['destination'] == BASE + 'go.md')['sha256'] = digest(path)
        self.save()
        self.assertEqual([], validate(self.root))

    def test_unknown_origin_is_not_resolved(self):
        self.origins['records'][0]['destination'] = '../untrusted.md'
        self.save()
        self.assertEqual(['origins-inventory'], validate(self.root))


if __name__ == '__main__':
    unittest.main()
