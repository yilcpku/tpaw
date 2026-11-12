"""Synthetic correctness tests; no personal plans or investment data in this file."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

import research as r


def temporary_directory():
    return tempfile.TemporaryDirectory(dir=os.environ.get("TPAW_RESEARCH_TEST_TMP"))


def fixture_plan():
    return {"v": 30, "timestamp": 1, "datingInfo": {"isDated": True}, "results": {"stale": True},
            "people": {"withPartner": False, "person1": {"ages": {
                "type": "retirementDateSpecified", "currentAgeInfo": {
                    "isDatedPlan": True, "monthOfBirth": {"year": 2000, "month": 1}},
                "retirementAge": {"inMonths": 360}, "maxAge": {"inMonths": 1080}}}},
            "wealth": {"futureSavings": {"old": {"do_not_double_count": True}}},
            "risk": {"tpaw": {"riskTolerance": {"at20": 12, "deltaAtMaxAge": -2,
                "forLegacyAsDeltaFromAt20": 2}, "timePreference": 0, "additionalAnnualSpendingTilt": 0}},
            "advanced": {"sampling": {"type": "monteCarlo", "data": {
                "blockSize": {"inMonths": 60}, "staggerRunStarts": True}}}}


class ResearchTests(unittest.TestCase):
    def test_export_uses_selected_history_not_last_history(self):
        with temporary_directory() as folder:
            p = Path(folder) / "plan.txt"
            p.write_text('HEADER\n' + json.dumps({"reverseHeadIndex": 1, "planParamsHistory": [
                {"diff": [{"op": "add", "path": "/v", "value": 30}, {"op": "add", "path": "/x", "value": 10}]},
                {"diff": [{"op": "replace", "path": "/x", "value": 20}]}]}))
            self.assertEqual(r.load_plan(p)["x"], 10)

    def test_export_patch_array_escaping_and_fail_closed(self):
        data = {"a/b": [1, 2]}
        out = r.apply_patch(data, [{"op": "add", "path": "/a~1b/1", "value": 3}])
        self.assertEqual(out, {"a/b": [1, 3, 2]})
        self.assertEqual(data, {"a/b": [1, 2]})
        with self.assertRaises(ValueError):
            r.apply_patch(data, [{"op": "move", "path": "/a", "from": "/a~1b"}])

    def test_risk_endpoints_and_direction(self):
        self.assertTrue(math.isinf(r.risk_to_rra(0)))
        self.assertAlmostEqual(r.risk_to_rra(1), 16)
        self.assertAlmostEqual(r.risk_to_rra(24), .5)
        self.assertGreater(r.risk_to_rra(10), r.risk_to_rra(15))

    def test_preference_validation_and_baseline_immutability(self):
        base = fixture_plan()
        original = copy.deepcopy(base)
        changed = r.with_preferences(base, {"at20": 18, "timePreference": .01})
        self.assertEqual(base, original)
        self.assertIsNone(changed["results"])
        self.assertEqual(changed["risk"]["tpaw"]["riskTolerance"]["at20"], 18)
        for prefs in ({"at20": 25}, {"at20": True}, {"timePreference": .0005},
                      {"timePreference": float("nan")}, {"deltaAtMaxAge": 1}, {"aggressiveness": 1}):
            with self.subTest(prefs=prefs), self.assertRaises(ValueError):
                r.with_preferences(base, prefs)

    def test_ledger_preserves_bonus_month_and_no_double_count(self):
        with temporary_directory() as folder:
            p = Path(folder) / "ledger.csv"
            p.write_text("month,salary_net_nominal,bonus_net_nominal,paid_notice_net_nominal,spending_nominal,price_index\n"
                         "2029-11,100,0,0,20,2\n2029-12,100,200,0,20,2\n2030-01,100,0,50,20,2\n")
            ledger = r.read_ledger(p)
            self.assertEqual([x["net_real_saving"] for x in ledger], [40, 140, 65])
            base = fixture_plan()
            out = r.with_retirement(base, "2030-01", ledger, "2029-11")
            amounts = [x["amountAndTiming"]["amount"] for x in out["wealth"]["futureSavings"].values()]
            self.assertEqual(amounts, [40, 140])  # Retirement month not counted as a working month.
            self.assertEqual(base["wealth"]["futureSavings"], {"old": {"do_not_double_count": True}})
            with self.assertRaises(ValueError):
                r.with_retirement(base, "2030-03", ledger, "2029-11")

    def test_private_outputs_and_immutable_baseline_hashes(self):
        with self.assertRaises(ValueError):
            r.private_destination(r.REPO / "results.json")
        with temporary_directory() as folder:
            p, m = Path(folder) / "original", Path(folder) / "manifest.json"
            p.write_text("original synthetic fixture")
            r.freeze([p], m)
            self.assertTrue(r.verify(m))
            p.write_text("changed")
            self.assertFalse(r.verify(m))

    def test_long_retirement_ledger_has_unique_colors_across_wealth(self):
        base = fixture_plan()
        base['wealth']['incomeDuringRetirement'] = {'income': {'colorIndex': 7}}
        ledger = [{'month': f'2029-{m:02}', 'net_real_saving': 1} for m in range(1, 13)]
        out = r.with_retirement(base, '2030-01', ledger, '2029-01')
        colors = [x['colorIndex'] for x in out['wealth']['futureSavings'].values()] + [7]
        self.assertEqual(len(colors), len(set(colors)))
        self.assertTrue(all(len(x['id']) == 10 and isinstance(x['amountAndTiming']['amount'], int)
                            for x in out['wealth']['futureSavings'].values()))

    def test_batch_limit_validation_before_writes_and_common_controls(self):
        with temporary_directory() as folder:
            root = Path(folder)
            plan = root / "plan.json"
            plan.write_text(json.dumps(fixture_plan()))
            cfg = {"upstream_commit": r.PIN, "plan": str(plan), "max_cases": 4,
                   "run": {"seed": 123, "simulation_count": 1000, "evaluation_timestamp_ms": 1, "timezone": "Etc/UTC"},
                   "preference_grid": {"at20": [10, 12], "timePreference": [0, .01]}}
            config = root / "config.json"
            config.write_text(json.dumps(cfg))
            self.assertEqual(r.prepare(config, root / "batch"), 4)
            cases = [r.read_json(p) for p in sorted((root / "batch").glob("case-*.json"))]
            self.assertEqual({c["status"] for c in cases}, {"not_run"})
            self.assertEqual({c["run"]["seed"] for c in cases}, {123})
            self.assertEqual({c["inputs"]["plan_sha256"] for c in cases}, {r.digest(plan)})
            cfg["max_cases"] = 3
            config.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                r.prepare(config, root / "too-large")
            self.assertFalse((root / "too-large").exists())

    def test_life_table_conditions_on_survival_and_preserves_open_tail(self):
        # Synthetic constant 1% q(x) until 100. Open interval has positive e(100).
        rows = [{"age": a, "lx": 1000000 * .99 ** a, "qx": .01 if a < 100 else 1,
                 "ex": 102 - a} for a in range(101)]
        table = r.PeriodLifeTable(rows)
        self.assertAlmostEqual(table.survival(50, 52), .99**2)
        self.assertAlmostEqual(table.survival(50, 50), 1)
        self.assertIsNone(table.survival(50, 101))
        self.assertIsNone(table.quantile(50, .95))
        self.assertEqual(table.diagnostics(99)["mean_age_at_death"], 102)
        self.assertIsNone(table.diagnostics(99)["survival_beyond_rolling_horizon"])
        with self.assertRaises(ValueError):
            table.survival(50, 49)

    def test_projected_cohort_uses_calendar_diagonal_and_rejects_missing_years(self):
        q = {(2026, 60): .1, (2027, 61): .2, (2026, 61): .9}
        self.assertEqual(r.cohort_survival(q, 2026, 60, 2), [1, .9, .7200000000000001])
        with self.assertRaises(ValueError):
            r.cohort_survival(q, 2026, 60, 3)

    def test_policy_no_lookahead_continuity_cap_and_joint_denominator(self):
        def transition(state, observation, retired, month):
            state += observation
            if not retired:
                state += 1  # Synthetic ongoing work contribution.
            return state, max(0, state) if retired else 0, .5
        estimate = lambda state, observed: max(0, state)
        path = [0] * 40
        late_crash = [0] * 15 + [-100] * 25
        a = r.conditional_policy(path, 0, transition, estimate, 0, 2, 10)
        b = r.conditional_policy(late_crash, 0, transition, estimate, 0, 2, 10)
        self.assertEqual(a["decision"], b["decision"])  # Later crash cannot change earlier decision.
        self.assertEqual(a["decision"]["delay_years"], 1)
        self.assertEqual(a["ending_state"], 12)  # No reset/resample at retirement.
        bad = r.conditional_policy([-1] * 40, 0, transition, estimate, 0, 2, 10)
        self.assertTrue(bad["decision"]["forced_at_cap_below_floor"])
        self.assertEqual(bad["decision"]["delay_years"], 2)
        result = r.policy_summary([a, b, bad], 10)
        self.assertEqual(result["path_count"], 3)
        self.assertAlmostEqual(sum(x["probability_of_all_paths"] for x in result["joint"]), 1)
        self.assertAlmostEqual(result["joint"][2]["below_floor_at_decision_joint_probability"], 1/3)
        self.assertAlmostEqual(result["all_path_shortfall_probability"], 2/3)

    def test_pathwise_hardship_and_recovery_censoring(self):
        out = r.path_metrics([100, 80, 50, 100, 75], {"preferred": 100, "reduced": 80, "minimum": 60}, 25)
        self.assertEqual(out["minimum"]["months_below"], 1)
        self.assertEqual(out["preferred"]["longest_spell_months"], 2)
        self.assertEqual(out["preferred"]["cumulative_shortfall"], 95)
        self.assertEqual(out["deepest_cut_from_high_water"], .5)
        self.assertTrue(out["recovery_right_censored"])
        self.assertEqual(out["lifetime_real_consumption"], 405)
        self.assertIsNone(out["monthly_spending_after_10_years"])

    def test_comparison_rejects_changed_paths_or_unknown_assumptions(self):
        with temporary_directory() as folder:
            root = Path(folder)
            controls = {"engine_commit": r.PIN, "market_snapshot_sha256": "fixture-snapshot",
                        "path_set_sha256": "fixture-paths", "seed": 123, "simulation_count": 2,
                        "sampling": "synthetic-test", "precision": "synthetic-test", "evaluation_timestamp_ms": 1,
                        "currency": "test-units", "purchasing_power_date": "test", "fees": 0, "tax": 0,
                        "fx": "synthetic-test", "comparison_design": "matched-assets-withdrawal-rule"}
            record = {"status": "simulated", "controls": controls,
                      "path_outcomes": [{"path_id": 0}, {"path_id": 1}]}
            a, b = root / "a.json", root / "b.json"
            a.write_text(json.dumps(record))
            b.write_text(json.dumps(record))
            r.compare_summaries([a, b], root / "comparison.json")
            self.assertIsNone(r.read_json(root / "comparison.json")["ranking"])
            record["path_outcomes"][1]["path_id"] = 0
            b.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                r.compare_summaries([a, b], root / "invalid.json")
            self.assertFalse((root / "invalid.json").exists())
            record["path_outcomes"][1]["path_id"] = 1
            record["controls"]["tax"] = None
            b.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                r.compare_summaries([a, b], root / "unknown.json")


if __name__ == "__main__":
    unittest.main()
