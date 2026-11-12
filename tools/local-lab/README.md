# Local TPAW research lab

An offline research extension with a Meta Astryx interface, a nominal CNY account
model, preserved native snapshots and an edited-input native control. Verification
covers the mechanisms and numerical agreement described below; historical proxy
data and explicit contract assumptions do not establish future retirement safety.

The unchanged upstream commit is `19b9d7b2e573ef7e5a317ee6c6420bc35be2c057`.
The existing rolling-horizon, conditional-retirement and file-replay experiments
are preserved in `tools/research` and the separate native research entry points.

## Run locally

Requirements: Python 3.13+, Node 24+, npm. The portable research extension uses
Python's standard library. The original native simulator still requires CUDA.

```powershell
cd packages/local-lab
npm ci
npm run build
cd ../..
python tools/local-lab/serve.py --data-dir "<your private data directory>" --port 8765
```

Open `http://127.0.0.1:8765`. The server binds only to loopback, serves its own
bundled assets, and makes no external requests. Do not load personal inputs into
a public host. Sources are fetched in a separate, explicit preparation step.

Data directories inside a Git checkout must already be ignored and untracked;
every write checks this. `.private/` is ignored for this purpose. Public provider
captures, derived data, personal scenarios and results stay outside Git. Frozen
data/result identifiers cannot be overwritten with different content.

`fetch_sources.py` records raw public bytes, retrieval times and hashes.
`prepare_sources.py` accepts French ZIP exports and captured FRED observation
tables, validates frequencies and joins only consecutive observed months.
`prepare_synthetic.py` constructs a separately labeled synthetic stress dataset
using the pinned 1871–2026 US real-stock anchor and observed joint differences.
Provider source dates, current coverage and limitations are retained in each
dataset. Raw licensed data are not redistributed here.

### Optional current-input native control

Build the offline native research export using `tools/research/Build-CudaLibrary.ps1`
and pin its SHA256 before use. Add `--native-config "<private config.json>"` when
starting the server. The private JSON contains absolute `dll`, `source`,
`stock_stats`, `bond_stats` paths, their corresponding `<key>_sha256` values, and
`cuda_bin`. The source/table paths are the pinned v8 Rust historical series and
its stock/bond empirical block-size tables. Keep config, requests and outputs in
the private directory, outside source control. The pinned Windows export requires
an ASCII output path. No DLL is downloaded or selected through the UI.

The native tab lets you select a candidate retirement date and fixed90/95/100
deadline, then rerun current form inputs. A separate child process has a5-minute
limit; only complete native outputs passing paired portable replay are returned.
The immutable archived reference remains a separate panel. Changing parameters
does not overwrite either result. Each run saves input, sampled-path and binary
hashes locally; the UI marks results stale when its inputs change.

## Authenticated server deployment

An explicitly authorized single-owner server deployment is separate from the
loopback-only desktop mode. Personal files remain outside Git and outside the
static directory; transferring an existing archive requires the owner's explicit
authorization. `serve_hosted.py` uses salted scrypt password hashes and in-memory
8-hour sessions, secure/HttpOnly/SameSite cookies, exact-origin JSON writes,
mandatory initial password change and session revocation after a password change.
There is no registration or public financial-data API. All private records are
blocked until the initial password has changed. Static assets contain no account
or financial records. Logs omit requests and financial values.

Build with `VITE_TPAW_HOSTED=1`, `TPAW_BASE_PATH=/tpaw/` and
`TPAW_BUILD_DIR=dist-hosted`, then run `npm run build`. Keep the normal default
build for the local CUDA-enabled app. Initialize credentials interactively in an
ignored/non-Git private directory using `AuthStore.create` with `getpass` input;
never place passwords in source, command-line arguments or public deployment files.

Run the hosted app behind an HTTPS reverse proxy, binding only to loopback:

```text
python serve_hosted.py --data-dir <private runtime> --static-dir <hosted dist>   --auth-file <private account.json> --origin https://planner.example.com   --path-prefix /tpaw/ --port 8766 --max-runs 100
```

The proxy must strip `/tpaw/` (trailing-slash `proxy_pass`), forward the public
`Host` unchanged, preserve cookies and pass original `Origin`/fetch headers. Do
not cache authenticated API responses. Scope changes to that route; existing
sites and TLS settings remain untouched. Use a dedicated service account and
restrict writable paths to the runtime and credential directories. The static
root must be disjoint from private data and credentials, checked at startup.

Only the portable Python model runs on a typical Linux CPU server. Preserved
native snapshots remain available; the pinned Windows/CUDA rerun stays in the
local app. The hosted response advertises its configured path-count cap. Existing
source/financial artifacts are copied with hashes, not regenerated or made public.

## Model boundaries

- `policy.py` ports the pinned constant-expectation TPAW Merton/NPV/spending
  equations to double precision. It is separate from the original CUDA baseline.
  Original risk tolerance constants are retained; all horizon cases share the
  same risk-age curve, anchored at age90 and held constant thereafter.
- Fixed90/95/100 and annual attained-age `x + e(x) + margin` funding horizons use
  identical realized market draws. Five margin years are a heuristic, never a
  safety quantile. Mortality is a frozen Hong Kong male period table; evaluation
  is censored at100 and its open-interval survivor tail stays explicit.
- Actual market paths use joint, real consecutive 60-month blocks. They never
  wrap from the end of a history to its beginning. This is a different sampler
  from the original CUDA circular bootstrap and is labeled accordingly.
- Equity total returns, CNY-per-USD FX and Chinese CPI are applied once. Fund
  NAV total returns must not have income/expenses applied again. Current French
  developed-market data are a proxy with different coverage from FTSE All-World.
- Forward means are absolute targets for the arithmetic average of overlapping
  12-month returns; volatility is monthly log standard deviation times sqrt12.
  CAGR, monthly arithmetic mean times12 and rolling12 statistics remain distinct.
  No extra CAPE/valuation haircut is applied after choosing an absolute target.
- Nominal deposits retain contractual interest until maturity and recognize lost
  accrued interest when broken early at the currently known demand rate. Nominal government bonds (annual coupons through7years, semiannual thereafter) are
  repriced from their remaining cashflows, including yield changes and early
  sales. Reinvestment uses rates known at each month start. These are explicit
  illustrative contracts, not product quotes, guarantees, or a default model.
- The original long equity/FX/CPI pack retains explicitly assumed defensive rates.
  `prepare_assets.py` adds a separate Apr2006-Apr2025 joint pack with official
  ChinaBond curves and BOC posted deposit/demand rates. It applies paired monthly
  rate changes to the current curve, with explicit zero floors and persistence;
  rates do not reset to unrelated levels at bootstrap boundaries. BOC posted
  quotes are a single-bank proxy and do not reconstruct executed contracts.
- Official VWRL monthly NAV total returns enter the hybrid from Jun2012; earlier
  French developed returns exclude emerging markets and have different cost
  coverage. Full monthly FTSE history is not claimed. Monthly ETF overlap and10
  exact Oct-Sep FTSE factsheet windows are audited and shown in the UI.
- Optional8-case outcome attribution holds common CNY accounting and nominal
  defensive assets fixed, varies only the equity real-return bridge, and averages
  all6 channel orders (Shapley). It disables forward recalibration in this panel
  so the measured return differences are not calibrated away.
- `audit_joint.py` checks generic contract identities across rate-persistence,
  synthetic-construction seed and calibration-period sensitivities. Its recorded
  rates, floors, moments and correlations are evidence of assumption sensitivity,
  not a validation of future macroeconomic regimes.
- Core cash-floor replenishment cannot draw on the separately partitioned
  reserve. Replenishment is a transfer, not consumption. Reserve withdrawals use
  equal amounts from its cash/equity sleeves and retain any unfunded difference.
- At a review, notice projects known contributions with fixed model expected
  returns and the same cash-floor, spending and nominal-contract logic as actual
  months. It never reads future realized notice returns or reverses a commitment
  after a market shock. Final-date forced exits and actual exit failures differ.
- Cashflow rows support dated net savings (already net salary/bonus/notice costs),
  retirement income, nominal/real essential and discretionary goals, annual budget
  replacement phases and separate reserve draws. Imported ledger coverage cannot
  silently extrapolate into a later candidate retirement.
- Reserve targets can be partitioned at evaluation or retirement. A future
  partition is planned as a core funding goal, then recorded as an internal
  transfer; only subsequent reserve withdrawals are consumption. Equal-sleeve
  draws are limited by the smaller sleeve, with shortages retained explicitly.
- `import_archive.py` reads hash-verified private author-validated processed
  requests/results plus an explicit private mapping. It preserves immutable native
  reference bytes, dated original inputs, FX and all intended mapping changes.
  It does not refresh current wealth, invent future payroll, or add baseline budget
  categories twice. Original-source snapshots are never overwritten.
- The UI separates ordinary lifestyle spending, one-off total spending, requested
  funding gaps, cash-floor gaps and reserve gaps. Imported native references retain
  the original monthly-marginal aggregation, real-return currency convention and
  calibration variance; edited inputs are disclosed rather than claimed as rerun.
- The edited-input native control uses current core wealth, planned cashflows,
  risk curve, expectations and independent planning variance. It retains the
  author's US-real stock/bond history, circular/staggered60-month sampler and
  empirical block60 mean correction. It fixes retirement/deadline and excludes
  CNY contracts/cash-floor/reserve returns; nominal goals are pre-deflated with
  planning CPI. A retirement reserve partition becomes a one-off core goal.
  These differences are enumerated; the extension/native difference is not a
  single-variable causal estimate. Source rolling moments and sampler targets
  are distinguished. Same-path portable replay uses independently carried wealth.
- Annual charts aggregate complete path-year sums before calculating quantiles.
  Incomplete terminal periods are labeled with their actual month count and are
  not connected as full annual observations or extrapolated beyond the endpoint.

## Verification

### Browser calculation

The web UI runs the same portable Python model in a module Web Worker using
Pyodide 314.0.7. `npm run build` packages a deterministic, SHA-256-checked archive
of public model modules and the pinned WASM runtime. All engine assets are served
from the same origin; financial payloads are never sent to a Python CDN.
The first visit downloads about 14 MB. Versioned runtime assets can be cached;
API responses, the engine manifest and HTML are not cached.

Authenticated `GET /api/browser-inputs/<dataset>` supplies the selected joint
history and mortality table. Browser reports are saved through `POST /api/results`
and explicitly labeled as client-computed; the storage server does not certify
their numerical contents. Hosted `POST /api/run` returns 410 to stale clients.
Login, password changes, archives and private storage keep their existing access
controls. Logout/unmount terminates the worker and clears the in-memory input
cache. Cancellation also terminates the worker, including WASM initialization.

The normal UI compares rolling life expectancy only with fixed age 90, reusing
the same sampled market draws. Legacy CLI multi-horizon and attribution tools
remain available separately. Compact runs aggregate monthly paths one at a time;
the policy recurrence is reused for months sharing the same horizon endpoint.
Frozen generic pre-change outputs test numerical equivalence across cash,
deposits and government bonds. Nothing in this optimization changes assumptions.

Charts support pointer/touch inspection, drag-to-zoom, reset, and a keyboard age
slider. Incomplete terminal years retain their actual month count and stay out of
the full-year line. Numeric controls keep a text draft while typing decimals.
Hidden CPI lag, rate persistence, cash trigger and risk conventions retain their
stored values and are disclosed on the methods page. Historical net savings are
imported dated amounts, not newly estimated BigLaw payroll; they already deduct
tax and work-period living expenses.

Runtime references: [Pyodide module workers](https://pyodide.org/en/stable/usage/webworker.html)
and [custom Python packages](https://pyodide.org/en/stable/usage/loading-custom-python-code.html).

```powershell
cd tools/local-lab
python -m unittest discover -s tests -v
```

Tests exercise currency direction, non-circular joint blocks, moments, return
attribution identities, nominal cashflow accounting, deposit-break losses, bond
pricing, separate reserve/cash floors, no-lookahead notice, horizon changes,
mortality mass and synthetic construction. They do not establish future safety.

`audit_native.py` optionally checks this port's consumption map against
hash-verified private decoded native outputs. It checks monthly consumption as a
function of native beginning balances. `export_native_paths.py` and
`audit_native_paths.py` optionally check full independently carried portable paths
against a supplied hash-pinned native DLL, including1000-path regression and
original-marginal rounding diagnostics. Exact CUDA floating-point identity is
not claimed. Keep all inputs, DLLs and reports private. The remaining integration
and release evidence is recorded in `REQUIREMENTS.md`.

Required Notice: Copyright (c) 2020-2026 Benjamin Mathew and Jacob Mathew.
The parent project's PolyForm Noncommercial 1.0.0 license applies.

## Multi-plan browser model update

The current browser model supersedes candidate-date selection and independent
reserve mechanics. See [retirement rules and monetary units](RETIREMENT-PLANS.md)
for fixed/window comparisons, monthly triggering, notice clipping, contribution
expiry, the one-time real-CNY retirement withdrawal, quartiles and decade minima.
Original archive records and legacy reproduction commands remain preserved.
