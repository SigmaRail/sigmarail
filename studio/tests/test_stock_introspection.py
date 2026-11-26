"""Tests for Stock Introspection endpoint and calculations."""
import os
import django
import pytest

import pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rest_framework.test import APIClient
from screens import stock_introspection


@pytest.mark.django_db
def test_stock_overview_endpoint_validation():
    client = APIClient()
    # Missing ticker
    res = client.get("/api/screens/stock-overview?as_of=2026-06-15")
    assert res.status_code == 400
    # Missing as_of
    res = client.get("/api/screens/stock-overview?ticker=NVDA")
    assert res.status_code == 400


def test_stock_introspection_uses_publication_time_and_dated_classification():
    from pathlib import Path

    assert callable(stock_introspection.append_missing_quarterly_actuals)
    source = (Path(__file__).parents[1] / "screens" / "stock_introspection.py").read_text()
    assert "available_at <= toDateTime64" in source
    assert "ASOF LEFT JOIN ticker_classification_daily" not in source
    assert "argMax(industry, lastupdated)" in source
    assert "cls.sector, cls.industry" in source
    assert "date != toDate('1970-01-01')" in source
    assert "lastupdated <= toDateTime64" in source


def test_optional_estimates_table_failure_removes_join_but_preserves_null_fields(monkeypatch):
    class QueryResult:
        def __init__(self, rows=(), columns=()):
            self.result_rows = rows
            self.column_names = columns

    class ClickHouseError(Exception):
        code = 60

    class Client:
        def __init__(self):
            self.calls = []

        def query(self, sql, parameters=None):
            self.calls.append((sql, parameters))
            if "SELECT\n        p.ticker" in sql:
                assert "ext_analyst_estimates_screener_estimates_daily" not in sql
                assert "CAST(NULL, 'Nullable(Float64)') AS eps_cq_mean" in sql
                assert "CAST(NULL, 'Nullable(Int8)') AS eps_beat_flag" in sql
                return QueryResult([], [])
            if "SELECT date FROM screener_price_tech_daily" in sql and "ORDER BY date DESC LIMIT 1" in sql:
                if len(self.calls) > 4:
                    return QueryResult([])
                return QueryResult([(datetime.date(2026, 11, 19),)])
            if "SELECT max(date) FROM ext_analyst_estimates" in sql:
                raise ClickHouseError("UNKNOWN_TABLE")
            raise AssertionError(f"unexpected query: {sql[:80]}")

    import datetime

    client = Client()
    with pytest.raises(ValueError, match="No market data found"):
        stock_introspection.get_stock_introspection(
            client, "ULCC", "2026-11-19", history_days=30, include_dossier=False
        )
    assert any("FROM screener_price_tech_daily p FINAL" in sql for sql, _ in client.calls)


def test_optional_estimates_only_swallows_unknown_table_errors():
    class Client:
        def query(self, sql, parameters=None):
            if "SELECT\n        p.ticker" in sql:
                return type("Result", (), {"result_rows": []})()
            if "SELECT date FROM screener_price_tech_daily" in sql:
                return type("Result", (), {"result_rows": [(datetime.date(2026, 11, 19),)]})()
            if "SELECT max(date) FROM ext_analyst_estimates" in sql:
                raise RuntimeError("ClickHouse server unavailable")
            raise AssertionError("unexpected follow-up query")

    import datetime

    with pytest.raises(RuntimeError, match="server unavailable"):
        stock_introspection.get_stock_introspection(
            Client(), "ULCC", "2026-11-19", history_days=30, include_dossier=False
        )



@pytest.mark.django_db
@pytest.mark.skip(
    reason=(
        "The stock overview requires joined, populated screener history and estimate fixtures; "
        "the lightweight test database does not materialize that dataset."
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
