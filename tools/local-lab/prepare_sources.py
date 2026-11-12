"""Validate frozen provider captures and build a bounded observed proxy dataset.

Defensive rates are explicitly scenario assumptions until a genuine joint yield
history is supplied. This stage does not claim a FTSE All-World replication.
"""
import argparse
import calendar
import csv
from dataclasses import asdict
import datetime as dt
from html.parser import HTMLParser
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
from tpaw_lab.longevity import parse_hk_api
from tpaw_lab.market import JointHistory, Observation, attribution, month_index
from tpaw_lab.storage import Store


class FredTable(HTMLParser):
    def __init__(self):
        super().__init__();self.active=False;self.cell=None;self.row=[];self.rows=[]

    def handle_starttag(self, tag, attrs):
        if tag=="table" and dict(attrs).get("id")=="data-table-observations":
            self.active=True
        if not self.active:
            return
        if tag=="tr":
            self.row=[]
        if tag in ("th","td"):
            self.cell=[]

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag in ("th","td") and self.cell is not None:
            self.row.append("".join(self.cell).strip());self.cell=None
        if tag=="tr" and self.row:
            self.rows.append(self.row)
        if tag=="table":
            self.active=False


def fred_html(path: Path, series: str) -> dict[str,float]:
    text=path.read_text(encoding="utf-8")
    if series not in text:
        raise ValueError("Wrong FRED series capture")
    parser=FredTable();parser.feed(text)
    result={}
    for row in parser.rows:
        if len(row)!=2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",row[0]):
            continue
        date,value=row
        if date in result:
            raise ValueError("Duplicate FRED date")
        if value in (".","", "ND"):
            continue
        number=float(value.replace(",",""))
        if number<=0:
            raise ValueError("Nonpositive source index/FX level")
        result[date]=number
    if not result:
        raise ValueError("No official FRED observations in capture")
    return result


def french_market(path: Path) -> dict[str,float]:
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=1 or archive.getinfo(names[0]).file_size>10*1024*1024:
            raise ValueError("Unexpected French archive structure")
        text=archive.read(names[0]).decode("utf-8-sig")
    result={};header=None
    for row in csv.reader(io.StringIO(text)):
        clean=[cell.strip() for cell in row]
        if len(clean)>2 and clean[1]=="Mkt-RF":
            header=clean;continue
        if not header or not clean or not re.fullmatch(r"\d{6}",clean[0]):
            continue  # annual rows have four digits; never mix their frequency
        if len(clean)!=len(header):
            raise ValueError("French column count mismatch")
        values=dict(zip(header,clean))
        market,rf=float(values["Mkt-RF"]),float(values["RF"])
        if market<=-99.99 or rf<=-99.99:
            raise ValueError("Missing French return sentinel")
        month=clean[0][:4]+"-"+clean[0][4:]
        if month in result:
            raise ValueError("Duplicate French monthly row")
        result[month]=1+(market+rf)/100
    if not result:
        raise ValueError("No French monthly market data")
    keys=list(result)
    if keys!=sorted(keys) or any(month_index(b)!=month_index(a)+1 for a,b in zip(keys,keys[1:])):
        raise ValueError("French monthly history not consecutive")
    return result


def build(raw: Path, html: Path) -> tuple[JointHistory,dict,dict]:
    global_equity=french_market(raw/"developed_factors.zip")
    us=french_market(raw/"us_factors.zip")
    china_daily=fred_html(html/"CHNCPIALLMINMEI.html","CHNCPIALLMINMEI")
    us_daily=fred_html(html/"CPIAUCNS.html","CPIAUCNS")
    fx_daily=fred_html(html/"DEXCHUS.html","DEXCHUS")
    china={d[:7]:v for d,v in china_daily.items()}
    us_cpi={d[:7]:v for d,v in us_daily.items()}
    fx={}
    for date,value in sorted(fx_daily.items()):
        if date[:7]<= "2026-10":
            fx[date[:7]]=(date,value)
    for month,(date,_) in fx.items():
        day=dt.date.fromisoformat(date)
        if calendar.monthrange(day.year,day.month)[1]-day.day>7:
            raise ValueError("Month-end FX stale by more than 7 days")
    common=sorted(set(global_equity)&set(us)&set(china)&set(us_cpi)&set(fx))
    rows=[]
    for month in common:
        prev=month_index(month)-1
        prior=f"{prev//12:04}-{prev%12+1:02}"
        if prior not in fx or prior not in china or prior not in us_cpi:
            continue
        rows.append(Observation(month,global_equity[month],us[month],fx[month][1]/fx[prior][1],
                                china[month]/china[prior],us_cpi[month]/us_cpi[prior],.02,.02,
                                "French developed/US total returns + Fed FX + OECD China CPI + BLS US CPI; nominal rates assumed 2%"))
    sources=("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5developed.html",
             "https://fred.stlouisfed.org/series/DEXCHUS", "https://fred.stlouisfed.org/series/CHNCPIALLMINMEI",
             "https://fred.stlouisfed.org/series/CPIAUCNS")
    limits=("Developed-market equity proxy includes dividends and capital gains, excludes emerging markets and differs from FTSE All-World. No fund fee is subtracted; no ETF NAV has been appended.",
            "US comparison is French broad US market, not S&P500; original native US benchmark remains separate.",
            "Equity, FX and CPI are observed. Deposit and bond yields are explicitly assumed flat 2%, NOT historical observed Chinese defensive returns. Yield-risk/correlation validation remains outstanding.",
            "CPI coverage is national, not personal consumption. OECD China series ends April 2025; no invented extension. FX uses last available daily noon NY quote, not NAV valuation time.",
            "Historical official-rate versus market-rate distortions and the 1994 exchange-rate unification require regime-specific sensitivity. No claim of fully investable pre-2003 global portfolio.")
    history=JointHistory(tuple(rows),"observed","发达市场代理 · 人民币实际收益 · 防御利率为显式假设",sources,limits)
    table=parse_hk_api(json.loads((raw/"hk_mortality.json").read_text(encoding="utf-8")))
    files=[raw/"developed_factors.zip",raw/"us_factors.zip",raw/"hk_mortality.json",*(html/f"{x}.html" for x in ("CHNCPIALLMINMEI","CPIAUCNS","DEXCHUS"))]
    audit={"files":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
           "source_coverage":{"developed_equity":[min(global_equity),max(global_equity)],"us_equity":[min(us),max(us)],
                              "china_cpi":[min(china),max(china)],"us_cpi":[min(us_cpi),max(us_cpi)],"fx":[min(fx),max(fx)]},
           "joined_months":len(rows),"joined_start":rows[0].month,"joined_end":rows[-1].month,
           "pre2003_months":sum(r.month<"2003-01" for r in rows),"rate_history_is_observed":False,
           "returns_attribution":attribution(history)}
    return history,{"rows":[table.rows[a] for a in sorted(table.rows)],"source":table.source},audit


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,required=True)
    parser.add_argument("--html",type=Path,required=True)
    parser.add_argument("--data-dir",type=Path,required=True)
    args=parser.parse_args()
    h,life,audit=build(args.raw,args.html)
    store=Store(args.data_dir)
    store.put("data",{"name":h.label,"history":asdict(h),"audit":audit},"developed-cny-proxy")
    store.put("data",life,"hk-male-period-2025")
    print(json.dumps({"joined_months":audit["joined_months"],"start":audit["joined_start"],
                      "end":audit["joined_end"],"pre2003_months":audit["pre2003_months"],
                      "defensive_rates":"Assumption only; joint historical yields not yet acquired"},ensure_ascii=False))
