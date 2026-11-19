from unittest.mock import patch

import pytest
from graphql_relay import to_global_id
from rest_framework.test import APIClient
from sigmarail.features.template_catalog import get_template, list_templates, summary_row


pytestmark = pytest.mark.django_db


def test_template_catalog_list_uses_installed_package_and_preserves_filters(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    expected = [summary_row(row) for row in list_templates(kind="strategy", status="active")]

    with (
        patch("apps.sigmarail_bridge.template_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        response = client.get(
            "/api/templates?kind=strategy&status=active",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )
        invalid = client.get("/api/templates?kind=invalid")

    assert response.status_code == 200
    assert response.json() == {"templates": expected}
    assert all(row["kind"] == "strategy" and row["status"] == "active" for row in expected)
    assert invalid.status_code == 400
    proxy.assert_not_called()


def test_template_catalog_detail_uses_installed_package(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with (
        patch("apps.sigmarail_bridge.template_catalog._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as proxy,
    ):
        response = client.get("/api/templates/momentum")
        missing = client.get("/api/templates/not-a-template")

    assert response.status_code == 200
    assert response.json() == get_template("momentum")
    assert response.json()["kind"] == "strategy"
    assert missing.status_code == 404
    proxy.assert_not_called()


def test_template_catalog_requires_authenticated_membership():
    response = APIClient().get("/api/templates?kind=strategy")

    assert response.status_code in (401, 403)
