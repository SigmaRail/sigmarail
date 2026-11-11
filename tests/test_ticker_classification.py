"""E2E for ticker_classification_daily PIT snapshots (VeraProjects#164).

`tickers` is current-state, so joining it stamps today's labels onto all
history. ticker_classification_daily snapshots labels per (ticker, date); a
1970-01-01 seed carries the earliest-known values and daily snapshots accrue
true PIT going forward. Tests assert ASOF joins resolve the last-known label
per date and that transform 133 emits one row per daily_metrics ticker/date.

CLS_HIST never appears in daily_metrics, so the transform cannot overwrite its
seeded label history — ASOF assertions stay order-independent.
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from sigmarail.database import execute_sql_file, get_project_root

CLS_DATE1 = date(1990, 1, 4)
CLS_DATE2 = date(1990, 1, 5)
CHUNK = ("1990-01-01", "1990-01-31")
TICKER = "CLS_TEST_A"
TICKER2 = "CLS_TEST_B"
HIST = "CLS_HIST"


def _transform_path() -> Path:
    root = Path(get_project_root())
    return root / "src" / "sigmarail" / "sql" / "schema" / "205-schema-ticker_classification_daily.sql"


@pytest.fixture(scope="module")
def seeded(global_client):
    client = global_client
    root = Path(get_project_root())
    schema = root / "src" / "sigmarail" / "sql" / "schema" / "205-schema-ticker_classification_daily.sql"
    assert schema.is_file(), "missing 205 schema"
    assert execute_sql_file(schema, description=schema.name)

    for table in ("tickers", "daily_metrics", "ticker_classification_daily"):
        client.command(
            f"ALTER TABLE {table} DELETE WHERE ticker IN %(t)s",
            parameters={"t": (TICKER, TICKER2, HIST)},
        )
    stamp = datetime(1990, 1, 3)
    old_stamp = datetime(1990, 1, 1)
    client.insert(
        "tickers",
        [
            (TICKER, TICKER, "N", "Domestic", "Technology", "Semiconductors",
             "Semiconductors", "Manufacturing", "Semiconductor & Related"),
            (TICKER2, TICKER2, "N", "Domestic", "Energy", "Oil & Gas",
             "Petroleum", "Mining", "Crude Petroleum"),
        ],
        column_names=[
            "ticker", "permaticker", "isdelisted", "category",
            "sector", "industry", "famaindustry", "sicsector", "sicindustry",
        ],
    )
    client.insert(
        "daily_metrics",
        [
            (TICKER, CLS_DATE1, 10.0, stamp),
            (TICKER, CLS_DATE2, 10.5, stamp),
            (TICKER2, CLS_DATE2, 20.0, stamp),
        ],
        column_names=["ticker", "date", "close", "lastupdated"],
    )
    # Label history for CLS_HIST: 1970 seed, then a reclassification between
    # the two snapshot days (sector Energy -> Technology).
    client.insert(
        "ticker_classification_daily",
        [
            (HIST, date(1970, 1, 1), "Materials", "Minerals", "Other",
             "Mining", "Metal Mining", old_stamp),
            (HIST, CLS_DATE1, "Energy", "Oil & Gas", "Petroleum",
             "Mining", "Crude Petroleum", old_stamp),
            (HIST, CLS_DATE2, "Technology", "Semiconductors", "Semiconductors",
             "Manufacturing", "Semiconductor & Related", old_stamp),
        ],
        column_names=[
            "ticker", "date", "sector", "industry", "famaindustry",
            "sicsector", "sicindustry", "lastupdated",
        ],
    )
    return client


def test_schema_seed_covers_unknown_history(global_client) -> None:
    """The 1970-01-01 seed row gives ASOF joins a label for any date."""
    res = global_client.query(
        "SELECT count() FROM ticker_classification_daily FINAL "
        "WHERE date = toDate('1970-01-01')"
    )
    assert res.result_rows[0][0] > 0, "backfill seed missing"


def test_asof_join_returns_last_known_label(seeded) -> None:
    """ASOF join picks the most recent snapshot <= query date."""
    res = seeded.query(
        """
        SELECT d.date, c.sector
        FROM (SELECT %(t)s AS ticker, toDate(%(d1)s) AS date
              UNION ALL SELECT %(t)s, toDate(%(d2)s)) d
        ASOF LEFT JOIN ticker_classification_daily c
            ON c.ticker = d.ticker AND d.date >= c.date
        ORDER BY d.date
        """,
        parameters={"t": HIST, "d1": CLS_DATE1, "d2": CLS_DATE2},
    )
    rows = res.result_rows
    assert rows[0][1] == "Energy", f"d1 sector={rows[0][1]}"
    assert rows[1][1] == "Technology", f"d2 sector={rows[1][1]}"


def test_asof_falls_back_to_seed_for_early_dates(seeded) -> None:
    res = seeded.query(
        """
        SELECT c.sector
        FROM (SELECT %(t)s AS ticker, toDate(%(d)s) AS date) d
        ASOF LEFT JOIN ticker_classification_daily c
            ON c.ticker = d.ticker AND d.date >= c.date
        """,
        parameters={"t": HIST, "d": date(1990, 1, 2)},
    )
    assert res.result_rows[0][0] == "Materials", res.result_rows


def test_transform_emits_snapshot_rows(seeded) -> None:
    """Transform 133 emits one classification row per daily_metrics ticker/date."""
    from sigmarail.transform_sql import run_transform_file

    run_transform_file(
        seeded,
        _transform_path(),
        {"chunk_start_date": CHUNK[0], "chunk_end_date": CHUNK[1]},
    )
    res = seeded.query(
        """
        SELECT ticker, date, sector
        FROM ticker_classification_daily FINAL
        WHERE ticker IN %(t)s AND date >= %(d1)s
        ORDER BY ticker, date
        """,
        parameters={"t": (TICKER, TICKER2), "d1": CLS_DATE1},
    )
    rows = {(r[0], r[1]): r[2] for r in res.result_rows}
    # 3 daily_metrics rows in-chunk: TICKER on both dates, TICKER2 on date2.
    assert (TICKER, CLS_DATE1) in rows
    assert (TICKER, CLS_DATE2) in rows
    assert (TICKER2, CLS_DATE2) in rows
    assert (TICKER2, CLS_DATE1) not in rows
    # Labels come from the tickers join.
    assert rows[(TICKER, CLS_DATE2)] == "Technology"
    assert rows[(TICKER2, CLS_DATE2)] == "Energy"
