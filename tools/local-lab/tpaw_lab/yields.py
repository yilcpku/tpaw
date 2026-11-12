"""Official ChinaBond yield-curve parsing and explicit term interpolation."""
import calendar
import datetime as dt
from html.parser import HTMLParser
import math
from .market import finite, month_index

TENORS=(3,6,12,36,60,84,120,360)


class ChinaBondTable(HTMLParser):
    def __init__(self):
        super().__init__();self.active=False;self.cell=None;self.row=[];self.rows=[];self.depth=0

    def handle_starttag(self,tag,attrs):
        if tag=="div" and dict(attrs).get("id")=="gjqxData":
            self.active=True;self.depth=1
        elif tag=="div" and self.active:
            self.depth+=1
        if not self.active:return
        if tag=="tr":self.row=[]
        if tag in ("td","th"):self.cell=[]

    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)

    def handle_endtag(self,tag):
        if not self.active:return
        if tag in ("td","th") and self.cell is not None:
            self.row.append("".join(self.cell).strip().replace("\xa0",""));self.cell=None
        if tag=="tr" and self.row:self.rows.append(self.row)
        if tag=="div":
            self.depth-=1
            if self.depth==0:self.active=False


def parse_chinabond(text:str, start:str, end:str)->dict[str,dict[str,float]]:
    parser=ChinaBondTable();parser.feed(text)
    result={}
    for row in parser.rows:
        if not row or row[0]!="中债国债收益率曲线":continue
        if len(row)!=10:raise ValueError("Official government curve column count changed")
        date=dt.date.fromisoformat(row[1]).isoformat()
        if not start<=date<=end:raise ValueError("Official yield response outside requested interval")
        if date in result:raise ValueError("Duplicate government curve date")
        curve={str(term):finite(float(value)/100,"official yield",0) for term,value in zip(TENORS,row[2:])}
        if any(value>.5 for value in curve.values()):raise ValueError("Yield percentage/decimal unit mismatch")
        result[date]=curve
    if not result:raise ValueError("No official government yield curves in response")
    return dict(sorted(result.items()))


def monthly_curves(daily:dict[str,dict[str,float]])->dict[str,dict]:
    result={}
    for date,curve in sorted(daily.items()):
        d=dt.date.fromisoformat(date)
        result[date[:7]]={"date":date,"curve":curve,"month_end_lag_days":calendar.monthrange(d.year,d.month)[1]-d.day}
    if any(r["month_end_lag_days"]>14 for r in result.values()):
        raise ValueError("Government month-end yield stale by more than14days")
    return result


class YieldCurve:
    """Owned immutable curve points with cached remaining-maturity quotes."""
    def __init__(self,curve:dict[str,float]):
        if not curve:raise ValueError("Empty curve")
        self.points=tuple(sorted((float(term),finite(rate,"curve yield",0)) for term,rate in curve.items()))
        if any(term<=0 for term,_ in self.points):raise ValueError("Positive month tenors required")
        self._cache={}

    def at(self,remaining_months:float)->float:
        if not math.isfinite(remaining_months) or remaining_months<0:raise ValueError("Invalid maturity")
        if remaining_months in self._cache:return self._cache[remaining_months]
        items=self.points
        value=items[-1][1]
        if remaining_months<=items[0][0]:value=items[0][1]
        else:
            for (a,ya),(b,yb) in zip(items,items[1:]):
                if remaining_months==b:value=yb;break
                if remaining_months<b:
                    value=min(max(ya,yb),max(min(ya,yb),ya+(yb-ya)*((remaining_months-a)/(b-a))))
                    break
        self._cache[remaining_months]=value
        return value


def curve_yield(curve:dict[str,float],remaining_months:float)->float:
    """Linear interpolation in remaining maturity; flat endpoint extrapolation.

    These are YTM curves, not spot zero curves. An annual-coupon bond is valued
    at the interpolated YTM for its remaining term, an explicit pricing proxy.
    """
    return YieldCurve(curve).at(remaining_months)


def apply_observed_change(known:dict[str,float], source_before:dict[str,float], source_after:dict[str,float], persistence:float=1)->tuple[dict[str,float],int]:
    """Carry observed joint curve shocks onto the currently known yield state.

    persistence1 gives observed month-to-month absolute yield changes; lower
    persistence adds an explicit pull toward the sampled historical level.
    No future source level is consulted until the monthly market move occurs.
    """
    if not 0<=finite(persistence,"yield persistence")<=1:raise ValueError("Yield persistence outside0..1")
    if set(known)!=set(source_before) or set(known)!=set(source_after):raise ValueError("Curve tenor sets differ")
    result={};clamps=0
    for tenor in known:
        rate=source_after[tenor]+persistence*(known[tenor]-source_before[tenor])
        clamps+=int(rate<0)
        result[tenor]=max(0,rate)
    return result,clamps
