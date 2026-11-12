"""Read-only policy check against hash-verified private native marginal outputs.

This validates spending as a function of native beginning balances. It does not
validate a new sampler, account ledger or full-path floating-point equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
from tpaw_lab.policy import PolicyPlan, TpawPolicy


def load_verified(case_path: Path, decoded_path: Path, request_path: Path, result_path: Path):
    case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    decoded = json.loads(decoded_path.read_text(encoding="utf-8-sig"))
    for key, path in (("request_sha256", request_path), ("result_sha256", result_path)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != decoded[key]:
            raise ValueError("Native artifact hash mismatch")
    return case,decoded


def plan_from_export(case:dict,decoded:dict,retirement_month:int)->PolicyPlan:
    result = decoded["result"]
    processed = result["planParamsProcessed"]
    cash = processed["amountTimed"]
    future, income, essential, discretionary = [tuple(x / 100 for x in cash[k]["totalX100"])
                for k in ("wealthFutureSavings", "wealthIncomeDuringRetirement", "extraExpensesEssential", "extraExpensesDiscretionary")]
    risk = processed["risk"]["tpaw"]
    preferences = case["plan"]["risk"]["tpaw"]
    returns = processed["returnsStatsForPlanning"]
    arrays = result["arrays"]
    balances = arrays["byPercentileByMfnSimulatedPercentileMajorBalanceStartX100"]
    adjustments = processed["adjustmentsToSpending"]["tpawAndSpaw"]
    if set(adjustments) != {"legacy"}:
        raise ValueError("This audit currently requires an unconstrained spending case")
    n = len(income)
    return PolicyPlan(balances[0] / 100, retirement_month, tuple(a+b for a,b in zip(future,income)),
                   essential, discretionary, tuple(risk["rraUnclampedIncludingPosInfinityByMfn"]), (n,) * n,
                   returns["stocks"]["empiricalAnnualNonLogExpectedReturn"],
                   returns["bonds"]["empiricalAnnualNonLogExpectedReturn"],
                   returns["stocks"]["empiricalAnnualLogVariance"], preferences["timePreference"],
                   preferences["additionalAnnualSpendingTilt"], adjustments["legacy"]["target"],
                   risk["legacyRraIncludingPosInfinity"])


def audit(case_path: Path, decoded_path: Path, request_path: Path, result_path: Path, retirement_month: int) -> dict:
    case,decoded=load_verified(case_path,decoded_path,request_path,result_path)
    p=plan_from_export(case,decoded,retirement_month)
    n=len(p.income)
    arrays=decoded["result"]["arrays"]
    balances=arrays["byPercentileByMfnSimulatedPercentileMajorBalanceStartX100"]
    general=arrays["byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100"]
    policy = TpawPolicy(p)
    errors = []
    relative = []
    for i, native in enumerate(general):
        m = i % n
        predicted = policy.step(balances[i] / 100, m)["general"]
        error = abs(predicted - native / 100)
        errors.append(error)
        relative.append(error / max(1, native / 100))
    return {"checks": len(errors), "max_absolute_general_error": max(errors), "max_relative_general_error": max(relative),
            "pass": all(e <= max(1.0, abs(v/100)*.0002) for e,v in zip(errors,general)),
            "tolerance": "max(1 currency unit, 0.02%); CUDA uses float32 policy/NPV, portable port float64",
            "scope": "Monthly native marginal beginning balance to spending map; monotone spending ranking; no new market paths or defensive ledger validated",
            "request_sha256": decoded["request_sha256"], "result_sha256": decoded["result_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("case", "decoded", "request", "result"):
        parser.add_argument("--"+name, required=True, type=Path)
    parser.add_argument("--retirement-month", required=True, type=int)
    a = parser.parse_args()
    report = audit(a.case, a.decoded, a.request, a.result, a.retirement_month)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
