"""Test-first: 4-for-1 splice across 5y window vs frozen older closeunadj."""

from pathlib import Path

import pandas as pd
import pytest

from sigmarail.splice_price_history import (
    SpliceFactor,
    build_splice_insert_sql,
    compute_splice_factor,
    factors_from_download_vs_ch,
)


def test_compute_splice_factor_four_for_one():
    """After a 4-for-1, restated close is 1/4 of the pre-restatement CH close."""
    fac = compute_splice_factor(
        ch_close=400.0,
        ch_closeadj=400.0,
        new_close=100.0,
        new_closeadj=100.0,
        ticker="AAPL",
        splice_date="2021-01-04",
    )
    assert fac is not None
    assert fac.needs_splice
    assert fac.px_factor == pytest.approx(0.25)
    assert fac.tr_factor == pytest.approx(0.25)


def test_compute_splice_factor_noop_when_aligned():
    fac = compute_splice_factor(
        ch_close=100.0,
        ch_closeadj=99.0,
        new_close=100.0,
        new_closeadj=99.0,
        ticker="AAPL",
        splice_date="2021-01-04",
    )
    assert fac is not None
    assert not fac.needs_splice


def test_factors_from_download_vs_ch_uses_oldest_date_per_ticker():
    new_df = pd.DataFrame(
        [
            {"ticker": "AAPL", "date": "2021-01-05", "close": 101.0, "closeadj": 101.0},
            {"ticker": "AAPL", "date": "2021-01-04", "close": 100.0, "closeadj": 100.0},
            {"ticker": "MSFT", "date": "2021-01-04", "close": 50.0, "closeadj": 50.0},
        ]
    )
    # CH still on pre-split basis at the overlap date for AAPL only.
    ch_rows = [
        ("AAPL", "2021-01-04", 400.0, 400.0),
        ("MSFT", "2021-01-04", 50.0, 50.0),
    ]
    factors = factors_from_download_vs_ch(new_df, ch_rows)
    assert len(factors) == 1
    assert factors[0].ticker == "AAPL"
    assert factors[0].splice_date == "2021-01-04"
    assert factors[0].px_factor == pytest.approx(0.25)


def test_build_splice_insert_sql_scales_ohlc_leaves_closeunadj():
    sql = build_splice_insert_sql(
        "sep",
        [
            SpliceFactor(
                ticker="AAPL",
                splice_date="2021-01-04",
                px_factor=0.25,
                tr_factor=0.25,
            )
        ],
    )
    assert sql is not None
    assert "INSERT INTO sep" in sql
    assert "p.open * f.px_factor" in sql
    assert "p.volume / f.px_factor" in sql
    assert "p.closeadj * f.tr_factor" in sql
    assert "p.closeunadj" in sql
    assert "p.closeunadj *" not in sql
    assert "p.date < f.splice_date" in sql
    assert "'AAPL'" in sql


def test_four_for_one_older_bar_math():
    """Older split-adj close scales; closeunadj frozen (exchange print)."""
    fac = compute_splice_factor(
        ch_close=400.0,
        ch_closeadj=380.0,
        new_close=100.0,
        new_closeadj=95.0,
        ticker="AAPL",
        splice_date="2021-01-04",
    )
    assert fac is not None
    older_close = 800.0
    older_closeunadj = 800.0
    older_closeadj = 760.0
    older_volume = 1_000_000.0

    scaled_close = older_close * fac.px_factor
    scaled_vol = older_volume / fac.px_factor
    scaled_adj = older_closeadj * fac.tr_factor

    assert scaled_close == pytest.approx(200.0)
    assert scaled_vol == pytest.approx(4_000_000.0)
    assert scaled_adj == pytest.approx(190.0)
    # closeunadj must not be multiplied by px_factor
    assert older_closeunadj == pytest.approx(800.0)
