"""Integration contract for the generated, provider-free baseline population."""

from __future__ import annotations

import json
import os

import pytest


def test_daily_price_projection_preserves_fixture_coverage(global_client) -> None:
    """Verify the loaded and transformed price spine retains the synthetic sample shape."""
    manifest_path = os.environ.get("SIGMARAIL_TEST_SYNTHETIC_MANIFEST")
    if not manifest_path:
        pytest.skip("population contract applies to pytest-managed synthetic data")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)

    result = global_client.query(
        """
        SELECT count(), uniqExact(ticker), uniqExact(date), min(date), max(date)
        FROM daily_prices FINAL
        """
    )
    row_count, ticker_count, session_count, first_date, last_date = result.result_rows[0]
    expected_rows = manifest["tables"]["sep"] + manifest["tables"]["sfp"]

    assert row_count == expected_rows
    assert ticker_count == manifest["symbol_count"]
    assert session_count == manifest["price_session_count"]
    assert str(first_date) == manifest["first_price_date"]
    assert str(last_date) == manifest["end_date"]

    duplicates = global_client.query(
        """
        SELECT count()
        FROM (
            SELECT ticker, date
            FROM daily_prices FINAL
            GROUP BY ticker, date
            HAVING count() != 1
        )
        """
    ).result_rows[0][0]
    assert duplicates == 0
