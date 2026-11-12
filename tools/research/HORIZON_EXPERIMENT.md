# Bounded native rolling-horizon experiment

This experimental local comparison preserves the saved plan. No personal inputs
or results belong in the repository. It does not constitute complete validation.

`tpaw-horizon` uses original Rust parameter processing, CUDA sampling, historical
return processing, Merton/NPV calculations and TPAW monthly accounting. A separate
C entry exports full paths before sorting, with actual sample indices and realized
returns. Original production/replay entries remain available. The optional monthly
planning-end array changes NPV/spending and legacy discount horizons; an absent
array retains the original fixed-end calculation. Portfolios continue on the same
paths without restarting, filtering, or consulting future realized returns.

`horizon_schedule.py` uses [C&SD 115-01021](https://www.censtatd.gov.hk/en/web_table.html?id=115-01021),
Hong Kong male 2025 **period** mortality, released 2 October 2026. At attained
integer age x, planning end-age is `x + e(x) + 5`, updated in the birthday month.
Between birthdays that calendar end-date stays fixed. The initial partial year
uses the last attained-age rule. Month precision is explicit: the exact birthday
day is unknown. End-age rounds to the nearest month (half-even), retaining the
author's inclusive final-age-month convention. Five years is a heuristic, not a
confidence level or safety guarantee. No future mortality improvement is assumed.

The first implementation retains the original risk-age curve and holds terminal
RRA beyond its original maximum age, rather than stretching the risk slope with
the changing horizon. Cashflows after the original horizon are explicitly zero.
Both choices isolate this funding-horizon experiment and need review before plans
with later income/liabilities or alternative risk-age policies are supported.

Fixed90 keeps its original final month; thereafter it uses one month remaining.
With zero legacy and no later income, its remaining assets are spent at the end
and zero spending/assets remain in all subsequent paths. This is an explicit
finite-horizon comparator, not a claim about emergency behavior after age90.

Financial evaluation stops at the exact age100 boundary. The official age100 row
is **open-ended**: q(100)=1 is not certain death within one year. No post100 death
probability is invented. Survivors and their conditional assets at100 stay separate.

`analyze_horizon.py` reports ongoing spending, balances/allocation, consumption if
alive through100, and mortality-weighted consumption/assets at death **before100**,
conditional on being alive at retirement. It linearly interpolates official l(x),
pays withdrawals at month start and assigns deaths month-end balances. Mortality
is independent of markets. Quantiles of mortality-weighted expectations are across
market paths, not joint death/market quantiles. Survivor probability/assets at100
are not assigned death or discarded. Setup costs are excluded from general monthly
spending and included in total consumption. Half-of-own-initial-spending cuts are
illustrative diagnostics conditional on survival to100, not agreed budget floors.

Validation includes annuity accounting under zero returns, horizon updates with
continuous wealth, invalid schedule rejection and a later-return no-lookahead test.
The expanded native suite passed 40 cases/387 assertions (19 benchmarks excluded).
The actual-path analyzer checks every path/month, identical realized sample indices
and returns, finite/nonnegative outputs, and mortality weights plus the age100 tail
summing to one. The fixed90 prefix reproduces all original local monthly 5/50/95
general/total spending, balance and allocation arrays within wire rounding.

Remaining limits: cohort improvement, mortality after100, risk-age anchor and later
liabilities, budget definitions, empirical global/RMB calibration and robustness
across seeds/regimes. Positive spending in this sample does not establish adequacy.

## Four-horizon robustness audit

Fixed95 and fixed100 schedules use the same original risk-age curve, assets,
cashflows, seed/count and realized sample indices/returns as fixed90 and rolling.
Funding horizons keep the inclusive terminal-age month convention. Financial
evaluation stops immediately on reaching100: fixed100 still has its terminal
month reserved, whereas rolling retains a further planning interval. Neither's
post100 consumption or tail risk is established by the censored comparison.

Annual utility time preference rho remains unchanged at its input setting. Horizon
updates do not alter rho or extra spending tilt. Mortality is used to form the
heuristic horizon and in outcome evaluation; the experiment is not a survival-
weighted expected-utility optimization. Future official-table revisions are not
forecast: it ages through one frozen 2025 period table.

`horizon_robustness.py` distinguishes statistics of per-market-path mortality
expectations from the joint mixture across market paths and enumerated monthly
death dates. The latter uses mortality weights rather than a random death sample.
Estate quantiles conditional on death before100 additionally divide by that death
probability. Censored consumption includes what age100 survivors consumed through
the cutoff, without assigning them death. They retain separate conditional assets.

The accounting identity checked path by path is
`sum(S_start * C_month) = sum(d_month * cumulative_C_month) + S100 * cumulative_C100`.
The corresponding discounted identity and estate conditioning/total-expectation
identity are also checked. Undiscounted outputs are sums of real HKD, not nominal
cash or utility. A separately labeled 2% real annual reporting discount sensitivity
uses month-start consumption and month-end estate, relative to retirement. It is
not utility rho, an estimated return, a chosen preference or an RMB risk-free rate.

Late-budget sensitivities use explicit real-HKD thresholds, not inferred user
preferences. All-survive-to100 counts and longest spells are separate from
mortality-weighted expected months/ever-shortfall probability conditional alive80.
The latter integrates first-shortfall survival probability. Probability bounds,
duration bounds, longest-vs-total duration and monotonicity across budgets are
checked. No currency conversion or RMB purchasing-power assertion is introduced.
