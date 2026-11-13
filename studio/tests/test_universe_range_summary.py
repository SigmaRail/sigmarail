"""Universe range summary API tests (mocked CH)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client


def _sample_spec() -> dict:
    return {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "overall_score"],
        "where": {
            "type": "all",
            "items": [
                {
                    "type": "gt",
                    "left": {"type": "col", "name": "close"},
                    "right": {"type": "lit", "value": 10},
                }
            ],
        },
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 20,
    }


@pytest.mark.django_db
def test_universe_range_summary_endpoint() -> None:
    mock_out = {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "dates": ["2025-01-02", "2025-01-03"],
        "member_counts": [15, 18],
        "summary": {"trading_days": 2, "avg_members_per_day": 16.5},
        "weekly_samples": [],
    }
    with patch("api.views.summarize_universe_range", return_value=mock_out):
        with patch("api.views.get_ch_client") as mock_ch:
            mock_ch.return_value = MagicMock()
            c = Client()
            resp = c.post(
                "/api/screens/universe-range-summary",
                data=json.dumps(
                    {
                        "spec": _sample_spec(),
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                    }
                ),
                content_type="application/json",
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["trading_days"] == 2
    assert body["member_counts"] == [15, 18]


def test_summarize_universe_range_uses_sigmarail_aggregate_contract() -> None:
    from screens.universe_range_summary import summarize_universe_range

    client = MagicMock()
    with patch(
        "sigmarail.universe.universe_membership_counts",
        return_value=[{"date": "2025-01-02", "count": 3}],
    ) as aggregate:
        out = summarize_universe_range(
            client,
            spec=_sample_spec(),
            start_date="2025-01-01",
            end_date="2025-01-10",
        )
    assert out["member_counts"] == [3]
    assert out["dates"] == ["2025-01-02"]
    aggregate.assert_called_once_with(
        _sample_spec(), start_date="2025-01-01", end_date="2025-01-10", client=client
    )


@pytest.mark.django_db
def test_compose_includes_lineage_stamps() -> None:
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "framework": {
                    "UniverseSelection": {"Type": "VeraScreenerUniverseSelectionModel", "Parameters": {}},
                    "Alpha": {"Type": "RsiAlphaModel", "Parameters": {"period": 14, "resolution": "Daily"}},
                    "PortfolioConstruction": {"Type": "EqualWeightingPortfolioConstructionModel", "Parameters": {}},
                    "RiskManagement": {"Type": "MaximumDrawdownPercentPerSecurity", "Parameters": {}},
                    "Execution": {"Type": "ImmediateExecutionModel", "Parameters": {}},
                },
                "title": "Lineage test",
                "universe": {"source": "inline", "inline_spec": _sample_spec()},
                "lineage": {"studio_screen_id": 7, "studio_screen_name": "My screen"},
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    algo = body["spec"]["AlgorithmParameters"]
    assert algo["studio_screen_id"] == "7"
    assert algo["studio_screen_name"] == "My screen"
    assert algo["studio_spec_hash"]
    assert body["lineage"]["studio_screen_id"] == "7"
