"""Pipeline compiler: ``PipelineDocument`` -> VeraLabV1 JSON document.

The compiler is a pure data transform (no SQL, no codegen). It walks the
stages and produces the VeraLabV1 five-slot shape that ``main.py`` consumes:

    {
      "SchemaVersion": 2,
      "Kind": "VeraLabV1",
      "Framework": {UniverseSelection, Alpha, PortfolioConstruction,
                    Execution, RiskManagement},
      "AlgorithmParameters": {...},  # only knobs still read at runtime
      "VeraBase": {
        "Universe": {...},           # pushdown where = universe.screen tree
        "DataSources": [...],
        "Regime": {...},             # optional score config
      },
    }

Universe slot owns screen (boolean tree) plus derived membership / named_groups
for Alpha flags. Alpha Parameters hold stages / gates / setup_where / pyramid only.
``VeraBase.Pipeline`` is not persisted (C-STRATEGY-PIPELINE-SSOT amend).
"""

from __future__ import annotations

import json
import re

from .field_registry import resolve_factor
from .pipeline import (
    AllocationPolicy,
    ExecutionConfig,
    FilterCondition,
    FilterGroup,
    FilterNot,
    FilterNode,
    ModelRef,
    PipelineBindings,
    PipelineDocument,
    PortfolioDocument,
    RiskRule,
    RiskRuleType,
    SelectionRule,
    SizingConfig,
    SizingPolicy,
    Stage,
    StageType,
    UniverseSource,
    champion_default_bindings,
    policy_rules_to_bindings,
)


# Columns that must always appear in the universe select list.
_BASE_SELECT = ["ticker", "close", "closeadj", "overall_score", "atr_14_pct"]

_TRIGGER_SELECT: dict[str, tuple[str, ...]] = {
    "pivot_breakout": ("high", "high_5d", "high_90d", "volume", "avg_vol_50d", "breakout_signal"),
    "breakout": ("high", "high_5d", "high_90d", "volume", "avg_vol_50d", "breakout_signal"),
    "vcp_complete": (
        "close",
        "high_90d",
        "vcp_atr_compression_5d_90d",
        "vcp_volume_dryup_5d_90d",
        "vcp_proximity_90d",
    ),
    "pullback_to_sma": ("close", "pullback_ready", "pocket_pivot_score", "sma50d"),
    "ema_cross": ("ema_21d", "sma50d"),
}

_OPERAND_TYPES = {"col", "lit", "formula"}


def _eq_col_lit1(where: dict | None) -> str | None:
    """Sugar: ``eq(col, 1)`` → column name for legacy ``setup_col``."""
    if not isinstance(where, dict) or where.get("type") != "eq":
        return None
    left, right = where.get("left"), where.get("right")
    if not isinstance(left, dict) or left.get("type") != "col":
        return None
    if not isinstance(right, dict) or right.get("type") != "lit":
        return None
    try:
        if int(right.get("value")) != 1:
            return None
    except (TypeError, ValueError):
        return None
    name = left.get("name")
    return str(name) if name else None


def _resolve_bindings(
    doc: PipelineDocument, computed_aliases: set[str]
) -> PipelineBindings | None:
    """Resolve flat bindings from policy_rules chain and/or authored bindings."""
    base: PipelineBindings | None = doc.bindings
    if base is None and (doc.gate_combine or "").lower() == "count":
        # Prefer authored combinator alias when present; else first score-gate id.
        hit_col = "screens_hit" if "screens_hit" in computed_aliases else None
        if hit_col is None:
            for alias in sorted(computed_aliases):
                if alias.startswith("screen_") or alias in ("hit_count", "screens_hit_w"):
                    hit_col = alias
                    break
        if hit_col is not None:
            base = champion_default_bindings(
                min_screens=int(doc.min_screens or 2),
                setup_col="setup_pass",
                hit_col=hit_col,
                include_setup="setup_pass" in computed_aliases,
            )
    if doc.policy_rules:
        return policy_rules_to_bindings(doc.policy_rules, base=base)
    return base


def _apply_bindings_to_slots(
    bindings: PipelineBindings,
    *,
    alpha_params: dict,
    pcm_params: dict,
    risk_params: dict,
    sort_col: str,
    min_screens: int,
) -> None:
    """Copy SlotExpr onto five-slot Parameters (AST first; sugar when applicable)."""
    if bindings.alpha_setup is not None and bindings.alpha_setup.where is not None:
        where = bindings.alpha_setup.where
        alpha_params["setup_expr"] = where
        sugar = _eq_col_lit1(where)
        if sugar:
            alpha_params["setup_col"] = sugar
        else:
            alpha_params.pop("setup_col", None)
    if bindings.alpha_rank:
        by = list(bindings.alpha_rank)
        if sort_col and sort_col not in by and len(by) == 1:
            by = by + [sort_col]
        min_map: dict = {}
        if bindings.alpha_eligibility and bindings.alpha_eligibility.where:
            # Prefer explicit min on first rank col when eligibility is gte(col, N)
            elig = bindings.alpha_eligibility.where
            if elig.get("type") == "gte":
                left, right = elig.get("left"), elig.get("right")
                if (
                    isinstance(left, dict)
                    and left.get("type") == "col"
                    and isinstance(right, dict)
                    and right.get("type") == "lit"
                    and by
                    and left.get("name") == by[0]
                ):
                    try:
                        min_map[str(by[0])] = int(right.get("value"))
                    except (TypeError, ValueError):
                        min_map[str(by[0])] = int(min_screens or 1)
        if not min_map and by:
            # Floor stays on unweighted hits when ranking by screens_hit_w.
            floor_key = "screens_hit" if str(by[0]) == "screens_hit_w" else str(by[0])
            min_map[floor_key] = int(min_screens or 1)
        alpha_params["row_rank"] = {"by": by, "min": min_map}
        if bindings.alpha_eligibility and bindings.alpha_eligibility.where:
            alpha_params["eligibility_expr"] = bindings.alpha_eligibility.where
    if bindings.alpha_confidence is not None and bindings.alpha_confidence.expr is not None:
        alpha_params["confidence_expr"] = bindings.alpha_confidence.expr
        alpha_params.setdefault("row_scale_denom", 5)
    if bindings.alpha_direction is not None and bindings.alpha_direction.expr is not None:
        alpha_params["direction_expr"] = bindings.alpha_direction.expr
    if bindings.alpha_magnitude is not None and bindings.alpha_magnitude.expr is not None:
        alpha_params["magnitude_expr"] = bindings.alpha_magnitude.expr
    if bindings.alpha_weight is not None and bindings.alpha_weight.expr is not None:
        alpha_params["weight_expr"] = bindings.alpha_weight.expr
    if bindings.alpha_insight_period_days is not None:
        alpha_params["insight_period_days"] = int(bindings.alpha_insight_period_days)
    if bindings.pcm_scale is not None and bindings.pcm_scale.expr is not None:
        pcm_params["pcm_scale_expr"] = bindings.pcm_scale.expr
        pcm_params["honor_insight_confidence"] = False
        pcm_params.pop("row_scale_col", None)
        pcm_params.pop("row_scale_denom", None)
    if bindings.pcm_allow_entry is not None and bindings.pcm_allow_entry.where is not None:
        pcm_params["pcm_allow_entry_expr"] = bindings.pcm_allow_entry.where
    if bindings.risk_skip_time_stop is not None and bindings.risk_skip_time_stop.where is not None:
        risk_params["risk_skip_time_stop_expr"] = bindings.risk_skip_time_stop.where
        # Prefer SlotExpr; drop legacy time_stop_skip_if sugar when binding is present.
        risk_params.pop("time_stop_skip_if", None)
    if (
        bindings.risk_allow_pyramid_add is not None
        and bindings.risk_allow_pyramid_add.where is not None
    ):
        where = bindings.risk_allow_pyramid_add.where
        # PCM sizes pyramid adds; Alpha emits them — both must see the gate.
        # Risk ManageRisk does not consume this gate (keep off Risk Parameters).
        pcm_params["risk_allow_pyramid_add_expr"] = where
        alpha_params["risk_allow_pyramid_add_expr"] = where


def _universe_rank_order_by(
    *,
    bindings: PipelineBindings | None,
    sort_col: str,
    select_cols: list[str],
    computed_aliases: set[str],
    gate_combine: str | None,
    bool_gate_aliases: set[str] | None = None,
) -> list[dict]:
    """Build Universe.order_by from insight rank keys (alpha_rank), else legacy defaults.

    Bool gate aliases (filter measures) must not appear in ORDER BY — Insight on those
    goes to post_where via eligibility ``alias = 1``.
    """
    available = set(select_cols) | set(computed_aliases)
    skip_bool = set(bool_gate_aliases or ())
    dirs = (
        dict(bindings.alpha_rank_directions)
        if bindings is not None and bindings.alpha_rank_directions
        else {}
    )
    if bindings is not None and bindings.alpha_rank:
        by = [
            ("screens_hit" if str(x) == "hit_count" and "screens_hit" in computed_aliases else str(x))
            for x in bindings.alpha_rank
            if str(x) and str(x) not in skip_bool
        ]
        order: list[dict] = []
        for field in by:
            if field not in available:
                # Ensure tie-break / rank cols are selected when possible.
                if field not in computed_aliases and field not in ("hit_count", "screens_hit", "screens_hit_w"):
                    select_cols.append(field)
                    available.add(field)
            direction = str(dirs.get(field) or "desc").lower()
            if direction not in ("asc", "desc"):
                direction = "desc"
            order.append({"field": field, "direction": direction})
        if order:
            return order
    order_by: list[dict] = [{"field": sort_col, "direction": "desc"}]
    if (gate_combine or "").lower() == "count" and "screens_hit" in computed_aliases:
        order_by = [
            {"field": "screens_hit", "direction": "desc"},
            {"field": sort_col, "direction": "desc"},
        ]
        if sort_col not in select_cols and sort_col not in computed_aliases:
            select_cols.append(sort_col)
        if "rs_rating" in select_cols and sort_col != "rs_rating":
            order_by = [
                {"field": "screens_hit", "direction": "desc"},
                {"field": "rs_rating", "direction": "desc"},
            ]
    return order_by


def _universe_post_where(
    *,
    bindings: PipelineBindings | None,
    stages: list,
    computed_aliases: set[str],
    min_screens: int,
    gate_combine: str | None,
) -> dict | None:
    """Eligibility / measure filters as Universe.post_where (alias-safe outer WHERE)."""
    from sigmarail.features.ir.universe_v1_column_registry import get_universe_v1_col_sql_map

    known_cols = set(get_universe_v1_col_sql_map().keys())
    stage_ids = {_stage_id(s) for s in stages if _STAGE_ID_RE.match(_stage_id(s))}
    # Signal/setup aliases that may appear in bindings without a computed emit.
    stage_ids |= {"setup_pass", "screens_hit", "screens_hit_w"}

    def _has_dangling_stage_ref(where: dict) -> bool:
        refs = _leaf_col_names(where)
        return bool((refs & stage_ids) - computed_aliases - known_cols)

    items: list[dict] = []
    if bindings is not None and bindings.alpha_eligibility and bindings.alpha_eligibility.where:
        elig = dict(bindings.alpha_eligibility.where)
        if not _has_dangling_stage_ref(elig):
            items.append(elig)
    elif (gate_combine or "").lower() == "count" and "screens_hit" in computed_aliases:
        items.append(
            {
                "type": "gte",
                "left": {"type": "col", "name": "screens_hit"},
                "right": {"type": "lit", "value": int(min_screens or 1)},
            }
        )
    # Setup as SQL filter only when setup_pass (or other stage cols) were emitted.
    if bindings is not None and bindings.alpha_setup and bindings.alpha_setup.where:
        setup_where = dict(bindings.alpha_setup.where)
        if not _has_dangling_stage_ref(setup_where):
            items.append(setup_where)
    for stage in stages:
        mf = getattr(stage, "measure_filter", None)
        if mf is None:
            continue
        node = _cmp_node(mf)
        if _has_dangling_stage_ref(node):
            continue
        items.append(node)
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return {"type": "all", "items": items}


# Binding ids for computed aliases / probe addressing (C-SCREEN-PROBE-V1).
_STAGE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _as_operand(value: object, *, kind: str | None = None) -> dict:
    """Normalize a pipeline operand into a universe_query_v1 operand node.

    ``kind`` supplies the fallback interpretation for a bare string: ``"col"``
    for left-hand operands / column comparisons, otherwise a literal.
    """
    if isinstance(value, dict) and value.get("type") in _OPERAND_TYPES:
        return dict(value)
    if kind in ("col", "formula"):
        return {"type": "col", "name": str(value)}
    return {"type": "lit", "value": value}


def _cmp_node(cond: FilterCondition) -> dict:
    """Map a FilterCondition to a universe_query_v1 comparison node."""
    left = _as_operand(cond.left, kind="col")
    right = _as_operand(cond.right, kind=cond.right_kind)
    if cond.op == "neq":
        return {"type": "not", "item": {"type": "eq", "left": left, "right": right}}
    return {"type": cond.op, "left": left, "right": right}


def _filter_node(node: FilterNode) -> dict:
    """Recursively map a pipeline filter tree to a universe_query_v1 where node.

    Mirrors ``decompiler._decompile_where``: an ``and`` group lowers to
    ``all`` and an ``or`` group lowers to ``any``, at any depth.
    """
    if isinstance(node, FilterNot):
        return {"type": "not", "item": _filter_node(node.item)}
    if isinstance(node, FilterGroup):
        out: dict = {
            "type": "all" if node.logic == "and" else "any",
            "items": [_filter_node(child) for child in node.conditions],
        }
        if node.name:
            out["name"] = node.name
        return out
    return _cmp_node(node)


def _prune_nulls(node: object) -> object:
    """Drop ``None``-valued keys recursively.

    Authored rule dicts carry flattened action fields (``days``, ``flag``,
    ``fraction``…) set to null; the runtime ``Rule``/action models are
    ``extra="forbid"``, so a null extra key still fails validation.
    """
    if isinstance(node, dict):
        return {k: _prune_nulls(v) for k, v in node.items() if v is not None}
    if isinstance(node, list):
        return [_prune_nulls(v) for v in node]
    return node


def _combine_filters(stages: list[Stage]) -> list[FilterNode]:
    """Collect filter + signal trees (signal is not membership; still needs select)."""
    out: list[FilterNode] = []
    for stage in stages:
        if stage.mode in (StageType.FILTER, StageType.SIGNAL):
            out.extend(stage.filters)
    return out


def _signal_filters(stages: list[Stage]) -> list[FilterNode]:
    """Setup AST owned by signal stages — not CH membership pushdown."""
    out: list[FilterNode] = []
    for stage in stages:
        if stage.mode == StageType.SIGNAL:
            out.extend(stage.filters)
    return out


def _gates_from_stages(stages: list[Stage]) -> list[dict]:
    """Emit Alpha.Parameters.gates[] from authored score stages with as_gate.

    Boolean-AST gates (Champion screens) emit ``where`` + ``count_as_signal``
    without ``score_fields`` when factors are empty. ``require_flag`` defaults
    to ``in_membership`` — ``omit_tt`` does not imply ``in_code_33``.
    """
    gates: list[dict] = []
    for stage in stages:
        if stage.mode != StageType.SCORE or not stage.as_gate:
            continue
        # Number expression measures are gates in Studio but not Alpha bool AST rows.
        if getattr(stage, "computed_expr", None):
            continue
        fields = [_factor_column(fw.name) for fw in stage.factors]
        gate: dict = {
            "id": _stage_id(stage),
            "count_as_signal": bool(stage.count_as_signal),
            "require_flag": stage.require_flag or "in_membership",
            "signal_weight": float(stage.signal_weight or 1.0),
        }
        if fields:
            gate["score_fields"] = fields
            top_k = 15
            if stage.selection and stage.selection.n:
                top_k = int(stage.selection.n)
            gate["top_k"] = top_k
        if stage.optional_score_fields:
            gate["optional_score_fields"] = list(stage.optional_score_fields)
        if stage.optional_min:
            gate["optional_min"] = dict(stage.optional_min)
        if stage.omit_tt:
            gate["omit_tt"] = True
        where = _build_where(list(stage.filters))
        if where:
            gate["where"] = where
        gates.append(gate)
    return gates


def _stage_id(stage: Stage) -> str:
    """Stable binding id for computed columns / Alpha / PCM / Risk."""
    if stage.id:
        return stage.id
    return stage.name.lower().replace(" ", "_")


def _bool_gate_aliases(stages: list[Stage]) -> set[str]:
    """Score gates with filters-only payload (no computed_expr) — Insight → WHERE, not ORDER BY."""
    out: set[str] = set()
    for stage in stages:
        if stage.mode != StageType.SCORE or not stage.as_gate:
            continue
        if getattr(stage, "computed_expr", None):
            continue
        sid = _stage_id(stage)
        if sid:
            out.add(sid)
    return out


def _binding_aliases_for_stage(stage: Stage) -> set[str]:
    """Aliases a stage may be addressed by in ``through_binding_id``."""
    sid = _stage_id(stage)
    out = {sid}
    if stage.mode == StageType.SIGNAL and stage.filters:
        out.add("setup_pass")
        if sid == "setup_group":
            out.add("setup_group")
    return out


def _resolve_prefix_cut(
    stages: list[Stage],
    *,
    through_stage_index: int | None,
    through_binding_id: str | None,
) -> int:
    """Inclusive stage index for prefix compile. Prefer binding_id."""
    if through_binding_id is not None:
        bid = str(through_binding_id).strip()
        if not bid or not _STAGE_ID_RE.match(bid):
            raise ValueError(f"invalid through_binding_id: {through_binding_id!r}")
        if bid == "screens_hit" or bid == "screens_hit_w":
            # Combinator requires every count_as_signal gate; cut at last such gate.
            last = -1
            for i, stage in enumerate(stages):
                if (
                    stage.mode == StageType.SCORE
                    and stage.as_gate
                    and stage.count_as_signal
                    and _build_where(list(stage.filters))
                ):
                    last = i
            if last < 0:
                raise ValueError(f"through_binding_id {bid!r} but no count_as_signal gates")
            return last
        for i, stage in enumerate(stages):
            if bid in _binding_aliases_for_stage(stage):
                return i
        raise ValueError(f"unknown through_binding_id: {bid!r}")
    if through_stage_index is None:
        raise ValueError("through_binding_id or through_stage_index is required")
    k = int(through_stage_index)
    if k < 0 or k >= len(stages):
        raise ValueError(f"through_stage_index out of range: {k}")
    return k


def _full_count_aliases(stages: list[Stage]) -> list[str]:
    """count_as_signal gate aliases for the full stage list (Champion screens_hit)."""
    out: list[str] = []
    for stage in stages:
        if stage.mode != StageType.SCORE or not stage.as_gate:
            continue
        if not stage.count_as_signal:
            continue
        if not _build_where(list(stage.filters)):
            continue
        out.append(_stage_id(stage))
    return out


def _computed_from_stages(
    stages: list[Stage],
    *,
    gate_combine: str | None,
    setup_where: dict | None,
    full_count_aliases: list[str] | None = None,
) -> list[dict]:
    """Emit Universe.computed[] for gate/setup bools and count combinator.

    Phase 1: ``gate_combine=count`` → per-gate ``toUInt8`` aliases + ``screens_hit``
    sum of ``count_as_signal`` gates. Setup signal filters → ``setup_pass``.

    When ``full_count_aliases`` is set (prefix compile), emit ``screens_hit`` only if
    every full-document count alias is present in this stage subset.
    """
    computed: list[dict] = []
    count_aliases: list[str] = []
    prior: set[str] = set()

    for stage in stages:
        if stage.mode != StageType.SCORE or not stage.as_gate:
            continue
        if getattr(stage, "computed_expr", None):
            continue
        where = _build_where(list(stage.filters))
        if not where:
            continue
        alias = _stage_id(stage)
        if not _STAGE_ID_RE.match(alias):
            raise ValueError(f"invalid stage binding id: {alias!r}")
        computed.append({"alias": alias, "kind": "bool", "where": where})
        prior.add(alias)
        if stage.count_as_signal:
            count_aliases.append(alias)

    # Setup pass: first signal stage that has filters (Champion Setup Group).
    for stage in stages:
        if stage.mode != StageType.SIGNAL or not stage.filters:
            continue
        alias = _stage_id(stage)
        if alias == "setup_group":
            alias = "setup_pass"
        if not _STAGE_ID_RE.match(alias):
            raise ValueError(f"invalid stage binding id: {alias!r}")
        where = setup_where or _build_where(list(stage.filters))
        if where and alias not in prior:
            computed.append({"alias": alias, "kind": "bool", "where": where})
            prior.add(alias)
        break
    else:
        if setup_where and "setup_pass" not in prior:
            computed.append({"alias": "setup_pass", "kind": "bool", "where": setup_where})
            prior.add("setup_pass")

    authored_hit = next(
        (
            s
            for s in stages
            if getattr(s, "computed_expr", None)
            and _stage_id(s) == "screens_hit"
        ),
        None,
    )
    authored_hit_w = next(
        (
            s
            for s in stages
            if getattr(s, "computed_expr", None)
            and _stage_id(s) == "screens_hit_w"
        ),
        None,
    )

    if authored_hit is not None:
        expr = dict(authored_hit.computed_expr)
        refs = _leaf_col_names(expr)
        missing = [a for a in refs if a not in prior and a not in ("screens_hit", "screens_hit_w")]
        if missing and count_aliases:
            # Studio may sync screens_hit = screen_1+… before gate filters compile.
            # Prefer sum of emitted count gates over dangling L7 lookups.
            computed.append(
                {
                    "alias": "screens_hit",
                    "kind": "number",
                    "sum_aliases": list(count_aliases),
                }
            )
            prior.add("screens_hit")
        elif missing:
            raise ValueError(
                f"screens_hit expr references unknown computed aliases {missing!r}; "
                "add gate filters (as_gate) or remove those columns from the formula"
            )
        elif refs and set(refs).issubset(set(count_aliases)):
            # Studio densifies screens_hit as Σ gate cols; emit sum_aliases (C-UNIVERSE-QUERY-V1).
            sum_ids = [a for a in count_aliases if a in refs]
            computed.append(
                {
                    "alias": "screens_hit",
                    "kind": "number",
                    "sum_aliases": sum_ids or list(count_aliases),
                }
            )
            prior.add("screens_hit")
        else:
            computed.append(
                {
                    "alias": "screens_hit",
                    "kind": "number",
                    "expr": expr,
                }
            )
            prior.add("screens_hit")
    elif (gate_combine or "").lower() == "count" and count_aliases:
        required = list(full_count_aliases) if full_count_aliases is not None else list(count_aliases)
        if full_count_aliases is None or set(required).issubset(set(count_aliases)):
            sum_ids = list(required) if full_count_aliases is not None else list(count_aliases)
            computed.append(
                {
                    "alias": "screens_hit",
                    "kind": "number",
                    "sum_aliases": sum_ids,
                }
            )
            prior.add("screens_hit")

    if authored_hit_w is not None:
        computed.append(
            {
                "alias": "screens_hit_w",
                "kind": "number",
                "expr": dict(authored_hit_w.computed_expr),
            }
        )
        prior.add("screens_hit_w")
    elif (gate_combine or "").lower() == "count" and count_aliases and "screens_hit" in prior:
        sum_ids = (
            list(full_count_aliases)
            if full_count_aliases is not None
            else list(count_aliases)
        )
        if full_count_aliases is None or set(sum_ids).issubset(set(count_aliases)):
            weights_by_id: dict[str, float] = {}
            for stage in stages:
                if stage.mode != StageType.SCORE or not stage.as_gate:
                    continue
                if not stage.count_as_signal:
                    continue
                sid = _stage_id(stage)
                if sid in sum_ids:
                    weights_by_id[sid] = float(stage.signal_weight or 1.0)
            if any(abs(weights_by_id.get(a, 1.0) - 1.0) > 1e-12 for a in sum_ids):
                computed.append(
                    {
                        "alias": "screens_hit_w",
                        "kind": "number",
                        "expr": _weighted_hit_expr(
                            [(a, weights_by_id.get(a, 1.0)) for a in sum_ids]
                        ),
                    }
                )
                prior.add("screens_hit_w")

    # Author computed number measures (aggregate prior aliases / L7).
    for stage in stages:
        expr = getattr(stage, "computed_expr", None)
        if not expr:
            continue
        alias = _stage_id(stage)
        if not _STAGE_ID_RE.match(alias):
            raise ValueError(f"invalid stage binding id: {alias!r}")
        if alias in ("screens_hit", "screens_hit_w"):
            continue  # already emitted above
        # Field Insight: alias is an L7/select column — ORDER BY uses it directly.
        if (
            isinstance(expr, dict)
            and expr.get("type") == "col"
            and str(expr.get("name") or "") == alias
        ):
            continue
        if alias in prior:
            raise ValueError(f"computed measure alias {alias!r} collides with prior computed")
        computed.append({"alias": alias, "kind": "number", "expr": dict(expr)})
        prior.add(alias)

    return computed


def _weighted_hit_expr(terms: list[tuple[str, float]]) -> dict:
    """Left-fold Σ (w_i * alias_i) as a formula Operand dict."""
    if not terms:
        raise ValueError("weighted hit requires at least one term")

    def _term(alias: str, weight: float) -> dict:
        col = {"type": "col", "name": alias}
        if abs(float(weight) - 1.0) < 1e-12:
            return col
        return {
            "type": "formula",
            "op": "*",
            "args": [{"type": "lit", "value": float(weight)}, col],
        }

    expr = _term(terms[0][0], terms[0][1])
    for alias, weight in terms[1:]:
        expr = {
            "type": "formula",
            "op": "+",
            "args": [expr, _term(alias, weight)],
        }
    return expr


def compile_pipeline_prefix(
    doc: PipelineDocument,
    *,
    through_stage_index: int | None = None,
    through_binding_id: str | None = None,
) -> dict:
    """Universe spec with ``computed[]`` only through stage k (inclusive).

    Prefer ``through_binding_id``. Returns a probe payload (not a full VeraLabV1):

    - ``universe``: UniverseQueryV1-shaped dict (hygiene WHERE + prefix computed)
    - ``through``: resolved cut ``{binding_id, stage_index, stage_name}``
    - ``computed_aliases``: ordered alias list
    - ``layers``: gate/setup layers included in the prefix
    """
    stages = list(doc.stages)
    k = _resolve_prefix_cut(
        stages,
        through_stage_index=through_stage_index,
        through_binding_id=through_binding_id,
    )
    prefix_stages = stages[: k + 1]
    cut_stage = stages[k]
    cut_binding = _stage_id(cut_stage)
    if through_binding_id and str(through_binding_id).strip() == "screens_hit":
        cut_binding = "screens_hit"
    elif cut_stage.mode == StageType.SIGNAL and cut_stage.filters:
        if cut_binding == "setup_group" or _stage_id(cut_stage) in ("setup_pass", "setup_group"):
            cut_binding = "setup_pass"
        elif through_binding_id and str(through_binding_id).strip() == "setup_pass":
            cut_binding = "setup_pass"

    factors = _collect_factors(prefix_stages)
    # Blend factors from full doc still useful for select harvest of physical cols
    # used by gates in the prefix; keep select lean via prefix stages + screen.
    select_cols = _build_select_columns(factors, prefix_stages, extra=doc.universe.select)
    for node in doc.universe.screen or []:
        for col in _filter_columns(node):
            if col and col not in select_cols:
                select_cols.append(col)

    screen_where, _membership_where, _named_groups = _screen_from_doc(doc)
    setup_where = _build_where(_signal_filters(prefix_stages))
    full_counts = _full_count_aliases(stages)
    computed = _computed_from_stages(
        prefix_stages,
        gate_combine=doc.gate_combine,
        setup_where=setup_where,
        full_count_aliases=full_counts,
    )
    computed_aliases = {c["alias"] for c in computed}

    # Fail closed: each computed where/expr must not col-ref aliases emitted later.
    emitted: set[str] = set()
    all_aliases = {c["alias"] for c in computed}
    for c in computed:
        alias = str(c.get("alias") or "")
        refs: set[str] = set()
        if c.get("where"):
            refs |= _leaf_col_names(c["where"])
        if c.get("expr"):
            refs |= _leaf_col_names(c["expr"])
        ahead = sorted(r for r in refs if r in all_aliases and r not in emitted and r != alias)
        if ahead:
            raise ValueError(
                f"computed {alias!r} references aliases not yet emitted: {ahead}"
            )
        emitted.add(alias)

    for c in computed:
        payload = c.get("where") or c.get("expr") or {}
        for col in _leaf_col_names(payload):
            if col and col not in select_cols and col not in computed_aliases:
                select_cols.append(col)

    sort_col = _primary_sort_column(factors)
    # Prefix compile: no full bindings resolve — keep count-mode ORDER BY defaults.
    order_by = _universe_rank_order_by(
        bindings=None,
        sort_col=sort_col,
        select_cols=select_cols,
        computed_aliases=set(computed_aliases),
        gate_combine=doc.gate_combine,
        bool_gate_aliases=_bool_gate_aliases(prefix_stages),
    )

    limit_per_day = 101
    if doc.universe.limit_per_day:
        limit_per_day = min(5000, int(doc.universe.limit_per_day))

    from sigmarail.features.ir.l7_from import resolve_joins_for_columns

    universe_spec: dict = {
        "version": 2,
        "spine": "screener_price_tech_daily",
        "joins": resolve_joins_for_columns(set(select_cols)),
        "select": select_cols,
        "order_by": order_by,
        "limit_per_day": limit_per_day,
        "where": screen_where or {"type": "all", "items": []},
    }
    if computed:
        universe_spec["computed"] = computed

    layers: list[dict] = []
    for i, stage in enumerate(prefix_stages):
        if stage.mode == StageType.SCORE and stage.as_gate and _build_where(list(stage.filters)):
            layers.append(
                {
                    "stage_index": i,
                    "binding_id": _stage_id(stage),
                    "stage_name": stage.name,
                    "mode": stage.mode.value,
                    "count_as_signal": bool(stage.count_as_signal),
                    "as_gate": True,
                }
            )
        elif stage.mode == StageType.SIGNAL and stage.filters:
            sid = _stage_id(stage)
            layers.append(
                {
                    "stage_index": i,
                    "binding_id": "setup_pass" if sid in ("setup_group", "setup_pass") else sid,
                    "stage_name": stage.name,
                    "mode": stage.mode.value,
                    "count_as_signal": False,
                    "as_gate": False,
                }
            )

    return {
        "universe": universe_spec,
        "through": {
            "binding_id": cut_binding,
            "stage_index": k,
            "stage_name": cut_stage.name,
        },
        "computed_aliases": [c["alias"] for c in computed],
        "layers": layers,
        "gate_combine": doc.gate_combine,
    }


def _is_computed_alias(name: str, computed: list[dict]) -> bool:
    return any(c.get("alias") == name for c in computed)


def _collect_factors(stages: list[Stage]) -> dict[str, float]:
    """Blend weights from score/watch stages that are not parallel gates."""
    out: dict[str, float] = {}
    for stage in stages:
        if stage.mode not in (StageType.SCORE, StageType.WATCH):
            continue
        if stage.mode == StageType.SCORE and stage.as_gate:
            continue
        if getattr(stage, "computed_expr", None):
            continue
        for fw in stage.factors:
            out[fw.name] = fw.weight
    return out


def _factor_column(name: str) -> str:
    """Resolve a semantic factor; unknown names pass through as raw columns."""
    try:
        return resolve_factor(name).column
    except ValueError:
        return name


def _resolve_factor_columns(factors: dict[str, float]) -> dict[str, str]:
    """Resolve semantic factor names to L7 columns, validating registry hits."""
    return {name: _factor_column(name) for name in factors}


def _resolve_factor_weights(factors: dict[str, float]) -> dict[str, float]:
    """Resolve semantic factor names to physical L7 columns (for ``field_weights``).

    Unknown names pass through as raw columns (the author may reference a
    physical column directly, e.g. the legacy specs use ``minervini_score``).
    """
    return {_factor_column(name): weight for name, weight in factors.items()}


def _primary_sort_column(factors: dict[str, float]) -> str:
    """Pick the highest-weight factor's column as the universe ORDER BY field."""
    if not factors:
        return "overall_score"
    top = max(factors.items(), key=lambda kv: kv[1])[0]
    return _factor_column(top)


def _operand_columns(value: object) -> list[str]:
    """Physical columns referenced by an operand (recurses into formulas)."""
    if isinstance(value, str):
        return [value]
    if not isinstance(value, dict):
        return []
    operand_type = value.get("type")
    if operand_type == "col":
        name = value.get("name")
        return [str(name)] if name else []
    if operand_type == "formula":
        cols: list[str] = []
        for arg in value.get("args", []) or []:
            cols.extend(_operand_columns(arg))
        return cols
    return []


def _filter_columns(node: FilterNode) -> list[str]:
    """All columns referenced by a filter tree, including nested groups."""
    if isinstance(node, FilterNot):
        return _filter_columns(node.item)
    if isinstance(node, FilterGroup):
        cols: list[str] = []
        for child in node.conditions:
            cols.extend(_filter_columns(child))
        return cols
    cols = _operand_columns(node.left)
    if node.right_kind == "col":
        cols.extend(_operand_columns(node.right) or [str(node.right)])
    elif node.right_kind == "formula":
        cols.extend(_operand_columns(node.right))
    return cols


def _entry_trigger_type(trigger: object) -> str:
    """Extract EntryTrigger.type from a model or dict (never ``dict.type``)."""
    if isinstance(trigger, dict):
        raw = trigger.get("type")
    else:
        raw = getattr(trigger, "type", None)
    if hasattr(raw, "value"):
        raw = raw.value
    return str(raw or "").strip().lower()


def _build_select_columns(
    factors: dict[str, float],
    stages: list[Stage],
    extra: list[str] | None = None,
) -> list[str]:
    """Assemble the universe select list from factors, filters, triggers, and sizing."""
    cols: list[str] = list(_BASE_SELECT)
    cols.extend(_resolve_factor_columns(factors).values())
    for node in _combine_filters(stages):
        for col in _filter_columns(node):
            if col not in cols:
                cols.append(col)
    for stage in stages:
        if stage.selection and stage.selection.method == "top_n_per_sector":
            if "sector" not in cols:
                cols.append("sector")
        for trigger in stage.entry_triggers or []:
            extra_cols = _TRIGGER_SELECT.get(_entry_trigger_type(trigger), ())
            for col in extra_cols:
                if col not in cols:
                    cols.append(col)
    for col in extra or []:
        if col not in cols:
            cols.append(col)
    return list(dict.fromkeys(cols))


def _build_where(filters: list[FilterNode]) -> dict | None:
    """Build the universe_query_v1 ``where`` AST from filter trees.

    Multiple filter stages / top-level trees are AND-ed; nested ``FilterGroup``
    nodes recurse into ``all`` / ``any`` via ``_filter_node`` — the exact inverse
    of ``decompiler._decompile_where``.
    """
    if not filters:
        return None
    if len(filters) == 1:
        return _filter_node(filters[0])
    return {"type": "all", "items": [_filter_node(f) for f in filters]}


def _selection_params(selection: SelectionRule | None, default_n: int) -> dict:
    """Map a selection rule to alpha-model selection parameters."""
    if selection is None:
        return {"method": "top_n", "n": default_n}
    if selection.method == "top_n":
        return {"method": "top_n", "n": selection.n or default_n}
    if selection.method == "top_n_per_sector":
        return {
            "method": "top_n_per_sector",
            "sectors": selection.sectors,
            "per_sector": selection.per_sector,
        }
    return {"method": "threshold", "min_score": selection.min_score}


_SIZING_MODELS = {
    SizingPolicy.ATR_RISK: "VeraScreenerPortfolioConstructionModel",
    SizingPolicy.RISK_BUDGETED: "RiskBudgetedPortfolioConstructionModel",
    SizingPolicy.RISK_PARITY: "RiskParityPortfolioConstructionModel",
    SizingPolicy.CONFIDENCE_WEIGHTED: "ConfidenceWeightedPortfolioConstructionModel",
    SizingPolicy.EQUAL_WEIGHT: "EqualWeightingPortfolioConstructionModel",
}

_EXECUTION_MODELS = {
    "market_order": "VeraScreenerExecutionModel",
    "vwap": "VolumeWeightedAveragePriceExecutionModel",
    "std_dev": "StandardDeviationExecutionModel",
    "immediate": "ImmediateExecutionModel",
}

_UNIVERSE_MODELS = {
    UniverseSource.SCREENER: "VeraScreenerUniverseSelectionModel",
    UniverseSource.MANUAL: "ManualUniverseSelectionModel",
    UniverseSource.COMPOSITE: "CompositeUniverseSelectionModel",
}


def _sizing_model(sizing: SizingConfig, max_positions: int) -> tuple[str, dict]:
    """Sizing policy → (LEAN PCM class, params); ``model`` passthrough wins."""
    if sizing.model is not None:
        return sizing.model.type, sizing.model.parameters
    if sizing.policy == SizingPolicy.RISK_PARITY:
        params: dict = {"max_positions": sizing.max_positions or max_positions}
        if sizing.max_weight is not None:
            params["max_weight"] = sizing.max_weight
        if sizing.rebalance is not None:
            params["rebalance"] = sizing.rebalance
        return _SIZING_MODELS[sizing.policy], params
    if sizing.policy == SizingPolicy.RISK_BUDGETED:
        params: dict = {
            "max_positions": sizing.max_positions or max_positions,
            "risk_per_trade_pct": sizing.risk_per_trade_pct or 0.01,
            "max_position_weight": sizing.max_weight or 0.15,
        }
        if sizing.honor_insight_confidence is not None:
            params["honor_insight_confidence"] = bool(sizing.honor_insight_confidence)
        if sizing.allow_adds_on_invested is not None:
            params["allow_adds_on_invested"] = bool(sizing.allow_adds_on_invested)
        if sizing.default_stop_loss_pct is not None:
            params["default_stop_loss_pct"] = float(sizing.default_stop_loss_pct)
        if sizing.min_regime_fraction is not None:
            params["min_regime_fraction"] = float(sizing.min_regime_fraction)
        if sizing.regime_neutral_fraction is not None:
            params["regime_neutral_fraction"] = float(sizing.regime_neutral_fraction)
        if sizing.regime_bull_fraction is not None:
            params["regime_bull_fraction"] = float(sizing.regime_bull_fraction)
        if sizing.scaled_max_positions_floor is not None:
            params["scaled_max_positions_floor"] = int(sizing.scaled_max_positions_floor)
        if sizing.use_regime_scaling is not None:
            params["use_regime_scaling"] = bool(sizing.use_regime_scaling)
        if sizing.enable_displacement is not None:
            params["enable_displacement"] = bool(sizing.enable_displacement)
        if sizing.displacement_min_hold_days is not None:
            params["displacement_min_hold_days"] = int(sizing.displacement_min_hold_days)
        if sizing.displacement_max_incumbent_r is not None:
            params["displacement_max_incumbent_r"] = float(sizing.displacement_max_incumbent_r)
        if sizing.displacement_min_challenger_rs is not None:
            params["displacement_min_challenger_rs"] = float(sizing.displacement_min_challenger_rs)
        if sizing.displacement_min_challenger_screens is not None:
            params["displacement_min_challenger_screens"] = int(sizing.displacement_min_challenger_screens)
        if sizing.displacement_immune_rs is not None:
            params["displacement_immune_rs"] = float(sizing.displacement_immune_rs)
        if sizing.rebalance:
            if sizing.rebalance == "daily":
                params["rebalance_period_days"] = 1
            elif sizing.rebalance == "weekly":
                params["rebalance_period_days"] = 5
            elif sizing.rebalance == "monthly":
                params["rebalance_period_days"] = 21
            else:
                params["rebalance"] = sizing.rebalance
        if sizing.enable_surrogates is not None:
            params["enable_surrogates"] = bool(sizing.enable_surrogates)
        if sizing.surrogate_sizing_mode is not None:
            params["surrogate_sizing_mode"] = str(sizing.surrogate_sizing_mode)
        if sizing.prefer_capital_efficient_surrogates is not None:
            params["prefer_capital_efficient_surrogates"] = bool(sizing.prefer_capital_efficient_surrogates)
        if sizing.min_surrogate_adv is not None:
            params["min_surrogate_adv"] = float(sizing.min_surrogate_adv)
        return _SIZING_MODELS[sizing.policy], params
    if sizing.policy == SizingPolicy.CONFIDENCE_WEIGHTED:
        params = {}
        if sizing.max_weight is not None:
            params["max_weight"] = sizing.max_weight
        return _SIZING_MODELS[sizing.policy], params
    if sizing.policy == SizingPolicy.EQUAL_WEIGHT:
        return _SIZING_MODELS[sizing.policy], {}
    return _SIZING_MODELS[SizingPolicy.ATR_RISK], {
        "max_positions": max_positions,
        "max_weight": sizing.max_weight if sizing.max_weight is not None else 0.10,
        "min_weight": sizing.min_weight if sizing.min_weight is not None else 0.05,
        "target_atr_risk": sizing.target_atr_risk if sizing.target_atr_risk is not None else 0.004,
    }


def _risk_rule_model(rule: RiskRule) -> tuple[str, dict]:
    if rule.type == RiskRuleType.PROGRESSIVE:
        params: dict = {}
        if rule.take_profit_r is not None:
            params["take_profit_r"] = rule.take_profit_r
        if rule.trailing_stop_pct is not None:
            params["trailing_stop_pct"] = rule.trailing_stop_pct
        if rule.max_holding_days is not None:
            params["max_holding_days"] = rule.max_holding_days
        return "SwingProgressiveRiskManagementModel", params
    if rule.type == RiskRuleType.TRAILING:
        return "TrailingStopRiskManagementModel", {"maximum_drawdown_percent": rule.maximum_drawdown_percent or 0.05}
    if rule.type == RiskRuleType.MAX_DRAWDOWN:
        return "MaximumDrawdownPercentPerSecurity", {"maximum_drawdown_percent": rule.maximum_drawdown_percent or 0.05}
    return "MaximumSectorExposureRiskManagementModel", {"maximum_sector_exposure": rule.maximum_sector_exposure or 0.25}


def _risk_model(doc: PipelineDocument, exit_stage: Stage | None) -> tuple[str, dict]:
    """Risk stack → (LEAN risk class, params); ``model`` passthrough wins."""
    if doc.risk.model is not None:
        return doc.risk.model.type, doc.risk.model.parameters
    rules = doc.risk.rules
    if not rules and exit_stage is not None:
        params: dict = {"take_profit_r": 2.5, "trailing_stop_pct": 0.15}
        if exit_stage.tranches:
            t1 = exit_stage.tranches[0]
            params["take_profit_r"] = t1.trigger_r
            params["tranche1_sell_pct"] = t1.sell_pct
            # Honesty: persist every swing tranche (not only T1)
            params["tranches"] = [
                t.model_dump(mode="json", exclude_none=True) for t in exit_stage.tranches
            ]
        if exit_stage.max_hold_days is not None:
            params["max_holding_days"] = exit_stage.max_hold_days
        if exit_stage.trailing_stop_pct is not None:
            params["trailing_stop_pct"] = exit_stage.trailing_stop_pct
        if exit_stage.atr_stop_multiplier is not None:
            params["atr_stop_multiplier"] = exit_stage.atr_stop_multiplier
        if exit_stage.max_stop_loss_pct is not None:
            params["max_stop_loss_pct"] = exit_stage.max_stop_loss_pct
        if exit_stage.use_atr_stops is not None:
            params["use_atr_stops"] = exit_stage.use_atr_stops
        if exit_stage.breakeven_time_stop_days is not None:
            params["breakeven_time_stop_days"] = exit_stage.breakeven_time_stop_days
        if exit_stage.max_single_weight is not None:
            params["max_single_weight"] = exit_stage.max_single_weight
        if exit_stage.breakeven_r_trigger is not None:
            params["breakeven_r_trigger"] = exit_stage.breakeven_r_trigger
        if doc.risk.time_stop_skip_if:
            params["time_stop_skip_if"] = dict(doc.risk.time_stop_skip_if)
        return "SwingProgressiveRiskManagementModel", params
    if len(rules) == 1:
        return _risk_rule_model(rules[0])
    if len(rules) > 1:
        models = []
        for r in rules:
            t, p = _risk_rule_model(r)
            models.append({"Type": t, "Parameters": p})
        return "CompositeRiskManagementModel", {"models": models}
    if doc.risk.time_stop_skip_if:
        return "SwingProgressiveRiskManagementModel", {
            "time_stop_skip_if": dict(doc.risk.time_stop_skip_if),
        }
    return "NullRiskManagementModel", {}


def _leaf_col_names(node: FilterNode | dict) -> set[str]:
    """Collect column names referenced in a filter tree / where AST."""
    out: set[str] = set()
    if isinstance(node, FilterNot):
        return _leaf_col_names(node.item)
    if isinstance(node, FilterGroup):
        for child in node.conditions:
            out |= _leaf_col_names(child)
        return out
    if isinstance(node, FilterCondition):
        left = node.left
        if isinstance(left, str):
            out.add(left)
        elif isinstance(left, dict) and left.get("type") == "col":
            out.add(str(left.get("name", "")))
        if node.right_kind == "col":
            if isinstance(node.right, str):
                out.add(node.right)
            elif isinstance(node.right, dict) and node.right.get("type") == "col":
                out.add(str(node.right.get("name", "")))
        return out
    if isinstance(node, dict):
        t = node.get("type")
        if t in ("all", "any"):
            for child in node.get("items") or []:
                out |= _leaf_col_names(child)
        elif t == "not":
            inner = node.get("item")
            if inner is not None:
                out |= _leaf_col_names(inner)
        elif t in ("gt", "gte", "lt", "lte", "eq", "neq"):
            for side in ("left", "right"):
                op = node.get(side)
                if isinstance(op, dict):
                    out |= _leaf_col_names(op)
        elif t == "col":
            name = node.get("name")
            if name:
                out.add(str(name))
        elif t == "formula":
            for arg in node.get("args") or []:
                if isinstance(arg, dict):
                    out |= _leaf_col_names(arg)
        return out
    return out


def _normalize_screen_root(screen: list[FilterNode]) -> FilterNode | None:
    """Single root group, or AND of a bare sibling list (no implicit named-OR)."""
    if not screen:
        return None
    if len(screen) == 1:
        return screen[0]
    return FilterGroup(logic="and", conditions=list(screen))


def _named_from_tree(root: FilterNode | None) -> tuple[dict | None, dict[str, dict]]:
    """Walk named groups for Alpha flags. Unnamed tree is the membership AST."""
    named: dict[str, dict] = {}
    membership: dict | None = None

    def walk(node: FilterNode) -> None:
        nonlocal membership
        if isinstance(node, FilterNot):
            # a negated subtree can still hold the named groups being collected
            walk(node.item)
            return
        if not isinstance(node, FilterGroup):
            return
        compiled = _filter_node(node)
        if node.name == "membership":
            membership = compiled
        elif node.name:
            named[str(node.name)] = compiled
        for child in node.conditions:
            walk(child)

    if root is not None:
        walk(root)
    if membership is None and not named:
        membership = _filter_node(root) if root is not None else None
    return membership, named


def _legacy_filter_screen(stages: list[Stage]) -> list[FilterNode]:
    """Filter-stage trees when universe.screen is empty (momentum-style presets)."""
    out: list[FilterNode] = []
    for stage in stages:
        if stage.mode != StageType.FILTER:
            continue
        if stage.name == "Universe Hygiene":
            continue
        out.extend(stage.filters)
    return out


def _screen_from_doc(
    doc: PipelineDocument,
) -> tuple[dict | None, dict | None, dict[str, dict]]:
    """Full screen WHERE + derived membership / named_groups for Alpha flags."""
    screen = list(doc.universe.screen or [])
    if not screen:
        screen = _legacy_filter_screen(doc.stages)
    root = _normalize_screen_root(screen)
    tree = _filter_node(root) if root is not None else None
    membership, named = _named_from_tree(root)
    return tree, membership, named


def _and_where_nodes(*nodes: dict | None) -> dict:
    """AND non-empty where ASTs into one universe_query_v1 node."""
    items: list[dict] = []
    for node in nodes:
        if not node:
            continue
        if node.get("type") == "all" and not node.get("items"):
            continue
        items.append(node)
    if not items:
        return {"type": "all", "items": []}
    if len(items) == 1:
        return items[0]
    return {"type": "all", "items": items}


def _or_where_nodes(*nodes: dict | None) -> dict:
    """OR non-empty where ASTs (membership OR named screen groups)."""
    items: list[dict] = []
    for node in nodes:
        if not node:
            continue
        if node.get("type") == "any" and not node.get("items"):
            continue
        items.append(node)
    if not items:
        return {"type": "any", "items": []}
    if len(items) == 1:
        return items[0]
    return {"type": "any", "items": items}


def _risk_stack_has_hedge(risk_type: str, risk_params: dict) -> bool:
    if risk_type == "VeraHedgeModel":
        return True
    if risk_type == "CompositeRiskManagementModel":
        for m in risk_params.get("models") or []:
            if isinstance(m, dict) and m.get("Type") == "VeraHedgeModel":
                return True
    return False


def _alpha_card_stages(stages: list[Stage]) -> list[dict]:
    """Alpha-owned stages only (filter/score/signal/confirm/watch/pyramid)."""
    alpha_modes = {
        StageType.FILTER,
        StageType.SCORE,
        StageType.SIGNAL,
        StageType.CONFIRM,
        StageType.WATCH,
        StageType.PYRAMID,
    }
    out: list[dict] = []
    for stage in stages:
        if stage.mode not in alpha_modes:
            continue
        if stage.name == "Universe Hygiene":
            continue
        out.append(stage.model_dump(mode="json", exclude_none=True))
    return out


def _build_data_sources(
    *,
    select_cols: list[str],
    regime_gate_payload: dict | None,
) -> list[dict]:
    """Emit VeraBase.DataSources catalog (equity + optional regime + bars)."""
    from sigmarail.features.ir.l7_from import resolve_joins_for_columns

    sources: list[dict] = [
        {
            "name": "equity",
            "Type": "VeraDailyScreener",
            "table": "screener_price_tech_daily",
            "grain": "ticker_date",
            "as_of": "T-1",
            "joins": resolve_joins_for_columns(set(select_cols)),
            "select": list(select_cols),
        },
        {
            "name": "bars",
            "Type": "ClickHouseDataProvider",
            "table": "daily_metrics",
            "grain": "ticker_date",
            "select": ["ticker", "date", "open", "high", "low", "close", "volume"],
        },
    ]
    if regime_gate_payload:
        weights = regime_gate_payload.get("signal_weights") or {}
        regime_select = list(weights.keys()) or [
            "s_ma200_macro",
            "s_breadth200",
            "s_breadth50",
        ]
        score = {
            k: regime_gate_payload[k]
            for k in (
                "threshold",
                "signal_weights",
                "confirm_on_days",
                "confirm_off_days",
                "missing_action",
                "min_allocation_fraction",
                "expression",
            )
            if k in regime_gate_payload
        }
        sources.insert(
            1,
            {
                "name": "regime",
                "Type": "VeraMarketRegimeSignalsDaily",
                "table": str(
                    regime_gate_payload.get("source") or "regime_signals_canonical"
                ),
                "grain": "session",
                "as_of": "T-1",
                "select": regime_select,
                "uses": list(regime_gate_payload.get("uses") or []),
                "score": score,
            },
        )
    return sources


def _universe_model(doc: PipelineDocument) -> tuple[str, dict]:
    """Universe source → (LEAN universe class, params); ``model`` passthrough wins."""
    if doc.universe.model is not None:
        return doc.universe.model.type, doc.universe.model.parameters
    if doc.universe.source == UniverseSource.MANUAL:
        return "ManualUniverseSelectionModel", {"symbols": doc.universe.symbols}
    return _UNIVERSE_MODELS[doc.universe.source], {}


def _execution_model(execution: ExecutionConfig) -> tuple[str, dict]:
    """Execution mode → (LEAN execution class, params); ``model`` passthrough wins."""
    if execution.model is not None:
        return execution.model.type, execution.model.parameters
    type_id = _EXECUTION_MODELS.get(execution.type, "VeraScreenerExecutionModel")
    params: dict = {}
    if type_id == "VeraScreenerExecutionModel":
        params["fill_session"] = execution.fill_session or "moo"
    return type_id, params


def _bound_manual_store_spec(spec: dict, symbols: list[str]) -> dict:
    """Bound the ``VeraBase.Universe`` store query to a fixed symbol list.

    A fixed-symbol (manual) book still needs its bars pre-hydrated and its
    regime/metrics loaded through the store, so the store universe query is
    filtered to exactly those symbols. Unlike the old ``_lower_manual_to_store``
    this does **not** rewrite the framework slots: a manual book keeps
    ``ManualUniverseSelectionModel`` + non-store-backed execution so LEAN runs
    the normal framework path (alpha → PCM → execution) and rebalances to target
    weights — which is what lets fixed sleeves coexist with dynamic screens.
    """
    if not symbols:
        raise ValueError("manual universe requires at least one symbol")
    uni = spec.setdefault("VeraBase", {}).setdefault("Universe", {})
    uni["where"] = {
        "type": "any",
        "items": [
            {
                "type": "eq",
                "left": {"type": "col", "name": "ticker"},
                "right": {"type": "lit", "value": sym},
            }
            for sym in symbols
        ],
    }
    uni["select"] = ["ticker", "close", "closeadj", "atr_14_pct"]
    uni["order_by"] = [{"field": "close", "direction": "desc"}]
    uni["limit_per_day"] = max(len(symbols), int(uni.get("limit_per_day") or 101))
    return spec


def compile_pipeline(doc: PipelineDocument) -> dict:
    """Compile a PipelineDocument into a VeraLabV1 JSON dict.

    Five-slot honesty (C-STRATEGY-PIPELINE-SSOT amend):
    - Universe owns the screen tree; membership / named_groups are derived flags
    - Pushdown WHERE is that tree (no hygiene AND)
    - Alpha Parameters hold stages / gates / setup_where only
    - Regime lives on DataSources (+ optional VeraBase.Regime score); no regime-gate blob
    """
    stages = doc.stages

    factors = _collect_factors(stages)
    select_cols = _build_select_columns(factors, stages, extra=doc.universe.select)
    for node in doc.universe.screen or []:
        for col in _filter_columns(node):
            if col and col not in select_cols:
                select_cols.append(col)
    screen_where, membership_where, named_groups = _screen_from_doc(doc)
    setup_where = _build_where(_signal_filters(stages))
    gates = _gates_from_stages(stages)
    computed = _computed_from_stages(
        stages, gate_combine=doc.gate_combine, setup_where=setup_where
    )
    computed_aliases = {c["alias"] for c in computed}
    pushdown_where = screen_where
    for gate in gates:
        for field in list(gate.get("score_fields") or []) + list(
            gate.get("optional_score_fields") or []
        ) + list((gate.get("optional_min") or {}).keys()):
            if field not in select_cols and field not in computed_aliases:
                select_cols.append(field)
            companion = {
                "eps_ny_rev_pct_90d": "eps_ny_n",
                "eps_nq_rev_pct_90d": "eps_nq_n",
                "eps_cq_rev_pct_90d": "eps_cq_n",
                "eps_cy_rev_pct_90d": "eps_cy_n",
            }.get(field)
            if companion and companion not in select_cols:
                select_cols.append(companion)
        gate_where = gate.get("where")
        if gate_where:
            for col in _leaf_col_names(gate_where):
                if col and col not in select_cols and col not in computed_aliases:
                    select_cols.append(col)
    for extra_where in (screen_where, membership_where, *named_groups.values()):
        if extra_where:
            for col in _leaf_col_names(extra_where):
                if col and col not in select_cols and col not in computed_aliases:
                    select_cols.append(col)
    if setup_where:
        for col in _leaf_col_names(setup_where):
            if col and col not in select_cols and col not in computed_aliases:
                select_cols.append(col)
    for c in computed:
        payload = c.get("where") or c.get("expr") or {}
        for col in _leaf_col_names(payload):
            if col and col not in select_cols and col not in computed_aliases:
                select_cols.append(col)
    for col in (
        "sma200_lag_30d",
        "eps_ny_rev_pct_90d",
        "eps_nq_rev_pct_90d",
        "eps_last_surprise_pct",
        "eps_cq_mean",
        "eps_ny_mean",
    ):
        blob = json.dumps(
            {
                "setup": setup_where,
                "screen": screen_where,
                "membership": membership_where,
                "named_groups": named_groups,
                "gates": gates,
            }
        )
        if col not in select_cols and col in blob:
            select_cols.append(col)

    sort_col = _primary_sort_column(factors)
    if sort_col not in select_cols and sort_col not in computed_aliases:
        select_cols.append(sort_col)

    signal_stages = [s for s in stages if s.mode == StageType.SIGNAL]
    signal_stage = signal_stages[0] if signal_stages else None
    blend_score = next(
        (
            s
            for s in stages
            if s.mode == StageType.SCORE
            and not s.as_gate
            and not getattr(s, "computed_expr", None)
        ),
        None,
    )
    score_stage = blend_score or next(
        (s for s in stages if s.mode == StageType.SCORE),
        None,
    )
    pyramid_stage = next((s for s in stages if s.mode == StageType.PYRAMID), None)
    exit_stage = next((s for s in stages if s.mode == StageType.EXIT), None)

    max_positions = doc.risk.max_positions
    for s in signal_stages:
        if s.max_positions:
            max_positions = s.max_positions
    if max_positions is None:
        max_positions = 10

    if pyramid_stage is not None or gates or doc.gate_combine or doc.min_screens:
        alpha_type = "VeraPyramidAlphaModel"
    elif len(factors) > 1:
        alpha_type = "VeraCompositeAlphaModel"
    else:
        alpha_type = "VeraScreenerAlphaModel"

    cb_drawdown = 0.10
    cb_pause = 20
    if doc.risk.circuit_breaker:
        cb_drawdown = float(doc.risk.circuit_breaker.get("drawdown", 0.10))
        cb_pause = int(doc.risk.circuit_breaker.get("pause_days", 20))

    selection = (
        (signal_stage.selection if signal_stage else None)
        or (score_stage.selection if score_stage else None)
    )

    regime_gate_payload: dict | None = None
    regime_uses: list[str] = []
    gate = doc.regime_gate or doc.risk.regime_gate
    if gate:
        if hasattr(gate, "model_dump"):
            regime_gate_payload = gate.model_dump(mode="json", exclude_none=True)
        else:
            regime_gate_payload = dict(gate)
        regime_uses = list(regime_gate_payload.get("uses") or [])

    alpha_params: dict = {
        "max_positions": max_positions,
        "stop_loss_pct": 0.08,
        "stop_cooldown_days": 10,
        "stages": _alpha_card_stages(stages),
        "uses": [u for u in regime_uses if u == "block_new_longs"],
        "gates": gates,
    }
    if signal_stage is not None and signal_stage.stop_cooldown_days is not None:
        alpha_params["stop_cooldown_days"] = int(signal_stage.stop_cooldown_days)
    if setup_where:
        alpha_params["setup_where"] = setup_where
    merged_triggers: list = []
    merged_stop = None
    for s in signal_stages:
        merged_triggers.extend(s.entry_triggers or [])
        if s.stop_loss is not None:
            merged_stop = s.stop_loss
    if merged_triggers:
        alpha_params["entry_triggers"] = [
            t.model_dump(exclude_none=True) for t in merged_triggers
        ]
    if merged_stop is not None:
        sl = merged_stop.model_dump(exclude_none=True)
        alpha_params["stop_loss"] = sl
        if sl.get("type") == "fixed_pct" and sl.get("pct") is not None:
            alpha_params["stop_loss_pct"] = sl["pct"]
        elif sl.get("type") == "atr":
            # ATR stop lives on stop_loss; do not flatten a percent default (8%).
            alpha_params["stop_loss_pct"] = 0
    if doc.gate_combine is not None:
        alpha_params["gate_combine"] = doc.gate_combine
    if doc.min_screens is not None:
        alpha_params["min_screens"] = doc.min_screens
    bindings = _resolve_bindings(doc, computed_aliases)
    if bindings is not None:

        def _harvest_select_col(col: str) -> None:
            # Runtime Risk/Alpha row fields (e.g. __position.price) are not L7 select.
            if not col or col.startswith("__"):
                return
            if col not in select_cols and col not in computed_aliases:
                select_cols.append(col)

        for slot in (
            bindings.alpha_confidence,
            bindings.alpha_direction,
            bindings.alpha_magnitude,
            bindings.alpha_weight,
            bindings.pcm_scale,
        ):
            if slot is not None and slot.expr is not None:
                for col in _leaf_col_names(slot.expr):
                    _harvest_select_col(col)
            if slot is not None and slot.where is not None:
                for col in _leaf_col_names(slot.where):
                    _harvest_select_col(col)
        for slot in (
            bindings.alpha_eligibility,
            bindings.alpha_setup,
            bindings.pcm_allow_entry,
            bindings.risk_skip_time_stop,
            bindings.risk_allow_pyramid_add,
        ):
            if slot is not None and slot.where is not None:
                for col in _leaf_col_names(slot.where):
                    _harvest_select_col(col)
    if bindings is None and (doc.gate_combine or "").lower() == "count" and "screens_hit" in computed_aliases:
        alpha_params["row_rank"] = {
            "by": ["screens_hit", sort_col],
            "min": {"screens_hit": int(doc.min_screens or 1)},
        }
        if "setup_pass" in computed_aliases:
            alpha_params["setup_col"] = "setup_pass"
        alpha_params["row_scale_denom"] = 5
    if alpha_type == "VeraScreenerAlphaModel":
        alpha_params["circuit_drawdown_threshold"] = cb_drawdown
        alpha_params["circuit_pause_days"] = cb_pause
    elif alpha_type == "VeraCompositeAlphaModel":
        alpha_params["circuit_drawdown_threshold"] = cb_drawdown
        alpha_params["circuit_pause_days"] = cb_pause
        alpha_params["field_weights"] = _resolve_factor_weights(factors)
    else:
        alpha_params["field_weights"] = _resolve_factor_weights(factors)
        alpha_params["selection"] = _selection_params(selection, max_positions)
        # phases / add_trigger_pct → PCM (not Alpha)

    if alpha_type == "VeraPyramidAlphaModel":
        alpha_params.pop("membership", None)
        alpha_params.pop("named_groups", None)

    if doc.alpha is not None:
        alpha_type = doc.alpha.type
        alpha_params = dict(doc.alpha.parameters)
        alpha_params.pop("membership", None)
        alpha_params.pop("named_groups", None)
        alpha_params.setdefault("stages", _alpha_card_stages(stages))
        alpha_params.setdefault("gates", _gates_from_stages(stages))
        if setup_where:
            alpha_params.setdefault("setup_where", setup_where)
        alpha_params.setdefault(
            "uses",
            [u for u in regime_uses if u == "block_new_longs"],
        )
        if doc.gate_combine is not None:
            alpha_params.setdefault("gate_combine", doc.gate_combine)
        if doc.min_screens is not None:
            alpha_params.setdefault("min_screens", doc.min_screens)

    if doc.max_entry_atr_pct is not None:
        alpha_params["max_entry_atr_pct"] = float(doc.max_entry_atr_pct)

    pcm_type, pcm_params = _sizing_model(doc.sizing, max_positions)
    pcm_params = dict(pcm_params)
    # Pyramid scale-in requires RiskBudgeted PCM (phases / add_trigger live there).
    if pyramid_stage is not None and pcm_type != "RiskBudgetedPortfolioConstructionModel":
        pcm_type = "RiskBudgetedPortfolioConstructionModel"
        pcm_params = {
            "risk_per_trade_pct": float(doc.sizing.risk_per_trade_pct or 0.005),
            "max_position_weight": float(doc.sizing.max_weight or 0.25),
            "max_positions": int(max_positions),
            "default_stop_loss_pct": float(doc.sizing.default_stop_loss_pct or 0.05),
            "honor_insight_confidence": bool(
                doc.sizing.honor_insight_confidence
                if doc.sizing.honor_insight_confidence is not None
                else True
            ),
            "allow_adds_on_invested": bool(
                doc.sizing.allow_adds_on_invested
                if doc.sizing.allow_adds_on_invested is not None
                else True
            ),
        }
    if pcm_type != "RiskBudgetedPortfolioConstructionModel":
        pcm_params.setdefault("hold_policy", "retain_if_invested")
        pcm_params.setdefault("max_total_exposure", 0.95)
        pcm_params.setdefault("exit_when_no_bars", True)
    if pcm_type == "RiskBudgetedPortfolioConstructionModel":
        if doc.sizing.use_regime_scaling is None and regime_gate_payload:
            pcm_params["use_regime_scaling"] = "scale_exposure" in regime_uses
        if doc.sizing.min_regime_fraction is not None:
            pcm_params.setdefault("min_regime_fraction", float(doc.sizing.min_regime_fraction))
        if doc.sizing.regime_neutral_fraction is not None:
            pcm_params["regime_neutral_fraction"] = float(doc.sizing.regime_neutral_fraction)
        if doc.sizing.regime_bull_fraction is not None:
            pcm_params["regime_bull_fraction"] = float(doc.sizing.regime_bull_fraction)
        if doc.sizing.scaled_max_positions_floor is not None:
            pcm_params["scaled_max_positions_floor"] = int(doc.sizing.scaled_max_positions_floor)
        if doc.sizing.enable_displacement is not None:
            pcm_params["enable_displacement"] = bool(doc.sizing.enable_displacement)
        if doc.sizing.displacement_min_hold_days is not None:
            pcm_params["displacement_min_hold_days"] = int(doc.sizing.displacement_min_hold_days)
        if doc.sizing.displacement_max_incumbent_r is not None:
            pcm_params["displacement_max_incumbent_r"] = float(doc.sizing.displacement_max_incumbent_r)
        if doc.sizing.displacement_min_challenger_rs is not None:
            pcm_params["displacement_min_challenger_rs"] = float(doc.sizing.displacement_min_challenger_rs)
        if doc.sizing.displacement_min_challenger_screens is not None:
            pcm_params["displacement_min_challenger_screens"] = int(doc.sizing.displacement_min_challenger_screens)
        if doc.sizing.displacement_immune_rs is not None:
            pcm_params["displacement_immune_rs"] = float(doc.sizing.displacement_immune_rs)
        if doc.sizing.rebalance:
            if doc.sizing.rebalance == "daily":
                pcm_params["rebalance_period_days"] = 1
            elif doc.sizing.rebalance == "weekly":
                pcm_params["rebalance_period_days"] = 5
            elif doc.sizing.rebalance == "monthly":
                pcm_params["rebalance_period_days"] = 21
            else:
                pcm_params["rebalance"] = doc.sizing.rebalance
        if doc.sizing.enable_surrogates is not None:
            pcm_params["enable_surrogates"] = bool(doc.sizing.enable_surrogates)
        if doc.sizing.surrogate_sizing_mode is not None:
            pcm_params["surrogate_sizing_mode"] = str(doc.sizing.surrogate_sizing_mode)
        if doc.sizing.prefer_capital_efficient_surrogates is not None:
            pcm_params["prefer_capital_efficient_surrogates"] = bool(doc.sizing.prefer_capital_efficient_surrogates)
        if doc.sizing.min_surrogate_adv is not None:
            pcm_params["min_surrogate_adv"] = float(doc.sizing.min_surrogate_adv)
        if "scaled_max_positions_floor" not in pcm_params:
            pcm_params["scaled_max_positions_floor"] = (
                0 if "block_new_longs" in regime_uses else 2
            )
        # RiskBudgeted PCM sizes via Insight.Confidence or pcm_scale_expr — never row_scale_col.
        pcm_params.pop("row_scale_col", None)
        if pyramid_stage is not None:
            pcm_params["phases"] = [p.model_dump() for p in pyramid_stage.phases]
            if pyramid_stage.add_trigger_pct is not None:
                pcm_params["add_trigger_pct"] = float(pyramid_stage.add_trigger_pct)
            else:
                pcm_params["add_trigger_pct"] = 0.02
        pcm_params["uses"] = [
            u for u in regime_uses if u in ("skip_pyramid_adds", "scale_exposure")
        ]
        # C-FW-RULES unified pass: authored rule table + book/operand ASTs
        # pass through verbatim — the runtime owns their semantics.
        if doc.sizing.rules:
            pcm_params["rules"] = [_prune_nulls(r) for r in doc.sizing.rules]
        if doc.sizing.size_expr is not None:
            pcm_params["size_expr"] = dict(doc.sizing.size_expr)
        if doc.sizing.scale_expr is not None:
            pcm_params["scale_expr"] = dict(doc.sizing.scale_expr)
        if doc.sizing.slots_expr is not None:
            pcm_params["slots_expr"] = dict(doc.sizing.slots_expr)
        if doc.sizing.order_expr is not None:
            pcm_params["order_expr"] = dict(doc.sizing.order_expr)

    risk_type, risk_params = _risk_model(doc, exit_stage)
    if (
        risk_type == "SwingProgressiveRiskManagementModel"
        and exit_stage is not None
    ):
        if exit_stage.rules:
            risk_params["rules"] = [_prune_nulls(r) for r in exit_stage.rules]
        if exit_stage.init_stop is not None:
            risk_params["init_stop"] = dict(exit_stage.init_stop)
    risk_params = dict(risk_params)
    if bindings is not None:
        _apply_bindings_to_slots(
            bindings,
            alpha_params=alpha_params,
            pcm_params=pcm_params,
            risk_params=risk_params,
            sort_col=sort_col,
            min_screens=int(doc.min_screens or 1),
        )
    if doc.policy_overrides:
        ov_payload = [
            {
                "id": ov.id,
                "label": ov.label,
                "when": ov.when.where,
                "set": dict(ov.set),
            }
            for ov in doc.policy_overrides
        ]
        pcm_params["policy_overrides"] = ov_payload
        risk_params["policy_overrides"] = ov_payload
    universe_type, universe_params = _universe_model(doc)
    universe_params = dict(universe_params)
    universe_params["screen"] = screen_where or {"type": "all", "items": []}
    universe_params["membership"] = membership_where or {"type": "all", "items": []}
    universe_params["named_groups"] = named_groups
    exec_type, exec_params = _execution_model(doc.execution)

    if doc.universe.source == UniverseSource.MANUAL and exec_type == "VeraScreenerExecutionModel":
        exec_type = "ImmediateExecutionModel"
        exec_params = {}

    if "hedge" in regime_uses and not _risk_stack_has_hedge(risk_type, risk_params):
        raise ValueError(
            "hedge use requires VeraHedgeModel in RiskManagement "
            "(CompositeRiskManagementModel with VeraHedgeModel, or Type=VeraHedgeModel)"
        )

    # When hedge instruments are authored, put VeraHedgeModel in the Risk stack
    # (honesty) instead of a dead AlgorithmParameters hedge-instruments string.
    if (
        doc.hedge is not None
        and doc.hedge.instruments
        and not _risk_stack_has_hedge(risk_type, risk_params)
        and "hedge" not in regime_uses
    ):
        hedge_params = {
            "instruments": [
                i.model_dump(mode="json", exclude_none=True) for i in doc.hedge.instruments
            ]
        }
        if risk_type in ("NullRiskManagementModel",):
            risk_type, risk_params = "VeraHedgeModel", hedge_params
        else:
            primary_type, primary_params = risk_type, dict(risk_params)
            risk_type = "CompositeRiskManagementModel"
            risk_params = {
                "models": [
                    {"Type": primary_type, "Parameters": primary_params},
                    {"Type": "VeraHedgeModel", "Parameters": hedge_params},
                ]
            }

    # Only pass AlgorithmParameters that runtime slots still read (no regime-gate blob).
    algo_params: dict = {}
    if doc.risk.circuit_breaker:
        cb = doc.risk.circuit_breaker
        algo_params["circuit_drawdown_threshold"] = str(cb.get("drawdown", 0.10))
        algo_params["circuit_pause_days"] = str(cb.get("pause_days", 20))
    stage_docs: list[dict] = []
    for stage in stages:
        dumped = stage.documentation.model_dump(mode="json", exclude_none=True)
        if any(dumped.values()):
            stage_docs.append(
                {
                    "mode": stage.mode.value,
                    "name": stage.name,
                    "documentation": dumped,
                }
            )
    if stage_docs:
        algo_params["stage-documentation"] = json.dumps(stage_docs)

    limit_per_day = 101
    if doc.universe.limit_per_day:
        limit_per_day = min(5000, int(doc.universe.limit_per_day))
    else:
        for s in stages:
            if s.mode == StageType.FILTER and s.max_candidates:
                limit_per_day = min(500, s.max_candidates)
                break

    order_by = _universe_rank_order_by(
        bindings=bindings,
        sort_col=sort_col,
        select_cols=select_cols,
        computed_aliases=set(computed_aliases),
        gate_combine=doc.gate_combine,
        bool_gate_aliases=_bool_gate_aliases(stages),
    )
    post_where = _universe_post_where(
        bindings=bindings,
        stages=stages,
        computed_aliases=set(computed_aliases),
        min_screens=int(doc.min_screens or 1),
        gate_combine=doc.gate_combine,
    )

    clean_select_cols = [
        c for c in select_cols
        if c not in computed_aliases and c not in ("hit_count", "screens_hit", "screens_hit_w")
    ]

    from sigmarail.features.ir.l7_from import resolve_joins_for_columns

    universe_spec: dict = {
        "version": 2,
        "spine": "screener_price_tech_daily",
        "joins": resolve_joins_for_columns(set(clean_select_cols)),
        "select": clean_select_cols,
        "order_by": order_by,
        "limit_per_day": limit_per_day,
        "where": pushdown_where or {"type": "all", "items": []},
    }
    if computed:
        universe_spec["computed"] = computed
    if post_where is not None:
        universe_spec["post_where"] = post_where

    framework = {
        "UniverseSelection": {"Type": universe_type, "Parameters": universe_params},
        "Alpha": {"Type": alpha_type, "Parameters": alpha_params},
        "PortfolioConstruction": {"Type": pcm_type, "Parameters": pcm_params},
        "Execution": {"Type": exec_type, "Parameters": exec_params},
        "RiskManagement": {"Type": risk_type, "Parameters": risk_params},
    }

    out: dict = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "title": doc.strategy_name,
        "Framework": framework,
        "AlgorithmParameters": algo_params,
    }
    vera_base: dict = {
        "Universe": universe_spec,
        "DataSources": _build_data_sources(
            select_cols=select_cols,
            regime_gate_payload=regime_gate_payload,
        ),
    }
    # Score document only (not a second strategy copy). Pipeline not persisted as SSOT.
    if regime_gate_payload:
        vera_base["Regime"] = {
            k: v
            for k, v in regime_gate_payload.items()
            if k != "uses"  # uses live on DataSources.regime
        }
    out["VeraBase"] = vera_base
    if doc.universe.source == UniverseSource.MANUAL:
        _bound_manual_store_spec(out, doc.universe.symbols or [])
    return out


def _has_dynamic_allocation(policy: AllocationPolicy) -> bool:
    """True when the allocation policy is non-default (needs the ensemble path)."""
    return (
        policy.base != "weights"
        or policy.regime is not None
        or policy.performance is not None
        or policy.vol_target is not None
    )


def _rebalance_days(cadence: str) -> int:
    """Map a rebalance cadence name to days (for the regime-weighted PCM)."""
    return {"daily": 1, "weekly": 7, "monthly": 30}.get((cadence or "weekly").lower(), 7)


def compile_portfolio(portfolio: PortfolioDocument) -> dict:
    """Compile a PortfolioDocument into a VeraLabV1 JSON dict.

    - A single-leg portfolio with default allocation compiles exactly like
      ``compile_pipeline`` on that leg (preserving the single-strategy shape).
    - N>1 legs (or a dynamic allocation policy) compile to a ``CompositeAlphaModel``
      ensemble + ``CompositeRiskManagementModel`` + an allocation-aware PCM.

    Regime / performance / volatility overlays are runtime gaps (plan §5): the
    compiler emits the *base* allocation and records the overlays in
    ``AlgorithmParameters`` for the (future) runtime allocator.
    """
    legs = portfolio.legs
    alloc = portfolio.allocation
    if len(legs) == 1 and not _has_dynamic_allocation(alloc):
        return compile_pipeline(legs[0])

    compiled = [compile_pipeline(leg) for leg in legs]
    alphas = [
        {"Type": c["Framework"]["Alpha"]["Type"], "Parameters": c["Framework"]["Alpha"]["Parameters"]}
        for c in compiled
    ]
    risks = [
        {"Type": c["Framework"]["RiskManagement"]["Type"], "Parameters": c["Framework"]["RiskManagement"]["Parameters"]}
        for c in compiled
        if c["Framework"]["RiskManagement"]["Type"] != "NullRiskManagementModel"
    ]
    risk_type, risk_params = "NullRiskManagementModel", {}
    if len(risks) == 1:
        risk_type, risk_params = risks[0]["Type"], risks[0]["Parameters"]
    elif len(risks) > 1:
        risk_type, risk_params = "CompositeRiskManagementModel", {"models": risks}

    # Symbol -> leg mapping, to flatten the regime map (leg-name keys -> symbols).
    symbol_to_leg: dict[str, str] = {}
    for leg in legs:
        for symbol in (leg.universe.symbols or []):
            symbol_to_leg[symbol] = leg.strategy_name

    pcm_type = "ConfidenceWeightedPortfolioConstructionModel"
    pcm_params: dict = {}
    if alloc.regime is not None:
        symbol_map: dict[str, dict[str, float]] = {}
        for quadrant, leg_weights in (alloc.regime.map or {}).items():
            symbol_map[quadrant] = {
                symbol: float(leg_weights[leg_name])
                for symbol, leg_name in symbol_to_leg.items()
                if leg_name in leg_weights
            }
        pcm_type = "RegimeWeightedPortfolioConstructionModel"
        pcm_params = {
            "regime_map": symbol_map,
            "signal": alloc.regime.signal,
            "rebalance_days": _rebalance_days(alloc.rebalance),
        }
    elif alloc.base == "risk_parity":
        pcm_type = "RiskParityPortfolioConstructionModel"
        pcm_params = {"rebalance": alloc.rebalance}
    elif alloc.base == "hrp":
        # HRP is a runtime gap; fall back to risk-parity weighting.
        pcm_type = "RiskParityPortfolioConstructionModel"
        pcm_params = {"rebalance": alloc.rebalance}
    elif alloc.weights:
        pcm_type = "InsightWeightingPortfolioConstructionModel"
        pcm_params = {"weights": alloc.weights}

    algo_params: dict = {}
    if alloc.regime is not None:
        # Note: NOT "regime-source" — that key drives the technical regime
        # (daily/composed/tsmom). The economic-environment signal lives in the
        # RegimeWeightedPortfolioConstructionModel's own `signal` param.
        algo_params["economic-regime-signal"] = alloc.regime.signal
    if alloc.vol_target is not None:
        algo_params["vol-target"] = str(alloc.vol_target.target_vol)
    if alloc.performance is not None:
        algo_params["performance-metric"] = alloc.performance.metric
        algo_params["performance-lookback-days"] = str(alloc.performance.lookback_days)

    # Combined universe: a multi-leg portfolio trades the union of its sleeves'
    # universes, not just the first leg's.
    universes = [c["Framework"]["UniverseSelection"] for c in compiled]
    if universes and all(u.get("Type") == "ManualUniverseSelectionModel" for u in universes):
        symbols: list[str] = []
        for u in universes:
            symbols.extend(u.get("Parameters", {}).get("symbols", []))
        universe_selection = {
            "Type": "ManualUniverseSelectionModel",
            "Parameters": {"symbols": list(dict.fromkeys(symbols))},
        }
    else:
        universe_selection = compiled[0]["Framework"]["UniverseSelection"]

    out = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {
            "UniverseSelection": universe_selection,
            "Alpha": {"Type": "CompositeAlphaModel", "Parameters": {"models": alphas}},
            "PortfolioConstruction": {"Type": pcm_type, "Parameters": pcm_params},
            "Execution": compiled[0]["Framework"]["Execution"],
            "RiskManagement": {"Type": risk_type, "Parameters": risk_params},
        },
        "AlgorithmParameters": algo_params,
        "VeraBase": compiled[0].get("VeraBase", {}),
    }
    # Fixed-symbol portfolio (all legs manual): bound ONE store universe query to
    # the union of sleeve symbols so the store pre-hydrates exactly those ETFs.
    # The framework slots stay ManualUniverse + immediate execution (framework
    # path), which rebalances the fixed sleeves to target weights.
    if legs and all(leg.universe.source == UniverseSource.MANUAL for leg in legs):
        symbols = [s for leg in legs for s in (leg.universe.symbols or [])]
        _bound_manual_store_spec(out, sorted(set(symbols)))
    return out
