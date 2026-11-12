import json
from pathlib import Path
import unittest
from dataclasses import asdict
from tpaw_lab.browser import run_browser,BROWSER_MODEL_VERSION
from tpaw_lab.simulation import compare_horizons,simulate
from test_simulation import life
from test_market import fixture


class BrowserModelTests(unittest.TestCase):
    def assert_original_fields_equal(self,actual,expected):
        if isinstance(expected,dict):
            for k,value in expected.items():self.assert_original_fields_equal(actual[k],value)
        elif isinstance(expected,list):
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):self.assert_original_fields_equal(a,b)
        elif isinstance(expected,float):self.assertAlmostEqual(actual,expected,delta=max(1e-8,abs(expected)*1e-12))
        else:self.assertEqual(actual,expected)

    def test_streaming_matches_frozen_prechange_numerical_oracle(self):
        oracle=json.loads((Path(__file__).parent/'fixtures/browser-model-reference.json').read_text(encoding='utf-8'))
        for case in oracle['cases']:
            with self.subTest(asset=case['scenario']['defensive'],horizon=case['scenario']['horizon']):
                result=simulate(case['scenario'],fixture(),life(),retain_paths=False)
                self.assertEqual(result['paths'],[])
                self.assert_original_fields_equal(result,case['result'])

    def test_two_horizons_progress_and_draws_remain_paired(self):
        oracle=json.loads((Path(__file__).parent/'fixtures/browser-model-reference.json').read_text(encoding='utf-8'))
        s=oracle['cases'][0]['scenario'];progress=[]
        result=compare_horizons(s,fixture(),life(),modes=('rolling','fixed90'),retain_paths=False,progress=progress.append)
        self.assertEqual(set(result['horizon_comparison']['cases']),{'rolling','fixed90'})
        self.assertEqual(progress[-1],1)
        self.assertEqual(progress,sorted(progress))

    def test_browser_bridge_returns_compact_traceable_two_case_report(self):
        oracle=json.loads((Path(__file__).parent/'fixtures/browser-model-reference.json').read_text(encoding='utf-8'))
        s={**oracle['cases'][0]['scenario'],'dataset':'generic'};history=fixture();table=life()
        payload={'model_version':BROWSER_MODEL_VERSION,'scenario':s,'engine_sha256':'generic-test-hash','inputs':{
            'source':{'history':{'rows':[asdict(r) for r in history.rows],'kind':history.kind,'label':history.label,
                'sources':history.sources,'limitations':history.limitations}},
            'mortality':{'rows':list(table.rows.values()),'source':table.source}}}
        result=json.loads(run_browser(json.dumps(payload)))
        self.assertNotIn('paths',result);self.assertNotIn('path_metrics',result)
        self.assertEqual(result['provenance']['compute_location'],'browser')
        self.assertEqual(result['provenance']['engine_sha256'],'generic-test-hash')
        self.assertEqual(set(result['horizon_comparison']['cases']),{'rolling','fixed90'})

    def test_stale_ui_cannot_silently_run_new_financial_rules(self):
        with self.assertRaisesRegex(ValueError,'刷新页面'):
            run_browser(json.dumps({'scenario':{}}))
