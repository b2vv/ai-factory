"""Every reason the helper can emit is listed in the contract (T07 L9).

The canonical set below is checked two ways: each reason appears in contract.md's reason tables, and the helper's
single-quoted kebab-case literals, minus the known non-reason literals, are exactly this set, so a new reason in any
syntactic form fails here until the contract lists it.
"""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/ui-measurements'
REASONS = {
    'viewport-unavailable', 'route-mismatch', 'state-not-settled', 'fonts-not-settled',          # call level
    'invalid-selector', 'missing-target', 'ambiguous-target',                                     # matching
    'non-html-target', 'unrendered-target', 'animation-state-unavailable', 'active-animation',     # render
    'unsupported-text-target', 'unsupported-compositing', 'unsupported-paint', 'unsupported-pseudo-paint',
    'non-opaque-or-non-srgb',                                                                     # contrast
    'stable-fixture-not-established', 'oversized-text',                                           # text
    'oversized-value', 'report-budget', 'budget', 'unsupported-check',                            # budgets, defensive
}
NOT_REASONS = {
    # style property names and derived keys
    'font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing', 'text-transform', 'font-family',
    'background-color', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'margin-top', 'margin-right',
    'margin-bottom', 'margin-left', 'row-gap', 'column-gap', 'min-width', 'min-height', 'border-top-width',
    'border-right-width', 'border-bottom-width', 'border-left-width', 'border-top-color', 'border-right-color',
    'border-bottom-color', 'border-left-color', 'border-top-left-radius', 'border-top-right-radius',
    'border-bottom-right-radius', 'border-bottom-left-radius', 'box-shadow', 'font-family-first', 'box-shadow-layers',
    # box and media keywords, expected-field values
    'border-box', 'padding-box', 'no-preference', 'not-requested', 'fit-or-local-scroll',
}


def literals(source):
    return set(re.findall(r"'([a-z]+(?:-[a-z]+)+)'", source))


class ContractReasons(unittest.TestCase):
    def setUp(self):
        self.source = (SKILL / 'scripts/measure-ui.cjs').read_text()
        self.contract = (SKILL / 'references/contract.md').read_text()

    def test_helper_reasons_are_the_canonical_set(self):
        found = literals(self.source) - NOT_REASONS
        # `budget` is one word, so it is not a kebab literal; check it separately.
        self.assertIn("'budget'", self.source)
        self.assertEqual(REASONS - {'budget'}, found)

    def test_contract_lists_every_reason(self):
        table = {m for row in self.contract.splitlines() if row.startswith('|')
                 for m in re.findall(r'`([a-z]+(?:-[a-z]+)*)`', row.split('|')[1])}
        self.assertEqual(set(), REASONS - table)

    def test_scan_catches_a_new_reason(self):
        self.assertIn('brand-new-reason', literals(self.source + "\nresult.reason = 'brand-new-reason';") - NOT_REASONS)


if __name__ == '__main__':
    unittest.main()
