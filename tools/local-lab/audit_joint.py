"""Generic reproducible joint-source, regime and rate-process sensitivity audit."""
import argparse
import csv
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import statistics
from tpaw_lab.comparison import compare_channels,outcome_vector
from tpaw_lab.longevity import LifeTable
from tpaw_lab.market import JointHistory,Observation,return_statistics
from tpaw_lab.simulation import simulate,compare_horizons
from tpaw_lab.storage import Store
from tpaw_lab.synthetic import components,fit,long_stress


def load(store,key):
    raw=store.get("data",key)["history"]
    return JointHistory(tuple(Observation(**r) for r in raw["rows"]),raw["kind"],raw["label"],tuple(raw["sources"]),tuple(raw["limitations"]))


def diagnostics(h):
    y=[components(row) for row in h.rows]
    width=len(y[0]); columns=[[r[i] for r in y] for i in range(width)]
    return {"start":h.rows[0].month,"end":h.rows[-1].month,"months":len(h.rows),
            "component_means":[statistics.mean(c) for c in columns],"component_std":[statistics.stdev(c) for c in columns],
            "component_correlation":[[statistics.correlation(a,b) if statistics.pstdev(a)*statistics.pstdev(b)>0 else None for b in columns] for a in columns],
            "global_cny_real":return_statistics([r.equity_gross("global","cny") for r in h.rows])}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--data-dir",type=Path,required=True);p.add_argument("--id",required=True)
    a=p.parse_args();store=Store(a.data_dir)
    observed=load(store,"global-cny-joint-official-v1");synthetic=load(store,"synthetic-joint-20261112-v1")
    life=store.get("data","hk-male-period-2025");table=LifeTable(life["rows"],life["source"])
    s={"name":"Generic joint source verification; not personal finances","initial_assets":1000000,"reserve":100000,
       "current_age":40,"evaluation_month":"2026-11","candidates":"2028-04,2029-04,2030-04","notice_months":3,
       "annual_budget":30000,"threshold_annual":30000,"horizon":"rolling","margin":5,
       "stock_return":4,"stock_volatility":18,"planning_defensive_return":0,"time_preference":0,
       "risk_tolerance":12,"cash_multiple":1.5,"term_years":5,"defensive":"deposit","runs":5,"seed":1234,
       "use_forward_targets":False,"initial_deposit_rate":.02,"initial_government_yield":.02,"demand_rate":.001,
       "defensive_rate_mode":"history","rate_persistence":1,"reserve_draws":[{"months_after_retirement":0,"real_amount":10000}]}
    audit={"name":"Generic joint model/source audit","scenario":s,"observed_moments":diagnostics(observed),
           "synthetic_moments":diagnostics(synthetic),"rate_sensitivities":[],"regime_sensitivities":[],"seed_sensitivities":[]}
    for key,h in (("observed",observed),("synthetic",synthetic)):
        for kind in ("deposit","government_bond"):
            for phi in (1,.97,.9):
                result=simulate({**s,"defensive":kind,"rate_persistence":phi},h,table)
                yields=[r["known_government_yield_end"] for path in result["paths"] for r in path["records"]]
                audit["rate_sensitivities"].append({"data":key,"kind":kind,"persistence":phi,
                      "outcomes":outcome_vector(result),"zero_floor_clamps":result["provenance"]["rate_zero_floor_clamps"],
                      "government_yield_path_min_max":[min(yields),max(yields)]})
                print(key,kind,phi,"passed account identities",flush=True)
    audit["horizons"]=compare_horizons(s,observed,table)["horizon_comparison"]
    audit["attribution"]=compare_channels(s,observed,table)
    path=Path(__file__).resolve().parents[2]/"packages/simulator-rust/src/lib/historical_monthly_returns/data/v8/v8_raw_data.csv"
    with path.open(newline="",encoding="utf-8-sig") as handle:
        anchor=[(f"{int(r['year']):04}-{int(r['month']):02}",1+float(r['stock real return'])) for r in csv.DictReader(handle)]
    audit["anchor_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    for seed in (20261112,20261113,20261114):
        h,construction=long_stress(anchor,observed,seed)
        result=simulate(s,h,table)
        audit["seed_sensitivities"].append({"seed":seed,"moments":diagnostics(h),"construction_zero_clamps":construction["yield_nonnegative_clamps"],"outcomes":outcome_vector(result)})
        print("construction seed",seed,"passed",flush=True)
    for name,subset in (("2006-2015",tuple(r for r in observed.rows if r.month<'2016-01')),("2016-2025",tuple(r for r in observed.rows if r.month>='2016-01'))):
        segment=replace(observed,rows=subset)
        h,construction=long_stress(anchor,segment,20261112)
        result=simulate(s,h,table)
        audit["regime_sensitivities"].append({"regime":name,"fitted_betas":fit(segment)["betas"],"moments":diagnostics(h),"outcomes":outcome_vector(result)})
        print("calibration regime",name,"passed",flush=True)
    audit["limits"]=["Small generic mechanics/sensitivity sample, not user finances or a safety-probability estimate.",
       "OLS preserves exact fitted observations with residuals but not future structural relationships. Constructed long-anchor moments can differ materially from the observed sample.",
       "Nonnegative floors and rate persistence affect joint outcomes; recorded clamps and ranges must be reviewed, not hidden."]
    store.put("results",audit,a.id)
    print("Saved immutable private audit",a.id,flush=True)
