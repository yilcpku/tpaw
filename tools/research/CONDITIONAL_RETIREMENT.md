# Experimental retirement exit option

This separate local executable reuses the original Rust parameter processing,
historical sampling, CUDA TPAW precomputation, spending constraints and monthly
accounting. It changes when retirement starts on each path. It does not modify
the production simulator entry point or the saved original plan. No API, cloud,
telemetry, credentials or new asset selection is involved.

## Contract and timing

Supply exactly three author-validated protobuf requests, with retirement dates
twelve months apart. Match evaluation date, explicit initial balance, risk/time
preferences, original horizon, sampling and empirical calibration snapshot.
Prepare the candidate cashflow/expense schedules privately. Future employment
income belongs only before each candidate exit; a setup expense tied to retirement
moves with that exit. Do not add notice pay on top of salary already included in
the notice months. The runner uses candidate0 until its first review.

At the beginning of each review month, before that month's return, compute the
ongoing spending available if retirement starts now. This probe uses the same
precomputation, discretionary-goal scaling and wealth constraints as the actual
monthly spending calculation. Retire if it meets an explicitly supplied real
spending threshold. Otherwise select the next candidate schedule and work another
twelve months. Preserve current assets, realized returns and previous decisions;
never restart a path, filter adverse paths or resume paid work after retirement.

At the last review the financial scenario retires regardless of the threshold.
Record both `forced_below_threshold` and
`would_still_work_if_threshold_required`. The latter is a separately reported
censored alternative decision, not simulated employment beyond the cap. Do not
claim both outcomes' financial paths have been calculated. Unobserved later
decision probes remain -1. No user readiness rule is inferred from the threshold.

The default `--notice-months 0` is a **frictionless financial exit-option
illustration**. The implemented `--notice-months 3` variant separates the
commitment month from retirement. At the start of the review month, before its
cashflow and return, project the next three months' known net contributions and
constant model expected returns through the author's existing monthly allocation
and accounting functions. Probe the projected retirement-month ongoing spending.
Do not read those months' realized returns in the projection, transfer projected
wealth into the actual account, or add notice pay on top of existing salary.

If that forecast passes, commit irrevocably and retain the selected schedule
through retirement; actual notice-period market returns still affect wealth and
initial spending. Do not reverse notice with hindsight. If it fails, choose the
next annual candidate immediately, including its known longer employment schedule
and associated allocation assumptions. At the final commitment date, force notice
for the final retirement date and separately flag failure of the projected rule.
Report **projected failure at commitment** and **actual failure at exit** separately.
A forecast that passed is not a spending guarantee during the intervening period.

In the bounded April-exit comparison, reviews occur at the start of January,
with January/February/March monthly net savings paid once, before their respective
monthly returns according to the original engine convention. December bonuses
are already in observed January wealth; no new post-baseline bonus is invented.
Paid notice is those ordinary salary months, not an additional income entry.
The synthetic notice test verifies three contributions, irrevocability after an
unforeseen notice-period shock, delayed/capped exits, and zero-threshold baseline
consistency. `analyze_notice.py` additionally audits the monthly balance identity,
selected ledger prefixes, actual/forecast spending flags and unchanged common paths.

Each candidate uses the author's deterministic expected-run goal reference from
the original evaluation date. These are forecast assumptions, not realized
future information. Switching references does not reset actual wealth. This is
one explicit reference convention, not a claim of an optimized dynamic policy.
All preferences and the original fixed horizon remain unchanged. Current Rust
historical processing supplies zero expected-return changes; this executable
rejects nonzero changes until beginning-of-month timing is audited.

## Employment scenarios

Future salary rungs may be frozen at a currently documented public scale and
advanced by seniority. That does not establish future pay, job continuity or
promotion. [Skadden's current salary information](https://www.skadden.com/careers/associate-salary-information)
corroborates the known rungs; it explicitly describes the current scale and
discretionary bonuses. [Reuters' Cravath raise report](https://www.reuters.com/legal/legalindustry/cravath-announces-raises-upping-pay-ante-large-law-firms-2023-11-28/)
provides historical context, not a future bonus announcement. Preserve the
original ledger exactly, including December timing. Excluding additional future
bonuses is a transparent sensitivity, not a prediction of zero bonuses. A separate
flat real net-savings sensitivity avoids inventing a future payroll ladder. Keep
the existing tax/MPF convention explicit rather than reapplying tax twice. Tax on
retirement assets/withdrawals remains provisional until modeled separately.

## Run and audit

Build the native library with `Build-CudaLibrary.ps1`, then the Rust
`tpaw-conditional` binary with that library's local import path. Use a private
directory outside every Git checkout for the request manifest and outputs:

```powershell
tpaw-conditional --requests F:/private/requests.json --presets F:/private/presets.json --threshold 25000 --output-prefix F:/private/example
tpaw-conditional --requests F:/private/requests.json --presets F:/private/presets.json --threshold 25000 --notice-months 3 --output-prefix F:/private/notice
python tools/research/analyze_conditional.py --experiment F:/private/experiment --fixed-paths F:/private/fixed-paths.csv --output F:/private/comparison.json
python tools/research/analyze_notice.py --experiment F:/private/notice-experiment --output F:/private/notice-comparison.json
```

The private design specifies decision-month indices, evaluation age/months,
simulation count, currency, thresholds and scenarios. Compare a threshold-zero
control with the original fixed-date full paths. The audit rejects missing or
reordered paths, differing market indices/returns, nonfinite/negative financial
outputs, earlier ignored passing reviews, populated unobserved reviews,
inconsistent cap flags, spending before retirement, or probe/actual-spending
disagreement. Report every path in joint delay/spending summaries and include
all forced below-threshold exits. A threshold is only an initial review rule;
it does not maintain a spending floor after retirement.

Native tests use a zero-return synthetic case to verify immediate retirement,
one-year deferral with continuous savings, cap failure retention, and the fact
that a later return shock cannot change earlier probes, decisions or spending.
The expanded suite passed 42 correctness cases /490 assertions on the existing
Windows CUDA13.3 setup; 19 benchmarks were excluded. Rust check/build succeeded.
Full production Linux/CUDA12.9.1 parity and the old website snapshot remain
unverified. Historical US calibration is a benchmark, not personal probabilities
or an intended RMB defensive-asset selection.

Report ongoing spending separately from setup expenses, at actual exit and at
common later ages. Compare same-budget pathwise shortfalls and their duration,
not only pointwise percentiles. Cumulative spending here is undiscounted real
retirement consumption conditional on survival throughout the fixed horizon;
delayed exits also have fewer retirement months. Do not select an optimum by
highest median or presume future dislike of work is known.

## Next bounded stage

The proposed defensive sleeve is CNY long-term deposits or nominal government
bonds, with no product, issuer, maturity or rate selected. AGGU acquisition has
stopped and is not a required data gate. Keep the US benchmark separate while
specifying two illustrative ladders: contractual deposit cashflows/early-break
terms, and government-bond cashflows/prices/early-sale duration risk. Both need
reinvestment, liquidity and stochastic Chinese inflation assumptions; nominal
returns are not guaranteed real returns. Use the already pinned global-equity,
FX and Chinese-CPI history for bounded historical/stress accounting before any
long-horizon forecast. No transactions or product commitments are implied.
