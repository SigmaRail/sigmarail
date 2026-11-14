"""backtest domain: read-side report + comparison + specs/runs/jobs (thin hooks)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call, get_client, try_call


def _rows(client: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = client.query(sql, parameters=params or {})
    return [dict(zip(result.column_names, r)) for r in result.result_rows]


def report(run_id: str) -> dict[str, Any]:
    """Agent-friendly digest for one run (metrics/highlights/warnings)."""
    from sigmarail.features.backtest_report import get_backtest_report

    if not run_id or not run_id.strip():
        return {"error": "run_id is required", "code": "invalid_argument"}
    return call(get_backtest_report, run_id=run_id.strip())


def list_runs_by_ir_id(ir_id: str, limit: int = 20) -> dict[str, Any]:
    from sigmarail.features.backtest_report import list_runs_by_ir_id as _list

    return call(_list, ir_id=ir_id, limit=limit)


def wait(job_id: str, timeout_sec: int = 3600, poll_interval_sec: float = 5) -> dict[str, Any]:
    from sigmarail.features.backtest_report import wait_for_backtest

    return call(wait_for_backtest, job_id=job_id, timeout_sec=timeout_sec, poll_interval_sec=poll_interval_sec)


def list_specs(limit: int = 20) -> dict[str, Any]:
    """Enriched spec metadata (shared with REST ``/backtests/specs`` list)."""
    from screens.backtest_jobs import list_specs as _list_specs

    return call(_list_specs, limit=limit)


def get_spec(ir_id: str) -> dict[str, Any]:
    """Full spec (algorithm_json + parsed ``spec``), shared with REST detail."""
    from screens.backtest_jobs import get_spec_by_ir_id

    if not ir_id or not ir_id.strip():
        return {"error": "ir_id is required", "code": "invalid_argument"}
    result = call(get_spec_by_ir_id, ir_id=ir_id.strip())
    if result is None:
        return {"error": f"spec not found: {ir_id}", "code": "not_found"}
    return result


def list_runs(strategy_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Enriched run metadata (shared with REST ``/backtests/runs`` list)."""
    from screens.backtest import list_backtest_runs

    return call(list_backtest_runs, strategy_id=strategy_id, limit=limit)


def get_run(run_id: str) -> dict[str, Any]:
    if not run_id or not run_id.strip():
        return {"error": "run_id is required", "code": "invalid_argument"}
    client = get_client()
    try:
        run_rows = _rows(client, "SELECT * FROM strategy_runs FINAL WHERE run_id = %(run_id)s LIMIT 1", {"run_id": run_id.strip()})
        if not run_rows:
            return {"error": f"run not found: {run_id}", "code": "not_found"}
        run = run_rows[0]
        run["artifacts"] = _rows(
            client,
            "SELECT artifact_type, artifact_json FROM strategy_run_artifacts FINAL WHERE run_id = %(run_id)s",
            {"run_id": run_id.strip()},
        )
        return run
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()


def list_jobs(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Recent jobs (latest row per job_id; shared with REST ``/backtests/jobs``)."""
    from screens import execution

    valid = {"pending", "running", "done", "failed"}
    if status and status not in valid:
        return {"error": f"status must be one of: {', '.join(sorted(valid))}", "code": "invalid_argument"}
    return try_call(execution.list_recent_jobs, limit=limit, status=status)


# --- write-side (folded from vera-mcp-backtest) ---------------------------
def save_spec(
    ir_id: str,
    title: str,
    spec_json: str,
    notes: str = "",
    spec_schema_version: int | None = None,
    force_new_version: bool = False,
    changelog_notes: str = "",
    author_agent: str = "agent",
) -> dict[str, Any]:
    """Save a spec; FORKS automatically when ``ir_id`` already has backtest runs.

    Guarded save (see ``screens/spec_save.py``): editing a spec that already has
    runs mints a new ``ir_id`` with ``parent_ir_id`` + ``mutation_type="fork"``
    rather than overwriting, so an existing run is never re-pointed at content it
    did not produce.

    **The returned ``ir_id`` may differ from the one passed in** — check
    ``forked`` and use the returned value for follow-up calls such as
    ``strategy_submit_backtest``.
    """
    from screens.spec_save import save_spec_guarded

    return try_call(
        save_spec_guarded,
        ir_id=ir_id,
        title=title,
        spec_json=spec_json,
        notes=notes,
        spec_schema_version=spec_schema_version,
        force_fork=force_new_version,
        changelog_notes=changelog_notes,
        author_agent=author_agent,
    )


def save_from_template(
    template_id: str,
    ir_id: str | None = None,
    title: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    from sigmarail_studio_mcp.backtest_runner.strategy import create_spec_from_strategy_template

    return try_call(
        create_spec_from_strategy_template,
        template_id=template_id,
        ir_id=ir_id,
        title=title,
        notes=notes,
    )


def submit(ir_id: str, start_date: str, end_date: str, job_id: str | None = None, immediate: bool = False, extra_env: dict[str, str] | None = None, lean_project: str | None = None) -> dict[str, Any]:
    from sigmarail_studio_mcp.backtest_runner.runner import run_job, submit_job

    def _do() -> dict[str, Any]:
        jid = submit_job(ir_id, start_date, end_date, job_id=job_id, extra_env=extra_env, lean_project=lean_project)
        if immediate:
            return run_job(jid, ir_id, start_date, end_date, extra_env=extra_env, lean_project=lean_project)
        return {"job_id": jid, "status": "pending"}

    return try_call(_do)


def submit_from_template(
    template_id: str,
    start_date: str,
    end_date: str,
    ir_id: str | None = None,
    immediate: bool = False,
    extra_env: dict[str, str] | None = None,
    lean_project: str | None = None,
) -> dict[str, Any]:
    from sigmarail_studio_mcp.backtest_runner.strategy import submit_backtest_from_template

    return try_call(
        submit_backtest_from_template,
        template_id=template_id,
        start_date=start_date,
        end_date=end_date,
        ir_id=ir_id,
        immediate=immediate,
        extra_env=extra_env,
        lean_project=lean_project,
    )


def job_status(job_id: str) -> dict[str, Any]:
    """Full job row incl. telemetry (shared with REST ``/backtests/jobs/<id>``)."""
    from screens.backtest_jobs import get_job_status

    if not job_id or not job_id.strip():
        return {"error": "job_id is required", "code": "invalid_argument"}
    result = call(get_job_status, job_id=job_id.strip())
    if result is None:
        return {"error": f"job not found: {job_id}", "code": "not_found"}
    return result


def cancel(job_id: str) -> dict[str, Any]:
    from sigmarail_studio_mcp.backtest_runner.runner import cancel_job

    return try_call(cancel_job, job_id=job_id)


def investigate(
    job_id: str,
    heartbeat_stale_seconds: int = 180,
    log_stale_seconds: int = 600,
    tail_lines: int = 40,
) -> dict[str, Any]:
    """Hang/failure forensics for one job (verdict + log tail + hints)."""
    from sigmarail_studio_mcp.backtest_runner.runner import investigate_job

    return try_call(
        investigate_job,
        job_id=job_id,
        heartbeat_stale_seconds=heartbeat_stale_seconds,
        log_stale_seconds=log_stale_seconds,
        tail_lines=tail_lines,
    )


def list_pending(limit: int = 50) -> dict[str, Any]:
    client = get_client()
    try:
        limit = max(1, min(int(limit), 500))
        rows = _rows(
            client,
            "SELECT * FROM backtest_jobs FINAL WHERE status = 'pending' ORDER BY submitted_at ASC LIMIT %(limit)s",
            {"limit": limit},
        )
        return {"jobs": rows}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()


_COMPARABLE = (
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "total_orders",
    "total_fees",
)


def compare(run_id_a: str, run_id_b: str) -> dict[str, Any]:
    """Diff the key metrics of two runs (A vs B, delta = B - A)."""
    ra = report(run_id_a)
    if "error" in ra:
        return {"error": f"run_a: {ra['error']}", "code": ra.get("code")}
    rb = report(run_id_b)
    if "error" in rb:
        return {"error": f"run_b: {rb['error']}", "code": rb.get("code")}

    ma, mb = ra.get("metrics", {}), rb.get("metrics", {})
    diff = {}
    for key in _COMPARABLE:
        a, b = ma.get(key), mb.get(key)
        delta = round(b - a, 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        diff[key] = {"a": a, "b": b, "delta": delta}

    return {
        "run_a": {"run_id": ra["run_id"], "ir_id": ra.get("ir_id"), "period": ra.get("period")},
        "run_b": {"run_id": rb["run_id"], "ir_id": rb.get("ir_id"), "period": rb.get("period")},
        "diff": diff,
        "regime_diff": None,  # populated when regime attribution is available
        "loss_attribution": None,  # populated when loss-cause attribution is available
    }


def run_attribution(run_id: str) -> dict[str, Any]:
    """Per-trade loss-cause attribution for one run (fees / stops / drawdown exits)."""
    client = get_client()
    try:
        from sigmarail.features.backtest_report import get_backtest_report

        rep = get_backtest_report(client, run_id)
        if isinstance(rep, dict) and "error" in rep:
            return rep
        return {
            "run_id": run_id,
            "metrics": (rep.get("metrics") if isinstance(rep, dict) else None),
            "highlights": (rep.get("highlights") if isinstance(rep, dict) else []),
            "warnings": (rep.get("warnings") if isinstance(rep, dict) else []),
            "primary_loss_cause": None,  # loss-cause classifier: future slice
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()
