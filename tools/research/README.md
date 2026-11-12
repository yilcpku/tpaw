# Local research tools — experimental

The current Astryx/CNY model and verification evidence are documented in
[the local lab](../local-lab/README.md). Historical test notes below describe
the earlier bounded experiments, rather than current release coverage.

These tools prepare experiments, replay the engine with frozen local inputs, and
validate mechanics. They do **not** replace
the TPAW engine, establish deployment parity, or validate any retirement plan.
No financial simulation result is bundled. Personal plans, configurations,
snapshots and outputs belong outside every Git checkout; the Python writer enforces
this. Nothing here uploads data, starts a service, installs dependencies, or trades.

Required Notice: Copyright (c) 2020-2026 Benjamin Mathew and Jacob Mathew.
The [repository license](../../LICENSE.md) links to PolyForm Noncommercial 1.0.0.
Its notice and noncommercial restrictions continue to apply. Upstream currently
does not accept PRs; these research tools are maintained on the independent fork.

## Tested commands

Python 3, standard library only:

```powershell
# From repository root. Use a writable temporary directory if the sandbox default is restricted.
$env:TPAW_RESEARCH_TEST_TMP='F:\Temp'
python -W error::ResourceWarning -m unittest discover -s tools/research -v
python tools/research/research.py freeze --output C:/private-research/baseline.json C:/private-research/original.tpaw.txt
python tools/research/research.py verify C:/private-research/baseline.json
python tools/research/research.py prepare C:/private-research/config.json --output C:/private-research/batch-001
python tools/research/research.py longevity C:/private-research/hk-male-period-2025.json --ages 50 60 70 80 90 --margin 5 --output C:/private-research/longevity.json
# Optional public-data retrieval; contacts only the official C&SD API.
./tools/research/Fetch-HkLifeTable.ps1 -OutputDirectory C:/private-research/csd-snapshot
```

`freeze` and `prepare` refuse to overwrite outputs. `prepare` imports the selected
head of v30 `.tpaw.txt` JSON-patch history and invalidates stale saved results.
The importer supports add/replace/remove/test and rejects other operations rather
than guessing. Candidate plans still need the author's full schema guard and
normalization before use by a future engine adapter.

Example configuration (placeholder filenames, explicitly chosen new experiment controls):

```json
{
  "upstream_commit": "19b9d7b2e573ef7e5a317ee6c6420bc35be2c057",
  "plan": "C:/private-research/original.tpaw.txt",
  "baseline_manifest": "C:/private-research/baseline.json",
  "run": {
    "seed": 860336713,
    "simulation_count": 1000,
    "evaluation_timestamp_ms": 1,
    "timezone": "Asia/Hong_Kong",
    "market_snapshot": null,
    "precision": "efficient mixed f32/f64 plus wire rounding"
  },
  "preference_grid": {"at20": [10, 12, 14], "timePreference": [-0.005, 0, 0.005]},
  "max_cases": 9
}
```

The timestamp above is a placeholder and must be replaced. Seed/count are reviewed
source defaults, **not recovered evidence of a past website run**. Every prepared
case has status `not_run`. An absent snapshot is an explicit blocker.

Add `retirement_months`, `ledger`, and `ledger_start_month` for deterministic
exit-month experiments. The ledger columns are:

```csv
month,salary_net_nominal,bonus_net_nominal,paid_notice_net_nominal,spending_nominal,price_index
```

All pay columns are already net of the applicable deductions, including tax/MPF
when relevant. `price_index` is relative to the common purchasing-power date.
No salary progression, bonus entitlement, notice pay, inflation, or tax calculation
is invented. Contributions are `(salary + bonus + notice - spending)/price_index`.
Only working months strictly before retirement are included; the original future
savings list is replaced to avoid double-counting. No post-departure tax payments
are inferred. Negative savings currently fail validation and require separate
expense handling. Missing months fail. Inputs after the final supplied ledger month
are never extrapolated. Expenses linked to `namedAge: retirement` follow the new
date automatically; absolute-date expenses need explicit review. Partner plans and
undated retirement-month generation are intentionally unsupported.

The v30 author guard requires 10-character IDs, globally unique wealth color
indexes and whole-unit one-time amounts. The generator preserves the unrounded
ledger, rounds each generated saving to nearest whole currency unit (half-even),
and uses deterministic short IDs. The full author guard is still mandatory.

Stage date-only, preference-only and setup/budget sensitivities separately. The
default cap is 36 cases and the hard limit is 200. Optional 1–2 year delays require
additional employment/bonus assumptions and supplied ledger coverage.

## Actual preference semantics

Source: [PlanParams30](../../packages/common/src/Params/PlanParams/PlanParams30.ts),
[inherited value grids](../../packages/common/src/Params/PlanParams/Old/PlanParams27.ts),
[risk processing](../../packages/simulator-rust/src/lib/simulate/process_plan_params_server/process_risk.rs),
[Merton formula](../../packages/simulator-cuda/src/simulate/cuda_process_run_x_mfn_simulated_x_mfn/mertons_formula.h).

| Input | Author field / accepted values | Meaning |
|---|---|---|
| `at20` | `risk.tpaw.riskTolerance.at20`, integer 0–24 | Age-20 anchor of risk tolerance. Larger scores mean smaller relative risk aversion (RRA). |
| `deltaAtMaxAge` | integer −24–0 | Linear change in risk score between age 20 and maximum age, clamped below at zero. |
| `forLegacyAsDeltaFromAt20` | integer 0–24 | Additional risk tolerance for the legacy goal. |
| `timePreference` | −0.05–0.05 by 0.001 | Annual utility discount parameter rho. More positive values favor earlier consumption, all else equal. |
| `additionalAnnualSpendingTilt` | −0.05–0.05 by 0.001 | Extra annual spending-growth tilt, separate from utility time preference. |

For positive score s, `RRA = 16 * exp(-(s-1)*log(32)/23)`; zero maps to infinity.
The anchor spans RRA 16 at s=1 to 0.5 at s=24. The *current-age* risk score differs
when the age slope is nonzero. These scores are not stock percentages or loss
limits. The allocation also depends on expected returns, variance, income, expenses,
legacy and constraints. No separate invented “aggressiveness” slider is introduced.
TPAW has its own utility/allocation approximation; `research.py` does not pretend
to reproduce its financial calculations.

## Reproduction gate and engine adapter

Pin source plus local diff hash, deployed engine identity if available, raw
normalized protobuf request, original plan, evaluation clock/timezone, daily market
snapshot and history version/hash, seed, simulation count, percentile request,
block length/staggering, numeric mode, GPU, CUDA/cuRAND and compiler versions.
Keep returned processed presets, generated sample indices and result bytes.

The browser actually normalizes in `@tpaw/common`, calls `getPlanParamsServer`,
encodes `WireSimulationArgs` and sends zlib/deflate to `/3/simulate`. The Rust
simulator processes the parameters then calls CUDA. A JSON plan is **not** the
wire request. The CUDA Monte Carlo sampler uses **cuRAND XORWOW** seeded by run;
the Rust ChaCha8 helper is used in other processing and must not be mistaken for
the executed CUDA sampler. Reuse complete common sample-index paths across cases,
including the longest evaluation horizon, rather than merely giving all cases the
same nominal seed. Seed equality alone does not prove identical paths after
toolchain, data, run numbering, or sampling changes.

Daily preset data currently download from configured GCS `latest/` paths;
`syntheticConstant` still receives a downloaded live series and is not an offline
startup. Lawful fixture files can replace the external dependency for **new smoke
tests**: JSON matching `DailyMarketDataForPresets` and, when estimation is used,
`VTAndBNDData`. They cannot establish parity with the original unknown snapshot.
Historical return versions and CAPE regression inputs are already in source.

Engine integration stages (file-only stages 1–3 are now implemented; see
[REPLAY_DESIGN.md](REPLAY_DESIGN.md) for verified scope and coverage):

1. Add a local file-only replay subcommand before dotenv/CONFIG/Sentry startup.
   Decode an uncompressed saved `WireSimulationArgs`, load immutable preset JSON,
   and either use `no_estimate` or an explicit frozen estimation fixture. Reject
   missing fields/date coverage. Disable outgoing network and telemetry by
   construction; do not request production credentials.
2. Use the existing Rust conversion and `simulate()` with those fixtures; write
   result protobuf and build/input hashes outside Git. Never print requests or
   processed balances. Preserve the original engine result schema and rounding.
3. Add a small Node adapter using built `@tpaw/common` and the existing wire
   encoder, to validate/normalize each prepared case. Avoid the web application's
   private icon/font dependencies and authentication services.
4. Only after regression at the original fixed horizon, execute new date/preference
   batches. A new fixture-backed run is a separate benchmark when original inputs
   cannot be recovered. Never rename a near-match as exact reproduction.

`public_market.py --start YYYY-MM-DD --end YYYY-MM-DD --output PRIVATE_DIR`
downloads public Treasury real-yield and FRED SP500/T10YIE CSVs, intersects complete
observation dates, converts rates from percent and pins hashes. `--raw-directory`
reuses files named `treasury.csv`, `sp500.csv`, `inflation.csv` with no network.
The market-close timestamp convention is not publication/vintage evidence. Keep
SP500 raw data and generated fixtures local under its redistribution restrictions.
These observations update the US preset inputs; compiled US earnings and historical
returns remain the pinned upstream assumptions. This does not calibrate RMB/global
asset risks or establish website parity.

`RunBatch.ps1` accepts prepared cases, frozen presets, a new private output folder,
the existing replay executable, and runtime/common Node module directories. It
encodes, executes and inspects at most 36 cases, then writes `comparison.json` and
`comparison.csv`. `SummarizeReplay.ts` reports pointwise 5/50/95 percentiles for
initial and later spending, balances and allocation, without selecting an optimum.
It verifies common sampling-generator inputs on the same executable, including
horizon and historical data; the realized sample matrix is not exported. A full
path exporter is still required for hardship probability, cut duration or rolling
longevity/conditional-retirement comparisons.

`compare` accepts future standardized adapter summaries with `status: simulated`,
common controls, and every path exactly once. It refuses differing seed, snapshot,
sample path set, simulation count, precision, clock, currency/base date, fee/tax/FX
assumptions or comparison design. It exports data without choosing an optimum.
`path_metrics` supplies spending, hardship, cut/recovery and consumption/bequest
diagnostics. Matching stock/bond holdings versus comparing whole allocation
strategies are distinct experiment designs; both matched initial spending and
native strategy spending should be reported. Pointwise percentiles do not measure
the probability of ever falling below a budget. Complete path output is required
for those comparisons; the public endpoint's percentile arrays alone are insufficient.

## Conditional retirement and rolling longevity

The first native rolling-policy experiment is now implemented separately in
`tpaw-horizon`; see [HORIZON_EXPERIMENT.md](HORIZON_EXPERIMENT.md) for its exact
annual rule, open-tail treatment, risk/cashflow constraints, full-path validation
and remaining limits. It preserves the original saved plan and standard replay.

`conditional_policy` is a tested generic state machine, **not integrated TPAW**.
Decision dates are the baseline and 12/24 months later. The callback receives the
state and observed history before the decision month's return. The same state/path
continues; no reroll, restart, or bad-path filtering occurs. The cap is explicit:
if forced to retire below the illustrative floor, that failure remains visible.
`policy_summary` reports joint spending/delay outcomes against all original paths.
No financial trigger or future subjective preference about work is selected for
any user. A funded-ratio criterion can later be another explicit callback.

`PeriodLifeTable` calculates `P(T>b | T>a)=l(b)/l(a)`, conditional mean age at death
`a+e(a)`, mean plus a configurable margin, upper death-age quantiles and fixed-age
90 diagnostics. The latest observed official table retrieved on 2026-10-23 is
[C&SD Table 115-01021](https://www.censtatd.gov.hk/en/web_table.html?id=115-01021),
**2025** mortality, release **2 October 2026**. Means use official e(x), not a
truncated integration to 100. Survival between integer ages linearly interpolates
official l(x); this is an explicit approximation.

The row at age 100 is **open-ended**, despite q(x)=1. It is not a one-year death
probability and must never terminate life at 101. Quantiles/probabilities needing
the distribution after 100 return null, with the surviving tail explicitly shown.
An age-120 model cap is a computational assumption, not a biological maximum.

[Projected Table 150-11002](https://www.censtatd.gov.hk/en/web_table.html?id=150-11002)
currently displays annual **2026–2046** rates, release **12 February 2026**. Its
notes identify **2021-based projections first published 15 August 2023**. These are
projected *period* tables; they are not automatically a cohort lifetime forecast.
A cohort scenario follows the calendar-year/age diagonal and requires a stated
mortality-improvement/tail rule after 2046. `cohort_survival` refuses missing rates.
Never use the open age-100 q(x) as an annual cohort q(x).

For illustration, official 2025 male period mortality at exact age 50 gives mean
age at death **84.59**, mean-plus-five horizon **89.59**, about **37.65%** surviving
beyond that horizon, versus **35.98%** beyond age 90. Its 90th death-age quantile
is about **97.36**, 95th about **99.77**, and 99th is in the open age-100 tail.
These are population table calculations, not personalized health predictions.
Five additional years are not a fixed confidence level or safety guarantee.
The 37.65% figure is a point-in-time survival diagnostic for that single frozen
horizon, **not** the ruin probability of an annually recalculated withdrawal
policy. The rolling strategy changes its horizon and withdrawals as wealth,
returns and survival evolve. Compare its actual late-life consumption and assets
at death, including unspent surplus, using common paths. Expected age at death
generally moves later on survival while remaining years generally decrease;
annual withdrawal need not fall mechanically.

To connect a rolling horizon to TPAW, update annually conditional on survival,
carry wealth and realized returns forward, retain a longer evaluation age (e.g.
95/100 and tail stress), and regenerate future planning arrays. Merely changing
the initial `maxAge` does not implement rolling updates. `maxAge` also anchors
the risk-score age slope and named-age timing, so keep those effects explicit.
Report spending/shortfall tradeoffs beyond the mean-plus-margin planning horizon;
never drop people still alive beyond that horizon or force a floor while asserting
non-depletion.

## Global equities and RMB liabilities

The bounded experimental monthly pipeline and its currently missing exact AGGU
input are documented in [GLOBAL_RMB_DATA.md](GLOBAL_RMB_DATA.md). Its interim
equity/macro histories and hypothetical cash stresses do not recalibrate the TPAW
engine or establish personal lifetime probabilities.

Keep the existing U.S. calibration as a labeled benchmark. Replacing it requires
aligned, licensed global-equity total returns and valuation inputs, fund costs and
tax assumptions; actual bond cashflows/credit/duration and the verified share-class
ISIN/hedge; and consistent USD/RMB FX plus Chinese consumption inflation.
An international equity portfolio is not assumed to have higher risk.
VT/BND data used for balance estimation are not the simulated 1871-based history.

For a USD nominal total-return factor G, RMB-per-USD FX X and Chinese CPI I,
`real_RMB_gross = G * (X_next/X_now) / (I_next/I_now)`. Preserve their joint
dependence. A fund's listing currency does not identify its economic FX exposure.
Nominal TIPS total returns already include their U.S. CPI-linked cashflows: do not
add U.S. inflation twice. USD TIPS do not hedge Chinese CPI/RMB liabilities.

RMB nominal sovereign yield combined with assumed inflation supplies a scenario
`(1+y)/(1+expected_inflation)-1`, not a guaranteed real rate or generally the exact
expectation under stochastic inflation. Long nominal bonds have inflation and
early-sale duration risk; reinvestment and maturity mismatch matter. A broad bond
fund is not a risk-free real annuity. Do not use trailing CPI as a multi-decade
inflation forecast or coupon as current yield. Use transparent inflation/FX/rate
sensitivities until an implementable RMB liability hedge is verified.

## Native Windows build experiment

The existing project Dockerfile targets CUDA 12.9.1 on Ubuntu 24.04, GNU-style
compiler flags, Linux library directories, and an absolute bindgen path. Its Rust
README is stale wasm guidance. WSL and Docker were not installed on the inspected
machine, but CUDA 13.3, MSVC 14.51 and an RTX 4090 (sm_89) were present.

`Build-CudaTests.ps1` uses only those existing tools, builds the source list from
Meson into a separate directory, fingerprints inputs for incremental recompilation,
and excludes upstream benchmarks on execution. It does not install or enable
anything. The portability diff replaces GNU statement expressions with ordinary
C++ expressions/lambdas, GNU unused attributes with `[[maybe_unused]]`, and adds
explicit Thrust includes. The Windows build preincludes Windows.h before upstream
FLOAT/CURRENCY macros and enables the conforming MSVC preprocessor.

```powershell
./tools/research/Build-CudaTests.ps1 -OutputDirectory C:/private-research/cuda-build -Run
```

CUDA 13.3 test results cannot establish identical floating-point/cuRAND behavior
to the pinned CUDA 12.9.1 deployment. The committed bindings include unused Linux
aliases such as `__uint64_t = c_ulong`; `c_ulong` differs in size on Windows.
However, the inspected public sampling seed and empirical-mean function already
use Rust `u64`, so no seed-width defect has been demonstrated. Validate every
used FFI structure layout, seed width, exports/import library and DLL search path;
regenerate with bindgen when target differences require it.

Verified on 2026-10-23: the full native test executable built successfully;
**39 correctness cases and 359 assertions passed**, with 19 benchmark cases
excluded. This includes `run_tpaw` and `simulate` using source/synthetic fixtures.
The Python suite passed **12 tests**. Thrust deprecation and recursive kernel
stack-size warnings remain. These are successful engine smoke tests, not a
reproduction of the website result. Subsequently, 2 targeted Rust replay tests
and 76 tests in the four nonempty common source suites passed. The default common
test command fails on an upstream empty test suite (and its compiled duplicate).
Full upstream Rust/web suites and original financial-output regression have not run.

The next bounded Windows integration would need an isolated Rust toolchain,
protobuf compiler and libclang/bindgen, plus project dependencies. Planning estimate:
1–3 GB download and 3–8 GB workspace/build storage, 30–90 minutes, unmeasured and
dependent on network/compilation. The subsequently approved isolated installation
and successful file replay are documented in [REPLAY_DESIGN.md](REPLAY_DESIGN.md).
Ordinary
project-local Python/Meson/Node packages are separate from installing WSL,
virtualization, GPU drivers or Docker services. Those system changes need specific
authorization. A clean Linux/CUDA-12.9.1 environment is the closer parity path but
is not currently installed; do not overwrite an existing LLM CUDA configuration.

Official build references: [NVIDIA 12.9.1 Windows guide](https://docs.nvidia.com/cuda/archive/12.9.1/cuda-installation-guide-microsoft-windows/index.html),
[NVIDIA WSL guide](https://docs.nvidia.com/cuda/archive/12.9.1/wsl-user-guide/index.html),
[Rust installation](https://rust-lang.org/install.html),
[Meson quickstart](https://mesonbuild.com/Quick-guide.html).
