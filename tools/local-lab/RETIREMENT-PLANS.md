# Retirement plans and real purchasing power

Browser-model protocol: `retirement-plans-real-cny-v1`. The Python bridge refuses
older UI envelopes rather than silently applying new rules to old reserve forms.
Model source remains SHA256-pinned and entirely self-hosted.

A scenario compares1–8 independent retirement plans on the same realized market
samples. A fixed plan retires on its explicit month regardless of consumption.
A window plan reviews at the start of every month from start through end,
forecasting first actual retirement-month daily consumption times12. The proposed
exit is min(review month + notice months, window end). A passing review commits
irrevocably. Later market shocks cannot cancel it. Failed reviews continue through
the window; if none pass, retirement occurs at the end with a failed-target flag.
No review occurs before the window opens, and month-m market observations are not
read until decisions at the start of month-m are final. Policy construction is
lazy and shared across paths for a simulation call; reached dates are not evicted
and rebuilt for each path. Very long windows therefore use more memory.

All new monetary flows are evaluation-month REAL CNY: annual living benchmark,
window spending targets, fixed/monthly net savings, explicit retirement income,
and the default2,500,000 retirement withdrawal. Payments are indexed with the
current simulated CPI at month start (publication lag0). Legacy nominal income
is converted by the explicit planning CPI to evaluation-month purchasing power,
then indexed on the realized path. Calendar legacy rows are expanded for an
editable real-valued UI view; retirement-relative nominal rows are converted per
actual proposed exit during schedule compilation, with their legacy label kept.
This conversion is an assumption, not a refreshed actual CPI observation.

Every possible exit compiles a separate contribution schedule: net-savings rows
and the constant working contribution are excluded for m >= actual exit. Notice
months before exit still contribute. Explicit retirement income is a different
kind and begins only at exit. Future dated working contributions remain in the
shared editable table for later-retiring plans, but are inert after an early exit.

The new browser model sets reserve0, empties reserve draws/transfers and removes
old essential/discretionary/budget/reserve-draw presets. It retains net savings
and any explicitly entered retirement income. It inserts exactly one essential,
non-lifestyle2,500,000 REAL CNY goal at the exit month. Planning and trigger
forecasts account for this payment before ordinary spending, and actual payment
is deducted once from core wealth. Paid/short amounts are reported separately;
no separate reserve remains invested and no retained reserve funds a second draw.
The amount is editable; ordinary consumption graphs exclude the one-off payment.
Legacy CLI/native references retain their original machinery for reproduction;
original saved scenarios/results are never rewritten by a load or migration view.

Graphs retain p5/p50/p95 and shade p25–p75. Each yearly observation is the sum of
12 monthly daily-consumption amounts BEFORE calculating cross-path quantiles.
Post-retirement age curves include only paths retired by that year's start, and
show the eligible count. Not-yet-retired paths are not zero spending observations.
During a trigger window these age cohorts can differ between plans; this selection
is disclosed, and curves are not unconditional lifetime success probabilities.

Decade minima group complete yearly points by their starting age:31 <= age <41,
41 <= age <51, etc. The minimum is min(pointwise p5) in each group, not p5 of each
path's worst year. Labels state covered ages; unmodeled ages and partial terminal
years are not inserted. Initial retirement-period totals can be shorter than12
months at the age100 censor and carry their actual min/max month count.

Tests cover fixed dates, monthly triggering, notice/end clipping, forced end,
no-lookahead, constant/dated contribution expiry, one-off accounting, removed
presets, nominal-to-real conversion, quartile ordering, paired draws, decade
boundaries, age100 truncation and >64-date policy reuse. Frozen pre-change generic
oracles continue to check the legacy ledger. No test fixtures contain personal
financial records.
