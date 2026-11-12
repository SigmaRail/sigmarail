"""strategy domain: semantic factors, pipeline schema, validate/fork, catalog templates."""
from __future__ import annotations

import json
from typing import Any


def list_factors() -> dict[str, Any]:
    """Semantic factor registry (name -> L7 column/table/direction)."""
    from vera_query_core.strategy import list_factors as _list_factors

    return {"factors": _list_factors()}


def list_presets() -> dict[str, Any]:
    """Named strategy presets."""
    from vera_query_core.strategy.presets import list_presets as _list_presets

    return {"presets": _list_presets()}


def list_templates(kind: str | None = None, status: str | None = "active") -> dict[str, Any]:
    """List screener and strategy templates (C-TEMPLATE-CATALOG-V1). Default status=active."""
    from vera_query_core.template_catalog import list_templates as _list, summary_row

    if kind not in (None, "", "screener", "strategy"):
        return {"error": "kind must be screener or strategy", "code": "invalid_argument"}
    if status not in (None, "", "active", "deprecated", "draft"):
        return {"error": "status must be active, deprecated, or draft", "code": "invalid_argument"}
    kind_arg = kind or None
    status_arg = status or None
    rows = [summary_row(r) for r in _list(kind=kind_arg, status=status_arg)]
    return {"templates": rows}


def get_template(template_id: str) -> dict[str, Any]:
    """Load one catalog template (screener IR or strategy PipelineDocument)."""
    from vera_query_core.template_catalog import get_template as _get

    try:
        return _get(template_id)
    except ValueError as exc:
        return {"error": str(exc), "code": "invalid_argument"}


def list_columns() -> dict[str, Any]:
    """Screener column surface for authoring (from the L7 join manifest + DDL)."""
    from sigmarail_studio_mcp.domains.catalog import list_columns as _catalog_columns

    return _catalog_columns()


def pipeline_schema() -> dict[str, Any]:
    """JSON schema for a staged PipelineDocument.

    Authoring boundary (canonical: VeraProjects/docs/EXPRESSION_SURFACE.md
    §11): predicates/scorings belong in AST sites (`when`, `*_expr`, rule
    operands); effects belong in the bounded `then` action vocabulary with
    operand args; engine mechanics (fill_session, surrogates, uses[],
    phases[]) are structured config — never author a procedural knob where
    an AST site exists. Runtime-only nodes (signal/regime/signal_compare)
    are legible ONLY in graph-policy `if` conditions — spec_lint E113
    rejects them at save at any other site (they would silently dead-eval).
    """
    from vera_query_core.strategy import PipelineDocument

    return PipelineDocument.model_json_schema()


def validate_pipeline(pipeline_json: str) -> dict[str, Any]:
    """Validate a staged PipelineDocument JSON without compiling it."""
    from vera_query_core.strategy import PipelineDocument

    try:
        data = json.loads(pipeline_json)
    except json.JSONDecodeError as exc:
        return {"valid": False, "code": "invalid_argument", "error": f"pipeline_json is not valid JSON: {exc}"}
    try:
        PipelineDocument.model_validate(data)
        return {"valid": True}
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "code": "validation_failed", "error": str(exc)}


def compile_preset(preset_id: str) -> dict[str, Any]:
    """Compile a named strategy preset into a VeraLabV1 spec dict."""
    from vera_query_core.strategy import compile_pipeline as _compile
    from vera_query_core.strategy.presets import get_preset

    try:
        doc = get_preset(preset_id)
        return {"spec": _compile(doc)}
    except ValueError as exc:
        return {"error": str(exc), "code": "unknown_preset"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}


def compile_pipeline(pipeline_json: str) -> dict[str, Any]:
    """Compile a staged PipelineDocument JSON into a VeraLabV1 spec dict."""
    from vera_query_core.strategy import PipelineDocument, compile_pipeline as _compile

    try:
        data = json.loads(pipeline_json)
    except json.JSONDecodeError as exc:
        return {"error": f"pipeline_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = PipelineDocument.model_validate(data)
        return {"spec": _compile(doc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}


def fork(spec_json: str) -> dict[str, Any]:
    """Decompile a VeraLabV1 spec JSON back into a PipelineDocument (for editing)."""
    from vera_query_core.strategy import decompile_pipeline

    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return {"error": f"spec_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = decompile_pipeline(data)
        return {"pipeline": doc.model_dump()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "decompile_failed"}


def compile_portfolio(portfolio_json: str) -> dict[str, Any]:
    """Compile a PortfolioDocument JSON (legs + allocation) into a VeraLabV1 spec."""
    from vera_query_core.strategy import PortfolioDocument, compile_portfolio as _compile

    try:
        data = json.loads(portfolio_json)
    except json.JSONDecodeError as exc:
        return {"error": f"portfolio_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = PortfolioDocument.model_validate(data)
        return {"spec": _compile(doc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}


def fork_portfolio(spec_json: str) -> dict[str, Any]:
    """Decompile a VeraLabV1 spec JSON back into a PortfolioDocument (for editing)."""
    from vera_query_core.strategy import decompile_portfolio

    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return {"error": f"spec_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = decompile_portfolio(data)
        return {"portfolio": doc.model_dump()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "decompile_failed"}


def list_setup_recipes() -> dict[str, Any]:
    """Named setup expression packs (SSOT for composed setup trees).

    ``champion_setup_or`` = volume_thrust_breakout OR vcp_compression OR pocket_pivot.
    Compose these instead of hand-typing expression trees — the thresholds live in one place.
    """
    from vera_query_core.strategy.setup_recipes import list_setup_recipes as _list

    return {"setup_recipes": _list()}


def compose_document(
    preset_id: str = "minervini_sepa",
    setup_recipe_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compose an authored PipelineDocument from a preset + setup recipe packs (no JSON to write).

    This is the *semantic* authoring entry: state the intent (preset + recipe ids), not the AST.
    Follow with ``save_pipeline`` (compile + save) and then a backtest submit.
    """
    from vera_query_core.strategy.presets import get_preset
    from vera_query_core.strategy.setup_recipes import apply_setup_recipe, list_setup_recipes

    try:
        doc = get_preset(preset_id)
    except ValueError as exc:
        return {"error": str(exc), "code": "unknown_preset"}
    known = [r["id"] for r in list_setup_recipes()]
    for i, rid in enumerate(setup_recipe_ids or ["champion_setup_or"]):
        if rid not in known:
            return {"error": f"Unknown setup recipe {rid!r}; known: {known}", "code": "unknown_recipe"}
        doc = apply_setup_recipe(doc, rid, replace=(i == 0))
    return {"pipeline": doc.model_dump()}


def save_pipeline(
    ir_id: str,
    title: str,
    pipeline_json: str,
    notes: str = "",
    *,
    changelog_notes: str = "",
    author_agent: str = "agent",
    force_new_version: bool = False,
) -> dict[str, Any]:
    """Validate + compile an authored PipelineDocument and save it (forks if runs exist).

    The missing middle exit: turns a ``PipelineDocument`` (from ``compose_document`` or
    ``strategy_fork``) straight into a stored, runnable spec — no raw VeraLabV1 JSON to build.
    """
    from vera_query_core.strategy import PipelineDocument, compile_pipeline as _compile
    from screens.spec_save import save_spec_guarded

    try:
        data = json.loads(pipeline_json)
    except json.JSONDecodeError as exc:
        return {"error": f"pipeline_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = PipelineDocument.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "validation_failed"}
    try:
        spec = _compile(doc)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}
    result = save_spec_guarded(
        ir_id=ir_id,
        title=title,
        spec_json=json.dumps(spec),
        notes=notes,
        force_fork=force_new_version,
        changelog_notes=changelog_notes,
        author_agent=author_agent,
    )
    return result


def patch_pipeline(
    ir_id: str,
    ops: list[dict[str, Any]],
    *,
    dry_run: bool = True,
    expected_hash: str | None = None,
    retest: bool = False,
    through_binding_id: str | None = None,
    probe_mode: str = "measures",
) -> dict[str, Any]:
    """HTTP → Django POST /api/backtests/specs/:ir_id/pipeline-ops."""
    from sigmarail_studio_mcp.http_client import studio_post

    body: dict[str, Any] = {
        "ops": ops,
        "dry_run": dry_run,
        "retest": retest,
        "probe_mode": probe_mode,
    }
    if expected_hash:
        body["expected_hash"] = expected_hash
    if through_binding_id:
        body["through"] = {"binding_id": through_binding_id}
    try:
        return studio_post(f"/api/backtests/specs/{ir_id}/pipeline-ops", body)
    except ValueError as exc:
        return {"error": str(exc), "code": "studio_http_error"}


# --- AST semantic diff + lint (Component 2: implementation plan) --------------


def strategy_diff(spec_a_json: str, spec_b_json: str) -> dict[str, Any]:
    """Semantic structural diff between two specs (PipelineDocument or VeraLabV1).

    Accepts either authored ``PipelineDocument`` JSON (top-level ``stages`` /
    ``bindings``) or compiled VeraLabV1 (``Framework`` slots); the latter is
    decompiled first so both inputs compare in the same document space.
    """
    from vera_query_core.strategy import PipelineDocument, decompile_pipeline

    def _to_doc(raw: str, label: str) -> dict[str, Any]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}: not valid JSON: {exc}") from exc
        if isinstance(data, dict) and "Framework" in data:
            return decompile_pipeline(data).model_dump()
        return PipelineDocument.model_validate(data).model_dump()

    try:
        doc_a = _to_doc(spec_a_json, "spec_a")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "invalid_argument"}
    try:
        doc_b = _to_doc(spec_b_json, "spec_b")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "invalid_argument"}

    diffs: list[dict[str, Any]] = []
    for slot in ("stages", "bindings", "universe", "sizing", "risk", "execution"):
        if doc_a.get(slot) != doc_b.get(slot):
            diffs.append({"slot": slot, "from": doc_a.get(slot), "to": doc_b.get(slot)})
    return {"has_diff": len(diffs) > 0, "diffs": diffs}


def strategy_lint(pipeline_json: str) -> dict[str, Any]:
    """Validate a PipelineDocument AST and flag runtime-contract conflicts.

    Enforces the runtime XOR contract (``pcm_scale_expr`` vs
    ``honor_insight_confidence``) and warns on insight tags attached to the
    ``SwingProgressiveRiskManagementModel`` risk slot (ignored at runtime).
    """
    from vera_query_core.strategy import PipelineDocument

    try:
        data = json.loads(pipeline_json) if isinstance(pipeline_json, str) else pipeline_json
    except json.JSONDecodeError as exc:
        return {"valid": False, "code": "invalid_argument", "diagnostics": [{"message": f"not valid JSON: {exc}", "severity": "error"}]}
    try:
        doc = PipelineDocument.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "code": "validation_failed", "diagnostics": [{"message": str(exc), "severity": "error"}]}

    diagnostics: list[dict[str, Any]] = []
    dump = doc.model_dump()
    bindings = (dump.get("bindings") or {})
    if isinstance(bindings, dict) and bindings.get("pcm_scale") and bindings.get("alpha_confidence"):
        diagnostics.append({
            "message": "bindings.pcm_scale conflicts with bindings.alpha_confidence (runtime XOR: scale expression takes precedence; confidence is ignored)",
            "severity": "error",
            "slot": "portfolio_construction",
        })
    if isinstance(bindings, dict):
        allow = bindings.get("risk_allow_pyramid_add") or {}
        allow_text = ""
        try:
            import json as _json

            allow_text = _json.dumps(allow)
        except Exception:
            allow_text = str(allow)
        if allow and ("insight" in allow_text.lower() or "confidence" in allow_text.lower()):
            diagnostics.append({
                "message": "bindings.risk_allow_pyramid_add references insight/confidence tags, but SwingProgressiveRiskManagementModel ignores them at runtime",
                "severity": "warning",
                "slot": "risk_management",
            })
    return {"valid": not any(d.get("severity") == "error" for d in diagnostics), "diagnostics": diagnostics}
