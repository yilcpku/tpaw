"""Export original native paths from verified private processed artifacts."""
import argparse
import json
from pathlib import Path
from audit_native import load_verified
from tpaw_lab.native import export_paths
from tpaw_lab.storage import Store


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-prefix',type=Path,required=True);p.add_argument('--retirement-month',type=int,required=True)
    p.add_argument('--dll',type=Path,required=True);p.add_argument('--dll-sha256',required=True);p.add_argument('--cuda-bin',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',type=int)
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--id',required=True)
    a=p.parse_args();prefix=str(a.case_prefix)
    case,decoded=load_verified(*(Path(prefix+'-'+name+ext) for name,ext in (('case','.json'),('decoded','.json'),('request','.pb'),('result','.pb'))))
    source=Path(__file__).resolve().parents[2]/'packages/simulator-rust/src/lib/historical_monthly_returns/data/v8/v8_raw_monthly_non_log_series.rs'
    report=export_paths(case,decoded,a.retirement_month,a.dll,a.dll_sha256,a.cuda_bin,source,a.output,a.runs)
    report.update(request_sha256=decoded['request_sha256'],result_sha256=decoded['result_sha256'])
    Store(a.data_dir).put('results',{'name':'Pinned native original path export','report':report},a.id)
    print(json.dumps(report,indent=2))
