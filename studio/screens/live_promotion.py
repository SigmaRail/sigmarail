"""Paper / live deployment registry helpers (live_deployments via ClickHouse)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from screens.lineage import (
    STUDIO_SCREEN_ID_KEY,
    STUDIO_SPEC_HASH_KEY,
    universe_spec_hash,
)
def _row_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return dict(zip(columns, row))


def _lineage_warnings(client: Any, *, ir_id: str) -> list[str]:
    """Soft warnings when saved screen hash differs from spec stamp (A0)."""
    warnings: list[str] = []
    spec_rows = client.query(
        "SELECT algorithm_json FROM strategy_algorithm_specs FINAL"
        " WHERE ir_id = %(ir_id)s LIMIT 1",
        parameters={"ir_id": ir_id},
    )
    if not spec_rows.result_rows:
        return warnings
    raw_json = spec_rows.result_rows[0][0]
    try:
        doc = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (TypeError, json.JSONDecodeError):
        return warnings
    if not isinstance(doc, dict):
        return warnings
    algo = doc.get("AlgorithmParameters")
    if not isinstance(algo, dict):
        return warnings
    stamped_hash = str(algo.get(STUDIO_SPEC_HASH_KEY) or "").strip()
    screen_id_raw = algo.get(STUDIO_SCREEN_ID_KEY)
    if not stamped_hash or screen_id_raw is None:
        return warnings
    try:
        from screens.screen_store import ScreenNotFoundError, get_screen_repository

        screen = get_screen_repository(client=client).get(str(screen_id_raw))
    except ScreenNotFoundError:
        return warnings
    except Exception:
        return warnings
    if not isinstance(screen.spec, dict):
        return warnings
    current_hash = screen.spec_content_hash or universe_spec_hash(screen.spec)
    if current_hash != stamped_hash:
        warnings.append(
            "Saved screen spec hash differs from stamped hash on algorithm spec "
            f"(screen_id={screen_id_raw}). Backtest used inline/stale universe; "
            "save screen before promote for reproducibility."
        )
    return warnings


def check_promotion_gate(
    client: Any,
    *,
    approval_backtest_run_id: str,
    ir_id: str,
) -> dict[str, Any]:
    """Verify a backtest run is eligible for paper promotion.

    Requires ``strategy_runs`` row; when a ``backtest_jobs`` row exists for the
    same id (run_id == job_id), its status must be ``done``.
    """
    run_id = (approval_backtest_run_id or "").strip()
    ir_id = (ir_id or "").strip()
    if not run_id:
        return {"ok": False, "code": "invalid_argument", "error": "approval_backtest_run_id is required"}
    if not ir_id:
        return {"ok": False, "code": "invalid_argument", "error": "ir_id is required"}

    run_rows = client.query(
        "SELECT run_id, ir_id, trimRight(CAST(ir_content_hash AS Nullable(String)), '\\0') AS ir_content_hash,"
        "       total_return, annual_return, sharpe_ratio, max_drawdown,"
        "       period_start, period_end, run_timestamp"
        " FROM strategy_runs FINAL WHERE run_id = %(run_id)s LIMIT 1",
        parameters={"run_id": run_id},
    )
    if not run_rows.result_rows:
        return {
            "ok": False,
            "code": "not_found",
            "error": f"backtest run not found: {run_id}",
        }

    run = _row_dict(run_rows.column_names, run_rows.result_rows[0])
    run_ir = str(run.get("ir_id") or "").strip()
    if run_ir != ir_id:
        return {
            "ok": False,
            "code": "ir_mismatch",
            "error": f"run ir_id {run_ir!r} does not match requested {ir_id!r}",
        }

    job_rows = client.query(
        "SELECT job_id, status FROM backtest_jobs FINAL WHERE job_id = %(jid)s LIMIT 1",
        parameters={"jid": run_id},
    )
    if job_rows.result_rows:
        job = _row_dict(job_rows.column_names, job_rows.result_rows[0])
        job_status = str(job.get("status") or "")
        if job_status != "done":
            return {
                "ok": False,
                "code": "job_not_done",
                "error": f"backtest job status is {job_status!r}; must be 'done'",
                "job_status": job_status,
            }

    run_hash = str(run.get("ir_content_hash") or "").strip()
    if not run_hash:
        return {
            "ok": False,
            "code": "run_strategy_hash_missing",
            "error": "backtest run has no strategy content hash; rerun the backtest before promotion",
        }
    try:
        from screens.backtest_jobs import get_spec_by_ir_id

        current_spec = get_spec_by_ir_id(client, ir_id)
    except Exception:
        current_spec = None
    current_hash = str((current_spec or {}).get("ir_content_hash") or "").strip()
    if not current_hash:
        return {
            "ok": False,
            "code": "current_strategy_missing",
            "error": "the saved strategy version could not be verified; save and backtest the current strategy before promotion",
        }
    if run_hash != current_hash:
        return {
            "ok": False,
            "code": "strategy_version_mismatch",
            "error": "the saved strategy changed after this backtest; rerun the current strategy before promotion",
        }

    report = get_backtest_report(client, run_id)
    metrics = report.get("metrics") if isinstance(report, dict) else None
    warnings = _lineage_warnings(client, ir_id=ir_id)

    return {
        "ok": True,
        "run_id": run_id,
        "ir_id": ir_id,
        "ir_content_hash": run_hash,
        "run_summary": {
            "period_start": run.get("period_start"),
            "period_end": run.get("period_end"),
            "run_timestamp": run.get("run_timestamp"),
            "total_return": run.get("total_return"),
            "annual_return": run.get("annual_return"),
            "sharpe_ratio": run.get("sharpe_ratio"),
            "max_drawdown": run.get("max_drawdown"),
        },
        "metrics": metrics,
        "highlights": report.get("highlights") if isinstance(report, dict) else [],
        "warnings": warnings,
    }


def register_paper_deployment(
    client: Any,
    *,
    deployment_id: str,
    ir_id: str,
    approval_backtest_run_id: str,
    lean_environment: str = "live-alpaca",
    brokerage: str = "AlpacaBrokerage",
    account_profile_id: str | None = None,
    account_identifier: str | None = None,
    promotion_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a row into ``live_deployments`` (paper promotion registry).

    Mirrors ``LeanProjects/VeraTradingLab/scripts/register_live_deployment.py``.
    """
    deployment_id = (deployment_id or "").strip() or str(uuid.uuid4())
    ir_id = (ir_id or "").strip()
    approval_backtest_run_id = (approval_backtest_run_id or "").strip()
    if not ir_id:
        raise ValueError("ir_id is required")
    if not approval_backtest_run_id:
        raise ValueError("approval_backtest_run_id is required")

    gate = promotion_gate
    if gate is None:
        gate = check_promotion_gate(
            client,
            approval_backtest_run_id=approval_backtest_run_id,
            ir_id=ir_id,
        )
    elif (
        gate.get("ok") is not True
        or str(gate.get("run_id") or "") != approval_backtest_run_id
        or str(gate.get("ir_id") or "") != ir_id
        or not str(gate.get("ir_content_hash") or "").strip()
    ):
        raise ValueError("promotion_gate: prevalidated gate does not match the requested run and strategy")
    if not gate.get("ok"):
        code = gate.get("code", "promotion_denied")
        err = gate.get("error", "promotion gate failed")
        raise ValueError(f"{code}: {err}")

    started_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    started_str = started_dt.strftime("%Y-%m-%d %H:%M:%S")
    parameter_values = {
        "VERA_LAB_ID": ir_id,
        "deployment_id": deployment_id,
        "approval_backtest_run_id": approval_backtest_run_id,
    }
    if account_profile_id:
        parameter_values["account_profile_id"] = account_profile_id
    if account_identifier:
        parameter_values["account_identifier"] = account_identifier
    parameters = json.dumps(
        parameter_values,
        separators=(",", ":"),
    )
    row = [
        deployment_id,
        ir_id,
        lean_environment,
        brokerage,
        "running",
        started_dt,
        None,
        approval_backtest_run_id,
        parameters,
    ]
    client.insert(
        "live_deployments",
        [row],
        column_names=[
            "deployment_id",
            "ir_id",
            "lean_environment",
            "brokerage",
            "status",
            "started_at",
            "stopped_at",
            "approval_backtest_run_id",
            "parameters",
        ],
    )

    return {
        "deployment_id": deployment_id,
        "ir_id": ir_id,
        "lean_environment": lean_environment,
        "brokerage": brokerage,
        "status": "running",
        "started_at": started_str,
        "approval_backtest_run_id": approval_backtest_run_id,
        "promotion_gate": gate,
    }


def list_live_deployments(client: Any, *, limit: int = 20) -> dict[str, Any]:
    """List recent deployments from ``live_deployments FINAL``."""
    return list_live_deployments_core(client, limit=limit)


def list_live_deployments_core(client: Any, *, limit: int = 20) -> dict[str, Any]:
    """Compatibility report adapter; requires the optional Vera runtime."""
    from vera_query_core.live_report import list_live_deployments as _list_live_deployments

    return _list_live_deployments(client, limit=limit)


def get_live_deployment_status(client: Any, deployment_id: str) -> dict[str, Any]:
    """Deployment status digest via ``vera_query_core.live_report.get_live_status``."""
    return get_live_status(client, deployment_id)


def get_live_status(client: Any, deployment_id: str) -> dict[str, Any]:
    """Compatibility report adapter; requires the optional Vera runtime."""
    from vera_query_core.live_report import get_live_status as _get_live_status

    return _get_live_status(client, deployment_id)


def get_backtest_report(client: Any, run_id: str) -> dict[str, Any]:
    """Compatibility report adapter; requires the optional Vera runtime."""
    from vera_query_core.backtest_report import get_backtest_report

    return get_backtest_report(client, run_id)


def update_deployment_status(client: Any, deployment_id: str, new_status: str) -> dict[str, Any]:
    """Append a replacement row for a locally controlled deployment lifecycle change."""
    if new_status not in {"stopped", "failed"}:
        raise ValueError("new_status must be stopped or failed")
    rows = client.query(
        "SELECT deployment_id, ir_id, lean_environment, brokerage, status, started_at, stopped_at, "
        "approval_backtest_run_id, parameters FROM live_deployments FINAL "
        "WHERE deployment_id = %(did)s LIMIT 1",
        parameters={"did": deployment_id},
    )
    if not rows.result_rows:
        raise ValueError(f"deployment not found: {deployment_id}")
    values = list(rows.result_rows[0])
    values[4] = new_status
    values[6] = datetime.now(timezone.utc).replace(tzinfo=None)
    client.insert(
        "live_deployments",
        [values],
        column_names=[
            "deployment_id", "ir_id", "lean_environment", "brokerage", "status",
            "started_at", "stopped_at", "approval_backtest_run_id", "parameters",
        ],
    )
    return {"deployment_id": deployment_id, "status": new_status}


__all__ = [
    "check_promotion_gate",
    "get_live_deployment_status",
    "list_live_deployments",
    "register_paper_deployment",
    "update_deployment_status",
]
