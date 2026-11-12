"""Import a hash-verified archived author plan without changing its sources.

The private mapping chooses FX, budgets and reserve treatment explicitly. Native
outputs stay an immutable dated reference; archived wealth is never called current.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from audit_native import load_verified
from tpaw_lab.baseline import COMPARISON_FIELDS,input_signature
from tpaw_lab.market import finite,month_index
from tpaw_lab.storage import Store


def month_at(evaluation,index):
    i=month_index(evaluation)+index
    return f'{i//12:04}-{i%12+1:02}'


def goal_row(goal,kind,fx,include=True):
    amount=goal['amountAndTiming']
    if amount['type']!='recurring' or amount.get('delta') is not None:
        raise ValueError('Importer supports fixed recurring/one-period author goals only')
    period=amount['monthRange']
    if period['type']!='startAndDuration':raise ValueError('Unsupported author date range')
    start=period['start']
    if start['type']=='calendarMonth':
        date=start['calendarMonth'];reference='calendar';value=f"{date['year']:04}-{date['month']:02}"
    elif start['type']=='namedAge' and start['age']=='retirement' and start['person']=='person1':
        reference='retirement';value=0
    else:raise ValueError('Unsupported author goal date reference')
    return {'label':goal.get('label',goal['id']),'source_id':goal['id'],'kind':kind,'reference':reference,'start':value,
            'duration_months':period['duration']['inMonths'],'every_months':amount['everyXMonths'],
            'amount':amount['baseAmount']*fx,'basis':'nominal' if goal['nominal'] else 'real','include_in_lifestyle':include}


def build(config:dict,case:dict,decoded:dict):
    plan=case['plan'];result=decoded['result'];p=result['planParamsProcessed']
    if plan['v']!=30 or plan['people'].get('withPartner') or plan['risk']['tpaw']['additionalAnnualSpendingTilt'] is None:
        raise ValueError('Unsupported archived author-plan shape')
    fx=finite(config['cny_per_source_unit'],'fixed import FX',1e-12)
    evaluation=config['evaluation_month'];retirement=case['retirement_month'];exit_index=month_index(retirement)-month_index(evaluation)
    native_n=len(p['amountTimed']['wealthFutureSavings']['totalX100'])
    birth=plan['people']['person1']['ages']['currentAgeInfo']['monthOfBirth']
    age=(month_index(evaluation)-month_index(f"{birth['year']:04}-{birth['month']:02}"))/12
    reserve_id=config['reserve_goal_id']
    goals=plan['adjustmentsToSpending']['extraSpending']
    if reserve_id not in goals['essential']:raise ValueError('Selected reserve goal absent from original plan')
    oneoff=goal_row(goals['essential'][reserve_id],'essential',fx,False)
    if oneoff['reference']!='retirement' or oneoff['duration_months']!=1:raise ValueError('Reserve mapping requires one retirement-period goal')
    rows=[]
    # Keep every working month, including explicit zero, preserving the already
    # netted salary/bonus/notice series. No second salary/bonus entry is invented.
    for m,value in enumerate(p['amountTimed']['wealthFutureSavings']['totalX100'][:exit_index]):
        rows.append({'label':'归档设定净储蓄 '+month_at(evaluation,m),'kind':'net_savings','reference':'calendar',
                     'start':month_at(evaluation,m),'duration_months':1,'every_months':1,'amount':value/100*fx,'basis':'real'})
    for m,value in enumerate(p['amountTimed']['wealthIncomeDuringRetirement']['totalX100']):
        if value:rows.append({'label':'归档退休收入','kind':'retirement_income','start':month_at(evaluation,m),'amount':value/100*fx,'basis':'real'})
    for kind,items in goals.items():
        if kind not in ('essential','discretionary'):raise ValueError('Unsupported author goal category')
        for ident,goal in items.items():rows.append(goal_row(goal,kind,fx,ident!=reserve_id))
    returns=p['returnsStatsForPlanning'];risk=plan['risk']['tpaw']
    original={
        'name':config['name']+' · 旧合约隔离对照（历史输入）','initial_assets':result['arrays']['byPercentileByMfnSimulatedPercentileMajorBalanceStartX100'][0]/100*fx,
        'current_age':age,'evaluation_month':evaluation,'candidates':retirement,'notice_months':3,
        'annual_budget':config['annual_budget_cny'],'threshold_annual':config['annual_budget_cny'],
        'reserve':0,'reserve_funding':'initial','reserve_basis':'real','reserve_cash_rate':config.get('reserve_cash_rate',.001),
        'horizon':'fixed90','margin':5,'defensive':'government_bond','term_years':5,'cash_multiple':0,'floor_trigger_fraction':1,
        'stock_return':100*returns['stocks']['empiricalAnnualNonLogExpectedReturn'],
        'stock_volatility':100*returns['stocks']['empiricalAnnualLogVariance']**.5,
        'policy_variance_annual':returns['stocks']['empiricalAnnualLogVariance'],
        'planning_defensive_return':100*returns['bonds']['empiricalAnnualNonLogExpectedReturn'],
        'risk_tolerance':risk['riskTolerance']['at20'],'risk_delta_at90':risk['riskTolerance']['deltaAtMaxAge'],
        'policy_rra':p['risk']['tpaw']['rraUnclampedIncludingPosInfinityByMfn'],
        'time_preference':risk['timePreference'],'additional_spending_tilt':risk['additionalAnnualSpendingTilt'],
        'legacy_target':p['adjustmentsToSpending']['tpawAndSpaw']['legacy']['target']*fx,
        'legacy_rra':p['risk']['tpaw']['legacyRraIncludingPosInfinity'],
        'monthly_savings':0,'savings_mode':'dated','require_savings_coverage':True,'savings_coverage_end':month_at(evaluation,exit_index-1),
        'cashflow_rows':rows+copy.deepcopy(config.get('budget_phases',[])),
        'planning_cpi':p['annualInflation'],'initial_deposit_rate':config.get('initial_deposit_rate',.02),
        'initial_government_yield':config.get('initial_government_yield',.02),'demand_rate':config.get('demand_rate',.001),
        'defensive_rate_mode':'history','rate_persistence':config.get('rate_persistence',.97),'cpi_publication_lag_months':1,
        'use_forward_targets':True,'dataset':config.get('dataset','global-cny-joint-official-v1'),'seed':case['run']['seed'],'runs':config.get('runs',100),
        'include_attribution':False,'native_baseline_id':config['baseline_id'],'import_variant':'archive_contract',
        'native_differences':['全球股票/中国CPI/人民币汇率替代美国实际收益','人民币名义国债替代原版真实债券收益','非环绕60月联合抽样及较短历史','公布CPI滞后','路径数不同；并非原版样本逐路径配对'],
        'source_note':'历史资产输入和归档未来净储蓄/奖金假设，按固定导入汇率换算；不是当前账户刷新或未来收入承诺。保留原版规划方差，月度采样波动目标为单独口径。',
        'source_evaluation_month':evaluation,'import_fx_cny_per_source_unit':fx}
    expanded=copy.deepcopy(original)
    expanded.update(name=config['name']+' · 准备金/现金底线扩展（历史输入）',import_variant='reserve_extension',
                    reserve=oneoff['amount'],reserve_basis=oneoff['basis'],reserve_funding='retirement',horizon='rolling',cash_multiple=1.5)
    expanded['cashflow_rows']=[row for row in expanded['cashflow_rows'] if row.get('source_id')!=reserve_id]
    for row in expanded['cashflow_rows']:
        if row.get('source_id') in config.get('permanent_goal_ids',[]):row['duration_months']=1440
        if row.get('source_id') in config.get('retirement_relative_goal_ids',[]) or row.get('kind')=='budget':
            if row.get('reference','calendar')=='calendar':
                row['start']=month_index(row['start'])-month_index(retirement);row['reference']='retirement'
    expanded['cashflow_rows']+=copy.deepcopy(config.get('reserve_draws',[]))
    expanded['native_differences']+=['每年更新寿命终点','旧版退休时支出目标改为内部准备金划分，支取另记消费','增加独立1.5倍年预算境内现金底线']
    if config.get('permanent_goal_ids'):expanded['native_differences']+=['明确的永久生活增量延续到原版90岁截断之后']
    if config.get('retirement_relative_goal_ids'):expanded['native_differences']+=['租住/购房阶段随退休日移动，保持24个月租住间隔']
    profiles=[]
    values=result['arrays']['byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100']
    for m in range(native_n):
        profiles.append({'age':age+m/12,'p5':values[m]/100*fx*12,'p50':values[native_n+m]/100*fx*12,'p95':values[2*native_n+m]/100*fx*12})
    baseline={'name':config['name']+' · 原生归档基准','currency':'CNY-scaled original real-HKD accounting; US real-return convention',
        'source_currency':case['run'].get('currency','original unit'),'fixed_import_fx':fx,'evaluation_month':evaluation,'retirement_month':retirement,
        'runs':result['numRuns'],'profiles':profiles,'aggregation':'原版每个月的一般支出分位数 ×12；不是年度总和分位数',
        'first_month_general_annual_q5_q50_q95':[values[j*native_n+exit_index]/100*fx*12 for j in range(3)],
        'planning':{'stock_return':original['stock_return'],'bond_return':original['planning_defensive_return'],
                    'stock_annual_log_variance':original['policy_variance_annual'],'risk_tolerance':original['risk_tolerance'],'time_preference':original['time_preference']},
        'request_sha256':decoded['request_sha256'],'result_sha256':decoded['result_sha256'],
        'limits':['原版结果与输入均保持归档字节；不是旧网站结果的逐位复现。','金额按固定汇率等比例展示，美国实际收益口径不等于人民币实际购买力。',
                  '原版使用1871–2026美国历史与环绕区块采样；原版图是月支出分位数年度化。修改版采用非环绕联合区块，两个图的聚合口径不同。',
                  '旧版一次性退休目标原本扣离核心资产；扩展情景将它划入独立准备金。余额差异包含这项明确的会计变化。',
                  '原版规划方差为引擎的年度对数方差；修改版月波动×√12采样目标与其独立保留，不能混称。'],
        'imported_scenario_inputs':{s['import_variant']:{key:s.get(key) for key in COMPARISON_FIELDS} for s in (original,expanded)}}
    return baseline,original,expanded


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);parser.add_argument('--data-dir',type=Path,required=True)
    args=parser.parse_args();config=json.loads(args.config.read_text(encoding='utf-8'))
    prefix=config['case_prefix']
    case,decoded=load_verified(*(Path(prefix+'-'+name+ext) for name,ext in (('case','.json'),('decoded','.json'),('request','.pb'),('result','.pb'))))
    if hashlib.sha256(Path(prefix+'-case.json').read_bytes()).hexdigest()!=config['case_sha256']:raise ValueError('Archived case hash mismatch')
    baseline,original,expanded=build(config,case,decoded)
    baseline['case_sha256']=config['case_sha256'];baseline['import_config_sha256']=hashlib.sha256(args.config.read_bytes()).hexdigest()
    store=Store(args.data_dir);store.put('baselines',baseline,config['baseline_id'])
    for suffix,scenario in (('archive',original),('extension',expanded)):
        scenario['import_signature']=input_signature(scenario)
        store.put('scenarios',scenario,config['scenario_id']+'-'+suffix)
    print('Verified archived native reference and2 explicitly labeled local scenarios imported; source files unchanged.')
