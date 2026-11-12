"""Public-only Treasury/FRED fixture builder; no plan inputs or credentials.

Retain downloaded SP500 data privately: its FRED notes restrict redistribution.
This is a new empirical fixture, never a claim to recover a website snapshot.
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
import urllib.request
from zoneinfo import ZoneInfo
from research import digest, private_destination, write_private

BONDS = [('five_year', '5 YR'), ('seven_year', '7 YR'), ('ten_year', '10 YR'),
         ('twenty_year', '20 YR'), ('thirty_year', '30 YR')]


def normalize(sp_csv, inflation_csv, treasury_csv):
    def fred(text, key):
        return {x['observation_date']: float(x[key]) for x in csv.DictReader(io.StringIO(text))
                if x[key] not in ('', '.')}
    stocks, inflation = fred(sp_csv, 'SP500'), fred(inflation_csv, 'T10YIE')
    bonds = {dt.datetime.strptime(x['Date'], '%m/%d/%Y').date().isoformat(): x
             for x in csv.DictReader(io.StringIO(treasury_csv)) if all(x[k] for _, k in BONDS)}
    dates = sorted(set(stocks) & set(inflation) & set(bonds))
    if not dates:
        raise ValueError('No complete common observation dates')
    rows = []
    for date in dates:
        close = int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(16),
                                       ZoneInfo('America/New_York')).timestamp() * 1000)
        rates = {k: float(bonds[date][col]) / 100 for k, col in BONDS}
        values = [stocks[date], inflation[date], *rates.values()]
        if any(not math.isfinite(x) for x in values) or stocks[date] <= 0:
            raise ValueError('Invalid public observation')
        rows.append({'closing_time_ms': close,
                     'sp500': {'closing_time_ms': close, 'value': stocks[date]},
                     'inflation': {'closing_time_ms': close, 'value': inflation[date] / 100},
                     'bond_rates': {'closing_time_ms': close, **rates}})
    return rows, dates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--end', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--raw-directory', type=Path, help='Reuse previously downloaded raw CSVs; no network')
    args = parser.parse_args()
    if args.start.year != args.end.year or args.end < args.start:
        raise ValueError('Use one ordered calendar year per snapshot')
    root = private_destination(args.output)
    if root.exists():
        raise ValueError('Use a fresh output directory')
    sources = {
        'treasury.csv': f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{args.start.year}/all?type=daily_treasury_real_yield_curve',
        'sp500.csv': f'https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500&cosd={args.start}&coed={args.end}',
        'inflation.csv': f'https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE&cosd={args.start}&coed={args.end}'}
    root.mkdir(parents=True)
    records = []
    for name, url in sources.items():
        if args.raw_directory:
            data = (args.raw_directory / name).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read()
        if b'<' in data[:100]:
            raise ValueError('Expected public CSV')
        with (root / name).open('xb') as stream:
            stream.write(data)
        records.append({'name': name, 'url': url, 'sha256': digest(root / name)})
    rows, dates = normalize(*(root.joinpath(n).read_text(encoding='utf-8-sig')
                             for n in ['sp500.csv', 'inflation.csv', 'treasury.csv']))
    selected = [(row, date) for row, date in zip(rows, dates) if str(args.start) <= date <= str(args.end)]
    if not selected:
        raise ValueError('No common dates inside requested range')
    write_private(root / 'presets.json', [r for r, _ in selected])
    write_private(root / 'manifest.json', {'type': 'empirical_public_source_fixture_not_website_snapshot',
        'retrieved_or_imported_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'sources': records,
        'common_observation_dates': [d for _, d in selected], 'presets_sha256': digest(root / 'presets.json'),
        'units': 'FRED breakeven and Treasury percent divided by 100; S&P price index unchanged',
        'time': '16:00 America/New_York observation convention; not historical publication/vintage evidence',
        'missingness': 'Only complete common dates; no interpolation/forward-fill; upstream compiled earnings/history retained',
        'rights': 'Keep SP500 source/fixture local; consult FRED series redistribution restrictions'})
    print('Public empirical fixture saved locally; complete common observations:', len(selected))


if __name__ == '__main__':
    main()
