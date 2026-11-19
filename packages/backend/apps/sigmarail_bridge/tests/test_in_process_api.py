import json
from types import SimpleNamespace
from unittest.mock import patch

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.sigmarail_bridge.in_process_api import dispatch_api_request
from apps.sigmarail_bridge.views import DomainAPIRouteView

def test_app_tension_route_executes_domain_api_in_process():
    user = SimpleNamespace(is_authenticated=True, is_anonymous=False, id=1, pk=1)
    request = APIRequestFactory().get("/api/screens/ir-schema", HTTP_X_TENANT_ID="test-tenant")
    force_authenticate(request, user=user)

    with (
        patch(
            "apps.sigmarail_bridge.views._workspace_for_request",
            return_value=(SimpleNamespace(id=1), None),
        ),
        patch(
            "apps.sigmarail_bridge.views.dispatch_api_request",
            wraps=dispatch_api_request,
        ) as dispatch,
    ):
        response = DomainAPIRouteView.as_view()(request)

    payload = json.loads(response.content)
    assert response.status_code == 200
    assert payload["title"] == "UniverseQueryV1"
    dispatch.assert_called_once()
    assert dispatch.call_args.args[:2] == ("GET", "/api/screens/ir-schema")
