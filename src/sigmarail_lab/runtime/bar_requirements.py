"""Bar-fetch requirements declared per framework model.

The strategy invariant is that entry *and* ongoing hold decisions are made from
precomputed columns + open-trade state, never from raw bars. Bars exist only to
price execution and manage open positions. This module declares, per framework
``Type`` id, the bar window each model needs so the bar provider can fetch a
bounded window instead of the full backtest range.

Fields are in *days* at daily resolution (the provider pads in calendar days
too, see ``ClickHouseDataProvider._historyPadDays``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from sigmarail_lab.ir.lean_framework_json import FrameworkBundleV1, FrameworkSlotSpec


@dataclass(frozen=True)
class BarRequirements:
    """Bar-fetch needs of one framework model (or the merged strategy).

    ``warmup_bars`` is the lookback a model needs before it can act.
    ``max_hold_days`` is the worst-case hold measured from entry — it covers
    portfolio decisions (trailing/time stops) that can outlive the screen's
    exit signal. ``required_columns`` are the screener columns the model reads
    (so the universe ``select`` can include them).
    """

    warmup_bars: int = 0
    max_hold_days: int = 0
    needs_live_bars: bool = False
    required_columns: tuple[str, ...] = ()
    hold_days_param: str | None = None  # spec parameter overriding max_hold_days


# Framework Type id -> default requirements.
#
# Swing risk reads precomputed ATR (``atr_14_pct``) from the store (Phase 2), so
# it no longer needs bar warm-up or the live bar stream for ATR. The swing alpha
# models still build rolling windows from live bars (Phase 3 will precompute them).
BAR_REQUIREMENTS_BY_TYPE: dict[str, BarRequirements] = {
    "SwingProgressiveRiskManagementModel": BarRequirements(
        warmup_bars=0,
        max_hold_days=25,
        needs_live_bars=False,
        required_columns=("atr_14_pct",),
        hold_days_param="max_holding_days",
    ),
    "SwingBreakoutAlphaModel": BarRequirements(
        warmup_bars=10,
        needs_live_bars=True,
    ),
    "SwingPullbackAlphaModel": BarRequirements(
        warmup_bars=10,
        needs_live_bars=True,
    ),
    "VeraScreenerAlphaModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=("overall_score",),
    ),
    "VeraCompositeAlphaModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=(),
    ),
    "VeraPyramidAlphaModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=(
            "overall_score",
            "high",
            "volume",
            "avg_vol_50d",
            "factor_residual_60d",
            "factor_alpha_tstat_60d",
            "factor_beta_mkt_60d",
        ),
    ),
    "VeraScreenerPortfolioConstructionModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=("atr_14_pct",),
    ),
    "VeraScreenerExecutionModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=(),
    ),
    "VeraScreenerUniverseSelectionModel": BarRequirements(
        warmup_bars=0,
        needs_live_bars=False,
        required_columns=(),
    ),
}


def _ast_columns(node: object) -> set[str]:
    """Physical columns referenced by a universe_query_v1 where AST."""
    out: set[str] = set()
    if not isinstance(node, dict):
        return out
    ntype = node.get("type")
    if ntype in ("all", "any"):
        for child in node.get("items") or []:
            out |= _ast_columns(child)
        return out
    if ntype == "not":
        return _ast_columns(node.get("item"))
    if ntype in ("gt", "gte", "lt", "lte", "eq"):
        for side in ("left", "right"):
            out |= _operand_columns(node.get(side))
    return out


def _operand_columns(operand: object) -> set[str]:
    if isinstance(operand, str):
        return {operand}
    if not isinstance(operand, dict):
        return set()
    kind = operand.get("type")
    if kind == "col" and operand.get("name"):
        return {str(operand["name"])}
    if kind == "formula":
        cols: set[str] = set()
        for arg in operand.get("args") or []:
            cols |= _operand_columns(arg)
        return cols
    return set()


def _slot_specs(bundle: "FrameworkBundleV1") -> Iterable["FrameworkSlotSpec"]:
    return (
        bundle.universe_selection,
        bundle.alpha,
        bundle.portfolio_construction,
        bundle.execution,
        bundle.risk_management,
    )


def _resolve_for_spec(type_id: str, spec: "FrameworkSlotSpec") -> BarRequirements:
    req = BAR_REQUIREMENTS_BY_TYPE.get(type_id, BarRequirements())
    if req.hold_days_param and spec.parameters:
        raw = spec.parameters.get(req.hold_days_param)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            req = replace(req, max_hold_days=int(raw))

    extra_cols = set(req.required_columns)
    needs_live = req.needs_live_bars

    # Inspect entry triggers if present in parameters
    if spec.parameters and "entry_triggers" in spec.parameters:
        triggers = spec.parameters.get("entry_triggers")
        if isinstance(triggers, list):
            for trig in triggers:
                if isinstance(trig, dict):
                    ttype = str(trig.get("type") or "").strip().lower()
                    if ttype in ("pivot_breakout", "breakout"):
                        extra_cols.update(("high", "high_90d", "volume", "avg_vol_50d", "breakout_signal"))
                    elif ttype == "vcp_complete":
                        extra_cols.update(
                            (
                                "close",
                                "high_90d",
                                "vcp_atr_compression_5d_90d",
                                "vcp_volume_dryup_5d_90d",
                                "vcp_proximity_90d",
                            )
                        )
                    elif ttype == "pullback_to_sma":
                        extra_cols.update(("close", "pullback_ready", "pocket_pivot_score"))
                        period = trig.get("sma_period")
                        extra_cols.add(f"sma{int(period)}d" if period else "sma50d")
                    elif ttype in ("rsi_cross", "macd"):
                        needs_live = True
                    elif ttype == "ema_cross":
                        extra_cols.update(("ema_21d", "sma50d"))

    # Inspect stop-loss for ATR requirement
    if spec.parameters and "stop_loss" in spec.parameters:
        sl = spec.parameters.get("stop_loss")
        if isinstance(sl, dict) and sl.get("type") == "atr":
            extra_cols.add("atr_14_pct")
        elif isinstance(sl, dict) and sl.get("type") == "pivot":
            # C3: the pivot-derived stop needs the entry's VCP pivot line in the universe row.
            extra_cols.add(str(sl.get("field") or "vcp_pivot_line"))

    # Inspect factor weights if present
    if spec.parameters and "field_weights" in spec.parameters:
        fw = spec.parameters.get("field_weights")
        if isinstance(fw, dict):
            extra_cols.update(str(k) for k in fw.keys())

    # Inspect expression parameters that reference row columns
    expr_param_names = [
        "eligibility_expr",
        "confidence_expr",
        "direction_expr",
        "magnitude_expr",
        "weight_expr",
        "setup_expr",
        "pcm_scale_expr",
    ]
    for ep in expr_param_names:
        if spec.parameters and ep in spec.parameters:
            extra_cols.update(_ast_columns(spec.parameters.get(ep)))

    if spec.parameters:
        extra_cols.update(_ast_columns(spec.parameters.get("setup_where")))
        extra_cols.update(_ast_columns(spec.parameters.get("screen")))
        extra_cols.update(_ast_columns(spec.parameters.get("membership")))
        extra_cols.update(_ast_columns(spec.parameters.get("hygiene_where")))
        named = spec.parameters.get("named_groups") or {}
        if isinstance(named, dict):
            for gast in named.values():
                extra_cols.update(_ast_columns(gast))
        gates = spec.parameters.get("gates") or []
        if isinstance(gates, list):
            for gate in gates:
                if not isinstance(gate, dict):
                    continue
                extra_cols.update(str(f) for f in gate.get("score_fields") or [])
                extra_cols.update(str(f) for f in gate.get("optional_score_fields") or [])
                extra_cols.update(_ast_columns(gate.get("where")))

    req = replace(req, needs_live_bars=needs_live, required_columns=tuple(sorted(extra_cols)))

    # Walk composite models[] recursively if present
    child_reqs = []
    if spec.parameters and "models" in spec.parameters:
        models = spec.parameters.get("models")
        if isinstance(models, list):
            for child in models:
                if isinstance(child, dict):
                    child_type = (child.get("Type") or child.get("type") or "").strip()
                    child_params = child.get("Parameters") or child.get("parameters") or {}
                    from sigmarail_lab.ir.lean_framework_json import FrameworkSlotSpec
                    child_spec = FrameworkSlotSpec(type=child_type, parameters=child_params)
                    child_reqs.append(_resolve_for_spec(child_type, child_spec))

    if child_reqs:
        req = merge_bar_requirements(req, *child_reqs)

    return req


def merge_bar_requirements(*reqs: BarRequirements) -> BarRequirements:
    """Combine model requirements into the strategy-wide requirement."""
    return BarRequirements(
        warmup_bars=max((r.warmup_bars for r in reqs), default=0),
        max_hold_days=max((r.max_hold_days for r in reqs), default=0),
        needs_live_bars=any(r.needs_live_bars for r in reqs),
        required_columns=tuple(
            sorted({c for r in reqs for c in r.required_columns})
        ),
        hold_days_param=None,  # merged; per-model override already applied
    )


def collect_bar_requirements(bundle: "FrameworkBundleV1") -> BarRequirements:
    """Sum the bar-fetch requirements of all five framework slots."""
    reqs = [
        _resolve_for_spec((spec.type or "").strip(), spec)
        for spec in _slot_specs(bundle)
    ]
    return merge_bar_requirements(*reqs)


def ensure_select_columns(spec: dict, columns: Iterable[str]) -> dict:
    """Return a copy of a ``universe_query_v1`` spec with ``columns`` added to ``select``.

    The manifest's ``required_columns`` (e.g. ``atr_14_pct`` for the swing risk
    model) must be present in the universe ``select`` for the store to return
    them. This merges them in idempotently without mutating the input spec.
    Computed aliases (from ``spec.computed``) are excluded from ``select`` since
    they are generated by the query service, not read from the table.
    """
    out = dict(spec)
    select = list(out.get("select") or [])
    computed_aliases = {item.get("alias") for item in (out.get("computed") or []) if isinstance(item, dict)}
    for col in columns:
        if col not in select and col not in computed_aliases:
            select.append(col)
    out["select"] = select
    return out


def required_columns_for(bundle: "FrameworkBundleV1") -> tuple[str, ...]:
    """Columns the composed strategy needs in the universe ``select``."""
    return collect_bar_requirements(bundle).required_columns


def validate_select_columns(spec_or_select: dict | Iterable[str], required: Iterable[str]) -> None:
    """Raise ValueError if any required column is missing from select (+ computed aliases)."""
    if isinstance(spec_or_select, dict):
        select = set(spec_or_select.get("select") or [])
        for item in spec_or_select.get("computed") or []:
            if isinstance(item, dict) and item.get("alias"):
                select.add(str(item["alias"]))
    else:
        select = set(spec_or_select)
    missing = [c for c in sorted(set(required)) if c not in select]
    if missing:
        raise ValueError(
            f"Select columns cannot satisfy required columns; missing: {missing}"
        )
