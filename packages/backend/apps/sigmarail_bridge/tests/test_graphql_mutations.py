from types import SimpleNamespace
from unittest.mock import patch

import pytest
from graphql_relay import to_global_id
from rest_framework.test import APIClient

from apps.sigmarail_bridge.graphql import Mutation
from apps.sigmarail_bridge.models import WorkspaceBacktestReference, WorkspaceScreen, WorkspaceStrategyReference
from sigmarail_spec.strategy import get_preset

pytestmark = pytest.mark.django_db


def test_save_screen_compiles_ast_before_writing():
    tenant = SimpleNamespace(pk="tenant-1")
    screen_spec = {"version": 1, "from": "daily_screener", "select": ["ticker"], "where": {}}
    expected = {"ok": True, "result": {"id": "screen-1"}}
    with (
        patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant),
        patch("sigmarail.universe.compile_universe_spec", return_value=("SELECT 1", {})) as compile_spec,
        patch("apps.sigmarail_bridge.graphql._workspace_api_call", return_value=expected) as api_call,
    ):
        result = Mutation.resolve_sigmarail_save_screen(
            None,
            SimpleNamespace(context=SimpleNamespace(user=object())),
            "tenant-relay-id",
            "momentum leaders",
            screen_spec,
        )

    assert result is expected
    compile_spec.assert_called_once_with(screen_spec)
    assert api_call.call_args.args[1:4] == (tenant, "POST", "/api/screens/saved")
    assert api_call.call_args.args[4]["spec"] == screen_spec


def test_save_strategy_compiles_and_persists_canonical_pipeline_pair():
    tenant = SimpleNamespace(pk="tenant-1")
    pipeline = get_preset("minervini_sepa_weighted").model_dump(mode="json")
    expected = {"ok": True, "result": {"ir_id": "agent-sepa"}}
    with (
        patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant),
        patch("apps.sigmarail_bridge.graphql._workspace_api_call", return_value=expected) as api_call,
    ):
        result = Mutation.resolve_sigmarail_save_strategy(
            None,
            SimpleNamespace(context=SimpleNamespace(user=object())),
            "tenant-relay-id",
            "agent-sepa",
            "Agent SEPA",
            pipeline,
        )

    assert result is expected
    payload = api_call.call_args.args[4]
    assert api_call.call_args.args[1:4] == (tenant, "POST", "/api/backtests/specs")
    assert payload["pipeline_document"] == pipeline
    assert isinstance(payload["spec"], dict)
    assert payload["spec"]


def test_invalid_strategy_ast_is_rejected_without_writing():
    tenant = SimpleNamespace(pk="tenant-1")
    with (
        patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant),
        patch("apps.sigmarail_bridge.graphql._workspace_api_call") as api_call,
    ):
        result = Mutation.resolve_sigmarail_save_strategy(
            None,
            SimpleNamespace(context=SimpleNamespace(user=object())),
            "tenant-relay-id",
            "bad-strategy",
            "Bad strategy",
            {"invalid": True},
        )

    assert result["ok"] is False
    assert result["code"] == "INVALID_STRATEGY_AST"
    api_call.assert_not_called()


def test_experiment_decision_requires_completed_tenant_owned_run(user, tenant):
    pending = WorkspaceBacktestReference.objects.create(
        tenant=tenant,
        created_by=user,
        job_id="pending-mcp-job",
        ir_id="strategy-a",
        status="running",
    )
    with patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant):
        result = Mutation.resolve_sigmarail_record_experiment_decision(
            None,
            SimpleNamespace(context=SimpleNamespace(user=user)),
            "tenant-relay-id",
            pending.job_id,
            "retain",
            "Early result looks promising.",
        )
    assert result["ok"] is False
    assert result["code"] == "BACKTEST_NOT_COMPLETE"


def test_experiment_decision_is_saved_with_hashes_and_actor(user, tenant):
    run = WorkspaceBacktestReference.objects.create(
        tenant=tenant,
        created_by=user,
        job_id="completed-mcp-job",
        ir_id="strategy-a",
        strategy_content_hash="strategy-sha256",
        configuration={"request_hash": "request-sha256"},
        status="done",
    )
    with patch("apps.sigmarail_bridge.graphql._authorize_tenant", return_value=tenant):
        result = Mutation.resolve_sigmarail_record_experiment_decision(
            None,
            SimpleNamespace(context=SimpleNamespace(user=user)),
            "tenant-relay-id",
            run.job_id,
            "revise",
            "The result needs a broader OOS check.",
            {"trade_count": 18},
        )

    run.refresh_from_db()
    event = run.configuration["research_decision"]
    assert result["ok"] is True
    assert event["decision"] == "revise"
    assert event["evidence"] == {"trade_count": 18}
    assert event["strategy_content_hash"] == "strategy-sha256"
    assert event["request_hash"] == "request-sha256"
    assert event["recorded_by"] == str(user.pk)


def test_graphql_screen_mutation_persists_tenant_owned_screen(user, tenant, tenant_membership_factory):
    from screens.adapter import preset_to_universe_spec

    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/graphql/",
        {
            "query": """
              mutation SaveScreen($tenantId: ID!, $screenName: String!, $spec: GenericScalar!) {
                sigmarailSaveScreen(tenantId: $tenantId, screenName: $screenName, spec: $spec)
              }
            """,
            "variables": {
                "tenantId": to_global_id("TenantType", tenant.id),
                "screenName": "MCP screen integration",
                "spec": preset_to_universe_spec("leaders"),
            },
        },
        format="json",
    )

    assert response.status_code == 200
    assert "errors" not in response.json()
    payload = response.json()["data"]["sigmarailSaveScreen"]
    assert payload["ok"] is True, response.json()
    screen = WorkspaceScreen.objects.get(name="MCP screen integration", tenant=tenant, owner_user=user)
    assert screen.spec["version"] == 2


def test_graphql_strategy_mutation_compiles_and_persists_tenant_owned_strategy(
    user, tenant, tenant_membership_factory
):
    tenant_membership_factory(user=user, tenant=tenant)
    client = APIClient()
    client.force_authenticate(user=user)
    pipeline = get_preset("minervini_sepa_weighted").model_dump(mode="json")
    response = client.post(
        "/api/graphql/",
        {
            "query": """
              mutation SaveStrategy($tenantId: ID!, $irId: String!, $title: String!, $pipelineDocument: GenericScalar!) {
                sigmarailSaveStrategy(tenantId: $tenantId, irId: $irId, title: $title, pipelineDocument: $pipelineDocument)
              }
            """,
            "variables": {
                "tenantId": to_global_id("TenantType", tenant.id),
                "irId": "mcp-integration-strategy",
                "title": "MCP integration strategy",
                "pipelineDocument": pipeline,
            },
        },
        format="json",
    )

    assert response.status_code == 200
    assert "errors" not in response.json()
    payload = response.json()["data"]["sigmarailSaveStrategy"]
    assert payload["ok"] is True, response.json()
    strategy = WorkspaceStrategyReference.objects.get(ir_id="mcp-integration-strategy", tenant=tenant)
    assert strategy.owner_user_id == user.pk
    assert strategy.pipeline_document == pipeline
    assert strategy.spec
