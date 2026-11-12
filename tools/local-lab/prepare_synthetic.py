"""Freeze a clearly labeled synthetic 1871–2026 stress dataset locally."""
import argparse
import csv
from dataclasses import asdict
import hashlib
from pathlib import Path
from tpaw_lab.market import JointHistory,Observation,attribution
from tpaw_lab.storage import Store
from tpaw_lab.synthetic import long_stress


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--observed-id",default="developed-cny-proxy")
    parser.add_argument("--seed",type=int,default=20261112)
    parser.add_argument("--id",default=None)
    args=parser.parse_args()
    store=Store(args.data_dir)
    original=store.get("data",args.observed_id)
    raw=original["history"]
    observed=JointHistory(tuple(Observation(**row) for row in raw["rows"]),raw["kind"],raw["label"],tuple(raw["sources"]),tuple(raw["limitations"]))
    anchor_path=Path(__file__).resolve().parents[2]/"packages/simulator-rust/src/lib/historical_monthly_returns/data/v8/v8_raw_data.csv"
    with anchor_path.open(newline="",encoding="utf-8-sig") as handle:
        anchor=[(f"{int(row['year']):04}-{int(row['month']):02}",1+float(row['stock real return'])) for row in csv.DictReader(handle)]
    history,audit=long_stress(anchor,observed,args.seed)
    audit["anchor_sha256"]=hashlib.sha256(anchor_path.read_bytes()).hexdigest()
    audit["observed_audit"]=original["audit"]
    audit["returns_attribution"]=attribution(history)
    identifier=args.id or "synthetic-long-"+str(args.seed)
    store.put("data",{"name":history.label,"history":asdict(history),"audit":audit},identifier)
    print("SYNTHETIC stress dataset frozen:",identifier,"months",len(history.rows),"calendar",anchor[0][0],anchor[-1][0])
