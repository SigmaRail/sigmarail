"""screen domain: L7 presets + stage-prefix probe (HTTP → Django)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call
from sigmarail_studio_mcp.http_client import studio_post


def stocks(date: str, preset: str = "leaders", limit: int = 25) -> dict[str, Any]:
    """Run an L7 screener preset (leaders / minervini_tt / vcp_tight / high_rs / …)."""
    from vera_query_core.platform_tools import screen_stocks

    return call(screen_stocks, date=date, preset=preset, limit=limit)


def _probe(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return studio_post("/api/screens/probe", body)
    except ValueError as exc:
        return {"error": str(exc), "code": "studio_http_error"}


def probe_layers(
    *,
    preset_id: str | None = None,
    pipeline: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
    through_binding_id: str | None = None,
    through_stage_index: int | None = None,
    probe_mode: str = "measures",
) -> dict[str, Any]:
    """List prefix layers / computed aliases (no ClickHouse)."""
    body: dict[str, Any] = {"view": "layers", "probe_mode": probe_mode}
    if preset_id:
        body["preset_id"] = preset_id
    elif pipeline is not None:
        body["pipeline"] = pipeline
    elif spec is not None:
        body["spec"] = spec
    else:
        return {"error": "preset_id, pipeline, or spec required", "code": "invalid_argument"}
    through: dict[str, Any] = {}
    if through_binding_id is not None:
        through["binding_id"] = through_binding_id
    if through_stage_index is not None:
        through["stage_index"] = through_stage_index
    if through:
        body["through"] = through
    return _probe(body)


def probe_asof(
    *,
    as_of: str,
    preset_id: str | None = None,
    pipeline: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
    through_binding_id: str | None = None,
    through_stage_index: int | None = None,
    probe_mode: str = "measures",
    limit: int = 25,
) -> dict[str, Any]:
    """Single-day ranked sample of prefix columns."""
    body: dict[str, Any] = {
        "view": "asof",
        "as_of": as_of,
        "probe_mode": probe_mode,
        "limit": limit,
    }
    if preset_id:
        body["preset_id"] = preset_id
    elif pipeline is not None:
        body["pipeline"] = pipeline
    elif spec is not None:
        body["spec"] = spec
    else:
        return {"error": "preset_id, pipeline, or spec required", "code": "invalid_argument"}
    through: dict[str, Any] = {}
    if through_binding_id is not None:
        through["binding_id"] = through_binding_id
    if through_stage_index is not None:
        through["stage_index"] = through_stage_index
    if through:
        body["through"] = through
    return _probe(body)


def probe_range(
    *,
    end_date: str,
    start_date: str | None = None,
    preset_id: str | None = None,
    pipeline: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
    through_binding_id: str | None = None,
    through_stage_index: int | None = None,
    probe_mode: str = "measures",
) -> dict[str, Any]:
    """Per-day member counts + measure averages (aggregates only)."""
    body: dict[str, Any] = {
        "view": "range",
        "end_date": end_date,
        "probe_mode": probe_mode,
    }
    if start_date:
        body["start_date"] = start_date
    if preset_id:
        body["preset_id"] = preset_id
    elif pipeline is not None:
        body["pipeline"] = pipeline
    elif spec is not None:
        body["spec"] = spec
    else:
        return {"error": "preset_id, pipeline, or spec required", "code": "invalid_argument"}
    through: dict[str, Any] = {}
    if through_binding_id is not None:
        through["binding_id"] = through_binding_id
    if through_stage_index is not None:
        through["stage_index"] = through_stage_index
    if through:
        body["through"] = through
    return _probe(body)


def probe_diff(
    *,
    as_of: str,
    preset_id: str | None = None,
    pipeline: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
    through_binding_id: str | None = None,
    through_stage_index: int | None = None,
    through_b_binding_id: str | None = None,
    through_b_stage_index: int | None = None,
    probe_mode: str = "members",
) -> dict[str, Any]:
    """Layer A vs B: size delta, Jaccard, entering/leaving (capped)."""
    body: dict[str, Any] = {
        "view": "diff",
        "as_of": as_of,
        "probe_mode": probe_mode,
    }
    if preset_id:
        body["preset_id"] = preset_id
    elif pipeline is not None:
        body["pipeline"] = pipeline
    elif spec is not None:
        body["spec"] = spec
    else:
        return {"error": "preset_id, pipeline, or spec required", "code": "invalid_argument"}
    through: dict[str, Any] = {}
    if through_binding_id is not None:
        through["binding_id"] = through_binding_id
    if through_stage_index is not None:
        through["stage_index"] = through_stage_index
    if through:
        body["through"] = through
    through_b: dict[str, Any] = {}
    if through_b_binding_id is not None:
        through_b["binding_id"] = through_b_binding_id
    if through_b_stage_index is not None:
        through_b["stage_index"] = through_b_stage_index
    if through_b:
        body["through_b"] = through_b
    return _probe(body)
