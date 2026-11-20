"""Save-time materialization of the SigmaRail Spec-owned risk ladder.

Two surfaces:

- :func:`materialize_swing_risk_rules` — injects ``Parameters.rules`` into a
  compiled VeraLabV1 spec's ``Framework.RiskManagement`` when the model is
  ``SwingProgressiveRiskManagementModel`` and carries no authored rules.
- :func:`seed_pipeline_risk_rules` — mirrors those rules into the stored
  ``pipeline_document``'s exit stage when the author left it empty, so the
  Studio Risk card renders the same decision table that will run.
"""

from __future__ import annotations

import copy
from typing import Any

__all__ = [
    "generate_default_init_stop",
    "generate_swing_risk_ladder",
    "materialize_swing_risk_rules",
    "seed_pipeline_risk_rules",
]

_SWING_RISK_TYPE = "SwingProgressiveRiskManagementModel"


def generate_swing_risk_ladder(params: dict[str, Any] | None = None) -> list[dict]:
    """Generate the canonical ladder for the given risk ``Parameters``.

    The same generator is included in SigmaRail Spec and LEAN vendors.
    """
    from sigmarail_spec.strategy.risk_ladder import generate_swing_risk_ladder as _gen
    return _gen(**(params or {}))


def generate_default_init_stop(params: dict[str, Any] | None = None) -> dict:
    """Generate the default ``init_stop`` Operand AST for the given Parameters.

    Only the init-stop knobs matter — ``use_atr_stops``,
    ``atr_stop_multiplier``, ``max_stop_loss_pct``. Returns ``None`` when
    The same generator is included in SigmaRail Spec and LEAN vendors.
    """
    from sigmarail_spec.strategy.risk_ladder import generate_default_init_stop as _gen
    params = params or {}
    return _gen(
        use_atr_stops=bool(params.get("use_atr_stops", True)),
        atr_stop_multiplier=float(params.get("atr_stop_multiplier", 2.0)),
        max_stop_loss_pct=float(params.get("max_stop_loss_pct", 0.05)),
    )


def materialize_swing_risk_rules(spec: dict[str, Any]) -> bool:
    """Inject the generated ladder into a VeraLabV1 spec when absent.

    Mutates ``spec`` in place; returns ``True`` when ``Parameters.rules`` was
    written. Only applies to a top-level ``SwingProgressiveRiskManagementModel``
    without authored rules — composite stacks and authored rule sets are left
    untouched.
    """
    try:
        risk = (spec.get("Framework") or {}).get("RiskManagement") or {}
    except AttributeError:
        return False
    if risk.get("Type") != _SWING_RISK_TYPE:
        return False
    params = risk.get("Parameters")
    if not isinstance(params, dict):
        params = {}
        risk["Parameters"] = params
    changed = False
    if not params.get("rules"):
        ladder = generate_swing_risk_ladder(params)
        if ladder:
            params["rules"] = ladder
            changed = True
    if params.get("init_stop") is None:
        init_stop = generate_default_init_stop(params)
        if init_stop is not None:
            params["init_stop"] = init_stop
            changed = True
    return changed


def seed_pipeline_risk_rules(spec: dict[str, Any], pipeline_doc: dict[str, Any]) -> bool:
    """Copy spec ``Parameters.rules``/``init_stop`` into the exit stage when empty.

    One direction of truth — spec → doc: the stored pipeline document mirrors
    the exact decision table the run will execute, so the Studio Risk card
    shows what runs instead of "runtime defaults apply".

    Mutates ``pipeline_doc`` in place; returns ``True`` when seeded. Each
    field seeds independently and never clobbers authored stage content.
    """
    try:
        risk = (spec.get("Framework") or {}).get("RiskManagement") or {}
        params = risk.get("Parameters") or {}
        rules = params.get("rules")
        init_stop = params.get("init_stop")
    except AttributeError:
        return False
    stages = pipeline_doc.get("stages")
    if not isinstance(stages, list):
        return False
    exit_stage = next(
        (s for s in stages if isinstance(s, dict) and s.get("mode") == "exit"),
        None,
    )
    if exit_stage is None:
        return False
    seeded = False
    if isinstance(rules, list) and rules and not exit_stage.get("rules"):
        exit_stage["rules"] = copy.deepcopy(rules)
        seeded = True
    if isinstance(init_stop, dict) and not exit_stage.get("init_stop"):
        exit_stage["init_stop"] = copy.deepcopy(init_stop)
        seeded = True
    return seeded


def hydrate_rule_descriptions(spec: dict[str, Any], pipeline_doc: dict[str, Any] | None) -> int:
    """Fill missing ``description`` on canonical ladder rules (read-side).

    Specs saved before the intent field existed carry rules without
    descriptions; because specs with runs are immutable, a save-fork is the
    only persistence path — so this hydrates the *served* document instead.
    Name-matched against a regenerated ladder from the spec's own
    Parameters, so the text describes this spec's baked literals. Authored
    rules with non-canonical names and rules that already carry a
    description are untouched. Mutates in place; returns count filled.
    """
    try:
        risk = (spec.get("Framework") or {}).get("RiskManagement") or {}
        params = risk.get("Parameters") or {}
        rules = params.get("rules")
    except AttributeError:
        return 0
    if not isinstance(rules, list) or not rules:
        return 0
    ladder = generate_swing_risk_ladder(
        {k: v for k, v in params.items() if k not in ("rules", "init_stop")}
    )
    if not ladder:
        return 0
    desc = {r.get("name"): r.get("description") for r in ladder if r.get("description")}
    # Legacy rules no longer generated by the ladder still deserve intent text —
    # interpolate from the spec's own Parameters where applicable.
    if "max_weight_cap" not in desc:
        try:
            max_w = float(params.get("max_single_weight") or 0.20)
            desc["max_weight_cap"] = (
                f"Post-fill concentration cap (deprecated — PCM owns this now): if a "
                f"position's market weight exceeds {max_w * 100:g}% of equity, cap "
                "further growth at 80% of that level."
            )
        except (TypeError, ValueError):
            pass
    filled = 0
    surfaces = [rules]
    if isinstance(pipeline_doc, dict):
        for stage in pipeline_doc.get("stages") or []:
            if isinstance(stage, dict) and isinstance(stage.get("rules"), list):
                surfaces.append(stage["rules"])
    for surface in surfaces:
        for rule in surface:
            if not isinstance(rule, dict) or rule.get("description"):
                continue
            d = desc.get(rule.get("name"))
            if d:
                rule["description"] = d
                filled += 1
    return filled
