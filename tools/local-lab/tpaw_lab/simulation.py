"""Pathwise TPAW research policy with nominal CNY asset/liquidity ledgers.

No account connections or network. Only the selected recorded history is sampled.
The unchanged original native executable remains a separate benchmark.
"""
import copy
from dataclasses import dataclass
import hashlib
import math
import statistics
from .defensive import DefensiveSleeve, PartitionedAssets
from .longevity import LifeTable
from .market import JointHistory, calibrate_equity, contiguous_blocks, finite, month_index
from .policy import PolicyPlan, TpawPolicy
from .yields import TENORS, apply_observed_change, curve_yield
from .cashflows import FlowSchedule,compile_flows


def rra_curve(age_months: int, months: int, at20: float, delta_at90: float = -2) -> tuple[float, ...]:
    # Pinned author constants: 25 integer settings (0..24), 16 to 0.5 RRA.
    if not 0 <= finite(at20, "risk tolerance") <= 24:
        raise ValueError("Risk tolerance outside 0..24")
    if not -24<=finite(delta_at90,"risk delta at90")<=0:
        raise ValueError("Risk delta at90 outside-24..0")
    def rra(tolerance):
        return math.inf if tolerance <= 0 else 16 * math.exp(-(tolerance-1) * math.log(32) / 23)
    return tuple(rra(max(0, at20 + delta_at90 * (min(max(age_months+m,240),1080)-240) / (1080-240))) for m in range(months))


def quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    p = q * (len(values)-1)
    lo, hi = math.floor(p), math.ceil(p)
    return values[lo] + (values[hi]-values[lo]) * (p-lo)


def weighted_quantile(pairs: list[tuple[float,float]], q: float) -> float:
    pairs=sorted((value,weight) for value,weight in pairs if weight>0)
    mass=sum(weight for _,weight in pairs)
    if not pairs or not 0<=q<=1:
        raise ValueError("Invalid weighted outcome distribution")
    running=0.0
    for value,weight in pairs:
        running+=weight
        if running>=q*mass:
            return value
    return pairs[-1][0]


def candidates(s: dict, months: int) -> tuple[int, ...]:
    evaluation = month_index(s.get("evaluation_month", "2026-11"))
    dates = [month_index(x.strip())-evaluation for x in s["candidates"].split(",")]
    notice = s["notice_months"]
    if type(notice) is not int or notice < 0 or notice > 24 or not dates or len(dates) > 24:
        raise ValueError("Invalid notice period or candidate count")
    if dates != sorted(set(dates)) or dates[0] < notice or dates[-1] >= months:
        raise ValueError("候选退休月份必须递增、覆盖通知期，并在模拟区间内。")
    return tuple(dates)


def prepare(s: dict, history: JointHistory, table: LifeTable):
    age = finite(s["current_age"], "current age")
    if not 18 <= age < 100 or not math.isclose(age*12, round(age*12)):
        raise ValueError("Age must have month precision between 18 and 100")
    age_months = round(age*12)
    ends = table.schedule(age_months, s["horizon"], s["margin"])
    months, planning = len(ends), max(ends)
    exits = candidates(s, months)
    assets, reserve = finite(s["initial_assets"], "initial assets", 0), finite(s["reserve"], "reserve", 0)
    funding=s.get("reserve_funding","initial")
    if funding=="initial" and reserve > assets:
        raise ValueError("准备金超过总资产；它应从已有资产中划出。")
    runs = s["runs"]
    if type(runs) is not int or not 1 <= runs <= 1000:
        raise ValueError("Runs must lie in 1..1000")
    finite(s["annual_budget"], "annual budget", 0)
    finite(s["threshold_annual"], "retirement threshold", 0)
    finite(s.get("monthly_savings",0), "known monthly net savings", 0)
    finite(s["cash_multiple"], "cash-floor multiple", 0)
    if not 0 <= s["cash_multiple"] <= 10:
        raise ValueError("Cash floor multiple outside 0..10")
    if type(s["term_years"]) is not int or not 1 <= s["term_years"] <= 30:
        raise ValueError("Defensive term outside 1..30 years")
    if s.get("defensive_rate_mode","constant") not in ("constant","history"):
        raise ValueError("Unknown defensive-rate scenario")
    persistence=finite(s.get("rate_persistence",1),"rate persistence",0)
    if persistence>1: raise ValueError("Rate persistence outside0..1")
    if s.get("defensive_rate_mode")=="history":
        if any(r.government_curve is None or r.deposit_curve is None or r.demand_rate is None for r in history.rows):
            raise ValueError("历史利率模式需要两个月末的国债、存款和活期曲线；旧的假设利率数据不可用于此模式。")
        if s["defensive"]=="deposit" and s["term_years"] not in (1,2,3,5):
            raise ValueError("挂牌存款历史只支持1、2、3、5年整存整取期限。")
    for field,default in (("initial_deposit_rate",.02),("initial_government_yield",.02),("demand_rate",.001),("reserve_cash_rate",.001)):
        if not 0 <= finite(s.get(field,default),field) <= .5:
            raise ValueError("Nominal defensive rates must lie in 0..50%")
    if s.get("demand_rate",.001)>s.get("initial_deposit_rate",.02):
        raise ValueError("Early-break demand rate exceeds the term-deposit rate")
    mu, bond = finite(s["stock_return"], "stock expectation")/100, finite(s["planning_defensive_return"], "bond expectation")/100
    vol = finite(s["stock_volatility"], "stock volatility", .01)/100
    h = calibrate_equity(history,"global","cny",mu,vol) if s.get("use_forward_targets",True) else history
    indices = contiguous_blocks(h,months,runs,s["seed"])
    policies,flows = [],[]
    risk = rra_curve(age_months,planning,s["risk_tolerance"],s.get("risk_delta_at90",-2))
    if s.get("policy_rra"):
        supplied=s["policy_rra"]
        if not isinstance(supplied,list) or not supplied:raise ValueError("Invalid imported risk schedule")
        risk=tuple(supplied[m] if m<len(supplied) else supplied[-1] for m in range(planning))
    variance=finite(s.get("policy_variance_annual",vol*vol),"planning stock variance",1e-12)
    for exit_month in exits:
        flow=compile_flows(s,planning,exit_month);flows.append(flow)
        essential=tuple(a+b for a,b in zip(flow.planned("essential"),flow.planned("reserve_transfer")))
        policies.append(TpawPolicy(PolicyPlan(assets-(reserve if funding=="initial" else 0),exit_month,
                         flow.planned("income"),essential,flow.planned("discretionary"),risk,ends,
                         mu,bond,variance,s["time_preference"],s.get("additional_spending_tilt",0),
                         s.get("legacy_target",0),s.get("legacy_rra",4))))
    return age_months, h, indices, exits, policies,flows


@dataclass(frozen=True)
class MonthStartResult:
    decision:dict
    income:float
    requested:float
    paid:float
    paid_general:float
    paid_lifestyle:float
    budget:float
    floor:dict
    funding_short:float
    reserve_paid:float
    reserve_short:float
    essential:float
    paid_essential:float
    stock_fraction_actual:float


def apply_month_start(s:dict,account:PartitionedAssets,policy:TpawPolicy,flow:FlowSchedule|None,m:int,known_cpi:float,retirement:int|None)->MonthStartResult:
    decision = policy.step(account.core_value/known_cpi,m)
    income = flow.nominal("income",m,known_cpi) if flow else decision["income"]*known_cpi
    account.defensive.cash += income
    funding_short=0.
    if flow:
        transfer=flow.nominal("reserve_transfer",m,known_cpi)
        if transfer:funding_short=account.fund_reserve(transfer)["shortfall"]
        essential=flow.nominal("essential",m,known_cpi)
        disc_scale=decision["target_discretionary"]/policy.plan.discretionary[m] if policy.plan.discretionary[m] else 0.
        discretionary=flow.nominal("discretionary",m,known_cpi)*disc_scale
        general=decision["target_general"]*known_cpi
        budget=flow.nominal("budget",m,known_cpi)
        lifestyle_essential=flow.nominal("lifestyle_essential",m,known_cpi)
        lifestyle_discretionary=flow.nominal("lifestyle_discretionary",m,known_cpi)*disc_scale
    else:
        essential=policy.plan.essential[m]*known_cpi
        discretionary=decision["target_discretionary"]*known_cpi
        general=decision["target_general"]*known_cpi
        budget=s["annual_budget"]*known_cpi
        lifestyle_essential=essential;lifestyle_discretionary=discretionary
    requested = essential+discretionary+general
    paid = account.defensive.release(requested)
    equity_sale = min(account.equity,max(0.0,requested-paid))
    account.equity -= equity_sale
    paid += equity_sale
    paid_essential=min(paid,essential);remaining=paid-paid_essential
    paid_discretionary=min(remaining,discretionary);paid_general=min(general,remaining-paid_discretionary)
    paid_lifestyle=paid_general+(paid_essential*lifestyle_essential/essential if essential else 0)+(paid_discretionary*lifestyle_discretionary/discretionary if discretionary else 0)
    floor = account.replenish_cash(budget,s["cash_multiple"],s.get("floor_trigger_fraction",1.0))
    rebalance=account.rebalance_equity(decision["stock_fraction"],budget*s["cash_multiple"])
    account.defensive.invest_cash_above(budget*s["cash_multiple"])
    reserve_paid = reserve_short = 0.0
    if flow:
        requested_draw=flow.nominal("reserve_draw",m,known_cpi)
        result=account.reserve_withdrawal(requested_draw)
        reserve_paid=result["paid"];reserve_short=result["shortfall"]
    elif retirement is not None:
        for draw in s.get("reserve_draws",[]):
            if m==retirement+draw["months_after_retirement"]:
                result=account.reserve_withdrawal(draw["real_amount"]*known_cpi)
                reserve_paid+=result["paid"];reserve_short+=result["shortfall"]
    return MonthStartResult(decision=decision,income=income,requested=requested,paid=paid,paid_general=paid_general,paid_lifestyle=paid_lifestyle,budget=budget,floor=floor,funding_short=funding_short,reserve_paid=reserve_paid,reserve_short=reserve_short,essential=essential,paid_essential=paid_essential,stock_fraction_actual=rebalance["actual_stock_fraction"])


def project_notice(s:dict,account:PartitionedAssets,policy:TpawPolicy,flow:FlowSchedule|None,m:int,retirement:int,known_cpi:float,lag:int)->float:
    """Forecast the same nominal ledger, with no future realized observations.

    Use explicit planning CPI, expected real equity and currently known contractual
    rates/curves. CPI publication lag and protected cash remain operative.
    """
    projected=copy.deepcopy(account)
    inflation=(1+s.get("planning_cpi",.02))**(1/12)
    known_origin=max(0,m-lag)
    for future in range(m,retirement):
        forecast_known_cpi=known_cpi*inflation**(max(0,future-lag)-known_origin)
        apply_month_start(s,projected,policy,flow,future,forecast_known_cpi,retirement)
        gross_equity=(1+policy.expected_stock)*inflation
        projected.equity*=gross_equity;projected.reserve_equity*=gross_equity
        projected.reserve_cash*=(1+s.get("reserve_cash_rate",projected.defensive.demand_rate))**(1/12)
        sleeve=projected.defensive
        sleeve.advance(sleeve.known_deposit_rate,sleeve.known_government_yield)
    forecast_known_cpi=known_cpi*inflation**(max(0,retirement-lag)-known_origin)
    probe=apply_month_start(s,projected,policy,flow,retirement,forecast_known_cpi,retirement)
    forecast_price=known_cpi*inflation**(retirement-known_origin)
    return 12*probe.paid_lifestyle/forecast_price


def run_path(s: dict, history: JointHistory, indices: tuple[int, ...], exits: tuple[int,...], policies: list[TpawPolicy], flows:list[FlowSchedule]|None=None) -> dict:
    assets, reserve = s["initial_assets"], s["reserve"]
    initial_reserve=reserve if s.get("reserve_funding","initial")=="initial" else 0.
    initial_cash = min(assets-initial_reserve,s["annual_budget"]*s["cash_multiple"])
    account = PartitionedAssets(assets-initial_reserve-initial_cash,
                                DefensiveSleeve(initial_cash,kind=s["defensive"],term_months=s["term_years"]*12,
                                                known_deposit_rate=s.get("initial_deposit_rate",.02),
                                                known_government_yield=s.get("initial_government_yield",.02),
                                                demand_rate=s.get("demand_rate",.001)),initial_reserve/2,initial_reserve/2)
    if s.get("defensive_rate_mode")=="history":
        account.defensive.set_government_curve({str(t):s.get("initial_government_yield",.02) for t in TENORS})
        account.defensive.deposit_curve={str(t):s.get("initial_deposit_rate",.02) for t in (3,6,12,24,36,60)}
    cpis = [1.0]
    active, committed, retirement, forced, projection = 0, False, None, False, None
    records, reviews = [], []
    lag = s.get("cpi_publication_lag_months",1)
    if type(lag) is not int or not 0 <= lag <= 12:
        raise ValueError("CPI lag must lie in 0..12 months")
    for m, index in enumerate(indices):
        cpi, known_cpi = cpis[-1], cpis[max(0,len(cpis)-1-lag)]
        # No realized month-m observation is read until decisions are final.
        if not committed and m == exits[active]-s["notice_months"]:
            policy = policies[active]
            projection=project_notice(s,account,policy,flows[active] if flows else None,m,exits[active],known_cpi,lag)
            passed = projection >= s["threshold_annual"]
            reviews.append({"month":m,"candidate":exits[active],"projected_annual_general":projection,"passed":passed})
            if passed or active == len(exits)-1:
                committed, retirement, forced = True,exits[active],not passed
            else:
                active += 1
        policy = policies[active]
        flow=flows[active] if flows else None
        start = account.total_value
        loss_before = account.defensive.lost_accrued_interest
        step=apply_month_start(s,account,policy,flow,m,known_cpi,retirement)
        row = history.rows[index]  # month-m realized data become visible here
        eq_gross = row.global_equity_usd_gross*row.cny_per_usd_gross
        before_returns = account.total_value
        account.equity *= eq_gross
        account.reserve_equity *= eq_gross
        account.reserve_cash *= (1+s.get("reserve_cash_rate",account.defensive.demand_rate))**(1/12)
        clamps=0
        if s.get("defensive_rate_mode")=="history":
            phi=s.get("rate_persistence",1)
            next_curve,c=apply_observed_change(account.defensive.government_curve,row.government_curve_before,row.government_curve,phi);clamps+=c
            next_deposit_curve,c=apply_observed_change(account.defensive.deposit_curve,row.deposit_curve_before,row.deposit_curve,phi);clamps+=c
            next_demand,c=apply_observed_change({"demand":account.defensive.demand_rate},{"demand":row.demand_rate_before},{"demand":row.demand_rate},phi);clamps+=c
            next_deposit=next_deposit_curve[str(s["term_years"]*12)] if s["defensive"]=="deposit" else next_deposit_curve["60"]
            next_government=curve_yield(next_curve,s["term_years"]*12)
            account.defensive.advance(next_deposit,next_government,next_curve,next_deposit_curve,next_demand["demand"])
        else:
            account.defensive.advance(s.get("initial_deposit_rate",.02),s.get("initial_government_yield",.02))
        market_change = account.total_value-before_returns
        # Selling a deposit can forfeit booked interest. Record this separately.
        transfer_loss = account.defensive.lost_accrued_interest-loss_before
        if not math.isclose(account.total_value,start+step.income-step.paid-step.reserve_paid-transfer_loss+market_change,abs_tol=.01):
            raise ArithmeticError("Nominal account identity failed")
        record = {"month":m,"sample_index":index,"sample_month":row.month,"cpi_start":cpi,"cpi_known":known_cpi,
                  "general_real":step.paid_general/cpi,"total_real":step.paid/cpi,"lifestyle_real":step.paid_lifestyle/cpi,
                  "lifestyle_budget_real":(flow.budget_real[m]+flow.budget_nominal[m]/cpi) if flow else s["annual_budget"],"essential_real":step.paid_essential/cpi,
                  "reserve_withdrawal_real":step.reserve_paid/cpi,"reserve_funding_short_real":step.funding_short/cpi,
                  "household_total_real":(step.paid+step.reserve_paid)/cpi,
                  "core_end_real":account.core_value/(cpi*row.china_cpi_gross),
                  "estate_end_real":account.total_value/(cpi*row.china_cpi_gross),
                  "cash_floor_short_real":step.floor["shortfall"]/cpi,"reserve_short_real":step.reserve_short/cpi,
                  "unfunded_consumption_real":max(0.0,step.requested-step.paid)/cpi,
                  "unfunded_essential_real":max(0.,step.essential-step.paid_essential)/cpi,
                  "transfer_interest_loss_real":transfer_loss/cpi,"stock_fraction_after_spending":step.stock_fraction_actual,"policy_stock_fraction_after_spending":step.decision["stock_fraction"]}
        record.update(rate_zero_floor_clamps=clamps,known_government_yield_end=account.defensive.known_government_yield,
                      known_deposit_rate_end=account.defensive.known_deposit_rate,known_demand_rate_end=account.defensive.demand_rate)
        records.append(record)
        cpis.append(cpi*row.china_cpi_gross)
    if retirement is None:
        raise ArithmeticError("Final retirement cap was not exercised")
    actual = records[retirement]["lifestyle_real"]*12
    return {"retirement_month":retirement,"commitment_month":retirement-s["notice_months"],"forced_below_threshold":forced,
            "actual_exit_below_threshold":actual<s["threshold_annual"],"projected_exit_general_annual":projection,
            "actual_exit_general_annual":actual,"reviews":reviews,"records":records}


def simulate(s: dict, history: JointHistory, table: LifeTable) -> dict:
    age_months,h,indices,exits,policies,flows = prepare(s,history,table)
    paths = [run_path(s,h,draw,exits,policies,flows) for draw in indices]
    weights = table.weights(age_months,len(indices[0]))
    profiles = []
    for m in range(0,len(indices[0]),12):
        # Annual sum of monthly general consumption; final partial year marked.
        values = [sum(r["lifestyle_real"] for r in path["records"][m:m+12]) for path in paths]
        profiles.append({"age":(age_months+m)/12,"p5":quantile(values,.05),"p50":quantile(values,.5),"p95":quantile(values,.95),
                         "months_summed":min(12,len(indices[0])-m)})
    late_start = max(0,960-age_months)
    metrics = []
    estates_at_death=[]
    for path in paths:
        cuts, longest, spell, max_cut = 0,0,0,0.0
        late_begin=max(late_start,path["retirement_month"])
        for record in path["records"][late_begin:]:
            budget_month=record["lifestyle_budget_real"]/12
            short = max(0,budget_month-record["lifestyle_real"])
            cuts += int(short>1e-8);spell = spell+1 if short>1e-8 else 0;longest=max(longest,spell)
            max_cut = max(max_cut,short/budget_month if budget_month else 0)
        records = path["records"]
        estate = sum(w*r["estate_end_real"] for w,r in zip(weights["death_end"],records))
        estates_at_death.extend((r["estate_end_real"],w/len(paths)) for w,r in zip(weights["death_end"],records) if w>0)
        first_short=next((m for m in range(late_begin,len(records)) if records[m]["lifestyle_real"]+1e-8<records[m]["lifestyle_budget_real"]/12),None)
        alive_late=weights["alive_start"][late_start] if late_start<len(records) else 0
        metrics.append({"late_budget_short_months_if_alive_to100":cuts,"late_longest_short_spell_months_if_alive_to100":longest,
                        "late_max_budget_cut_fraction_if_alive_to100":max_cut,"unconditional_expected_estate_before100":estate,
                        "expected_late_budget_short_months_from_current_age":sum(weights["alive_start"][m] for m in range(late_begin,len(records)) if records[m]["lifestyle_real"]+1e-8<records[m]["lifestyle_budget_real"]/12),
                        "ever_late_budget_short_conditional_alive_late_start":weights["alive_start"][first_short]/alive_late if first_short is not None and alive_late else 0,
                        "assets_if_alive100":records[-1]["estate_end_real"],
                        "any_unfunded_consumption":any(r["unfunded_consumption_real"]>.01 for r in records),
                        "any_cash_floor_short":any(r["cash_floor_short_real"]>.01 for r in records),
                        "any_reserve_short":any(r["reserve_short_real"]>.01 or r["reserve_funding_short_real"]>.01 for r in records),
                        "whole_retirement_budget_short_months":sum(r["lifestyle_real"]+1e-8<r["lifestyle_budget_real"]/12 for r in records[path["retirement_month"]:])})
    n = len(paths)
    initial = [sum(r["lifestyle_real"] for r in p["records"][p["retirement_month"]:p["retirement_month"]+12]) for p in paths]
    initial_months=[min(12,len(p['records'])-p['retirement_month']) for p in paths]
    initial_label="退休后首12个月日常支出中位数" if min(initial_months)==12 else f"退休初段（{min(initial_months)}至{max(initial_months)}个月，100岁截断）支出中位数"
    distribution={"estate_at_death_before100_q5_q50_q95":[weighted_quantile(estates_at_death,q) for q in (.05,.5,.95)],
                  "assets_if_alive100_q5_q50_q95":[quantile([x['assets_if_alive100'] for x in metrics],q) for q in (.05,.5,.95)],
                  "late_max_budget_cut_fraction_q5_q50_q95":[quantile([x['late_max_budget_cut_fraction_if_alive_to100'] for x in metrics],q) for q in (.05,.5,.95)],
                  "late_longest_short_spell_months_q5_q50_q95":[quantile([x['late_longest_short_spell_months_if_alive_to100'] for x in metrics],q) for q in (.05,.5,.95)],
                  "sampling_path_fraction_any_cash_floor_short":sum(x['any_cash_floor_short'] for x in metrics)/n,
                  "sampling_path_fraction_any_unfunded_consumption":sum(x['any_unfunded_consumption'] for x in metrics)/n,
                  "sampling_path_fraction_any_reserve_short":sum(x['any_reserve_short'] for x in metrics)/n,
                  "initial_spending_months_min_max":[min(initial_months),max(initial_months)],
                  "whole_retirement_budget_short_months_q5_q50_q95":[quantile([x['whole_retirement_budget_short_months'] for x in metrics],q) for q in (.05,.5,.95)],
                  "ever_late_budget_short_conditional_alive_late_start":statistics.mean(x['ever_late_budget_short_conditional_alive_late_start'] for x in metrics)}
    sample_hash=hashlib.sha256(repr(indices).encode()).hexdigest()
    return {"label":s["name"],"profiles":profiles,"path_metrics":metrics,"paths":paths,"distributions":distribution,
            "summary":[{"name":initial_label,"value":f"¥{statistics.median(initial):,.0f}"+(f"（{min(initial_months)}至{max(initial_months)}个月）" if min(initial_months)<12 else "")},
                       {"name":"80 岁后预算不足月数中位数（存活至100）","value":f"{statistics.median(x['late_budget_short_months_if_alive_to100'] for x in metrics):.0f} 月"},
                       {"name":"死亡时资产中位数（仅100岁前死亡）","value":f"¥{distribution['estate_at_death_before100_q5_q50_q95'][1]:,.0f}"},
                       {"name":"80岁后最大预算削减幅度中位数","value":f"{distribution['late_max_budget_cut_fraction_q5_q50_q95'][1]:.1%}"},
                       {"name":"最长连续不足时长中位数（存活至100）","value":f"{distribution['late_longest_short_spell_months_q5_q50_q95'][1]:.0f} 月"},
                       {"name":"被迫在门槛下退休的路径比例","value":f"{sum(p['forced_below_threshold'] for p in paths)/n:.1%}"}],
            "mortality":{"source":table.source,"survival_to100":weights["tail_alive"],"conditioned_alive_at_evaluation_age":True},
            "provenance":{"history_kind":h.kind,"history_start":h.rows[0].month,"history_end":h.rows[-1].month,
                          "sources":h.sources,"limitations":h.limitations,"sample_index_sha256":sample_hash,"sampler":"joint non-circular contiguous 60-month blocks",
                          "defensive_rate_mode":s.get("defensive_rate_mode","constant"),
                          "defensive_rates_are_product_quotes":False,"cpi_publication_lag_months":s.get("cpi_publication_lag_months",1),
                          "historical_rate_process":"joint observed absolute curve changes; zero floor; explicit pull-to-sampled-level if persistence<1",
                          "rate_persistence":s.get("rate_persistence",1),
                          "reserve_funding":s.get("reserve_funding","initial"),"reserve_basis":s.get("reserve_basis","real"),
                          "cashflow_planning_cpi":s.get("planning_cpi",.02),"budget_rows_are_extra_expenses":False,
                          "rate_zero_floor_clamps":sum(r["rate_zero_floor_clamps"] for p in paths for r in p["records"]),
                          "policy":"portable double-precision constant-expectation TPAW research port; original native baseline remains separate"},
            "notes":["模拟至恰好100岁；超过该年龄的死亡与资产风险没有外推。",
                     "支出图显示逐点分位数；支出削减月数按完整路径计算。",
                     "短历史及其重抽样路径比例不是未来几十年安全概率。前瞻收益与波动为绝对替换目标。",
                     "名义存款合约、提前支取损失与国债价格单独记账；实际消费使用所设CPI公布滞后。"]}


def compare_horizons(s: dict,history: JointHistory,table: LifeTable) -> dict:
    """Matched market histories, preferences, cashflows and accounting; vary end only."""
    modes=("fixed90","fixed95","fixed100","rolling")
    cases={}
    for mode in modes:
        variant={**s,"horizon":mode}
        cases[mode]=simulate(variant,history,table)
    signatures={case["provenance"]["sample_index_sha256"] for case in cases.values()}
    if len(signatures)!=1:
        raise ArithmeticError("Horizon comparison used different realized market draws")
    selected=cases[s["horizon"]]
    selected["horizon_comparison"]={"varied_fields":["horizon"],"matched_sample_index_sha256":signatures.pop(),
        "cases":{mode:{k:v for k,v in case.items() if k not in ("paths","path_metrics","horizon_comparison")} for mode,case in cases.items()}}
    return selected
