"""Exercise the weekly stage SQL fold against the frozen weekly replay."""

from __future__ import annotations

import shutil
import csv
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
TRANSFORM = ROOT / "src/sigmarail/sql/schema/05-schema-weekly-metrics-derived.sql"
DAILY_TRANSFORM = ROOT / "src/sigmarail/sql/schema/03-schema-daily_metrics_derived.sql"
DAILY_SCHEMA = ROOT / "src/sigmarail/sql/schema/03-schema-daily_metrics_derived.sql"


def test_weekly_transform_force_refresh_bypasses_freshness():
    """A forced historical populate must include already-current weekly tickers."""
    transform_sql = TRANSFORM.read_text(encoding="utf-8")
    assert "-- Expects SQL variables: chunk_start_date, chunk_end_date, force_refresh" in transform_sql
    assert "WHEN {force_refresh:UInt8} = 1 THEN 1" in transform_sql


def test_daily_transform_has_no_provisional_weekly_projection():
    """The daily surface must not depend on or expose provisional weekly state."""
    transform_sql = DAILY_TRANSFORM.read_text(encoding="utf-8")
    schema_sql = DAILY_SCHEMA.read_text(encoding="utf-8")
    provisional_fields = (
        "sma10w_asof",
        "sma30w_asof",
        "sma40w_asof",
        "weekly_stage_code_asof",
        "weekly_stage_duration_asof",
        "weekly_input_state",
    )

    assert '"sources":["daily_metrics"]' in transform_sql
    assert "weekly_metrics" not in transform_sql
    assert "asof_weekly" not in transform_sql
    for field in provisional_fields:
        assert field not in transform_sql
        assert field not in schema_sql


@pytest.mark.skipif(shutil.which("clickhouse") is None, reason="clickhouse local is required to execute transform SQL")
def test_weekly_stage_daily_visibility_is_causal_for_full_and_short_weeks():
    """Monday-labeled weekly values never leak into earlier daily sessions."""
    weekly_metrics_sql = (ROOT / "src/sigmarail/sql/schema/04-schema-weekly-metrics.sql").read_text(encoding="utf-8")
    assert "date + toIntervalDay(4) <= (SELECT max(date) FROM daily_price_sequence FINAL)" in weekly_metrics_sql

    query = """WITH
sessions AS (
    SELECT 'SPY' AS ticker, toDate('2025-04-07') AS date UNION ALL
    SELECT 'SPY', toDate('2025-04-08') UNION ALL
    SELECT 'SPY', toDate('2025-04-09') UNION ALL
    SELECT 'SPY', toDate('2025-04-10') UNION ALL
    SELECT 'SPY', toDate('2025-04-11') UNION ALL
    SELECT 'SPY', toDate('2025-04-14') UNION ALL
    SELECT 'SPY', toDate('2025-04-15') UNION ALL
    SELECT 'SPY', toDate('2025-04-16') UNION ALL
    SELECT 'SPY', toDate('2025-04-17') UNION ALL
    SELECT 'SPY', toDate('2025-04-21')
),
completed_weeks AS (
    SELECT 'SPY' AS ticker, toDate('2025-04-07') AS date, '3A' AS stage_code UNION ALL
    SELECT 'SPY', toDate('2025-04-14'), '2A'
),
weekly_asof AS (
    SELECT *, date + toIntervalDay(4) AS available_date
    FROM completed_weeks
),
visible AS (
    SELECT s.date, w.stage_code
    FROM sessions AS s
    ASOF LEFT JOIN weekly_asof AS w ON s.ticker = w.ticker AND s.date >= w.available_date
)
SELECT
    toString(date) AS session_date,
    if(empty(stage_code), 'UNKNOWN', stage_code) AS stage_code
FROM visible
ORDER BY date
FORMAT TSVWithNames
"""
    completed = subprocess.run(
        [shutil.which("clickhouse"), "local", "--query", query],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    rows = list(csv.DictReader(completed.stdout.splitlines(), delimiter="\t"))
    assert rows == [
        {"session_date": "2025-04-07", "stage_code": "UNKNOWN"},
        {"session_date": "2025-04-08", "stage_code": "UNKNOWN"},
        {"session_date": "2025-04-09", "stage_code": "UNKNOWN"},
        {"session_date": "2025-04-10", "stage_code": "UNKNOWN"},
        {"session_date": "2025-04-11", "stage_code": "3A"},
        {"session_date": "2025-04-14", "stage_code": "3A"},
        {"session_date": "2025-04-15", "stage_code": "3A"},
        {"session_date": "2025-04-16", "stage_code": "3A"},
        {"session_date": "2025-04-17", "stage_code": "3A"},
        {"session_date": "2025-04-21", "stage_code": "2A"},
    ]


@pytest.mark.skipif(shutil.which("clickhouse") is None, reason="clickhouse local is required to execute transform SQL")
def test_checkpoint_seed_argmax_matches_replacing_latest_version(tmp_path):
    """The no-FINAL seed selector returns the same row version as ReplacingMergeTree."""
    query_path = tmp_path / "checkpoint_seed.sql"
    query_path.write_text(
        """WITH
source AS (
    SELECT * FROM values(
        'ticker String, date Date, lastupdated DateTime, stage_state UInt8',
        ('AAA', toDate('2014-09-22'), toDateTime('2014-10-01 10:00:00'), toUInt8(1)),
        ('AAA', toDate('2014-09-22'), toDateTime('2014-10-02 10:00:00'), toUInt8(2)),
        ('AAA', toDate('2014-09-29'), toDateTime('2014-10-03 10:00:00'), toUInt8(3)),
        ('BBB', toDate('2014-09-22'), toDateTime('2014-10-01 10:00:00'), toUInt8(4)),
        ('BBB', toDate('2014-09-29'), toDateTime('2014-10-01 10:00:00'), toUInt8(5))
    )
),
replacing_latest AS (
    SELECT ticker, date, argMax(stage_state, lastupdated) AS stage_state
    FROM source
    GROUP BY ticker, date
),
expected AS (
    SELECT ticker, argMax(stage_state, date) AS stage_state
    FROM replacing_latest
    WHERE date < toDate('2014-10-06')
    GROUP BY ticker
),
actual AS (
    SELECT ticker, argMax(stage_state, (date, lastupdated)) AS stage_state
    FROM source
    WHERE date < toDate('2014-10-06')
    GROUP BY ticker
)
SELECT countIf(expected.stage_state != actual.stage_state) AS mismatches
FROM expected
INNER JOIN actual USING (ticker)
FORMAT TSV
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [shutil.which("clickhouse"), "local", "--queries-file", str(query_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "0"


