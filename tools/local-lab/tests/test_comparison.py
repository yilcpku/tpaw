import unittest
from tpaw_lab.comparison import compare_channels,channel_history,CHANNELS
from test_market import fixture
from test_simulation import scenario,life


class ComparisonTests(unittest.TestCase):
    def test_attribution_keeps_truncated_initial_period_bounds(self):
        s=scenario();s.update(current_age=99.5,candidates='2027-02')
        result=compare_channels(s,fixture(),life())
        for case in result['cases'].values():
            self.assertEqual(case['initial_spending_months_min_max'],[3,3])
            self.assertIn('initial_period_spending_median',case['metrics'])
    def test_real_equity_bridge_endpoints_and_cash_deflator_unchanged(self):
        h=fixture()
        a=channel_history(h,frozenset()).rows[0]
        b=channel_history(h,frozenset(CHANNELS)).rows[0]
        original=h.rows[0]
        self.assertAlmostEqual(a.equity_gross('global','cny'),original.equity_gross('us','usd'))
        self.assertAlmostEqual(b.equity_gross('global','cny'),original.equity_gross('global','cny'))
        self.assertEqual(a.china_cpi_gross,original.china_cpi_gross)
        self.assertEqual(a.deposit_rate_annual,original.deposit_rate_annual)

    def test_shapley_non_linear_outcomes_sum_to_paired_total(self):
        result=compare_channels(scenario(),fixture(),life())
        cases=result['cases']
        for metric in cases[0]['metrics']:
            self.assertAlmostEqual(sum(c[metric] for c in result['shapley_contributions'].values()),
                                   cases[7]['metrics'][metric]-cases[0]['metrics'][metric])
        self.assertEqual(len(result['matched_sample_index_sha256']),64)
