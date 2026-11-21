"""Static contract regressions; live Go-template behavior remains runtime-gated."""
import os
from pathlib import Path
import unittest

ROOT=Path(os.environ.get('AF_TEST_BASE',str(Path(__file__).resolve().parents[2])))
class BootstrapNullTests(unittest.TestCase):
    def test_each_optional_collection_has_explicit_empty_branch(self):
        text=(ROOT/'runtime/scanners/scan.sh').read_text()
        for key in ('Devices','DeviceRequests','VolumesFrom','PortBindings'):
            with self.subTest(key=key):
                expected='{{if .HostConfig.'+key+'}}{{len .HostConfig.'+key+'}}{{else}}0{{end}}'
                self.assertEqual(text.count(expected),1)
    def test_nonempty_branch_retains_actual_count_and_exact_zero_gate(self):
        text=(ROOT/'runtime/scanners/scan.sh').read_text()
        self.assertIn('|created|0|0|0|0||private"',text)
        self.assertIn('[ "$(cat "$CONTROL_OUT")" = "$expected_fields" ] || finish 3',text)
        for key in ('Devices','DeviceRequests','VolumesFrom','PortBindings'):
            self.assertIn('{{len .HostConfig.'+key+'}}{{else}}0{{end}}',text)
    def test_bootstrap_guard_precedes_start(self):
        text=(ROOT/'runtime/scanners/scan.sh').read_text()
        self.assertLess(text.index('expected_fields='),text.index('checked docker start "$cid"'))
        self.assertLess(text.index('"$expected_fields" ] || finish 3'),text.index('checked docker start "$cid"'))
