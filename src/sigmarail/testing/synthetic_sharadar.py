"""Deterministic, provider-free Sharadar-shaped data for SigmaRail integration tests.

The generated rows exercise SigmaRail's source schema and transforms. They are not
observations, reconstructions, or estimates of real securities data.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path

from dateutil.easter import easter

LINEAGE = json.loads(files("sigmarail").joinpath("spec/lineage-manifest.json").read_text(encoding="utf-8"))
TABLES = {
    table["name"]: [column["name"] for column in table["columns"]]
    for table in LINEAGE["tables"]
    if table["kind"] == "sharadar_source"
}
_ANCHORS = [
    ("AAPL", "Technology", "Consumer Electronics", 0),
    ("MSFT", "Technology", "Software", 1),
    ("NVDA", "Technology", "Semiconductors", 2),
    ("AMZN", "Consumer Cyclical", "Internet Retail", 3),
    ("GOOGL", "Communication Services", "Internet Content", 4),
    ("META", "Communication Services", "Internet Content", 5),
    ("TSLA", "Consumer Cyclical", "Auto Manufacturers", 6),
    ("AVGO", "Technology", "Semiconductors", 7),
    ("AMD", "Technology", "Semiconductors", 8),
    ("NFLX", "Communication Services", "Entertainment", 9),
    ("JPM", "Financial Services", "Banks", 10),
    ("XOM", "Energy", "Oil & Gas", 11),
    ("COST", "Consumer Defensive", "Discount Stores", 12),
    ("UNH", "Healthcare", "Healthcare Plans", 13),
    ("SPY", "ETF", "Index Fund", 14),
]
_SECTORS = [
    "Technology", "Healthcare", "Financial Services", "Industrials", "Energy",
    "Consumer Cyclical", "Consumer Defensive", "Utilities", "Real Estate",
    "Communication Services", "Basic Materials",
]
_STOCKS = _ANCHORS[:-1] + [
    (f"SYN{i:02d}", _SECTORS[i % len(_SECTORS)], f"Synthetic Industry {i % 9}", i)
    for i in range(1, 22)
]
_FUNDS = [
    ("SPY", "Broad Market", "Synthetic Broad Market Fund", 35),
    ("QQQ", "Technology", "Synthetic Nasdaq Fund", 36),
    ("TQQQ", "Technology", "Synthetic Leveraged Nasdaq Fund", 37),
    ("XLK", "Technology", "Synthetic Technology Sector Fund", 38),
    ("XLV", "Healthcare", "Synthetic Healthcare Sector Fund", 39),
    ("XLF", "Financial Services", "Synthetic Financial Sector Fund", 40),
    ("XLY", "Consumer Cyclical", "Synthetic Cyclical Sector Fund", 41),
    ("XLP", "Consumer Defensive", "Synthetic Defensive Sector Fund", 42),
    ("XLI", "Industrials", "Synthetic Industrial Sector Fund", 43),
    ("XLE", "Energy", "Synthetic Energy Sector Fund", 44),
    ("XLU", "Utilities", "Synthetic Utilities Sector Fund", 45),
    ("XLRE", "Real Estate", "Synthetic Real Estate Sector Fund", 46),
    ("XLC", "Communication Services", "Synthetic Communications Sector Fund", 47),
    ("XLB", "Basic Materials", "Synthetic Materials Sector Fund", 48),
    ("IWM", "Broad Market", "Synthetic Small Cap Fund", 49),
    ("DIA", "Broad Market", "Synthetic Industrial Average Fund", 50),
]
SYMBOLS = _STOCKS + _FUNDS
START = date(2021, 1, 1)
END = date(2024, 12, 31)

_SCALE_LABELS = {
    1: "Nano", 2: "Micro", 3: "Small", 4: "Mid", 5: "Large", 6: "Mega"
}


def _observed(day: date) -> date:
    return day - timedelta(days=1) if day.weekday() == 5 else day + timedelta(days=1) if day.weekday() == 6 else day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    first_next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = first_next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _market_holidays() -> set[date]:
    holidays: set[date] = set()
    for year in range(START.year - 1, END.year + 1):
        new_year = date(year, 1, 1)
        # NYSE does not observe New Year's Day on the prior Friday when Jan 1
        # falls on Saturday (e.g. 2022); other fixed holidays are observed.
        if new_year.weekday() != 5:
            holidays.add(_observed(new_year))
        holidays.update({
            _nth_weekday(year, 1, 0, 3),
            _nth_weekday(year, 2, 0, 3),
            easter(year) - timedelta(days=2),
            _last_weekday(year, 5, 0),
            _observed(date(year, 7, 4)),
            _nth_weekday(year, 9, 0, 1),
            _nth_weekday(year, 11, 3, 4),
            _observed(date(year, 12, 25)),
        })
        if year >= 2022:
            holidays.add(_observed(date(year, 6, 19)))
    return holidays


def _sessions():
    holidays = _market_holidays()
    day = START
    while day <= END:
        if day.weekday() < 5 and day not in holidays:
            yield day
        day += timedelta(days=1)


def _write(path: Path, rows: list[dict], columns: list[str]) -> int:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _market_factor(day_index: int) -> float:
    """Deterministic shared market cycle; identical for every symbol and SPY."""
    return 0.20 * math.sin(day_index / 31) + 0.07 * math.sin(day_index / 9)


def _price(symbol_index: int, day_index: int) -> float:
    """Return a positive series with distinct deterministic trend archetypes.

    Each symbol carries a common market factor (so cross-sectional betas against
    SPY are meaningful) scaled by a per-symbol sensitivity, plus its own
    idiosyncratic drift and cycles.
    """
    base = 35 + symbol_index * 17
    profile = symbol_index % 7
    daily_drift = (0.00055, 0.00135, 0.0008, -0.00025, 0.0001, 0.0007, 0.0010)[profile]
    amplitude = (0.025, 0.04, 0.09, 0.055, 0.11, 0.07, 0.14)[profile]
    cycle = amplitude * math.sin(day_index / (37 + symbol_index % 31) + symbol_index)
    shorter_cycle = 0.018 * math.sin(day_index / (9 + symbol_index % 5) + profile)
    # Per-symbol market sensitivity. Broad-market funds (SPY/QIQ/DIA/IWM) lead
    # the factor; sector funds sit in the middle; individual names vary from
    # low-beta defensives to high-beta cyclicals so median beta_mkt is realistic.
    sensitivity = (1.6, 1.0, 1.3, 0.6, 0.9, 1.1, 1.4)[profile]
    if symbol_index == 35:  # SPY: the market proxy itself
        sensitivity = 1.0
    elif symbol_index >= 36 and symbol_index < len(SYMBOLS):
        sensitivity = 0.75 + 0.35 * ((symbol_index - 36) % 4)
    return round(base * math.exp(
        daily_drift * day_index + cycle + shorter_cycle
        + sensitivity * _market_factor(day_index)
    ), 4)


def generate_synthetic_dataset(destination: Path | str) -> dict:
    """Write all source-table CSVs and return a deterministic count manifest."""
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    sessions = list(_sessions())
    if len(sessions) != 1005:
        raise AssertionError(f"Synthetic NYSE session count changed: expected 1005, got {len(sessions)}")
    last = END.isoformat()
    tickers = []
    for index, (ticker, sector, industry, _) in enumerate(SYMBOLS):
        if index < len(_STOCKS):
            category = "Domestic Common Stock" if index < 27 else "Domestic Common Stock Primary Class"
            scale = (index % 6) + 1
        else:
            category = "IDX" if ticker in {"SPY", "QQQ"} else "ETF"
            scale = 6
        tickers.append({
            "table": "funds" if index >= len(_STOCKS) else "stocks",
            "permaticker": f"SYN{index + 1:04d}", "ticker": ticker,
            "name": f"Synthetic {ticker} Corporation", "exchange": "NYSE" if ticker in {"JPM", "XOM", "UNH"} else "NASDAQ",
            "isdelisted": "N", "category": category, "cusips": f"SYN{index:06d}", "figi": "",
            "siccode": "7372", "sicsector": sector, "sicindustry": industry,
            "famaindustry": industry, "sector": sector, "industry": industry,
            "scalemarketcap": f"{scale} - {_SCALE_LABELS[scale]}",
            "scalerevenue": f"{scale} - {_SCALE_LABELS[scale]}", "relatedtickers": "", "currency": "USD",
            "location": "Synthetic", "lastupdated": "2024-12-31 23:59:59",
            "firstadded": START.isoformat(), "firstpricedate": START.isoformat(), "lastpricedate": last,
            "firstquarter": "2021-03-31", "lastquarter": "2024-12-31",
            "secfilings": "", "companysite": "",
        })
    counts["tickers"] = _write(out / "SHARADAR_TICKERS_SYNTHETIC.csv", tickers, TABLES["tickers"])

    prices: dict[str, list[dict]] = {"sep": [], "sfp": []}
    daily = []
    for i, (ticker, _, _, _) in enumerate(SYMBOLS):
        table = "sfp" if i >= len(_STOCKS) else "sep"
        for n, day in enumerate(sessions):
            close = _price(i, n)
            previous = _price(i, max(n - 1, 0))
            intraday = 0.0035 * math.sin(n * 1.73 + i)
            opened = close * (1 - intraday)
            spread = 0.006 + 0.004 * ((i + n) % 4)
            volume = 800_000 + ((n * 7919 + i * 104729) % 4_000_000)
            volume += 700_000 if close >= previous else 0
            prices[table].append({
                "ticker": ticker, "date": day.isoformat(), "open": round(opened, 4),
                "high": round(max(opened, close) * (1 + spread), 4),
                "low": round(min(opened, close) * (1 - spread), 4), "close": close,
                "volume": volume, "closeadj": close, "closeunadj": close,
                "lastupdated": f"{day.isoformat()} 23:59:59",
            })
            if table == "sep":
                marketcap = close * 100_000_000
                daily.append({
                    "ticker": ticker, "date": day.isoformat(), "lastupdated": f"{day.isoformat()} 23:59:59",
                    "ev": marketcap * 1.08, "evebit": 18 + i, "evebitda": 13 + i,
                    "marketcap": marketcap, "pb": 4 + i * .2, "pe": 20 + i, "ps": 5 + i * .1,
                    "shareswa": 100_000_000, "sharefactor": 1,
                })
    for table, rows in prices.items():
        counts[table] = _write(out / f"SHARADAR_{table.upper()}_SYNTHETIC.csv", rows, TABLES[table])
    counts["daily"] = _write(out / "SHARADAR_DAILY_SYNTHETIC.csv", daily, TABLES["daily"])

    # This mirrors the sample's exact dimension mix: 72 records per stock,
    # with filings dated after period end so point-in-time joins cannot look ahead.
    sf1 = []
    quarter_ends = [date(y, m, 1) - timedelta(days=1)
                    for y in range(2021, 2025) for m in (4, 7, 10)]
    quarter_ends += [date(y, 12, 31) for y in range(2021, 2025)]
    quarter_ends = sorted(set(d for d in quarter_ends if START <= d <= END))
    numeric_names = [c for c in TABLES["sf1"] if c not in {"ticker", "dimension", "calendardate", "date", "reportperiod", "fiscalperiod", "lastupdated", "sic", "currency"}]
    growth_profiles = (0.025, 0.075, 0.16, -0.015, 0.005, 0.11, 0.045)
    for i, (ticker, _, _, _) in enumerate(_STOCKS):
        growth_rate = growth_profiles[i % len(growth_profiles)]
        for period_index, period_end in enumerate(quarter_ends):
            filed = period_end + timedelta(days=35)
            dimensions = ("ARQ", "MRQ", "MRT", "ART")
            if period_end.month == 12:
                dimensions += ("ARY", "MRY")
            for dimension in dimensions:
                row = {"ticker": ticker, "dimension": dimension, "calendardate": period_end.isoformat(),
                       "date": filed.isoformat(), "reportperiod": period_end.isoformat(),
                       "fiscalperiod": f"Q{((period_end.month - 1) // 3) + 1}",
                       "lastupdated": f"{filed.isoformat()} 23:59:59", "sic": "7372", "currency": "USD"}
                year_index = period_end.year - START.year
                year_revenue = 1_000_000_000 * (1 + i * .07) * ((1 + growth_rate) ** year_index)
                is_quarter = dimension in {"ARQ", "MRQ"}
                revenue = year_revenue / 4 if is_quarter else year_revenue
                eps = 4.0 * (1 + growth_rate) ** year_index
                if is_quarter:
                    eps /= 4
                for name in numeric_names:
                    value = 0.0
                    if name in {"revenue", "revenueusd", "sales", "salesusd"}:
                        value = revenue
                    elif name in {"netinc", "netinccmn", "netinccmnusd"}:
                        value = revenue * .12
                    elif name in {"ncfo", "ncfi", "ebit", "opinc", "gp"}:
                        value = revenue * .18
                    elif name == "capex":
                        value = -revenue * .08
                    elif name == "fcf":
                        value = revenue * .10
                    elif name in {"assets", "assetsavg", "equity", "equityavg", "marketcap"}:
                        value = revenue * 2.2
                    elif name in {"sharesbas", "shareswa", "shareswadil"}:
                        value = 100_000_000
                    elif name in {"price", "eps", "epsusd", "epsdil", "epsdilusd"}:
                        value = eps
                    elif name in {"roa", "roe", "roic", "ros", "netmargin", "grossmargin"}:
                        value = .08 + (i % 7) * .025
                    row[name] = round(value, 4)
                sf1.append(row)
    counts["sf1"] = _write(out / "SHARADAR_SF1_SYNTHETIC.csv", sf1, TABLES["sf1"])

    # Match the source sample: metrics and SF2 are absent; the manifest records
    # their expected empty state without asking ClickHouse to load header-only files.
    empty_tables = {"metrics", "sf2"}
    for table in sorted(empty_tables):
        counts[table] = 0

    # Compact institutional holdings snapshots exercise the quarterly ownership
    # joins while keeping deterministic data generation independent of vendors.
    report_dates = [date(y, m, 1) - timedelta(days=1)
                    for y in range(2021, 2025) for m in (4, 7, 10)]
    report_dates += [date(y, 12, 31) for y in range(2021, 2025)]
    report_dates = sorted(set(d for d in report_dates if d <= END))
    sf3, sf3a, sf3b = [], [], []
    for d_index, report_date in enumerate(report_dates):
        for ticker_index, (ticker, _, _, _) in enumerate(_STOCKS):
            holders = 10 + ticker_index % 13 + d_index
            units = 100_000 + ticker_index * 1_000 + d_index * 200
            price = _price(ticker_index, d_index * 60)
            value = units * price
            sf3a.append({
                "date": report_date.isoformat(), "ticker": ticker, "name": f"Synthetic {ticker}",
                "shrholders": holders, "cllholders": 0, "putholders": 0, "wntholders": 0,
                "dbtholders": 0, "prfholders": 0, "fndholders": 0, "undholders": 0,
                "shrunits": units, "cllunits": 0, "putunits": 0, "wntunits": 0,
                "dbtunits": 0, "prfunits": 0, "fndunits": 0, "undunits": 0,
                "shrvalue": value, "cllvalue": 0, "putvalue": 0, "wntvalue": 0,
                "dbtvalue": 0, "prfvalue": 0, "fndvalue": 0, "undvalue": 0,
                "totalvalue": value, "percentoftotal": 100,
            })
            for investor_index in range(3):
                investor_id = f"SYNTH-FILER-{investor_index + 1}"
                for security_index, security_type in enumerate(("SHR", "CLL", "PUT")):
                    holding_units = units * (investor_index + 1) // (security_index + 1)
                    sf3.append({"ticker": ticker, "investorid": investor_id, "securitytype": security_type,
                                "date": report_date.isoformat(), "value": holding_units * price, "units": holding_units})
        for investor_index in range(3):
            investor_id = f"SYNTH-FILER-{investor_index + 1}"
            units = 2_000_000 + d_index * 10_000 + investor_index * 50_000
            value = units * 100
            row = {"date": report_date.isoformat(), "investorid": investor_id,
                   "investorname": f"Synthetic Institutional Filer {investor_index + 1}"}
            for col in TABLES["sf3b"]:
                if col in {"date", "investorid", "investorname"}:
                    continue
                row[col] = units if col.endswith("holdings") or col.endswith("units") else value if col.endswith("value") or col == "totalvalue" else 100
            sf3b.append(row)
    counts["sf3"] = _write(out / "SHARADAR_SF3_SYNTHETIC.csv", sf3, TABLES["sf3"])
    counts["sf3a"] = _write(out / "SHARADAR_SF3A_SYNTHETIC.csv", sf3a, TABLES["sf3a"])
    counts["sf3b"] = _write(out / "SHARADAR_SF3B_SYNTHETIC.csv", sf3b, TABLES["sf3b"])

    events = [{"ticker": ticker, "date": date(2021 + year, 3 + ((event_index % 4) * 2), 15).isoformat(),
               "eventcodes": f"{(event_index % 8) + 1:02d}"}
              for index, (ticker, _, _, _) in enumerate(_STOCKS)
              for year in range(4) for event_index in range(4)]
    counts["events"] = _write(out / "SHARADAR_EVENTS_SYNTHETIC.csv", events, TABLES["events"])
    actions = [{"date": date(2021 + year, month, 15).isoformat(), "action": "dividend",
                "ticker": ticker, "name": f"Synthetic {ticker}", "value": 0.25,
                "contraticker": "", "contraname": ""}
               for ticker, _, _, _ in _STOCKS for year in range(4) for month in (3, 6, 9, 12)]
    counts["actions"] = _write(out / "SHARADAR_ACTIONS_SYNTHETIC.csv", actions,
                                [c for c in TABLES["actions"] if c != "lastupdated"])
    sp500 = [{"date": START.isoformat(), "action": "added", "ticker": ticker,
              "name": f"Synthetic {ticker}", "contraticker": "", "contraname": "", "note": "synthetic"}
             for ticker, _, _, _ in _STOCKS]
    counts["sp500"] = _write(out / "SHARADAR_SP500_SYNTHETIC.csv", sp500,
                             [c for c in TABLES["sp500"] if c != "lastupdated"])
    manifest = {
        "profile": "deterministic-synthetic-v1", "provider_data": False,
        "start_date": START.isoformat(), "end_date": END.isoformat(),
        "first_price_date": sessions[0].isoformat(),
        "symbol_count": len(SYMBOLS), "stock_count": len(_STOCKS),
        "fund_count": len(_FUNDS), "price_session_count": len(sessions),
        "tables": counts,
    }
    (out / "synthetic-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
