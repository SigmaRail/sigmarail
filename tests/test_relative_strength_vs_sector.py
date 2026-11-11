"""E2E for stage_analysis.relative_strength_vs_sector (VeraProjects#168).

The column is the percentile (0-100) of the ticker's 3m performance within its
PIT sector peers from ticker_classification_daily — NULL when unclassified,
when fewer than 5 sector members have perf_3m, or when the ticker's own
perf_3m is NULL. Seeds sector cohorts into relative_strength +
ticker_classification_daily + daily_metrics and runs transform 64 for real.
"""

import math
from datetime import date, datetime
from pathlib import Path

import pytest

from sigmarail.database import get_project_root

SEED_DATE = date(1990, 1, 5)
CHUNK = ("1990-01-05", "1990-01-05")

# SecA: 6 members, with a tied return; ticker order makes the last two ranks stable.
SECA = {"SA_A1": 0.10, "SA_A2": 0.20, "SA_A3": 0.30,
        "SA_A4": 0.40, "SA_A5": 0.50, "SA_A6": 0.50}
# SecB: exactly 5 members (floor boundary) -> percentiles 0,25,50,75,100
SECB = {"SB_1": 0.10, "SB_2": 0.20, "SB_3": 0.30, "SB_4": 0.40, "SB_5": 0.50}
# Thin sector: 3 members -> below the 5-member floor -> all NULL
SECT = {"ST_1": 0.10, "ST_2": 0.20, "ST_3": 0.30}
EXTRA = {"SU_UNCLASS": 0.40,   # no classification row -> NULL
         "SA_NULLPERF": None}  # in SecA but NULL perf_3m -> NULL


def _transform_path() -> Path:
    root = Path(get_project_root())
    return root / "src" / "sigmarail" / "sql" / "schema" / "83-schema-stage_analysis.sql"


@pytest.fixture(scope="module")
def mart(global_client):
    client = global_client

    all_tickers = tuple(SECA) + tuple(SECB) + tuple(SECT) + tuple(EXTRA)
    for table in ("relative_strength", "daily_metrics",
                  "ticker_classification_daily"):
        client.command(
            f"ALTER TABLE {table} DELETE WHERE ticker IN %(t)s",
            parameters={"t": all_tickers},
        )
    client.command(
        "ALTER TABLE stage_analysis DELETE WHERE ticker IN %(t)s",
        parameters={"t": all_tickers},
    )
    stamp = datetime(2030, 1, 1)
    sectors = {**{t: "SecA" for t in SECA}, **{t: "SecB" for t in SECB},
               **{t: "SecThin" for t in SECT}, "SA_NULLPERF": "SecA"}
    perfs = {**SECA, **SECB, **SECT, **EXTRA}
    client.insert(
        "ticker_classification_daily",
        [(t, date(1970, 1, 1), s, "ind", "fama", "sics", "sici", stamp) for t, s in sectors.items()],
        column_names=["ticker", "date", "sector", "industry", "famaindustry",
                      "sicsector", "sicindustry", "lastupdated"],
    )
    client.insert(
        "daily_metrics",
        [(t, SEED_DATE, 50.0, stamp) for t in all_tickers],
        column_names=["ticker", "date", "close", "lastupdated"],
    )
    client.insert(
        "relative_strength",
        [(t, SEED_DATE, None, None, p3, None, None, None, None, None, None,
          None, 1, None, None, stamp) for t, p3 in perfs.items()],
        column_names=["ticker", "date", "yearly_performance", "performance_6m",
                      "performance_3m", "performance_1m", "composite_performance",
                      "rs_rating", "sma10d_rs_rating", "sma21d_rs_rating",
                      "sma50d_rs_rating", "sma200d_rs_rating", "momentum_rank",
                      "price_relative_ratio", "price_relative_ratio_rebased",
                      "lastupdated"],
    )
    from sigmarail.transform_sql import run_transform_file

    run_transform_file(
        client,
        _transform_path(),
        {"chunk_start_date": CHUNK[0], "chunk_end_date": CHUNK[1]},
    )
    res = client.query(
        """
        SELECT ticker, relative_strength_vs_sector
        FROM stage_analysis FINAL
        WHERE date = %(d)s AND ticker IN %(t)s
        """,
        parameters={"d": SEED_DATE, "t": all_tickers},
    )
    return dict(res.result_rows)


def _close(got: float | None, want: float) -> bool:
    return got is not None and math.isclose(got, want, rel_tol=1e-5, abs_tol=1e-4)


def test_sector_percentile_ranks_within_sector(mart) -> None:
    """Tied returns use ticker order; SA_A3 is 3rd of 6 and SB_3 is 3rd of 5."""
    assert _close(mart["SA_A3"], 40.0)
    assert _close(mart["SA_A5"], 80.0)
    assert _close(mart["SA_A6"], 100.0)
    assert _close(mart["SA_A1"], 0.0)
    assert _close(mart["SB_3"], 50.0)


def test_unclassified_and_thin_sector_are_null(mart) -> None:
    assert mart["SU_UNCLASS"] is None, "unclassified ticker must emit NULL"
    for t in SECT:
        assert mart[t] is None, f"{t}: thin sector must emit NULL"


def test_null_perf_member_is_null_and_excluded(mart) -> None:
    assert mart["SA_NULLPERF"] is None, "NULL perf_3m -> NULL sector pct"
    # SA_NULLPERF excluded from the denominator: SecA still has exactly 6
    # non-NULL members (SA_A1..A6), keeping the floor and spread exact.
    assert _close(mart["SA_A3"], 40.0)
