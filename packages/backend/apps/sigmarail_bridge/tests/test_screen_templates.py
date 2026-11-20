from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db


def test_packaged_screen_templates_list_and_detail_require_membership(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with (
        patch("apps.sigmarail_bridge.screen_templates._workspace_for_request", return_value=(tenant, None)),
        patch("apps.sigmarail_bridge.views.dispatch_api_request") as legacy_request,
    ):
        response = client.get("/api/screens/templates")

        assert response.status_code == 200
        templates = response.json()["templates"]
        ids = {template["id"] for template in templates}
        assert len(templates) == 23
        assert "minervini_trend_template" in ids
        assert all(template["status"] == "active" for template in templates)

        detail = client.get("/api/screens/templates/minervini_trend_template")
        assert detail.status_code == 200
        document = detail.json()
        assert document["screen_ir"] == "universe_query_v1"
        assert document["spec"]["version"] == 1
        assert document["spec"]["from"] == "daily_screener"

        missing = client.get("/api/screens/templates/not_a_template")
        assert missing.status_code == 404
        legacy_request.assert_not_called()


def test_packaged_screen_templates_reject_unauthenticated_requests():
    response = APIClient().get("/api/screens/templates")

    assert response.status_code in (401, 403)
