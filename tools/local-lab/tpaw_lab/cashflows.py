"""Dated, explicitly denominated cashflows and lifestyle-budget benchmarks.

Budget rows replace the adequacy benchmark; they are not additional expenses.
Net-savings rows already net working spending/taxes and stop at retirement.
Nominal goals use an explicit CPI forecast in planning and known CPI at payment.
"""
from dataclasses import dataclass
import math
from .market import finite,month_index

KINDS=("net_savings","retirement_income","essential","discretionary","budget","reserve_draw")


@dataclass
class FlowSchedule:
    income_real:list[float]
    income_nominal:list[float]
    essential_real:list[float]
    essential_nominal:list[float]
    discretionary_real:list[float]
    discretionary_nominal:list[float]
    lifestyle_essential_real:list[float]
    lifestyle_essential_nominal:list[float]
    lifestyle_discretionary_real:list[float]
    lifestyle_discretionary_nominal:list[float]
    budget_real:list[float]
    budget_nominal:list[float]
    reserve_draw_real:list[float]
    reserve_draw_nominal:list[float]
    reserve_transfer_real:list[float]
    reserve_transfer_nominal:list[float]
    planning_cpi:float

    def planned(self,name:str)->tuple[float,...]:
        real,nominal=getattr(self,name+"_real"),getattr(self,name+"_nominal")
        return tuple(a+b/(1+self.planning_cpi)**(m/12) for m,(a,b) in enumerate(zip(real,nominal)))

    def nominal(self,name:str,m:int,known_cpi:float)->float:
        return getattr(self,name+"_real")[m]*known_cpi+getattr(self,name+"_nominal")[m]


def compile_flows(s:dict,months:int,retirement:int)->FlowSchedule:
    fields=[name for name in FlowSchedule.__dataclass_fields__ if name!="planning_cpi"]
    arrays={name:[0.]*months for name in fields}
    inflation=finite(s.get("planning_cpi",.02),"planning CPI")
    if not -.05<=inflation<=.5:raise ValueError("规划通胀需在-5%至50%之间。")
    flows=FlowSchedule(**arrays,planning_cpi=inflation)
    evaluation=month_index(s.get("evaluation_month","2026-11"))
    coverage=s.get("savings_coverage_end")
    savings_mode=s.get("savings_mode","constant")
    if coverage and savings_mode=="dated" and evaluation+retirement-1>month_index(coverage):
        raise ValueError("候选退休日超出已知净储蓄覆盖月份；请补齐现金流或明确修改覆盖范围。")
    rows=s.get("cashflow_rows",[])
    if not isinstance(rows,list) or len(rows)>2000:raise ValueError("现金流行数超出范围。")
    if savings_mode not in ("constant","dated"):raise ValueError("未知储蓄模式。")
    if savings_mode=="constant":
        for m in range(retirement):flows.income_real[m]=s.get("monthly_savings",0)
    for m in range(months):flows.budget_real[m]=s["annual_budget"]
    budget_assigned=set();savings_assigned=set()
    for row in rows:
        kind=row.get("kind");basis=row.get("basis","real");reference=row.get("reference","calendar")
        if kind not in KINDS or basis not in ("real","nominal") or reference not in ("calendar","retirement"):
            raise ValueError("现金流类别、价格口径或日期基准无效。")
        if kind=="net_savings" and savings_mode=="constant":continue
        amount=finite(row.get("amount"),"cashflow amount",0)
        if reference=="calendar":start=month_index(row.get("start",""))-evaluation
        else:
            offset=row.get("start",0)
            if type(offset) is not int or not -1440<=offset<=1440:raise ValueError("相对退休月份无效。")
            start=retirement+offset
        duration=row.get("duration_months",1);every=row.get("every_months",1)
        if type(duration) is not int or not 1<=duration<=1440 or type(every) is not int or not 1<=every<=120:
            raise ValueError("现金流持续月数或间隔无效。")
        target={"net_savings":"income","retirement_income":"income","essential":"essential",
                "discretionary":"discretionary","budget":"budget","reserve_draw":"reserve_draw"}[kind]
        for m in range(max(0,start),min(months,start+duration)):
            if (m-start)%every:continue
            if kind=="net_savings" and m>=retirement:continue
            if kind=="net_savings":savings_assigned.add(m)
            if kind=="retirement_income" and m<retirement:continue
            if kind=="budget":
                if m in budget_assigned:raise ValueError("年度预算阶段重叠；每月只能有一个替换预算。")
                budget_assigned.add(m);flows.budget_real[m]=flows.budget_nominal[m]=0.
            getattr(flows,target+"_"+basis)[m]+=amount
            if kind in ("essential","discretionary") and row.get("include_in_lifestyle",True):
                getattr(flows,"lifestyle_"+kind+"_"+basis)[m]+=amount
    if savings_mode=="dated" and s.get("require_savings_coverage",False) and savings_assigned!=set(range(retirement)):
        raise ValueError("日期净储蓄缺少工作月份；已知零储蓄月份也需明确列出。")
    funding=s.get("reserve_funding","initial")
    if funding not in ("initial","retirement"):raise ValueError("未知准备金划分时点。")
    reserve=finite(s["reserve"],"reserve",0)
    basis=s.get("reserve_basis","real")
    if basis not in ("real","nominal"):raise ValueError("准备金价格口径无效。")
    if funding=="retirement":getattr(flows,"reserve_transfer_"+basis)[retirement]=reserve
    # Backward-compatible saved reserve schedules; do not also enter these rows.
    for draw in s.get("reserve_draws",[]):
        offset=draw.get("months_after_retirement")
        if type(offset) is not int or offset<0:raise ValueError("准备金支取月份无效。")
        basis=draw.get("basis","real")
        if basis not in ("real","nominal"):raise ValueError("准备金支取口径无效。")
        amount=finite(draw.get("real_amount"),"reserve draw",0)
        if retirement+offset<months:getattr(flows,"reserve_draw_"+basis)[retirement+offset]+=amount
    return flows
