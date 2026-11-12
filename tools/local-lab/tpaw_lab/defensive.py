"""Nominal CNY deposits and coupon government bonds, with explicit liquidity.

Illustrative contracts, not quotes or product recommendations. No default,
deposit insurance, taxes, bid/ask spreads or settlement delay are inferred.
All quantities here are nominal CNY; deflation occurs once in the caller.
"""
from dataclasses import dataclass, field
import math
from .market import finite
from .yields import curve_yield,YieldCurve


@dataclass
class Deposit:
    principal: float
    annual_rate: float
    term_months: int
    break_rate: float
    elapsed: int = 0

    def __post_init__(self):
        finite(self.principal, "deposit principal", 0)
        finite(self.annual_rate, "deposit rate", 0)
        finite(self.break_rate, "early withdrawal rate", 0)
        if type(self.term_months) is not int or self.term_months < 1 or not 0 <= self.elapsed <= self.term_months:
            raise ValueError("Invalid deposit maturity")
        if self.break_rate > self.annual_rate:
            raise ValueError("Early-break rate cannot exceed the contractual rate")

    @property
    def book_value(self) -> float:
        return self.principal * (1 + self.annual_rate * self.elapsed / 12)

    @property
    def liquidation_value(self) -> float:
        rate = self.annual_rate if self.elapsed == self.term_months else self.break_rate
        return self.principal * (1 + rate * self.elapsed / 12)

    def sell(self, cash_needed: float) -> tuple[float, float]:
        """Partial early withdrawal; retained principal keeps original contract.

        Returns cash and lost accrued contractual interest. This partial-break
        rule is an explicit scenario contract, not universal bank behavior.
        """
        finite(cash_needed, "cash needed", 0)
        value = self.liquidation_value
        fraction = min(1.0, cash_needed / value) if value else 0.0
        cash = value * fraction
        penalty = (self.book_value - value) * fraction
        self.principal *= 1 - fraction
        return cash, penalty


@dataclass
class GovernmentBond:
    face: float
    annual_coupon: float
    term_months: int
    elapsed: int = 0
    coupon_period_months: int = 12
    _price_key:tuple|None=field(default=None,init=False,repr=False,compare=False)
    _unit_price:float=field(default=0,init=False,repr=False,compare=False)

    def __post_init__(self):
        finite(self.face, "bond face", 0)
        finite(self.annual_coupon, "coupon", 0)
        if type(self.term_months) is not int or self.term_months < 12 or self.term_months % 12 or not 0 <= self.elapsed <= self.term_months:
            raise ValueError("Bonds require whole-year terms")
        if self.coupon_period_months not in (6,12):
            raise ValueError("Coupon period must be6 or12 months")

    def price(self, annual_yield: float) -> float:
        """Dirty nominal price after payments at the current month boundary."""
        y = finite(annual_yield, "bond yield")
        period=self.coupon_period_months
        base=1+y*period/12
        if base<=0:
            raise ValueError("Invalid periodic bond yield")
        if self.elapsed == self.term_months:
            return 0.0  # redemption was paid by advance()
        key=(y,self.elapsed,self.term_months,self.annual_coupon,period)
        if key==self._price_key:return self.face*self._unit_price
        coupon = self.annual_coupon * period/12
        coupons = sum(coupon / base ** ((m - self.elapsed) / period)
                      for m in range(period, self.term_months + 1, period) if m > self.elapsed)
        self._price_key=key
        self._unit_price=coupons+1/base**((self.term_months-self.elapsed)/period)
        return self.face*self._unit_price

    def advance(self) -> float:
        if self.elapsed >= self.term_months:
            raise ValueError("Matured bond advanced twice")
        self.elapsed += 1
        coupon = self.face * self.annual_coupon * self.coupon_period_months/12 if self.elapsed % self.coupon_period_months == 0 else 0.0
        return coupon + (self.face if self.elapsed == self.term_months else 0.0)

    def sell(self, cash_needed: float, annual_yield: float) -> float:
        finite(cash_needed, "cash needed", 0)
        value = self.price(annual_yield)
        fraction = min(1.0, cash_needed / value) if value else 0.0
        cash = value * fraction
        self.face *= 1 - fraction
        return cash


@dataclass
class DefensiveSleeve:
    cash: float
    kind: str = "deposit"
    term_months: int = 60
    known_deposit_rate: float = 0.02
    known_government_yield: float = 0.02
    demand_rate: float = 0.001
    deposits: list[Deposit] = field(default_factory=list)
    bonds: list[GovernmentBond] = field(default_factory=list)
    lost_accrued_interest: float = 0.0
    government_curve: dict[str,float] | None = None
    deposit_curve: dict[str,float] | None = None
    break_at_current_demand: bool = True
    _government_curve_source:dict|None=field(default=None,init=False,repr=False,compare=False)
    _government_curve_view:YieldCurve|None=field(default=None,init=False,repr=False,compare=False)

    def __post_init__(self):
        finite(self.cash, "cash", 0)
        if self.kind not in ("deposit", "government_bond", "cash"):
            raise ValueError("Unknown CNY defensive asset")
        if type(self.term_months) is not int or not 12 <= self.term_months <= 360 or self.term_months % 12:
            raise ValueError("Defensive term must be whole years, 1 to 30")
        finite(self.known_deposit_rate, "deposit rate", 0)
        finite(self.known_government_yield, "government yield", 0)
        finite(self.demand_rate, "demand rate", 0)
        if self.demand_rate > self.known_deposit_rate:
            raise ValueError("Demand rate must not exceed initial term-deposit rate")
        if self.government_curve:self.set_government_curve(self.government_curve)

    @property
    def value(self) -> float:
        return self.cash + sum(d.book_value for d in self.deposits) + sum(b.price(self.bond_yield(b)) for b in self.bonds)

    def bond_yield(self, bond: GovernmentBond) -> float:
        if not self.government_curve:return self.known_government_yield
        if self._government_curve_source is not self.government_curve:
            self._government_curve_view=YieldCurve(self.government_curve)
            self._government_curve_source=self.government_curve
        return self._government_curve_view.at(bond.term_months-bond.elapsed)

    def set_government_curve(self,curve:dict):
        """Own a new quote snapshot; callers never mutate a curve in place."""
        self.government_curve=dict(curve)
        self._government_curve_source=self.government_curve
        self._government_curve_view=YieldCurve(self.government_curve)

    def update_break_rates(self):
        if self.break_at_current_demand:
            for lot in self.deposits:
                lot.break_rate=self.demand_rate

    @property
    def liquidatable(self) -> float:
        self.update_break_rates()
        return self.cash + sum(d.liquidation_value for d in self.deposits) + sum(b.price(self.bond_yield(b)) for b in self.bonds)

    def release(self, amount: float, cash_floor:float=0) -> float:
        """Raise cash using existing cash, then oldest term lots; no borrowing."""
        finite(amount, "release amount", 0)
        finite(cash_floor,"protected cash",0)
        self.update_break_rates()
        missing = max(0.0, amount - max(0.,self.cash-cash_floor))
        for lot in self.deposits:
            if missing <= 1e-10:
                break
            proceeds, loss = lot.sell(missing)
            self.cash += proceeds
            self.lost_accrued_interest += loss
            missing -= proceeds
        for lot in self.bonds:
            if missing <= 1e-10:
                break
            proceeds = lot.sell(missing, self.bond_yield(lot))
            self.cash += proceeds
            missing -= proceeds
        paid = min(amount, max(0.,self.cash-cash_floor))
        self.cash = max(0.0, self.cash - paid)
        self.deposits = [lot for lot in self.deposits if lot.principal > 1e-10]
        self.bonds = [lot for lot in self.bonds if lot.face > 1e-10]
        return paid

    def invest_cash_above(self, floor: float) -> float:
        """Keep cash floor liquid; buy the selected contract at known start rates."""
        finite(floor, "cash floor", 0)
        amount = max(0.0, self.cash - floor)
        if amount == 0 or self.kind == "cash":
            return 0.0
        if self.kind == "deposit":
            rate=self.deposit_curve.get(str(self.term_months)) if self.deposit_curve else self.known_deposit_rate
            if rate is None: raise ValueError("Selected term is not an observed deposit product")
            self.deposits.append(Deposit(amount, rate, self.term_months,min(self.demand_rate,rate)))
        else:
            rate=curve_yield(self.government_curve,self.term_months) if self.government_curve else self.known_government_yield
            # Representative par contract: <=7y annual, >7y semiannual. This is
            # a maturity-bucket proxy, not reconstruction of actual bond issues.
            self.bonds.append(GovernmentBond(amount,rate,self.term_months,coupon_period_months=6 if self.term_months>84 else 12))
        self.cash -= amount
        return amount

    def advance(self, next_deposit_rate: float, next_government_yield: float,
                next_government_curve: dict | None = None, next_deposit_curve: dict | None = None,
                next_demand_rate: float | None = None):
        """Realize one month, then expose its closing rates for next month.

        New rates never change a prior deposit contract or a prior buy/sell price.
        Coupon/redemption cash is available at this month end, not month start.
        """
        finite(next_deposit_rate, "next deposit rate", 0)
        finite(next_government_yield, "next government yield", 0)
        self.cash *= (1 + self.demand_rate) ** (1 / 12)
        retained = []
        for lot in self.deposits:
            lot.elapsed += 1
            if lot.elapsed == lot.term_months:
                self.cash += lot.book_value
            else:
                retained.append(lot)
        self.deposits = retained
        retained_bonds = []
        for lot in self.bonds:
            self.cash += lot.advance()
            if lot.elapsed < lot.term_months:
                retained_bonds.append(lot)
        self.bonds = retained_bonds
        self.known_deposit_rate = next_deposit_rate
        self.known_government_yield = next_government_yield
        if next_government_curve is not None: self.set_government_curve(next_government_curve)
        if next_deposit_curve is not None: self.deposit_curve=next_deposit_curve
        if next_demand_rate is not None: self.demand_rate=finite(next_demand_rate,"next demand rate",0)


@dataclass
class PartitionedAssets:
    """One initial partition: reserve is never counted as spendable core cash."""
    equity: float
    defensive: DefensiveSleeve
    reserve_cash: float
    reserve_equity: float

    def __post_init__(self):
        for key in ("equity", "reserve_cash", "reserve_equity"):
            finite(getattr(self, key), key, 0)

    @property
    def core_value(self) -> float:
        return self.equity + self.defensive.value

    @property
    def total_value(self) -> float:
        return self.core_value + self.reserve_cash + self.reserve_equity

    def fund_reserve(self,amount:float)->dict:
        """Partition existing core wealth once, half to each reserve sleeve."""
        finite(amount,"reserve funding",0)
        cash=self.defensive.release(amount)
        sale=min(self.equity,max(0.,amount-cash));self.equity-=sale
        funded=cash+sale
        self.reserve_cash+=funded/2;self.reserve_equity+=funded/2
        return {"target":amount,"funded":funded,"shortfall":max(0.,amount-funded)}

    def rebalance_equity(self,fraction:float,cash_target:float)->dict:
        """Protect current cash up to its target, investing excess cash normally."""
        if not 0<=finite(fraction,"stock fraction")<=1:raise ValueError("Stock fraction outside0..1")
        protected=min(self.defensive.cash,finite(cash_target,"cash target",0))
        desired=min(fraction*self.core_value,max(0.,self.core_value-protected))
        bought=sold=0.
        if desired<self.equity:
            sold=self.equity-desired;self.equity-=sold;self.defensive.cash+=sold
        else:
            bought=self.defensive.release(desired-self.equity,protected);self.equity+=bought
        return {"equity_bought":bought,"equity_sold":sold,"protected_cash":protected,
                "actual_stock_fraction":self.equity/self.core_value if self.core_value else 0.}

    def replenish_cash(self, annual_spending: float, multiple: float = 1.5, trigger_fraction: float = 1.0) -> dict:
        """At month start, top up after cash drops below trigger * target.

        Use defensive maturities/cash first, sell oldest defensive lots next,
        then sell global equity. The reserve is excluded. This transfer creates
        no consumption. Report an unfunded target instead of inventing money.
        """
        finite(annual_spending, "annual spending", 0)
        finite(multiple, "cash-floor multiple", 0)
        if not 0 <= finite(trigger_fraction, "trigger fraction") <= 1:
            raise ValueError("Trigger fraction must lie in [0,1]")
        target = annual_spending * multiple
        before = self.defensive.cash
        if before + 1e-10 >= target * trigger_fraction:
            return {"target": target, "triggered": False, "cash": before,
                    "shortfall": max(0.0, target - before), "equity_sold": 0.0, "break_interest_lost": 0.0}
        loss_before = self.defensive.lost_accrued_interest
        # release() temporarily removes all raised cash; add it back once.
        raised = self.defensive.release(target)
        self.defensive.cash += raised
        equity_sold = min(self.equity, max(0.0, target - self.defensive.cash))
        self.equity -= equity_sold
        self.defensive.cash += equity_sold
        return {"target": target, "triggered": True, "cash": self.defensive.cash,
                "shortfall": max(0.0, target - self.defensive.cash), "equity_sold": equity_sold,
                "break_interest_lost": self.defensive.lost_accrued_interest - loss_before}

    def reserve_withdrawal(self, amount: float) -> dict:
        """Equal amounts from reserve sleeves. Report shortage; no core raid."""
        finite(amount, "reserve withdrawal", 0)
        half = amount / 2
        from_cash = from_equity = min(half,self.reserve_cash,self.reserve_equity)
        self.reserve_cash -= from_cash
        self.reserve_equity -= from_equity
        return {"requested": amount, "paid": from_cash + from_equity,
                "shortfall": max(0.0, amount - from_cash - from_equity),
                "cash_paid": from_cash, "equity_paid": from_equity}
