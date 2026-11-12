"""Four-horizon audit, exact monthly mortality mixtures and explicit HKD budgets."""
import argparse
import csv
import hashlib
import math
from pathlib import Path
from research import PeriodLifeTable, read_json, write_private, digest, number
from analyze_horizon import quantiles

MODES=['fixed90','fixed95','fixed100','rolling-mean-plus-five']

def mortality_weights(table,age0,retire,months):
    denom=table.survivors((age0+retire)/12)
    alive=[table.survivors((age0+m)/12)/denom if m>=retire else 0.0 for m in range(months)]
    death=[(table.survivors((age0+m)/12)-table.survivors((age0+m+1)/12))/denom if m>=retire else 0.0 for m in range(months)]
    tail=table.survivors((age0+months)/12)/denom
    if abs(sum(death)+tail-1)>1e-10:raise ValueError('Mortality mass lost')
    return alive,death,tail

def weighted_quantiles(pairs):
    pairs=sorted((v,w) for v,w in pairs if w>0)
    mass=sum(w for _,w in pairs)
    if not pairs or mass<=0:raise ValueError('No outcome mass')
    out=[];cum=0;qi=0;qs=[.05,.5,.95]
    for value,weight in pairs:
        cum+=weight
        while qi<3 and cum>=mass*qs[qi]:out.append(value);qi+=1
        if qi==3:break
    return out

def expectation_identity(c,estate,alive,death,tail):
    cumulative=[];value=0
    for x in c:value+=x;cumulative.append(value)
    survival=sum(s*x for s,x in zip(alive,c))
    mixture=sum(w*x for w,x in zip(death,cumulative))+tail*cumulative[-1]
    return survival,mixture,sum(w*b for w,b in zip(death,estate))

def stats(values):return {'mean':sum(values)/len(values),'q5_q50_q95':quantiles(values)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ['experiment','case','life-table','output']:p.add_argument('--'+x,required=True,type=Path)
    p.add_argument('--budgets-hkd',type=float,nargs='+',default=[15000,20000,25000])
    p.add_argument('--report-real-discount-rate',type=float,default=.02)
    a=p.parse_args();number(a.report_real_discount_rate,0,.1)
    if len(a.budgets_hkd)>5:raise ValueError('Bound budget sensitivities')
    for b in a.budgets_hkd:number(b,1,1000000)
    d=read_json(a.experiment/'design.json');case=read_json(a.case)
    table=PeriodLifeTable(read_json(a.life_table)['rows'])
    age0=d['current_age_months'];months=d['evaluation_months']
    retire=case['plan']['people']['person1']['ages']['retirementAge']['inMonths']-age0
    alive,death,tail=mortality_weights(table,age0,retire,months)
    start80=80*12-age0
    if not retire<start80<months:raise ValueError('This bounded audit requires retirement before80 and evaluation through100')
    alive80=alive[start80]
    targets={retire:'retirement',**{x*12-age0:f'age{x}' for x in [60,80,90,91,95,96,99]}}
    result={};signatures=[];identity_max=0.0
    for mode in MODES:
        n=None;last_count=0;signature=hashlib.sha256();profile={};month_values=[]
        # All native cases here use the same bounded 1,000-path request.
        n=case['run']['simulation_count']
        cumulative=[0.0]*n;cum_discounted=[0.0]*n;ec=[0.0]*n;ecd=[0.0]*n
        ee=[0.0]*n;eed=[0.0]*n;mixture_c=[0.0]*n;mixture_cd=[0.0]*n;tail_assets=[0.0]*n
        joint_c=[];joint_estate=[];joint_discounted_c=[];joint_discounted_estate=[]
        budget={str(int(b)):{'count':[0]*n,'longest':[0]*n,'spell':[0]*n,'first':[None]*n,
            'life_weighted_months':[0.0]*n,'shortfall':[0.0]*n} for b in a.budgets_hkd}
        with (a.experiment/(mode+'-paths.csv')).open(newline='') as f:
            for row in csv.DictReader(f):
                m=int(row['month']);r=int(row['run'])
                if (m,r)!=divmod(last_count,n):raise ValueError('Missing or reordered native path')
                if m>=months:raise ValueError('Too many months')
                signature.update(('|'.join(row[k] for k in ['month','run','sample_index','stock_return','bond_return'])+'\n').encode())
                c=float(row['total']);g=float(row['general']);estate=float(row['balance_end']);balance=float(row['balance_start'])
                if any(not math.isfinite(v) or v<-.001 for v in [c,g,estate,balance]):raise ValueError('Invalid outcome')
                if m>=retire:
                    dc=(1+a.report_real_discount_rate)**(-(m-retire)/12)
                    de=(1+a.report_real_discount_rate)**(-(m+1-retire)/12)
                    cumulative[r]+=c;cum_discounted[r]+=dc*c
                    ec[r]+=alive[m]*c;ecd[r]+=alive[m]*dc*c
                    ee[r]+=death[m]*estate;eed[r]+=death[m]*de*estate
                    mixture_c[r]+=death[m]*cumulative[r]
                    mixture_cd[r]+=death[m]*cum_discounted[r]
                    w=death[m]/n
                    if w>0:
                        joint_c.append((cumulative[r],w));joint_estate.append((estate,w))
                        joint_discounted_c.append((cum_discounted[r],w));joint_discounted_estate.append((de*estate,w))
                if m>=start80:
                    for b in a.budgets_hkd:
                        s=budget[str(int(b))];below=g<b
                        s['count'][r]+=below;s['spell'][r]=s['spell'][r]+1 if below else 0
                        s['longest'][r]=max(s['longest'][r],s['spell'][r])
                        if below and s['first'][r] is None:s['first'][r]=m
                        s['life_weighted_months'][r]+=alive[m]/alive80*below
                        s['shortfall'][r]+=max(0,b-g)
                if m in targets:month_values.append((g,balance))
                if r==n-1 and m in targets:
                    profile[targets[m]]={'general':quantiles([x[0] for x in month_values]),'balance_start':quantiles([x[1] for x in month_values])}
                    month_values=[]
                if m==months-1:tail_assets[r]=estate
                last_count+=1
        if last_count!=n*months:raise ValueError('Missing native rows')
        signatures.append(signature.hexdigest())
        errors=[abs(x-(y+tail*z)) for x,y,z in zip(ec,mixture_c,cumulative)]
        identity_max=max(identity_max,max(errors))
        if any(error>1e-8*max(1,abs(value)) for error,value in zip(errors,ec)):raise ValueError('Mortality consumption identity fails')
        if any(abs(x-y-tail*z)>1e-8*max(1,abs(x)) for x,y,z in zip(ecd,mixture_cd,cum_discounted)):
            raise ValueError('Discounted mortality consumption identity fails')
        mass=sum(w for _,w in joint_estate)
        joint_estate_mean=sum(v*w for v,w in joint_estate)/mass
        if abs(mass-(1-tail))>1e-9 or abs(joint_estate_mean-sum(ee)/n/(1-tail))>1e-8*max(1,joint_estate_mean):
            raise ValueError('Mortality estate conditioning identity fails')
        # Censored survivors contribute consumption through100; they are never
        # silently included in the death-before100 estate distribution.
        censored_c=[*joint_c,*[(x,tail/n) for x in cumulative]]
        censored_discounted_c=[*joint_discounted_c,*[(x,tail/n) for x in cum_discounted]]
        budgets={}
        for label,s in budget.items():
            budgets[label]={'ever_below_if_alive_through100':sum(x is not None for x in s['first'])/n,
                'months_below_if_alive_through100':stats(s['count']),
                'longest_spell_months_if_alive_through100':stats(s['longest']),
                'expected_months_below_conditional_alive80':sum(s['life_weighted_months'])/n,
                'joint_probability_shortfall_before100_conditional_alive80':sum(alive[x]/alive80 if x is not None else 0 for x in s['first'])/n,
                'cumulative_hkd_shortfall_if_alive_through100':stats(s['shortfall'])}
            check=budgets[label]
            if not (0<=check['joint_probability_shortfall_before100_conditional_alive80']<=check['ever_below_if_alive_through100']<=1):
                raise ValueError('Shortfall probability conditioning inconsistent')
            if not (0<=check['expected_months_below_conditional_alive80']<=check['months_below_if_alive_through100']['mean']<=months-start80):
                raise ValueError('Shortfall duration conditioning inconsistent')
            if any(l>c for l,c in zip(s['longest'],s['count'])):raise ValueError('Longest spell exceeds total duration')
        ordered=[budgets[str(int(b))] for b in sorted(a.budgets_hkd)]
        for low,high in zip(ordered,ordered[1:]):
            for key in ['expected_months_below_conditional_alive80','joint_probability_shortfall_before100_conditional_alive80']:
                if low[key]>high[key]+1e-12:raise ValueError('Budget monotonicity fails')
        result[mode]={'profiles':profile,
            'per_market_path_mortality_expectations':{'undiscounted_consumption_through_min_death_or100':stats(ec),
                'discounted_consumption_through_min_death_or100':stats(ecd),
                'undiscounted_estate_death_before100':stats(ee),'discounted_estate_death_before100':stats(eed)},
            'joint_market_and_enumerated_monthly_mortality':{
                'undiscounted_consumption_death_before100_conditional_on_death_before100':weighted_quantiles(joint_c),
                'undiscounted_consumption_censored_at100':weighted_quantiles(censored_c),
                'discounted_consumption_censored_at100':weighted_quantiles(censored_discounted_c),
                'undiscounted_estate_conditional_on_death_before100':weighted_quantiles(joint_estate),
                'undiscounted_estate_mean_conditional_on_death_before100':joint_estate_mean,
                'discounted_estate_conditional_on_death_before100':weighted_quantiles(joint_discounted_estate)},
            'assets100_conditional_alive100':stats(tail_assets),'cumulative_total_if_alive_through100':stats(cumulative),
            'late_age80_to100_illustrative_budgets':budgets,'native_rows':last_count,
            'paths_sha256':digest(a.experiment/(mode+'-paths.csv'))}
        del joint_c,joint_estate,joint_discounted_c,joint_discounted_estate,censored_c,censored_discounted_c
        print('Validated and summarized',mode,'without logging financial values')
    if len(set(signatures))!=1:raise ValueError('Realized paths differ across policies')
    write_private(a.output,{'status':'bounded_four_horizon_robustness_not_full_policy_validation','results':result,
        'common_path_signature':signatures[0],'num_paths':n,'rows_each':n*months,
        'mortality_expectation_identity_max_absolute_hkd':identity_max,
        'currency':'HKD, original October2026 purchasing power; no FX conversion or RMB inflation model',
        'utility_rho_constant':case['plan']['risk']['tpaw']['timePreference'],
        'report_real_discount_rate':a.report_real_discount_rate,
        'discount_semantics':'Real annual financial discount from retirement; consumption at month start, estate at month end. Illustrative reporting sensitivity, not utility rho, market forecast or RMB risk-free return.',
        'undiscounted_semantics':'Real cash sums with zero financial discount, including setup in total consumption; ongoing budget tests exclude setup.',
        'mortality_conditioning':'Alive at retirement, 2025 HK male frozen period mortality, independent of returns. Linear within-year lx interpolation. Death-before100 estate quantiles additionally condition on death before100; age100 survivors remain separate.',
        'survival100_conditional_alive_retirement':tail,'survival100_conditional_alive80':tail/alive80,
        'distribution_semantics':'Per-path expectation statistics integrate mortality first then summarize 1,000 market paths. Joint statistics enumerate monthly deaths with official weights across all market paths; no random death draw or post100 mortality invented. Censored consumption includes survivor100 consumption but does not label them dead.',
        'budget_semantics':'Illustrative constant real HKD thresholds, not user-approved preferred/minimum budgets. Durations refer to ages80..<100; survival100 and mortality-weighted conditional-alive80 versions are distinct.',
        'annual_convention':d['policy'],'risk_curve':'Same original age90 risk-age anchor retained, terminal RRA held thereafter',
        'baseline_originals_preserved':True,'market_scope':'Pinned US Jan1871-Mar2026 historical returns plus Oct2026 calibration; not global/RMB calibrated',
        'input_hashes':{'case':digest(a.case),'life_table':digest(a.life_table)}})
    print('Four-policy common paths and mortality identities passed; private robustness summary saved')

if __name__=='__main__':main()
