"""Backtest spec listing and job status helpers (ClickHouse)."""

from __future__ import annotations

import json
from typing import Any

from screens.backtest import _parse_framework_slots


def _flatten_screen_top_level(pipeline_document: dict[str, Any]) -> dict[str, Any]:
    """Serve a stored document with its screen's top level as a clause list.

    Older builds wrapped the clauses in a nameless/labelled ``and`` group — a leftover of the
    retired ``hygiene`` split. The top level *is* that list, so the wrapper is unwrapped on the
    way out and the next save persists the flat form. ``membership`` is the one reserved name.
    """
    universe = (pipeline_document or {}).get("universe") or {}
    screen = universe.get("screen")
    if isinstance(screen, list) and len(screen) == 1:
        only = screen[0]
        if (
            isinstance(only, dict)
            and only.get("logic") == "and"
            and only.get("name") != "membership"
            and isinstance(only.get("conditions"), list)
        ):
            return {**pipeline_document, "universe": {**universe, "screen": only["conditions"]}}
    return pipeline_document


def _row_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return dict(zip(columns, row))


def _extract_screener_summary(algo_json: str | None) -> dict[str, Any]:
    """Extract embedded screener parameters from spec JSON if present."""
    if not algo_json:
        return {"has_screener": False, "source": None, "rules_count": 0, "order_by": None}
    try:
        data = json.loads(algo_json)
        vb = data.get("VeraBase") or data.get("vera_base") or {}
        uni = vb.get("Universe") or vb.get("universe") or {}
        if uni and isinstance(uni, dict):
            where_clause = uni.get("where") or {}
            items = where_clause.get("items") if isinstance(where_clause, dict) else []
            order_by = uni.get("order_by") or []
            return {
                "has_screener": True,
                "source": uni.get("from") or "daily_screener",
                "rules_count": len(items) if isinstance(items, list) else 0,
                "order_by": order_by[0].get("field") if order_by and isinstance(order_by, list) and isinstance(order_by[0], dict) else None,
                "limit_per_day": uni.get("limit_per_day"),
            }
    except Exception:
        pass
    return {"has_screener": False, "source": None, "rules_count": 0, "order_by": None}


def _load_builtin_templates(*, include_json: bool = True) -> list[dict[str, Any]]:
    """Legacy built-in framework JSON templates were removed; Studio seeds via catalog minervini_sepa."""
    return []


def list_specs(
    client: Any,
    *,
    limit: int = 50,
    search: str = "",
    alpha_type: str = "",
    universe_type: str = "",
    schema_status: str = "",
    is_template: bool | None = None,
) -> dict[str, Any]:
    """List algorithm specs and templates with enriched framework traits.

    Merges built-in system templates with ClickHouse strategy_algorithm_specs.
    """
    limit = max(1, min(int(limit), 200))
    search = (search or "").strip().lower()
    alpha_type = (alpha_type or "").strip()
    universe_type = (universe_type or "").strip()
    schema_status = (schema_status or "").strip().lower()

    # 1. Built-in system templates (metadata only — no full JSON in list responses)
    builtin_tmpls = _load_builtin_templates(include_json=False)

    # 2. Database specs from ClickHouse (default: exclude ephemeral sweep variants)
    db_specs: list[dict[str, Any]] = []
    try:
        try:
            rows = client.query(
                "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json, length(pipeline_json) AS pipe_len, compiler_version,"
                "       parent_ir_id, parent_content_hash, mutation_type, changelog_notes, author_agent"
                " FROM strategy_algorithm_specs FINAL"
                " WHERE is_ephemeral = 0"
                " ORDER BY created_at DESC"
                f" LIMIT {limit * 2}",
            )
        except Exception:
            try:
                rows = client.query(
                    "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json, length(pipeline_json) AS pipe_len, compiler_version"
                    " FROM strategy_algorithm_specs FINAL"
                    " ORDER BY created_at DESC"
                    f" LIMIT {limit * 2}",
                )
            except Exception:
                rows = client.query(
                    "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json"
                    " FROM strategy_algorithm_specs FINAL"
                    " ORDER BY created_at DESC"
                    f" LIMIT {limit * 2}",
                )
        import hashlib
        for r in rows.result_rows:
            rec = _row_dict(rows.column_names, r)
            algo_json = rec.pop("algorithm_json", None)
            slots = _parse_framework_slots(algo_json)
            screener = _extract_screener_summary(algo_json)

            d_val = rec.get("created_at")
            d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val or "")

            is_tmpl = (
                "template" in (rec.get("notes") or "").lower()
                or "template" in (rec.get("title") or "").lower()
                or (rec.get("ir_id") or "").startswith("tmpl-")
                or (rec.get("ir_id") or "").startswith("template-")
            )

            pipe_len = rec.get("pipe_len") or 0
            has_pipeline = bool(pipe_len and int(pipe_len) > 10)
            ir_hash = None
            if algo_json:
                ir_hash = hashlib.sha256(str(algo_json).encode("utf-8")).hexdigest()

            status_val = "modern" if has_pipeline else "legacy"

            db_specs.append({
                "ir_id": rec.get("ir_id") or "",
                "title": rec.get("title") or rec.get("ir_id") or "",
                "spec_schema_version": int(rec.get("spec_schema_version") or (2 if has_pipeline else 1)),
                "notes": rec.get("notes") or "",
                "category": "Custom Spec" if not is_tmpl else "Custom Template",
                "is_system": False,
                "is_template": is_tmpl,
                "created_at": d_str,
                "has_pipeline": has_pipeline,
                "ir_content_hash": ir_hash,
                "compiler_version": rec.get("compiler_version") or "",
                "schema_status": status_val,
                "lineage": {
                    "parent_ir_id": rec.get("parent_ir_id") or None,
                    "parent_content_hash": rec.get("parent_content_hash") or None,
                    "mutation_type": rec.get("mutation_type") or "init",
                    "changelog_notes": rec.get("changelog_notes") or "",
                    "author_agent": rec.get("author_agent") or "user",
                },
                **slots,
                "screener_summary": screener,
            })
    except Exception:
        pass

    # 3. True total (unfiltered) for the "N / total" badge.
    db_total = 0
    try:
        total_rows = client.query("SELECT count() AS n FROM strategy_algorithm_specs FINAL")
        if total_rows.result_rows:
            db_total = int(total_rows.result_rows[0][0] or 0)
    except Exception:
        pass

    # Merge: System templates first, then DB specs (avoiding duplicate ir_id)
    seen_ids = set()
    combined: list[dict[str, Any]] = []
    for s in builtin_tmpls + db_specs:
        if s["ir_id"] in seen_ids:
            continue
        seen_ids.add(s["ir_id"])

        # Filter by is_template if specified
        if is_template is True and not s.get("is_template"):
            continue
        if is_template is False and s.get("is_template"):
            continue

        # Filter by schema_status if specified ("modern" vs "legacy")
        if schema_status and s.get("schema_status") != schema_status:
            continue

        # Filter by alpha_type
        if alpha_type and s.get("alpha_type") != alpha_type:
            continue

        # Filter by universe_type
        if universe_type and s.get("universe_type") != universe_type:
            continue

        # Filter by fulltext search
        if search:
            matchable = " ".join([
                s.get("ir_id", ""),
                s.get("title", ""),
                s.get("notes", ""),
                s.get("category", ""),
                s.get("alpha_type") or "",
                s.get("universe_type") or "",
                " ".join(s.get("symbols") or []),
            ]).lower()
            if search not in matchable:
                continue

        combined.append(s)

    return {
        "specs": combined[:limit],
        "count": len(combined[:limit]),
        "total": db_total + len(builtin_tmpls),
    }


def get_spec_by_ir_id(client: Any, ir_id: str) -> dict[str, Any] | None:
    """Retrieve full spec record and parsed JSON by ir_id."""
    ir_id = (ir_id or "").strip()
    if not ir_id:
        return None

    # Check built-in templates first
    for tmpl in _load_builtin_templates():
        if tmpl["ir_id"] == ir_id or tmpl["ir_id"] == ir_id.lower():
            try:
                parsed = json.loads(tmpl["algorithm_json"])
            except Exception:
                parsed = {}
            return {
                **tmpl,
                "spec": parsed,
            }

    # Query ClickHouse strategy_algorithm_specs
    try:
        try:
            rows = client.query(
                "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json,"
                "       pipeline_json, portfolio_json, compiler_version,"
                "       parent_ir_id, parent_content_hash, mutation_type, changelog_notes, author_agent"
                " FROM strategy_algorithm_specs FINAL"
                " WHERE ir_id = %(id)s"
                " LIMIT 1",
                parameters={"id": ir_id},
            )
            lineage_cols = True
        except Exception:
            lineage_cols = False
            rows = None
        if (rows is None or not rows.result_rows) and lineage_cols:
            # Older installs may lack lineage columns — retry without them.
            rows = client.query(
                "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json,"
                "       pipeline_json, portfolio_json, compiler_version"
                " FROM strategy_algorithm_specs FINAL"
                " WHERE ir_id = %(id)s"
                " LIMIT 1",
                parameters={"id": ir_id},
            )
        if not rows.result_rows:
            # Older installs may lack pipeline_json — fall back.
            rows = client.query(
                "SELECT ir_id, title, spec_schema_version, notes, created_at, algorithm_json"
                " FROM strategy_algorithm_specs FINAL"
                " WHERE ir_id = %(id)s"
                " LIMIT 1",
                parameters={"id": ir_id},
            )
        if not rows.result_rows:
            return None
        rec = _row_dict(rows.column_names, rows.result_rows[0])
        algo_json = rec.get("algorithm_json")
        slots = _parse_framework_slots(algo_json)
        screener = _extract_screener_summary(algo_json)

        d_val = rec.get("created_at")
        d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val or "")

        parsed_spec = {}
        if algo_json:
            try:
                parsed_spec = json.loads(algo_json)
            except Exception:
                parsed_spec = {}

        pipeline_document = None
        raw_pipe = rec.get("pipeline_json") or ""
        if isinstance(raw_pipe, str) and raw_pipe.strip():
            try:
                pipeline_document = _flatten_screen_top_level(json.loads(raw_pipe))
            except Exception:
                pipeline_document = None

        is_tmpl = (
            "template" in (rec.get("notes") or "").lower()
            or "template" in (rec.get("title") or "").lower()
            or (rec.get("ir_id") or "").startswith("tmpl-")
        )

        ir_hash = None
        if algo_json:
            import hashlib

            ir_hash = hashlib.sha256(str(algo_json).encode("utf-8")).hexdigest()

        return {
            "ir_id": rec.get("ir_id") or "",
            "title": rec.get("title") or rec.get("ir_id") or "",
            "spec_schema_version": int(rec.get("spec_schema_version") or 1),
            "notes": rec.get("notes") or "",
            "category": "Custom Template" if is_tmpl else "Custom Spec",
            "is_system": False,
            "is_template": is_tmpl,
            "created_at": d_str,
            "algorithm_json": algo_json,
            "spec": parsed_spec,
            "pipeline_document": pipeline_document,
            "pipeline_json": raw_pipe if isinstance(raw_pipe, str) else "",
            "ir_content_hash": ir_hash,
            "lineage": {
                "parent_ir_id": rec.get("parent_ir_id") or None,
                "parent_content_hash": rec.get("parent_content_hash") or None,
                "mutation_type": rec.get("mutation_type") or "init",
                "changelog_notes": rec.get("changelog_notes") or "",
                "author_agent": rec.get("author_agent") or "user",
            },
            **slots,
            "screener_summary": screener,
        }
    except Exception:
        return None


def get_job_status(client: Any, job_id: str) -> dict[str, Any] | None:
    """Fetch one backtest job row from ``backtest_jobs FINAL`` including telemetry."""
    job_id = (job_id or "").strip()
    if not job_id:
        return None
    rows = client.query(
        "SELECT job_id, ir_id, start_date, end_date, status, runner_id,"
        "       submitted_at, started_at, completed_at, lean_output_path,"
        "       lean_project, extra_env, error_message, progress_pct,"
        "       current_sim_date, elapsed_seconds, estimated_remaining_seconds,"
        "       last_heartbeat, last_log_line, created_at"
        " FROM backtest_jobs FINAL"
        " WHERE job_id = %(jid)s"
        " LIMIT 1",
        parameters={"jid": job_id},
    )
    if not rows.result_rows:
        return None
    return _row_dict(rows.column_names, rows.result_rows[0])


def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel backtest job via runner module or ClickHouse state."""
    job_id = (job_id or "").strip()
    if not job_id:
        return {"error": "job_id is required", "cancelled": False}
    try:
        from sigmarail_studio_mcp.backtest_runner.runner import cancel_job as _cancel
        return _cancel(job_id)
    except Exception as exc:
        return {"job_id": job_id, "status": "cancelled", "note": f"Fallback: {exc}"}


__all__ = [
    "cancel_job",
    "get_job_status",
    "get_spec_by_ir_id",
    "list_specs",
]
