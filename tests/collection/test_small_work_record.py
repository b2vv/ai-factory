"""Small work leaves a record in every connected project (T34): a before-skill rule in agent-entry."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SmallWorkRecord(unittest.TestCase):
    def rule(self):
        text = (ROOT / 'rules/agent-entry.md').read_text()
        before = text.split('## How to add a rule', 1)[0]
        m = re.search(r'^### \d+\. Small work leaves a record$(.*?)(?=^##|\Z)', before, re.M | re.S)
        self.assertIsNotNone(m, 'the rule must be a before-skill rule in agent-entry')
        return ' '.join(m.group(1).split())

    def test_rule_names_when_where_and_what(self):
        rule = self.rule().lower()
        for phrase in ('before you report the result', 'more than one step', 'what changed', 'existing task record', 'no second tracker',
                       "owner's words", 'not checked', 'outside the repository', 'trivial one-step'):
            self.assertIn(phrase, rule)

    def test_rule_is_reachable_from_the_existing_small_route(self):
        # The pre-code checkpoint already says "Small keeps one record"; the entry rule makes it happen at the end too.
        self.assertIn('pre-code-checkpoint.md', self.rule())


if __name__ == '__main__':
    unittest.main()
