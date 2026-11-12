"""Edited-input control through the offline native kernel, with paired replay.

The original circular US-real-return sampler and a fixed retirement/deadline are
deliberate controls. This is not the CNY nominal-asset/conditional-exit extension.
No archived request/result is changed or used as the output of this new run.
"""
import csv
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
from .cashflows import compile_flows
from .market import finite,month_index,return_statistics
from .native import (U,F,D,Pair,Ages,Opt,Adjustments,RiskTPAW,RiskSWR,Risk,
                     ReturnStats,MonteCarlo,SamplingData,Sampling,Advanced,
                     Params,HistoricalPart,Historical,Arrays,verify_abi)
from .policy import PolicyPlan,TpawPolicy
from .simulation import rra_curve,quantile
from .storage import private_root


def verified_config(path:Path)->dict:
    config=json.loads(path.read_text(encoding='utf-8-sig'))
    for name in ('dll','source','stock_stats','bond_stats'):
        file=Path(config[name]).resolve()
        if hashlib.sha256(file.read_bytes()).hexdigest()!=config[name+'_sha256']:
            raise ValueError('Native control pinned file hash changed: '+name)
        config[name]=str(file)
    config['cuda_bin']=str(Path(config['cuda_bin']).resolve(strict=True))
    return config


def control_plan(s:dict,retirement_date:str,horizon:str)->PolicyPlan:
    if horizon not in ('fixed90','fixed95','fixed100'):
        raise ValueError('原生独立对照需选择固定90、95或100岁。')
    age=finite(s['current_age'],'age')
    if not 18<=age<100 or not math.isclose(age*12,round(age*12)):
        raise ValueError('Age must have month precision between18 and100')
    age_m=round(age*12);n=int(horizon[5:])*12-age_m+1
    retirement=month_index(retirement_date)-month_index(s['evaluation_month'])
    if retirement_date not in [x.strip() for x in s['candidates'].split(',')] or not 0<=retirement<n:
        raise ValueError('原生对照退休日需是表单候选日期，并早于固定规划终点。')
    assets=finite(s['initial_assets'],'assets',0);reserve=finite(s['reserve'],'reserve',0)
    initial_reserve=reserve if s.get('reserve_funding','initial')=='initial' else 0
    if assets<initial_reserve:raise ValueError('准备金超过总资产。')
    flows=compile_flows(s,n,retirement)
    essential=tuple(a+b for a,b in zip(flows.planned('essential'),flows.planned('reserve_transfer')))
    risk=rra_curve(age_m,n,s['risk_tolerance'],s.get('risk_delta_at90',-2))
    if s.get('policy_rra'):
        supplied=s['policy_rra'];risk=tuple(supplied[min(m,len(supplied)-1)] for m in range(n))
    vol=finite(s['stock_volatility'],'volatility',.01)/100
    return PolicyPlan(assets-initial_reserve,retirement,flows.planned('income'),essential,
        flows.planned('discretionary'),risk,(n,)*n,s['stock_return']/100,
        s['planning_defensive_return']/100,s.get('policy_variance_annual',vol*vol),
        s['time_preference'],s.get('additional_spending_tilt',0),s.get('legacy_target',0),s.get('legacy_rra',4))


def adjusted_column(values:list[float],stats_text:str,target:float,annual_log_vol:float|None)->tuple[list[float],dict]:
    """Author's empirical block-60 correction and centered log-vol scaling.

    Original table is a finite500k-run CUDA calibration, not exact population
    moments. Keep its approximation distinct from overlapping12-month moments.
    """
    entries=re.findall(r'EmpiricalStats32::new\(([^,]+),\s*([^\)]+)\)',stats_text)
    if len(entries)!=1441:raise ValueError('Native empirical block table changed')
    mean60,var60=(F(float(x)).value for x in entries[60])
    logs=[math.log1p(F(v).value) for v in values]
    mean=statistics.mean(logs);base_vol=statistics.stdev(logs)*math.sqrt(12)
    scale=annual_log_vol/base_vol if annual_log_vol is not None else 1.
    correction=(math.log1p(mean60)/12-mean)*scale**2
    shifted=math.log1p(finite(target,'native target'))/12-correction
    adjusted=[math.expm1(shifted+(x-mean)*scale) for x in logs]
    return adjusted,{'target_sampler_annual_arithmetic_mean':target,'monthly_log_vol_scale':scale,
                     'native_sampler_annual_log_variance_estimate':var60*scale**2,
                     'source_rolling_statistics':return_statistics(tuple(1+x for x in adjusted))}


def native_history(config:dict,s:dict):
    entries=re.findall(r'RawMonthlyNonLogSeriesEntry::new\((\d+),\s*(\d+),\s*([^,]+),\s*([^\)]+)\)',Path(config['source']).read_text(encoding='utf-8'))
    if len(entries)<1000:raise ValueError('Native US historical source incomplete')
    stocks,stock_stats=adjusted_column([float(row[2]) for row in entries],Path(config['stock_stats']).read_text(),s['stock_return']/100,s['stock_volatility']/100)
    bonds,bond_stats=adjusted_column([float(row[3]) for row in entries],Path(config['bond_stats']).read_text(),s['planning_defensive_return']/100,None)
    data=(Historical*len(entries))(*(Historical(HistoricalPart(a,0),HistoricalPart(b,0)) for a,b in zip(stocks,bonds)))
    return data,{'start':f'{entries[0][0]}-{int(entries[0][1]):02d}','end':f'{entries[-1][0]}-{int(entries[-1][1]):02d}',
                 'stocks':stock_stats,'bonds':bond_stats,'block_months':60,'stagger_run_starts':True}


def export_control(plan:PolicyPlan,history,runs:int,seed:int,config:dict,output:Path):
    verify_abi()
    if os.name!='nt':raise ValueError('Native control requires Windows64')
    if type(runs) is not int or not 1<=runs<=1000 or type(seed) is not int or not 0<=seed<2**64:
        raise ValueError('Native path count or seed outside bounds')
    output=private_output_path(output)
    n=len(plan.income)
    # Original ABI separates working savings and retirement income, then combines.
    future=(D*n)(*(x if m<plan.retirement_month else 0 for m,x in enumerate(plan.income)))
    income=(D*n)(*(x if m>=plan.retirement_month else 0 for m,x in enumerate(plan.income)))
    essential=(D*n)(*plan.essential);discretionary=(D*n)(*plan.discretionary)
    rra=(F*n)(*plan.rra);zero=(F*n)();percentiles=(U*3)(5,50,95)
    arrays=Arrays(future,income,essential,discretionary,rra,zero,zero,3,percentiles,len(history),history)
    mu=[math.expm1(math.log1p(x)/12) for x in (plan.stock_mu_annual,plan.bond_mu_annual)]
    params=Params(Ages(n,plan.retirement_month),Adjustments(Opt(0,0),Opt(0,0),plan.legacy),
        Risk(RiskTPAW(plan.time_preference,plan.additional_spending_tilt,plan.legacy_rra),RiskSWR(0,0)),
        Advanced(ReturnStats(Pair(*mu),plan.stock_annual_log_variance),
            Sampling(0,SamplingData(mc=MonteCarlo(seed,runs,60,1))),0))
    ends=(U*n)(*plan.end_by_month)
    with os.add_dll_directory(config['cuda_bin']),os.add_dll_directory(str(Path(config['dll']).parent)):
        library=C.CDLL(config['dll']);function=library.cuda_research_horizon
        function.argtypes=[U,D,C.POINTER(Params),C.POINTER(Arrays),C.POINTER(U),C.c_char_p];function.restype=C.c_int
        status=function(n,plan.initial_balance,C.byref(params),C.byref(arrays),ends,str(output.resolve()).encode('ascii'))
    if status!=0:raise RuntimeError('Native control did not complete')


def private_output_path(output:Path)->Path:
    if output.is_symlink() or output.exists():raise ValueError('Native output already exists or is a symbolic link')
    root=private_root(output.parent)
    canonical=output.resolve()
    if not canonical.is_relative_to(root):raise ValueError('Native output escapes verified private directory')
    try:str(canonical).encode('ascii')
    except UnicodeEncodeError:raise ValueError('Pinned Windows native export requires an ASCII private output directory') from None
    return canonical


def summarize_control(plan:PolicyPlan,s:dict,output:Path)->dict:
    runs=s['runs'];n=len(plan.income);policy=TpawPolicy(plan)
    spending=[[0.]*n for _ in range(runs)];ending=[0.]*runs
    balances=[plan.initial_balance]*runs;checks=0;max_error=0.;max_alloc=0.;passed=True;seen=0
    sample_hash=hashlib.sha256()
    with output.open(newline='') as handle:
        for row in csv.DictReader(handle):
            m,r=int(row['month']),int(row['run'])
            if (m,r)!=divmod(seen,runs):raise ValueError('Native output ordering or dimensions changed')
            native={key:float(row[key]) for key in ('balance_start','general','total','stock_fraction','balance_end')}
            if any(not math.isfinite(x) for x in native.values()):raise ValueError('Nonfinite native output')
            replay=policy.step(balances[r],m,float(row['stock_return']),float(row['bond_return']))
            for key in ('balance_start','general','total','balance_end'):
                error=abs(native[key]-replay[key]);max_error=max(max_error,error)
                passed=passed and error<=max(1.,abs(native[key])*.0002);checks+=1
            allocation_error=abs(native['stock_fraction']-replay['stock_fraction']);max_alloc=max(max_alloc,allocation_error)
            passed=passed and allocation_error<=.0001;checks+=1
            balances[r]=replay['balance_end'];spending[r][m]=native['total'];ending[r]=native['balance_end']
            sample_hash.update((row['sample_index']+',').encode('ascii'));seen+=1
    if seen!=n*runs:raise ValueError('Incomplete native output')
    profiles=[]
    for m in range(0,n,12):
        values=[sum(path[m:min(n,m+12)]) for path in spending]
        profiles.append(dict(age=s['current_age']+m/12,months_summed=min(12,n-m),**{
            key:quantile(values,q) for key,q in (('p5',.05),('p50',.5),('p95',.95))}))
    first=[sum(path[plan.retirement_month:min(n,plan.retirement_month+12)]) for path in spending]
    return {'profiles':profiles,'first_retirement_period_months':min(12,n-plan.retirement_month),
        'first_retirement_period_total_q5_q50_q95':[quantile(first,q) for q in (.05,.5,.95)],
        'terminal_core_balance_q5_q50_q95':[quantile(ending,q) for q in (.05,.5,.95)],
        'paired_replay':{'pass':passed,'checks':checks,'max_absolute_money_error':max_error,'max_allocation_error':max_alloc,
            'tolerance':'max(1 accounting unit,0.02%) per money field;0.0001 allocation; float64 independently carried wealth'},
        'sample_index_sha256':sample_hash.hexdigest(),'path_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


def run_control(s:dict,retirement:str,horizon:str,config:dict,output_dir:Path)->dict:
    plan=control_plan(s,retirement,horizon);history,moments=native_history(config,s)
    output=output_dir/'paths.csv';export_control(plan,history,s['runs'],s['seed'],config,output)
    result=summarize_control(plan,s,output)
    if not result['paired_replay']['pass']:raise ValueError('Native/portable paired replay exceeded tolerance; result withheld')
    result.update({'label':s['name']+' · 当前输入原生独立对照','retirement_month':retirement,'horizon':horizon,
        'runs':s['runs'],'planning_months':len(plan.income),'history':moments,
        'pinned_sha256':{k:config[k+'_sha256'] for k in ('dll','source','stock_stats','bond_stats')},
        'limits':[
            '当前表单金额等比例作为实际记账单位；沿用美国实际收益购买力，并非人民币实际收益预测。',
            '退休日固定为选中候选月；不执行门槛决策或通知期。固定规划终点与原版内核一致，不模拟终点以后的生活。',
            '核心资产、已知净储蓄、费用、风险曲线、规划收益/方差和遗产目标来自本次表单。名义现金流按表单规划CPI预先折算；没有路径CPI。',
            '初始准备金从核心资产剔除；退休时准备金改为核心一次性目标，不再计入核心结果。准备金后续收益/支取及现金底线不在原版内核中。',
            '防御资产采用原版美国实际债券收益，不采用人民币存款/国债合约。股票和债券同步进行原版循环60个月区块采样。',
            '原生年均收益校准采用作者block60经验修正与绝对目标，不追加CAPE扣减；修改版使用非循环的滚动12月均值校准，两者口径不同。',
            '该对照与可移植策略在同一组原生路径逐月核对。它和人民币扩展的差额包含所列多项规则变化，不能单独归因于股票或寿命。']})
    return result
