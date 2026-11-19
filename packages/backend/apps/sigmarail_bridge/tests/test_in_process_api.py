import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.sigmarail_bridge.in_process_api import dispatch_api_request
from apps.sigmarail_bridge.views import DomainAPIRouteView, _forwarded_request_body

pytestmark = pytest.mark.django_db


def test_forwarded_json_body_survives_drfs_consumed_stream():
    payload = {"as_of": "2026-11-10", "spec": {"version": 1}}
    django_request = APIRequestFactory().post("/api/screens/preview-ir", payload, format="json")
    request = Request(django_request, parsers=[JSONParser()])

    assert request.data == payload
    assert _forwarded_request_body(request) == b'{"as_of":"2026-11-10","spec":{"version":1}}'

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
