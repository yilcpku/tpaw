"""Audit bounded conditional retirement paths; no network or alternative engine.

Required Notice: Copyright (c) 2020-2026 Benjamin Mathew and Jacob Mathew.
See ../../LICENSE.md (PolyForm Noncommercial 1.0.0).
"""
import argparse
import csv
import hashlib
import math
from contextlib import ExitStack
from pathlib import Path
from research import read_json, write_private, digest
from analyze_horizon import quantiles


def decisions(path, n, starts, threshold):
    rows = list(csv.DictReader(path.open(newline='')))
    if len(rows) != n:
        raise ValueError('Decision count')
    for i, row in enumerate(rows):
        if int(row['run']) != i or int(row['retirement_month']) not in starts:
            raise ValueError('Missing or invalid decision')
        chosen = starts.index(int(row['retirement_month']))
        reviews = [float(row[f'review{j}']) for j in range(3)]
        if any(not math.isfinite(v) for v in reviews):
            raise ValueError('Nonfinite decision')
        if any(v >= threshold for v in reviews[:chosen]):
            raise ValueError('Ignored earlier passing review')
        if any(v != -1 for v in reviews[chosen+1:]):
            raise ValueError('Unobserved future review populated')
        forced = int(row['forced_below_threshold'])
        if forced != int(chosen == 2 and reviews[chosen] < threshold):
            raise ValueError('Cap flag mismatch')
        if int(row['would_still_work_if_threshold_required']) != forced:
            raise ValueError('Alternative censored flag mismatch')
        if not forced and reviews[chosen] < threshold:
            raise ValueError('Premature exit')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--fixed-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    design = read_json(args.experiment/'design.json')
    n = design['simulation_count']
    starts = design['decision_start_months']
    months = design['evaluation_months']
    age0 = design['current_age_months']
    if len(starts) != 3 or starts != sorted(set(starts)) or starts[-1] >= months:
        raise ValueError('Invalid decision clock')
    targets = {60*12-age0: 'age60', 80*12-age0: 'age80'}
    configs = [('control-th0', 0)] + [
        (f'{mode}-th{t}', t)
        for mode in ['frozen-base-no-new-bonus', 'flat-real-savings']
        for t in design['thresholds_real_hkd']]
    data = {}
    for name, threshold in configs:
        rows = decisions(args.experiment/(name+'-decisions.csv'), n, starts, threshold)
        data[name] = {
            'threshold': threshold, 'decisions': rows,
            'initial': [0.0]*n, 'total': [0.0]*n,
            'first_setup': [0.0]*n, 'balance_at_exit': [0.0]*n,
            'months_below': [0]*n, 'longest_below': [0]*n,
            'spell': [0]*n, 'ever_below': [False]*n,
            'profiles': {}, 'monthly': [], 'retired_months': [0]*n,
            'budgets': {b: {'months': [0]*n, 'ever': [False]*n}
                        for b in design['thresholds_real_hkd']},
        }
    max_regression = {key: 0.0 for key in ['balance_start', 'general', 'total', 'balance_end']}
    path_hash = hashlib.sha256()
    with ExitStack() as stack:
        streams = {name: csv.DictReader(stack.enter_context((args.experiment/(name+'-paths.csv')).open(newline='')))
                   for name, _ in configs}
        fixed = csv.DictReader(stack.enter_context(args.fixed_paths.open(newline='')))
        for index in range(n*months):
            m, r = divmod(index, n)
            reference = next(fixed)
            if (int(reference['month']), int(reference['run'])) != (m, r):
                raise ValueError('Fixed path order')
            key = ','.join(reference[x] for x in ['sample_index', 'stock_return', 'bond_return'])
            path_hash.update((key+'\n').encode())
            for name, _ in configs:
                row = next(streams[name]); s = data[name]
                if (int(row['month']), int(row['run'])) != (m, r):
                    raise ValueError('Missing/reordered path')
                if ','.join(row[x] for x in ['sample_index', 'stock_return', 'bond_return']) != key:
                    raise ValueError('Different realized market path')
                values = {x: float(row[x]) for x in ['balance_start', 'general', 'total', 'balance_end']}
                if any(not math.isfinite(x) or x < -.001 for x in values.values()):
                    raise ValueError('Invalid financial value')
                if values['general'] > values['total']+.001:
                    raise ValueError('General spending exceeds total')
                if name == 'control-th0':
                    for field in max_regression:
                        max_regression[field] = max(max_regression[field], abs(values[field]-float(reference[field])))
                elif m < starts[0]:
                    if any(abs(values[field]-float(reference[field])) > 1e-7 for field in max_regression):
                        raise ValueError('Changed path before first retirement decision')
                decision = s['decisions'][r]; retire = int(decision['retirement_month'])
                if m < retire and values['total'] != 0:
                    raise ValueError('Retirement withdrawal before chosen exit')
                if m == retire:
                    s['initial'][r] = values['general']
                    s['first_setup'][r] = values['total']-values['general']
                    s['balance_at_exit'][r] = values['balance_start']
                    if abs(values['general']-float(decision[f'review{starts.index(retire)}'])) > 1e-7:
                        raise ValueError('Decision probe differs from actual first spending')
                if m >= retire:
                    s['total'][r] += values['total']
                    s['retired_months'][r] += 1
                    below = values['general'] < s['threshold']
                    s['months_below'][r] += int(below)
                    s['ever_below'][r] |= below
                    s['spell'][r] = s['spell'][r]+1 if below else 0
                    s['longest_below'][r] = max(s['longest_below'][r], s['spell'][r])
                    for budget, b in s['budgets'].items():
                        b['months'][r] += int(values['general'] < budget)
                        b['ever'][r] |= values['general'] < budget
                if m in targets:
                    s['monthly'].append(values['general'])
                    if r == n-1:
                        s['profiles'][targets[m]] = quantiles(s['monthly'])
                        s['monthly'] = []
        for stream in streams.values():
            if next(stream, None) is not None:
                raise ValueError('Extra conditional paths')
    if any(x > 1e-7 for x in max_regression.values()):
        raise ValueError('Threshold0 differs from original fixed-date financial path')
    first_review = [row['review0'] for row in data['control-th0']['decisions']]
    if any([row['review0'] for row in s['decisions']] != first_review for s in data.values()):
        raise ValueError('First financial review differs across thresholds/cashflow modes')
    results = {}
    for name, threshold in configs:
        s = data[name]
        counts = [sum(int(x['retirement_month']) == m for x in s['decisions']) for m in starts]
        forced = sum(int(x['forced_below_threshold']) for x in s['decisions'])
        groups = {}
        for m in starts:
            ids = [i for i, x in enumerate(s['decisions']) if int(x['retirement_month']) == m]
            groups[str(m)] = {'count': len(ids), 'fraction_of_all_paths': len(ids)/n,
                             'initial_general_spending': quantiles([s['initial'][i] for i in ids]) if ids else None}
        results[name] = {
            'threshold': threshold, 'delay_counts_0_1_2_years': counts,
            'delay_frequencies': [x/n for x in counts],
            'mean_delay_months': (counts[1]*12+counts[2]*24)/n,
            'forced_retire_below_threshold_at_cap_count': forced,
            'would_still_work_if_threshold_required_count': forced,
            'first_general_spending_all_paths': quantiles(s['initial']),
            'first_setup_all_paths': quantiles(s['first_setup']),
            'balance_at_exit_all_paths': quantiles(s['balance_at_exit']),
            'first_general_spending_by_exit_group': groups,
            'common_age_general_spending': s['profiles'],
            'ever_general_below_own_review_threshold_after_retirement': sum(s['ever_below'])/n,
            'mean_months_general_below_own_review_threshold_after_retirement': sum(s['months_below'])/n,
            'longest_months_below_own_review_threshold': quantiles(s['longest_below']),
            'undiscounted_total_retirement_consumption_if_alive_to90': quantiles(s['total']),
            'retired_months_before_fixed90': quantiles(s['retired_months']),
            'same_budget_metrics_all_paths_alive_to90': {
                str(budget): {'ever_below': sum(b['ever'])/n,
                              'mean_months_below': sum(b['months'])/n}
                for budget, b in s['budgets'].items()},
            'paired_initial_general_minus_fixed_date_initial': quantiles([
                value-base for value, base in zip(s['initial'], data['control-th0']['initial'])]),
        }
    write_private(args.output, {
        'status': 'experimental_US_calibration_not_personal_probability_validation',
        'currency': design['currency'],
        'percentile_order': [5, 50, 95], 'design': design,
        'all_paths_retained': n, 'months': months,
        'common_realized_path_sha256': path_hash.hexdigest(),
        'threshold0_max_pathwise_regression_error': max_regression,
        'cashflow_modes': 'Known salary rungs by seniority with no new bonuses; alternatively flat real net saving. Neither is guaranteed future employment.',
        'decision_timing': 'Before current monthly return; current observed wealth and candidate0/1/2 budget. Three-month advance notice not modeled: financial exit-option illustration.',
        'cap_convention': 'All paths retire at24months for financial outcomes, including failures. Still-working is a separate censored flag, not additional employment simulation.',
        'shortfall_semantics': 'Threshold is illustrative ongoing spending, not a user minimum. Pathwise metrics assume alive throughout to fixed90; no mortality weighting or discounting.',
        'results': results,
        'input_sha256': {str(p): digest(p) for p in [args.experiment/'design.json', *[args.experiment/(name+'-decisions.csv') for name, _ in configs]]},
    })
    print('All-count, common-path, review timing, cap retention and unchanged fixed-date regression checks passed; private comparison saved')


if __name__ == '__main__':
    main()
