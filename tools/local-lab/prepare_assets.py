"""Join frozen official ETF, ChinaBond and BOC observations on actual months.

Writes fresh dataset identifiers. No source download or extrapolation occurs.
"""
import argparse
from dataclasses import asdict,replace
import hashlib
import json
import math
from pathlib import Path
import statistics
from tpaw_lab.deposits import at_month_end,parse_posted
from tpaw_lab.market import JointHistory,Observation,month_index,return_statistics
from tpaw_lab.storage import Store
from tpaw_lab.yields import monthly_curves,parse_chinabond


def issuer_returns(path:Path,port:str)->dict[str,float]:
    data=json.loads(path.read_text(encoding="utf-8"))
    if data["portId"]!=port or data["currencyCode"]!="USD" or data["benchmark"]!="FTSE All-World Index":
        raise ValueError("Wrong issuer return identity or currency")
    result={}
    for row in data["fundData"]["annualNAVReturns"]["returns"]:
        month=row["asOfDate"][:7]
        if month in result: raise ValueError("Duplicate ETF month")
        result[month]=1+float(row["monthPercent"])/100
    keys=sorted(result)
    if any(month_index(b)!=month_index(a)+1 for a,b in zip(keys,keys[1:])):
        raise ValueError("ETF monthly observations have gaps")
    if min(result.values())<=0: raise ValueError("Invalid ETF gross factor")
    return dict(sorted(result.items()))


def compare_returns(a:dict,b:dict)->dict:
    months=sorted(set(a)&set(b))
    x=[a[m]-1 for m in months]; y=[b[m]-1 for m in months]
    d=[math.log(a[m]/b[m]) for m in months]
    return {"months":len(months),"start":months[0],"end":months[-1],
            "a":return_statistics([a[m] for m in months]),"b":return_statistics([b[m] for m in months]),
            "monthly_simple_correlation":statistics.correlation(x,y),
            "annualized_log_return_difference_a_minus_b":12*statistics.mean(d),
            "monthly_log_difference_std_times_sqrt12":statistics.stdev(d)*math.sqrt(12),
            "max_absolute_monthly_simple_difference":max(abs(v-w) for v,w in zip(x,y))}


def prior_month(month):
    i=month_index(month)-1
    return f"{i//12:04}-{i%12+1:02}"


def prepare(root:Path,store:Store):
    original=store.get("data","developed-cny-proxy")
    raw=original["history"]
    rows=tuple(Observation(**r) for r in raw["rows"])
    french={r.month:r.global_equity_usd_gross for r in rows}
    files={}
    def pinned(path):
        files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text(encoding="utf-8")
    vwrl_path=root/"vanguard-official-02/vwrl.json"
    vwra_path=root/"vanguard-official-01/vwra.json"
    pinned(vwrl_path);pinned(vwra_path)
    vwrl=issuer_returns(vwrl_path,"9505");vwra=issuer_returns(vwra_path,"9679")
    # Official factsheet, page2, as of30Sep2026. These are Oct-Sep windows,
    # net-expense fund returns and the stated FTSE total-return benchmark.
    pdf=root/"vanguard-factsheet-01/vwrl-factsheet.pdf"
    files[str(pdf.relative_to(root))]=hashlib.sha256(pdf.read_bytes()).hexdigest()
    fund=[18.71,9.60,1.30,10.32,27.34,-20.59,20.90,31.47,17.32,16.71]
    benchmark=[18.68,9.67,1.30,10.31,27.41,-20.59,20.89,31.56,17.32,16.66]
    annual=[]
    for year,f,b in zip(range(2017,2027),fund,benchmark):
        months=[f"{i//12:04}-{i%12+1:02}" for i in range((year-1)*12+9,year*12+9)]
        computed=math.prod(vwrl[m] for m in months)-1
        if abs(computed-f/100)>.000051:
            raise ValueError("ETF monthly compounding disagrees with official factsheet rounding")
        annual.append({"start":months[0],"end":months[-1],"fund":computed,"benchmark":b/100,
                       "developed_proxy":math.prod(french[m] for m in months)-1 if all(m in french for m in months) else None})
    # Use the full pinned French series for exact official factsheet windows,
    # even when the CPI-joined pack ends earlier.
    from prepare_sources import french_market
    french_full=french_market(root/"public-sources-01/developed_factors.zip")
    for case in annual:
        months=[m for m in french_full if case["start"]<=m<=case["end"]]
        if len(months)!=12: raise ValueError("Incomplete French factsheet overlap window")
        case["developed_proxy"]=math.prod(french_full[m] for m in months)-1
    report={"name":"Official ETF and developed-market proxy overlap",
            "monthly_proxy_minus_vwrl":compare_returns(french_full,vwrl),
            "monthly_vwra_minus_vwrl":compare_returns(vwra,vwrl),
            "ftse_annual_oct_sep_windows":annual,
            "ftse_annual_log_difference_proxy_minus_index":statistics.mean(math.log((1+r["developed_proxy"])/(1+r["benchmark"])) for r in annual),
            "limits":["French developed total market excludes emerging markets; FTSE All-World includes developed/emerging large and mid caps.",
                      "ETF monthly NAV total returns reinvest income and already include fund expenses. No extra fee or dividend is applied.",
                      "Pre2012 proxy returns have no fund fee deduction; the hybrid has an explicit method/cost change in Jun2012.",
                      "Issuer FTSE benchmark is available here only in10 disjoint annual Oct-Sep windows. No full monthly FTSE index was obtained.",
                      "VWRA/VWRP accumulating and VWRL distributing share-class total returns can differ slightly; monthly NAV USD factors are used, not GBP market prices."]}
    daily={}
    paths=[root/"asset-discovery-02/chinabond-2006.html",root/"public-assets-01/chinabond-2024.html",*sorted((root/"chinabond-history-01").glob("chinabond-*.html"))]
    for path in paths:
        year=int(path.stem[-4:]);text=pinned(path)
        curve=parse_chinabond(text,f"{year}-01-01",f"{year}-12-31")
        if set(daily)&set(curve): raise ValueError("Duplicate official yield date")
        daily.update(curve)
    monthly=monthly_curves(daily)
    quotes={}
    for path in sorted((root/"boc-history-01").glob("deposit-*.html")):
        date=path.stem.removeprefix("deposit-")
        quotes[date]=parse_posted(pinned(path),date)
    hybrids=tuple(replace(r,global_equity_usd_gross=vwrl.get(r.month,r.global_equity_usd_gross),
                         source="French developed proxy before2012Jun; official USD VWRL NAV total return thereafter; Fed FX, OECD/BLS CPI") for r in rows)
    joint=[]; quote_dates={}
    for row in hybrids:
        prev=prior_month(row.month)
        if row.month not in monthly or prev not in monthly: continue
        before=at_month_end(quotes,prev);after=at_month_end(quotes,row.month)
        joint.append(replace(row,government_yield_annual=monthly[row.month]["curve"]["60"],deposit_rate_annual=after["curve"]["60"],
                             government_curve_before=monthly[prev]["curve"],government_curve=monthly[row.month]["curve"],
                             deposit_curve_before=before["curve"],deposit_curve=after["curve"],
                             demand_rate_before=before["demand"],demand_rate=after["demand"],
                             source=row.source+" + official ChinaBond nominal YTM curve + BOC posted retail deposit curve"))
        quote_dates[row.month]={"government":monthly[row.month]["date"],"deposit":after["date"],"demand":after["demand_quote_date"]}
    sources=tuple(raw["sources"])+("https://www.vanguardinvestor.co.uk/api/funds/vanguard-ftse-all-world-ucits-etf-usd-distributing",
             "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery","https://www.boc.cn/fimarkets/lilv/fd31/")
    limits=tuple(report["limits"])+("China CPI ends Apr2025. The shorter joint pack starts Apr2006 because observed government curves begin Mar2006; no earlier government curves are fabricated.",
            "ChinaBond published nominal YTM curves are interpolated by remaining maturity, not bootstrapped spot curves or actual individual issue returns. Fees, settlement and default are not modeled.",
            "BOC posted rates are a single-bank proxy, not actual negotiated deposit contracts. Quotes carry forward until the next dated posting; omitted demand rows retain the last separately published demand quote.",
            "Monthly rate changes are jointly sampled with equity/FX/CPI. At block boundaries changes are applied to the current curve; a zero floor and optional persistence are explicit scenario assumptions. Long-horizon rate regimes require sensitivity.",
            "Original1993-2025 equity/FX/CPI history remains available separately with constant defensive-rate assumptions.")
    history=JointHistory(tuple(joint),"observed","全球股票代理/ETF · 人民币 · 真实国债与挂牌存款变化",sources,limits)
    factors={"global_usd_log":[math.log(r.global_equity_usd_gross) for r in joint],
             "us_usd_log":[math.log(r.us_equity_usd_gross) for r in joint],
             "fx_log":[math.log(r.cny_per_usd_gross) for r in joint],
             "china_cpi_log":[math.log(r.china_cpi_gross) for r in joint],
             "us_cpi_log":[math.log(r.us_cpi_gross) for r in joint],
             "government5y_change":[r.government_curve["60"]-r.government_curve_before["60"] for r in joint],
             "deposit5y_change":[r.deposit_curve["60"]-r.deposit_curve_before["60"] for r in joint],
             "demand_change":[r.demand_rate-r.demand_rate_before for r in joint]}
    corr={a:{b:statistics.correlation(x,y) if statistics.pstdev(x)*statistics.pstdev(y)>0 else None for b,y in factors.items()} for a,x in factors.items()}
    audit={"files":{**original["audit"]["files"],**files},"joined_months":len(joint),"joined_start":joint[0].month,"joined_end":joint[-1].month,
           "government_daily_curves":len(daily),"deposit_quote_count":len(quotes),"source_quote_dates":quote_dates,
           "monthly_factor_correlation":corr,"return_statistics":return_statistics([r.equity_gross("global","cny") for r in joint]),
           "proxy_comparison":report,"rate_history_is_observed":True,"fees_applied_after_source":0}
    store.put("data",{"name":history.label,"history":asdict(history),"audit":audit},"global-cny-joint-official-v1")
    hybrid=JointHistory(hybrids,"observed","长观测股票/汇率/CPI · 全球代理/ETF · 防御利率需设定",sources,tuple(report["limits"])+tuple(raw["limitations"]))
    store.put("data",{"name":hybrid.label,"history":asdict(hybrid),"audit":{"files":audit["files"],"proxy_comparison":report,"rate_history_is_observed":False}},"global-cny-hybrid-v1")
    return {"joint_months":len(joint),"start":joint[0].month,"end":joint[-1].month,"curves":len(daily),"deposit_quotes":len(quotes),
            "monthly_proxy_vs_etf":report["monthly_proxy_minus_vwrl"],"annual_ftse_log_difference":report["ftse_annual_log_difference_proxy_minus_index"]}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",type=Path,required=True);p.add_argument("--data-dir",type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.root,Store(a.data_dir)),ensure_ascii=False,indent=2))
