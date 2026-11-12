from dataclasses import replace
import math
import unittest
from tpaw_lab.longevity import LifeTable
from tpaw_lab.market import JointHistory
from tpaw_lab.policy import PolicyPlan, TpawPolicy
from tpaw_lab.simulation import compare_horizons, run_path, simulate
from test_market import fixture


def life():
    # Artificial mortality for mechanics only; never used as an empirical table.
    return LifeTable([{"age":age,"lx":100000*math.exp(-.015*age),"ex":max(3,85-age)}
                      for age in range(101)], {"kind":"synthetic unit test"})


def scenario():
    return {"name":"Unit test only", "initial_assets":1200,"reserve":0,"current_age":98,
            "evaluation_month":"2026-11","candidates":"2027-02,2027-08,2028-02","notice_months":3,
            "annual_budget":60,"threshold_annual":0,"horizon":"fixed100","margin":5,
            "stock_return":0,"stock_volatility":20,"planning_defensive_return":0,"time_preference":0,
            "risk_tolerance":12,"cash_multiple":0,"term_years":1,"defensive":"cash","runs":2,"seed":1,
            "use_forward_targets":False,"initial_deposit_rate":0,"initial_government_yield":0,"demand_rate":0}


class SimulationTests(unittest.TestCase):
    def test_notice_projection_obeys_cash_floor_without_unavailable_equity_gains(self):
        s=scenario();s.update(annual_budget=800,cash_multiple=1.5,risk_tolerance=24,stock_return=10,
                              planning_cpi=0,threshold_annual=680)
        h=fixture();h=replace(h,rows=tuple(replace(r,global_equity_usd_gross=1,cny_per_usd_gross=1,china_cpi_gross=1) for r in h.rows))
        result=simulate(s,h,life())['paths'][0]
        self.assertFalse(result['reviews'][0]['passed'])
        self.assertLess(result['reviews'][0]['projected_annual_general'],680)
        forced=simulate({**s,'threshold_annual':0},h,life())['paths'][0]
        self.assertAlmostEqual(forced['projected_exit_general_annual'],forced['actual_exit_general_annual'],places=6)
        self.assertTrue(all(r['stock_fraction_after_spending']==0 for r in forced['records'][:4]))

    def test_fractional_age_and_late_retirement_keep_partial_period_lengths(self):
        s=scenario();s.update(current_age=99.5,candidates='2027-02')
        result=simulate(s,fixture(),life())
        self.assertEqual(result['profiles'][-1]['months_summed'],6)
        self.assertEqual(result['distributions']['initial_spending_months_min_max'],[3,3])
        self.assertIn('100岁截断',result['summary'][0]['name'])
    def test_rate_changes_not_sampled_levels_at_block_boundary(self):
        h=fixture()
        rows=tuple(replace(r,government_curve_before={str(t):.08 for t in (3,6,12,36,60,84,120,360)},
                           government_curve={str(t):.081 for t in (3,6,12,36,60,84,120,360)},
                           deposit_curve_before={str(t):.08 for t in (3,6,12,24,36,60)},
                           deposit_curve={str(t):.08 for t in (3,6,12,24,36,60)},
                           demand_rate_before=.01,demand_rate=.01) for r in h.rows)
        s=scenario();s.update(defensive='government_bond',defensive_rate_mode='history',initial_government_yield=.02,
                              initial_deposit_rate=.02,demand_rate=.001)
        result=simulate(s,replace(h,rows=rows),life())
        records=result['paths'][0]['records']
        self.assertAlmostEqual(records[0]['known_government_yield_end'],.021)
        self.assertAlmostEqual(records[1]['known_government_yield_end'],.022)
        self.assertAlmostEqual(records[0]['known_deposit_rate_end'],.02)
        self.assertAlmostEqual(records[0]['known_demand_rate_end'],.001)

    def test_notice_is_irrevocable_and_future_shock_unseen(self):
        months=36
        zero=(0.,)*months
        exits=(3,15,27)
        policies=[]
        for exit in exits:
            income=tuple(100. if m<exit else 0. for m in range(months))
            policies.append(TpawPolicy(PolicyPlan(1200,exit,income,zero,zero,(4.,)*months,(months,)*months,.05,0,.04)))
        base=fixture(months)
        rows=tuple(replace(r,global_equity_usd_gross=1,us_equity_usd_gross=1,cny_per_usd_gross=1,
                           china_cpi_gross=1,us_cpi_gross=1,deposit_rate_annual=0,government_yield_annual=0) for r in base.rows)
        plain=replace(base,rows=rows)
        shock=replace(plain,rows=rows[:1]+(replace(rows[1],global_equity_usd_gross=.1),)+rows[2:])
        s=scenario()
        s["threshold_annual"]=500
        a=run_path(s,plain,tuple(range(months)),exits,policies)
        b=run_path(s,shock,tuple(range(months)),exits,policies)
        self.assertEqual(a["retirement_month"],3)
        self.assertEqual(a["commitment_month"],0)
        self.assertEqual(b["retirement_month"],3)
        self.assertEqual(a["reviews"],b["reviews"])
        self.assertLess(b["actual_exit_general_annual"],a["actual_exit_general_annual"])
        self.assertFalse(a["forced_below_threshold"])
        self.assertTrue(b["actual_exit_below_threshold"])

    def test_mortality_mass_and_open_tail_retained(self):
        w=life().weights(98*12,24)
        self.assertAlmostEqual(sum(w["death_end"])+w["tail_alive"],1)
        self.assertGreater(w["tail_alive"],0)
        with self.assertRaises(ValueError):
            life().weights(98*12,25)

    def test_full_ledger_with_deposit_interest_and_cash_floor(self):
        s=scenario()
        s.update(defensive="deposit",cash_multiple=1.5,annual_budget=60,monthly_savings=20,
                 reserve=100,reserve_draws=[{"months_after_retirement":2,"real_amount":20}])
        result=simulate(s,fixture(),life())
        self.assertEqual(len(result["paths"]),2)
        for path in result["paths"]:
            self.assertEqual(path["retirement_month"],3)
            self.assertEqual(path["commitment_month"],0)
            self.assertEqual(len(path["records"]),24)
            self.assertTrue(all(r["estate_end_real"]>=0 for r in path["records"]))

    def test_rolling_updates_on_birthday_and_fixed_expiry(self):
        table=life()
        ends=table.schedule(40*12+6,"rolling",5)
        self.assertEqual(ends[0],ends[5])
        # Fixture's e(x) keeps mean death age 85 until x=82; use old ages where
        # the floor on e(x) makes the conditional planning endpoint move forward.
        old=table.schedule(98*12+6,"rolling",5)
        self.assertEqual(old[0],old[5])
        self.assertGreater(old[6],old[5])
        fixed=table.schedule(89*12,"fixed90",5)
        self.assertEqual(fixed[0],13)
        self.assertEqual(fixed[20],21)

    def test_four_horizons_change_only_endpoint_on_same_draws(self):
        result=compare_horizons(scenario(),fixture(),life())
        comparison=result["horizon_comparison"]
        self.assertEqual(set(comparison["cases"]),{"fixed90","fixed95","fixed100","rolling"})
        self.assertEqual(comparison["varied_fields"],["horizon"])
        signatures={c["provenance"]["sample_index_sha256"] for c in comparison["cases"].values()}
        self.assertEqual(signatures,{comparison["matched_sample_index_sha256"]})
        self.assertTrue(all(c["mortality"]["survival_to100"]>0 for c in comparison["cases"].values()))


if __name__ == "__main__":
    unittest.main()
