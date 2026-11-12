"""Validate coherent native paths and summarize an explicitly censored policy comparison."""
import argparse
import csv
import json
import math
from itertools import zip_longest
from pathlib import Path
from research import PeriodLifeTable, read_json, write_private, digest

def quantiles(values):
    values=sorted(values)
    return [values[int(math.floor(p/100*(len(values)-1)+.5))] for p in [5,50,95]]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['experiment','case','life-table','baseline-decoded','output']:
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    design=read_json(args.experiment/'design.json');case=read_json(args.case)
    table=PeriodLifeTable(read_json(args.life_table)['rows'])
    baseline=read_json(args.baseline_decoded)['result']
    n=baseline['numRuns'];months=design['evaluation_months'];old=design['original_months'];age0=design['current_age_months']
    retire=case['plan']['people']['person1']['ages']['retirementAge']['inMonths']-age0
    survival_at_retirement=table.survivors((age0+retire)/12)
    death_weights=[];alive_weights=[]
    for m in range(months):
        a=(age0+m)/12;b=(age0+m+1)/12
        alive_weights.append(table.survivors(a)/survival_at_retirement if m>=retire else 0)
        death_weights.append((table.survivors(a)-table.survivors(b))/survival_at_retirement if m>=retire else 0)
    tail=table.survivors(100)/survival_at_retirement
    if abs(sum(death_weights)+tail-1)>1e-10:raise ValueError('Mortality weights do not preserve age100 tail')
    targets={retire:'retirement',**{a*12-age0:f'age{a}' for a in [60,80,90,91,95,99] if 0<=a*12-age0<months}}
    modes=['fixed90','rolling-mean-plus-five']
    sums={mode:{'total':[0.0]*n,'general':[0.0]*n,'mortality_weighted_consumption':[0.0]*n,
        'death_before100_assets':[0.0]*n,'assets100':[0.0]*n,'initial':[0.0]*n,
        'ever_below_half_initial':[False]*n,'longest_below_half_initial':[0]*n,'spell':[0]*n,'profiles':{}} for mode in modes}
    streams=[(args.experiment/(mode+'-paths.csv')).open(newline='') for mode in modes]
    regression_max={'general':0.0,'total':0.0,'balance_start':0.0,'stock_fraction':0.0}
    fields={'general':('byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100',100),
        'total':('byPercentileByMfnSimulatedPercentileMajorWithdrawalsTotalX100',100),
        'balance_start':('byPercentileByMfnSimulatedPercentileMajorBalanceStartX100',100),
        'stock_fraction':('byPercentileByMfnSimulatedPercentileMajorAfterWithdrawalsAllocationSavingsPortfolioX10000',10000)}
    monthly={mode:{k:[] for k in fields} for mode in modes}
    count=0
    try:
        for pair in zip_longest(*(csv.DictReader(x) for x in streams)):
            if any(x is None for x in pair):raise ValueError('Different path counts')
            expected_m,expected_r=divmod(count,n)
            for row in pair:
                if int(row['month'])!=expected_m or int(row['run'])!=expected_r:raise ValueError('Missing/reordered path')
            for key in ['sample_index','stock_return','bond_return']:
                if pair[0][key]!=pair[1][key]:raise ValueError('Common path mismatch')
            m,r=expected_m,expected_r
            for mode,row in zip(modes,pair):
                v={k:float(x) for k,x in row.items()}
                if any(not math.isfinite(x) for x in v.values()) or min(v['balance_start'],v['balance_end'],v['general'],v['total']) < -.001:raise ValueError('Invalid financial path')
                for k in fields:monthly[mode][k].append(v[k])
                s=sums[mode]
                if m==retire:s['initial'][r]=v['general']
                if m>=retire:
                    s['total'][r]+=v['total'];s['general'][r]+=v['general']
                    s['mortality_weighted_consumption'][r]+=alive_weights[m]*v['total']
                    s['death_before100_assets'][r]+=death_weights[m]*v['balance_end']
                    below=v['general'] < .5*s['initial'][r]
                    s['ever_below_half_initial'][r]|=below
                    s['spell'][r]=s['spell'][r]+1 if below else 0
                    s['longest_below_half_initial'][r]=max(s['longest_below_half_initial'][r],s['spell'][r])
                if m==months-1:s['assets100'][r]=v['balance_end']
            if r==n-1:
                if m<old:
                    for k,(wire,scale) in fields.items():
                        for pi,value in enumerate(quantiles(monthly['fixed90'][k])):
                            expected=baseline['arrays'][wire][pi*old+m]/scale
                            regression_max[k]=max(regression_max[k],abs(value-expected))
                if m in targets:
                    for mode in modes:sums[mode]['profiles'][targets[m]]={k:quantiles(v) for k,v in monthly[mode].items()}
                monthly={mode:{k:[] for k in fields} for mode in modes}
            count+=1
    finally:
        for stream in streams:stream.close()
    if count!=n*months:raise ValueError('Wrong total path count')
    if any(error>(.006 if k!='stock_fraction' else .000051) for k,error in regression_max.items()):
        raise ValueError('Fixed90 financial regression differs beyond wire rounding')
    results={}
    for mode,s in sums.items():
        results[mode]={'pointwise_profiles':s['profiles'],'cumulative_total_if_alive_to100':quantiles(s['total']),
            'cumulative_general_if_alive_to100':quantiles(s['general']),
            'mortality_weighted_expected_consumption_before100_by_market_path':quantiles(s['mortality_weighted_consumption']),
            'mortality_weighted_expected_assets_at_death_before100_by_market_path':quantiles(s['death_before100_assets']),
            'assets_at100_if_alive':quantiles(s['assets100']),
            'ever_below_half_own_initial_general_spending_if_alive_to100':sum(s['ever_below_half_initial'])/n,
            'longest_months_below_half_own_initial_general_spending':quantiles(s['longest_below_half_initial'])}
    paired={key:quantiles([b-a for a,b in zip(sums['fixed90'][key],sums['rolling-mean-plus-five'][key])])
        for key in ['total','general','mortality_weighted_consumption','death_before100_assets','assets100']}
    write_private(args.output,{'status':'bounded_native_policy_comparison_not_complete_validation',
        'percentile_order':[5,50,95],'num_paths':n,'evaluation_months':months,'retirement_start_month':retire,
        'currency':'HKD in original October2026 purchasing power','common_realized_sample_indices_and_returns':True,
        'fixed90_regression_max_absolute_error':regression_max,'survival_to100_conditional_alive_at_retirement':tail,
        'mortality_weighting':'Withdrawals paid at beginning of month; deaths assigned month-end asset balance; period mortality independent of market paths. Quantiles of expected outcomes across market paths, not joint death/market quantiles.',
        'tail':'No death-age100 qx applied. Before100 components only; probability and conditional assets of survivors at100 remain separate, not counted as dead or discarded.',
        'cut_metric':'Half of each path own initial general spending is an illustrative relative-cut metric, not an agreed minimum budget.',
        'design':design,'results':results,'paired_rolling_minus_fixed90':paired,
        'input_hashes':{x.name:digest(x) for x in [args.case,args.life_table,args.baseline_decoded,*[args.experiment/(mode+'-paths.csv') for mode in modes]]}})
    print('Horizon common-path, full-count, mortality-tail and fixed90 financial regression checks passed; private summary saved')

if __name__=='__main__':main()
