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


if __name__ == '__main__':
    unittest.main()
