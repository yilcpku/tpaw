import math
import unittest
from dataclasses import replace
from tpaw_lab.market import JointHistory, Observation, attribution, calibrate_equity, contiguous_blocks, return_statistics


def fixture(n=180):
    rows = tuple(Observation(f"{1990+i//12:04}-{i%12+1:02}", math.exp(.004 + .04*math.sin(i)),
                             math.exp(.005 + .035*math.sin(i+.2)), math.exp(.001+.005*math.cos(i)),
                             math.exp(.002+.002*math.sin(i)), math.exp(.0015+.001*math.sin(i+.5)),
                             .02+.003*math.sin(i), .025+.003*math.cos(i), "unit-test synthetic fixture")
                 for i in range(n))
    return JointHistory(rows, "synthetic_stress", "TEST ONLY", ("synthetic",), ("Not empirical data",))


class MarketTests(unittest.TestCase):
    def test_currency_direction_and_no_us_inflation_in_cny(self):
        r = replace(fixture().rows[0], global_equity_usd_gross=1.1, cny_per_usd_gross=.9,
                    china_cpi_gross=1.02, us_cpi_gross=1.5)
        self.assertAlmostEqual(r.equity_gross("global", "cny"), 1.1*.9/1.02)
        self.assertAlmostEqual(r.equity_gross("global", "usd"), 1.1/1.5)

    def test_real_contiguous_blocks_never_wrap_and_shared_rows(self):
        h = fixture()
        indices = contiguous_blocks(h, 720, 50, 7)
        self.assertEqual(indices, contiguous_blocks(h, 720, 50, 7))
        self.assertNotEqual(indices, contiguous_blocks(h, 720, 50, 8))
        for path in indices:
            self.assertEqual(len(path), 720)
            for start in range(0, 720, 60):
                block = path[start:start+60]
                self.assertEqual(block, tuple(range(block[0], block[0]+60)))
                self.assertLess(block[-1], len(h.rows))
        with self.assertRaises(ValueError):
            contiguous_blocks(fixture(59), 60, 1, 0)

    def test_missing_or_reordered_month_rejected(self):
        h = fixture()
        with self.assertRaises(ValueError):
            replace(h, rows=h.rows[:10] + h.rows[11:])
        with self.assertRaises(ValueError):
            replace(h, rows=tuple(reversed(h.rows)))

    def test_forward_targets_replaced_once_macro_pairing_preserved(self):
        h = fixture()
        new = calibrate_equity(h, "global", "cny", .035, .15)
        stats = return_statistics([r.equity_gross("global", "cny") for r in new.rows])
        self.assertAlmostEqual(stats["rolling_12m_arithmetic_mean"], .035, places=12)
        self.assertAlmostEqual(stats["monthly_log_volatility_times_sqrt12_sample"], .15, places=12)
        for a, b in zip(h.rows, new.rows):
            self.assertEqual((a.china_cpi_gross, a.cny_per_usd_gross, a.government_yield_annual),
                             (b.china_cpi_gross, b.cny_per_usd_gross, b.government_yield_annual))
        self.assertEqual(new.kind, "synthetic_stress")
        same = calibrate_equity(new, "global", "cny", .035, .15)
        for a, b in zip(new.rows, same.rows):
            self.assertAlmostEqual(a.global_equity_usd_gross, b.global_equity_usd_gross, places=12)

    def test_attribution_is_exact_and_separates_four_components(self):
        result = attribution(fixture())
        components = result["annualized_log_components"]
        self.assertEqual(len(components), 4)
        self.assertAlmostEqual(sum(components.values()), result["total_annualized_log_difference"])

    def test_arithmetic_cagr_rolling12_are_distinct(self):
        stats = return_statistics([1.2, .8] * 12)
        self.assertAlmostEqual(stats["arithmetic_monthly_mean_times_12"], 0)
        self.assertLess(stats["compound_annual_growth_rate"], 0)
        self.assertAlmostEqual(stats["rolling_12m_arithmetic_mean"], (.96 ** 6) - 1)


if __name__ == "__main__":
    unittest.main()
