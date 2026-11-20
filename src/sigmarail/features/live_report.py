"""Agent-oriented live deployment + snapshot reads."""

from __future__ import annotations

import json
from typing import Any


def _row_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return dict(zip(columns, row))


def list_live_deployments(
    client: Any,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    valid = {"running", "stopped", "failed"}
    limit = max(1, min(int(limit), 200))
    where = ""
    params: dict[str, Any] = {}
    if status:
        if status not in valid:
            return {
                "error": f"status must be one of: {', '.join(sorted(valid))}",
                "code": "invalid_argument",
            }
        where = "WHERE status = %(status)s"
        params["status"] = status

    rows = client.query(
        "SELECT deployment_id, ir_id, lean_environment, brokerage, status,"
        "       started_at, stopped_at, approval_backtest_run_id, parameters, created_at"
        f" FROM live_deployments FINAL {where}"
        " ORDER BY started_at DESC"
        f" LIMIT {limit}",
        parameters=params,
    )
    return {
        "deployments": [_row_dict(rows.column_names, r) for r in rows.result_rows],
    }


def _latest_snapshot(client: Any, deployment_id: str) -> dict[str, Any] | None:
    rows = client.query(
        "SELECT deployment_id, as_of, equity, cash, buying_power, day_pnl, total_pnl,"
        "       positions_json, source, created_at"
        " FROM live_account_snapshots"
        " WHERE deployment_id = %(did)s"
        " ORDER BY as_of DESC, created_at DESC"
        " LIMIT 1",
        parameters={"did": deployment_id},
    )
    if not rows.result_rows:
        return None
    snap = _row_dict(rows.column_names, rows.result_rows[0])
    pj = snap.get("positions_json")
    if isinstance(pj, str) and pj:
        try:
            snap["positions"] = json.loads(pj)
        except json.JSONDecodeError:
            snap["positions"] = []
    return snap


def get_live_status(client: Any, deployment_id: str) -> dict[str, Any]:
    deployment_id = (deployment_id or "").strip()
    if not deployment_id:
        return {"error": "deployment_id is required", "code": "invalid_argument"}

    dep_rows = client.query(
        "SELECT deployment_id, ir_id, lean_environment, brokerage, status,"
        "       started_at, stopped_at, approval_backtest_run_id, parameters"
        " FROM live_deployments FINAL WHERE deployment_id = %(did)s LIMIT 1",
        parameters={"did": deployment_id},
    )
    if not dep_rows.result_rows:
        return {"error": f"deployment not found: {deployment_id}", "code": "not_found"}

    deployment = _row_dict(dep_rows.column_names, dep_rows.result_rows[0])
    snapshot = _latest_snapshot(client, deployment_id)

    spec_summary: dict[str, Any] | None = None
    ir_id = deployment.get("ir_id")
    if ir_id:
        spec_rows = client.query(
            "SELECT ir_id, title, spec_schema_version, notes, created_at"
            " FROM strategy_algorithm_specs FINAL WHERE ir_id = %(ir_id)s LIMIT 1",
            parameters={"ir_id": str(ir_id)},
        )
        if spec_rows.result_rows:
            spec_summary = _row_dict(spec_rows.column_names, spec_rows.result_rows[0])

    approval_report: dict[str, Any] | None = None
    approval_run = deployment.get("approval_backtest_run_id")
    if approval_run:
        from sigmarail.features.backtest_report import get_backtest_report

        approval_report = get_backtest_report(client, str(approval_run))

    highlights: list[str] = []
    if snapshot:
        if snapshot.get("equity") is not None:
            highlights.append(f"Equity: {snapshot['equity']}")
        if snapshot.get("cash") is not None:
            highlights.append(f"Cash: {snapshot['cash']}")
        if snapshot.get("as_of"):
            highlights.append(f"Snapshot as_of: {snapshot['as_of']}")
    else:
        highlights.append("No snapshots yet — register deployment and run live ingest")

    return {
        "deployment": deployment,
        "latest_snapshot": snapshot,
        "spec_summary": spec_summary,
        "approval_backtest_report": approval_report,
        "highlights": highlights,
    }


def get_live_performance(
    client: Any,
    deployment_id: str,
    days: int = 30,
) -> dict[str, Any]:
    deployment_id = (deployment_id or "").strip()
    if not deployment_id:
        return {"error": "deployment_id is required", "code": "invalid_argument"}
    days = max(1, min(int(days), 365))

    rows = client.query(
        "SELECT as_of, equity, cash, day_pnl, total_pnl, source"
        " FROM live_account_snapshots"
        " WHERE deployment_id = %(did)s"
        " AND as_of >= today() - %(days)s"
        " ORDER BY as_of ASC",
        parameters={"did": deployment_id, "days": days},
    )
    series = [_row_dict(rows.column_names, r) for r in rows.result_rows]
    return {
        "deployment_id": deployment_id,
        "days": days,
        "points": series,
        "point_count": len(series),
    }
