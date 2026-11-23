"""Relative links in skills are opened from the skill's real location (T12, owner decision D3 a)."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def flat(path):
    return ' '.join((ROOT / path).read_text().split())


class LinkBase(unittest.TestCase):
    def test_agent_entry_states_the_rule_before_skills(self):
        text = (ROOT / 'rules/agent-entry.md').read_text()
        before = text.split('## How to add a rule', 1)[0]
        m = re.search(r'^### \d+\. Open a skill.s relative links from its real location$(.*?)(?=^##|\Z)', before, re.M | re.S)
        self.assertIsNotNone(m, 'the rule must be a before-skill rule in agent-entry')
        rule = ' '.join(m.group(1).split())
        for phrase in ('realpath', 'never join `..` to the symlinked', 'not missing until it also fails from the real path',
                       '<kit>/skills/**/<name>/SKILL.md'):
            self.assertIn(phrase, rule)

    def test_design_pass_opens_helpers_from_the_real_location(self):
        text = flat('skills/design-pass/SKILL.md')
        self.assertNotIn('relative to this directory', text)
        self.assertIn("relative to this file's real location", text)


if __name__ == '__main__':
    unittest.main()
