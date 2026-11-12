"""Explicit fixed dates and monthly window decisions; no future realized data."""
import re
from .market import finite,month_index


def decade_minima(profiles):
    groups={}
    for row in profiles:
        if row.get('months_summed',12)!=12:continue
        start=((int(row['age'])-1)//10)*10+1
        groups.setdefault(start,[]).append(row)
    return [{'start_age':start,'end_age':start+9,'age':min(rows,key=lambda r:r['p5'])['age'],
             'p5':min(r['p5'] for r in rows),'covered_start':min(r['age'] for r in rows),
             'covered_end':max(r['age'] for r in rows),'points':len(rows)} for start,rows in sorted(groups.items())]


def review_schedule(s,months):
    rule=s['retirement_rule'];notice=s['notice_months']
    if type(notice) is not int or not 0<=notice<=24:raise ValueError('通知期需为0至24个月。')
    evaluation=month_index(s['evaluation_month'])
    if rule.get('kind')=='fixed':
        end=month_index(rule['date'])-evaluation
        schedule=((max(0,end-notice),end),)
    elif rule.get('kind')=='window':
        start=month_index(rule['start'])-evaluation;end=month_index(rule['end'])-evaluation
        if start<0 or start>end:raise ValueError('退休时间段需从评估月或之后开始，且开始不晚于结束。')
        finite(rule['target_annual'],'目标年消费',0)
        schedule=tuple((m,min(m+notice,end)) for m in range(start,end+1))
    else:raise ValueError('请选择固定时间或时间段＋目标消费。')
    if not 0<=end<months:raise ValueError('退休时间必须在评估月与100岁之间。')
    return schedule


def browser_plans(s):
    plans=s.get('retirement_plans')
    if plans is None:
        # Old saved records remain untouched; each old date becomes a fixed case.
        plans=[{'id':f'fixed-{i}','name':date.strip(),'kind':'fixed','date':date.strip()}
               for i,date in enumerate(s.get('candidates','').split(',')) if date.strip()]
    if not isinstance(plans,list) or not 1<=len(plans)<=8:raise ValueError('请设置1至8个退休方案。')
    ids=set()
    for plan in plans:
        if not isinstance(plan,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',str(plan.get('id',''))) or plan['id'] in ids:
            raise ValueError('退休方案标识无效或重复。')
        ids.add(plan['id'])
        if not isinstance(plan.get('name'),str) or not plan['name'].strip():raise ValueError('请填写方案名称。')
    return plans


def simplified_scenario(s,plan):
    amount=finite(s.get('retirement_withdrawal',2500000),'退休一次性支取',0)
    rows=[dict(row) for row in s.get('cashflow_rows',[]) if row.get('kind') in ('net_savings','retirement_income')]
    rows.append({'label':'退休一次性支取','kind':'essential','reference':'retirement','start':0,
                 'duration_months':1,'amount':amount,'basis':'real','include_in_lifestyle':False})
    return {**s,'retirement_rule':plan,'reserve':0,'reserve_funding':'initial','reserve_draws':[],
            'reserve_cash_rate':0,'cashflow_rows':rows,'real_cashflows_only':True,'cpi_publication_lag_months':0,
            'threshold_annual':plan.get('target_annual',0) if plan['kind']=='window' else 0}


def compare_retirement(s,history,table,progress=None):
    from .simulation import compare_horizons
    plans=browser_plans(s);reports={}
    for i,plan in enumerate(plans):
        variant=simplified_scenario(s,plan)
        report=(lambda fraction,i=i:progress((i+fraction)/len(plans))) if progress else None
        result=compare_horizons(variant,history,table,modes=('rolling','fixed90'),retain_paths=False,progress=report)
        result.pop('paths',None);result.pop('path_metrics',None)
        result['retirement_plan']=plan
        reports[plan['id']]=result
    hashes={result['provenance']['sample_index_sha256'] for result in reports.values()}
    if len(hashes)!=1:raise ArithmeticError('Retirement comparisons did not share market draws')
    selected=dict(next(iter(reports.values())))
    selected['retirement_comparison']={'cases':reports,'matched_sample_index_sha256':hashes.pop(),
        'cashflow_basis':'evaluation-month real CNY; nominal legacy savings converted with planning CPI',
        'withdrawal_real_cny':s.get('retirement_withdrawal',2500000),
        'notes':['各方案共享市场抽样；区间每月检查，达标后经过通知期，最迟在区间末月退休。',
                 '退休当月起净储蓄为零；250万元默认按评估月购买力支取，不计入日常消费曲线。',
                 '退休后曲线只统计该完整年度开始前已退休的路径；人数随年龄列出，未退休路径不按零计入。']}
    return selected
