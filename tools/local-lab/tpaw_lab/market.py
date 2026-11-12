"""Joint monthly observations, explicit return units, and non-circular block draws.

All factors are month-on-month gross factors, not percentages or index levels.
Source acquisition is separate: this module never fetches or silently extends data.
"""
from dataclasses import dataclass, replace
import math
import random
import statistics
from typing import Literal


def finite(value: float, name: str, low: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    if low is not None and value < low:
        raise ValueError(f"{name}: below allowed minimum")
    return float(value)


def month_index(month: str) -> int:
    if len(month) != 7 or month[4] != "-":
        raise ValueError("Use YYYY-MM months")
    y, m = map(int, month.split("-"))
    if not 1 <= m <= 12 or not 1800 <= y <= 2200:
        raise ValueError("Invalid month")
    return y * 12 + m - 1


@dataclass(frozen=True)
class Observation:
    month: str
    global_equity_usd_gross: float
    us_equity_usd_gross: float
    cny_per_usd_gross: float
    china_cpi_gross: float
    us_cpi_gross: float
    deposit_rate_annual: float
    government_yield_annual: float
    source: str
    government_curve_before: dict[str,float] | None = None
    government_curve: dict[str,float] | None = None
    deposit_curve_before: dict[str,float] | None = None
    deposit_curve: dict[str,float] | None = None
    demand_rate_before: float | None = None
    demand_rate: float | None = None

    def __post_init__(self):
        month_index(self.month)
        for key in ("global_equity_usd_gross", "us_equity_usd_gross", "cny_per_usd_gross", "china_cpi_gross", "us_cpi_gross"):
            if finite(getattr(self, key), key) <= 0:
                raise ValueError(f"{key}: positive gross factor required")
        for key in ("deposit_rate_annual", "government_yield_annual"):
            if finite(getattr(self, key), key) <= -1:
                raise ValueError(f"{key}: annual rate must exceed -100%")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("Every row needs a source identifier")
        for field in ("government_curve", "deposit_curve"):
            before,after=getattr(self,field+"_before"),getattr(self,field)
            if (before is None)!=(after is None):
                raise ValueError("Historical rate changes require both month boundaries")
            if before is not None:
                if not before or set(before)!=set(after):
                    raise ValueError("Rate curve tenor sets differ")
                for curve in (before,after):
                    for term,rate in curve.items():
                        if not str(term).isdigit() or int(term)<=0:
                            raise ValueError("Curve tenors must be positive whole months")
                        finite(rate,"nominal curve rate",0)
        if (self.demand_rate_before is None)!=(self.demand_rate is None):
            raise ValueError("Demand-rate history needs both boundaries")
        if self.demand_rate is not None:
            finite(self.demand_rate,"demand rate",0)
            finite(self.demand_rate_before,"demand rate before",0)

    def equity_gross(self, universe: Literal["global", "us"], currency: Literal["cny", "usd"]) -> float:
        if universe not in ("global", "us") or currency not in ("cny", "usd"):
            raise ValueError("Unknown equity universe or real currency")
        usd = self.global_equity_usd_gross if universe == "global" else self.us_equity_usd_gross
        return usd * self.cny_per_usd_gross / self.china_cpi_gross if currency == "cny" else usd / self.us_cpi_gross


@dataclass(frozen=True)
class JointHistory:
    rows: tuple[Observation, ...]
    kind: Literal["observed", "synthetic_stress"]
    label: str
    sources: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self):
        if self.kind not in ("observed", "synthetic_stress") or not self.rows:
            raise ValueError("Explicit history kind and nonempty rows required")
        if not self.label or not self.sources or not self.limitations:
            raise ValueError("History label, sources and limitations required")
        indices = [month_index(row.month) for row in self.rows]
        if any(b != a + 1 for a, b in zip(indices, indices[1:])):
            raise ValueError("History must be ordered, unique, consecutive months")


def contiguous_blocks(history: JointHistory, months: int, runs: int, seed: int, block: int = 60) -> tuple[tuple[int, ...], ...]:
    """Uniform moving-block bootstrap; no wrap inside a historical block.

    The final simulation block may be truncated at the evaluation boundary.
    Reuse these exact indices for every paired market/strategy comparison.
    Python Random's generator is separate from the unchanged original CUDA RNG.
    """
    if any(type(x) is not int for x in (months, runs, seed, block)):
        raise ValueError("Integer sampling inputs required")
    if not 0 < months <= 1440 or not 0 < runs <= 10000 or not 0 < block <= len(history.rows):
        raise ValueError("Sampling bounds or insufficient history")
    rng = random.Random(seed)
    result = []
    for _ in range(runs):
        indices = []
        while len(indices) < months:
            start = rng.randrange(len(history.rows) - block + 1)
            indices.extend(range(start, start + min(block, months - len(indices))))
        result.append(tuple(indices))
    return tuple(result)


def return_statistics(gross: list[float] | tuple[float, ...]) -> dict:
    """Name unlike statistics explicitly; monthly vol uses sample ddof=1.

    sqrt(12) monthly volatility assumes no serial dependence. Rolling 12-month
    volatility measures overlapping annual returns and includes serial effects.
    """
    if len(gross) < 13 or any(finite(x, "gross") <= 0 for x in gross):
        raise ValueError("At least 13 positive monthly gross factors required")
    simple = [x - 1 for x in gross]
    logs = [math.log(x) for x in gross]
    rolling = [math.expm1(sum(logs[i:i + 12])) for i in range(len(logs) - 11)]
    return {
        "months": len(gross),
        "arithmetic_monthly_mean": statistics.mean(simple),
        "arithmetic_monthly_mean_times_12": 12 * statistics.mean(simple),
        "compound_annual_growth_rate": math.expm1(12 * statistics.mean(logs)),
        "rolling_12m_arithmetic_mean": statistics.mean(rolling),
        "rolling_12m_simple_volatility_sample": statistics.stdev(rolling),
        "monthly_simple_volatility_times_sqrt12_sample": statistics.stdev(simple) * math.sqrt(12),
        "monthly_log_volatility_times_sqrt12_sample": statistics.stdev(logs) * math.sqrt(12),
        "rolling_12m_log_volatility_sample": statistics.stdev([sum(logs[i:i + 12]) for i in range(len(logs) - 11)]),
        "rolling_12m_observations": len(rolling),
        "rolling_windows_overlap": True,
    }


def calibrate_equity(history: JointHistory, universe: Literal["global", "us"], currency: Literal["cny", "usd"],
                     target_rolling12_mean: float, target_monthly_log_vol_annualized: float) -> JointHistory:
    """Absolute forward targets replace historical moments once.

    Scale centered real log returns, then shift to match the arithmetic mean of
    overlapping 12-month gross returns. CPI/FX/yield observations remain paired.
    No CAPE haircut or fund expense is subsequently subtracted. The transformed
    result is a synthetic scenario, never an observed return history.
    """
    target = finite(target_rolling12_mean, "target annual arithmetic mean")
    vol = finite(target_monthly_log_vol_annualized, "target log volatility", 0)
    if target <= -1 or len(history.rows) < 13:
        raise ValueError("Invalid forward target or insufficient history")
    logs = [math.log(row.equity_gross(universe, currency)) for row in history.rows]
    src_vol = statistics.stdev(logs) * math.sqrt(12)
    if src_vol == 0 and vol > 0:
        raise ValueError("Cannot create volatility from a constant series")
    center = statistics.mean(logs)
    residual = [(x - center) * (vol / src_vol if src_vol else 0) for x in logs]
    window_logs = [sum(residual[i:i + 12]) for i in range(len(logs) - 11)]
    # Log-sum-exp avoids overflow in the rolling gross-factor expectation.
    maximum = max(window_logs)
    log_base = maximum + math.log(statistics.mean(math.exp(x - maximum) for x in window_logs))
    shift = (math.log1p(target) - log_base) / 12
    rows = []
    for row, residual_log in zip(history.rows, residual):
        real = math.exp(residual_log + shift)
        usd = real * row.china_cpi_gross / row.cny_per_usd_gross if currency == "cny" else real * row.us_cpi_gross
        key = "global_equity_usd_gross" if universe == "global" else "us_equity_usd_gross"
        rows.append(replace(row, **{key: usd}))
    return JointHistory(tuple(rows), "synthetic_stress", history.label + " / absolute forward-moment scenario", history.sources,
                        history.limitations + ("Forward targets replace historical equity moments; no second valuation adjustment. Residual ordering and paired macro/yield rows retained; empirical correlation can change after transformation.",))


def attribution(history: JointHistory) -> dict:
    """Exact additive log decomposition on the same dates, plus return statistics.

    log(global CNY real / US USD real) = log(global/USD US) + log(FX)
        + log(US CPI) - log(China CPI). This is not a withdrawal-outcome attribution.
    """
    rows = history.rows
    annual = lambda values: 12 * statistics.mean(values)
    components = {
        "global_minus_us_equity_annual_log": annual([math.log(r.global_equity_usd_gross / r.us_equity_usd_gross) for r in rows]),
        "cny_per_usd_annual_log": annual([math.log(r.cny_per_usd_gross) for r in rows]),
        "us_cpi_annual_log": annual([math.log(r.us_cpi_gross) for r in rows]),
        "minus_china_cpi_annual_log": -annual([math.log(r.china_cpi_gross) for r in rows]),
    }
    actual = annual([math.log(r.equity_gross("global", "cny") / r.equity_gross("us", "usd")) for r in rows])
    if not math.isclose(sum(components.values()), actual, rel_tol=1e-11, abs_tol=1e-12):
        raise ArithmeticError("Return attribution identity failed")
    return {"start": rows[0].month, "end": rows[-1].month, "kind": history.kind,
            "annualized_log_components": components, "total_annualized_log_difference": actual,
            "series": {f"{u}_{c}_real": return_statistics([r.equity_gross(u, c) for r in rows])
                       for u, c in (("us", "usd"), ("global", "usd"), ("us", "cny"), ("global", "cny"))}}
