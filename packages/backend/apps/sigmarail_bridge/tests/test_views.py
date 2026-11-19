import json
from unittest.mock import patch

import httpx
import pytest
from graphql_relay import to_global_id
from rest_framework.test import APIClient

from apps.sigmarail_bridge.models import (
    WorkspaceBacktestReference,
    WorkspaceDeploymentReference,
    WorkspaceOptimizerReference,
    WorkspaceStrategyReference,
)

pytestmark = pytest.mark.django_db


def test_bridge_requires_an_authenticated_user():
    client = APIClient()

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as request_upstream:
        response = client.get("/api/screens/fields")

    assert response.status_code in (401, 403)
    request_upstream.assert_not_called()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/screens/fields?category=core", None),
        ("post", "/api/backtests/compose", b'{"ir_id":"example"}'),
    ],
)
def test_authenticated_bridge_forwards_route_and_body_without_credentials(
    method, path, body, user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["token"] = "app-tension-session-token"
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={"ok": True},
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response) as request_upstream:
        response = getattr(client, method)(
            path,
            data=body,
            content_type="application/json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    args, kwargs = request_upstream.call_args
    assert args[:2] == (method.upper(), path.split("?", 1)[0])
    if body is not None:
        assert kwargs["content"] == body
    assert kwargs["user"] == user
    assert kwargs["headers"]["x-tenant-id"] == to_global_id("TenantType", tenant.id)
    assert "cookie" not in kwargs["headers"]
    assert "authorization" not in kwargs["headers"]


def test_authenticated_bridge_requires_active_workspace(user):
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as request_upstream:
        response = client.get("/api/screens/fields")

    assert response.status_code == 400
    request_upstream.assert_not_called()


def test_authenticated_bridge_rejects_a_workspace_without_membership(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as request_upstream:
        response = client.get(
            "/api/screens/fields",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    request_upstream.assert_not_called()


def test_strategy_catalog_marks_legacy_records_shared_and_hides_other_workspaces(
    user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, creator=user, tenant=tenant)
    WorkspaceStrategyReference.objects.create(
        tenant=tenant, created_by=user, owner_user=user, ir_id="mine", synced=True
    )
    WorkspaceStrategyReference.objects.create(tenant=other_workspace, ir_id="other", synced=True)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/specs?limit=10")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "specs": [
                {"ir_id": "legacy", "is_system": False},
                {"ir_id": "system", "is_system": True},
                {"ir_id": "mine", "is_system": False},
                {"ir_id": "other", "is_system": False},
            ],
            "count": 4,
        },
    )
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response) as upstream:
        response = client.get(
            "/api/backtests/specs?limit=10",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    records = {item["ir_id"]: item for item in response.json()["specs"]}
    assert set(records) == {"legacy", "system", "mine"}
    assert records["legacy"]["is_shared"] is True
    assert records["system"]["is_shared"] is False
    assert records["mine"]["is_shared"] is False
    assert response.json()["count"] == 3
    assert upstream.call_args.args[1] == "/api/backtests/specs"
    assert upstream.call_args.kwargs["query"] == "limit=10"


def test_new_strategy_save_registers_workspace_ownership(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    existing_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/specs/tenant-owned")
    saved_request = httpx.Request("POST", "http://studio-api.internal:8001/api/backtests/specs")
    responses = [
        httpx.Response(404, request=existing_request, json={"detail": "not found"}),
        httpx.Response(201, request=saved_request, json={"ir_id": "tenant-owned", "title": "Owned strategy"}),
    ]

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", side_effect=responses) as upstream:
        response = client.post(
            "/api/backtests/specs",
            {"ir_id": "tenant-owned", "title": "Owned strategy", "spec": {"SchemaVersion": 2}},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 201
    assert response.json()["is_shared"] is False
    reference = WorkspaceStrategyReference.objects.get(ir_id="tenant-owned")
    assert reference.tenant == tenant
    assert reference.created_by == user
    assert reference.synced is True
    assert upstream.call_count == 2
    assert upstream.call_args.args[0] == "POST"


def test_existing_unowned_strategy_cannot_be_saved_in_place(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    existing_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/specs/shared")
    existing_response = httpx.Response(200, request=existing_request, json={"ir_id": "shared"})

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=existing_response) as upstream:
        response = client.post(
            "/api/backtests/specs",
            {"ir_id": "shared", "title": "Changed", "spec": {"SchemaVersion": 2}},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    assert response.json()["code"] == "strategy_shared_read_only"
    upstream.assert_called_once()
    assert not WorkspaceStrategyReference.objects.filter(ir_id="shared").exists()


def test_strategy_spec_read_and_mutation_are_scoped_to_owning_workspace(
    user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceStrategyReference.objects.create(tenant=other_workspace, ir_id="private", synced=True)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        detail = client.get(
            "/api/backtests/specs/private",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )
        mutation = client.post(
            "/api/backtests/specs/private/pipeline-ops",
            {"operation": "patch"},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert detail.status_code == 404
    assert mutation.status_code == 404
    upstream.assert_not_called()


def test_shared_strategy_pipeline_mutations_are_rejected(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        response = client.post(
            "/api/backtests/specs/legacy/pipeline-ops",
            {"operation": "patch"},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    assert response.json()["code"] == "strategy_shared_read_only"
    upstream.assert_not_called()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/backtests/jobs", {"ir_id": "other-workspace-strategy"}),
        ("/api/backtests/optimize", {"base_ir_id": "other-workspace-strategy"}),
        ("/api/live/deployments", {"ir_id": "other-workspace-strategy"}),
    ],
)
def test_strategy_execution_writes_cannot_reference_another_workspace_strategy(
    path, payload, user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceStrategyReference.objects.create(
        tenant=other_workspace,
        ir_id="other-workspace-strategy",
        synced=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        response = client.post(
            path,
            payload,
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Strategy spec not found."
    upstream.assert_not_called()


def test_submitted_backtest_is_assigned_to_the_active_workspace(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("POST", "http://studio-api.internal:8001/api/backtests/jobs")

    def submit(method, url, *, content, **kwargs):
        payload = json.loads(content)
        return httpx.Response(
            202,
            request=upstream_request,
            json={"job_id": payload["job_id"], "status": "pending"},
        )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", side_effect=submit) as upstream:
        response = client.post(
            "/api/backtests/jobs",
            {"ir_id": "shared-legacy", "start_date": "2025-01-01", "end_date": "2026-01-01"},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 202
    assert response.json()["is_shared"] is False
    reference = WorkspaceBacktestReference.objects.get(job_id=response.json()["job_id"])
    assert reference.run_id == reference.job_id
    assert reference.ir_id == "shared-legacy"
    assert reference.tenant == tenant
    assert reference.created_by == user
    forwarded_payload = json.loads(upstream.call_args.kwargs["content"])
    assert forwarded_payload["job_id"] == reference.job_id


def test_backtest_catalog_hides_other_workspaces_and_marks_legacy_rows_shared(
    user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceBacktestReference.objects.create(
        tenant=tenant,
        ir_id="owned-strategy",
        job_id="owned-job",
        run_id="owned-job",
        created_by=user,
    )
    WorkspaceBacktestReference.objects.create(
        tenant=other_workspace,
        ir_id="private-strategy",
        job_id="private-job",
        run_id="private-job",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/runs")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "runs": [
                {"run_id": "owned-job", "ir_id": "owned-strategy"},
                {"run_id": "private-job", "ir_id": "private-strategy"},
                {"run_id": "legacy-run", "ir_id": "legacy-strategy"},
            ],
            "count": 3,
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get(
            "/api/backtests/runs",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    runs = {run["run_id"]: run for run in response.json()["runs"]}
    assert set(runs) == {"owned-job", "legacy-run"}
    assert runs["owned-job"]["is_shared"] is False
    assert runs["legacy-run"]["is_shared"] is True
    assert response.json()["count"] == 2


def test_optimizer_launch_assigns_session_variants_and_jobs_to_workspace(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("POST", "http://studio-api.internal:8001/api/backtests/optimize")
    upstream_response = httpx.Response(
        201,
        request=upstream_request,
        json={
            "session_id": "workspace-session",
            "base_ir_id": "shared-base",
            "jobs": [{"job_id": "variant-job", "ir_id": "owned-variant"}],
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.post(
            "/api/backtests/optimize",
            {"base_ir_id": "shared-base"},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 201
    assert response.json()["is_shared"] is False
    assert WorkspaceOptimizerReference.objects.get(session_id="workspace-session").tenant == tenant
    strategy = WorkspaceStrategyReference.objects.get(ir_id="owned-variant")
    assert strategy.tenant == tenant
    assert strategy.synced is True
    backtest = WorkspaceBacktestReference.objects.get(job_id="variant-job")
    assert backtest.tenant == tenant
    assert backtest.run_id == "variant-job"


def test_optimizer_session_catalog_hides_other_workspaces_and_keeps_legacy_shared(
    user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceOptimizerReference.objects.create(
        tenant=other_workspace,
        session_id="private-session",
        base_ir_id="private-strategy",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/optimize/sessions")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "sessions": [{"session_id": "private-session"}, {"session_id": "legacy-session"}],
            "count": 2,
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get(
            "/api/backtests/optimize/sessions",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    sessions = {item["session_id"]: item for item in response.json()["sessions"]}
    assert set(sessions) == {"legacy-session"}
    assert sessions["legacy-session"]["is_shared"] is True
    assert response.json()["count"] == 1


def test_paper_deployment_registration_is_assigned_to_the_active_workspace(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("POST", "http://studio-api.internal:8001/api/live/deployments")

    def register(method, url, *, content, **kwargs):
        payload = json.loads(content)
        return httpx.Response(
            201,
            request=upstream_request,
            json={"deployment_id": payload["deployment_id"], "ir_id": payload["ir_id"]},
        )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", side_effect=register) as upstream:
        response = client.post(
            "/api/live/deployments",
            {"ir_id": "shared-legacy", "approval_backtest_run_id": "shared-run"},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 201
    assert response.json()["is_shared"] is False
    reference = WorkspaceDeploymentReference.objects.get(deployment_id=response.json()["deployment_id"])
    assert reference.tenant == tenant
    assert reference.created_by == user
    assert reference.ir_id == "shared-legacy"
    assert json.loads(upstream.call_args.kwargs["content"])["deployment_id"] == reference.deployment_id


def test_deployment_catalog_hides_other_workspaces_and_marks_legacy_shared(
    user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceDeploymentReference.objects.create(
        tenant=other_workspace,
        deployment_id="private-deployment",
        ir_id="private-strategy",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/live/deployments")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "deployments": [
                {"deployment_id": "private-deployment"},
                {"deployment_id": "legacy-deployment"},
            ],
            "count": 2,
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get(
            "/api/live/deployments",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    deployments = {item["deployment_id"]: item for item in response.json()["deployments"]}
    assert set(deployments) == {"legacy-deployment"}
    assert deployments["legacy-deployment"]["is_shared"] is True
    assert response.json()["count"] == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/backtests/jobs/private-job",
        "/api/backtests/runs/private-job/report",
        "/api/backtests/compare?run_ids=private-job",
        "/api/backtests/optimize/sessions/private-session",
        "/api/live/deployments/private-deployment/status",
        "/api/live/promotion-gate?ir_id=private-strategy&approval_backtest_run_id=private-job",
    ],
)
def test_detail_and_compare_routes_reject_other_workspace_records(
    path, user, tenant, tenant_factory, tenant_membership_factory
):
    other_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    WorkspaceBacktestReference.objects.create(
        tenant=other_workspace,
        ir_id="private-strategy",
        job_id="private-job",
        run_id="private-job",
    )
    WorkspaceOptimizerReference.objects.create(
        tenant=other_workspace,
        session_id="private-session",
        base_ir_id="private-strategy",
    )
    WorkspaceDeploymentReference.objects.create(
        tenant=other_workspace,
        deployment_id="private-deployment",
        ir_id="private-strategy",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        response = client.get(path, HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id))

    assert response.status_code == 404
    upstream.assert_not_called()


def test_shared_legacy_backtest_cannot_be_cancelled(user, tenant, tenant_membership_factory):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        response = client.post(
            "/api/backtests/jobs/shared-job/cancel",
            {},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 403
    assert response.json()["code"] == "shared_backtest_read_only"
    upstream.assert_not_called()


def test_workspace_broker_account_metadata_is_owned_in_postgres_and_secrets_are_not_copied(
    user, tenant, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceBrokerAccountReference

    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("POST", "http://studio-api.internal:8001/api/live/accounts")

    def save_account(method, url, *, content, **kwargs):
        payload = json.loads(content)
        assert payload["credentials"] == {"alpaca-api-key": "fixture-key", "alpaca-api-secret": "fixture-secret"}
        return httpx.Response(
            200,
            request=upstream_request,
            json={
                "id": payload["id"],
                "provider": payload["provider"],
                "data_provider": payload["data_provider"],
                "environment": payload["environment"],
                "display_name": payload["display_name"],
                "account_identifier": payload["account_identifier"],
                "active": True,
                "credentials_configured": True,
                "connection_verification_available": True,
                "updated_at": "2026-11-16T12:00:00+00:00",
            },
        )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", side_effect=save_account):
        response = client.post(
            "/api/live/accounts",
            {
                "provider": "alpaca",
                "data_provider": "alpaca",
                "environment": "paper",
                "display_name": "Research paper",
                "account_identifier": "account-fixture",
                "credentials": {
                    "alpaca-api-key": "fixture-key",
                    "alpaca-api-secret": "fixture-secret",
                },
            },
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    reference = WorkspaceBrokerAccountReference.objects.get(profile_id=response.json()["id"])
    assert reference.tenant == tenant
    assert reference.created_by == user
    assert reference.provider == "alpaca"
    assert reference.data_provider == "alpaca"
    assert reference.environment == "paper"
    assert reference.display_name == "Research paper"
    assert reference.account_identifier == "account-fixture"
    assert reference.active is True
    assert "fixture-secret" not in str(reference.__dict__)


def test_workspace_account_reads_prefer_postgres_metadata_and_sync_active_changes(
    user, tenant, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceBrokerAccountReference

    tenant_membership_factory(user=user, tenant=tenant)
    account = WorkspaceBrokerAccountReference.objects.create(
        tenant=tenant,
        created_by=user,
        profile_id="workspace-paper-account",
        provider="alpaca",
        data_provider="alpaca",
        environment="paper",
        display_name="Postgres name",
        account_identifier="postgres-account",
        active=False,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/live/accounts")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "profiles": [
                {
                    "id": account.profile_id,
                    "provider": "alpaca",
                    "data_provider": "alpaca",
                    "environment": "paper",
                    "display_name": "Stale SQLite name",
                    "account_identifier": "stale-account",
                    "active": True,
                    "credentials_configured": True,
                    "updated_at": "2026-11-16T12:00:00+00:00",
                },
                {"id": "unowned-profile", "environment": "paper"},
            ],
            "count": 2,
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get(
            "/api/live/accounts",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    profile = response.json()["profiles"][0]
    assert profile["display_name"] == "Postgres name"
    assert profile["account_identifier"] == "postgres-account"
    assert profile["active"] is False
    assert profile["credentials_configured"] is True

    upstream_request = httpx.Request("PATCH", f"http://studio-api.internal:8001/api/live/accounts/{account.profile_id}")
    upstream_response = httpx.Response(200, request=upstream_request, json={"active": True})
    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        update_response = client.patch(
            f"/api/live/accounts/{account.profile_id}",
            {"active": True},
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert update_response.status_code == 200
    account.refresh_from_db()
    assert account.active is True


def test_legacy_sqlite_account_metadata_is_imported_on_first_workspace_read(
    user, tenant, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceBrokerAccountReference

    tenant_membership_factory(user=user, tenant=tenant)
    account = WorkspaceBrokerAccountReference.objects.create(
        tenant=tenant,
        created_by=user,
        profile_id="legacy-paper-account",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/live/accounts")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={
            "profiles": [
                {
                    "id": account.profile_id,
                    "provider": "alpaca",
                    "data_provider": "alpaca",
                    "environment": "paper",
                    "display_name": "Imported account",
                    "account_identifier": "legacy-id",
                    "active": False,
                    "credentials_configured": True,
                    "updated_at": "2026-11-15T12:00:00+00:00",
                },
            ],
            "count": 1,
        },
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get(
            "/api/live/accounts",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
        )

    assert response.status_code == 200
    assert response.json()["profiles"][0]["display_name"] == "Imported account"
    account.refresh_from_db()
    assert account.provider == "alpaca"
    assert account.data_provider == "alpaca"
    assert account.environment == "paper"
    assert account.display_name == "Imported account"
    assert account.account_identifier == "legacy-id"
    assert account.active is False


def test_workspace_screen_list_is_scoped_and_keeps_legacy_screens_read_only(
    user, tenant_factory, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceScreen

    workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=workspace)
    client = APIClient()
    client.force_authenticate(user=user)
    legacy_request = httpx.Request("GET", "http://studio-api.internal:8001/api/screens/saved")
    legacy_response = httpx.Response(
        200,
        request=legacy_request,
        json={
            "screens": [
                {"id": "default", "name": "Built in", "is_system": True, "spec": {}},
                {"id": "old-123", "name": "Legacy screen", "is_system": False, "spec": {}},
            ]
        },
    )
    WorkspaceScreen.objects.create(
        tenant=workspace,
        created_by=user,
        owner_user=user,
        name="Workspace screen",
        spec={"version": 1},
    )

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=legacy_response):
        response = client.get(
            "/api/screens/saved",
            HTTP_X_TENANT_ID=to_global_id("TenantType", workspace.id),
        )

    assert response.status_code == 200
    screens = response.json()["screens"]
    system_screens = [screen for screen in screens if screen.get("is_system")]
    assert len(system_screens) == 23
    assert "canslim" in {str(screen["id"]) for screen in system_screens}
    assert [(screen["id"], screen.get("is_shared", False)) for screen in screens if not screen.get("is_system")] == [
        ("shared:old-123", True),
        (str(WorkspaceScreen.objects.get(name="Workspace screen").id), False),
    ]


def test_workspace_screen_list_marks_malformed_shared_catalog_unavailable(
    user, tenant_factory, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceScreen

    workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=workspace)
    WorkspaceScreen.objects.create(
        tenant=workspace,
        created_by=user,
        owner_user=user,
        name="Workspace screen",
        spec={"version": 1},
    )
    malformed_response = httpx.Response(
        200,
        request=httpx.Request("GET", "http://studio-api.internal:8001/api/screens/saved"),
        json={"screens": None},
    )
    client = APIClient()
    client.force_authenticate(user=user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=malformed_response):
        response = client.get(
            "/api/screens/saved",
            HTTP_X_TENANT_ID=to_global_id("TenantType", workspace.id),
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["shared_catalog_available"] is False
    assert "temporarily unavailable" in payload["shared_catalog_warning"]
    assert "Built-in templates" in payload["shared_catalog_warning"]
    screens = payload["screens"]
    assert len([screen for screen in screens if screen.get("is_system")]) == 23
    system_screens = [screen for screen in screens if screen.get("is_system")]
    assert all(screen.get("spec", {}).get("from") == "daily_screener" for screen in system_screens)
    assert [screen["name"] for screen in screens if not screen.get("is_system")] == ["Workspace screen"]


def test_workspace_screen_create_and_update_are_isolated_by_membership(
    user, user_factory, tenant_factory, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceScreen

    first_workspace = tenant_factory()
    second_workspace = tenant_factory()
    tenant_membership_factory(user=user, tenant=first_workspace)
    other_user = user_factory()
    tenant_membership_factory(user=other_user, tenant=second_workspace)
    client = APIClient()
    client.force_authenticate(user=user)

    created = client.post(
        "/api/screens/saved",
        {"name": "Private screen", "spec": {"version": 1}},
        format="json",
        HTTP_X_TENANT_ID=to_global_id("TenantType", first_workspace.id),
    )
    assert created.status_code == 201
    assert created.json()["is_shared"] is False
    screen_id = created.json()["id"]

    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    missing = outsider.put(
        f"/api/screens/saved/{screen_id}",
        {"name": "Stolen", "spec": {"version": 2}},
        format="json",
        HTTP_X_TENANT_ID=to_global_id("TenantType", second_workspace.id),
    )
    assert missing.status_code == 404
    assert WorkspaceScreen.objects.get(id=screen_id).name == "Private screen"


def test_saving_shared_screen_creates_workspace_copy(user, tenant, tenant_membership_factory):
    from apps.sigmarail_bridge.models import WorkspaceScreen

    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        "/api/screens/saved/shared:old-123",
        {"name": "My copy", "description": "Private copy", "spec": {"version": 1}},
        format="json",
        HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
    )

    assert response.status_code == 201
    assert response.json()["is_shared"] is False
    assert WorkspaceScreen.objects.filter(id=response.json()["id"], tenant=tenant, name="My copy").exists()


def test_saved_screens_are_private_between_members_of_the_same_workspace(
    user, user_factory, tenant, tenant_membership_factory
):
    from apps.sigmarail_bridge.models import WorkspaceScreen

    other_user = user_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    tenant_membership_factory(user=other_user, tenant=tenant)
    owner_client = APIClient()
    owner_client.force_authenticate(user=user)
    created = owner_client.post(
        "/api/screens/saved",
        {"name": "Private screen", "spec": {"version": 1}},
        format="json",
        HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
    )
    assert created.status_code == 201

    other_client = APIClient()
    other_client.force_authenticate(user=other_user)
    with patch(
        "apps.sigmarail_bridge.views.dispatch_api_request",
        return_value=httpx.Response(
            200,
            request=httpx.Request("GET", "http://studio-api.internal/api/screens/saved"),
            json={"screens": []},
        ),
    ):
        listed = other_client.get("/api/screens/saved", HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id))
    hidden = other_client.put(
        f"/api/screens/saved/{created.json()['id']}",
        {"name": "Changed", "spec": {"version": 2}},
        format="json",
        HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
    )
    deleted = other_client.delete(
        f"/api/screens/saved/{created.json()['id']}",
        HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id),
    )

    assert listed.status_code == 200
    listed_screens = listed.json()["screens"]
    assert len([screen for screen in listed_screens if screen.get("is_system")]) == 23
    assert all(screen.get("is_system") for screen in listed_screens)
    assert hidden.status_code == 404
    assert deleted.status_code == 404
    assert WorkspaceScreen.objects.get(id=created.json()["id"]).owner_user == user


def test_strategy_catalog_hides_another_members_private_strategy(
    user, user_factory, tenant, tenant_membership_factory
):
    other_user = user_factory()
    tenant_membership_factory(user=user, tenant=tenant)
    tenant_membership_factory(user=other_user, tenant=tenant)
    WorkspaceStrategyReference.objects.create(
        tenant=tenant,
        created_by=user,
        owner_user=user,
        ir_id="private-to-owner",
        synced=True,
    )
    upstream_request = httpx.Request("GET", "http://studio-api.internal:8001/api/backtests/specs")
    upstream_response = httpx.Response(
        200,
        request=upstream_request,
        json={"specs": [{"ir_id": "private-to-owner", "is_system": False}], "count": 1},
    )
    client = APIClient()
    client.force_authenticate(user=other_user)

    with patch("apps.sigmarail_bridge.views.dispatch_api_request", return_value=upstream_response):
        response = client.get("/api/backtests/specs", HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.id))

    assert response.status_code == 200
    assert response.json()["specs"] == []


def test_workspace_saved_screens_require_authentication_and_membership():
    client = APIClient()
    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        unauthenticated = client.get("/api/screens/saved", HTTP_X_TENANT_ID="workspace")
        assert unauthenticated.status_code in (401, 403)
        upstream.assert_not_called()


def test_workspace_saved_screens_require_active_workspace(user):
    client = APIClient()
    client.force_authenticate(user=user)
    with patch("apps.sigmarail_bridge.views.dispatch_api_request") as upstream:
        response = client.get("/api/screens/saved")

    assert response.status_code == 400
    upstream.assert_not_called()
