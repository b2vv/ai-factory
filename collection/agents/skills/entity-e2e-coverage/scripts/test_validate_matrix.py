import copy,json,unittest
from pathlib import Path
from validate_matrix import validate

CASES=json.loads((Path(__file__).resolve().parents[1]/'references/cases.json').read_text())

class CoverageTests(unittest.TestCase):
    def test_scenarios(self):
        for case,complete in zip(CASES,[False,True,True,False,False]):
            with self.subTest(case=case['case']):
                self.assertEqual(not validate(case['contract'],case['report']),complete)

    def test_false_passes(self):
        for fault in ('surface','state','channel','assertion','revision','diff','run_id','environment','fixture_id','executed','skip','duplicate_assertion'):
            c=copy.deepcopy(CASES[1]['contract']);r=copy.deepcopy(CASES[1]['report'])
            row=r['results'][2];ev=row['evidence']
            if fault=='skip':row['status']='SKIP'
            elif fault=='executed':ev[fault]=False
            elif fault=='duplicate_assertion':ev['assertion_id']=r['results'][0]['evidence']['assertion_id']
            else:ev[fault]='different'
            with self.subTest(fault=fault):self.assertTrue(validate(c,r))

    def test_missing_and_duplicate_rows(self):
        c=CASES[1]['contract'];r=copy.deepcopy(CASES[1]['report']);r['results'].pop()
        self.assertTrue(validate(c,r))
        r=copy.deepcopy(CASES[1]['report']);r['results'].append(r['results'][0])
        self.assertTrue(validate(c,r))

    def test_required_cannot_be_na(self):
        r=copy.deepcopy(CASES[1]['report']);r['results'][2]={'id':r['results'][2]['id'],'status':'N/A'}
        self.assertTrue(validate(CASES[1]['contract'],r))

    def test_na_needs_source(self):
        c=copy.deepcopy(CASES[2]['contract']);c['rows'][2].pop('na_source')
        self.assertTrue(validate(c,CASES[2]['report']))

    def test_stale_report(self):
        r=copy.deepcopy(CASES[1]['report']);r['diff']='new-diff'
        self.assertTrue(validate(CASES[1]['contract'],r))

    def test_bad_input(self):
        for c,r in [(None,{}),({},{}),({'qa':[],'rows':['bad']},{'results':[]})]:
            self.assertTrue(validate(c,r))

SCOPED=json.loads((Path(__file__).resolve().parents[1]/'references/scoped-cases.json').read_text())

def scoped_test(case):
    def test(self):
        errors=validate(case['contract'],case['report'])
        self.assertEqual(not errors,case['complete'],errors)
        if case['case'].startswith('report-overclaim'):
            self.assertTrue(any('unsupported PASS claim' in e for e in errors), errors)
    return test

for scenario in SCOPED:
    setattr(CoverageTests, 'test_' + scenario['case'].replace('-', '_'), scoped_test(scenario))

if __name__=='__main__':unittest.main()

