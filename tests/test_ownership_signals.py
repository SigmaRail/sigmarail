"""Golden tests for ownership_signals_daily (Sharadar SF2/SF3A PIT rules)."""

from __future__ import annotations

import logging
from datetime import date

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def ownership_table_exists(global_client) -> bool:
    rows = global_client.query("SHOW TABLES LIKE 'ownership_signals_daily'")
    return len(rows.result_rows) > 0


def _row(client, ticker: str, session: str) -> dict | None:
    q = """
        SELECT
            ticker,
            date,
            inst_calendardate,
            inst_public_asof_date,
            inst_calendardate_complete,
            inst_shrholders,
            inst_shrholders_qoq_delta,
            inst_sponsor_trend,
            insider_cluster_buy_flag,
            insider_sentiment_90d,
            insider_open_buys_90d,
            insider_open_sells_90d,
            insider_last_filingdate
        FROM ownership_signals_daily FINAL
        WHERE ticker = %(ticker)s AND date = toDate(%(session)s)
        LIMIT 1
    """
    result = client.query(q, parameters={"ticker": ticker, "session": session})
    if not result.result_rows:
        return None
    return dict(zip(result.column_names, result.result_rows[0]))


class TestOwnershipSignalsSchema:
    def test_schema_exists(self, global_client, ownership_table_exists):
        if not ownership_table_exists:
            pytest.skip("ownership_signals_daily not deployed")
        desc = global_client.query("DESCRIBE TABLE ownership_signals_daily")
        cols = {r[0] for r in desc.result_rows}
        for needle in (
            "inst_calendardate",
            "inst_public_asof_date",
            "inst_data_lag_days",
            "insider_sentiment_90d",
            "insider_cluster_buy_flag",
        ):
            assert needle in cols, f"missing column {needle}"


class TestOwnershipSignalsGolden:
    """Prod-validated tickers; skip when table empty or ticker absent."""

    def test_hwm_pit_q3_before_q4_public(self, global_client, ownership_table_exists):
        if not ownership_table_exists:
            pytest.skip("ownership_signals_daily not deployed")
        row = _row(global_client, "HWM", "2026-01-15")
        if row is None:
            pytest.skip("HWM 2026-01-15 not populated")
        assert row["inst_calendardate"] == date(2025, 9, 30), (
            "Before 45d lag after Q4, must stay on Q3 2025-09-30"
        )
        assert row["inst_calendardate"] != date(2025, 12, 31)

    def test_hwm_q4_public_after_lag(self, global_client, ownership_table_exists):
        if not ownership_table_exists:
            pytest.skip("ownership_signals_daily not deployed")
        row = _row(global_client, "HWM", "2026-02-20")
        if row is None:
            pytest.skip("HWM 2026-02-20 not populated")
        assert row["inst_calendardate"] == date(2025, 12, 31)
        if row["inst_shrholders_qoq_delta"]:
            assert row["inst_shrholders_qoq_delta"] >= 50, "HWM Q3→Q4 ~+97 holders"

    def test_smmt_cluster_buy_flag(self, global_client, ownership_table_exists):
        if not ownership_table_exists:
            pytest.skip("ownership_signals_daily not deployed")
        row = _row(global_client, "SMMT", "2026-06-12")
        if row is None:
            pytest.skip("SMMT 2026-06-12 not populated")
        assert row["insider_cluster_buy_flag"] == 1

    def test_insider_pit_no_future_filingdates(self, global_client, ownership_table_exists):
        if not ownership_table_exists:
            pytest.skip("ownership_signals_daily not deployed")
        bad = global_client.query(
            """
            SELECT count() AS n
            FROM ownership_signals_daily FINAL
            WHERE insider_last_filingdate IS NOT NULL
              AND insider_last_filingdate > date
            """
        )
        assert bad.result_rows[0][0] == 0


class TestScreenerOwnershipJoin:
    """screener_ownership_daily is the L7 delivery projection for ownership cols.

    The retired daily_screener spine no longer exists; ownership signals ship
    through the screener_ownership_daily satellite (schema 180 / transform 124).
    """

    TABLE = "screener_ownership_daily"

    def test_screener_has_ownership_columns(self, global_client):
        exists = global_client.query(
            f"SHOW TABLES LIKE '{self.TABLE}'"
        ).result_rows
        if not exists:
            pytest.skip(f"{self.TABLE} not deployed")
        desc = global_client.query(f"DESCRIBE TABLE {self.TABLE}")
        cols = {r[0] for r in desc.result_rows}
        for needle in (
            "inst_shrholders_qoq_delta",
            "inst_sponsor_trend",
            "insider_sentiment_90d",
            "insider_cluster_buy_flag",
        ):
            assert needle in cols, f"{self.TABLE} missing {needle}"

    def test_hwm_screener_pit_matches(self, global_client):
        exists = global_client.query(
            f"SHOW TABLES LIKE '{self.TABLE}'"
        ).result_rows
        if not exists:
            pytest.skip(f"{self.TABLE} not deployed")
        row = global_client.query(
            f"""
            SELECT inst_calendardate, inst_shrholders_qoq_delta
            FROM {self.TABLE} FINAL
            WHERE ticker = 'HWM' AND date = toDate('2026-02-20')
            LIMIT 1
            """
        )
        if not row.result_rows:
            pytest.skip("HWM screener row not populated")
        cal, delta = row.result_rows[0]
        if cal is not None:
            assert str(cal)[:10] == "2025-12-31"
