"""Frozen official period mortality; no invented death beyond the open interval."""
import math
from .market import finite


class LifeTable:
    def __init__(self, rows: list[dict], source: dict):
        self.rows = {r["age"]: r for r in rows}
        self.source = source
        if len(rows) != 101 or set(self.rows) != set(range(101)):
            raise ValueError("Official ages 0..99 and open age 100 required")
        for age, row in self.rows.items():
            if finite(row["lx"], "survivors") <= 0 or finite(row["ex"], "remaining life expectancy") < 0:
                raise ValueError("Invalid mortality row")
            if age and row["lx"] > self.rows[age-1]["lx"]:
                raise ValueError("Survivors increase with age")

    def survivors(self, age: float) -> float:
        if not 0 <= finite(age, "age") <= 100:
            raise ValueError("Open-age tail cannot be interpolated")
        lower = math.floor(age)
        if lower == 100:
            return self.rows[100]["lx"]
        return self.rows[lower]["lx"] * (1 - (age-lower)) + self.rows[lower+1]["lx"] * (age-lower)

    def schedule(self, current_age_months: int, mode: str, margin_years: float = 5) -> tuple[int, ...]:
        if type(current_age_months) is not int or not 0 <= current_age_months < 1200:
            raise ValueError("Invalid current age")
        if not 0 <= finite(margin_years, "safety years") <= 30:
            raise ValueError("Safety years outside 0..30")
        months = 1200 - current_age_months
        if mode in ("fixed90", "fixed95", "fixed100"):
            end = int(mode[5:]) * 12 - current_age_months + 1
            return tuple(max(m + 1, end) for m in range(months))
        if mode != "rolling":
            raise ValueError("Unknown horizon rule")
        ends = []
        for m in range(months):
            attained = (current_age_months + m) // 12
            end = round(12 * (attained + self.rows[attained]["ex"] + margin_years)) - current_age_months + 1
            if end <= m:
                raise ValueError("Rolling horizon expired")
            ends.append(end)
        return tuple(ends)

    def weights(self, age_months: int, months: int) -> dict:
        if age_months + months > 1200:
            raise ValueError("Mortality evaluation extends past open age 100")
        base = self.survivors(age_months/12)
        survival = [self.survivors((age_months+m)/12)/base for m in range(months+1)]
        death = [survival[m]-survival[m+1] for m in range(months)]
        if abs(sum(death) + survival[-1] - 1) > 1e-10:
            raise ArithmeticError("Mortality mass lost")
        return {"alive_start": survival[:-1], "death_end": death, "tail_alive": survival[-1]}


def parse_hk_api(raw: dict) -> LifeTable:
    if raw.get("header", {}).get("status", {}).get("code") != 0:
        raise ValueError("Official mortality request failed")
    fields = {"QX": "qx", "LX": "lx", "EX": "ex", "TX": "tx", "LLX": "person_years"}
    rows: dict[int, dict] = {}
    records = raw["dataSet"]
    if len(records) != 505:
        raise ValueError("Official mortality response incomplete")
    for record in records:
        if record["SEX"] != "M" or int(record["period"]) != 2025:
            raise ValueError("Unexpected mortality population or year")
        age = {"zero": 0, "100_and_over": 100}.get(record["AGE"])
        if age is None:
            age = int(record["AGE"])
        field = fields[record["sv"]]
        row = rows.setdefault(age, {"age": age})
        if field in row:
            raise ValueError("Duplicate mortality observation")
        row[field] = float(record["figure"])
    return LifeTable([rows[a] for a in sorted(rows)], {"agency": "Hong Kong Census and Statistics Department",
                       "url": "https://www.censtatd.gov.hk/en/web_table.html?id=115-01021",
                       "sex": "male", "period_year": 2025, "open_age": 100,
                       "limitation": "Period table, no cohort improvement. q(100)=1 describes an open interval, not death within a year."})
