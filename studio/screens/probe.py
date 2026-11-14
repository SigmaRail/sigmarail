"""Stage-prefix screener probe (C-SCREEN-PROBE-V1).

Django-owned domain logic. SPA and sigmarail-studio MCP both POST the same bodies.
``view=layers`` never opens ClickHouse.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any, Literal

from screens.ir_preview import preview_universe_ir, validate_universe_ir_spec
from screens.universe_range_summary import (  # noqa: E402
    default_range_end_start,
    membership_tenure_by_ticker,
    summarize_universe_range,
)

_ASOF_DEFAULT_LIMIT = 500
_ASOF_HARD_LIMIT = 5000
_DIFF_NAME_CAP = 20
ProbeMode = Literal["measures", "members"]
ProbeView = Literal["layers", "asof", "range", "diff"]


def _parse_iso_date(value: str) -> date:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("date is required")
    return date.fromisoformat(raw[:10])


def _resolve_source(body: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (pipeline_doc dict | None, universe_spec | None). Exactly one source."""
    sources = []
    pipeline = body.get("pipeline")
    if isinstance(pipeline, dict):
        sources.append("pipeline")
    spec = body.get("spec")
    if isinstance(spec, dict):
        sources.append("spec")
    preset_id = str(body.get("preset_id") or "").strip()
    if preset_id:
        sources.append("preset_id")
    if len(sources) != 1:
        raise ValueError(
            "exactly one of pipeline, spec, preset_id is required "
            f"(got {sources or 'none'})"
        )
    if preset_id:
        from sigmarail_spec.strategy.presets import get_preset

        doc = get_preset(preset_id)
        return doc.model_dump(mode="json"), None
    if pipeline is not None:
        return pipeline, None
    return None, spec


def _compile_prefix(
    *,
    pipeline: dict[str, Any] | None,
    spec: dict[str, Any] | None,
    through: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build prefix payload. For ``spec`` source, pass through as UniverseQueryV1."""
    if spec is not None:
        validate_universe_ir_spec(spec)
        computed = list(spec.get("computed") or [])
        aliases = [str(c.get("alias") or "") for c in computed if c.get("alias")]
        through_out = {"binding_id": None, "stage_index": None, "stage_name": "spec"}
        if through:
            bid = through.get("binding_id")
            idx = through.get("stage_index")
            if bid is not None:
                bid_s = str(bid).strip()
                if bid_s not in aliases:
                    raise ValueError(f"unknown through_binding_id: {bid_s!r}")
                # Truncate computed through that alias (inclusive).
                cut = aliases.index(bid_s)
                computed = computed[: cut + 1]
                aliases = aliases[: cut + 1]
                through_out = {
                    "binding_id": bid_s,
                    "stage_index": cut,
                    "stage_name": bid_s,
                }
            elif idx is not None:
                k = int(idx)
                if k < 0 or k >= len(computed):
                    raise ValueError(f"through_stage_index out of range: {k}")
                computed = computed[: k + 1]
                aliases = aliases[: k + 1]
                through_out = {
                    "binding_id": aliases[-1] if aliases else None,
                    "stage_index": k,
                    "stage_name": aliases[-1] if aliases else "spec",
                }
        uni = copy.deepcopy(spec)
        if computed:
            uni["computed"] = computed
        else:
            uni.pop("computed", None)
        layers = [
            {
                "stage_index": i,
                "binding_id": a,
                "stage_name": a,
                "mode": "computed",
                "count_as_signal": a != "screens_hit" and a != "setup_pass",
                "as_gate": True,
            }
            for i, a in enumerate(aliases)
            if a not in ("screens_hit",)
        ]
        return {
            "universe": uni,
            "through": through_out,
            "computed_aliases": aliases,
            "layers": layers,
            "gate_combine": None,
        }

    assert pipeline is not None
    from sigmarail_spec.strategy.compiler import compile_pipeline_prefix
    from sigmarail_spec.strategy.pipeline import PipelineDocument

    doc = PipelineDocument.model_validate(pipeline)
    through = through or {}
    kwargs: dict[str, Any] = {}
    if through.get("binding_id") is not None:
        kwargs["through_binding_id"] = str(through["binding_id"]).strip()
    elif through.get("stage_index") is not None:
        kwargs["through_stage_index"] = int(through["stage_index"])
    else:
        # Default: through last stage that contributes to computed[] (filter gates,
        # authored number measures like hit_count / insight_*, and setup_pass).
        # Do not stop at the first signal — shortlist/Insight measures often follow.
        last = None
        for i, stage in enumerate(doc.stages):
            if stage.mode.value == "score" and stage.as_gate:
                if stage.filters or getattr(stage, "computed_expr", None):
                    last = i
            elif stage.mode.value == "signal" and stage.filters:
                last = i
        if last is None:
            raise ValueError("pipeline has no gate/setup stages to probe")
        kwargs["through_stage_index"] = last
    return compile_pipeline_prefix(doc, **kwargs)


def _apply_probe_mode(universe: dict[str, Any], *, probe_mode: str, through_binding: str | None) -> dict[str, Any]:
    """measures: hygiene WHERE only. members: AND the through stage bool predicate.

    Computed aliases are SELECT-only; do not col-ref them in WHERE (L7 catalog).
    Members mode reuses the gate ``where`` AST from ``computed[]``.
    """
    uni = copy.deepcopy(universe)
    mode = (probe_mode or "measures").strip().lower()
    if mode not in ("measures", "members"):
        raise ValueError(f"probe_mode must be measures|members, got {probe_mode!r}")
    if mode == "measures":
        return uni
    computed = list(uni.get("computed") or [])
    bool_items = [c for c in computed if c.get("kind") == "bool" and c.get("where")]
    target = None
    if through_binding:
        target = next((c for c in bool_items if c.get("alias") == through_binding), None)
    if target is None and bool_items:
        target = bool_items[-1]
    if target is None:
        raise ValueError("members mode requires a bool computed alias with where in the prefix")
    gate = copy.deepcopy(target["where"])
    where = uni.get("where")
    if not where or (isinstance(where, dict) and where.get("type") == "all" and not where.get("items")):
        uni["where"] = gate
    else:
        uni["where"] = {"type": "all", "items": [where, gate]}
    return uni


def _diagnostics_from_asof(rows: list[dict[str, Any]], aliases: list[str]) -> dict[str, Any]:
    n = len(rows)
    hit_rate: dict[str, float] = {}
    for alias in aliases:
        if alias == "screens_hit":
            continue
        vals = []
        for r in rows:
            v = r.get(alias)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if vals:
            hit_rate[alias] = round(sum(1 for v in vals if v >= 0.5) / len(vals), 4)
    sparse = [a for a, r in hit_rate.items() if r < 0.05]
    saturated = [a for a, r in hit_rate.items() if r > 0.95]
    return {
        "n_members": n,
        "hit_rate": hit_rate,
        "sparse": sparse,
        "saturated": saturated,
    }


def run_probe(body: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
    """Dispatch probe by ``view``. ``layers`` ignores ``client``."""
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    view = str(body.get("view") or "layers").strip().lower()
    if view not in ("layers", "asof", "range", "diff"):
        raise ValueError(f"view must be layers|asof|range|diff, got {view!r}")
    probe_mode = str(body.get("probe_mode") or "measures").strip().lower()
    include_sql = bool(body.get("include_sql"))
    through = body.get("through") if isinstance(body.get("through"), dict) else None

    pipeline, spec = _resolve_source(body)
    prefix = _compile_prefix(pipeline=pipeline, spec=spec, through=through)
    universe = prefix["universe"]
    aliases = list(prefix.get("computed_aliases") or [])
    through_binding = (prefix.get("through") or {}).get("binding_id")

    base_meta = {
        "probe_mode": probe_mode,
        "view": view,
        "through": prefix.get("through"),
        "computed_aliases": aliases,
        "layers": prefix.get("layers") or [],
        "contract": "C-SCREEN-PROBE-V1",
    }

    if view == "layers":
        return {
            **base_meta,
            "combinator_present": "screens_hit" in aliases,
            "diagnostics": {"note": "layers view does not query ClickHouse"},
        }

    uni_mode = _apply_probe_mode(universe, probe_mode=probe_mode, through_binding=through_binding)
    # NTH-1: optional allowlisted return fields (merged into UniverseQueryV1.select).
    # Never append names already in computed[] — that raises "collides with select".
    extra_raw = body.get("extra_select")
    computed_names = {
        str(c.get("alias") or "").strip()
        for c in (uni_mode.get("computed") or [])
        if isinstance(c, dict)
    }
    if isinstance(extra_raw, list) and extra_raw:
        cols = list(uni_mode.get("select") or [])
        for item in extra_raw[:8]:
            name = str(item).strip()
            if (
                name
                and name not in cols
                and name != "exchange"
                and name not in computed_names
            ):
                cols.append(name)
        uni_mode["select"] = cols
    order_raw = body.get("order_by")
    if isinstance(order_raw, list) and order_raw:
        # Only order by columns that exist on the compiled universe (select ∪ computed).
        available = set(uni_mode.get("select") or []) | computed_names
        cleaned: list[dict[str, Any]] = []
        for item in order_raw:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            if field and field in available:
                cleaned.append(item)
        if cleaned:
            uni_mode["order_by"] = cleaned
    validate_universe_ir_spec(uni_mode)

    if client is None:
        raise ValueError(f"view={view} requires a ClickHouse client")

    if view == "asof":
        as_of = str(body.get("as_of") or "").strip()
        if not as_of:
            raise ValueError("as_of is required for view=asof")
        limit = int(body.get("limit") or _ASOF_DEFAULT_LIMIT)
        limit = max(1, min(limit, _ASOF_HARD_LIMIT))
        # Cap limit_per_day for the preview.
        uni_mode = copy.deepcopy(uni_mode)
        uni_mode["limit_per_day"] = min(int(uni_mode.get("limit_per_day") or limit), limit)
        out = preview_universe_ir(client, as_of=as_of, spec_dict=uni_mode)
        rows = list(out.get("rows") or [])[:limit]
        if bool(body.get("include_tenure")):
            tenure_start = str(body.get("tenure_start") or body.get("start_date") or "").strip()
            if not tenure_start:
                tenure_start, _ = default_range_end_start(end_date=as_of)
            tickers = [str(r.get("ticker") or "").upper() for r in rows if r.get("ticker")]
            try:
                tenure = membership_tenure_by_ticker(
                    client,
                    spec=uni_mode,
                    start_date=tenure_start,
                    asof=as_of,
                    tickers=tickers or None,
                )
                for r in rows:
                    t = str(r.get("ticker") or "").upper()
                    r["days_in_universe"] = int(tenure.get(t, 0))
            except Exception as exc:
                # Tenure is optional enrichment — do not fail the asof table.
                for r in rows:
                    r.setdefault("days_in_universe", None)
                diag_note = f"tenure_skipped: {exc}"
            else:
                diag_note = None
        else:
            diag_note = None
        diag = _diagnostics_from_asof(rows, aliases)
        diag["n_universe"] = int(out.get("count") or len(rows))
        if diag_note:
            diag["note"] = diag_note
        result: dict[str, Any] = {
            **base_meta,
            "as_of": out.get("as_of") or as_of,
            "columns": out.get("columns") or [],
            "rows": rows,
            "count": len(rows),
            "diagnostics": diag,
        }
        if bool(body.get("include_tenure")) and rows and "days_in_universe" in rows[0]:
            cols = list(result["columns"])
            if "days_in_universe" not in cols:
                cols.append("days_in_universe")
            result["columns"] = cols
        if include_sql:
            _parsed, sql, params = validate_universe_ir_spec(uni_mode)
            result["sql"] = sql.strip()
            result["params"] = {k: params[k] for k in sorted(params)}
        return result

    if view == "range":
        end_date = str(body.get("end_date") or "").strip()
        start_date = str(body.get("start_date") or "").strip()
        if not end_date:
            raise ValueError("end_date is required for view=range")
        if not start_date:
            start_date, end_date = default_range_end_start(end_date=end_date)
        # No width cap: the range summary is one aggregate query, and how much history to chart
        # is the caller's choice. An inverted pair is still rejected below.
        _parse_iso_date(start_date)
        _parse_iso_date(end_date)
        summary = summarize_universe_range(
            client, spec=uni_mode, start_date=start_date, end_date=end_date
        )
        enabled_raw = body.get("enabled_bindings")
        enabled_bindings: list[str] = []
        if isinstance(enabled_raw, list):
            enabled_bindings = [
                str(x).strip()
                for x in enabled_raw
                if str(x).strip() and str(x).strip() != "screens_hit"
            ]
        cumulative = bool(body.get("cumulative"))
        bool_aliases = [a for a in aliases if a != "screens_hit"][:8]
        funnel_aliases = (
            [a for a in enabled_bindings if a in bool_aliases]
            if cumulative and enabled_bindings
            else None
        )
        measure_series = _measure_series_range(
            client,
            spec=uni_mode,
            start_date=start_date,
            end_date=end_date,
            aliases=bool_aliases,
            screens_hit="screens_hit" in aliases,
            funnel_aliases=funnel_aliases,
        )
        empty_days = sum(1 for c in summary.get("member_counts") or [] if c == 0)
        return {
            **base_meta,
            "start_date": summary["start_date"],
            "end_date": summary["end_date"],
            "dates": summary["dates"],
            "member_counts": summary["member_counts"],
            "summary": summary.get("summary"),
            "measure_series": measure_series,
            "enabled_bindings": enabled_bindings,
            "cumulative": cumulative,
            "diagnostics": {
                "empty_days": empty_days,
                "trading_days": (summary.get("summary") or {}).get("trading_days", 0),
                "avg_members_per_day": (summary.get("summary") or {}).get(
                    "avg_members_per_day", 0
                ),
                "series_unit": "pass_count",
            },
        }

    # diff: compare through vs previous layer (or through_b)
    through_b = body.get("through_b") if isinstance(body.get("through_b"), dict) else None
    if through_b is None and through is not None:
        # Default: previous stage index
        idx = (prefix.get("through") or {}).get("stage_index")
        if idx is None or int(idx) <= 0:
            raise ValueError("diff needs through_b or a through stage_index > 0")
        through_b = {"stage_index": int(idx) - 1}
    if through_b is None:
        raise ValueError("diff requires through and through_b (or stage_index > 0)")

    as_of = str(body.get("as_of") or "").strip()
    if not as_of:
        raise ValueError("as_of is required for view=diff")

    prefix_b = _compile_prefix(pipeline=pipeline, spec=spec, through=through_b)
    uni_a = _apply_probe_mode(
        universe, probe_mode=probe_mode, through_binding=through_binding
    )
    uni_b = _apply_probe_mode(
        prefix_b["universe"],
        probe_mode=probe_mode,
        through_binding=(prefix_b.get("through") or {}).get("binding_id"),
    )
    for uni in (uni_a, uni_b):
        uni["limit_per_day"] = min(int(uni.get("limit_per_day") or 200), 200)

    out_a = preview_universe_ir(client, as_of=as_of, spec_dict=uni_a)
    out_b = preview_universe_ir(client, as_of=as_of, spec_dict=uni_b)
    set_a = {str(r.get("ticker")) for r in (out_a.get("rows") or []) if r.get("ticker")}
    set_b = {str(r.get("ticker")) for r in (out_b.get("rows") or []) if r.get("ticker")}
    entering = sorted(set_a - set_b)[:_DIFF_NAME_CAP]
    leaving = sorted(set_b - set_a)[:_DIFF_NAME_CAP]
    inter = len(set_a & set_b)
    union = len(set_a | set_b) or 1
    jaccard = round(inter / union, 4)
    return {
        **base_meta,
        "as_of": as_of,
        "through_b": prefix_b.get("through"),
        "size_a": len(set_a),
        "size_b": len(set_b),
        "size_delta": len(set_a) - len(set_b),
        "jaccard": jaccard,
        "entering": entering,
        "leaving": leaving,
        "diagnostics": {
            "drop_off": round(1.0 - (len(set_a) / max(len(set_b), 1)), 4) if set_b else None,
            "n_entering": len(set_a - set_b),
            "n_leaving": len(set_b - set_a),
        },
    }


def _measure_series_range(
    client: Any,
    *,
    spec: dict[str, Any],
    start_date: str,
    end_date: str,
    aliases: list[str],
    screens_hit: bool,
    funnel_aliases: list[str] | None = None,
) -> dict[str, list[float]]:
    """Per-day pass counts for bool computed cols (+ optional AND funnel).

    Bool aliases use ``sum(toUInt8(alias))`` (absolute passers among hygiene rows),
    not ``avg`` hit-rate — same units as ``member_counts``.
    """
    from sigmarail.universe import universe_measure_series

    return universe_measure_series(
        spec,
        start_date=start_date,
        end_date=end_date,
        aliases=aliases,
        screens_hit=screens_hit,
        funnel_aliases=funnel_aliases,
        client=client,
    )


__all__ = ["run_probe"]
