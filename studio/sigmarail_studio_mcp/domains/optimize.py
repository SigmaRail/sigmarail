"""optimize domain: sweep sessions, response surfaces, Pareto frontiers (Studio screens)."""
from __future__ import annotations

import json
from typing import Any

from sigmarail_studio_mcp.ch import call, get_client


def list_runs(limit: int = 50, policy_source: str | None = "search") -> dict[str, Any]:
    from sigmarail.features.platform_tools import list_optimizer_runs

    return call(list_optimizer_runs, limit=limit, policy_source=policy_source)


def policy_scorecard(policy_name: str, asset_ticker: str = "SPY", window: str | None = None) -> dict[str, Any]:
    from sigmarail.features.platform_tools import get_policy_scorecard

    return call(get_policy_scorecard, policy_name=policy_name, asset_ticker=asset_ticker, window=window)


# --- Studio sweep sessions (Component 2: implementation plan) ----------------


def list_sessions(limit: int = 20, base_ir_id: str | None = None) -> dict[str, Any]:
    """List recent hyperparameter sweep sessions with status and metrics."""
    from screens.optimizer import list_optimizer_sessions

    def _list(client: Any) -> dict[str, Any]:
        sessions = list_optimizer_sessions(client, limit=limit)
        if base_ir_id:
            sessions = [s for s in sessions if s.get("base_ir_id") == base_ir_id]
        return {"sessions": sessions}

    return call(_list)


def launch_sweep(
    base_ir_id: str,
    param_x_name: str,
    param_x_values: list[float],
    param_y_name: str | None = None,
    param_y_values: list[float] | None = None,
    start_date: str = "",
    end_date: str = "",
    strategy_type: str = "euler",
    oos_days: int = 60,
    objective: str = "sharpe_ratio",
    title: str | None = None,
    max_concurrent: int = 4,
    lean_project: str = "VeraTradingLab",
) -> dict[str, Any]:
    """Launch a 1D or 2D hyperparameter sweep session (Euler or grid)."""
    from screens.optimizer import create_and_launch_optimization_session

    def _launch(client: Any) -> dict[str, Any]:
        from datetime import datetime, timedelta, timezone

        s_date = (start_date or "").strip()
        e_date = (end_date or "").strip()
        if not s_date or not e_date:
            end_dt = datetime.now(timezone.utc).date()
            start_dt = end_dt - timedelta(days=365)
            s_date = s_date or start_dt.isoformat()
            e_date = e_date or end_dt.isoformat()
        return create_and_launch_optimization_session(
            client=client,
            base_ir_id=base_ir_id,
            start_date=s_date,
            end_date=e_date,
            param_x_name=param_x_name,
            param_x_values=param_x_values,
            param_y_name=param_y_name,
            param_y_values=param_y_values,
            title=title or "",
            objective=objective,
            strategy_type=strategy_type,
            oos_days=oos_days,
            max_concurrent=max_concurrent,
            lean_project=lean_project,
        )

    return call(_launch)


def get_session_heatmap(session_id: str) -> dict[str, Any]:
    """Parameter response surface, heatmap grid, and completed run points."""
    from screens.optimizer import get_optimizer_session_heatmap

    def _heat(client: Any) -> dict[str, Any]:
        return get_optimizer_session_heatmap(session_id, client=client)

    return call(_heat)


def get_pareto_frontier(session_id: str) -> dict[str, Any]:
    """Non-dominated Pareto optimal runs (max Return/Sharpe, min MaxDD)."""
    hm = get_session_heatmap(session_id)
    if "error" in hm:
        return hm
    return {
        "session_id": session_id,
        "is_done": hm.get("is_done", False),
        "pareto_frontier": hm.get("pareto_frontier", []),
        "best_run": hm.get("best_run"),
        "total_points": len(hm.get("all_points", [])),
    }


def cancel_session(session_id: str) -> dict[str, Any]:
    """Mark a sweep session cancelled and cancel its pending backtest jobs."""
    from screens import execution

    client = get_client()
    try:
        try:
            client.command(
                "ALTER TABLE strategy_optimizer_sessions UPDATE status = 'cancelled', updated_at = now() WHERE session_id = %(sid)s",
                parameters={"sid": session_id},
            )
        except Exception:
            pass
        jobs = client.query(
            "SELECT job_id FROM backtest_jobs FINAL WHERE extra_env LIKE %(pat)s AND status IN ('pending', 'running')",
            parameters={"pat": f'%"OPTIMIZER_SESSION_ID": "{session_id}"%'},
        )
        cancelled: list[str] = []
        for (jid,) in jobs.result_rows:
            try:
                execution.cancel_job(jid)
                cancelled.append(jid)
            except Exception:
                pass
        return {"session_id": session_id, "status": "cancelled", "cancelled_jobs": cancelled}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()


def promote_optimal_run(
    session_id: str,
    run_id: str,
    new_ir_id: str,
    title: str,
    changelog: str = "",
) -> dict[str, Any]:
    """Patch the sweep base spec with the winning combo and save as a new version."""
    from screens.optimizer import _deep_inject_param, get_optimizer_session_heatmap

    client = get_client()
    try:
        hm = get_optimizer_session_heatmap(session_id, client=client)
        if "error" in hm:
            return hm
        point = next((p for p in hm.get("all_points", []) if p.get("run_id") == run_id), None)
        if not point:
            return {"error": f"run_id {run_id} not found in session {session_id}", "code": "not_found"}

        base_ir_id = hm.get("session", {}).get("base_ir_id")
        base_rows = client.query(
            "SELECT algorithm_json FROM strategy_algorithm_specs FINAL WHERE ir_id = %(id)s LIMIT 1",
            parameters={"id": base_ir_id},
        )
        if not base_rows.result_rows:
            return {"error": f"base spec {base_ir_id} not found", "code": "not_found"}

        import copy

        raw = base_rows.result_rows[0][0]
        spec = json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)
        for k, v in (point.get("combo") or point.get("parameters") or {}).items():
            _deep_inject_param(spec, k, v)

        from sigmarail_studio_mcp.backtest_runner.runner import save_spec as _save

        combo_keys = list((point.get("combo") or point.get("parameters") or {}).keys())
        saved = _save(
            ir_id=new_ir_id,
            title=title,
            spec_json=json.dumps(spec),
            notes=f"Promoted from sweep {session_id} run {run_id}. {changelog}".strip(),
            parent_ir_id=base_ir_id,
            mutation_type="sweep_promotion",
            changelog_notes=changelog or f"Optimized {combo_keys} via sweep {session_id}",
        )
        return {
            "saved": True,
            "ir_id": new_ir_id,
            "promoted_run_id": run_id,
            "params": point.get("combo") or point.get("parameters"),
            "save": saved,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()
