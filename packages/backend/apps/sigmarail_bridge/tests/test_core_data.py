from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from django.test import override_settings
from graphql_relay import to_global_id
from rest_framework.test import APIClient
from rest_framework.response import Response

from apps.sigmarail_bridge.core_data import _clickhouse_client

pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_data_routes_dispatch_in_process_when_native_queries_are_disabled(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal/api/data/datasets")

    with (
        override_settings(
            SIGMARAIL_CLICKHOUSE_ENABLED=False,
        ),
        patch(
            "apps.sigmarail_bridge.views.dispatch_api_request",
            return_value=httpx.Response(200, request=upstream_request, json={"source": "in-process domain view"}),
        ) as forward,
    ):
        response = client.get(
            "/api/data/datasets",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"source": "in-process domain view"}
    forward.assert_called_once()
    assert forward.call_args.args[:2] == ("GET", "/api/data/datasets")


def test_native_dataset_catalog_requires_active_workspace_and_uses_spec_manifest(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    expected = {"module_id": "sigmarail.core", "count": 1, "datasets": []}

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data.list_datasets", return_value=expected) as list_manifest,
    ):
        response = client.get(
            "/api/data/datasets",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == expected
    list_manifest.assert_called_once_with()


def test_native_query_validates_before_opening_clickhouse(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        response = client.post(
            "/api/data/query",
            {},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 400
    get_client.assert_not_called()


def test_native_query_passes_only_validated_query_to_read_only_client(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    query = {
        "module_id": "sigmarail.core",
        "dataset_id": "sigmarail.core.screener_price_tech_daily",
        "select": [{"field_id": "sigmarail.field.screener_price_tech_daily.ticker.ticker"}],
        "as_of_date": "2024-12-31",
    }
    result = {
        "module_id": "sigmarail.core",
        "dataset_id": query["dataset_id"],
        "row_count": 0,
        "rows": [],
    }
    readonly_client = object()

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
        patch("apps.sigmarail_bridge.core_data.compile_query") as compile_query,
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value=result) as execute_query,
    ):
        response = client.post(
            "/api/data/query",
            query,
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == result
    compile_query.assert_called_once()
    execute_query.assert_called_once()
    assert execute_query.call_args.kwargs["client"] is readonly_client


def test_native_query_fails_closed_when_database_connection_is_not_configured(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    query = {
        "module_id": "sigmarail.core",
        "dataset_id": "sigmarail.core.screener_price_tech_daily",
        "select": [{"field_id": "sigmarail.field.screener_price_tech_daily.ticker.ticker"}],
        "as_of_date": "2024-12-31",
    }
    _clickhouse_client.cache_clear()

    with (
        override_settings(
            SIGMARAIL_CLICKHOUSE_ENABLED=True,
            SIGMARAIL_CLICKHOUSE_HOST="",
            SIGMARAIL_CLICKHOUSE_USER="",
        ),
        patch("apps.sigmarail_bridge.core_data.compile_query"),
    ):
        response = client.post(
            "/api/data/query",
            query,
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "SigmaRail ClickHouse query service is unavailable."


def test_clickhouse_client_is_created_with_readonly_setting():
    _clickhouse_client.cache_clear()
    password_for_test = "test-secret"
    with (
        override_settings(
            SIGMARAIL_CLICKHOUSE_ENABLED=True,
            SIGMARAIL_CLICKHOUSE_HOST="clickhouse.internal",
            SIGMARAIL_CLICKHOUSE_HTTP_PORT=8123,
            SIGMARAIL_CLICKHOUSE_USER="studio_reader",
            SIGMARAIL_CLICKHOUSE_PASSWORD=password_for_test,
            SIGMARAIL_CLICKHOUSE_DATABASE="sigmarail",
            SIGMARAIL_CLICKHOUSE_SECURE=False,
        ),
        patch("apps.sigmarail_bridge.core_data.clickhouse_connect.get_client", return_value=object()) as create,
    ):
        _clickhouse_client()

    assert create.call_args.kwargs["settings"] == {"readonly": 2}
    assert create.call_args.kwargs["username"] == "studio_reader"
    _clickhouse_client.cache_clear()


def test_latest_trading_date_uses_typed_query_and_preserves_response_shape(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    readonly_client = object()
    field_id = "sigmarail.field.screener_price_tech_daily.date.date"

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data.timezone.localdate", return_value=date(2026, 11, 16)),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
        patch(
            "apps.sigmarail_bridge.core_data.query_dataset",
            return_value={"rows": [{"latest_date": "2026-11-13"}]},
        ) as execute_query,
    ):
        response = client.get(
            "/api/screens/latest-trading-date",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"latest_date": "2026-11-13"}
    query = execute_query.call_args.args[0]
    assert query.dataset_id == "sigmarail.core.screener_price_tech_daily"
    assert query.select[0].field_id == field_id
    assert query.select[0].alias == "latest_date"
    assert query.where.op == "lte"
    assert query.where.value == "2026-11-16"
    assert query.order_by[0].field_id == field_id
    assert query.order_by[0].direction == "desc"
    assert query.limit == 1
    assert execute_query.call_args.kwargs["client"] is readonly_client


def test_latest_trading_date_returns_null_when_dataset_has_no_rows(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=object()),
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value={"rows": []}),
    ):
        response = client.get(
            "/api/screens/latest-trading-date",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"latest_date": None}


def test_latest_trading_date_uses_compatibility_bridge_while_native_queries_are_disabled(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    bridge_response = Response({"latest_date": "2026-11-13"})

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=False),
        patch(
            "apps.sigmarail_bridge.core_data.DomainAPIRouteView._dispatch",
            return_value=bridge_response,
        ) as forward,
        patch("apps.sigmarail_bridge.core_data.query_dataset") as execute_query,
    ):
        response = client.get(
            "/api/screens/latest-trading-date",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"latest_date": "2026-11-13"}
    forward.assert_called_once()
    execute_query.assert_not_called()


def test_latest_trading_date_requires_active_tenant_membership(user, tenant):
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        response = client.get(
            "/api/screens/latest-trading-date",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    get_client.assert_not_called()


def test_as_of_range_uses_typed_query_and_preserves_legacy_response(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    readonly_client = object()
    field_id = "sigmarail.field.screener_price_tech_daily.date.date"
    rows = [{"date": "2026-11-16"}, {"date": "2026-11-13"}]

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data.timezone.localdate", return_value=date(2026, 11, 16)),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value={"rows": rows}) as execute_query,
    ):
        response = client.get(
            "/api/screens/as-of-range?limit=10000",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200, response.json()
    assert response.json() == {"dates": ["2026-11-16", "2026-11-13"], "count": 2}
    query = execute_query.call_args.args[0]
    assert query.dataset_id == "sigmarail.core.screener_price_tech_daily"
    assert query.select[0].field_id == field_id
    assert query.select[0].alias == "date"
    assert query.order_by[0].field_id == field_id
    assert query.order_by[0].direction == "desc"
    assert query.where.op == "lte"
    assert query.where.value == "2026-11-16"
    assert query.limit == 1000
    assert execute_query.call_args.kwargs == {"client": readonly_client, "total_limit": 10000}


def test_as_of_range_caps_limit_and_rejects_non_integer_before_clickhouse(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        invalid = client.get(
            "/api/screens/as-of-range?limit=recent",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )
    assert invalid.status_code == 400
    get_client.assert_not_called()

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=object()),
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value={"rows": []}) as execute_query,
    ):
        capped = client.get(
            "/api/screens/as-of-range?limit=50000",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert capped.status_code == 200, capped.json()
    assert capped.json() == {"dates": [], "count": 0}
    assert execute_query.call_args.kwargs["total_limit"] == 10000


def test_as_of_range_requires_active_tenant_membership(user, tenant):
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        response = client.get(
            "/api/screens/as-of-range",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    get_client.assert_not_called()


def test_market_context_uses_typed_core_query_and_preserves_legacy_rows(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    readonly_client = object()
    rows = [
        {
            "date": date(2026, 11, 12),
            "allocation_note": "risk-on",
            "vix_close": Decimal("18.25"),
            "uvxy_vs_vix_basis": None,
        }
    ]

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value={"rows": rows}) as execute_query,
    ):
        response = client.get(
            "/api/screens/market-context?start_date=2026-01-01&end_date=2026-11-16&limit=2000",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200, response.json()
    assert response.json() == [
        {
            "date": "2026-11-12",
            "allocation_note": "risk-on",
            "vix_close": 18.25,
            "uvxy_vs_vix_basis": None,
        }
    ]
    query = execute_query.call_args.args[0]
    assert query.module_id == "sigmarail.core"
    assert query.dataset_id == "sigmarail.core.market_context_daily"
    assert query.as_of_date is None
    assert query.start_date is None
    assert query.end_date is None
    assert query.where.op == "all"
    assert query.where.items[0].op == "gte"
    assert query.where.items[0].field_id == "sigmarail.field.market_context_daily.date.date"
    assert query.where.items[0].value == "2026-01-01"
    assert query.where.items[1].op == "lte"
    assert query.where.items[1].value == "2026-11-16"
    assert query.order_by[0].field_id == "sigmarail.field.market_context_daily.date.date"
    assert query.order_by[0].direction == "asc"
    assert len(query.select) == 58
    assert query.select[0].alias == "date"
    assert query.select[-1].alias == "svxy_vs_vix_basis"
    assert query.limit == 1000
    assert execute_query.call_args.kwargs == {"client": readonly_client, "total_limit": 2000}


def test_market_context_validates_dates_and_limit_before_clickhouse(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    headers = {"HTTP_X_TENANT_ID": to_global_id("TenantType", tenant.id)}

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        missing = client.get("/api/screens/market-context?end_date=2026-11-16", **headers)
        invalid = client.get(
            "/api/screens/market-context?start_date=2026-13-01&end_date=2026-11-16",
            **headers,
        )
        reversed_range = client.get(
            "/api/screens/market-context?start_date=2026-11-16&end_date=2026-01-01",
            **headers,
        )
        invalid_limit = client.get(
            "/api/screens/market-context?start_date=2026-01-01&end_date=2026-11-16&limit=recent",
            **headers,
        )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert reversed_range.status_code == 400
    assert invalid_limit.status_code == 400
    get_client.assert_not_called()

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=object()),
        patch("apps.sigmarail_bridge.core_data.compile_query"),
        patch("apps.sigmarail_bridge.core_data.query_dataset", return_value={"rows": []}) as execute_query,
    ):
        capped = client.get(
            "/api/screens/market-context?start_date=2026-01-01&end_date=2026-11-16&limit=50000",
            **headers,
        )

    assert capped.status_code == 200
    assert capped.json() == []
    assert execute_query.call_args.kwargs["total_limit"] == 5000


def test_market_context_requires_active_tenant_membership(user, tenant):
    client = _client(user)

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        response = client.get(
            "/api/screens/market-context?start_date=2026-01-01&end_date=2026-11-16",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    get_client.assert_not_called()


def test_market_context_uses_compatibility_bridge_until_native_queries_are_enabled(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    bridge_response = Response([{"date": "2026-11-12", "vix_close": 18.25}])

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=False),
        patch(
            "apps.sigmarail_bridge.views.DomainAPIRouteView._dispatch",
            return_value=bridge_response,
        ) as forward,
        patch("apps.sigmarail_bridge.core_data.query_dataset") as execute_query,
    ):
        response = client.get(
            "/api/screens/market-context?start_date=2026-01-01&end_date=2026-11-16",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == [{"date": "2026-11-12", "vix_close": 18.25}]
    forward.assert_called_once()
    execute_query.assert_not_called()


def test_universe_compile_uses_sigma_rail_compiler_without_clickhouse(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    spec = {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "overall_score"],
        "where": {
            "type": "gt",
            "left": {"type": "col", "name": "overall_score"},
            "right": {"type": "lit", "value": 70},
        },
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 10,
    }

    with (
        patch("apps.sigmarail_bridge.core_data._clickhouse_client") as get_client,
    ):
        response = client.post(
            "/api/screens/compile-sql",
            {"spec": spec},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    result = response.json()
    assert result["sql"].startswith("SELECT ")
    assert "LEFT ANY JOIN `screener_ratings_daily`" in result["sql"]
    assert "d1.`overall_score` > %(p2)s" in result["sql"]
    assert result["params"]["p2"] == 70
    get_client.assert_not_called()


def test_universe_schema_is_served_from_the_installed_spec_package(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)

    with patch("apps.sigmarail_bridge.core_data._workspace_for_request", return_value=(tenant, None)):
        response = client.get(
            "/api/screens/ir-schema",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json()["title"] == "UniverseQueryV1"


def test_universe_preview_runs_compatible_specs_through_native_read_only_client(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    spec = {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "overall_score"],
        "where": {
            "type": "gt",
            "left": {"type": "col", "name": "overall_score"},
            "right": {"type": "lit", "value": 70},
        },
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 10,
    }
    query_result = SimpleNamespace(
        column_names=["ticker", "date", "close", "exchange", "overall_score"],
        result_rows=[["abc", date(2024, 12, 31), Decimal("12.5"), "NASDAQ", Decimal("91.0")]],
    )
    readonly_client = SimpleNamespace(query=Mock(return_value=query_result))

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
    ):
        response = client.post(
            "/api/screens/preview-ir",
            {"as_of": "2024-12-31", "spec": spec},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["as_of"] == "2024-12-31"
    assert body["rows"][0]["ticker"] == "ABC"
    assert body["rows"][0]["close"] == 12.5
    assert body["rows"][0]["exchange"] == "NASDAQ"
    assert body["rows"][0]["overall_score"] == 91.0
    assert body["limit"] == 10
    sql = readonly_client.query.call_args.args[0]
    assert sql.startswith("SELECT ")
    assert "`exchange`" in sql
    assert readonly_client.query.call_args.kwargs["parameters"]["start_date"] == "2024-12-31"
    assert readonly_client.query.call_args.kwargs["parameters"]["end_date"] == "2024-12-31"
    assert readonly_client.query.call_args.kwargs["settings"] == {"allow_experimental_analyzer": 0}


def test_universe_preview_keeps_tenure_on_the_compatibility_service(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    bridge_response = Response({"source": "in-process domain view"})
    spec = {"version": 1, "from": "daily_screener"}

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch("apps.sigmarail_bridge.core_data.compile_universe_spec") as compile_spec,
        patch(
            "apps.sigmarail_bridge.core_data.DomainAPIRouteView._dispatch",
            return_value=bridge_response,
        ) as forward,
    ):
        response = client.post(
            "/api/screens/preview-ir",
            {"as_of": "2024-12-31", "spec": spec, "include_tenure": True},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"source": "in-process domain view"}
    compile_spec.assert_not_called()
    forward.assert_called_once()


def test_universe_preview_uses_compatibility_service_for_unsupported_fields(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    bridge_response = Response({"source": "in-process domain view"})
    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch(
            "apps.sigmarail_bridge.core_data.compile_universe_spec",
            side_effect=ValueError("field is outside the installed core contract"),
        ),
        patch(
            "apps.sigmarail_bridge.core_data.DomainAPIRouteView._dispatch",
            return_value=bridge_response,
        ) as forward,
    ):
        response = client.post(
            "/api/screens/preview-ir",
            {"as_of": "2024-12-31", "spec": {"select": ["eps_cq_mean"]}},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"source": "in-process domain view"}
    forward.assert_called_once()


def test_universe_preview_preserves_latest_trading_date_fallback(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    bridge_response = Response({"source": "latest-date compatibility fallback"})
    empty_result = SimpleNamespace(column_names=["ticker", "date"], result_rows=[])
    readonly_client = SimpleNamespace(query=Mock(return_value=empty_result))

    with (
        override_settings(SIGMARAIL_CLICKHOUSE_ENABLED=True),
        patch(
            "apps.sigmarail_bridge.core_data.compile_universe_spec",
            return_value=("SELECT native preview", {"start_date": "2024-12-31", "end_date": "2024-12-31"}),
        ),
        patch("apps.sigmarail_bridge.core_data._clickhouse_client", return_value=readonly_client),
        patch(
            "apps.sigmarail_bridge.core_data.DomainAPIRouteView._dispatch",
            return_value=bridge_response,
        ) as forward,
    ):
        response = client.post(
            "/api/screens/preview-ir",
            {"as_of": "2024-12-31", "spec": {"select": ["ticker"]}},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"source": "latest-date compatibility fallback"}
    forward.assert_called_once()
