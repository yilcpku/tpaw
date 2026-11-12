# Completion audit — full scope retained

Status: implementation and integration verified; release receipt is maintained locally.
Passing unit tests alone is insufficient; the evidence below includes actual native
paths, broad ledger integrations and observed UI results.

## Implemented mechanisms

- Annual attained-age conditional mean plus configurable margin; fixed90/95/100.
- Paired market draws for four-horizon comparisons and explicit age100 censoring.
- Monthly consumption paths, late budget-cut size/spells, estate distributions
  conditional on death before100, and separate age100 survivor assets.
- USD total equity returns × CNY/USD ÷ China CPI, with joint non-circular60-month
  sampling and distinct return statistics.
- Pre2003 French developed-market proxy, official VWRL total-return splice from
  Jun2012,172-month proxy/ETF overlap and10 official nonoverlapping FTSE Oct-Sep
  windows. Proxy/fund cost and emerging-market coverage differences retained.
- Observed-history pack separate from an explicitly synthetic1871–2026 pressure
  construction. Modern fitted joint components/residuals are not historical RMB.
- Absolute forward return/volatility targets without a second valuation haircut.
- Nominal deposit and coupon-government-bond accounting, maturity, reinvestment,
  current-demand early-break, remaining-term YTM curve and6/12month coupons.
- Official Apr2006-Apr2025 joint curve/posted-rate history, observed monthly rate
  changes, explicit zero floor/persistence, factor correlations, regime/seed
  sensitivity. Model dependence is quantified; no future-regime validation claim.
- Eight paired equity-channel outcome controls with6-order Shapley contributions.
- Original DLL full-path export:1000x687months,3,435,000 portable-policy checks
  passed predeclared0.02%/1-unit tolerance. Native float32 vs portable float64
  remains deliberate. Reconstructing rounded processed inputs differs from saved
  native marginals by <0.74 balance units /0.009 spending units; not bit-exact.
- Arbitrary ordered candidate retirement months, irrevocable notice, no use of
  future realized notice-period returns, separate forced/actual threshold flags.
- Separate reserve and dynamic core onshore cash-floor ledgers, no double wealth.
- Local Astryx UI, local save/load/run, source/provenance and sensitivity display.
- Hash-verified archived native reference panel plus explicit historical plan
  imports, dated net contributions/bonuses, nominal/real phase goals, budget
  replacement, retirement reserve partition, strict equal-sleeve draws.
-65 mechanism/import/audit tests and desktop/mobile editor/risk-panel checks.

## Completion evidence

- Joint observed and synthetic integration: deposits/government bonds, persistence
  1/.97/.9, three construction seeds, two calibration regimes, four horizons and
  eight outcome-attribution controls. Rate nonnegativity clamps, moment/correlation
  changes and assumption sensitivity are retained in the audit and UI.
- Two historically imported scenarios each passed100 paths x four horizons with
  exact registered-input matching and unchanged source hashes. Dated savings stop
  at retirement; missing ledger coverage fails instead of extrapolating payroll.
- Edited-input native control covers all three fixed deadlines and a selected
  candidate date. Two imported scenarios x100 paths x three deadlines passed
  2,241,000 paired money/allocation checks. Old native snapshots stay immutable;
  fixed-date US-real/circular-sampler and nominal-goal differences are explicit.
- Current Python model/import/privacy/audit suite:65 tests. Research helpers:23
  tests. Windows directory-link destination tests:3 tests. Current-source native
  CUDA suite:42 correctness cases/490 assertions,19 benchmarks skipped. Astryx
  TypeScript and production build pass; Vite reports a nonfatal large-chunk warning.
- Desktop/mobile scenario editing, save/load, native rerun/stale markers, partial
  terminal-period labeling and actual consumption outputs were observed. Saved
  phase scenarios rerun deterministically. API rejects cross-origin writes and
  incomplete inputs. Runtime assets/API are local; external source acquisition is
  a separate explicit command, with same-origin CSP on the runtime page.
- Standards review: no remaining hard violation; one nonblocking duplicate Rust
  snapshot-validator heuristic. Spec review: notice projections now use the same
  cash-floor/contracts as actual months; partial-year sums are labeled and excluded
  from annual polylines. Focused native-control review found no further issue.
- Private archive verifies its original1257 manifest entries,843 pinned sources,
  and zero tracked/staged private files. Generic source contains no personal
  financial inputs, result files, DLLs or market-provider caches.

## Interpretation and coverage limits

This implements the requested research workflow, not a calibrated lifetime safety
probability. Mean remaining life plus five years is a heuristic. Age100 is an
explicit evaluation censor; survivors are not assigned death. Period mortality,
pre-ETF developed-market proxies, official single-bank posted rates and YTM-based
representative bonds retain their documented limitations. Long pre-overlap CNY
components are explicitly synthetic. Current valuation targets are absolute
sensitivity inputs, without a duplicate CAPE haircut.

The native control's agreement tolerance is max(1 accounting unit,0.02%) for money
and0.0001 for stock allocation, reflecting nativefloat32/portablefloat64. It does
not establish website/deployed CUDA-version parity. The full upstream Rust/web
suite is not asserted. The local lab runs through the verified Python/native
bridge; optional archived Rust research entries remain separate.

Verified generic source is to land on the user's fork under the repository's
normal PR/squash workflow. The private local release receipt records the final
commit/PR and complete evidence hashes; no personal materials accompany that PR.
