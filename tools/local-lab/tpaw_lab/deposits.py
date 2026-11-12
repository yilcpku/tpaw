"""Bank of China posted retail deposit curves; not executed product quotes."""
from html.parser import HTMLParser
import re
from urllib.parse import urljoin
from .market import finite

TENORS = {"三个月":3, "半年":6, "六个月":6, "一年":12, "二年":24, "两年":24, "三年":36, "五年":60}


class Table(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None

    def handle_starttag(self, tag, attrs):
        if tag=="tr": self.row=[]
        if tag in ("td","th"): self.cell=[]

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append(re.sub(r"\s+", "", "".join(self.cell))); self.cell=None
        if tag=="tr" and self.row: self.rows.append(self.row)


def index_links(text: str) -> dict[str,str]:
    links=re.findall(r'<a[^>]*href="([^"]+)"[^>]*>人民币存款利率表(\d{4}-\d{2}-\d{2})</a>',text)
    if not links: raise ValueError("No official dated deposit links")
    return {date:urljoin("https://www.boc.cn/fimarkets/lilv/fd31/",url) for url,date in links}


def parse_posted(text: str, date: str) -> dict:
    if date not in text: raise ValueError("Deposit effective date absent from page")
    parser=Table(); parser.feed(text)
    active=False; curve={}; demand=None
    for row in parser.rows:
        if len(row)!=2: continue
        label,value=row
        if "活期" in label and demand is None and re.fullmatch(r"\d+(?:\.\d+)?",value):
            demand=float(value)/100
        if "整存整取" in label and not active and not curve:
            active=True; continue
        if active and label in TENORS:
            term=str(TENORS[label])
            if term in curve: raise ValueError("Duplicate deposit tenor")
            curve[term]=finite(float(value)/100,"posted deposit rate",0)
        elif active and curve: break
    if set(curve)!={"3","6","12","24","36","60"}:
        raise ValueError("Incomplete posted lump-sum deposit curve")
    if any(rate>.5 or (demand is not None and rate<demand) for rate in curve.values()):
        raise ValueError("Deposit percentage unit or product scope mismatch")
    return {"date":date,"curve":curve,"demand":demand}


def at_month_end(quotes: dict[str,dict], month: str) -> dict:
    available=[date for date in quotes if date[:7]<=month]
    if not available: raise ValueError("No earlier official posted deposit quote")
    selected=quotes[max(available)]
    demand_dates=[date for date in available if quotes[date]["demand"] is not None]
    if not demand_dates: raise ValueError("No earlier published demand-rate observation")
    anchor=max(demand_dates)
    return {**selected,"demand":quotes[anchor]["demand"],"demand_quote_date":anchor}
