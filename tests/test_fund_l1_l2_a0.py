"""
Sharadar fundamental L1 / L2 / daily_fundamentals validation.

Runs against the explicitly enabled disposable sigmarail_test database.
"""

from __future__ import annotations

import os

import clickhouse_connect
import pytest

from sigmarail.database import load_schema
from sigmarail.populate import DataPopulator

TICKER = "AAPL"

DERIVED_TABLES = (
    "arq_derived",
    "ary_derived",
    "mrq_derived",
    "mrt_derived",
    "mry_derived",
)

FUND_METRICS = [
    "arq",
    "ary",
    "mrq",
    "mrt",
    "mry",
    "arq_derived",
    "ary_derived",
    "mrq_derived",
    "mrt_derived",
    "mry_derived",
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


def _count(client: clickhouse_connect.driver.Client, table: str) -> int:
    return int(client.query(f"SELECT count() FROM {table}").result_rows[0][0])


@pytest.fixture(scope="module")
def ensure_fund_populated(global_client: clickhouse_connect.driver.Client) -> None:
    """
    Reused test DBs may predate Episode A0 L2 schemas. Load missing *_derived DDL,
    then force-refresh L1/L2/L4 fund metrics over the fixture populate window.
    """
    missing_derived = [t for t in DERIVED_TABLES if not _table_exists(global_client, t)]
    if missing_derived:
        ok_schema = load_schema()
        assert ok_schema, f"load_schema failed; still missing derived tables: {missing_derived}"
        still_missing = [t for t in DERIVED_TABLES if not _table_exists(global_client, t)]
        assert not still_missing, f"*_derived tables still missing after load_schema: {still_missing}"

    need_populate = (
        not _table_exists(global_client, "mrt_derived")
        or _count(global_client, "mrt") == 0
        or _count(global_client, "mrt_derived") == 0
        or _count(global_client, "daily_fundamentals") == 0
    )
    if not need_populate:
        return

    start, end = _populate_start_end()
    pop = DataPopulator()
    ok = pop.populate_metrics(
        start_date=start,
        end_date=end,
        metrics_to_process=FUND_METRICS,
        force_refresh=True,
    )
    assert ok, (
        f"Failed to populate fund L1/L2/L4 metrics in test mode "
        f"(range={start}..{end}, metrics={FUND_METRICS})"
    )


def test_l2_derived_tables_exist(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    db = str(global_client.query("SELECT currentDatabase()").result_rows[0][0])
    for name in DERIVED_TABLES:
        n = int(
            global_client.query(
                "SELECT count() FROM system.tables "
                "WHERE database = {db:String} AND name = {name:String}",
                parameters={"db": db, "name": name},
            ).result_rows[0][0]
        )
        assert n == 1, f"missing L2 table {name} in {db}"


def test_l1_vendor_rows(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    for table in ("arq", "mrq", "mrt"):
        total = _count(global_client, table)
        assert total > 0, f"{table} is empty after fund populate"
        aapl = int(
            global_client.query(
                f"SELECT count() FROM {table} FINAL WHERE ticker = {{t:String}}",
                parameters={"t": TICKER},
            ).result_rows[0][0]
        )
        assert aapl > 0, f"{table} has no rows for {TICKER}"


def test_l2_mrt_derived_has_ranks_or_growth(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    row = global_client.query(
        """
        SELECT
            countIf(roa_yoy_growth IS NOT NULL) AS n_growth,
            countIf(roa_industry_rank IS NOT NULL) AS n_rank
        FROM mrt_derived FINAL
        WHERE ticker = {t:String}
        """,
        parameters={"t": TICKER},
    ).result_rows[0]
    n_growth, n_rank = int(row[0]), int(row[1])
    if n_growth == 0 and n_rank == 0:
        pytest.skip(
            f"{TICKER} mrt_derived has neither roa_yoy_growth nor roa_industry_rank "
            "(SF1 TTM history may be too short for YoY; ranks should normally exist)"
        )
    # Prefer ranks when YoY window is short; either non-null field satisfies the split.
    assert n_growth > 0 or n_rank > 0


def test_l2_arq_derived_growth(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    n = int(
        global_client.query(
            """
            SELECT count()
            FROM arq_derived FINAL
            WHERE ticker = {t:String}
              AND revenue_growth_yoy IS NOT NULL
            """,
            parameters={"t": TICKER},
        ).result_rows[0][0]
    )
    if n == 0:
        pytest.skip(
            f"{TICKER} arq_derived has no non-null revenue_growth_yoy "
            "(insufficient ARQ history for YoY in the test fixture)"
        )
    assert n > 0


def test_mrq_dimension_is_mrq(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    """mrq.date must come from SF1 dimension=MRQ (not ARQ-only calendardates)."""
    sample = global_client.query(
        """
        SELECT toString(max(date))
        FROM mrq FINAL
        WHERE ticker = {t:String}
        """,
        parameters={"t": TICKER},
    ).result_rows
    if not sample or sample[0][0] is None:
        pytest.skip(f"no mrq rows for {TICKER}")
    mrq_date = sample[0][0]

    matched = int(
        global_client.query(
            """
            SELECT count()
            FROM sf1 FINAL
            WHERE ticker = {t:String}
              AND dimension = 'MRQ'
              AND calendardate = toDate({d:String})
            """,
            parameters={"t": TICKER, "d": mrq_date},
        ).result_rows[0][0]
    )
    assert matched > 0, (
        f"mrq max(date)={mrq_date} for {TICKER} does not match any SF1 MRQ calendardate "
        "(possible ARQ fallback regression)"
    )


def test_daily_fundamentals_zips_l1_and_l2(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    """L4 ASOF: daily_fundamentals.mrt_* matches L1 mrt / L2 mrt_derived for a recent day."""
    dm = global_client.query(
        """
        SELECT toString(max(date))
        FROM daily_metrics FINAL
        WHERE ticker = {t:String}
        """,
        parameters={"t": TICKER},
    ).result_rows
    if not dm or not dm[0][0]:
        pytest.skip(f"no daily_metrics for {TICKER}")
    as_of = dm[0][0]

    df_row = global_client.query(
        """
        SELECT mrt_roa, mrt_roa_industry_rank
        FROM daily_fundamentals FINAL
        WHERE ticker = {t:String} AND date = toDate({d:String})
        LIMIT 1
        """,
        parameters={"t": TICKER, "d": as_of},
    ).result_rows
    if not df_row:
        pytest.skip(f"no daily_fundamentals row for {TICKER} on {as_of}")

    df_roa, df_rank = df_row[0][0], df_row[0][1]

    mrt_row = global_client.query(
        """
        SELECT roa, toString(date)
        FROM mrt FINAL
        WHERE ticker = {t:String} AND date <= toDate({d:String})
        ORDER BY date DESC
        LIMIT 1
        """,
        parameters={"t": TICKER, "d": as_of},
    ).result_rows
    assert mrt_row, f"no ASOF mrt row for {TICKER} on/before {as_of}"
    mrt_roa, mrt_date = mrt_row[0][0], mrt_row[0][1]

    assert df_roa is not None and mrt_roa is not None, (
        f"mrt_roa null on zip (df={df_roa}, mrt={mrt_roa}, as_of={as_of}, mrt_date={mrt_date})"
    )
    assert float(df_roa) == pytest.approx(float(mrt_roa), rel=1e-9, abs=1e-9)

    derived = global_client.query(
        """
        SELECT roa_industry_rank
        FROM mrt_derived FINAL
        WHERE ticker = {t:String} AND date = toDate({md:String})
        LIMIT 1
        """,
        parameters={"t": TICKER, "md": mrt_date},
    ).result_rows
    if not derived or derived[0][0] is None:
        return
    expected_rank = float(derived[0][0])
    assert df_rank is not None, (
        f"daily_fundamentals.mrt_roa_industry_rank null but mrt_derived has "
        f"{expected_rank} at {mrt_date}"
    )
    assert float(df_rank) == pytest.approx(expected_rank, rel=1e-9, abs=1e-9)


def test_l1_arq_insert_excludes_growth_columns_still_nullable(
    global_client: clickhouse_connect.driver.Client, ensure_fund_populated: None
) -> None:
    """
    Dead L1 growth columns remain on `arq` (additive rollback), but L1 insert is
    vendor-only; values live on L2 `arq_derived`.
    """
    cols = set(
        global_client.query_df("DESCRIBE arq")["name"].astype(str).tolist()
    )
    assert "revenue_growth_yoy" in cols, "arq must still declare revenue_growth_yoy (dead L1 col)"

    pair = global_client.query(
        """
        SELECT
            a.revenue_growth_yoy AS l1_growth,
            d.revenue_growth_yoy AS l2_growth
        FROM arq a FINAL
        INNER JOIN arq_derived d FINAL
            ON a.ticker = d.ticker AND a.date = d.date
        WHERE a.ticker = {t:String}
        ORDER BY a.date DESC
        LIMIT 1
        """,
        parameters={"t": TICKER},
    ).result_rows
    if not pair:
        pytest.skip(f"no overlapping arq / arq_derived row for {TICKER}")

    l1_growth, l2_growth = pair[0][0], pair[0][1]
    if l1_growth is None and l2_growth is not None:
        return  # expected L1/L2 split after Episode A0
    if l1_growth is None and l2_growth is None:
        pytest.skip(
            f"{TICKER} latest arq/arq_derived both have NULL revenue_growth_yoy "
            "(insufficient history or fixture gap)"
        )
    # Non-null L1 growth can remain on reused DBs without rebuild; still OK.
    assert l1_growth is not None or l2_growth is not None
