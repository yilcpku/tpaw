import unittest
from unittest.mock import patch
from dataclasses import replace
from tpaw_lab.retirement import review_schedule,simplified_scenario,compare_retirement,decade_minima
from tpaw_lab.simulation import simulate,prepare
from tpaw_lab.policy import TpawPolicy
from tpaw_lab.cashflows import compile_flows
from test_market import fixture
from test_simulation import scenario,life


def base():
    s=scenario();s.update(current_age=97,initial_assets=100000,reserve=0,monthly_savings=100,
        savings_mode='constant',planning_cpi=0,retirement_withdrawal=25000)
    return s


def constant_history():
    h=fixture()
    return replace(h,rows=tuple(replace(r,global_equity_usd_gross=1,cny_per_usd_gross=1,china_cpi_gross=1,us_cpi_gross=1) for r in h.rows))


class RetirementTests(unittest.TestCase):
    def test_window_reviews_start_inside_window_and_clip_notice_to_end(self):
        s=base();s['retirement_rule']={'kind':'window','start':'2027-01','end':'2027-05','target_annual':100}
        self.assertEqual(review_schedule(s,36),((2,5),(3,6),(4,6),(5,6),(6,6)))

    def test_fixed_date_ignores_threshold_and_stops_savings_at_retirement(self):
        s=simplified_scenario(base(),{'id':'a','name':'Fixed','kind':'fixed','date':'2027-02'})
        result=simulate(s,constant_history(),life())
        path=result['paths'][0]
        self.assertEqual(path['retirement_month'],3)
        self.assertFalse(path['forced_below_threshold'])
        self.assertTrue(all(r['general_real']==0 for r in path['records'][:3]))
        self.assertAlmostEqual(path['records'][3]['essential_real'],25000)
        self.assertAlmostEqual(path['records'][3]['total_real']-path['records'][3]['lifestyle_real'],25000)
        f=compile_flows(s,36,3)
        self.assertEqual(f.income_real[:5],[100,100,100,0,0])
        self.assertTrue(all(v==0 for v in f.income_real[3:]))
        self.assertTrue(all(r['income_real']==0 for r in path['records'][3:]))

    def test_window_triggers_mid_period_once_then_observes_notice(self):
        s=simplified_scenario(base(),{'id':'a','name':'Window','kind':'window','start':'2026-11','end':'2027-05','target_annual':100})
        # Decision-only oracle: fail twice then pass; actual ledger still runs.
        with patch('tpaw_lab.simulation.project_notice',side_effect=[0,0,200,0,0,200]):
            result=simulate(s,constant_history(),life())
        for path in result['paths']:
            self.assertEqual(path['commitment_month'],2)
            self.assertEqual(path['retirement_month'],5)
            self.assertEqual(len(path['reviews']),3)
            self.assertFalse(path['forced_below_threshold'])

    def test_no_success_waits_until_end_and_stops_dated_future_savings(self):
        raw=base();raw.update(savings_mode='dated',require_savings_coverage=True,savings_coverage_end='2028-12',
            cashflow_rows=[{'kind':'net_savings','reference':'calendar','start':'2026-11','duration_months':24,'amount':100,'basis':'real'}])
        s=simplified_scenario(raw,{'id':'a','name':'Window','kind':'window','start':'2026-11','end':'2027-05','target_annual':1e12})
        result=simulate(s,constant_history(),life())
        for path in result['paths']:
            self.assertEqual(path['commitment_month'],6);self.assertEqual(path['retirement_month'],6)
            self.assertTrue(path['forced_below_threshold']);self.assertEqual(len(path['reviews']),7)
        f=compile_flows(s,36,6)
        self.assertEqual(f.income_real[:6],[100]*6);self.assertEqual(f.income_real[6:],[0]*30)
        early=compile_flows(s,36,3)
        self.assertEqual(early.income_real[3:],[0]*33)
        # Previously dated contributions after the actual exit never become wealth.
        raw['cashflow_rows'][0]['amount']=100000
        changed=simplified_scenario(raw,s['retirement_rule'])
        self.assertEqual(compile_flows(changed,36,3).income_real[3:],[0]*33)

    def test_removed_presets_do_not_reappear_or_double_count_withdrawal(self):
        raw=base();raw.update(reserve=50000,reserve_funding='retirement',reserve_draws=[{'months_after_retirement':0,'real_amount':1000}],
            cashflow_rows=[{'kind':'essential','reference':'retirement','start':0,'amount':9999},
                {'kind':'budget','reference':'retirement','start':0,'amount':9999},
                {'kind':'reserve_draw','reference':'retirement','start':0,'amount':9999}])
        s=simplified_scenario(raw,{'id':'a','name':'Fixed','kind':'fixed','date':'2027-02'})
        f=compile_flows(s,36,3)
        self.assertEqual(s['reserve'],0);self.assertEqual(sum(f.reserve_transfer_real),0)
        self.assertEqual(sum(f.reserve_draw_real),0);self.assertEqual(sum(f.essential_real),25000)
        self.assertEqual(sum(f.lifestyle_essential_real),0)

    def test_all_cashflows_real_and_legacy_nominal_savings_converted(self):
        raw=base();raw.update(planning_cpi=.1,savings_mode='dated',cashflow_rows=[{'kind':'net_savings','reference':'calendar',
            'start':'2027-11','duration_months':2,'amount':110,'basis':'nominal'}])
        s=simplified_scenario(raw,{'id':'a','name':'Fixed','kind':'fixed','date':'2028-02'})
        f=compile_flows(s,36,15)
        self.assertAlmostEqual(f.income_real[12],100)
        self.assertAlmostEqual(f.income_real[13],110/1.1**(13/12))
        self.assertEqual(sum(f.income_nominal),0)
        self.assertEqual(f.essential_real[15],25000);self.assertEqual(sum(f.essential_nominal),0)
        self.assertAlmostEqual(f.nominal('essential',15,1.2),30000)

    def test_decade_minimum_is_minimum_of_pointwise_p5_not_partial_year_or_working_zero(self):
        rows=[{'age':age,'p5':value,'months_summed':months} for age,value,months in
              [(30,5,12),(31,40,12),(35,10,12),(40,30,12),(41,8,12),(49,0,6)]]
        result=decade_minima(rows)
        self.assertEqual([(r['start_age'],r['end_age'],r['age'],r['p5']) for r in result],
                         [(21,30,30,5),(31,40,35,10),(41,50,41,8)])
        self.assertEqual(result[-1]['covered_end'],41)

    def test_same_month_decisions_do_not_see_future_market_shock(self):
        raw=base();plan={'id':'a','name':'Window','kind':'window','start':'2026-11','end':'2027-05','target_annual':1}
        s=simplified_scenario(raw,plan);h=constant_history()
        a=simulate(s,h,life())['paths'][0]
        shock=replace(h,rows=tuple(replace(r,global_equity_usd_gross=.01) for r in h.rows))
        b=simulate(s,shock,life())['paths'][0]
        self.assertEqual(a['reviews'][0],b['reviews'][0]);self.assertEqual(a['commitment_month'],0)
        self.assertEqual(b['retirement_month'],a['retirement_month'])

    def test_compared_plans_share_market_draws_and_show_quartiles(self):
        s=base();s['horizon']='rolling';s['retirement_plans']=[{'id':'a','name':'A','kind':'fixed','date':'2027-02'},
            {'id':'b','name':'B','kind':'window','start':'2026-11','end':'2027-08','target_annual':1e9}]
        progress=[];result=compare_retirement(s,fixture(),life(),progress.append)
        cases=result['retirement_comparison']['cases'];self.assertEqual(set(cases),{'a','b'})
        self.assertEqual(cases['a']['provenance']['sample_index_sha256'],cases['b']['provenance']['sample_index_sha256'])
        self.assertEqual(progress[-1],1);self.assertEqual(progress,sorted(progress))
        for case in cases.values():
            self.assertEqual(case['retirement_timing']['withdrawal_short_path_fraction'],0)
            for row in case['post_retirement_profiles']:
                self.assertLessEqual(row['p5'],row['p25']);self.assertLessEqual(row['p25'],row['p50'])
                self.assertLessEqual(row['p50'],row['p75']);self.assertLessEqual(row['p75'],row['p95'])
                self.assertGreater(row['retired_path_count'],0)

    def test_wide_failing_window_does_not_rebuild_policy_for_every_path(self):
        raw=base();raw.update(current_age=93,runs=2,retirement_withdrawal=1000)
        s=simplified_scenario(raw,{'id':'wide','name':'Wide','kind':'window','start':'2026-11','end':'2032-09','target_annual':1e12})
        exits=prepare(s,constant_history(),life())[3]
        self.assertGreater(len(exits),64)
        with patch('tpaw_lab.simulation.TpawPolicy',wraps=TpawPolicy) as constructor:
            simulate(s,constant_history(),life(),retain_paths=False)
        self.assertEqual(constructor.call_count,len(exits))

    def test_near100_initial_period_is_censored_and_never_called_full_year(self):
        raw=base();raw.update(current_age=99.5,retirement_withdrawal=1000)
        s=simplified_scenario(raw,{'id':'late','name':'Late','kind':'fixed','date':'2027-02'})
        result=simulate(s,fixture(),life())
        self.assertEqual(result['retirement_timing']['initial_spending_months_min_max'],[3,3])
        self.assertFalse(any(row['months_summed']==12 for row in result['post_retirement_profiles']))
        self.assertEqual(result['decade_minima'],[])

    def test_real_cashflows_keep_purchasing_power_on_inflation_path(self):
        raw=base();raw['retirement_withdrawal']=1000
        s=simplified_scenario(raw,{'id':'real','name':'Real','kind':'fixed','date':'2027-02'})
        h=constant_history();h=replace(h,rows=tuple(replace(r,china_cpi_gross=1.02) for r in h.rows))
        path=simulate(s,h,life())['paths'][0]
        self.assertGreater(path['records'][3]['cpi_start'],1)
        self.assertAlmostEqual(path['records'][3]['essential_real'],1000)
        for record in path['records'][:3]:self.assertAlmostEqual(record['income_real'],100)
        for record in path['records'][3:]:self.assertEqual(record['income_real'],0)

    def test_explicit_retirement_income_is_real_and_distinct_from_expired_work_savings(self):
        raw=base();raw.update(planning_cpi=.1,cashflow_rows=[{'kind':'retirement_income','reference':'retirement',
            'start':0,'duration_months':6,'amount':110,'basis':'nominal'}])
        s=simplified_scenario(raw,{'id':'income','name':'Income','kind':'fixed','date':'2027-11'})
        f=compile_flows(s,36,12)
        self.assertEqual(f.income_real[:12],[100]*12)
        self.assertAlmostEqual(f.income_real[12],100)
        self.assertEqual(sum(f.income_nominal),0)
        self.assertEqual(f.income_real[18:],[0]*18)
