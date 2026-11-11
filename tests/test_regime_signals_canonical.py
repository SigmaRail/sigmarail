"""
Unit tests for `regime_signals_canonical` (Layer 1 canonical signals).

These tests are intentionally light-weight and focus on invariants:
- Table exists + expected columns present
- Normalized signals are in [0,1] and non-null over the populated test window
- Query determinism (same query -> same result)

More event-anchored tests can be added once we pin a stable fixture window and
explicit anchor dates inside the test dataset.
"""

from __future__ import annotations

import pytest
import pandas as pd
import clickhouse_connect

from sigmarail.populate import DataPopulator


NORMALIZED_COLS = [
    "s_ma200_macro",
    "s_breadth200",
    "s_breadth50",
    "s_vix",
    "s_thrust",
    "s_risk_off",
    "s_ma200_self",
    "s_ma50_self",
    "s_ma_stack_self",
    "s_stage_self",
    "s_mom_6m_self",
    "s_rvol_self",
]

RAW_COLS = [
    "s_ma200_macro_raw",
    "s_breadth200_raw",
    "s_breadth50_raw",
    "s_vix_raw",
    "s_thrust_raw",
    "s_risk_off_raw",
    "s_ma200_self_raw",
    "s_ma50_self_raw",
    "s_ma_stack_self_raw",
    "s_stage_self_raw",
    "s_mom_6m_self_raw",
    "s_rvol_self_raw",
]


def _load_sample(
    client: clickhouse_connect.driver.Client,
    *,
    start: str = "2021-01-01",
    end: str = "2024-12-31",
    limit: int = 5000,
) -> pd.DataFrame:
    cols = ["ticker", "date"] + RAW_COLS + NORMALIZED_COLS
    q = f"""
    SELECT {", ".join(cols)}
    FROM regime_signals_canonical
    WHERE date >= toDate('{start}')
      AND date <= toDate('{end}')
    ORDER BY ticker, date
    LIMIT {int(limit)}
    """
    df = client.query_df(q)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


@pytest.fixture(scope="module")
def ensure_populated(global_client: clickhouse_connect.driver.Client) -> None:
    """
    The test harness reuses an existing test DB by default. Ensure the new metric
    is populated even when the database is reused from a prior run.
    """
    db = str(global_client.query("SELECT currentDatabase()").result_rows[0][0])
    cnt = int(global_client.query("SELECT count() FROM regime_signals_canonical").result_rows[0][0])
    if cnt > 0:
        return

    dm_cnt = int(global_client.query("SELECT count() FROM daily_metrics").result_rows[0][0])
    if dm_cnt == 0:
        pytest.skip("daily_metrics is empty in this fixture; cannot validate regime_signals_canonical")

    # Populate over the *actual* test dataset coverage (fixtures can vary).
    mm = global_client.query("SELECT toString(min(date)), toString(max(date)) FROM daily_metrics").result_rows[0]
    start, end = (mm[0] or ""), (mm[1] or "")
    if not start or not end or start == "1970-01-01":
        pytest.skip("daily_metrics coverage could not be determined; cannot validate regime_signals_canonical")

    pop = DataPopulator()
    ok = pop.populate_metrics(
        start_date=start,
        end_date=end,
        metrics_to_process=["regime_signals_canonical"],
        force_refresh=True,
    )
    assert ok, "Failed to populate regime_signals_canonical in test mode"

    cnt2 = int(global_client.query("SELECT count() FROM regime_signals_canonical").result_rows[0][0])
    assert cnt2 > 0, f"regime_signals_canonical still empty after populate (db={db}, count={cnt2}, range={start}..{end})"


def test_schema_has_expected_columns(global_client: clickhouse_connect.driver.Client) -> None:
    schema = global_client.query_df("DESCRIBE regime_signals_canonical")
    names = set(schema["name"].astype(str).tolist())

    for c in ["ticker", "date", "lastupdated", *RAW_COLS, *NORMALIZED_COLS]:
        assert c in names, f"Missing column in regime_signals_canonical: {c}"


def test_normalized_signals_in_unit_interval(
    global_client: clickhouse_connect.driver.Client, ensure_populated: None
) -> None:
    df = _load_sample(global_client, limit=8000)
    assert not df.empty, "No rows found in regime_signals_canonical after populate"

    for c in NORMALIZED_COLS:
        assert df[c].notna().all(), f"{c} contains NULLs (should be non-null Float32)."
        # allow tiny numeric drift (Float32) but enforce bounds
        assert (df[c] >= -1e-6).all(), f"{c} has values < 0"
        assert (df[c] <= 1.0 + 1e-6).all(), f"{c} has values > 1"


def test_breadth_and_stage_are_clamped(
    global_client: clickhouse_connect.driver.Client, ensure_populated: None
) -> None:
    df = _load_sample(global_client, limit=8000)
    assert not df.empty, "No rows found in regime_signals_canonical after populate"

    # breadth and stage are simple clamps; they should match raw where raw is present.
    # (Raw may be NULL early; ignore those rows.)
    for raw, norm in [
        ("s_breadth200_raw", "s_breadth200"),
        ("s_breadth50_raw", "s_breadth50"),
        ("s_stage_self_raw", "s_stage_self"),
    ]:
        ok = df[raw].notna()
        if ok.any():
            diff = (df.loc[ok, raw].astype(float).clip(0.0, 1.0) - df.loc[ok, norm].astype(float)).abs().max()
            assert float(diff) < 1e-6, f"{norm} should equal clamp({raw}) (max diff {diff})"


def test_query_determinism(global_client: clickhouse_connect.driver.Client) -> None:
    df1 = _load_sample(global_client, limit=2000)
    df2 = _load_sample(global_client, limit=2000)
    # DataFrames should be identical for identical queries.
    assert df1.equals(df2)

