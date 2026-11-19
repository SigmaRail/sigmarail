from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.sigmarail_bridge.models import WorkspaceStrategyFrameworkTemplate


pytestmark = pytest.mark.django_db


@pytest.fixture
def framework():
    return {
        "alpha": {"type": "PyramidAlpha", "config": {"signals": []}},
        "pcm": {"type": "RiskBudgetedPortfolioConstructionModel", "config": {}},
        "risk": {"type": "SwingProgressiveRiskManagementModel", "config": {}},
        "execution": {"type": "SigmaRailExecutionModel", "config": {}},
    }


def test_framework_templates_are_saved_in_the_active_tenant_for_the_owner(
    user, tenant, tenant_membership_factory, framework
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with (
        patch(
            "apps.sigmarail_bridge.strategy_framework_templates._workspace_for_request",
            return_value=(tenant, None),
        ),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as legacy_request,
    ):
        created = client.post(
            "/api/backtests/framework-templates",
            {
                "name": "My framework",
                "description": "Reusable position and risk configuration",
                "framework": framework,
            },
            format="json",
        )
        listed = client.get("/api/backtests/framework-templates")
        detail = client.get(f"/api/backtests/framework-templates/{created.json()['id']}")
        named_detail = client.get("/api/backtests/framework-templates/My%20framework")
        invalid_detail = client.get("/api/backtests/framework-templates/not-a-uuid")
        invalid_update = client.put(
            "/api/backtests/framework-templates/not-a-uuid",
            {"name": "Invalid"},
            format="json",
        )
        invalid_delete = client.delete("/api/backtests/framework-templates/not-a-uuid")
        updated = client.put(
            f"/api/backtests/framework-templates/{created.json()['id']}",
            {"description": "Updated note", "category": "Swing", "framework": framework},
            format="json",
        )
        deleted = client.delete(f"/api/backtests/framework-templates/{created.json()['id']}")
        missing = client.get(f"/api/backtests/framework-templates/{created.json()['id']}")

    assert created.status_code == 201
    assert created.json()["framework"] == framework
    assert created.json()["is_system"] is False
    assert listed.status_code == 200
    assert listed.json() == {"templates": [created.json()], "count": 1}
    assert detail.status_code == 200
    assert detail.json()["id"] == created.json()["id"]
    assert named_detail.status_code == 200
    assert named_detail.json()["id"] == created.json()["id"]
    assert invalid_detail.status_code == 404
    assert invalid_update.status_code == 404
    assert invalid_delete.status_code == 404
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated note"
    assert updated.json()["category"] == "Swing"
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": created.json()["id"]}
    assert missing.status_code == 404
    assert WorkspaceStrategyFrameworkTemplate.objects.filter(tenant=tenant).count() == 0
    legacy_request.assert_not_called()


def test_framework_templates_are_private_and_names_are_unique_per_owner(
    user, user_factory, tenant, tenant_membership_factory, framework
):
    other_user = user_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    tenant_membership_factory(user=other_user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(
        "apps.sigmarail_bridge.strategy_framework_templates._workspace_for_request",
        return_value=(tenant, None),
    ):
        created = client.post(
            "/api/backtests/framework-templates",
            {"name": "Private", "framework": framework},
            format="json",
        )
        duplicate = client.post(
            "/api/backtests/framework-templates",
            {"name": "private", "framework": framework},
            format="json",
        )
        client.force_authenticate(user=other_user)
        other_created = client.post(
            "/api/backtests/framework-templates",
            {"name": "Private", "framework": framework},
            format="json",
        )
        hidden = client.get(f"/api/backtests/framework-templates/{created.json()['id']}")
        hidden_update = client.put(
            f"/api/backtests/framework-templates/{created.json()['id']}",
            {"name": "Taken"},
            format="json",
        )
        hidden_delete = client.delete(f"/api/backtests/framework-templates/{created.json()['id']}")
        other_list = client.get("/api/backtests/framework-templates")

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert other_created.status_code == 201
    assert other_created.json()["id"] != created.json()["id"]
    assert hidden.status_code == 404
    assert hidden_update.status_code == 404
    assert hidden_delete.status_code == 404
    assert other_list.json()["count"] == 1
    assert other_list.json()["templates"][0]["id"] == other_created.json()["id"]
    assert WorkspaceStrategyFrameworkTemplate.objects.filter(tenant=tenant).count() == 2


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"framework": {}}, "name is required"),
        ({"name": "No framework"}, "framework must be a valid dictionary"),
        ({"name": "Wrong framework", "framework": []}, "framework must be a valid dictionary"),
        ({"name": "x" * 129, "framework": {}}, "name must be at most 128 characters"),
        (
            {"name": "Too long category", "category": "x" * 65, "framework": {}},
            "category must be at most 64 characters",
        ),
    ],
)
def test_framework_template_create_validates_payload(user, tenant, tenant_membership_factory, body, message):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(
        "apps.sigmarail_bridge.strategy_framework_templates._workspace_for_request",
        return_value=(tenant, None),
    ):
        response = client.post("/api/backtests/framework-templates", body, format="json")

    assert response.status_code == 400
    assert response.json() == {"detail": message}
    assert not WorkspaceStrategyFrameworkTemplate.objects.exists()


def test_framework_template_endpoint_requires_authentication_and_active_tenant(user):
    assert APIClient().get("/api/backtests/framework-templates").status_code in (401, 403)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/backtests/framework-templates")
    assert response.status_code == 400
    assert response.json() == {"detail": "An active workspace is required."}
