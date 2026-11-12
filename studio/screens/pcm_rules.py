"""Save-time materialization of the RiskBudgeted PCM allocation table (C-FW-RULES Phase 2).

The ladder's single source of truth is ``vera_lab.ir.pcm_ladder`` — the LEAN
container carries ``vera_lab`` but never ``vera_query_core``, and VeraBase
deliberately never imports ``vera_lab``. Studio is the composition root, so the
bridge lives here (same sibling-tree ``sys.path`` convention as
``screens/ch._ensure_verabasel_path`` and ``screens.risk_rules``).

When ``vera_lab`` is not reachable the helpers degrade to no-ops — the runtime
regenerates the identical table internally (``rules=None`` → ctor defaults),
so skipping materialization costs stored-spec *visibility*, never behavior.

Two surfaces:

- :func:`materialize_pcm_rules` — injects ``Parameters.rules``/``size_expr``
  and the book-level ``scale_expr``/``slots_expr``/``order_expr`` into a
  compiled VeraLabV1 spec's ``Framework.PortfolioConstruction`` when the
  model is ``RiskBudgetedPortfolioConstructionModel`` and carries no authored
  table.
- :func:`seed_pipeline_pcm_rules` — mirrors them into the stored
  ``pipeline_document``'s ``sizing`` block when absent, so the Studio PCM card
  renders the same decision table that will run.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "generate_pcm_book_exprs",
    "generate_pcm_ladder",
    "generate_pcm_size_expr",
    "hydrate_pcm_rule_descriptions",
    "materialize_pcm_rules",
    "pcm_bindings_catalog",
    "seed_pipeline_pcm_rules",
]

_PCM_TYPE = "RiskBudgetedPortfolioConstructionModel"


def _ensure_veralab_path() -> None:
    """Put the sibling VeraTradingLab tree on sys.path (mirrors ch.py)."""
    root = Path(__file__).resolve().parents[2]  # FinanceProjects
    vtl = root / "LeanProjects" / "VeraTradingLab"
    if vtl.is_dir():
        path = str(vtl)
        if path not in sys.path:
            sys.path.insert(0, path)


def _ladder_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    """Map PCM ``Parameters`` names → ``generate_pcm_ladder`` kwargs."""
    return {
        "max_position_weight": float(params.get("max_position_weight") or 0.15),
        "allow_adds_on_invested": bool(params.get("allow_adds_on_invested", False)),
        "use_regime_scaling": bool(params.get("use_regime_scaling", True)),
        "uses": params.get("uses") or [],
        "phases": params.get("phases"),
        "add_trigger_pct": float(params.get("add_trigger_pct") or 0.02),
        "max_entry_atr_pct": float(params.get("max_entry_atr_pct") or 0.0),
        "enable_displacement": bool(params.get("enable_displacement", False)),
        "displacement_min_hold_days": int(params.get("displacement_min_hold_days") or 5),
        "displacement_max_incumbent_r": float(params.get("displacement_max_incumbent_r") or 1.0),
        "displacement_min_challenger_rs": float(params.get("displacement_min_challenger_rs") or 90.0),
        "displacement_min_challenger_screens": int(params.get("displacement_min_challenger_screens") or 3),
        "displacement_immune_rs": float(params.get("displacement_immune_rs") or 95.0),
        "displacement_cooldown_days": int(params.get("displacement_cooldown_days") or 14),
        "pcm_allow_entry_expr": params.get("pcm_allow_entry_expr"),
        "risk_allow_pyramid_add_expr": params.get("risk_allow_pyramid_add_expr"),
    }


def generate_pcm_ladder(params: dict[str, Any] | None = None) -> list[dict] | None:
    """Generate the canonical PCM allocation table for the given Parameters.

    Returns ``None`` when vera_lab is unreachable; callers treat that as
    "leave the spec as-is" — the runtime regenerates the identical table.
    """
    _ensure_veralab_path()
    try:
        from vera_lab.ir.pcm_ladder import generate_pcm_ladder as _gen
    except Exception:
        return None
    try:
        return _gen(**_ladder_kwargs(params or {}))
    except Exception:
        return None


def generate_pcm_size_expr(params: dict[str, Any] | None = None) -> dict | None:
    """Generate the default ``size_expr`` Operand AST for the given Parameters."""
    _ensure_veralab_path()
    try:
        from vera_lab.ir.pcm_ladder import generate_default_size_expr as _gen
    except Exception:
        return None
    params = params or {}
    try:
        return _gen(
            risk_per_trade_pct=float(params.get("risk_per_trade_pct") or 0.01),
            max_position_weight=float(params.get("max_position_weight") or 0.15),
            honor_insight_confidence=bool(params.get("honor_insight_confidence", False)),
            pcm_scale_expr=params.get("pcm_scale_expr"),
        )
    except Exception:
        return None


def generate_pcm_book_exprs(params: dict[str, Any] | None = None) -> dict[str, dict] | None:
    """Generate the book-level ASTs (``scale_expr``/``slots_expr``/``order_expr``).

    Evaluated once per PCM pass — ``scale_expr`` → ``regime.scale``,
    ``slots_expr`` → ``acct.scaled_max_positions``, ``order_expr`` → unit
    ordering. Same authored-or-generated contract as ``rules``/``size_expr``.
    Returns ``None`` when vera_lab is unreachable.
    """
    _ensure_veralab_path()
    try:
        from vera_lab.ir.pcm_ladder import (
            generate_order_expr,
            generate_scale_expr,
            generate_slots_expr,
        )
    except Exception:
        return None
    params = params or {}
    try:
        use_regime = bool(params.get("use_regime_scaling", True))
        return {
            "scale_expr": generate_scale_expr(
                use_regime_scaling=use_regime,
                min_regime_fraction=float(params.get("min_regime_fraction") or 0.15),
            ),
            "slots_expr": generate_slots_expr(
                use_regime_scaling=use_regime,
                scaled_max_positions_floor=int(params.get("scaled_max_positions_floor") or 2),
                max_positions=int(params.get("max_positions") or 8),
            ),
            "order_expr": generate_order_expr(),
        }
    except Exception:
        return None


def pcm_bindings_catalog() -> dict[str, list[dict]] | None:
    """The PCM ``ref`` binding namespaces (cand/hold/acct/pyr/regime) for Studio."""
    _ensure_veralab_path()
    try:
        from vera_lab.ir.pcm_bindings import PCM_BINDING_NAMESPACES
    except Exception:
        return None
    return {ns: [dict(b) for b in items] for ns, items in PCM_BINDING_NAMESPACES.items()}


def materialize_pcm_rules(spec: dict[str, Any]) -> bool:
    """Inject the generated allocation table into a VeraLabV1 spec when absent.

    Mutates ``spec`` in place; returns ``True`` when anything was written.
    Only applies to ``RiskBudgetedPortfolioConstructionModel`` — composite or
    passthrough PCM stacks are untouched. ``rules`` and ``size_expr`` seed
    independently and never clobber authored content.
    """
    try:
        pcm = (spec.get("Framework") or {}).get("PortfolioConstruction") or {}
    except AttributeError:
        return False
    if pcm.get("Type") != _PCM_TYPE:
        return False
    params = pcm.get("Parameters")
    if not isinstance(params, dict):
        params = {}
        pcm["Parameters"] = params
    changed = False
    if params.get("rules") is None:
        ladder = generate_pcm_ladder(params)
        if ladder:
            params["rules"] = ladder
            changed = True
    if params.get("size_expr") is None:
        size_expr = generate_pcm_size_expr(params)
        if size_expr is not None:
            params["size_expr"] = size_expr
            changed = True
    book_exprs = None
    if any(params.get(k) is None for k in ("scale_expr", "slots_expr", "order_expr")):
        book_exprs = generate_pcm_book_exprs(params)
    for key, expr in (book_exprs or {}).items():
        if params.get(key) is None and isinstance(expr, dict):
            params[key] = expr
            changed = True
    return changed


def seed_pipeline_pcm_rules(spec: dict[str, Any], pipeline_doc: dict[str, Any]) -> bool:
    """Copy spec ``Parameters.rules``/``size_expr`` into ``sizing`` when absent.

    One direction of truth — spec → doc: the stored pipeline document mirrors
    the exact allocation table the run will execute, so the Studio PCM card
    shows what runs instead of "runtime defaults apply".
    """
    try:
        pcm = (spec.get("Framework") or {}).get("PortfolioConstruction") or {}
        params = pcm.get("Parameters") or {}
        rules = params.get("rules")
        exprs = {k: params.get(k) for k in ("size_expr", "scale_expr", "slots_expr", "order_expr")}
    except AttributeError:
        return False
    sizing = pipeline_doc.get("sizing")
    if not isinstance(sizing, dict):
        sizing = {}
        pipeline_doc["sizing"] = sizing
    seeded = False
    if isinstance(rules, list) and rules and sizing.get("rules") is None:
        sizing["rules"] = copy.deepcopy(rules)
        seeded = True
    for key, expr in exprs.items():
        if isinstance(expr, dict) and sizing.get(key) is None:
            sizing[key] = copy.deepcopy(expr)
            seeded = True
    return seeded


def hydrate_pcm_rule_descriptions(spec: dict[str, Any], pipeline_doc: dict[str, Any] | None) -> int:
    """Fill missing ``description`` on canonical PCM rules (read-side).

    Same contract as the risk hydrator: name-matched against a regenerated
    ladder from the spec's own Parameters. Authored rules with non-canonical
    names are untouched. Mutates in place; returns count filled.
    """
    try:
        pcm = (spec.get("Framework") or {}).get("PortfolioConstruction") or {}
        params = pcm.get("Parameters") or {}
        rules = params.get("rules")
    except AttributeError:
        return 0
    if not isinstance(rules, list) or not rules:
        return 0
    ladder = generate_pcm_ladder(
        {k: v for k, v in params.items()
         if k not in ("rules", "size_expr", "scale_expr", "slots_expr", "order_expr")}
    )
    if not ladder:
        return 0
    desc = {r.get("name"): r.get("description") for r in ladder if r.get("description")}
    filled = 0
    surfaces = [rules]
    if isinstance(pipeline_doc, dict):
        sizing = pipeline_doc.get("sizing")
        if isinstance(sizing, dict) and isinstance(sizing.get("rules"), list):
            surfaces.append(sizing["rules"])
    for surface in surfaces:
        for rule in surface:
            if not isinstance(rule, dict) or rule.get("description"):
                continue
            d = desc.get(rule.get("name"))
            if d:
                rule["description"] = d
                filled += 1
    return filled
