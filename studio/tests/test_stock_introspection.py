"""Tests for Stock Introspection endpoint and calculations."""
import os
import django
import pytest

import pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rest_framework.test import APIClient


@pytest.mark.django_db
def test_stock_overview_endpoint_validation():
    client = APIClient()
    # Missing ticker
    res = client.get("/api/screens/stock-overview?as_of=2026-06-15")
    assert res.status_code == 400

    # Missing as_of
    res = client.get("/api/screens/stock-overview?ticker=NVDA")
    assert res.status_code == 400


@pytest.mark.django_db
@pytest.mark.skip(
    reason=(
        "Legacy stock overview requires mixed-source tables and the Vera ticker database; "
        "it is outside SigmaRail Core's Sharadar-only synthetic fixture."
    )
)
def test_stock_overview_happy_path():
    client = APIClient()
    res = client.get("/api/screens/stock-overview?ticker=NVDA&as_of=2026-06-15&history_days=100&forward_days=30")
    assert res.status_code == 200
    data = res.json()
    assert data["ticker"] == "NVDA"
    assert data["as_of"] == "2026-06-15"
    assert "as_of_kpis" in data
    assert "trend_template" in data
    assert len(data["trend_template"]["items"]) == 8
    assert "chart_series" in data
    assert len(data["chart_series"]) > 0
    assert "forward_stats" in data
    assert "quarterly_growth" in data
    assert "annual_growth" in data
    assert isinstance(data["annual_growth"], list)
    # Multi-year reported quarters + up to 2 street estimate columns
    assert 8 <= len(data["quarterly_growth"]) <= 32
    if data.get("earnings_events"):
        assert "surprise_pct" in data["earnings_events"][0]
    kpis = data["as_of_kpis"]
    # Street means may be null for sparse history, but keys should be present when L7 joined
    assert "close" in kpis
    assert "stage_code" in kpis
    assert "stage_duration" in kpis
