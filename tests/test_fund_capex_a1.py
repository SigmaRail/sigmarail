"""
Sharadar CapEx checks for mrt/art L1, derived ratios L2, and daily_fundamentals.

Runs against the explicitly enabled disposable sigmarail_test database.
"""

from __future__ import annotations

import os

import clickhouse_connect
import pytest

from sigmarail.database import load_schema
from sigmarail.populate import DataPopulator
from sigmarail.transform_sql import discover_transform_specs

TICKER = "AAPL"

CAPEX_TABLES = (
    "art",
    "art_derived",
    "mrt",
    "mrt_derived",
    "daily_fundamentals",
)

CAPEX_METRICS = [
    "mrt",
    "art",
    "mrt_derived",
    "art_derived",
    "daily_fundamentals",
]


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


def _has_column(client: clickhouse_connect.driver.Client, table: str, column: str) -> bool:
    db = str(client.query("SELECT currentDatabase()").result_rows[0][0])
    n = int(
        client.query(
            """
            SELECT count()
            FROM system.columns
            WHERE database = {db:String} AND table = {t:String} AND name = {c:String}
            """,
            parameters={"db": db, "t": table, "c": column},
        ).result_rows[0][0]
    )
    return n == 1


def _count(client: clickhouse_connect.driver.Client, table: str) -> int:
    return int(client.query(f"SELECT count() FROM {table}").result_rows[0][0])


@pytest.fixture(scope="module")
def ensure_capex_populated(global_client: clickhouse_connect.driver.Client) -> None:
    """
    Ensure CapEx schemas exist and CapEx path is populated for the fixture window.
    """
    need_schema = (
        not _table_exists(global_client, "art")
        or not _table_exists(global_client, "art_derived")
        or not _has_column(global_client, "mrt", "capex")
        or not _has_column(global_client, "mrt_derived", "capex_to_ocf")
        or not _has_column(global_client, "daily_fundamentals", "mrt_capex")
        or not _has_column(global_client, "daily_fundamentals", "art_capex")
    )
    if need_schema:
        ok_schema = load_schema()
        assert ok_schema, "load_schema failed while applying CapEx/ART DDL"
        assert _table_exists(global_client, "art"), "art missing after load_schema"
        assert _table_exists(global_client, "art_derived"), "art_derived missing after load_schema"
        assert _has_column(global_client, "mrt", "capex"), "mrt.capex missing after load_schema"
        assert _has_column(global_client, "daily_fundamentals", "mrt_capex")

    need_populate = (
        _count(global_client, "art") == 0
        or _count(global_client, "art_derived") == 0
        or int(
            global_client.query(
                "SELECT countIf(capex IS NOT NULL OR ncfo IS NOT NULL) FROM mrt FINAL WHERE ticker = {t:String}",
                parameters={"t": TICKER},
            ).result_rows[0][0]
        )
        == 0
    )
    if not need_populate:
        # Still refresh if L4 CapEx cols empty for AAPL
        df_capex = int(
            global_client.query(
                """
                SELECT countIf(mrt_capex IS NOT NULL OR art_capex IS NOT NULL)
                FROM daily_fundamentals FINAL
                WHERE ticker = {t:String}
                """,
                parameters={"t": TICKER},
            ).result_rows[0][0]
        )
        if df_capex > 0:
            return

    start, end = _populate_start_end()
    pop = DataPopulator()
    ok = pop.populate_metrics(
        start_date=start,
        end_date=end,
        metrics_to_process=CAPEX_METRICS,
        force_refresh=True,
    )
    assert ok, (
        f"Failed to populate CapEx L1/L2/L4 metrics in test mode "
        f"(range={start}..{end}, metrics={CAPEX_METRICS})"
    )


def test_populate_includes_art_and_capex_metrics() -> None:
    targets = {spec.target for spec in discover_transform_specs() if spec.target}
    assert {"art", "art_derived", "mrt", "mrt_derived"} <= targets


def test_sf1_art_dimension_present(
    global_client: clickhouse_connect.driver.Client, ensure_capex_populated: None
) -> None:
    n = int(
        global_client.query(
            """
            SELECT count()
            FROM sf1 FINAL
            WHERE ticker = {t:String} AND dimension = 'ART'
            """,
            parameters={"t": TICKER},
        ).result_rows[0][0]
    )
    assert n > 0, f"test SF1 fixture missing ART rows for {TICKER}"


def test_mrt_capex_or_ncfo_non_null(
    global_client: clickhouse_connect.driver.Client, ensure_capex_populated: None
) -> None:
    row = global_client.query(
        """
        SELECT capex, ncfo, fcf
        FROM mrt FINAL
        WHERE ticker = {t:String}
          AND (capex IS NOT NULL OR ncfo IS NOT NULL)
        ORDER BY date DESC
        LIMIT 1
        """,
        parameters={"t": TICKER},
    ).result_rows
    assert row, f"{TICKER} mrt has no non-null capex/ncfo after CapEx populate"
    capex, ncfo, fcf = row[0]
    if capex is not None:
        assert float(capex) < 0, f"SF1 CapEx is typically negative; got {capex}"
    if capex is not None and ncfo is not None and fcf is not None:
        # Golden: fcf ≈ ncfo + capex (CapEx signed negative)
        assert float(fcf) == pytest.approx(float(ncfo) + float(capex), rel=1e-3, abs=1.0)


def test_art_l1_capex_populated(
    global_client: clickhouse_connect.driver.Client, ensure_capex_populated: None
) -> None:
    n = int(
        global_client.query(
            """
            SELECT count()
            FROM art FINAL
            WHERE ticker = {t:String}
              AND (capex IS NOT NULL OR ncfo IS NOT NULL)
            """,
            parameters={"t": TICKER},
        ).result_rows[0][0]
    )
    assert n > 0, f"{TICKER} art CapEx/ncfo empty after populate"


def test_mrt_derived_capex_ratios(
    global_client: clickhouse_connect.driver.Client, ensure_capex_populated: None
) -> None:
    n = int(
        global_client.query(
            """
            SELECT count()
            FROM mrt_derived FINAL
            WHERE ticker = {t:String}
              AND capex_to_ocf IS NOT NULL
            """,
            parameters={"t": TICKER},
        ).result_rows[0][0]
    )
    assert n > 0, f"{TICKER} mrt_derived.capex_to_ocf empty"


def test_daily_fundamentals_exposes_mrt_and_art_capex(
    global_client: clickhouse_connect.driver.Client, ensure_capex_populated: None
) -> None:
    cols = set(
        global_client.query_df("DESCRIBE daily_fundamentals")["name"].astype(str).tolist()
    )
    for col in ("mrt_capex", "mrt_ncfo", "mrt_capex_to_ocf", "art_capex", "art_ncfo", "art_capex_to_ocf"):
        assert col in cols, f"daily_fundamentals missing {col}"

    row = global_client.query(
        """
        SELECT mrt_capex, art_capex, mrt_capex_to_ocf, art_capex_to_ocf
        FROM daily_fundamentals FINAL
        WHERE ticker = {t:String}
          AND (mrt_capex IS NOT NULL OR art_capex IS NOT NULL)
        ORDER BY date DESC
        LIMIT 1
        """,
        parameters={"t": TICKER},
    ).result_rows
    assert row, f"{TICKER} daily_fundamentals CapEx fields empty after populate"
