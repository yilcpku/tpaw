"""Offline research orchestration. This is NOT a replacement for the TPAW engine.

Standard library only; no network, telemetry, or automatic dependency installation.
Required Notice: Copyright (c) 2020-2026 Benjamin Mathew and Jacob Mathew.
See ../../LICENSE.md (PolyForm Noncommercial 1.0.0).
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import uuid

PIN = "19b9d7b2e573ef7e5a317ee6c6420bc35be2c057"
REPO = Path(__file__).resolve().parents[2]


def number(value, lo=-math.inf, hi=math.inf):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("Number outside allowed range")
    return value


def integer(value, lo=0, hi=2**53 - 1):
    number(value, lo, hi)
    if int(value) != value:
        raise ValueError("Expected an integer")
    return int(value)


def month_index(value):
    try:
        y, m = map(int, value.split("-"))
    except (ValueError, AttributeError):
        raise ValueError("Month must be YYYY-MM") from None
    if len(value) != 7 or not 1900 <= y <= 2200 or not 1 <= m <= 12:
        raise ValueError("Invalid calendar month")
    return y * 12 + m - 1


def calendar_month(index):
    return {"year": index // 12, "month": index % 12 + 1}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def private_destination(path):
    """Never put private plans, configurations, or outputs inside any Git checkout."""
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists() or parent == REPO:
            raise ValueError("Private output must be outside every Git checkout")
    return path


def write_private(path, value):
    path = private_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def apply_patch(document, operations):
    """Restricted RFC6902 importer: add/replace/remove/test only, fail closed otherwise."""
    document = copy.deepcopy(document)
    for op in operations:
        kind, pointer = op["op"], op["path"]
        if kind not in {"add", "replace", "remove", "test"}:
            raise ValueError("Unsupported export patch operation")
        if pointer == "":
            if kind in {"add", "replace"}:
                document = copy.deepcopy(op["value"])
            elif kind == "test" and document == op["value"]:
                pass
            else:
                raise ValueError("Invalid root patch")
            continue
        if not pointer.startswith("/"):
            raise ValueError("Invalid JSON pointer")
        parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]
        parent = document
        for key in parts[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent[key]
        key = parts[-1]
        if isinstance(parent, list):
            idx = len(parent) if key == "-" and kind == "add" else int(key)
            if idx < 0 or idx > len(parent) or (kind != "add" and idx == len(parent)):
                raise ValueError("Invalid array patch index")
            if kind == "add":
                parent.insert(idx, copy.deepcopy(op["value"]))
            elif kind == "remove":
                parent.pop(idx)
            elif kind == "replace":
                parent[idx] = copy.deepcopy(op["value"])
            elif parent[idx] != op["value"]:
                raise ValueError("Patch test failed")
        else:
            if kind != "add" and key not in parent:
                raise ValueError("Patch key absent")
            if kind in {"add", "replace"}:
                parent[key] = copy.deepcopy(op["value"])
            elif kind == "remove":
                del parent[key]
            elif parent[key] != op["value"]:
                raise ValueError("Patch test failed")
    return document


def load_plan(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    raw = json.loads(text[text.index("{"):])
    if "planParamsHistory" not in raw:
        plan = raw
    else:
        history = raw["planParamsHistory"]
        head = len(history) - 1 - integer(raw["reverseHeadIndex"], 0, len(history) - 1)
        plan = {}
        for item in history[:head + 1]:
            plan = apply_patch(plan, item["diff"])
    if plan.get("v") != 30:
        raise ValueError("Only current v30 plans supported; use upstream migration for others")
    return plan


def risk_to_rra(risk):
    number(risk, 0, 24)
    return math.inf if risk == 0 else 16 * math.exp(-(risk - 1) * math.log(32) / 23)


def validate_preferences(preferences):
    allowed = {"at20", "deltaAtMaxAge", "forLegacyAsDeltaFromAt20", "timePreference", "additionalAnnualSpendingTilt"}
    if set(preferences) - allowed:
        raise ValueError("Unknown preference field")
    for key, value in preferences.items():
        if key == "at20" or key == "forLegacyAsDeltaFromAt20":
            integer(value, 0, 24)
        elif key == "deltaAtMaxAge":
            integer(value, -24, 0)
        else:
            number(value, -.05, .05)
            if abs(value * 1000 - round(value * 1000)) > 1e-9:
                raise ValueError("Time preference and extra tilt use increments of 0.001")


def with_preferences(plan, preferences):
    validate_preferences(preferences)
    plan = copy.deepcopy(plan)
    risk = plan["risk"]["tpaw"]
    for key, value in preferences.items():
        if key in {"at20", "deltaAtMaxAge", "forLegacyAsDeltaFromAt20"}:
            risk["riskTolerance"][key] = value
        else:
            risk[key] = value
    # Validate preserved values too, before emitting a new scenario.
    validate_preferences({**risk["riskTolerance"], "timePreference": risk["timePreference"],
                          "additionalAnnualSpendingTilt": risk["additionalAnnualSpendingTilt"]})
    plan["results"] = None
    return plan


def read_ledger(path):
    """Explicit already-net monthly ledger. Never extrapolate pay, tax, MPF, or bonuses."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    previous = None
    for row in rows:
        index = month_index(row["month"])
        if previous is not None and index != previous + 1:
            raise ValueError("Ledger months must be unique and consecutive")
        previous = index
        for key in ("salary_net_nominal", "bonus_net_nominal", "paid_notice_net_nominal", "spending_nominal", "price_index"):
            row[key] = number(float(row[key]), 0)
        if row["price_index"] <= 0:
            raise ValueError("price_index must be positive")
        row["net_real_saving"] = (row["salary_net_nominal"] + row["bonus_net_nominal"] +
                                  row["paid_notice_net_nominal"] - row["spending_nominal"]) / row["price_index"]
        if row["net_real_saving"] < 0:
            raise ValueError("Negative pre-retirement saving requires explicit expense treatment; not supported")
    if not rows:
        raise ValueError("Empty ledger")
    return rows


def with_retirement(plan, retirement_month, ledger, start_month):
    plan = copy.deepcopy(plan)
    if plan["people"].get("withPartner"):
        raise ValueError("Retirement-month generator currently supports single-person dated plans")
    ages = plan["people"]["person1"]["ages"]
    info = ages["currentAgeInfo"]
    if ages["type"] != "retirementDateSpecified" or not info["isDatedPlan"]:
        raise ValueError("A dated plan with a specified retirement age is required")
    start, end = month_index(start_month), month_index(retirement_month)
    if end < start:
        raise ValueError("Retirement precedes ledger start")
    selected = [r for r in ledger if start <= month_index(r["month"]) < end]
    if [month_index(r["month"]) for r in selected] != list(range(start, end)):
        raise ValueError("Ledger does not cover every required working month; extrapolation refused")
    birth = info["monthOfBirth"]
    age = end - (birth["year"] * 12 + birth["month"] - 1)
    if not 0 <= age <= ages["maxAge"]["inMonths"]:
        raise ValueError("Retirement age outside plan horizon")
    ages["retirementAge"] = {"inMonths": age}
    savings = {}
    # The author schema requires unique colors across both wealth lists.
    first_color = 1 + max((x["colorIndex"] for x in plan["wealth"].get("incomeDuringRetirement", {}).values()), default=-1)
    for i, row in enumerate(selected):
        ident = uuid.uuid5(uuid.NAMESPACE_URL, "tpaw-research/ledger/" + row["month"]).hex[:10]
        if ident in savings:
            raise ValueError("Generated savings ID collision")
        savings[ident] = {"id": ident, "label": "Explicit net saving " + row["month"], "nominal": False,
                          "sortIndex": i, "colorIndex": first_color + i,
                          # Author v30 requires whole currency units. Retain the
                          # unrounded source ledger and document half-even rounding.
                          "amountAndTiming": {"type": "oneTime", "amount": round(row["net_real_saving"]),
                                              "month": {"type": "calendarMonth", "calendarMonth": calendar_month(month_index(row["month"]))}}}
    # Replace, never append: avoids counting baseline contributions and ledger twice.
    plan["wealth"]["futureSavings"] = savings
    return plan


def freeze(paths, output):
    records = [{"path": str(Path(p).resolve()), "sha256": digest(p), "bytes": Path(p).stat().st_size} for p in paths]
    write_private(output, {"schema": 1, "upstream_commit": PIN, "files": records})


def verify(manifest):
    return all(digest(r["path"]) == r["sha256"] for r in read_json(manifest)["files"])


def prepare(config_path, output):
    config = read_json(config_path)
    if config.get("upstream_commit") != PIN:
        raise ValueError("Configuration must pin the reviewed upstream commit")
    base = load_plan(config["plan"])
    if "baseline_manifest" in config and not verify(config["baseline_manifest"]):
        raise ValueError("Immutable baseline hash verification failed")
    run = config["run"]
    integer(run["seed"], 0, 2**53 - 1)
    integer(run["simulation_count"], 1, 1000000)
    if not isinstance(run["evaluation_timestamp_ms"], int) or not run.get("timezone"):
        raise ValueError("Pin evaluation_timestamp_ms and timezone explicitly")
    grid = config.get("preference_grid", {})
    for key, values in grid.items():
        if not isinstance(values, list) or not values:
            raise ValueError("Grid axes must be nonempty arrays")
        for value in values:
            validate_preferences({key: value})
    months = config.get("retirement_months", [None])
    if not months or len(months) != len(set(months)):
        raise ValueError("Retirement month list must be nonempty and unique")
    count = math.prod(map(len, grid.values())) * len(months)
    if count > integer(config.get("max_cases", 36), 1, 200):
        raise ValueError("Batch exceeds explicit max_cases; stage the experiment")
    ledger = read_ledger(config["ledger"]) if any(m is not None for m in months) else None
    root = private_destination(output)
    if root.exists():
        raise ValueError("Output already exists; use a fresh directory")
    snapshot = run.get("market_snapshot")
    snapshot_hash = digest(snapshot) if snapshot else None
    inputs = {"plan_sha256": digest(config["plan"]), "config_sha256": digest(config_path),
              "market_snapshot_sha256": snapshot_hash, "ledger_sha256": digest(config["ledger"]) if ledger else None}
    cases = []
    for retirement, values in itertools.product(months, itertools.product(*grid.values())):
        prefs = dict(zip(grid, values))
        plan = with_preferences(base, prefs)
        if retirement is not None:
            plan = with_retirement(plan, retirement, ledger, config["ledger_start_month"])
        ident = "case-" + str(len(cases) + 1).zfill(3)
        case = {"id": ident, "status": "not_run", "scenario_type": "deterministic_retirement_month",
                "retirement_month": retirement, "preferences": prefs, "run": run,
                "upstream_commit": PIN, "inputs": inputs,
                "sampling": plan["advanced"]["sampling"],
                "longevity": config.get("longevity", {"type": "baseline_fixed_horizon"}),
                "blockers": ["Prepared only; requires author encoding and offline engine execution"] +
                            ([] if snapshot else ["Market snapshot unavailable"]),
                "plan": plan}
        cases.append(case)
    # All validation completes before any files are emitted.
    for case in cases:
        write_private(root / (case["id"] + ".json"), case)
    write_private(root / "manifest.json", {"schema": 1, "status": "prepared_not_simulated", "inputs": inputs,
                                           "case_ids": [c["id"] for c in cases], "count": count})
    return count


class PeriodLifeTable:
    """Use official l(x), T(x), e(x). The age-100 row is an OPEN age interval."""
    def __init__(self, rows):
        self.rows = {integer(r["age"], 0, 100): r for r in rows}
        if sorted(self.rows) != list(range(101)) or len(rows) != 101:
            raise ValueError("Require each age 0..99 and open age 100 exactly once")
        for age, row in self.rows.items():
            number(row["lx"], 0)
            number(row["ex"], 0)
            number(row["qx"], 0, 1)
            if row["lx"] <= 0 or (age and row["lx"] > self.rows[age - 1]["lx"]):
                raise ValueError("Invalid survivor curve")
            if age < 100 and abs(self.rows[age + 1]["lx"] - row["lx"] * (1 - row["qx"])) > 3:
                raise ValueError("qx and lx inconsistent beyond source rounding")

    def survivors(self, age):
        number(age, 0, 100)
        a = int(age)
        if a == 100:
            return self.rows[100]["lx"]
        return self.rows[a]["lx"] * (1 - (age - a)) + self.rows[a + 1]["lx"] * (age - a)

    def survival(self, current_age, horizon):
        number(current_age, 0, 100)
        number(horizon, current_age)
        return None if horizon > 100 else self.survivors(horizon) / self.survivors(current_age)

    def quantile(self, age, probability):
        number(probability, 0, 1)
        number(age, 0, 100)
        target = self.survivors(age) * (1 - probability)
        if target < self.rows[100]["lx"]:
            return None  # Censored: quantile lies in open age-100 interval.
        for a in range(int(age), 100):
            high, low = self.rows[a]["lx"], self.rows[a + 1]["lx"]
            if high >= target >= low and high > low:
                return max(age, a + (high - target) / (high - low))
        return 100.0

    def diagnostics(self, age, margin=5):
        age = integer(age, 0, 100)
        number(margin, 0, 30)
        # Official e(x) is used, not a truncated integral that kills everyone at 100.
        mean = age + self.rows[age]["ex"]
        horizon = mean + margin
        return {"current_age": age, "mean_age_at_death": mean, "rolling_mean_plus_margin_age": horizon,
                "margin_years": margin, "survival_beyond_rolling_horizon": self.survival(age, horizon),
                "fixed_age_90": 90, "survival_beyond_90": self.survival(age, max(90, age)),
                "death_age_q90": self.quantile(age, .90), "death_age_q95": self.quantile(age, .95),
                "death_age_q99": self.quantile(age, .99), "survival_to_100": self.survival(age, 100),
                "tail_note": "Null quantiles/probabilities require mortality within/after the open age-100 interval; never assume death at 100",
                "method": "Frozen period mortality; linear interpolation of lx between integer ages; not a cohort forecast"}


def cohort_survival(q_by_year_age, year, age, years):
    """Optional projected/cohort scenario: fail when future calendar-year rates absent."""
    integer(year, 1900, 2200)
    integer(age, 0, 130)
    integer(years, 0, 130)
    survival = [1.0]
    for t in range(years):
        if (year + t, age + t) not in q_by_year_age:
            raise ValueError("Missing projected cohort mortality; extrapolation refused")
        q = number(q_by_year_age[(year + t, age + t)], 0, 1)
        survival.append(survival[-1] * (1 - q))
    return survival


def conditional_policy(path, initial_state, transition, estimate, base_month, max_delay_years, spending_floor):
    """Generic state machine; transition/estimate must use observed data only.

    Not wired into TPAW. estimate(state, past_observations) returns current affordable
    real spending under the chosen horizon. No resampling or discarded bad paths.
    """
    integer(base_month, 0, len(path) - 1)
    integer(max_delay_years, 0, 2)
    number(spending_floor, 0)
    last = base_month + 12 * max_delay_years
    if last >= len(path):
        raise ValueError("Path must extend through last decision date")
    state = copy.deepcopy(initial_state)
    retired = False
    decision = None
    ledger = []
    observations = []
    for month, observation in enumerate(path):
        # Decision at START of month: current month's future return is not observed.
        if not retired and month >= base_month and (month - base_month) % 12 == 0:
            spending = number(estimate(copy.deepcopy(state), tuple(copy.deepcopy(observations))), 0)
            passed = spending >= spending_floor
            if passed or month == last:
                retired = True
                decision = {"retirement_month_index": month, "delay_years": (month - base_month) // 12,
                            "criterion_met": passed, "forced_at_cap_below_floor": not passed,
                            "spending_at_decision": spending}
        # The same state and same exogenous path continue after retirement.
        state, actual_spending, allocation = transition(state, observation, retired, month)
        ledger.append({"month": month, "retired": retired, "spending": number(actual_spending, 0),
                       "allocation": number(allocation, 0, 1)})
        observations.append(copy.deepcopy(observation))
    return {"decision": decision, "ledger": ledger, "ending_state": state}


def policy_summary(results, floor):
    """Joint denominator includes every original path, including forced bad outcomes."""
    if not results:
        raise ValueError("No paths")
    n = len(results)
    joint = []
    for delay in (0, 1, 2):
        group = [r for r in results if r["decision"]["delay_years"] == delay]
        joint.append({"delay_years": delay, "paths": len(group), "probability_of_all_paths": len(group) / n,
                      "below_floor_at_decision_joint_probability": sum(r["decision"]["spending_at_decision"] < floor for r in group) / n})
    return {"path_count": n, "joint": joint, "all_path_shortfall_probability":
            sum(any(x["retired"] and x["spending"] < floor for x in r["ledger"]) for r in results) / n}


def path_metrics(real_monthly_spending, budgets, real_bequest):
    """Retirement months only, before death censoring; currency/base date must match.

    A zero-wealth path stays in the input with its actual spending and shortfall.
    Recovery means returning to the previous spending high-water mark.
    """
    spending = [number(x, 0) for x in real_monthly_spending]
    if not spending:
        raise ValueError("No retirement consumption observations")
    if set(budgets) != {"preferred", "reduced", "minimum"}:
        raise ValueError("Three explicit budget levels required")
    for value in budgets.values():
        number(value, 0)
    if not budgets["preferred"] >= budgets["reduced"] >= budgets["minimum"]:
        raise ValueError("Budgets must be ordered preferred >= reduced >= minimum")
    outcome = {"initial_monthly_spending": spending[0], "lifetime_real_consumption": sum(spending),
               "real_bequest": number(real_bequest, 0)}
    for name, budget in budgets.items():
        below = [x < budget for x in spending]
        longest = max((sum(1 for _ in group) for value, group in itertools.groupby(below) if value), default=0)
        outcome[name] = {"ever_below": any(below), "months_below": sum(below), "longest_spell_months": longest,
                         "cumulative_shortfall": sum(max(0, budget - x) for x in spending)}
    high = spending[0]
    depth, spell, longest, still_below = 0, 0, 0, False
    for value in spending:
        if value < high:
            depth = max(depth, 1 - value / high) if high else depth
            spell += 1
            still_below = True
            longest = max(longest, spell)
        else:
            high, spell, still_below = value, 0, False
    mean = sum(spending) / len(spending)
    outcome.update({"deepest_cut_from_high_water": depth, "longest_recovery_spell_months": longest,
                    "recovery_right_censored": still_below,
                    "consumption_standard_deviation": math.sqrt(sum((x - mean)**2 for x in spending) / len(spending)),
                    "monthly_spending_after_10_years": spending[120] if len(spending) > 120 else None,
                    "monthly_spending_after_20_years": spending[240] if len(spending) > 240 else None})
    return outcome


def compare_summaries(paths, output):
    """Compare adapter summaries only after strict common-assumption validation."""
    records = [read_json(p) for p in paths]
    if not records:
        raise ValueError("No summaries supplied")
    controls = ("engine_commit", "market_snapshot_sha256", "path_set_sha256", "seed", "simulation_count",
                "sampling", "precision", "evaluation_timestamp_ms", "currency", "purchasing_power_date",
                "fees", "tax", "fx", "comparison_design")
    common = {k: records[0]["controls"][k] for k in controls}
    for record in records:
        if record.get("status") != "simulated" or not all(record["controls"].get(k) == v for k, v in common.items()):
            raise ValueError("Unsimulated or incomparable summaries")
        if any(v is None for v in record["controls"].values()):
            raise ValueError("Unknown assumptions cannot be silently treated as matched")
        if len(record["path_outcomes"]) != common["simulation_count"]:
            raise ValueError("Path denominator mismatch")
        ids = [x["path_id"] for x in record["path_outcomes"]]
        if len(set(ids)) != len(ids) or set(ids) != {x["path_id"] for x in records[0]["path_outcomes"]}:
            raise ValueError("Every common path must be retained exactly once")
    write_private(output, {"schema": 1, "controls": common, "scenarios": records,
                           "ranking": None, "note": "No optimum selected; compare spending and hardship jointly"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("freeze")
    p.add_argument("--output", required=True)
    p.add_argument("files", nargs="+")
    p = commands.add_parser("verify")
    p.add_argument("manifest")
    p = commands.add_parser("prepare")
    p.add_argument("config")
    p.add_argument("--output", required=True)
    p = commands.add_parser("longevity")
    p.add_argument("table")
    p.add_argument("--ages", nargs="+", type=int, required=True)
    p.add_argument("--margin", type=float, default=5)
    p.add_argument("--output", required=True)
    p = commands.add_parser("compare")
    p.add_argument("summaries", nargs="+")
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            freeze(args.files, args.output)
            print("Baseline fingerprints saved outside Git")
        elif args.command == "verify":
            if not verify(args.manifest):
                raise ValueError("Baseline fingerprints changed")
            print("PASS: all frozen original file fingerprints unchanged")
        elif args.command == "prepare":
            count = prepare(args.config, args.output)
            print(f"Prepared {count} cases; NOT SIMULATED")
        elif args.command == "compare":
            compare_summaries(args.summaries, args.output)
            print("Comparable simulation summaries exported; no optimum selected")
        else:
            data = read_json(args.table)
            table = PeriodLifeTable(data["rows"])
            write_private(args.output, {"source": data["source"], "data_sha256": digest(args.table),
                                       "diagnostics": [table.diagnostics(a, args.margin) for a in args.ages]})
            print("Life-table diagnostics saved; no spending simulation performed")
    except (ValueError, KeyError, OSError, TypeError) as exc:
        # No raw plans, paths, adapter output, or personal numbers in command logs.
        print("ERROR: research input or output validation failed (" + type(exc).__name__ + ")", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
