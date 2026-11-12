"""Audit full portable paths against untouched native realized return paths.

The portable balance is carried independently from month0, never replaced with
native marginal balances. Outputs stay private; this does not test CNY contracts.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from audit_native import load_verified,plan_from_export
from tpaw_lab.policy import TpawPolicy
from tpaw_lab.storage import Store


def audit_paths(path:Path,plan,runs:int):
    policy=TpawPolicy(plan);n=len(plan.income)
    balances=[plan.initial_balance]*runs
    fields=('balance_start','general','total','stock_fraction','balance_end')
    errors={key:{'max_absolute':0.,'max_relative_to_at_least1':0.,'failures':0} for key in fields}
    count=0;indices=hashlib.sha256();returns=hashlib.sha256()
    with path.open(newline='',encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            m,r=divmod(count,runs)
            if (int(row['month']),int(row['run']))!=(m,r):raise ValueError('Native paths reordered or missing')
            values={key:float(row[key]) for key in fields}
            stock,bond=float(row['stock_return']),float(row['bond_return'])
            if m>=n or not all(math.isfinite(v) for v in (*values.values(),stock,bond)):
                raise ValueError('Invalid native path value/bounds')
            predicted=policy.step(balances[r],m,stock,bond)
            balances[r]=predicted['balance_end']
            for key in fields:
                error=abs(predicted[key]-values[key])
                limit=.0001 if key=='stock_fraction' else max(1.,abs(values[key])*.0002)
                item=errors[key];item['max_absolute']=max(item['max_absolute'],error)
                item['max_relative_to_at_least1']=max(item['max_relative_to_at_least1'],error/max(1,abs(values[key])))
                item['failures']+=int(error>limit)
            indices.update((row['sample_index']+',').encode())
            returns.update((row['stock_return']+','+row['bond_return']+';').encode())
            count+=1
    if count!=runs*n: raise ValueError('Native path dimensions do not match')
    return {'rows':count,'runs':runs,'months':n,'checks':count*len(fields),'errors':errors,
            'pass':all(item['failures']==0 for item in errors.values()),
            'sample_index_sha256':indices.hexdigest(),'realized_returns_sha256':returns.hexdigest(),
            'path_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'tolerance':'Spending/balances max(1 currency unit,0.02%); allocation0.0001 absolute; full-path independently carried wealth',
            'scope':'Original US real stock/bond returns and fixed-horizon TPAW policy. New CNY nominal ledgers and non-circular sampler are intentionally separate.'}


def audit_marginals(path:Path,decoded):
    runs=decoded['result']['numRuns']
    arrays=decoded['result']['arrays']
    mappings={'balance_start':'BalanceStart','general':'WithdrawalsGeneral','total':'WithdrawalsTotal'}
    n=len(arrays['byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100'])//3
    report={key:{'checks':0,'max_absolute_currency_error':0.,'unequal_rounded_cents':0} for key in mappings}
    current={key:[] for key in mappings};count=0
    with path.open(newline='',encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            m,r=divmod(count,runs)
            if (int(row['month']),int(row['run']))!=(m,r):raise ValueError('Marginal path order')
            for key in current:current[key].append(float(row[key]))
            if r==runs-1:
                for key,label in mappings.items():
                    values=sorted(current[key]);current[key]=[]
                    for j,percentile in enumerate((5,50,95)):
                        index=math.floor(percentile/100*(runs-1)+.5)
                        expected=arrays['byPercentileByMfnSimulatedPercentileMajor'+label+'X100'][j*n+m]
                        value=values[index];item=report[key];item['checks']+=1
                        item['max_absolute_currency_error']=max(item['max_absolute_currency_error'],abs(value-expected/100))
                        item['unequal_rounded_cents']+=int(math.floor(value*100+.5)!=expected)
            count+=1
    if count!=runs*n:raise ValueError('Original marginal run count/dimensions differ')
    return {'fields':report,'all_rounded_cents_equal':all(v['unequal_rounded_cents']==0 for v in report.values()),
            'scope':'Original saved5/50/95 monthly native marginals against separate native full-path export; same1000 runs, seed and original circular sampler'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-prefix',type=Path,required=True);p.add_argument('--paths',type=Path,required=True)
    p.add_argument('--retirement-month',type=int,required=True);p.add_argument('--runs',type=int,required=True)
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--id',required=True)
    p.add_argument('--check-marginals',action='store_true')
    a=p.parse_args();prefix=str(a.case_prefix)
    case,decoded=load_verified(*(Path(prefix+'-'+name+ext) for name,ext in (('case','.json'),('decoded','.json'),('request','.pb'),('result','.pb'))))
    plan=plan_from_export(case,decoded,a.retirement_month)
    report=audit_paths(a.paths,plan,a.runs)
    if a.check_marginals:report['original_marginal_parity']=audit_marginals(a.paths,decoded)
    report.update(request_sha256=decoded['request_sha256'],result_sha256=decoded['result_sha256'])
    Store(a.data_dir).put('results',{'name':'Full native-vs-port path audit','report':report},a.id)
    print(json.dumps(report,indent=2));raise SystemExit(0 if report['pass'] else 1)
