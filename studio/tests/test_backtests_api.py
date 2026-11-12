"""Backtest API tests (mocked — no ClickHouse required)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from api.models import SavedScreen
from screens.backtest import get_run_report, list_backtest_runs
from screens.backtest_jobs import get_job_status, get_spec_by_ir_id, list_specs

_COMPOSE_FRAMEWORK = {
    "UniverseSelection": {"Type": "VeraScreenerUniverseSelectionModel", "Parameters": {}},
    "Alpha": {"Type": "RsiAlphaModel", "Parameters": {"period": 14, "resolution": "Daily"}},
    "PortfolioConstruction": {
        "Type": "VeraScreenerPortfolioConstructionModel",
        "Parameters": {"min_weight": 0.05, "max_weight": 0.25, "max_positions": 10},
    },
    "RiskManagement": {
        "Type": "MaximumDrawdownPercentPerSecurity",
        "Parameters": {"maximum_drawdown_percent": 0.05},
    },
    "Execution": {"Type": "ImmediateExecutionModel", "Parameters": {}},
}


def _sample_run_row() -> tuple:
    return (
        "run-abc123",
        "strat-1",
        "2026-08-20 14:30:00",
        "2024-01-01",
        "2026-08-01",
        "ir-model-x",
        "backtest",
        "mcp",
        0.12,
        0.08,
        1.45,
        1.80,
        -0.15,
        0.58,
        1.65,
        42,
        12.50,
        100000.0,
        112000.0,
        0.04,
        0.85,
        0.14,
        "deadbeef",
        "main",
        "RSI Momentum Strategy",
        json.dumps({
            "Framework": {
                "Alpha": {"Type": "RsiAlphaModel"},
                "UniverseSelection": {"Type": "ManualUniverseSelectionModel"},
                "RiskManagement": {"Type": "MaximumDrawdownPercentPerSecurity"},
            }
        }),
    )


def _runs_query_result(rows: list[tuple] | None = None) -> MagicMock:
    result = MagicMock()
    result.column_names = [
        "run_id",
        "strategy_id",
        "run_timestamp",
        "period_start",
        "period_end",
        "ir_id",
        "run_type",
        "trigger",
        "total_return",
        "annual_return",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "total_orders",
        "total_fees",
        "start_equity",
        "end_equity",
        "alpha",
        "beta",
        "volatility",
        "git_commit",
        "git_branch",
        "spec_title",
        "algorithm_json",
    ]
    result.result_rows = rows if rows is not None else [_sample_run_row()]
    return result


def _count_result(n: int = 0) -> MagicMock:
    result = MagicMock()
    result.result_rows = [(n,)]
    return result


def test_list_backtest_runs_happy() -> None:
    client = MagicMock()
    client.query.side_effect = [_count_result(3), _runs_query_result()]

    out = list_backtest_runs(client, limit=10, include_jobs=False)
    assert len(out["runs"]) == 1
    assert out["runs"][0]["run_id"] == "run-abc123"
    assert out["runs"][0]["ir_id"] == "ir-model-x"
    assert out["runs"][0]["sharpe_ratio"] == 1.45
    assert out["runs"][0]["alpha_type"] == "RsiAlphaModel"
    assert out["runs"][0]["spec_title"] == "RSI Momentum Strategy"
    assert "algorithm_json" not in out["runs"][0]
    assert out["total"] == 3
    assert client.query.call_count == 2
    sql = client.query.call_args[0][0]
    assert "strategy_runs" in sql
    assert "LIMIT %(limit)s" in sql
    assert client.query.call_args[1]["parameters"]["limit"] == 10


def test_list_backtest_runs_strategy_filter() -> None:
    client = MagicMock()
    client.query.return_value = _runs_query_result([])

    out = list_backtest_runs(client, strategy_id="my-strat", limit=5, include_jobs=False)
    assert out["runs"] == []
    _args, kwargs = client.query.call_args
    assert kwargs["parameters"]["sid"] == "my-strat"
    # WHERE is applied inside the strategy_runs FINAL subquery (filter-before-LIMIT),
    # so columns are unqualified (no `r.` alias inside the subquery).
    assert "strategy_id = %(sid)s" in _args[0]


def test_get_run_report_delegates() -> None:
    report = {
        "run_id": "run-abc123",
        "ir_id": "ir-model-x",
        "metrics": {"total_return": 0.12},
        "highlights": ["Total return: 12.00%"],
        "warnings": [],
    }
    with patch("screens.backtest.get_backtest_report", return_value=report) as mock_report:
        out = get_run_report(MagicMock(), "run-abc123")
    assert out == report
    mock_report.assert_called_once()


@pytest.mark.django_db
def test_backtest_runs_endpoint_happy() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = _runs_query_result()
        c = Client()
        resp = c.get("/api/backtests/runs?limit=5")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["run_id"] == "run-abc123"


@pytest.mark.django_db
def test_backtest_runs_invalid_limit_400() -> None:
    c = Client()
    resp = c.get("/api/backtests/runs?limit=not_int")
    assert resp.status_code == 400
    assert "limit" in resp.json()["detail"]


@pytest.mark.django_db
def test_backtest_runs_ch_error_502() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.side_effect = RuntimeError("connection refused")
        c = Client()
        resp = c.get("/api/backtests/runs")

    assert resp.status_code == 502
    assert "ClickHouse error" in resp.json()["detail"]


@pytest.mark.django_db
def test_backtest_report_endpoint_happy() -> None:
    report = {
        "run_id": "run-abc123",
        "ir_id": "ir-model-x",
        "period": {"start": "2024-01-01", "end": "2026-08-01"},
        "metrics": {"total_return": 0.12, "sharpe_ratio": 1.45},
        "highlights": ["Total return: 12.00%"],
        "warnings": ["git_commit is local — MCP path did not record repo SHA"],
        "provenance": {"git_commit": "local", "git_branch": "main"},
    }
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.get_run_report",
        return_value=report,
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/backtests/runs/run-abc123/report")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run-abc123"
    assert body["metrics"]["sharpe_ratio"] == 1.45
    assert len(body["highlights"]) == 1


@pytest.mark.django_db
def test_backtest_report_not_found_404() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.get_run_report",
        return_value={"error": "run not found: missing", "code": "not_found"},
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/backtests/runs/missing/report")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.django_db
def test_backtest_report_ch_error_502() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.get_run_report",
        side_effect=RuntimeError("timeout"),
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/backtests/runs/run-abc123/report")

    assert resp.status_code == 502
    assert "ClickHouse error" in resp.json()["detail"]


def _sample_universe() -> dict:
    return {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "rs_rating"],
        "where": {
            "type": "gte",
            "left": {"type": "col", "name": "rs_rating"},
            "right": {"type": "lit", "value": 70},
        },
        "order_by": [{"field": "rs_rating", "direction": "desc"}],
        "limit_per_day": 25,
    }


def _specs_query_result(rows: list[tuple] | None = None) -> MagicMock:
    result = MagicMock()
    result.column_names = [
        "ir_id",
        "title",
        "spec_schema_version",
        "notes",
        "created_at",
        "algorithm_json",
    ]
    result.result_rows = rows if rows is not None else [
        (
            "studio-test-abc123",
            "Test Strategy",
            2,
            "Custom test notes",
            "2026-08-20 12:00:00",
            json.dumps({
                "Framework": {
                    "Alpha": {"Type": "RsiAlphaModel"},
                    "UniverseSelection": {"Type": "ManualUniverseSelectionModel", "Parameters": {"symbols": ["AAPL"]}},
                    "RiskManagement": {"Type": "MaximumDrawdownPercentPerSecurity"},
                },
                "VeraBase": {
                    "Universe": {
                        "from": "daily_screener",
                        "where": {"items": [{"field": "rs_rating", "op": ">=", "value": 70}]},
                        "order_by": [{"field": "rs_rating", "direction": "desc"}],
                    }
                }
            }),
        ),
    ]
    return result


def _job_query_result(row: tuple | None = None) -> MagicMock:
    result = MagicMock()
    result.column_names = [
        "job_id",
        "ir_id",
        "start_date",
        "end_date",
        "status",
        "runner_id",
        "submitted_at",
        "started_at",
        "completed_at",
        "lean_output_path",
        "extra_env",
        "error_message",
        "created_at",
    ]
    if row is None:
        result.result_rows = [
            (
                "job-1",
                "studio-test-abc123",
                "2024-01-01",
                "2024-12-31",
                "pending",
                "",
                "2026-08-20 12:00:00",
                None,
                None,
                "",
                "{}",
                "",
                "2026-08-20 12:00:00",
            )
        ]
    else:
        result.result_rows = [row] if row else []
    return result


def test_list_specs_happy() -> None:
    client = MagicMock()
    client.query.return_value = _specs_query_result()
    out = list_specs(client, limit=10)
    assert len(out["specs"]) >= 1
    # Check that built-in templates or db spec exist
    found_db = next((s for s in out["specs"] if s["ir_id"] == "studio-test-abc123"), None)
    assert found_db is not None
    assert found_db["alpha_type"] == "RsiAlphaModel"
    assert found_db["symbols"] == ["AAPL"]
    assert found_db["screener_summary"]["has_screener"] is True


def test_get_spec_by_ir_id_builtin_removed() -> None:
    """Legacy system templates are no longer served from specs detail."""
    client = MagicMock()
    client.query.return_value = MagicMock(result_rows=[])
    out = get_spec_by_ir_id(client, "hybrid_rsi")
    assert out is None


def test_get_spec_by_ir_id_db() -> None:
    client = MagicMock()
    client.query.return_value = _specs_query_result()
    out = get_spec_by_ir_id(client, "studio-test-abc123")
    assert out is not None
    assert out["ir_id"] == "studio-test-abc123"
    assert out["alpha_type"] == "RsiAlphaModel"
    assert out["spec"]["Framework"]["Alpha"]["Type"] == "RsiAlphaModel"


def test_get_job_status_happy() -> None:
    client = MagicMock()
    client.query.return_value = _job_query_result()
    row = get_job_status(client, "job-1")
    assert row is not None
    assert row["job_id"] == "job-1"
    assert row["status"] == "pending"


@pytest.mark.django_db
def test_framework_catalog_endpoint() -> None:
    c = Client()
    resp = c.get("/api/backtests/framework-catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert "framework_catalog" in body
    assert "strategy_templates" in body
    assert body["strategy_templates"] == []


@pytest.mark.django_db
def test_compose_endpoint_inline_universe() -> None:
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "framework": _COMPOSE_FRAMEWORK,
                "title": "RSI Leaders",
                "universe": {"source": "inline", "inline_spec": _sample_universe()},
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["spec"]["Kind"] == "VeraLabV1"
    assert body["ir_id_suggested"].startswith("studio-rsi-leaders-")
    assert body["validation"]["ok"] is True


@pytest.mark.django_db
def test_compose_endpoint_inline_spec_alias() -> None:
    """Frontend historically sent source=inline_spec; accept as alias for inline."""
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "framework": _COMPOSE_FRAMEWORK,
                "universe": {"source": "inline_spec", "inline_spec": _sample_universe()},
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["spec"]["VeraBase"]["Universe"] == _sample_universe()


@pytest.mark.django_db
def test_compose_endpoint_saved_screen() -> None:
    screen = SavedScreen.objects.create(name="saved-leaders", spec=_sample_universe())
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "framework": _COMPOSE_FRAMEWORK,
                "universe": {"source": "saved_screen", "saved_screen_id": screen.pk},
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["spec"]["VeraBase"]["Universe"] == _sample_universe()


@pytest.mark.django_db
def test_compose_endpoint_screener_overrides(tmp_path, monkeypatch) -> None:
    import screens.strategy_compose as sc

    tid = "compose_stub"
    monkeypatch.setattr(sc, "STRATEGY_TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(
        sc,
        "_STRATEGY_TEMPLATE_META",
        {tid: {"label": "Stub", "description": "test"}},
    )
    (tmp_path / f"{tid}.json").write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Kind": "VeraLabV1",
                "VeraBase": {},
                "Framework": {
                    "UniverseSelection": {"Type": "VeraScreenerUniverseSelectionModel", "Parameters": {}},
                    "Alpha": {
                        "Type": "VeraScreenerAlphaModel",
                        "Parameters": {"max_positions": 10, "stop_loss_pct": 0.08, "min_hold_days": 5},
                    },
                    "PortfolioConstruction": {
                        "Type": "EqualWeightingPortfolioConstructionModel",
                        "Parameters": {
                            "max_positions": 10,
                            "max_weight": 0.25,
                            "min_weight": 0.05,
                            "target_atr_risk": 0.01,
                        },
                    },
                    "RiskManagement": {"Type": "MaximumDrawdownPercentPerSecurity", "Parameters": {}},
                    "Execution": {"Type": "ImmediateExecutionModel", "Parameters": {}},
                },
                "AlgorithmParameters": {"regime-source": "screener"},
            }
        ),
        encoding="utf-8",
    )
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "template_id": tid,
                "title": "Screener overrides",
                "universe": {"source": "inline", "inline_spec": _sample_universe()},
                "framework_overrides": {
                    "Alpha": {
                        "Parameters": {"max_positions": 15, "stop_loss_pct": 0.07},
                    },
                    "PortfolioConstruction": {
                        "Parameters": {
                            "max_positions": 15,
                            "max_weight": 0.2,
                            "target_atr_risk": 0.005,
                        },
                    },
                },
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    alpha = body["spec"]["Framework"]["Alpha"]["Parameters"]
    assert alpha["max_positions"] == 15
    assert alpha["min_hold_days"] == 5
    pcm = body["spec"]["Framework"]["PortfolioConstruction"]["Parameters"]
    assert pcm["max_weight"] == 0.2


@pytest.mark.django_db
def test_compose_endpoint_rejects_flat_overrides(tmp_path, monkeypatch) -> None:
    import screens.strategy_compose as sc

    tid = "compose_stub"
    monkeypatch.setattr(sc, "STRATEGY_TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(
        sc,
        "_STRATEGY_TEMPLATE_META",
        {tid: {"label": "Stub", "description": "test"}},
    )
    (tmp_path / f"{tid}.json").write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Kind": "VeraLabV1",
                "VeraBase": {},
                "Framework": _COMPOSE_FRAMEWORK,
                "AlgorithmParameters": {},
            }
        ),
        encoding="utf-8",
    )
    c = Client()
    resp = c.post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "template_id": tid,
                "universe": {"source": "inline", "inline_spec": _sample_universe()},
                "framework_overrides": {
                    "max_positions": 15,
                    "stop_loss_pct": 0.08,
                    "max_weight": 0.1,
                    "target_atr_risk": 0.004,
                },
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "max_positions" in resp.json()["detail"]


@pytest.mark.django_db
def test_specs_list_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = _specs_query_result()
        c = Client()
        resp = c.get("/api/backtests/specs?limit=5")
    assert resp.status_code == 200
    specs = resp.json()["specs"]
    assert len(specs) >= 1
    assert any(s["ir_id"] == "studio-test-abc123" for s in specs)


@pytest.mark.django_db
def test_specs_post_runner_missing_503() -> None:
    with patch("api.views.exec_adapter.save_spec", None):
        c = Client()
        resp = c.post(
            "/api/backtests/specs",
            data=json.dumps(
                {
                    "ir_id": "studio-x",
                    "title": "X",
                    "spec": {"Kind": "VeraLabV1"},
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 503
    assert "backtest runner" in resp.json()["detail"]


@pytest.mark.django_db
def test_specs_post_happy() -> None:
    # The view now saves through screens.spec_save.save_spec_guarded (fork guard),
    # NOT exec_adapter.save_spec directly — patch the guard so the test stays
    # hermetic. Without this the guard executes for real and writes a spec row
    # into ClickHouse (it did once: ir_id "studio-x").
    with patch("api.views.exec_adapter.runner_available", return_value=True), patch(
        "api.views.spec_save.save_spec_guarded"
    ) as mock_save:
        mock_save.return_value = {
            "ir_id": "studio-x",
            "inserted": True,
            "spec_schema_version": 2,
            "ir_content_hash": "abc",
        }
        c = Client()
        resp = c.post(
            "/api/backtests/specs",
            data=json.dumps(
                {
                    "ir_id": "studio-x",
                    "title": "X",
                    "spec": {"Kind": "VeraLabV1", "SchemaVersion": 2},
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 201
    assert resp.json()["inserted"] is True
    mock_save.assert_called_once()


@pytest.mark.django_db
def test_submit_endpoint_happy() -> None:
    with patch("api.views.exec_adapter.runner_available", return_value=True), patch(
        "api.views.exec_adapter.submit_backtest_job",
        return_value={"job_id": "job-99", "status": "running", "pid": 1234},
    ) as mock_submit:
        c = Client()
        resp = c.post(
            "/api/backtests/jobs",
            data=json.dumps(
                {
                    "ir_id": "studio-x",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "immediate": True,
                }
            ),
            content_type="application/json",
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == "job-99"
    assert body["status"] == "running"
    mock_submit.assert_called_once()


@pytest.mark.django_db
def test_submit_runner_missing_503() -> None:
    with patch("api.views.exec_adapter.runner_available", return_value=False):
        c = Client()
        resp = c.post(
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
    assert resp.status_code == 503


@pytest.mark.django_db
def test_job_status_endpoint_happy() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = _job_query_result()
        c = Client()
        resp = c.get("/api/backtests/jobs/job-1")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-1"


@pytest.mark.django_db
def test_job_status_not_found_404() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = _job_query_result(row=())
        c = Client()
        resp = c.get("/api/backtests/jobs/missing")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_spec_detail_endpoint_builtin_gone() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = MagicMock(result_rows=[])
        c = Client()
        resp = c.get("/api/backtests/specs/hybrid_rsi")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_spec_detail_endpoint_not_found_404() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value.query.return_value = MagicMock(result_rows=[])
        c = Client()
        resp = c.get("/api/backtests/specs/nonexistent-spec-999")
    assert resp.status_code == 404
