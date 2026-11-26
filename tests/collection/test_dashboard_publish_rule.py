"""Projects on the dashboard publish their status (T36): a before-skill rule in agent-entry, checked by the reminder."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DashboardPublishRule(unittest.TestCase):
    def rule(self):
        text = (ROOT / 'rules/agent-entry.md').read_text()
        before = text.split('## How to add a rule', 1)[0]
        m = re.search(r'^### \d+\. Projects on the dashboard publish their status$(.*?)(?=^##|\Z)', before, re.M | re.S)
        self.assertIsNotNone(m, 'the rule must be a before-skill rule in agent-entry')
        return ' '.join(m.group(1).split())

    def test_rule_names_scope_trigger_command_and_check(self):
        rule = self.rule()
        for phrase in ('Dashboard status for this project', 'After your own commit', 'stage of the primary task',
                       'kit.py project status', 'docs/dashboard-status.md', 'publishes nothing', 'Stop reminder',
                       'Claude Code and Codex', 'why no publish is needed'):
            self.assertIn(phrase, rule)

    def test_reminder_script_matches_the_rule(self):
        script = (ROOT / 'tools/dashboard_reminder.py').read_text()
        for phrase in ('kit.py project status', 'docs/dashboard-status.md', 'why no publish is needed'):
            self.assertIn(phrase, script)


if __name__ == '__main__':
    unittest.main()
