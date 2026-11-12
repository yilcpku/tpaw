"""Explicit synthetic long-history stress, never historical RMB observations.

Regress observed joint components on US real equity monthly log returns. Apply
the fitted component differences to the pinned long US real-return anchor, with
joint 60-month residual blocks. This is one stress construction, not a forecast
or a claim that the modern relationships held before the observed overlap.
"""
import math
import random
import statistics
from .market import JointHistory, Observation, month_index


def components(row: Observation) -> tuple[float, ...]:
    base=(math.log(row.global_equity_usd_gross/row.us_equity_usd_gross),
          math.log(row.cny_per_usd_gross),math.log(row.china_cpi_gross),math.log(row.us_cpi_gross))
    if row.government_curve is not None and row.deposit_curve is not None and row.demand_rate is not None:
        government=tuple(row.government_curve[t]-row.government_curve_before[t] for t in sorted(row.government_curve,key=int))
        deposit=tuple(row.deposit_curve[t]-row.deposit_curve_before[t] for t in sorted(row.deposit_curve,key=int))
        return base+government+deposit+(row.demand_rate-row.demand_rate_before,)
    return base+(math.log1p(row.deposit_rate_annual),math.log1p(row.government_yield_annual))


def fit(observed: JointHistory) -> dict:
    if observed.kind!="observed" or len(observed.rows)<60:
        raise ValueError("Use at least 60 actual joint observations, before forward adjustment")
    x=[math.log(row.equity_gross("us","usd")) for row in observed.rows]
    center=statistics.mean(x)
    variance=sum((value-center)**2 for value in x)
    if variance==0:
        raise ValueError("Cannot fit stock-dependent components without stock variation")
    y=[components(row) for row in observed.rows]
    count=len(y[0])
    if any(len(row)!=count for row in y): raise ValueError("Mixed observed curve availability")
    means=[statistics.mean(row[j] for row in y) for j in range(count)]
    beta=[sum((stock-center)*(row[j]-means[j]) for stock,row in zip(x,y))/variance for j in range(count)]
    residuals=[tuple(row[j]-means[j]-beta[j]*(stock-center) for j in range(count)) for stock,row in zip(x,y)]
    return {"x_mean":center,"component_means":means,"betas":beta,"joint_residuals":residuals}


def long_stress(anchor: list[tuple[str,float]], observed: JointHistory, seed: int) -> tuple[JointHistory, dict]:
    if type(seed) is not int or not anchor or any(gross<=0 or not math.isfinite(gross) for _,gross in anchor):
        raise ValueError("Invalid long anchor or seed")
    dates=[month_index(month) for month,_ in anchor]
    if any(b!=a+1 for a,b in zip(dates,dates[1:])):
        raise ValueError("Long US anchor is not consecutive")
    model=fit(observed)
    rng=random.Random(seed)
    residual_indices=[]
    while len(residual_indices)<len(anchor):
        start=rng.randrange(len(observed.rows)-60+1)
        residual_indices.extend(range(start,start+min(60,len(anchor)-len(residual_indices))))
    rows=[];yield_clamps=0
    full_curves=observed.rows[0].government_curve is not None
    government_terms=sorted(observed.rows[0].government_curve,key=int) if full_curves else []
    deposit_terms=sorted(observed.rows[0].deposit_curve,key=int) if full_curves else []
    count=len(model["betas"])
    for (month,us_real),index in zip(anchor,residual_indices):
        x=math.log(us_real)
        c=[model["component_means"][j]+model["betas"][j]*(x-model["x_mean"])+model["joint_residuals"][index][j] for j in range(count)]
        curve_fields={}
        if full_curves:
            source=observed.rows[index];offset=4
            for name,terms in (("government_curve",government_terms),("deposit_curve",deposit_terms)):
                before=getattr(source,name+"_before")
                after={t:max(0,before[t]+c[offset+j]) for j,t in enumerate(terms)}
                yield_clamps+=sum(before[t]+c[offset+j]<0 for j,t in enumerate(terms))
                curve_fields[name+"_before"]=before;curve_fields[name]=after;offset+=len(terms)
            demand=source.demand_rate_before+c[offset];yield_clamps+=int(demand<0)
            curve_fields.update(demand_rate_before=source.demand_rate_before,demand_rate=max(0,demand))
            deposit=curve_fields["deposit_curve"]["60"];government=curve_fields["government_curve"]["60"]
        else:
            deposit,government=math.expm1(c[4]),math.expm1(c[5])
            yield_clamps+=int(deposit<0)+int(government<0)
        us_nominal=us_real*math.exp(c[3])
        rows.append(Observation(month,us_nominal*math.exp(c[0]),us_nominal,math.exp(c[1]),math.exp(c[2]),math.exp(c[3]),
                                max(0,deposit),max(0,government),"SYNTHETIC: pinned US real anchor + modern conditional joint component/residual stress",**curve_fields))
    limitations=observed.limitations+(
        "SYNTHETIC DATA: all global, FX, CPI and CNY defensive components on the long calendar are constructed, not historical RMB observations.",
        "Modern monthly linear relationships are extrapolated to the entire US anchor. Joint residuals preserve 60-month macro/component ordering, not historical pre-overlap regimes or exact future correlations.",
        "US long anchor is pinned TPAW US real stocks; calibration US comparator is French broad US stocks. This methodology mismatch is an additional stress limitation, not removed by regression.",
        "No claim of freely convertible/investable historical CNY before financial reforms. Nominal defensive-yield nonnegativity clamps, if any, alter fitted relationships.")
    if full_curves:
        limitations+=("Rate curve before/after fields encode a conditional monthly shock around the sampled modern source level. They are not a continuous1871-2026 curve-level reconstruction. Simulation applies their differences to its own currently known curve state; constant-rate mode ignores these shocks.",)
    history=JointHistory(tuple(rows),"synthetic_stress","合成压力 · 1871–2026 美国历史锚 + 观测差异",observed.sources,limitations)
    audit={"kind":"synthetic_stress","anchor_start":anchor[0][0],"anchor_end":anchor[-1][0],
           "calibration_start":observed.rows[0].month,"calibration_end":observed.rows[-1].month,
           "construction_seed":seed,"residual_block_months":60,"yield_nonnegative_clamps":yield_clamps,
           "component_order":["global_minus_us_equity_log","fx_log","china_cpi_log","us_cpi_log"]+
                (["government_change_"+t for t in government_terms]+["deposit_change_"+t for t in deposit_terms]+["demand_rate_change"] if full_curves else ["log1p_deposit_rate","log1p_government_yield"]),
           "betas":model["betas"],"component_means":model["component_means"],
           "residual_source_indices":residual_indices,"no_historical_rmb_claim":True,
           "rate_curve_fields_encode_monthly_shocks":full_curves}
    return history,audit
