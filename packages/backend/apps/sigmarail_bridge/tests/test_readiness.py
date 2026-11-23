from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import override_settings

from apps.sigmarail_bridge.graphql import Query


def _info():
    return SimpleNamespace(context=SimpleNamespace(user=SimpleNamespace(is_authenticated=True)))


def test_readiness_reports_permissions_and_latest_dataset_coverage():
    client = Mock()
    latest_price = date(2026, 11, 20)
    latest_market = date(2026, 11, 19)

    def query(sql, parameters=None):
        if "max(date) FROM screener_price_tech_daily" in sql:
            return SimpleNamespace(result_rows=[(latest_price,)])
        if "count(), uniqExact(ticker) FROM screener_price_tech_daily" in sql:
            assert parameters == {"latest": latest_price}
            return SimpleNamespace(result_rows=[(12000, 5000)])
        if "max(date) FROM market_context_daily" in sql:
            return SimpleNamespace(result_rows=[(latest_market,)])
        assert "count() FROM market_context_daily" in sql
        assert parameters == {"latest": latest_market}
        return SimpleNamespace(result_rows=[(1,)])

    client.query.side_effect = query
    tenant = SimpleNamespace(pk="tenant-1")
    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant),
        patch(
            "apps.multitenancy.models.get_user_permissions_for_tenant",
            return_value={"screen.view", "backtest.view"},
        ),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=client),
    ):
        result = Query.resolve_sigmarail_readiness(None, _info(), "tenant-1")

    assert result["overall_status"] == "ready"
    assert result["permissions"]["codes"] == ["backtest.view", "screen.view"]
    assert result["data"][0]["latest_available_date"] == "2026-11-20"
    assert result["data"][0]["row_count"] == 12000
    assert result["data"][0]["symbol_count"] == 5000
    assert result["data"][1]["latest_available_date"] == "2026-11-19"
    client.close.assert_called_once()


def test_readiness_reports_disabled_data_backend_as_degraded():
    tenant = SimpleNamespace(pk="tenant-1")
    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=False),
        patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant),
        patch("apps.multitenancy.models.get_user_permissions_for_tenant", return_value={"screen.view"}),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as clickhouse_client,
    ):
        result = Query.resolve_sigmarail_readiness(None, _info(), "tenant-1")

    assert result["overall_status"] == "degraded"
    assert {item["code"] for item in result["data"]} == {"DATA_BACKEND_DISABLED"}
    clickhouse_client.assert_not_called()
