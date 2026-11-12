"""Explicit public-data acquisition; runtime simulator itself never fetches.

Fresh directories only. Raw bytes and hashes stay in the configured private root.
Sources are official provider exports; no credentials or user plan is transmitted.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
from tpaw_lab.storage import private_root

SOURCES = {
    "developed_factors.zip": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_5_Factors_CSV.zip",
    "us_factors.zip": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip",
    "DEXCHUS.csv": "https://fred.stlouisfed.org/graph.csv?id=DEXCHUS&cosd=1989-01-01&coed=2026-10-31",
    "CHNCPIALLMINMEI.csv": "https://fred.stlouisfed.org/graph.csv?id=CHNCPIALLMINMEI&cosd=1989-01-01&coed=2026-10-31",
    "CPIAUCNS.csv": "https://fred.stlouisfed.org/graph.csv?id=CPIAUCNS&cosd=1989-01-01&coed=2026-10-31",
}


def fetch_one(dest: Path, filename: str, url: str, data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "TPAW-local-research/0.1"})
    with urllib.request.urlopen(req, timeout=45) as response:
        body = response.read(40 * 1024 * 1024 + 1)
        if not body or len(body) > 40 * 1024 * 1024:
            raise ValueError("Public response size invalid")
        with (dest / filename).open("xb") as handle:
            handle.write(body)
        return {"filename": filename, "url": url, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(), "content_type": response.headers.get("Content-Type"),
                "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "data_date_must_be_checked_by_parser": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, required=True)
    a = p.parse_args()
    if a.destination.exists():
        raise ValueError("Use a new immutable public-data snapshot directory")
    dest = private_root(a.destination)
    rows, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_one, dest, name, url): name for name, url in SOURCES.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                rows.append(future.result())
                print(name, "saved")
            except Exception as error:
                failures.append({"filename": name, "error": type(error).__name__, "message": str(error)})
                print(name, type(error).__name__)
    query = {"id": "115-01021", "lang": "en", "period": {"start": "2025", "end": "2025"},
             "cv": {"SEX": ["M"], "AGE": ["zero"] + [str(x) for x in range(1, 100)] + ["100_and_over"]},
             "sv": {"QX": ["Raw_8dp_idx_n"], "LX": ["Raw_idx_n"], "EX": ["Raw_2dp_idx_n"],
                    "TX": ["Raw_idx_n"], "LLX": ["Raw_idx_n"]}}
    try:
        rows.append(fetch_one(dest, "hk_mortality.json", "https://www.censtatd.gov.hk/api/post.php",
                               urllib.parse.urlencode({"query": json.dumps(query)}).encode()))
    except Exception as error:
        failures.append({"filename": "hk_mortality.json", "error": type(error).__name__, "message": str(error)})
    (dest / "manifest.json").write_text(json.dumps({"files": rows, "failures": failures}, indent=2), encoding="utf-8")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
