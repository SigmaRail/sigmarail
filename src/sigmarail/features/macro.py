"""Macro economic-environment data: growth + inflation from FRED.

Fetches CPI-U (inflation) and Real GDP (growth) from the FRED public CSV
endpoint (no API key), computes YoY/QoQ deltas, forward-fills to daily, and
classifies the Dalio 4-quadrant environment. Populates ``macro_economic_daily``
so the All Weather regime overlay can be driven by real macro data in backtests.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import date, timedelta
from typing import Any

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

CPI_SERIES = "CPIAUCSL"  # CPI-U, seasonally adjusted, monthly
GDP_SERIES = "GDPC1"     # Real GDP, chained 2017 dollars, quarterly


def fetch_fred_series(series_id: str) -> dict[date, float]:
    """Fetch a FRED series as {date: value} via the public CSV endpoint."""
    url = FRED_CSV.format(series=series_id)
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    out: dict[date, float] = {}
    for r in csv.DictReader(io.StringIO(text)):
        try:
            d = date.fromisoformat(r["observation_date"])
            out[d] = float(r[series_id])
        except (KeyError, ValueError, TypeError):
            continue
    return out


def yoy(series: dict[date, float]) -> dict[date, float]:
    """Year-over-year % change (for monthly CPI)."""
    out: dict[date, float] = {}
    for d in sorted(series):
        one_year_ago = date(d.year - 1, d.month, d.day)
        base = series.get(one_year_ago)
        if base:
            out[d] = (series[d] - base) / base * 100.0
    return out


def qoq_annualized(series: dict[date, float]) -> dict[date, float]:
    """Quarter-over-quarter % change, annualized (for quarterly GDP)."""
    out: dict[date, float] = {}
    dates = sorted(series)
    for i in range(1, len(dates)):
        d, prev = dates[i], dates[i - 1]
        base = series[prev]
        if base and series[d] and base > 0:
            out[d] = ((series[d] / base) ** 4 - 1.0) * 100.0
    return out


def classify_environment(
    growth: float,
    inflation: float,
    *,
    growth_threshold: float = 0.0,
    inflation_threshold: float = 2.0,
) -> str:
    """Dalio 4-quadrant classification from growth/inflation deltas."""
    g_up = growth >= growth_threshold
    i_up = inflation >= inflation_threshold
    if g_up and i_up:
        return "reflation"
    if g_up and not i_up:
        return "goldilocks"
    if not g_up and i_up:
        return "stagflation"
    return "deflation"


def build_daily(
    growth: dict[date, float],
    inflation: dict[date, float],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """Forward-fill monthly/quarterly deltas to daily rows + quadrant."""
    if not growth or not inflation:
        return []
    growth_sorted = sorted(growth.items())
    inflation_sorted = sorted(inflation.items())
    lo = start or min(growth_sorted[0][0], inflation_sorted[0][0])
    hi = end or date.today()

    rows: list[dict[str, Any]] = []
    g_val: float | None = None
    i_val: float | None = None
    gi = ii = 0
    d = lo
    while d <= hi:
        while gi < len(growth_sorted) and growth_sorted[gi][0] <= d:
            g_val = growth_sorted[gi][1]
            gi += 1
        while ii < len(inflation_sorted) and inflation_sorted[ii][0] <= d:
            i_val = inflation_sorted[ii][1]
            ii += 1
        if g_val is not None and i_val is not None:
            rows.append(
                {
                    "date": d,  # date object (clickhouse_connect Date column)
                    "real_gdp_qoq": round(g_val, 4),
                    "cpi_yoy": round(i_val, 4),
                    "regime_quadrant": classify_environment(g_val, i_val),
                }
            )
        d += timedelta(days=1)
    return rows


def load(client: Any, *, persist: bool = True) -> dict[str, Any]:
    """Fetch FRED data, compute deltas, and (optionally) populate the table."""
    cpi = fetch_fred_series(CPI_SERIES)
    gdp = fetch_fred_series(GDP_SERIES)
    rows = build_daily(qoq_annualized(gdp), yoy(cpi))

    if persist and rows:
        client.command(
            "CREATE TABLE IF NOT EXISTS macro_economic_daily"
            " (date Date32, real_gdp_qoq Float64, cpi_yoy Float64, regime_quadrant LowCardinality(String))"
            " ENGINE = MergeTree ORDER BY date"
        )
        client.insert(
            "macro_economic_daily",
            [[r["date"], r["real_gdp_qoq"], r["cpi_yoy"], r["regime_quadrant"]] for r in rows],
            column_names=["date", "real_gdp_qoq", "cpi_yoy", "regime_quadrant"],
        )

    return {"cpi_obs": len(cpi), "gdp_obs": len(gdp), "daily_rows": len(rows)}


if __name__ == "__main__":
    import sys

    from sigmarail.features.ch_settings import connect_clickhouse, resolve_clickhouse_settings_unified

    client = connect_clickhouse(resolve_clickhouse_settings_unified())
    try:
        out = load(client, persist="--load" in sys.argv)
        print(out)
    finally:
        client.close()
