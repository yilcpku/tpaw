from dataclasses import replace
import unittest
from tpaw_lab.cashflows import compile_flows
from tpaw_lab.market import JointHistory
from tpaw_lab.simulation import simulate,prepare
from test_market import fixture
from test_simulation import scenario,life


class CashflowTests(unittest.TestCase):
    def test_dated_savings_bonus_notice_months_paid_once_and_stop_at_exit(self):
        s=scenario();s.update(evaluation_month='2026-11',savings_mode='dated',require_savings_coverage=True,
                             savings_coverage_end='2027-01',cashflow_rows=[
            {'kind':'net_savings','start':'2026-11','duration_months':3,'amount':10,'basis':'real'},
            {'kind':'net_savings','start':'2026-12','amount':20,'basis':'real'}])
        f=compile_flows(s,24,3)
        self.assertEqual(f.planned('income')[:5],(10,30,10,0,0))
        with self.assertRaises(ValueError):compile_flows(s,24,4)
        s['savings_coverage_end']='2027-03'
        with self.assertRaises(ValueError):compile_flows(s,24,4)

    def test_budget_replaces_benchmark_without_becoming_expense(self):
        s=scenario();s['cashflow_rows']=[{'kind':'budget','start':'2027-02','duration_months':2,'amount':120}]
        f=compile_flows(s,24,3)
        self.assertEqual(f.planned('budget')[:6],(60,60,60,120,120,60))
        self.assertEqual(sum(f.planned('essential')),0)
        s['cashflow_rows']*=2
        with self.assertRaises(ValueError):compile_flows(s,24,3)

    def test_constant_savings_override_does_not_also_add_dated_entries(self):
        s=scenario();s.update(monthly_savings=10,savings_mode='constant',savings_coverage_end='2026-11',
            cashflow_rows=[{'kind':'net_savings','start':'2026-12','amount':100}])
        self.assertEqual(compile_flows(s,24,3).planned('income')[:4],(10,10,10,0))

    def test_nominal_goals_plan_with_forecast_but_pay_known_nominal_amount(self):
        s=scenario();s.update(planning_cpi=.12,cashflow_rows=[{'kind':'essential','start':'2027-11','amount':112,'basis':'nominal'}])
        f=compile_flows(s,24,3)
        self.assertAlmostEqual(f.planned('essential')[12],100)
        self.assertEqual(f.nominal('essential',12,1.5),112)

    def test_retirement_reserve_partition_is_transfer_and_draw_is_consumption(self):
        s=scenario();s.update(reserve=200,reserve_funding='retirement',reserve_basis='nominal',risk_tolerance=0,
                             reserve_cash_rate=0,cashflow_rows=[{'kind':'reserve_draw','reference':'retirement','start':0,'amount':40,'basis':'nominal'}])
        h=fixture();h=replace(h,rows=tuple(replace(r,global_equity_usd_gross=1,cny_per_usd_gross=1,china_cpi_gross=1) for r in h.rows))
        result=simulate(s,h,life());records=result['paths'][0]['records']
        self.assertAlmostEqual(records[3]['reserve_withdrawal_real'],40)
        self.assertEqual(records[3]['reserve_funding_short_real'],0)
        # Full no-return identity includes reserve consumption once, no transfer.
        total_spent=sum(r['household_total_real'] for r in records)
        self.assertAlmostEqual(records[-1]['estate_end_real']+total_spent,s['initial_assets'],places=6)

    def test_unfunded_essential_goal_not_hidden_by_policy_cap(self):
        s=scenario();s.update(cashflow_rows=[{'kind':'essential','start':'2027-02','amount':10000,'basis':'real'}])
        result=simulate(s,fixture(),life())
        self.assertTrue(result['path_metrics'][0]['any_unfunded_consumption'])
        self.assertGreater(result['paths'][0]['records'][3]['unfunded_essential_real'],0)

    def test_unaffordable_goal_cannot_pass_notice_as_sustainable_spending(self):
        s=scenario();s.update(threshold_annual=100000,cashflow_rows=[{'kind':'essential','reference':'retirement','start':0,'duration_months':24,'amount':10000}])
        result=simulate(s,fixture(),life())
        first=result['paths'][0]['reviews'][0]
        self.assertFalse(first['passed'])
        self.assertLess(first['projected_annual_general'],100000)

    def test_future_notice_cpi_and_yield_shock_unseen_at_commitment(self):
        s=scenario();s.update(defensive='government_bond',defensive_rate_mode='history',initial_government_yield=.02,initial_deposit_rate=.02,threshold_annual=0)
        h=fixture();rows=tuple(replace(r,global_equity_usd_gross=1,cny_per_usd_gross=1,china_cpi_gross=1,
            government_curve_before={str(t):.02 for t in (3,6,12,36,60,84,120,360)},government_curve={str(t):.02 for t in (3,6,12,36,60,84,120,360)},
            deposit_curve_before={str(t):.02 for t in (3,6,12,24,36,60)},deposit_curve={str(t):.02 for t in (3,6,12,24,36,60)},demand_rate_before=0,demand_rate=0) for r in h.rows)
        plain=replace(h,rows=rows)
        index=prepare(s,plain,life())[2][0][1]
        changed=replace(rows[index],china_cpi_gross=2,government_curve={str(t):.08 for t in (3,6,12,36,60,84,120,360)})
        shock=replace(h,rows=rows[:index]+(changed,)+rows[index+1:])
        a=simulate(s,plain,life())['paths'][0];b=simulate(s,shock,life())['paths'][0]
        self.assertEqual(a['reviews'],b['reviews'])
        self.assertEqual(a['retirement_month'],b['retirement_month'])
        self.assertLess(b['actual_exit_general_annual'],a['actual_exit_general_annual'])
