"""Double-precision research port of the pinned TPAW constant-expectation policy.

Equations follow simulator-cuda/{mertons_formula.h,run_tpaw.cu,run_common.h}.
This is distinct from the unchanged native baseline; numerical parity must be
checked against the native engine. Market sampling/account ledgers are separate.
"""
from dataclasses import dataclass
import math
from .market import finite


@dataclass(frozen=True)
class PolicyPlan:
    initial_balance: float
    retirement_month: int
    income: tuple[float, ...]
    essential: tuple[float, ...]
    discretionary: tuple[float, ...]
    rra: tuple[float, ...]
    end_by_month: tuple[int, ...]
    stock_mu_annual: float
    bond_mu_annual: float
    stock_annual_log_variance: float
    time_preference: float = 0
    additional_spending_tilt: float = 0
    legacy: float = 0
    legacy_rra: float = 4
    floor: float | None = None
    ceiling: float | None = None

    def __post_init__(self):
        n = len(self.income)
        if not n or len(self.rra) != n or len(self.essential) != n or len(self.discretionary) != n:
            raise ValueError("Policy schedule dimensions")
        if not self.end_by_month or len(self.end_by_month) > n or any(type(e) is not int or e <= m or e > n for m, e in enumerate(self.end_by_month)):
            raise ValueError("Policy planning-end bounds")
        if type(self.retirement_month) is not int or not 0 <= self.retirement_month < len(self.end_by_month):
            raise ValueError("Retirement outside evaluation")
        finite(self.initial_balance, "initial balance", 0)
        for name in ("income", "essential", "discretionary"):
            for x in getattr(self, name):
                finite(x, name, 0)
        for x in self.rra + (self.legacy_rra,):
            if not (x > 0 and (math.isfinite(x) or x == math.inf)):
                raise ValueError("Positive RRA (or infinity) required")
        if finite(self.stock_mu_annual, "stock expectation") <= -1 or finite(self.bond_mu_annual, "bond expectation") <= -1:
            raise ValueError("Expected annual returns must exceed -100%")
        if finite(self.stock_annual_log_variance, "stock log variance") <= 0:
            raise ValueError("Positive stock log variance required")
        finite(self.time_preference, "time preference")
        finite(self.additional_spending_tilt, "spending tilt")
        finite(self.legacy, "legacy", 0)
        for x in (self.floor, self.ceiling):
            if x is not None:
                finite(x, "spending bound", 0)
        if self.floor is not None and self.ceiling is not None and self.floor > self.ceiling:
            raise ValueError("Floor exceeds ceiling")


@dataclass(frozen=True)
class Entry:
    income_npv: float
    essential_npv: float
    discretionary_npv: float
    legacy_npv: float
    stock_fraction: float
    legacy_stock_fraction: float
    denominator: float
    spending_tilt: float


@dataclass(frozen=True)
class Reference:
    wealth: float
    discretionary_elasticity: float
    legacy_elasticity: float


def merton(stock_mu: float, bond_mu: float, variance: float, rho: float, additional_tilt: float, rra: float) -> tuple[float, float]:
    premium = max(0.0, stock_mu - bond_mu)
    if math.isinf(rra):
        annual_tilt, weight = additional_tilt, 0.0
    else:
        gamma = max(rra, premium / variance)
        ratio = premium * premium / (2 * variance)
        annual_tilt = (bond_mu - rho + ratio) / gamma + ratio / (gamma * gamma) + additional_tilt
        weight = min(1.0, max(0.0, premium / variance / gamma))
    if annual_tilt <= -1:
        raise ValueError("Invalid Merton spending tilt")
    return weight, math.expm1(math.log1p(annual_tilt) / 12)


class TpawPolicy:
    def __init__(self, plan: PolicyPlan):
        self.plan = plan
        self.expected_stock = math.expm1(math.log1p(plan.stock_mu_annual) / 12)
        self.expected_bond = math.expm1(math.log1p(plan.bond_mu_annual) / 12)
        self.entries = self._precompute()
        self.references: list[Reference] = []
        wealth = plan.initial_balance
        for m in range(len(plan.end_by_month)):
            pre = self._pre(wealth, m, True)
            e = self.entries[m]
            total_stock = pre[4] * e.legacy_stock_fraction + (pre[3] + pre[5]) * e.stock_fraction
            elasticity = (total_stock / pre[0] if pre[0] else (e.legacy_stock_fraction + 2 * e.stock_fraction) / 3)
            self.references.append(Reference(pre[0], e.stock_fraction / elasticity if elasticity else 0,
                                             e.legacy_stock_fraction / elasticity if elasticity else 0))
            wealth = self.step(wealth, m, self.expected_stock, self.expected_bond, expected=True)["balance_end"]

    def _precompute(self) -> tuple[Entry, ...]:
        p = self.plan
        mertons = [merton(p.stock_mu_annual, p.bond_mu_annual, p.stock_annual_log_variance,
                          p.time_preference, p.additional_spending_tilt, gamma) for gamma in p.rra]
        legacy_weight = merton(p.stock_mu_annual, p.bond_mu_annual, p.stock_annual_log_variance,
                                p.time_preference, p.additional_spending_tilt, p.legacy_rra)[0]
        entries = [None]*len(p.end_by_month)
        grouped={}
        for m,end in enumerate(p.end_by_month):grouped.setdefault(end,[]).append(m)
        legacy_gross = 1 + self.expected_bond + (self.expected_stock - self.expected_bond) * legacy_weight
        for end,months in grouped.items():
            targets=set(months)
            income = essential = discretionary = denominator = 0.0
            for future in range(end - 1, months[0] - 1, -1):
                weight, tilt = mertons[future]
                portfolio_gross = 1 + self.expected_bond + (self.expected_stock - self.expected_bond) * weight
                income = income / (1 + self.expected_bond) + p.income[future]
                essential = essential / (1 + self.expected_bond) + p.essential[future]
                discretionary = discretionary / portfolio_gross + p.discretionary[future]
                denominator = denominator * (1 + tilt) / portfolio_gross + 1
                if future in targets:
                    m=future
                    entries[m]=Entry(income-p.income[m],essential-p.essential[m],discretionary-p.discretionary[m],
                        p.legacy/legacy_gross**(end-m),weight,legacy_weight,denominator,tilt)
        return tuple(entries)

    def _pre(self, balance: float, m: int, expected: bool):
        p, e = self.plan, self.entries[m]
        wealth = balance + e.income_npv + p.income[m]
        sd = sl = 1.0
        if not expected:
            reference = self.references[m]
            change = wealth / reference.wealth - 1 if reference.wealth else 0.0
            sd = max(0.0, 1 + change * reference.discretionary_elasticity)
            sl = max(0.0, 1 + change * reference.legacy_elasticity)
        available = max(0.0, wealth - e.essential_npv - p.essential[m])
        discretionary = min(available, (e.discretionary_npv + p.discretionary[m]) * sd)
        available -= discretionary
        legacy = min(available, e.legacy_npv * sl)
        return wealth, sd, sl, discretionary, legacy, available - legacy

    def step(self, balance: float, m: int, stock_return: float = 0, bond_return: float = 0, *,
             expected: bool = False, force_retired: bool = False) -> dict:
        """Start-of-month decision, contributions/withdrawals, then month return."""
        finite(balance, "balance", 0)
        if not 0 <= m < len(self.entries):
            raise ValueError("Month outside policy evaluation")
        for r in (stock_return, bond_return):
            if finite(r, "monthly return") < -1:
                raise ValueError("Monthly return below -100%")
        p, e = self.plan, self.entries[m]
        wealth, sd, sl, _, _, general_npv = self._pre(balance, m, expected)
        retired = force_retired or m >= p.retirement_month
        target_general = general_npv / e.denominator if retired else 0.0
        target_discretionary = p.discretionary[m] * sd
        if p.ceiling is not None:
            target_general = min(target_general, p.ceiling)
            target_discretionary = min(target_discretionary, p.discretionary[m])
        if p.floor is not None:
            if retired:
                target_general = max(target_general, p.floor)
            target_discretionary = max(target_discretionary, p.discretionary[m])
        available = balance + p.income[m]
        essential = min(available, p.essential[m]); available -= essential
        discretionary = min(available, target_discretionary); available -= discretionary
        general = min(available, target_general); available -= general
        # Native allocation protects remaining essential goals before risky goals.
        account = max(available, .00001) + e.income_npv
        account = max(0.0, account - e.essential_npv)
        d = min(account, e.discretionary_npv * sd); account -= d
        legacy = min(account, e.legacy_npv * sl); account -= legacy
        stock_amount = legacy * e.legacy_stock_fraction + (d + account) * e.stock_fraction
        fraction = min(1.0, max(0.0, stock_amount / max(available, .00001)))
        ending = available * (fraction * (1 + stock_return) + (1 - fraction) * (1 + bond_return))
        return {"balance_start": balance, "income": p.income[m], "essential": essential,
                "discretionary": discretionary, "general": general, "total": essential + discretionary + general,
                "balance_after_spending": available, "stock_fraction": fraction, "balance_end": ending,
                "unfunded_essential": max(0.0, p.essential[m] - essential),
                "target_general": target_general,"target_discretionary":target_discretionary,
                "unfunded_target": max(0.0, p.essential[m] + target_discretionary + target_general - essential - discretionary - general)}
