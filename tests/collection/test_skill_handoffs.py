"""ui-audit handoffs are stated on both sides (T09): interface-review, design-pass, semantic-consistency.

Each check reads only the section the statement belongs to, so a sentence elsewhere in the file does not satisfy it.
"""
import re, unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / 'skills'


def section(path, heading):
    """The text under a `## ` heading that starts with `heading`, up to the next `## ` heading."""
    text = (SKILLS / path).read_text()
    m = re.search(r'^## ' + re.escape(heading) + r'.*?$(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not m: raise AssertionError(f'{path}: no section {heading!r}')
    return ' '.join(m.group(1).split())


class Handoffs(unittest.TestCase):
    def test_interface_review_takes_requirement_failures_whatever_the_answer(self):
        s = section('interface-review/SKILL.md', 'When to use')
        self.assertIn('ui-audit', s)
        self.assertRegex(s, r'accessibility, keyboard or functional requirement')
        self.assertRegex(s, r'whatever the owner answered')
        self.assertRegex(s, r'dated limitation')

    def test_design_pass_brief_and_done_name_ui_audit(self):
        brief = section('design-pass/SKILL.md', '2. Brief')
        done = section('design-pass/SKILL.md', '6. Done')
        self.assertIn('ui-audit', brief)
        self.assertRegex(brief, r'requirement failures')
        self.assertIn('ui-audit', done)
        self.assertRegex(done, r'recorded owner decision|accepted dated limitation')

    def test_ui_audit_records_consistency_decisions_by_role(self):
        s = section('ui-audit/SKILL.md', '4. Report')
        self.assertRegex(s, r'role ID, cause and key')
        self.assertIn('semantic-consistency', s)
        self.assertRegex(s, r'by role ID')

    def test_semantic_consistency_finds_ui_audit_decisions(self):
        s = section('ux-review/references/semantic-consistency.md', '5. Outputs')
        self.assertIn('ui-audit', s)

    def test_section_scoping(self):
        with self.assertRaises(AssertionError):
            section('ui-audit/SKILL.md', 'No such heading')


if __name__ == '__main__':
    unittest.main()
