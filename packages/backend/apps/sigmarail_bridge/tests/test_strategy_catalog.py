from unittest.mock import patch

import pytest
from graphql_relay import to_global_id
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_strategy_factors_are_served_from_spec_without_proxy(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    expected = {"factors": {"momentum": {"title": "Momentum"}}}

    with (
        patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.strategy_catalog.list_factors", return_value=expected["factors"]),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        response = client.get(
            "/api/strategy/factors",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == expected
    proxy.assert_not_called()


def test_strategy_position_fields_are_served_from_spec(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    expected = [{"field": "entry", "label": "Entry price"}]

    with (
        patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.strategy_catalog.POSITION_BINDINGS", expected),
    ):
        response = client.get(
            "/api/strategy/position-fields",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"fields": expected, "count": 1}


def test_strategy_presets_are_served_from_spec_without_proxy(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    expected = [{"id": "momentum", "name": "Momentum"}]

    with (
        patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.strategy_catalog.list_presets", return_value=expected),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        response = client.get(
            "/api/strategy/presets",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"presets": expected}
    proxy.assert_not_called()


def test_strategy_preset_returns_spec_document(user, tenant, tenant_membership_factory):
    from sigmarail_spec.strategy import get_preset

    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    expected = get_preset("momentum").model_dump(mode="json")

    with patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)):
        response = client.get(
            "/api/strategy/presets/momentum",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_unknown_strategy_preset_returns_not_found(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)

    with patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)):
        response = client.get(
            "/api/strategy/presets/does-not-exist",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 404


def test_strategy_pipeline_compiler_and_decompiler_use_sigma_rail_spec_without_proxy(
    user, tenant, tenant_membership_factory
):
    from sigmarail_spec.strategy import compile_pipeline, decompile_pipeline, get_preset

    from apps.sigmarail_bridge.strategy_catalog import _materialize_generated_risk_rules

    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    document = get_preset("momentum")
    expected = compile_pipeline(document)
    _materialize_generated_risk_rules(expected)

    with (
        patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        compiled = client.post(
            "/api/strategy/pipelines/compile",
            document.model_dump(mode="json"),
            format="json",
        )
        assert compiled.status_code == 200
        assert compiled.json() == expected

        decompiled = client.post(
            "/api/strategy/pipelines/decompile",
            compiled.json(),
            format="json",
        )
        assert decompiled.status_code == 200
        assert decompiled.json() == decompile_pipeline(expected).model_dump(mode="json")

        valid = client.post(
            "/api/strategy/pipelines/validate",
            document.model_dump(mode="json"),
            format="json",
        )
        assert valid.status_code == 200
        assert valid.json() == {"valid": True}

        invalid = client.post("/api/strategy/pipelines/validate", {}, format="json")
        assert invalid.status_code == 200
        assert invalid.json()["valid"] is False
        assert invalid.json()["error"]
        proxy.assert_not_called()


def test_strategy_portfolio_compiler_and_decompiler_use_sigma_rail_spec_without_proxy(
    user, tenant, tenant_membership_factory
):
    from sigmarail_spec.strategy import compile_portfolio, decompile_portfolio
    from sigmarail_spec.strategy.presets import get_portfolio_preset, list_portfolio_presets

    tenant_membership_factory(user=user, tenant=tenant)
    client = _client(user)
    preset_id = list_portfolio_presets()[0]["id"]
    document = get_portfolio_preset(preset_id)
    expected = compile_portfolio(document)

    with (
        patch("apps.sigmarail_bridge.strategy_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        compiled = client.post(
            "/api/strategy/pipelines/compile-portfolio",
            document.model_dump(mode="json"),
            format="json",
        )
        assert compiled.status_code == 200
        assert compiled.json() == expected

        decompiled = client.post(
            "/api/strategy/pipelines/decompile-portfolio",
            compiled.json(),
            format="json",
        )
        assert decompiled.status_code == 200
        assert decompiled.json() == decompile_portfolio(expected).model_dump(mode="json")
        proxy.assert_not_called()


def test_strategy_pipeline_compile_requires_authenticated_membership():
    response = APIClient().post("/api/strategy/pipelines/compile", {}, format="json")

    assert response.status_code in (401, 403)
