"""
Sharadar-only market_context_daily integration checks.

Runs against the explicitly enabled disposable sigmarail_test database.
"""

from __future__ import annotations

import os

import clickhouse_connect
import pytest

from sigmarail.database import load_schema
from sigmarail.populate import DataPopulator
from sigmarail.transform_sql import discover_transform_specs

# Sources needed before 110-market-context-daily, in transform dependency order.
MARKET_CONTEXT_SOURCES = [
    "broad_market_breadth",
    "broad_market_breadth_weekly",
    "market_trend_template",
    "enhanced_bear_market_signals",
    "market_regime_signals",
    "market_regime_signals_daily",
]

MARKET_CONTEXT_METRICS = MARKET_CONTEXT_SOURCES + ["market_context_daily"]


def _populate_start_end() -> tuple[str, str]:
    start = os.environ.get("SIGMARAIL_TEST_POPULATE_START", "2021-01-01")
    end = os.environ.get("SIGMARAIL_TEST_POPULATE_END", "2024-12-31")
    return start, end


def _table_exists(client: clickhouse_connect.driver.Client, name: str) -> bool:
    db = str(client.query("SELECT currentDatabase()").result_rows[0][0])
    n = int(
        client.query(
            "SELECT count() FROM system.tables WHERE database = {db:String} AND name = {name:String}",
            parameters={"db": db, "name": name},
        ).result_rows[0][0]
    )
    return n == 1


def _count(client: clickhouse_connect.driver.Client, table: str) -> int:
    return int(client.query(f"SELECT count() FROM {table}").result_rows[0][0])


def test_populate_includes_market_context_daily() -> None:
    targets = {spec.target for spec in discover_transform_specs() if spec.target}
    assert "market_context_daily" in targets


def test_market_context_daily_schema_and_parity(
    global_client: clickhouse_connect.driver.Client,
) -> None:
    """
    Ensure the market context materialization agrees with its Sharadar-derived source.
    """
    if not _table_exists(global_client, "market_context_daily"):
        ok_schema = load_schema()
        assert ok_schema, "load_schema failed while applying market_context_daily DDL"
    assert _table_exists(global_client, "market_context_daily"), (
        "market_context_daily missing after load_schema"
    )

    mrs_count = _count(global_client, "market_regime_signals_daily")
    if mrs_count == 0:
        start, end = _populate_start_end()
        pop = DataPopulator()
        ok = pop.populate_metrics(
            start_date=start,
            end_date=end,
            metrics_to_process=MARKET_CONTEXT_SOURCES,
            force_refresh=True,
        )
        if not ok:
            pytest.skip(
                "market_regime_signals_daily empty and regime source populate failed; "
                "cannot exercise market_context_daily"
            )
        mrs_count = _count(global_client, "market_regime_signals_daily")
        if mrs_count == 0:
            pytest.skip(
                "market_regime_signals_daily still empty after source populate; "
                "skipping market_context_daily data assertions"
            )

    ctx_count = _count(global_client, "market_context_daily")
    if ctx_count == 0:
        start, end = _populate_start_end()
        pop = DataPopulator()
        ok_all = pop.populate_metrics(
            start_date=start,
            end_date=end,
            metrics_to_process=MARKET_CONTEXT_METRICS,
        )
        assert ok_all, (
            f"Failed populate of market_context sources+target "
            f"(range={start}..{end})"
        )
        ctx_count = _count(global_client, "market_context_daily")

    assert ctx_count > 0, "market_context_daily is empty after populating the core sources"

    overlap = global_client.query(
        """
        SELECT c.date, c.spy_close, m.spy_close
        FROM market_context_daily AS c FINAL
        INNER JOIN market_regime_signals_daily AS m FINAL USING (date)
        ORDER BY c.date DESC
        LIMIT 5
        """
    ).result_rows
    assert overlap, "market context and its Sharadar-derived source have no overlapping dates"
    for date, context_close, source_close in overlap:
        assert context_close == pytest.approx(float(source_close), rel=1e-7, abs=1e-8), (
            f"SPY close mismatch on {date}: context={context_close} source={source_close}"
        )
