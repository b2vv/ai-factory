"""Design skills name the same owner for each gate and use one severity scale (T10)."""
import re, unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / 'skills'


def flat(path):
    return ' '.join((SKILLS / path).read_text().split())


class Vocabulary(unittest.TestCase):
    def test_catalog_is_never_called_the_method(self):
        for path in SKILLS.rglob('*.md'):
            self.assertNotIn('the catalog is the method layer', ' '.join(path.read_text().split()), path)

    def test_mockup_fidelity_owner_is_reference_ui_reconstruction(self):
        ux = flat('ux-review/SKILL.md')
        self.assertNotIn('mockup fidelity to design-pass', ux)
        self.assertNotIn('(that is `design-pass`)', ux)
        self.assertIn('mockup fidelity to reference-ui-reconstruction', ux)
        self.assertRegex(ux, r'\[`reference-ui-reconstruction`\]\(\.\./reference-ui-reconstruction/SKILL\.md\) \(mockup reconstruction')

    def test_concept_fit_outcomes_have_their_owners(self):
        ir = flat('interface-review/SKILL.md')
        self.assertNotIn('lens, which owns them', ir)
        self.assertRegex(ir, r'anti-slop-design owns the visual-fit verdict and design-pass .{0,40}carries the compatibility outcome')

    def test_one_severity_scale(self):
        self.assertNotIn('As in `anti-slop-design`, the interface is not', flat('ux-review/SKILL.md'))
        self.assertIn('blocker+major list (scale in step 3, Rank)', flat('ux-review/SKILL.md'))
        self.assertIn('use the ux-review scale (step 3, Rank)', flat('anti-slop-design/SKILL.md'))

    def test_dials_not_applicable_to_targeted_changes(self):
        self.assertIn('N/A for a design-pass Targeted change', flat('anti-slop-design/SKILL.md'))

    def test_concept_fit_has_a_place_without_a_task_record(self):
        cf = flat('anti-slop-design/references/concept-fit.md')
        self.assertGreaterEqual(cf.count('design-pass final report'), 2)
        self.assertIn('concept card lines and concept-fit evidence records', flat('design-pass/SKILL.md'))


    def test_one_contrast_evidence_rule(self):
        # L16a, owner 23.11: offer a ui-measurements contrast run (also beside a project measurement); run after a yes.
        ux = flat('ux-review/SKILL.md')
        self.assertIn('Contrast evidence is a measurement of the actual paint', ux)
        self.assertIn('also when the project has its own measurement', ux)
        self.assertIn('run it only after a yes', ux)
        self.assertIn('contrast stays NOT_TESTED, never PASS', ux)
        self.assertIn('when the owner accepts the offered run', flat('ui-measurements/SKILL.md'))
        self.assertIn('when the owner accepted the offered run', flat('interface-review/SKILL.md'))
        self.assertIn('offer the owner a ui-measurements `contrast` run', flat('ui-audit/SKILL.md'))
        self.assertNotIn('only for missing supported measurements', flat('anti-slop-design/SKILL.md'))
        self.assertIn('when the owner accepted the offered run', flat('ship/frontend-design/SKILL.md'))
        for path in ('interface-review/SKILL.md', 'ui-audit/SKILL.md', 'design-pass/SKILL.md', 'anti-slop-design/SKILL.md'):
            text = flat(path)
            self.assertIn('ux-review measurement rules', text, path)
            self.assertNotIn('Contrast: the `measureUI` `contrast` result;', text, path)
        for path in ('ux-review/SKILL.md', 'interface-review/SKILL.md', 'ui-audit/SKILL.md', 'design-pass/SKILL.md',
                     'anti-slop-design/SKILL.md', 'ui-measurements/SKILL.md', 'ship/frontend-design/SKILL.md'):
            self.assertNotRegex(flat(path), r'(?i)always (run|use) (the )?\[?ui-measurements|run always', path)


if __name__ == '__main__':
    unittest.main()
