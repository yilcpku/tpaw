"""Capture every dated entry on the two verified official BOC index pages."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from fetch_asset_sources import capture
from tpaw_lab.deposits import index_links, parse_posted
from tpaw_lab.storage import private_root


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index",type=Path,nargs="+",required=True)
    p.add_argument("--destination",type=Path,required=True)
    a=p.parse_args()
    if a.destination.exists(): raise ValueError("Fresh capture directory required")
    root=private_root(a.destination); links={}
    for index in a.index: links.update(index_links(index.read_text(encoding="utf-8")))
    def fetch(date,url):
        name=f"deposit-{date}.html"
        report=capture(root,name,url)
        quote=parse_posted((root/name).read_text(encoding="utf-8"),date)
        return {**report,"quote":quote}
    reports=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(fetch,date,url):date for date,url in links.items()}
        for job in as_completed(jobs):
            date=jobs[job]
            try:
                report=job.result(); reports.append(report); print(date,"validated",flush=True)
            except Exception as error:
                reports.append({"date":date,"error":type(error).__name__,"message":str(error)})
                print(date,type(error).__name__,flush=True)
    (root/"manifest.json").write_text(json.dumps(reports,indent=2,ensure_ascii=False),encoding="utf-8")
    raise SystemExit(int(any("error" in r for r in reports)))
