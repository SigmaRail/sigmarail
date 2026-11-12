"""Execution adapter API tests (mocked — no ClickHouse/Docker required)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from screens import execution as exec_adapter


@pytest.mark.django_db
def test_execution_health_endpoint() -> None:
    with patch(
        "api.views.exec_adapter.execution_health",
        return_value={
            "docker": True,
            "lean_cli": True,
            "clickhouse": True,
            "worker_recent": False,
            "ready": True,
            "messages": [],
        },
    ):
        resp = Client().get("/api/execution/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["clickhouse"] is True


@pytest.mark.django_db
def test_execution_projects_endpoint() -> None:
    with patch(
        "api.views.exec_adapter.list_lean_projects",
        return_value={
            "projects": [{"id": "VeraTradingLab", "label": "Vera Trading Lab"}],
            "registry_path": "/tmp/lean_projects.yaml",
        },
    ):
        resp = Client().get("/api/execution/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"][0]["id"] == "VeraTradingLab"


@pytest.mark.django_db
def test_backtest_jobs_list_endpoint() -> None:
    with patch(
        "api.views.exec_adapter.list_recent_jobs",
        return_value={
            "jobs": [{"job_id": "job-1", "status": "pending", "ir_id": "studio-x"}],
            "count": 1,
        },
    ):
        resp = Client().get("/api/backtests/jobs?limit=5&status=pending")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["jobs"][0]["job_id"] == "job-1"


@pytest.mark.django_db
def test_backtest_job_log_endpoint_happy() -> None:
    with patch(
        "api.views.exec_adapter.get_job_log_tail",
        return_value={
            "job_id": "job-1",
            "log_path": "/tmp/lean-backtest.log",
            "lines": ["line one", "line two"],
            "text": "line one\nline two",
        },
    ):
        resp = Client().get("/api/backtests/jobs/job-1/log?tail=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lines"] == ["line one", "line two"]


@pytest.mark.django_db
def test_backtest_job_log_not_found_404() -> None:
    with patch(
        "api.views.exec_adapter.get_job_log_tail",
        return_value={"job_id": "missing", "error": "log file not found", "lines": []},
    ):
        resp = Client().get("/api/backtests/jobs/missing/log")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_submit_queue_mode_default() -> None:
    with patch("api.views.exec_adapter.runner_available", return_value=True), patch(
        "api.views.exec_adapter.submit_backtest_job",
        return_value={"job_id": "job-q", "status": "pending", "lean_project": "VeraTradingLab"},
    ) as mock_submit:
        resp = Client().post(
            "/api/backtests/jobs",
            data=json.dumps(
                {
                    "ir_id": "studio-x",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
    mock_submit.assert_called_once()
    _kwargs = mock_submit.call_args.kwargs
    assert _kwargs["immediate"] is False
    assert _kwargs["lean_project"] == "VeraTradingLab"


@pytest.mark.django_db
def test_submit_immediate_with_lean_project() -> None:
    with patch("api.views.exec_adapter.runner_available", return_value=True), patch(
        "api.views.exec_adapter.submit_backtest_job",
        return_value={"job_id": "job-imm", "status": "running", "lean_project": "VeraTradingLab"},
    ) as mock_submit:
        resp = Client().post(
            "/api/backtests/jobs",
            data=json.dumps(
                {
                    "ir_id": "studio-x",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "immediate": True,
                    "lean_project": "VeraTradingLab",
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    mock_submit.assert_called_once_with(
        ir_id="studio-x",
        start_date="2024-01-01",
        end_date="2024-12-31",
        lean_project="VeraTradingLab",
        immediate=True,
        extra_env=None,
    )


def test_list_lean_projects_fallback() -> None:
    from pathlib import Path

    with patch(
        "screens.execution.lean_projects_root",
        return_value=Path("/nonexistent/LeanProjects"),
    ):
        out = exec_adapter.list_lean_projects()
    assert out["projects"][0]["id"] == "VeraTradingLab"
    assert "note" in out


def test_execution_health_fallback_structure() -> None:
    with patch("screens.execution._runner_preflight", None), patch(
        "screens.execution.runner_available",
        return_value=True,
    ), patch(
        "screens.execution._docker_available",
        return_value=(True, "ok"),
    ), patch(
        "screens.execution._lean_cli_available",
        return_value=(True, "/usr/bin/lean"),
    ), patch(
        "screens.execution._clickhouse_ping",
        return_value=(True, "ok"),
    ), patch(
        "screens.execution._worker_recent",
        return_value=(True, "activity within 10m"),
    ):
        out = exec_adapter.execution_health()
    assert out["ready"] is True
    assert out["docker"] is True
    assert out["clickhouse"] is True


def test_list_recent_jobs_query_shape() -> None:
    client = MagicMock()
    client.query.return_value = MagicMock(column_names=["job_id", "status"], result_rows=[])
    with patch("screens.execution.get_ch_client", return_value=client):
        out = exec_adapter.list_recent_jobs(limit=10, status="pending")
    assert out["jobs"] == []
    sql = client.query.call_args[0][0]
    assert "GROUP BY job_id" in sql
    assert "argMax(lean_project, created_at)" in sql
    assert "max(created_at) AS created_at_max" in sql
    assert "HAVING argMax(status, created_at) = %(status)s" in sql
    assert client.query.call_args.kwargs["parameters"]["status"] == "pending"


@pytest.mark.django_db
def test_cancel_backtest_job_endpoint() -> None:
    with patch("api.views.exec_adapter.cancel_backtest_job", return_value={"job_id": "j1", "status": "cancelled"}):
        c = Client()
        resp = c.post("/api/backtests/jobs/j1/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
