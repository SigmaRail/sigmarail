"""T5 — the VCP satellite's SQL is validated against the Python reference, column for column.

This is the test the whole Phase 2 exercise exists for. The transform
(`sql/transform/metrics/131-screener-vcp-pivot-daily.sql`) carries a ZigZag state machine in SQL; the
oracle is `scripts/vcp_zigzag.py`, whose own semantics are pinned by 38 unit tests. Here the two are
run over the same bars and every published column must agree.

Why a database test and not a unit test: the SQL is where the fold actually runs in production, and
four separate bugs survived a clean parse-check and several careful readings — a stale-extreme
comparison, a one-bar iteration offset, a vacuous-truth arity guard, and an array typed as
Array(Nullable(Float64)) instead of a tuple. Only execution caught them. (See the transform header;
`git log -- sql/transform/metrics/131-screener-vcp-pivot-daily.sql` has the details.)

Two cases:

1. **Whole-window comparison** against the reference over the fixture spine, every column.
2. **Known-answer reproducer** on three synthetic bars — the minimum shape that broke the fold. A wide
   bar (high 13.24, low 12.59 after a 13.65 high) satisfies BOTH reversals at once, which is what makes
   the branch order and the update-before-test ordering matter. Small enough to debug by hand.

Both sides are read with FINAL: these tables are ReplacingMergeTree and the test instance has been
populated more than once, so a read without FINAL can legitimately return more rows than keys.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
from tests.support import vcp_zigzag_reference as vcp

TRANSFORM = REPO / "src" / "sigmarail" / "sql" / "schema" / "201-schema-screener_vcp_pivot_daily.sql"
WINDOW = {"chunk_start_date": "2021-01-01", "chunk_end_date": "2021-06-30"}

# The reference's VcpConfig defaults, which the transform declares as literals.
THRESHOLD = 0.05


@pytest.fixture(scope="module")
def db_client(global_client):
    return global_client

# Scalar columns compared exactly (floats to a tolerance smaller than any meaningful price move).
FLOAT_COLUMNS = {"pivot_line": 0.005, "dist_to_pivot_pct": 0.005, "contraction_ratio": 0.005}

# Boolean/flag columns: SQL UInt8 against the reference's bool.
FLAG_COLUMNS = [
    "depths_descending", "depths_descending_tol",
    "highs_descending", "highs_descending_tol",
    "lows_ascending", "lows_ascending_tol",
    "halving", "max_contraction_ratio_ok", "first_leg_deep_enough", "legs_long_enough",
    "base_long_enough", "base_qualified", "wide_and_loose", "has_shakeout",
    "volume_dryup_compressing", "atr_contracting",
    "breakout", "breakout_clear", "breakout_event", "breakout_on_volume",
]

# Integer columns compared exactly.
INT_COLUMNS = ["contraction_count", "ignored_legs", "pivot_proximity_band"]

# String column.
STR_COLUMNS = ["execution_state"]


def _select_body() -> str:
    """The transform's SELECT — the view body after the ``AS`` marker."""
    sql = TRANSFORM.read_text()
    assert "\nAS\n" in sql, "transform lost its AS/body split"
    return sql.split("\nAS\n", 1)[1].strip().rstrip(";").strip()


def _bars_by_ticker(client) -> dict:
    """The same bars the transform reads: FINAL, ascending by date."""
    rows = client.query(
        """SELECT ticker, date, toFloat64(assumeNotNull(high)), toFloat64(assumeNotNull(low)),
                  toFloat64(assumeNotNull(close)), toFloat64(assumeNotNull(volume)),
                  toFloat64(assumeNotNull(avg_vol_50d)), toFloat64(assumeNotNull(atr_14)),
                  toFloat64(assumeNotNull(sma200d))
           FROM screener_price_tech_daily FINAL"""
    ).result_rows
    bars: dict = {}
    for row in rows:
        bars.setdefault(row[0], []).append(row[1:])
    for ticker in bars:
        bars[ticker].sort(key=lambda x: x[0])
    return bars


def _reference_state(bars, idx: int):
    dates = [x[0] for x in bars]
    return vcp.state_at(
        dates, [x[1] for x in bars], [x[2] for x in bars], idx,
        threshold=THRESHOLD,
        closes=[x[3] for x in bars],
        volumes=[x[4] for x in bars],
        avg_vol_50d=[x[5] for x in bars],
        atr_14=[x[6] for x in bars],
        sma200=bars[idx][7],
        # The transform's leg_volume_ratios are stock-relative in v1; the market-neutral division is a
        # documented follow-up, so the oracle must be called the same way or it is not the same question.
        market_volumes=None,
    )


def _compare(sql_row: dict, ref, label: str) -> None:
    for column in INT_COLUMNS + STR_COLUMNS:
        assert sql_row[column] == getattr(ref, column), f"{label}: {column}: {sql_row[column]} != {getattr(ref, column)}"
    for column, tolerance in FLOAT_COLUMNS.items():
        got, want = sql_row[column], getattr(ref, column)
        if want is None or got is None:
            assert got is None and want is None, f"{label}: {column}: {got} != {want}"
        else:
            assert abs(float(got) - float(want)) < tolerance, f"{label}: {column}: {got} != {want}"
    for column in FLAG_COLUMNS:
        assert bool(sql_row[column]) is bool(getattr(ref, column)), f"{label}: {column}: {sql_row[column]} != {getattr(ref, column)}"
    assert [round(x, 3) for x in sql_row["contraction_depths"]] == [round(x, 3) for x in ref.depths], f"{label}: contraction_depths"
    assert len(sql_row["leg_depths"]) == len(ref.leg_depths_all), f"{label}: leg_depths length"
    assert list(sql_row["leg_days"]) == list(ref.leg_days), f"{label}: leg_days"


def test_sql_matches_the_reference_over_the_fixture_window(db_client) -> None:
    """Every published column, every row the transform would emit for the window."""
    bars = _bars_by_ticker(db_client)
    assert bars, "fixture spine is empty — run sigmarail-populate so it populates sigmarail_test"
    result = db_client.query(_select_body(), parameters=WINDOW)
    columns = result.column_names
    rows = result.result_rows
    assert rows, "the transform emitted nothing for the fixture window"
    compared = 0
    for row in rows:
        sql_row = dict(zip(columns, row))
        ticker, date = sql_row["ticker"], sql_row["date"]
        ticker_bars = bars.get(ticker)
        if not ticker_bars:
            continue
        idx = next((i for i, x in enumerate(ticker_bars) if x[0] == date), None)
        if idx is None:
            continue
        _compare(sql_row, _reference_state(ticker_bars, idx), f"{ticker} {date}")
        compared += 1
    assert compared > 1000, f"only {compared} rows compared — check the fixture window"


def test_wide_bar_known_answer(db_client) -> None:
    """Three bars, one of which reverses in both directions at once.

    This is the minimum shape that broke the fold: condition 1 tested a stale running low, so the wide
    bar fell through to the high-confirmation and confirmed a high at itself instead of confirming the
    earlier low. Kept as a case of its own because the whole-window test cannot say *why* it failed.
    """
    ticker = "ZZTEST"
    db_client.command("ALTER TABLE screener_price_tech_daily DELETE WHERE ticker = %(t)s", parameters={"t": ticker})
    db_client.command(
        """INSERT INTO screener_price_tech_daily
           (ticker, date, high, low, close, volume, avg_vol_50d, atr_14, sma200d)
           VALUES (%(t)s,'2021-03-01',13.65,12.96,13.00,1000000,1000000,0.5,10),
                  (%(t)s,'2021-03-02',13.44,13.09,13.20,1000000,1000000,0.5,10),
                  (%(t)s,'2021-03-03',13.24,12.59,12.70,1000000,1000000,0.5,10)""",
        parameters={"t": ticker},
    )
    try:
        bars = [(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7]) for x in
                db_client.query(
                    """SELECT date, toFloat64(assumeNotNull(high)), toFloat64(assumeNotNull(low)),
                              toFloat64(assumeNotNull(close)), toFloat64(assumeNotNull(volume)),
                              toFloat64(assumeNotNull(avg_vol_50d)), toFloat64(assumeNotNull(atr_14)),
                              toFloat64(assumeNotNull(sma200d))
                       FROM screener_price_tech_daily FINAL WHERE ticker = %(t)s ORDER BY date""",
                    parameters={"t": ticker},
                ).result_rows]
        assert len(bars) == 3, f"expected 3 scratch bars, found {len(bars)}"
        result = db_client.query(_select_body(), parameters={"chunk_start_date": "2021-03-01", "chunk_end_date": "2021-03-31"})
        columns = result.column_names
        rows = [dict(zip(columns, r)) for r in result.result_rows if dict(zip(columns, r))["ticker"] == ticker]
        assert rows, "the transform emitted no row for the scratch ticker"
        last = max(rows, key=lambda r: r["date"])
        _compare(last, _reference_state(bars, 2), f"{ticker} {last['date']}")
        # What regressed here, concretely: with the stale-extreme bug the SQL found a high pivot at
        # bar 1 AND a low at bar 3, i.e. one completed contraction. The reference confirms only the low,
        # no leg completes, so there is no base and therefore no pivot level — count 0, line NULL.
        assert last["contraction_count"] == 0, f"expected no completed leg, got {last['contraction_count']} (depths {last['contraction_depths']})"
        assert last["pivot_line"] is None, f"expected no pivot level without a base, got {last['pivot_line']}"
    finally:
        db_client.command("ALTER TABLE screener_price_tech_daily DELETE WHERE ticker = %(t)s", parameters={"t": ticker})
