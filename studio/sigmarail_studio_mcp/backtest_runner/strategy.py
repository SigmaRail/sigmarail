"""MCP strategy composition helpers: build, compile, and inspect pipelines.

Thin wrappers over ``vera_query_core.strategy`` so the ``vera-backtest`` MCP
server can author staged pipelines and compile them to VeraLabV1 specs
without the agent hand-writing framework JSON.
"""

from __future__ import annotations

import json
from typing import Any


def _strategy_module():
    try:
        from vera_query_core.strategy import (  # noqa: PLC0415
            PipelineDocument,
            compile_pipeline,
            decompile_pipeline,
            list_factors,
        )
        from vera_query_core.strategy.presets import get_preset, list_presets  # noqa: PLC0415

        return {
            "PipelineDocument": PipelineDocument,
            "compile": compile_pipeline,
            "decompile": decompile_pipeline,
            "list_factors": list_factors,
            "get_preset": get_preset,
            "list_presets": list_presets,
        }
    except ImportError as exc:
        raise RuntimeError(
            "vera_query_core.strategy not importable; ensure VeraBase is on PYTHONPATH"
        ) from exc


def list_factors() -> dict[str, Any]:
    """List available semantic factors and their L7 column mappings."""
    mod = _strategy_module()
    return {"factors": mod["list_factors"]()}


def list_presets() -> dict[str, Any]:
    """List named strategy presets."""
    mod = _strategy_module()
    return {"presets": mod["list_presets"]()}


def compile_pipeline(pipeline_json: str) -> dict[str, Any]:
    """Compile a staged PipelineDocument JSON into a VeraLabV1 spec dict.

    ``pipeline_json`` must be a valid JSON PipelineDocument (strategy_name +
    stages[]).
    """
    mod = _strategy_module()
    try:
        data = json.loads(pipeline_json)
    except json.JSONDecodeError as exc:
        return {"error": f"pipeline_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = mod["PipelineDocument"].model_validate(data)
        return {"spec": mod["compile"](doc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}


def compile_preset(preset_id: str) -> dict[str, Any]:
    """Compile a named preset into a VeraLabV1 spec dict."""
    mod = _strategy_module()
    try:
        doc = mod["get_preset"](preset_id)
        return {"spec": mod["compile"](doc)}
    except ValueError as exc:
        return {"error": str(exc), "code": "unknown_preset"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "compile_failed"}


def decompile_spec(spec_json: str) -> dict[str, Any]:
    """Decompile a VeraLabV1 spec JSON back into a PipelineDocument."""
    mod = _strategy_module()
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return {"error": f"spec_json is not valid JSON: {exc}", "code": "invalid_argument"}
    try:
        doc = mod["decompile"](data)
        return {"pipeline": doc.model_dump()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "decompile_failed"}


def list_templates(kind: str | None = None, status: str | None = "active") -> dict[str, Any]:
    from vera_query_core.template_catalog import list_templates as _list, summary_row

    kind_arg = kind or None
    status_arg = status or None
    if kind_arg not in (None, "screener", "strategy"):
        return {"error": "kind must be screener or strategy", "code": "invalid_argument"}
    if status_arg not in (None, "active", "deprecated", "draft"):
        return {"error": "status must be active, deprecated, or draft", "code": "invalid_argument"}
    rows = [summary_row(r) for r in _list(kind=kind_arg, status=status_arg)]
    return {"templates": rows}


def get_template(template_id: str) -> dict[str, Any]:
    from vera_query_core.template_catalog import get_template as _get

    try:
        return _get(template_id)
    except ValueError as exc:
        return {"error": str(exc), "code": "unknown_template"}


def create_spec_from_strategy_template(
    template_id: str,
    ir_id: str | None = None,
    title: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Compile a strategy template and save it as a VeraLab spec."""
    from sigmarail_studio_mcp.backtest_runner.runner import save_spec

    compiled = compile_preset(template_id)
    if compiled.get("error"):
        return compiled
    spec = compiled["spec"]
    saved_id = (ir_id or f"tpl-{template_id}").strip()
    saved_title = (title or f"From template {template_id}").strip()
    try:
        saved = save_spec(
            ir_id=saved_id,
            title=saved_title,
            spec_json=json.dumps(spec),
            notes=notes or f"create_spec_from_strategy_template:{template_id}",
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "save_failed"}
    return {"ir_id": saved_id, "title": saved_title, "saved": saved, "spec": spec}


def submit_backtest_from_template(
    template_id: str,
    start_date: str,
    end_date: str,
    ir_id: str | None = None,
    immediate: bool = False,
    extra_env: dict[str, str] | None = None,
    lean_project: str | None = None,
) -> dict[str, Any]:
    """Compile + save a strategy template, then enqueue (or run) a backtest."""
    from sigmarail_studio_mcp.backtest_runner.runner import run_job, submit_job

    created = create_spec_from_strategy_template(template_id, ir_id=ir_id)
    if created.get("error"):
        return created
    saved_id = str(created["ir_id"])
    try:
        job_id = submit_job(
            saved_id,
            start_date,
            end_date,
            extra_env=extra_env,
            lean_project=lean_project,
        )
        if immediate:
            return {
                "ir_id": saved_id,
                **run_job(
                    job_id,
                    saved_id,
                    start_date,
                    end_date,
                    extra_env=extra_env,
                    lean_project=lean_project,
                ),
            }
        return {"ir_id": saved_id, "job_id": job_id, "status": "pending"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "submit_failed"}
