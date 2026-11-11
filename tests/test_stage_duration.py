"""Canonical daily stage_duration must count the emitted detailed stage_code."""

from __future__ import annotations

import pandas as pd
import pytest
import clickhouse_connect

pytestmark = [pytest.mark.metrics]

PANEL = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX")


@pytest.fixture(scope="module")
def stage_rows(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    symbols = ",".join(f"'{symbol}'" for symbol in PANEL)
    rows = global_client.query_df(
        f"""
        SELECT ticker, date, stage_code, stage_duration
        FROM daily_metrics_derived FINAL
        WHERE ticker IN ({symbols})
        ORDER BY ticker, date
        """
    )
    if rows.empty:
        pytest.skip("daily_metrics_derived has no rows for the fixed stage panel")
    rows["date"] = pd.to_datetime(rows["date"])
    return rows


def test_daily_stage_transform_preserves_source_key_set(
    global_client: clickhouse_connect.driver.Client,
) -> None:
    symbols = ",".join(f"'{symbol}'" for symbol in PANEL)
    source = global_client.query(
        f"""
        SELECT count(), uniqExact(tuple(ticker, date))
        FROM daily_metrics FINAL
        WHERE ticker IN ({symbols})
        """
    ).result_rows[0]
    target = global_client.query(
        f"""
        SELECT count(), uniqExact(tuple(ticker, date))
        FROM daily_metrics_derived FINAL
        WHERE ticker IN ({symbols})
        """
    ).result_rows[0]
    source_only = global_client.query(
        f"""
        SELECT count()
        FROM (
            SELECT ticker, date FROM daily_metrics FINAL WHERE ticker IN ({symbols})
        ) AS source
        LEFT ANTI JOIN (
            SELECT ticker, date FROM daily_metrics_derived FINAL WHERE ticker IN ({symbols})
        ) AS derived USING (ticker, date)
        """
    ).result_rows[0][0]
    derived_only = global_client.query(
        f"""
        SELECT count()
        FROM (
            SELECT ticker, date FROM daily_metrics_derived FINAL WHERE ticker IN ({symbols})
        ) AS derived
        LEFT ANTI JOIN (
            SELECT ticker, date FROM daily_metrics FINAL WHERE ticker IN ({symbols})
        ) AS source USING (ticker, date)
        """
    ).result_rows[0][0]

    assert source[0] == source[1], "daily_metrics fixture must be unique at ticker/date grain"
    assert target[0] == target[1], "daily_metrics_derived must stay unique at ticker/date grain"
    assert target[0] == source[0]
    assert source_only == 0
    assert derived_only == 0


def test_duration_is_populated_for_valid_codes_and_null_for_warmup(stage_rows: pd.DataFrame) -> None:
    valid = stage_rows[stage_rows["stage_code"].notna()]
    assert not valid.empty, "expected canonical stage codes after moving-average warmup"
    assert valid["stage_duration"].notna().all()
    assert valid["stage_duration"].ge(1).all()
    assert stage_rows.loc[stage_rows["stage_code"].isna(), "stage_duration"].isna().all()


def test_duration_matches_full_history_run_length(stage_rows: pd.DataFrame) -> None:
    rows = stage_rows.sort_values(["ticker", "date"]).copy()
    rows["new_run"] = rows.groupby("ticker", sort=False)["stage_code"].transform(
        lambda values: values.ne(values.shift()).fillna(True)
    )
    rows["run_id"] = rows.groupby("ticker", sort=False)["new_run"].cumsum()
    rows["expected_duration"] = rows.groupby(["ticker", "run_id"], sort=False).cumcount() + 1
    valid = rows[rows["stage_code"].notna()]
    bad = valid[valid["expected_duration"] != valid["stage_duration"]]
    assert bad.empty, (
        f"{len(bad):,} rows disagree with the full-history run length; "
        f"first mismatches: {bad.head(5).to_dict('records')}"
    )
