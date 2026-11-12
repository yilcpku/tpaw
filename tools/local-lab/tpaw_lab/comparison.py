"""Paired equity-channel withdrawal outcomes with an exact Shapley bridge.

Currency of the common cash ledger and lifestyle budget remains CNY. These are
counterfactual *equity real-return factors*, not investable USD-deposit portfolios.
"""
from dataclasses import replace
import itertools
import math
from .simulation import simulate,quantile

CHANNELS=("global_equity","fx","china_inflation")


def channel_history(history,enabled:frozenset):
    rows=[]
    for row in history.rows:
        nominal=row.global_equity_usd_gross if "global_equity" in enabled else row.us_equity_usd_gross
        fx=row.cny_per_usd_gross if "fx" in enabled else 1
        cpi=row.china_cpi_gross if "china_inflation" in enabled else row.us_cpi_gross
        target_real=nominal*fx/cpi
        # Existing ledger applies FX / ChinaCPI once. Algebraically compensate
        # only the synthetic equity factor so all other accounting stays fixed.
        adjusted=target_real*row.china_cpi_gross/row.cny_per_usd_gross
        rows.append(replace(row,global_equity_usd_gross=adjusted))
    return replace(history,rows=tuple(rows),kind="synthetic_stress",
                   label="Paired equity-return channel control",
                   limitations=history.limitations+("Equity return-channel counterfactual; CNY budget, nominal defensive contracts and CPI publication timing are held common.",))


def outcome_vector(result):
    initial=[sum(r["lifestyle_real"] for r in p["records"][p["retirement_month"]:p["retirement_month"]+12]) for p in result["paths"]]
    d=result["distributions"]
    return {"initial_period_spending_median":quantile(initial,.5),
            "death_before100_estate_median":d["estate_at_death_before100_q5_q50_q95"][1],
            "late_max_budget_cut_fraction_median":d["late_max_budget_cut_fraction_q5_q50_q95"][1],
            "late_longest_cut_months_median":d["late_longest_short_spell_months_q5_q50_q95"][1],
            "assets_alive100_median":d["assets_if_alive100_q5_q50_q95"][1],
            "unfunded_consumption_path_fraction":d["sampling_path_fraction_any_unfunded_consumption"]}


def compare_channels(s,history,table):
    if s.get("use_forward_targets",True):
        # Recalibrating every counterfactual to the same mean and volatility
        # would remove some of the very differences being measured.
        source_mode="Raw source return factors; forward calibration disabled only for this attribution panel. Planning expectations remain identical."
    else: source_mode="Raw source return factors; planning expectations held identical."
    cases={};signatures=set()
    for mask in range(8):
        enabled=frozenset(c for i,c in enumerate(CHANNELS) if mask & (1<<i))
        case=simulate({**s,"use_forward_targets":False},channel_history(history,enabled),table)
        signatures.add(case["provenance"]["sample_index_sha256"])
        cases[mask]={"enabled":sorted(enabled),"metrics":outcome_vector(case),
                     "initial_spending_months_min_max":case['distributions']['initial_spending_months_min_max']}
    if len(signatures)!=1: raise ArithmeticError("Attribution paths were not paired")
    contributions={channel:{metric:0. for metric in cases[0]["metrics"]} for channel in CHANNELS}
    for order in itertools.permutations(range(3)):
        mask=0
        for i in order:
            after=mask|(1<<i)
            for metric in contributions[CHANNELS[i]]:
                contributions[CHANNELS[i]][metric]+=(cases[after]["metrics"][metric]-cases[mask]["metrics"][metric])/6
            mask=after
    for metric in cases[0]["metrics"]:
        total=cases[7]["metrics"][metric]-cases[0]["metrics"][metric]
        if not math.isclose(total,sum(c[metric] for c in contributions.values()),rel_tol=1e-9,abs_tol=1e-7):
            raise ArithmeticError("Outcome attribution bridge failed")
    return {"cases":cases,"shapley_contributions":contributions,"matched_sample_index_sha256":signatures.pop(),
            "method":"8 paired counterfactuals; equal average over6 channel orders. Nonlinear metric differences add exactly, not unique causal estimates.",
            "return_mode":source_mode,"varied_fields":list(CHANNELS),
            "held_fixed":["CNY lifestyle budget and consumption deflator","nominal defensive contracts and rate changes","planning expectations and risk preferences","candidate dates and notice policy","reserve/cash-floor rules","joint sample indices"],
            "limits":["Base equity factor is broad US nominal / US CPI; full factor is global nominal × CNY/USD / China CPI.",
                      "Only equity factors change; every case retains a common CNY cash ledger. This is outcome attribution of the equity-return bridge, not an executable US-dollar household plan.",
                      "CPI contribution switches both countries' inflation factors together (US CPI versus China CPI); it does not establish causation.",
                      "Sampled path fractions are scenario frequencies, not future safety probabilities."]}
