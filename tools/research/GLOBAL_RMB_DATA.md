# Experimental global-equity / real-RMB data pipeline

`global_rmb.py` builds a new, private monthly fixture. It does not replace any
saved plan, silently refresh holdings, or validate a long-horizon forecast. Raw
issuer/macro data, hashes, current holdings and outputs stay outside Git on F.

## Sources and meaning

- Vanguard public individual-investor fund data: USD NAV monthly **total returns**
  for IE00BK5BQT80 (accumulation, port9679) and IE00B3RBWM25 (distribution, port9505).
  The retail page identifies NAV-to-NAV performance as net of expenses with gross
  income reinvested. Dividends and fund fees must not be added/deducted again.
  VWRL distributions are preserved separately for auditing, not added to these
  total returns. GBP/EUR exchange listings do not make the underlying class hedged.
- The previously investigated AGGU class IE00BZ043R46 is USD Hedged Acc. Its
  acquisition is outside the CNY deposit/government-bond model's scope. It is
  not a required retirement calibration input or an outstanding data blocker.
  Historical holdings remain separate from future asset choices; no sale is implied.
  A proposed CNY long-term deposit or nominal bond sleeve has no selected issuer,
  maturity or rate. No complete global stock/defensive portfolio replay is claimed.
- Fed/FRED DEXCHUS is **CNY per USD**, using the last available observation of
  completed months. Actual observation dates are retained; a gap over seven days
  fails. NY-noon FX versus fund NAV timing and cross-market holidays remain caveats.
- OECD/FRED CHNCPIALLMINMEI ends April2025. UN general/all-items China CPI extends
  through August2026 in the retrieved source. UN also contains a separate food
  series with duplicate dates: it must be excluded by table/series grain.

UN headline tables use2010=100 but China switches to2015=100 in January2016
(footnotes2086 and708). The Dec2015-to-Jan2016 level ratio is never a price return.
The pipeline uses only post-break UN ratios, checks twelve overlapping monthly
changes against OECD, and chains ratios after the final OECD month. It retains
the OECD anchor level. Source rounding/revisions and broad national consumption
coverage remain; this is not Kunming/travel-specific inflation.

For nominal USD total-return gross factor G, CNY-per-USD gross FX factor X and
Chinese CPI gross factor I, `real_RMB_gross = G * X / I`. No US CPI is added. Bond
currency hedging embedded in an actual AGGU NAV must not be applied a second time;
USD-to-RMB exposure would still remain.

## Current bounded output and limits

The initial retrieved overlap is August2019–August2026,85 monthly observations.
Both Vanguard classes have nearly identical total returns on this overlap, which
supports the reinvested-series interpretation; it is not a long-sample validation.
The source retains longer VWRL history as a potential explicit proxy, never an
unlabeled extension of the accumulation class or AGGU.

The interim deterministic examples use normalized initial real wealth100 and a
constant-real withdrawal benchmark of3% of initial wealth yearly, paid in equal
monthly amounts. This is **ex-post real accounting**, not an operational CPI-lag
withdrawal rule, a TPAW run or a future forecast. Implementable nominal-CNY spending
requires a stated publication-lag convention. Broker costs/taxes are not modeled.

One group is100% global equity. A separate hypothetical group is80% equity and20%
zero-interest RMB cash, rebalanced monthly. This cash is neither AGGU nor guaranteed
real purchasing power. Within each group, allocation is held identical across the
observed path and three explicit stress overlays: one-time10% CNY appreciation at
the start, an additional1.02 annual CPI growth factor, and both combined. These
overlays are assumptions, not estimates or probabilities. The actual portfolio,
dynamic TPAW allocation and hypothetical defensive assets remain separate.

Do not bootstrap this short history into apparently reliable50-year probabilities,
infer a higher global-equity risk than US risk, or treat a favorable historical
sequence as sufficient retirement funding. Licensed long global-index history has
not been obtained or purchased. The next defensive-sleeve stage should compare
illustrative CNY nominal deposit and nominal government-bond ladders separately.
Deposits require explicit contractual rates, maturities, early-withdrawal terms,
issuer limits and reinvestment assumptions. Government bonds require cashflows,
maturities, yield/price data, early-sale duration risk and reinvestment assumptions.
Both require uncertain Chinese CPI and liquidity assumptions; neither a nominal
coupon nor nominal deposit rate is a guaranteed real purchasing-power return.
The earlier zero-interest cash example is only a stress-accounting fixture, not
a selected CNY asset. The US TIPS benchmark likewise is not that selection.

Tests cover FX direction, inflation scaling, no duplicate distributions/fees,
holiday/partial-month FX selection, share-class identity, all-items versus food,
and preservation of the CPI base break. Personal inputs and computed results are
intentionally absent from this document.
