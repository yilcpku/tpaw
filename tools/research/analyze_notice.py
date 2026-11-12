"""Compare irrevocable advance notice against the frictionless exit option.

Required Notice: Copyright (c) 2020-2026 Benjamin Mathew and Jacob Mathew.
See ../../LICENSE.md (PolyForm Noncommercial 1.0.0).
"""
import argparse
import csv
import math
import struct
from contextlib import ExitStack
from pathlib import Path
from analyze_conditional import decisions
from analyze_horizon import quantiles
from research import read_json, write_private, digest


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    design = read_json(args.experiment/'design.json')
    n, months = design['simulation_count'], design['evaluation_months']
    starts = design['decision_start_months']
    age0 = design['current_age_months']
    threshold = design['threshold_real_hkd']
    notice = design['notice_months']
    ledger = list(csv.DictReader(Path(design['cashflow_ledger']).open(newline='')))
    ledger_by_month = {row['month']: row for row in ledger}
    if len(ledger_by_month) != len(ledger):
        raise ValueError('Duplicate monthly income')
    rounding_unit = design['ledger_real_income_rounding_unit']
    if not math.isfinite(rounding_unit) or rounding_unit <= 0:
        raise ValueError('Ledger rounding unit')
    clock_year, clock_month = map(int, design['evaluation_calendar_month'].split('-'))
    real = {}
    for m in range(months):
        calendar = clock_year*12+clock_month-1+m
        key = f'{calendar//12:04}-{calendar%12+1:02}'
        row = ledger_by_month.get(key)
        if row:
            if float(row['paid_notice_net_nominal']) != 0:
                raise ValueError('Extra notice pay duplicates existing monthly salary')
            amount = (float(row['salary_net_nominal'])+float(row['bonus_net_nominal'])-float(row['spending_nominal']))/float(row['price_index'])
            real[m] = round(amount/rounding_unit)*rounding_unit
        else:
            real[m] = 0.0
    data = {}
    for name, spec in design['cases'].items():
        prefix = Path(spec['prefix'])
        d = decisions(Path(str(prefix)+'-decisions.csv'), n, starts, spec['threshold'])
        for row in d:
            if spec['notice_months']:
                if int(row['notice_months']) != notice or int(row['commitment_month']) != int(row['retirement_month'])-notice:
                    raise ValueError('Notice/commitment clock mismatch')
        data[name] = {'spec': spec, 'decisions': d, 'initial': [0.0]*n,
                      'forecasts': [0.0]*n, 'income_sum': [0.0]*n,
                      'consumption': [0.0]*n, 'below': [0]*n, 'ever': [False]*n,
                      'profiles': {}, 'monthly': [], 'accounting_max_error': 0.0}
    regression = 0.0
    with ExitStack() as stack:
        streams = {name: csv.DictReader(stack.enter_context(
            Path(s['spec']['prefix']+'-paths.csv').open(newline=''))) for name, s in data.items()}
        for index in range(n*months):
            m, r = divmod(index, n)
            rows = {name: next(stream) for name, stream in streams.items()}
            base = rows['fixed-date']
            for name, row in rows.items():
                s = data[name]; spec = s['spec']; decision = s['decisions'][r]
                retire = int(decision['retirement_month'])
                if (int(row['month']), int(row['run'])) != (m, r):
                    raise ValueError('Missing/reordered financial paths')
                if any(row[k] != base[k] for k in ['sample_index', 'stock_return', 'bond_return']):
                    raise ValueError('Market paths differ')
                v = {k: float(row[k]) for k in ['balance_start', 'balance_end', 'general', 'total']}
                if any(not math.isfinite(x) or x < -.001 for x in v.values()):
                    raise ValueError('Invalid financial output')
                if name == 'notice-control' or m < starts[0]-notice:
                    error = max(abs(v[k]-float(base[k])) for k in v)
                    regression = max(regression, error)
                    if error > 1e-7:
                        raise ValueError('Changed fixed baseline or pre-decision history')
                if m < retire and v['total'] != 0:
                    raise ValueError('Withdrawal before committed exit')
                if spec['notice_months']:
                    inc, allocation = float(row['income_applied']), float(row['stock_fraction'])
                    if inc < 0 or not math.isfinite(inc) or not 0 <= allocation <= 1:
                        raise ValueError('Cashflow/allocation')
                    if m >= retire and inc != 0:
                        raise ValueError('Employment income after retirement')
                    if abs(inc-(real[m] if m < retire else 0)) > 1e-7:
                        raise ValueError('Selected monthly cashflow differs from rounded frozen ledger')
                    s['income_sum'][r] += inc
                    net = max(0, v['balance_start']+inc-v['total'])
                    stock = net*allocation
                    expected_end = stock*f32(1+float(row['stock_return'])) + (net-stock)*f32(1+float(row['bond_return']))
                    error = abs(expected_end-v['balance_end'])
                    s['accounting_max_error'] = max(s['accounting_max_error'], error)
                    if error > max(1e-6, abs(expected_end)*1e-12):
                        raise ValueError('Balance identity: possible duplicated contributions')
                if m == retire:
                    s['initial'][r] = v['general']
                    s['forecasts'][r] = float(decision[f'review{starts.index(retire)}'])
                    if spec['notice_months']:
                        if abs(float(decision['actual_initial_spending'])-v['general']) > 1e-7:
                            raise ValueError('Actual exit spending mismatch')
                        if int(decision['actual_initial_below_threshold']) != int(v['general'] < spec['threshold']):
                            raise ValueError('Actual exit threshold flag')
                if m >= retire:
                    s['consumption'][r] += v['total']
                    s['below'][r] += int(v['general'] < threshold)
                    s['ever'][r] |= v['general'] < threshold
                if m in [60*12-age0, 80*12-age0]:
                    s['monthly'].append(v['general'])
                    if r == n-1:
                        s['profiles'][f'age{(m+age0)//12}'] = quantiles(s['monthly'])
                        s['monthly'] = []
        if any(next(stream, None) is not None for stream in streams.values()):
            raise ValueError('Extra financial paths')
    results = {}
    # The frozen ledger contains the input monthly net savings only once. Its
    # prefix is compared with each path's exported, actually selected cashflow.
    for name, s in data.items():
        d = s['decisions']; spec = s['spec']
        counts = [sum(int(row['retirement_month']) == m for row in d) for m in starts]
        if spec['notice_months']:
            # Compare actual normalized inputs, preserving the documented
            # preparation rounding rather than silently changing the baseline.
            for r, row in enumerate(d):
                expected_income = sum(real[m] for m in range(int(row['retirement_month'])))
                if abs(s['income_sum'][r]-expected_income) > 1e-6:
                    raise ValueError('Selected income disagrees with once-only frozen ledger')
        passed = [i for i, v in enumerate(s['forecasts']) if v >= spec['threshold']]
        missed_after_passing = sum(s['initial'][i] < spec['threshold'] for i in passed)
        results[name] = {
            'delay_counts_0_1_2_years': counts,
            'delay_frequencies': [v/n for v in counts],
            'mean_delay_months': (counts[1]*12+counts[2]*24)/n,
            'cap_projected_below_threshold_count': sum(int(row['forced_below_threshold']) for row in d),
            'would_still_work_if_projected_threshold_required_count': sum(int(row['would_still_work_if_threshold_required']) for row in d),
            'actual_exit_below_threshold_count': sum(v < spec['threshold'] for v in s['initial']),
            'actual_exit_below_common_comparison_budget_count': sum(v < threshold for v in s['initial']),
            'passed_commitment_threshold_count': len(passed),
            'passed_commitment_but_missed_at_actual_exit_count': missed_after_passing,
            'first_general_spending_actual': quantiles(s['initial']),
            'first_general_spending_forecast_at_commitment': quantiles(s['forecasts']),
            'actual_minus_forecast_spending': quantiles([a-b for a,b in zip(s['initial'], s['forecasts'])]),
            'common_age_general_spending': s['profiles'],
            'same_budget_ever_below_if_alive_to90': sum(s['ever'])/n,
            'same_budget_mean_months_below_if_alive_to90': sum(s['below'])/n,
            'undiscounted_retirement_consumption_if_alive_to90': quantiles(s['consumption']),
            'balance_identity_max_error': s['accounting_max_error'] if spec['notice_months'] else None,
        }
    write_private(args.output, {'status': 'bounded_notice_aware_US_benchmark_not_personal_validation',
        'design': design, 'percentile_order': [5,50,95],
        'threshold0_max_full_path_error': regression,
        'all_paths_retained': n, 'common_market_paths': True,
        'income_audit': 'Monthly balance identity and once-only selected ledger prefix; no salary after exit or extra paid-notice entry.',
        'cap_semantics': 'January projected criterion can force April retirement at cap; actual April failure reported separately. Still-working remains censored alternative only.',
        'results': results,
        'input_sha256': {str(p): digest(p) for p in [args.experiment/'design.json', Path(design['cashflow_ledger'])]},
    })
    print('Notice timing, common paths, fixed control and once-only cashflow accounting passed; private comparison saved')


if __name__ == '__main__':
    main()
