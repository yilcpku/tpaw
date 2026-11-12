import math
import unittest
from dataclasses import replace
from tpaw_lab.policy import PolicyPlan, TpawPolicy, merton


def plan(months=120):
    zero = (0.0,) * months
    return PolicyPlan(1200, 0, zero, zero, zero, (math.inf,) * months,
                      (months,) * months, 0, 0, .04)


class PolicyTests(unittest.TestCase):
    def test_zero_return_annuity_and_accounting(self):
        policy = TpawPolicy(plan())
        balance = 1200
        for m in range(120):
            result = policy.step(balance, m)
            self.assertAlmostEqual(result["general"], 10)
            self.assertAlmostEqual(balance - result["total"], result["balance_end"])
            balance = result["balance_end"]
        self.assertAlmostEqual(balance, 0)

    def test_horizon_update_keeps_wealth_and_reduces_spending(self):
        p = plan(24)
        p = replace(p, end_by_month=(12,) * 6 + (18,) * 6)
        policy = TpawPolicy(p)
        balance = 1200
        for m in range(6):
            balance = policy.step(balance, m)["balance_end"]
        self.assertAlmostEqual(balance, 600)
        self.assertAlmostEqual(policy.step(balance, 6)["general"], 50)

    def test_future_market_shock_cannot_change_earlier_decision(self):
        p = replace(plan(24), rra=(4,) * 24, stock_mu_annual=.05, bond_mu_annual=.01)
        policy = TpawPolicy(p)
        def run(shock_month):
            balance, results = p.initial_balance, []
            for m in range(24):
                result = policy.step(balance, m, -.5 if m == shock_month else 0, 0)
                results.append(result)
                balance = result["balance_end"]
            return results
        a, b = run(-1), run(12)
        self.assertEqual([x["general"] for x in a[:13]], [x["general"] for x in b[:13]])
        self.assertLess(b[13]["general"], a[13]["general"])

    def test_essential_first_and_no_assets_invented_by_floor(self):
        p = replace(plan(12), initial_balance=5, essential=(7,) + (0,) * 11, floor=10)
        result = TpawPolicy(p).step(5, 0)
        self.assertEqual(result["essential"], 5)
        self.assertEqual(result["general"], 0)
        self.assertEqual(result["unfunded_essential"], 2)
        self.assertEqual(result["balance_end"], 0)

    def test_merton_matches_pinned_source_equations(self):
        weight, tilt = merton(.06, .02, .04, .005, 0, 4)
        self.assertAlmostEqual(weight, .25)
        annual = (.02 - .005 + .04**2 / (.08)) / 4 + (.04**2 / .08) / 16
        self.assertAlmostEqual((1 + tilt)**12 - 1, annual)
        self.assertEqual(merton(.01, .02, .04, 0, 0, 4)[0], 0)


if __name__ == "__main__":
    unittest.main()
