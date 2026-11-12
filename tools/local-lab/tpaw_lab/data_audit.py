"""A read-only audit view for both frozen observed and synthetic datasets."""
import math
import statistics
from .market import JointHistory,Observation,return_statistics


def audit_view(data:dict)->dict:
    raw=data['history'];h=JointHistory(tuple(Observation(**r) for r in raw['rows']),raw['kind'],raw['label'],tuple(raw['sources']),tuple(raw['limitations']))
    factors={name:[] for name in ('global_equity_usd_log','us_equity_usd_log','fx_log','china_cpi_log','us_cpi_log')}
    has_rates=all(r.government_curve is not None for r in h.rows)
    if has_rates:factors.update(government_5y_change=[],deposit_5y_change=[],demand_change=[])
    for row in h.rows:
        for key,value in zip(tuple(factors)[:5],(row.global_equity_usd_gross,row.us_equity_usd_gross,row.cny_per_usd_gross,row.china_cpi_gross,row.us_cpi_gross)):
            factors[key].append(math.log(value))
        if has_rates:
            factors['government_5y_change'].append(row.government_curve['60']-row.government_curve_before['60'])
            factors['deposit_5y_change'].append(row.deposit_curve['60']-row.deposit_curve_before['60'])
            factors['demand_change'].append(row.demand_rate-row.demand_rate_before)
    correlation={a:{b:statistics.correlation(x,y) if statistics.pstdev(x)*statistics.pstdev(y)>0 else None
                    for b,y in factors.items()} for a,x in factors.items()}
    return {**data.get('audit',{}),'data_kind':h.kind,'joined_start':h.rows[0].month,'joined_end':h.rows[-1].month,
        'joined_months':len(h.rows),'return_statistics':return_statistics(tuple(r.equity_gross('global','cny') for r in h.rows)),
        'monthly_factor_correlation':correlation}
