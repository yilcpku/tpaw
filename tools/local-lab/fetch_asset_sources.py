"""Small official-source acquisition sample before collecting longer histories."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request
from tpaw_lab.storage import private_root

SAMPLES={
    "chinabond-2024.html":"https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery?startDate=2024-01-01&endDate=2024-12-31&gjqx=0&qxId=ycqx&locale=cn_ZH",
    "vanguard-retail-overview.html":"https://www.vanguardinvestor.co.uk/investments/vanguard-ftse-all-world-ucits-etf-usd-accumulating/overview",
}


def capture(root: Path,name: str,url: str):
    request=urllib.request.Request(url,headers={"User-Agent":"TPAW-local-research/0.1"})
    with urllib.request.urlopen(request,timeout=30) as response:
        body=response.read(20*1024*1024+1)
        if not body or len(body)>20*1024*1024:
            raise ValueError("Unexpected source size")
        (root/name).write_bytes(body)
        return {"filename":name,"url":url,"final_url":response.url,"content_type":response.headers.get("Content-Type"),
                "bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),"retrieved_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    if args.destination.exists():
        raise ValueError("Use a fresh snapshot directory")
    root=private_root(args.destination)
    reports=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        jobs={executor.submit(capture,root,name,url):name for name,url in SAMPLES.items()}
        for job,name in jobs.items():
            try:
                report=job.result();reports.append(report);print(name,report["bytes"])
            except Exception as error:
                reports.append({"filename":name,"error":type(error).__name__,"message":str(error)})
                print(name,type(error).__name__)
    (root/"manifest.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")
