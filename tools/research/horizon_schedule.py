"""Annual attained-age conditional-mean-plus-margin schedule; no mortality invention."""
import math
from research import PeriodLifeTable, integer, number


def build_schedule(current_age_months, original_months, rows, margin=5, evaluation_age=100):
    current_age_months=integer(current_age_months,0,1199)
    integer(original_months,1,1440)
    number(margin,0,30)
    # No annual q(100) exists: censor financial evaluation at the exact age100 boundary.
    evaluation_age=integer(evaluation_age,1,100)
    months=evaluation_age*12-current_age_months
    if months<=0:
        raise ValueError('Evaluation must extend beyond current age')
    table=PeriodLifeTable(rows)
    rolling=[]
    for m in range(months):
        attained=(current_age_months+m)//12
        horizon=attained+table.rows[attained]['ex']+margin
        # Match upstream's inclusive final age-month convention; nearest month,
        # half-even. Updated on birthdays, held as a calendar end-date between them.
        end=round(horizon*12)-current_age_months+1
        if end<=m:
            raise ValueError('Positive remaining planning horizon required')
        rolling.append(end)
    fixed=[max(original_months,m+1) for m in range(months)]
    planning=max(original_months,months,max(rolling))
    return {'evaluation_months':months,'planning_months':planning,
            'rolling':rolling,'fixed':fixed,'current_age_months':current_age_months,
            'evaluation_age':evaluation_age,'margin_years':margin,
            'policy':'Official period e(x) at attained integer age; birthday updates; age-month rounding',
            'fixed_expiry':'Original age90 funding end; thereafter one-month remaining horizon, retaining zero-wealth paths',
            'tail':'Financial evaluation censored at exact age100; survivors and their assets remain explicit, no q(100) applied'}
