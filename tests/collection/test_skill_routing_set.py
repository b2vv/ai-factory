"""The skill-routing eval set names real skills, covers the confusable pairs and is scored mechanically (T11)."""
import importlib.util, json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / 'evals' / 'skill-routing'
spec = importlib.util.spec_from_file_location('run_routing', EVALS / 'run_routing.py')
run_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_routing)


def skill_descriptions():
    found = {}
    for path in (ROOT / 'skills').rglob('SKILL.md'):
        head = path.read_text().split('\n---', 1)[0]
        name = re.search(r'^name:\s*["\']?([\w-]+)', head, re.M)
        desc = re.search(r'^description:\s*(.+)$', head, re.M)
        if name and desc:
            found[name.group(1)] = desc.group(1)
    return found


class RoutingSet(unittest.TestCase):
    cases = run_routing.load_cases()

    def by_id(self, case_id):
        return next(c for c in self.cases if c['id'] == case_id)

    def test_names_are_real_skills_and_ids_unique(self):
        skills = skill_descriptions()
        ids = [c['id'] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.cases:
            for name in [case['expected_skill'], *case['not_instead']]:
                self.assertIn(name, skills, case['id'])
            self.assertNotIn(case['expected_skill'], case['not_instead'], case['id'])

    def test_audit_gaps_are_closed(self):
        self.assertIn('ui-audit', self.by_id('design-audit')['not_instead'])
        self.assertIn('design-pass', self.by_id('design-reference')['not_instead'])
        self.assertIn('ui-audit', self.by_id('design-measure')['not_instead'])
        self.assertTrue({'ux-review', 'anti-slop-design'} <= set(self.by_id('design-find')['not_instead']))
        expected = {'design-product-audit': 'interface-review', 'design-method': 'frontend-design',
                    'review-crg': 'crg-review-changes', 'design-critique': 'interface-review'}
        for case_id, skill in expected.items():
            self.assertEqual(self.by_id(case_id)['expected_skill'], skill)

    def test_no_trigger_phrase_is_shared(self):
        owners = {}
        for name, desc in skill_descriptions().items():
            if 'Triggers:' not in desc:
                continue
            for phrase in re.findall(r'[“"]([^”"]+)[”"]', desc.split('Triggers:', 1)[1]):
                key = phrase.strip().lower()
                if key == name:
                    continue
                self.assertNotIn(key, owners, f'{name} and {owners.get(key)} share "{phrase}"')
                owners[key] = name

    def test_only_interface_review_critiques_a_screen(self):
        interface = {'anti-slop-design', 'interface-review', 'ux-review', 'ui-audit', 'design-pass', 'frontend-design',
                     'reference-ui-reconstruction', 'ui-measurements'}
        owners = {name for name, desc in skill_descriptions().items()
                  if name in interface and re.search(r'[“"]critique the ', desc, re.I)}
        self.assertEqual(owners, {'interface-review'})

    def test_interface_review_advertises_audit_mode(self):
        # Routing follow-up F1 (2026-11-23): the product-audit case loaded no skill twice.
        desc = skill_descriptions()['interface-review']
        self.assertIn("read-only audit of an existing product's screens", desc)
        self.assertIn('(audit mode)', desc)

    def test_fixture_is_realistic_and_deterministic(self):
        builder = EVALS / 'make_fixture.py'
        with tempfile.TemporaryDirectory() as tmp:
            heads = []
            for name in ('a', 'b'):
                dest = Path(tmp) / name
                subprocess.run([sys.executable, '-I', str(builder), str(dest)], check=True, capture_output=True)
                heads.append(subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD']).strip())
            self.assertEqual(heads[0], heads[1])
            dest = Path(tmp) / 'a'
            self.assertEqual(b'feature/csv-export', subprocess.check_output(['git', '-C', str(dest), 'branch', '--show-current']).strip())
            screens = list((dest / 'ui' / 'admin').glob('*.html'))
            self.assertGreaterEqual(len(screens), 6)
            for rel in ('PLAN.md', 'REVIEW-COMMENTS.md', 'src/billing/documents.py', 'ui/dashboard.html',
                        'ui/reference/settings-mockup.png', 'ui/checkout/payment.html'):
                self.assertTrue((dest / rel).is_file(), rel)
            self.assertGreaterEqual((dest / 'src/billing/documents.py').read_text().count('class '), 5)
            again = subprocess.run([sys.executable, '-I', str(builder), str(dest)], capture_output=True)
            self.assertNotEqual(0, again.returncode)  # never writes into an existing directory

    def test_parser_reads_the_first_skill(self):
        init = json.dumps({'type': 'system', 'subtype': 'init', 'model': 'm-1'})
        bash = json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}}]}})
        skill = lambda s: json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': 'x'}, {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': s}}]}})
        self.assertEqual(run_routing.first_skill([init, bash, skill('plugin:ux-review'), skill('ui-audit')]), 'ux-review')
        self.assertEqual(run_routing.first_skill([init, bash, 'not json', '']), 'none')
        self.assertEqual(run_routing.trace_model([init]), 'm-1')

    def test_recorded_results_cover_every_case(self):
        for path in (EVALS / 'results').glob('*.json'):
            data = json.loads(path.read_text())
            self.assertEqual(sorted(r['id'] for r in data['results']), sorted(c['id'] for c in self.cases), path)
            for r in data['results']:
                self.assertIn(r['outcome'], {'PASS', 'NO_SKILL', 'FAIL_NOT_INSTEAD', 'FAIL_OTHER', 'NOT_RUN'})


if __name__ == '__main__':
    unittest.main()
