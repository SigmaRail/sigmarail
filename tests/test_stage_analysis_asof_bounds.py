"""Guard stage-analysis ASOF inputs against wide or future-dated scans."""

from __future__ import annotations

from pathlib import Path


TRANSFORM = Path(__file__).parents[1] / "src" / "sigmarail" / "sql" / "schema" / "83-schema-stage_analysis.sql"


def _asof_input(sql: str, alias: str) -> str:
    """Return one wrapped ASOF source subquery, including its FROM/WHERE."""
    end = sql.index(f") AS {alias} ON")
    start = sql.rindex("ASOF LEFT JOIN (", 0, end)
    return sql[start:end]


def test_weekly_asof_sources_project_consumed_columns_with_causal_chunk_bounds() -> None:
    sql = TRANSFORM.read_text(encoding="utf-8")

    weekly = _asof_input(sql, "weekly")
    assert "FROM weekly_derived_inputs" in weekly
    assert "stage_code" in weekly
    assert "sma30w_slope" in weekly
    assert "sma50w_slope" in weekly
    assert "SELECT *" not in weekly
    assert "stock.date >= weekly.available_date" in sql

    weekly_sma = _asof_input(sql, "weekly_sma")
    assert "FROM weekly_sma_inputs" in weekly_sma
    for column in ("sma10w", "sma30w", "sma50w"):
        assert column in weekly_sma
    assert "SELECT *" not in weekly_sma
    assert "stock.date >= weekly_sma.available_date" in sql


def test_weekly_asof_inputs_use_bounded_recent_rows_and_exact_sparse_ticker_seed() -> None:
    sql = TRANSFORM.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert '"chunk_size":"3m"' in sql
    assert "FROM weekly_metrics_derived FINAL" in sql
    assert "FROM weekly_metrics FINAL" in sql
    assert sql.count("date >= addDays(toDate({chunk_start_date:String}), -25)") == 2
    assert sql.count("date <= addDays(toDate({chunk_end_date:String}), -4)") == 2
    assert sql.count("date < addDays(toDate({chunk_start_date:String}), -25)") == 2
    assert "ticker IN (SELECT ticker FROM weekly_derived_missing)" in sql
    assert "ticker IN (SELECT ticker FROM weekly_sma_missing)" in sql
    assert sql.count("argMax(tuple(date,") == 2
    assert sql.count("WHERE recent.available_date = toDate(0)") == 2
    assert "chunk_stock_first" in sql
    assert "stock.first_stock_date >= recent.available_date" in sql
    assert "ORDER BY rs.performance_3m ASC, stock.ticker ASC" in normalized
    assert "weekly_derived_recent\n    UNION ALL" in sql
    assert "weekly_sma_recent\n    UNION ALL" in sql
    assert "FROM daily_metrics FINAL" in sql
    assert "LEFT JOIN daily_metrics_derived AS derived FINAL" in sql


def test_classification_asof_source_stops_at_chunk_end_without_changing_asof_key() -> None:
    sql = TRANSFORM.read_text(encoding="utf-8")
    classification = _asof_input(sql, "cls")

    assert "SELECT ticker, date, sector" in classification
    assert "FROM ticker_classification_daily" in classification
    assert "WHERE date <= toDate({chunk_end_date:String})" in classification
    assert "chunk_start_date" not in classification
    assert "stock.date >= cls.date" in sql
