"""Live / paper deployment API tests (mocked — no ClickHouse required)."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from screens.live_promotion import (
    check_promotion_gate,
    get_live_deployment_status,
    list_live_deployments,
    register_paper_deployment,
)


_STRATEGY_HASH = hashlib.sha256(b"{}").hexdigest()


def _run_query_result(row: tuple | None = None) -> MagicMock:
    result = MagicMock()
    result.column_names = [
        "run_id",
        "ir_id",
        "ir_content_hash",
        "total_return",
        "annual_return",
        "sharpe_ratio",
        "max_drawdown",
        "period_start",
        "period_end",
        "run_timestamp",
    ]
    if row is None:
        row = (
            "run-abc",
            "ir-model-x",
            _STRATEGY_HASH,
            0.12,
            0.08,
            1.45,
            -0.15,
            "2024-01-01",
            "2024-12-31",
            "2026-08-20 12:00:00",
        )
    result.result_rows = [row] if row else []
    return result


def _job_query_result(status: str = "done") -> MagicMock:
    result = MagicMock()
    result.column_names = ["job_id", "status"]
    result.result_rows = [("run-abc", status)]
    return result


def _empty_spec_query_result() -> MagicMock:
    result = MagicMock()
    result.result_rows = []
    return result


def _gate_query_side_effect(job_status: str = "done") -> list[MagicMock]:
    return [
        _run_query_result(),
        _job_query_result(job_status),
        _empty_spec_query_result(),
    ]


def _deployments_query_result() -> MagicMock:
    result = MagicMock()
    result.column_names = [
        "deployment_id",
        "ir_id",
        "lean_environment",
        "brokerage",
        "status",
        "started_at",
        "stopped_at",
        "approval_backtest_run_id",
        "parameters",
        "created_at",
    ]
    result.result_rows = [
        (
            "dep-1",
            "ir-model-x",
            "live-alpaca",
            "AlpacaBrokerage",
            "running",
            "2026-08-20 14:00:00",
            None,
            "run-abc",
            "{}",
            "2026-08-20 14:00:00",
        )
    ]
    return result


def test_check_promotion_gate_happy() -> None:
    client = MagicMock()
    client.query.side_effect = _gate_query_side_effect("done")
    with patch(
        "screens.live_promotion.get_backtest_report",
        return_value={"metrics": {"total_return": 0.12}, "highlights": ["ok"]},
    ), patch(
        "screens.backtest_jobs.get_spec_by_ir_id",
        return_value={"ir_content_hash": _STRATEGY_HASH},
    ):
        out = check_promotion_gate(
            client,
            approval_backtest_run_id="run-abc",
            ir_id="ir-model-x",
        )
    assert out["ok"] is True
    assert out["run_id"] == "run-abc"
    assert out["run_summary"]["sharpe_ratio"] == 1.45
    assert out.get("warnings") == []


def test_check_promotion_gate_job_not_done() -> None:
    client = MagicMock()
    client.query.side_effect = [_run_query_result(), _job_query_result("running")]
    out = check_promotion_gate(
        client,
        approval_backtest_run_id="run-abc",
        ir_id="ir-model-x",
    )
    assert out["ok"] is False
    assert out["code"] == "job_not_done"


def test_check_promotion_gate_rejects_changed_saved_strategy() -> None:
    client = MagicMock()
    client.query.side_effect = [_run_query_result(), _job_query_result("done")]
    with patch("screens.backtest_jobs.get_spec_by_ir_id", return_value={"ir_content_hash": "changed-hash"}):
        out = check_promotion_gate(client, approval_backtest_run_id="run-abc", ir_id="ir-model-x")
    assert out["ok"] is False
    assert out["code"] == "strategy_version_mismatch"


def test_register_paper_deployment_inserts() -> None:
    client = MagicMock()
    client.query.side_effect = _gate_query_side_effect("done")
    with patch(
        "screens.live_promotion.get_backtest_report",
        return_value={"metrics": {}, "highlights": []},
    ), patch(
        "screens.backtest_jobs.get_spec_by_ir_id",
        return_value={"ir_content_hash": _STRATEGY_HASH},
    ):
        out = register_paper_deployment(
            client,
            deployment_id="dep-new",
            ir_id="ir-model-x",
            approval_backtest_run_id="run-abc",
        )
    assert out["deployment_id"] == "dep-new"
    assert out["status"] == "running"
    client.insert.assert_called_once()
    args = client.insert.call_args
    assert args[0][0] == "live_deployments"


def test_list_live_deployments_delegates() -> None:
    expected = {"deployments": [{"deployment_id": "dep-1"}]}
    with patch("screens.live_promotion.list_live_deployments_core", return_value=expected):
        out = list_live_deployments(MagicMock(), limit=5)
    assert out == expected


def test_get_live_deployment_status_delegates() -> None:
    expected = {"deployment": {"deployment_id": "dep-1"}, "highlights": []}
    with patch("screens.live_promotion.get_live_status", return_value=expected):
        out = get_live_deployment_status(MagicMock(), "dep-1")
    assert out == expected


@pytest.mark.django_db
def test_live_deployments_list_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.list_live_deployments",
        return_value={"deployments": [{"deployment_id": "dep-1"}]},
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/live/deployments?limit=5")
    assert resp.status_code == 200
    assert resp.json()["deployments"][0]["deployment_id"] == "dep-1"


@pytest.mark.django_db
def test_live_deployments_post_happy() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.register_paper_deployment",
        return_value={
            "deployment_id": "dep-new",
            "ir_id": "ir-x",
            "status": "running",
        },
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.post(
            "/api/live/deployments",
            data=json.dumps(
                {
                    "ir_id": "ir-x",
                    "approval_backtest_run_id": "run-abc",
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 201
    assert resp.json()["deployment_id"] == "dep-new"


@pytest.mark.django_db
def test_live_deployments_post_gate_denied_409() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.register_paper_deployment",
        side_effect=ValueError("job_not_done: backtest job status is 'running'"),
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.post(
            "/api/live/deployments",
            data=json.dumps(
                {
                    "ir_id": "ir-x",
                    "approval_backtest_run_id": "run-abc",
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_live_deployment_status_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.get_live_deployment_status",
        return_value={"deployment": {"deployment_id": "dep-1"}, "highlights": ["Equity: 100"]},
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/live/deployments/dep-1/status")
    assert resp.status_code == 200
    assert resp.json()["highlights"] == ["Equity: 100"]


@pytest.mark.django_db
def test_live_promotion_gate_endpoint_ok() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.check_promotion_gate",
        return_value={"ok": True, "run_id": "run-abc", "ir_id": "ir-x"},
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get(
            "/api/live/promotion-gate?ir_id=ir-x&approval_backtest_run_id=run-abc"
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
