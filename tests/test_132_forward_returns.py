"""E2E tests for transform 132 (screener_forward_returns_daily).

Seeds a deterministic synthetic price spine in an unused 1990 date range
(real fixtures cover 2021+), runs the actual transform body for bounded
chunks, and asserts:

- fwd_ret_5d / fwd_ret_21d equal the Python ground truth (closeadj basis)
- the +40d forward lookahead buffer keeps chunk-end rows non-NULL
- ew_universe_ret_* equals the cross-sectional mean of that date's forwards
- rows past seeded history correctly NULL their forward returns

VeraProjects#71 (sub-slice of #70).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import clickhouse_connect
import pytest

from sigmarail.config import get_project_root
from sigmarail.database import execute_sql_file

TICKERS = ("FWD_A", "FWD_B", "FWD_C")
SEED_START = date(1990, 1, 2)
N_BARS = 80  # business days; ~01-02 .. 04-24

CHUNK_A = ("1990-01-01", "1990-02-15")   # lookahead must reach into Mar
CHUNK_B = ("1990-03-26", "1990-04-30")   # runs into the seeded tail


def _bdates() -> list[date]:
    days, d = [], SEED_START
    while len(days) < N_BARS:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _price(ticker: str, i: int) -> float:
    if ticker == "FWD_A":
        return 100.0 * (1.01**i)
    if ticker == "FWD_B":
        return 50.0 * (1.0 + 0.002 * i)
    return 200.0 * (0.995**i)  # FWD_C declining


def _expected_ret(ticker: str, i: int, k: int) -> float | None:
    """Python ground truth: closeadj[i+k] / closeadj[i] - 1, NULL past tail."""
    if i + k >= N_BARS:
        return None
    return _price(ticker, i + k) / _price(ticker, i) - 1.0


def _transform_body() -> str:
    root = Path(get_project_root())
    return str(root / "src" / "sigmarail" / "sql" / "schema" / "202-schema-screener_forward_returns_daily.sql")


def _ensure_schema(client: clickhouse_connect.driver.Client) -> None:
    root = Path(get_project_root())
    for name in (
        "176-schema-screener_price_tech_daily.sql",
        "202-schema-screener_forward_returns_daily.sql",
    ):
        path = root / "src" / "sigmarail" / "sql" / "schema" / name
        assert path.is_file(), f"missing schema {path}"
        assert execute_sql_file(path, description=name), f"failed to load {name}"


def _seed_prices(client: clickhouse_connect.driver.Client) -> None:
    rows = []
    for ticker in TICKERS:
        for i, d in enumerate(_bdates()):
            px = _price(ticker, i)
            rows.append(
                (
                    ticker,
                    d,
                    ticker,                      # company_name
                    "Technology",                # sector
                    "Test",                      # industry
                    "NASDAQ",                    # exchange
                    "USD",                       # currency
                    "Domestic Common Stock",     # category
                    px,                          # close
                    px,                          # closeadj
                    1_000_000.0,                 # volume
                )
            )
    client.insert(
        "screener_price_tech_daily",
        rows,
        column_names=[
            "ticker", "date", "company_name", "sector", "industry",
            "exchange", "currency", "category", "close", "closeadj", "volume",
        ],
    )


@pytest.fixture(scope="module")
def fwd_mart(global_client: clickhouse_connect.driver.Client) -> clickhouse_connect.driver.Client:
    client = global_client
    _ensure_schema(client)
    _seed_prices(client)
    from sigmarail.transform_sql import run_transform_file

    path = Path(_transform_body())
    for start, end in (CHUNK_A, CHUNK_B):
        run_transform_file(
            client,
            path,
            {"chunk_start_date": start, "chunk_end_date": end},
        )
    return client


def _fetch_rows(client) -> dict[tuple[str, str], tuple]:
    res = client.query(
        """
        SELECT ticker, date, close,
               fwd_ret_5d, fwd_ret_21d, ew_universe_ret_5d, ew_universe_ret_21d
        FROM screener_forward_returns_daily FINAL
        WHERE ticker IN %(tickers)s
        """,
        parameters={"tickers": TICKERS},
    )
    return {(str(r[0]), str(r[1])): r[2:] for r in res.result_rows}


def test_chunk_a_row_scope_and_dates(fwd_mart) -> None:
    rows = _fetch_rows(fwd_mart)
    chunk_a_days = [d for d in _bdates() if CHUNK_A[0] <= str(d) <= CHUNK_A[1]]
    chunk_b_days = [d for d in _bdates() if CHUNK_B[0] <= str(d) <= CHUNK_B[1]]
    expected_keys = {
        (t, str(d)) for t in TICKERS for d in chunk_a_days + chunk_b_days
    }
    assert set(rows) == expected_keys
    # nothing emitted outside the emitted chunk ranges
    for (_, d) in rows:
        assert str(d) <= CHUNK_A[1] or CHUNK_B[0] <= str(d) <= CHUNK_B[1]


def test_forward_returns_match_python_truth(fwd_mart) -> None:
    rows = _fetch_rows(fwd_mart)
    index = {str(d): i for i, d in enumerate(_bdates())}
    checked = 0
    for (ticker, d), r in rows.items():
        i = index[d]
        exp5 = _expected_ret(ticker, i, 5)
        exp21 = _expected_ret(ticker, i, 21)
        got5, got21 = r[1], r[2]
        if exp5 is None:
            assert got5 is None, f"{ticker} {d} fwd5 should be NULL"
        else:
            assert got5 is not None and math.isclose(got5, exp5, rel_tol=1e-6, abs_tol=1e-9)
        if exp21 is None:
            assert got21 is None, f"{ticker} {d} fwd21 should be NULL"
        else:
            assert got21 is not None and math.isclose(got21, exp21, rel_tol=1e-6, abs_tol=1e-9)
        # close column carries the signal-date split-adjusted price
        assert r[0] is not None and r[0] > 0
        checked += 1
    assert checked > 0


def test_chunk_end_not_null_lookahead_worked(fwd_mart) -> None:
    """1990-02-15 sits inside the chunk but its +21 bars need the lookahead
    window; without it these would be NULL."""
    rows = _fetch_rows(fwd_mart)
    for t in TICKERS:
        r = rows[(t, CHUNK_A[1])]
        assert r[1] is not None and r[2] is not None, f"{t} chunk-end NULL"


def test_tail_rows_null_forward_returns(fwd_mart) -> None:
    """Bars near the end of seeded history cannot produce forward returns."""
    rows = _fetch_rows(fwd_mart)
    null5 = [k for k, r in rows.items() if r[1] is None]
    null21 = [k for k, r in rows.items() if r[2] is None]
    # Chunk B emits seeded bars idx 59..79 (03-26..04-23): fwd5 NULL for
    # i>=75 (5 dates), fwd21 NULL for every emitted date (i+21 >= 80).
    assert len(null5) == 3 * 5
    assert len(null21) == 3 * 21


def test_ew_universe_is_cross_sectional_mean(fwd_mart) -> None:
    rows = _fetch_rows(fwd_mart)
    by_date: dict[str, list[tuple[str, tuple]]] = {}
    for key, r in rows.items():
        by_date.setdefault(key[1], []).append((key[0], r))
    checked = 0
    for d, members in by_date.items():
        exp5 = [r[1] for _, r in members if r[1] is not None]
        exp21 = [r[2] for _, r in members if r[2] is not None]
        mean5 = sum(exp5) / len(exp5) if exp5 else None
        mean21 = sum(exp21) / len(exp21) if exp21 else None
        for _, r in members:
            if mean5 is None:
                assert r[3] is None or math.isnan(r[3])
            else:
                assert math.isclose(r[3], mean5, rel_tol=1e-5, abs_tol=1e-7)
            if mean21 is None:
                assert r[4] is None or math.isnan(r[4])
            else:
                assert math.isclose(r[4], mean21, rel_tol=1e-5, abs_tol=1e-7)
        checked += 1
    assert checked > 0


def test_derived_list_includes_target() -> None:
    from sigmarail.config import get_schema_files
    from sigmarail.transform_sql import discover_transform_specs

    assert "screener_forward_returns_daily" in {
        spec.target for spec in discover_transform_specs() if spec.target
    }
    assert any("screener_forward_returns_daily" in path.read_text() for path in get_schema_files())
