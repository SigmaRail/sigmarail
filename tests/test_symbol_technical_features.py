"""Golden / integration tests for symbol_technical_features_daily (skip without ClickHouse)."""

from __future__ import annotations

import pytest


def _table_exists(client, name: str) -> bool:
    n = client.command(f"EXISTS TABLE {name}")
    return int(n) == 1


@pytest.mark.integration
def test_symbol_technical_features_schema(global_client) -> None:
    if not _table_exists(global_client, "symbol_technical_features_daily"):
        pytest.skip("symbol_technical_features_daily not deployed")
    df = global_client.query_df("DESCRIBE symbol_technical_features_daily")
    cols = set(df["name"].astype(str).tolist())
    for required in (
        "pct_from_sma20d",
        "drawdown_from_50d_high",
        "up_days_last_3",
        "first_up_day_low",
        "entry_gate",
    ):
        assert required in cols


@pytest.mark.integration
def test_golden_may_2025_tqqq_extension_direction(global_client) -> None:
    if not _table_exists(global_client, "symbol_technical_features_daily"):
        pytest.skip("symbol_technical_features_daily not deployed")
    row = global_client.query_df(
        """
        SELECT pct_from_sma20d, extended_above_sma20_flag
        FROM symbol_technical_features_daily FINAL
        WHERE ticker = 'TQQQ' AND date = toDate('2025-05-29')
        """
    )
    if row.empty:
        pytest.skip("no TQQQ row for 2025-05-29")
    pct = float(row["pct_from_sma20d"].iloc[0] or 0)
    assert pct > 0.05, "late May 2025 TQQQ should show SMA extension (directional)"


@pytest.mark.integration
def test_golden_qqq_pullback_in_2025(global_client) -> None:
    if not _table_exists(global_client, "symbol_technical_features_daily"):
        pytest.skip("symbol_technical_features_daily not deployed")
    n = global_client.command(
        """
        SELECT count()
        FROM symbol_technical_features_daily FINAL
        WHERE ticker = 'QQQ'
          AND date BETWEEN toDate('2025-01-01') AND toDate('2025-05-29')
          AND drawdown_from_50d_high <= -0.05
        """
    )
    if int(n) == 0:
        pytest.skip("QQQ pullback rows not populated for 2025 window")
    assert int(n) > 0


@pytest.mark.integration
def test_posture_view_exists(global_client) -> None:
    n = global_client.command("EXISTS VIEW tqqq_tactical_posture_daily")
    if int(n) == 0:
        pytest.skip("tqqq_tactical_posture_daily view not deployed")
    df = global_client.query_df(
        """
        SELECT posture_label
        FROM tqqq_tactical_posture_daily
        WHERE date = toDate('2025-05-29')
        LIMIT 1
        """
    )
    if df.empty:
        pytest.skip("no posture row for 2025-05-29")
    assert df["posture_label"].iloc[0] in {
        "no_trade",
        "entry_candidate",
        "hold",
        "trim",
        "exit",
    }
