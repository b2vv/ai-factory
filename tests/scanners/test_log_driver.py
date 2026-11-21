"""Contract tests; daemon start acceptance is a separate runtime gate."""
import ast
import os
from pathlib import Path
import unittest
ROOT=Path(os.environ.get('AF_TEST_BASE',str(Path(__file__).resolve().parents[2])))
class LogDriverTests(unittest.TestCase):
    def test_helper_and_updater_create_disable_compression_keep_limits(self):
        shell=(ROOT/'runtime/scanners/scan.sh').read_text()
        commands=[x for x in shell.splitlines() if 'docker create ' in x]
        self.assertEqual(len(commands),2)
        for command in commands:self.assertIn('--log-driver local --log-opt max-size=1m --log-opt max-file=1 --log-opt compress=false',command)
    def test_engine_render_and_inspect_guards_use_exact_log_options(self):
        source=(ROOT/'runtime/scanners/container_helper.py').read_text();tree=ast.parse(source)
        options=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Dict):
                try:value=ast.literal_eval(node)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and 'max-file' in value:options.append(value)
        self.assertEqual(len(options),3)
        for value in options:self.assertEqual(value,{'max-size':'1m','max-file':'1','compress':'false'})
        self.assertEqual(source.count("'log bounds mismatch'"),2)
    def test_helper_guard_precedes_start(self):
        shell=(ROOT/'runtime/scanners/scan.sh').read_text()
        guard='{"Type":"local","Config":{"compress":"false","max-file":"1","max-size":"1m"}}'
        self.assertIn(guard,shell)
        self.assertLess(shell.index(guard),shell.index('checked docker start "$cid"'))
