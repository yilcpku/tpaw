"""Experimental public-source monthly total-return/RMB pipeline, not a forecast."""
import argparse
import calendar
import csv
import datetime as dt
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from research import read_json,write_private,digest,number,private_destination

def index(month):
    y,m=map(int,month.split('-'));return y*12+m-1
def month(value):return f'{value//12:04}-{value%12+1:02}'
def consecutive(keys):
    values=sorted(map(index,keys))
    if any(b!=a+1 for a,b in zip(values,values[1:])):raise ValueError('Missing/duplicate monthly observation')

def fred(path,key):
    out={}
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            date=dt.date.fromisoformat(row['observation_date'])
            if date.isoformat() in out:raise ValueError('Duplicate source date')
            if row[key] not in ('','.'):out[date.isoformat()]=number(float(row[key]),0.000001)
    return out

def fx_month_ends(daily,last_complete_month):
    out={}
    for date,value in sorted(daily.items()):
        if date[:7]<=last_complete_month:out[date[:7]]={'date':date,'cny_per_usd':value}
    for key,row in out.items():
        date=dt.date.fromisoformat(row['date']);end=dt.date(date.year,date.month,calendar.monthrange(date.year,date.month)[1])
        if (end-date).days>7:raise ValueError('FX month-end more than seven days stale')
    consecutive(out)
    return out

class Rows(HTMLParser):
    def __init__(self):super().__init__();self.stack=[];self.cells=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.stack.append([])
        if tag in ('td','th'):self.cells.append([])
    def handle_data(self,data):
        if self.cells:self.cells[-1].append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cells:
            text=' '.join(''.join(self.cells.pop()).split())
            if self.stack:self.stack[-1].append(text)
        if tag=='tr' and self.stack:self.rows.append(self.stack.pop())

def un_cpi(text):
    p=Rows();p.feed(text)
    months={name.upper():i+1 for i,name in enumerate(calendar.month_abbr[1:])}
    out={};active=False
    for row in p.rows:
        heading=' '.join(row)
        if 'Price indices - Consumer price indices:' in heading:
            active='general (all items)' in heading
            continue
        if not active:continue
        for i,cell in enumerate(row[:-1]):
            m=re.fullmatch(r'(\d{4})([A-Z]{3})',cell)
            if m and m[2] in months:
                date=f'{m[1]}-{months[m[2]]:02}'
                if date in out:raise ValueError('Duplicate UN month')
                value=number(float(row[i+1].replace(',','')),0.000001)
                out[date]={'value':value,'notes':' '.join(row[i+2:])}
    if not out or '2086/ Base: 2015=100.' not in ' '.join(' '.join(x) for x in p.rows):
        raise ValueError('UN China base footnote unavailable')
    return out

def cpi_chain(oecd_daily,un):
    oecd={d[:7]:v for d,v in oecd_daily.items()};consecutive(oecd)
    # Never cross the documented Jan2016 level break. Only UN ratios after this
    # break are candidates for extending the original OECD index at its last month.
    safe={m:v['value'] for m,v in un.items() if m>='2016-01' and '2086/' in v['notes']}
    consecutive(safe)
    anchor=max(oecd)
    if anchor not in safe:raise ValueError('No CPI splice anchor')
    overlap=sorted(set(oecd)&set(safe))[-13:]
    discrepancies=[]
    for before,after in zip(overlap,overlap[1:]):
        if index(after)!=index(before)+1:raise ValueError('CPI overlap gap')
        discrepancies.append(abs((oecd[after]/oecd[before])/(safe[after]/safe[before])-1))
    if len(discrepancies)<9 or max(discrepancies)>.002:
        raise ValueError('OECD/UN monthly changes not sufficiently consistent for experimental splice')
    out={m:{'value':v,'source':'OECD/FRED'} for m,v in oecd.items()}
    for m in sorted(x for x in safe if x>anchor):
        prev=month(index(m)-1)
        if prev not in out or prev not in safe:raise ValueError('CPI extension gap')
        out[m]={'value':out[prev]['value']*safe[m]/safe[prev],'source':'UN post2016 ratio chained to OECD anchor'}
    return out,{'anchor':anchor,'overlap_monthly_change_max_relative_discrepancy':max(discrepancies),
        'overlap_changes_checked':len(discrepancies),'extension_through':max(out),
        'un_2015_dec_to_2016_jan_level_ratio_excluded':un['2016-01']['value']/un['2015-12']['value'],
        'method':'Only postJan2016 UN ratios; no use of the rebase crossing. UN one-decimal rounding and source revisions remain.',
        'status':'Experimental compatible-ratio splice, not person-specific consumption inflation'}

def issuer_returns(obj,expected_port):
    if obj['portId']!=expected_port or obj['currencyCode']!='USD':raise ValueError('Unexpected issuer share-class identity/currency')
    out={}
    for row in obj['fundData']['annualNAVReturns']['returns']:
        date=dt.date.fromisoformat(row['asOfDate']);key=date.isoformat()[:7]
        if date.day!=calendar.monthrange(date.year,date.month)[1] or key in out:raise ValueError('Return date/duplicate error')
        out[key]=1+number(row['monthPercent'],-99.999999)/100
    consecutive(out)
    return out

def real_rmb_gross(usd_gross,fx_gross,cpi_gross):
    for x in [usd_gross,fx_gross,cpi_gross]:number(x,0.000001)
    return usd_gross*fx_gross/cpi_gross

def portfolio_replay(rows,equity_weight,withdrawal_rate=.03,fx_shock=0,extra_inflation=0):
    number(equity_weight,0,1);number(withdrawal_rate,0,.2);number(fx_shock,-.5,.5);number(extra_inflation,0,.2)
    # Normalized initial wealth avoids silently importing private baseline assets.
    wealth=100.0;peak=wealth;drawdown=0;short=0;spent=0;path=[]
    for i,row in enumerate(rows):
        spend=min(wealth,100*withdrawal_rate/12);short+=spend+1e-10<100*withdrawal_rate/12;wealth-=spend;spent+=spend
        inflation=row['cpi_gross']*(1+extra_inflation)**(1/12)
        fx=row['fx_gross']*(1+fx_shock if i==0 else 1)
        equity=real_rmb_gross(row['equity_usd_gross'],fx,inflation)
        # Hypothetical zero-interest RMB cash, not AGGU or a guaranteed real asset.
        cash=1/inflation
        wealth*=equity_weight*equity+(1-equity_weight)*cash
        peak=max(peak,wealth);drawdown=max(drawdown,1-wealth/peak)
        path.append({'month':row['month'],'wealth':wealth,'spending':spend})
    return {'ending_wealth_per_100_initial':wealth,'cumulative_spending_per_100_initial':spent,
        'max_wealth_drawdown_including_withdrawals':drawdown,'months_with_unfunded_scheduled_withdrawal':short,'path':path}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=private_destination(a.output)
    if out.exists():raise ValueError('Use a new immutable output directory')
    fx=fx_month_ends(fred(a.raw/'DEXCHUS.csv','DEXCHUS'),'2026-09')
    cpi,cpi_audit=cpi_chain(fred(a.raw/'CHNCPIALLMINMEI.csv','CHNCPIALLMINMEI'),un_cpi((a.raw/'UN-China-CPI.html').read_text()))
    acc=read_json(a.raw/'vanguard-retail-vwra.json');dist=read_json(a.raw/'vanguard-retail-vwrl.json')
    vwra=issuer_returns(acc,'9679');vwrl=issuer_returns(dist,'9505')
    common=sorted(set(vwra)&set(vwrl)&set(fx)&set(cpi))
    rows=[]
    for m in common:
        prev=month(index(m)-1)
        if prev not in fx or prev not in cpi:continue
        fg=fx[m]['cny_per_usd']/fx[prev]['cny_per_usd'];ig=cpi[m]['value']/cpi[prev]['value']
        rows.append({'month':m,'vwra_usd_gross':vwra[m],'vwrl_usd_total_return_gross':vwrl[m],
            'fx_gross':fg,'cpi_gross':ig,'cpi_level':cpi[m]['value'],'fx_date':fx[m]['date'],
            'vwra_real_rmb_gross':real_rmb_gross(vwra[m],fg,ig),
            'vwrl_real_rmb_gross':real_rmb_gross(vwrl[m],fg,ig),
            'equity_usd_gross':vwra[m]})
    consecutive([x['month'] for x in rows])
    if not rows:raise ValueError('No matched real observations')
    write_private(out/'monthly-matched-equity-fx-cpi.json',rows)
    with (out/'monthly-matched-equity-fx-cpi.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_private(out/'cpi-splice-audit.json',cpi_audit)
    write_private(out/'vanguard-vwrl-distributions.json',dist['fundData']['distributionHistory'])
    experiments=[]
    for weight in [1.0,.8]:
        for name,shock,inf in [('observed_history',0,0),('cny_appreciates10pct_at_start',-.1,0),('extra2pct_annual_cpi_growth_factor',0,.02),('combined',-.1,.02)]:
            experiments.append({'name':name,'model_equity_weight':weight,
                'other_asset':'none' if weight==1 else 'hypothetical zero-interest RMB cash; not AGGU',
                'withdrawal':'3% of initial real wealth per year in equal monthly amounts, beginning of month; illustrative',
                'results':portfolio_replay(rows,weight,fx_shock=shock,extra_inflation=inf)})
    write_private(out/'deterministic-equity-and-hypothetical-cash-stresses.json',{'status':'short_history_stress_illustrations_not_probabilistic_forecasts',
        'start':rows[0]['month'],'end':rows[-1]['month'],'months':len(rows),'experiments':experiments,
        'costs':'Issuer NAV total returns already include fund costs/income reinvestment; no duplicate fees/dividends. Broker costs, taxes and cash interest not modeled.',
        'allocation':'Constant model weights rebalanced monthly across all stresses. Neither actual holdings nor dynamic TPAW allocation.',
        'fx':'CNY per USD. One-time10% reduction at first month for appreciation stress; level persists. Extra CPI stress multiplies monthly price growth by1.02^(1/12).',
        'limitations':['Exact AGGU series missing; no actual portfolio replay or full matched stock/bond dataset claimed',
         'Fixed historical path and hypothetical stresses, no bootstrap probabilities or 50-year forecasts','National CPI is not Kunming/travel-specific']})
    write_private(out/'manifest.json',{'kind':'experimental_global_equity_rmb_monthly_pipeline','start':rows[0]['month'],'end':rows[-1]['month'],'months':len(rows),
        'raw_sha256':{p.name:digest(p) for p in a.raw.iterdir() if p.is_file()},'cpi_audit':cpi_audit,
        'vwra_vwrl_monthly_total_return_max_absolute_gross_difference':max(abs(vwra[m]-vwrl[m]) for m in common),
        'share_classes':{'vwra':'IE00BK5BQT80; official USD accumulation NAV total returns; VWRP GBP listing same ISIN',
         'vwrl':'IE00B3RBWM25; official USD NAV total returns with income reinvested; distributions saved separately, not added again',
         'aggu':'IE00BZ043R46 USD Hedged Acc; exact NAV history pending unaccepted issuer terms'},
        'fx_alignment':'Last available US Federal Reserve observation each completed month; <=7 calendar-day lag; noon NY versus NAV valuation/holiday mismatch remains',
        'blocked_actual_portfolio':'Missing exact AGGU NAV/total-return series; do not substitute an unhedged benchmark or zero-interest cash',
        'private_rights':'Raw issuer/FRED data retained locally; no public redistribution authorized'})
    print('Experimental equity/FX/CPI dataset saved:',len(rows),'months;',rows[0]['month'],'through',rows[-1]['month'],'; exact AGGU portfolio remains blocked')

if __name__=='__main__':main()
