"""Collect official government curves in the site's supported <=one-year windows."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
from fetch_asset_sources import capture
from tpaw_lab.storage import private_root
from tpaw_lab.yields import parse_chinabond


def fetch(root:Path,year:int):
    start=f"{year}-01-01"
    end=f"{year}-12-31" if year<2026 else "2026-10-31"
    url=f"https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery?startDate={start}&endDate={end}&gjqx=0&qxId=ycqx&locale=cn_ZH"
    name=f"chinabond-{year}.html"
    report=capture(root,name,url)
    daily=parse_chinabond((root/name).read_text(encoding="utf-8"),start,end)
    report.update(daily_curves=len(daily),first_date=min(daily),last_date=max(daily))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination",type=Path,required=True)
    parser.add_argument("--years",type=int,nargs="+",required=True)
    args=parser.parse_args()
    if args.destination.exists() or any(not 2006<=year<=2026 for year in args.years):
        raise ValueError("Fresh destination and supported years2006..2026 required")
    root=private_root(args.destination)
    reports=[]
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs={executor.submit(fetch,root,year):year for year in sorted(set(args.years))}
        for job in as_completed(jobs):
            year=jobs[job]
            try:
                report=job.result();reports.append(report)
                print(year,report["daily_curves"],report["first_date"],report["last_date"],flush=True)
            except Exception as error:
                reports.append({"year":year,"error":type(error).__name__,"message":str(error)})
                print(year,type(error).__name__,flush=True)
    (root/"manifest.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")
    raise SystemExit(1 if any("error" in report for report in reports) else 0)
