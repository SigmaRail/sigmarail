"""Backtest run listing and report digests (strategy_runs via vera_query_core)."""

from __future__ import annotations

import json
from typing import Any

from screens.spec_save import hash_algorithm_json, run_revision_stale


def _parse_framework_slots(algo_json: str | None) -> dict[str, Any]:
    if not algo_json:
        return {
            "alpha_type": None,
            "universe_type": None,
            "risk_type": None,
            "portfolio_type": None,
            "execution_type": None,
            "symbols": [],
        }
    try:
        data = json.loads(algo_json)
        framework = data.get("Framework") or data.get("framework") or {}
        alpha_info = framework.get("Alpha") or framework.get("alpha") or {}
        universe_info = framework.get("UniverseSelection") or framework.get("universe") or {}
        risk_info = framework.get("RiskManagement") or framework.get("risk") or {}
        port_info = framework.get("PortfolioConstruction") or framework.get("portfolio_construction") or {}
        exec_info = framework.get("Execution") or framework.get("execution") or {}

        alpha_type = alpha_info.get("Type") or alpha_info.get("type_id")
        universe_type = universe_info.get("Type") or universe_info.get("type_id")
        risk_type = risk_info.get("Type") or risk_info.get("type_id")
        portfolio_type = port_info.get("Type") or port_info.get("type_id")
        execution_type = exec_info.get("Type") or exec_info.get("type_id")

        symbols: list[str] = []
        if isinstance(universe_info.get("Parameters"), dict):
            symbols = universe_info["Parameters"].get("symbols") or []
        elif isinstance(universe_info.get("spec"), dict):
            symbols = universe_info["spec"].get("symbols") or []

        return {
            "alpha_type": alpha_type,
            "universe_type": universe_type,
            "risk_type": risk_type,
            "portfolio_type": portfolio_type,
            "execution_type": execution_type,
            "symbols": symbols if isinstance(symbols, list) else [],
        }
    except Exception:
        return {
            "alpha_type": None,
            "universe_type": None,
            "risk_type": None,
            "portfolio_type": None,
            "execution_type": None,
            "symbols": [],
        }


def list_backtest_runs(
    client: Any,
    strategy_id: str | None = None,
    ir_id: str | None = None,
    ir_content_hash: str | None = None,
    limit: int = 50,
    status: str | None = None,
    run_type: str | None = None,
    min_sharpe: float | None = None,
    min_return: float | None = None,
    max_dd: float | None = None,
    search: str | None = None,
    include_jobs: bool = True,
) -> dict[str, Any]:
    """List enriched backtest runs from ``strategy_runs`` and ``backtest_jobs``."""
    limit = max(1, min(int(limit), 500))
    status_filter = (status or "").strip().lower() if status else None
    run_type_filter = (run_type or "").strip().lower() if run_type else None
    search_term = (search or "").strip().lower() if search else None
    ir_id_filter = (ir_id or "").strip() if ir_id else None
    ir_hash_filter = (ir_content_hash or "").strip() if ir_content_hash else None

    # 1. Query completed runs from strategy_runs joined with specs
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if strategy_id:
        where_clauses.append("strategy_id = %(sid)s")
        params["sid"] = strategy_id

    if ir_id_filter:
        where_clauses.append("ir_id = %(ir_id)s")
        params["ir_id"] = ir_id_filter

    if ir_hash_filter:
        where_clauses.append("ir_content_hash = %(ir_content_hash)s")
        params["ir_content_hash"] = ir_hash_filter

    if run_type_filter and run_type_filter != "all":
        where_clauses.append("run_type = %(rtype)s")
        params["rtype"] = run_type_filter

    if min_sharpe is not None:
        where_clauses.append("sharpe_ratio >= %(min_sharpe)s")
        params["min_sharpe"] = float(min_sharpe)

    if min_return is not None:
        where_clauses.append("total_return >= %(min_return)s")
        params["min_return"] = float(min_return)

    if max_dd is not None:
        where_clauses.append("max_drawdown <= %(max_dd)s")
        params["max_dd"] = float(max_dd)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    sql = f"""
        SELECT
            r.run_id,
            r.strategy_id,
            r.run_timestamp,
            r.period_start,
            r.period_end,
            r.ir_id,
            r.ir_schema_version,
            trimRight(CAST(r.ir_content_hash AS Nullable(String)), '\\0') AS ir_content_hash,
            r.run_type,
            r.trigger,
            r.total_return,
            r.annual_return,
            r.sharpe_ratio,
            r.sortino_ratio,
            r.max_drawdown,
            r.win_rate,
            r.profit_factor,
            r.total_orders,
            r.total_fees,
            r.start_equity,
            r.end_equity,
            r.alpha,
            r.beta,
            r.volatility,
            trimRight(CAST(r.git_commit AS Nullable(String)), '\\0') AS git_commit,
            r.git_branch,
            s.title AS spec_title,
            s.algorithm_json
        FROM (
            SELECT * FROM strategy_runs FINAL
            {where_sql}
            ORDER BY run_timestamp DESC
            LIMIT %(limit)s
        ) r
        LEFT JOIN strategy_algorithm_specs s FINAL ON r.ir_id = s.ir_id
        ORDER BY r.run_timestamp DESC
    """
    params["limit"] = limit

    completed_runs: list[dict[str, Any]] = []
    completed_total = 0
    if status_filter not in ("pending", "running", "failed"):
        try:
            ct = client.query(
                f"SELECT count() AS n FROM strategy_runs FINAL {where_sql}",
                parameters={k: v for k, v in params.items() if k != "limit"},
            )
            if ct.result_rows:
                completed_total = int(ct.result_rows[0][0] or 0)
        except Exception:
            pass
        rows = client.query(sql, parameters=params)
        for row in rows.result_rows:
            d = dict(zip(rows.column_names, row))
            algo_json = d.pop("algorithm_json", None)
            # `strategy_algorithm_specs` stores no hash column — derive the spec's
            # current hash from the algorithm_json already selected above, via the
            # one shared helper (screens/spec_save.py).
            spec_hash = hash_algorithm_json(algo_json)
            d["spec_ir_content_hash"] = spec_hash or None
            # C: a run whose recorded spec hash differs from the spec's current
            # hash was produced from an earlier revision.
            d["revision_stale"] = run_revision_stale(d.get("ir_content_hash"), spec_hash)
            slots = _parse_framework_slots(algo_json)
            d.update(slots)
            d["status"] = "done"
            d["error_message"] = None
            d["progress_pct"] = 1.0
            if d.get("run_timestamp"):
                d["run_timestamp"] = str(d["run_timestamp"])
            if d.get("period_start"):
                d["period_start"] = str(d["period_start"])
            if d.get("period_end"):
                d["period_end"] = str(d["period_end"])
            completed_runs.append(d)

        # Deduplicate completed_runs by run_id (keep most recent)
        seen_rids: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for d in completed_runs:
            rid = str(d.get("run_id") or "")
            if rid:
                if rid in seen_rids:
                    continue
                seen_rids.add(rid)
            deduped.append(d)
        completed_runs = deduped

    # 2. Query pending / running / failed jobs from backtest_jobs if requested
    active_jobs: list[dict[str, Any]] = []
    active_total = 0
    if include_jobs and status_filter != "done":
        try:
            job_status_filter = ""
            job_where_clauses = []
            job_params: dict[str, Any] = {}
            if status_filter in ("pending", "running", "failed"):
                job_status_filter = f"WHERE status = '{status_filter}'"
                job_where_clauses.append("status = %(j_status)s")
                job_params["j_status"] = status_filter
            else:
                job_status_filter = "WHERE status != 'done'"
                job_where_clauses.append("status != 'done'")

            if ir_id_filter:
                job_where_clauses.append("ir_id = %(j_ir_id)s")
                job_params["j_ir_id"] = ir_id_filter

            job_where_sql = f"WHERE {' AND '.join(job_where_clauses)}"

            try:
                jt = client.query(f"SELECT count() AS n FROM backtest_jobs FINAL {job_where_sql}", parameters=job_params)
                if jt.result_rows:
                    active_total = int(jt.result_rows[0][0] or 0)
            except Exception:
                pass

            jobs_sql = f"""
                SELECT
                    j.job_id AS run_id,
                    j.ir_id,
                    toString(j.status) AS status,
                    j.error_message,
                    j.progress_pct,
                    j.submitted_at AS run_timestamp,
                    j.start_date AS period_start,
                    j.end_date AS period_end,
                    s.title AS spec_title,
                    s.algorithm_json
                FROM (
                    SELECT * FROM backtest_jobs FINAL {job_where_sql}
                ) AS j
                LEFT JOIN strategy_algorithm_specs s FINAL ON j.ir_id = s.ir_id
                ORDER BY j.created_at DESC
                LIMIT 50
            """
            job_rows = client.query(jobs_sql, parameters=job_params)
            # Avoid duplicate if job already in completed_runs
            completed_ids = {r["run_id"] for r in completed_runs}
            for row in job_rows.result_rows:
                d = dict(zip(job_rows.column_names, row))
                if d["run_id"] in completed_ids:
                    continue
                algo_json = d.pop("algorithm_json", None)
                slots = _parse_framework_slots(algo_json)
                d.update(slots)
                d["strategy_id"] = "VeraTradingLab"
                d["run_type"] = "base"
                d["trigger"] = "job"
                d["total_return"] = None
                d["annual_return"] = None
                d["sharpe_ratio"] = None
                d["sortino_ratio"] = None
                d["max_drawdown"] = None
                d["win_rate"] = None
                d["profit_factor"] = None
                d["total_orders"] = 0
                d["total_fees"] = 0.0
                d["git_commit"] = ""
                d["git_branch"] = ""
                if d.get("run_timestamp"):
                    d["run_timestamp"] = str(d["run_timestamp"])
                if d.get("period_start"):
                    d["period_start"] = str(d["period_start"])
                if d.get("period_end"):
                    d["period_end"] = str(d["period_end"])
                active_jobs.append(d)
        except Exception:
            pass

    # Combine and order by recency (most recent activity first), so a
    # just-completed run is not buried beneath a backlog of older
    # failed/running job rows.
    all_runs = active_jobs + completed_runs

    # Apply search filter across fields if provided
    if search_term:
        filtered: list[dict[str, Any]] = []
        for r in all_runs:
            match = (
                search_term in (r.get("run_id") or "").lower()
                or search_term in (r.get("ir_id") or "").lower()
                or search_term in (r.get("spec_title") or "").lower()
                or search_term in (r.get("alpha_type") or "").lower()
                or search_term in (r.get("universe_type") or "").lower()
                or search_term in (r.get("risk_type") or "").lower()
                or search_term in (r.get("status") or "").lower()
                or any(search_term in s.lower() for s in (r.get("symbols") or []))
            )
            if match:
                filtered.append(r)
        all_runs = filtered

    # Unified recency ordering: both lists carry a string ``run_timestamp``
    # (completed runs use run_timestamp; jobs use submitted_at AS run_timestamp).
    all_runs.sort(key=lambda r: r.get("run_timestamp") or "", reverse=True)
    # Unified recency ordering: active (running/pending) jobs surface at the top,
    # followed by runs ordered by run_timestamp descending.
    all_runs.sort(
        key=lambda r: (
            1 if str(r.get("status") or "").lower() in ("running", "pending") else 0,
            str(r.get("run_timestamp") or ""),
        ),
        reverse=True,
    )

    return {
        "runs": all_runs[:limit],
        "total": completed_total + active_total,
    }


def get_run_report(client: Any, run_id: str) -> dict[str, Any]:
    """Agent-friendly backtest digest for one run."""
    return get_backtest_report(client, run_id)


def get_backtest_report(client: Any, run_id: str) -> dict[str, Any]:
    """Compatibility report adapter; requires the optional Vera runtime."""
    from vera_query_core.backtest_report import get_backtest_report

    return get_backtest_report(client, run_id)


def list_runs_by_ir_id(ir_id: str, *, limit: int = 50) -> dict[str, Any]:
    """List compatibility backtest runs; requires the optional Vera runtime."""
    from vera_query_core.backtest_report import list_runs_by_ir_id as _list_runs

    return _list_runs(ir_id, limit=limit)


def get_run_context(client: Any, run_id: str, *, trades_limit: int = 50) -> dict[str, Any]:
    """Context-pack for one run: report + closed trades + equity summary + spec + warnings.

    Lazy imports avoid a ``screens.backtest <-> screens.backtest_jobs`` cycle.
    """
    from screens.run_artifacts import get_run_closed_trades, get_run_equity_curve

    report = get_run_report(client, run_id)
    if isinstance(report, dict) and report.get("code") in ("not_found", "invalid_argument"):
        return report

    closed_trades = get_run_closed_trades(client, run_id, limit=trades_limit)
    equity = get_run_equity_curve(client, run_id)

    spec = None
    ir_id = report.get("ir_id")
    if ir_id:
        from screens.backtest_jobs import get_spec_by_ir_id

        spec = get_spec_by_ir_id(client, ir_id)

    return {
        "run_id": run_id,
        "report": report,
        "closed_trades": closed_trades,
        "equity_summary": equity,
        "spec": spec,
        "warnings": report.get("warnings", []),
    }


__all__ = [
    "get_run_context",
    "get_run_report",
    "list_backtest_runs",
    "list_runs_by_ir_id",
]
