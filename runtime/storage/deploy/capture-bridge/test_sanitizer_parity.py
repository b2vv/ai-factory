"""Differential corpus against the actual Go source patterns (stdlib-only Go runner).

Explicitly skipped without Go/source; never claims parity from Python tests alone.
"""
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture_queue import contains_credential

class Parity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('go'),'Go toolchain unavailable')
    def test_go_source_corpus(self):
        source=Path(__file__).resolve().parents[2]/'internal/capture/sanitize.go'
        if not source.exists():self.skipTest('server source not in installed component')
        patterns=re.findall(r'regexp.MustCompile\(`([^`]+)`\)',source.read_text())
        self.assertEqual(len(patterns),7)
        corpus=['safe message','toKen: value','paſſword: value','token\v: value','apİ_key: value','apı_key: value','ſecret: value',
                '-----BEGIN PRIVATE KEY-----','sk-abcdefghijklmnop','ghp_abcdefghijklmnop','https://user:pass@host',
                'eyJaaa.abcdef.abcdef','bearer abcdefghijkl','authorization: canary']
        for prefix,label,space in itertools.product(('', 'a', ' ', 'é','K','ſ','İ','ı'),
                ('token','toKen','password','paſſword','api_key','apİ_key','apı_key','secret','ſecret','cookie','authorization'),
                ('', ' ', '\t','\n','\r','\f','\v','\u00a0','\u2003')):
            corpus.append(prefix+label+space+': test-canary')
        code='''package main
import("encoding/json";"os";"regexp")
func main(){ var texts []string; json.NewDecoder(os.Stdin).Decode(&texts)
patterns:=[]string{'''+','.join('`'+p+'`' for p in patterns)+'''}
out:=make([]bool,len(texts)); for i,t:=range texts { for _,p:=range patterns { if regexp.MustCompile(p).MatchString(t){out[i]=true;break} } }; json.NewEncoder(os.Stdout).Encode(out) }
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'parity.go';path.write_text(code)
            result=subprocess.run(['go','run',str(path)],input=json.dumps(corpus),text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        expected=json.loads(result.stdout)
        mismatches=[repr(t) for t,want in zip(corpus,expected) if contains_credential(t)!=want]
        self.assertEqual(mismatches,[])
        print('Go/Python sanitizer parity:',len(corpus),'cases')

if __name__=='__main__':unittest.main()
