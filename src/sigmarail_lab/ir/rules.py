"""Rule/Action AST for Vera framework slots.

Risk action set (Phase 1 — position lifecycle):
- Exit(fraction: float) — terminal
- Trim(fraction: float) — terminal
- RatchetStop(to: Operand, mode: Literal["max", "set"] = "max") — non-terminal
- CapWeight(to: Operand) — non-terminal, deprecated (PCM owns concentration)
- ArmCooldown(days: int) — non-terminal
- SetFlag(flag: str) — non-terminal; sets a per-position flag visible to later
  rules as ``__position.<flag>`` (e.g. tranche1_taken, runner_active). This is how
  rules declare their own bookkeeping instead of the runtime keying off rule
  names.

PCM action set (allocation decisions — see the action docstrings):
- Enter(size_scale?) — terminal; emits a buy target, consumes a slot
- Add(size_scale?) — terminal; advances the pyramid phase, emits an add target
- Skip() — terminal; suppresses the unit today
- Resize(to: Operand) — terminal; absolute weight target (0 = flatten)
- Displace(...) — non-terminal; flattens the weakest qualifying incumbent

``validate_rules(slot=...)`` enforces the per-slot vocabulary: risk actions in
a PCM rule (and vice versa) fail validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, model_validator

from sigmarail_spec.expr import (
    BoolExprItem,
    Operand,
)


def _wrap_literal(v: Any) -> Any:
    """Coerce a bare number into ``{"type": "lit", "value": v}`` — numeric
    action args are operands (EXPRESSION_SURFACE §11); literals stay accepted
    for stored-spec compatibility."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return {"type": "lit", "value": v}
    return v


CoercedOperand = Annotated[Operand, BeforeValidator(_wrap_literal)]


class ActionBase(BaseModel):
    """Shared base for the bounded effect vocabulary.

    ``v`` pins the effect semantics a stored spec was authored against — the
    registry (:data:`ACTION_REGISTRY`) carries the current version; when an
    action's engine implementation changes in a way that alters outcomes, its
    ``version`` bumps and older ``v`` values replay against the pinned
    semantics (or lint warns). Every other field is an operand — literals
    only for enums/modes/names.
    """

    model_config = ConfigDict(extra="forbid")

    v: int = Field(default=1, ge=1)


class Exit(ActionBase):
    type: Literal["exit"] = "exit"
    fraction: CoercedOperand


class Trim(ActionBase):
    type: Literal["trim"] = "trim"
    fraction: CoercedOperand


class RatchetStop(ActionBase):
    type: Literal["ratchet_stop"] = "ratchet_stop"
    to: CoercedOperand
    mode: Literal["max", "set"] = "max"


class CapWeight(ActionBase):
    """DEPRECATED — kept so stored specs with a max_weight_cap rule still
    validate and evaluate. Concentration control moved to the PCM
    (max_position_weight drift scan in RiskBudgetedPortfolioConstructionModel);
    the generated ladder no longer emits this action."""

    type: Literal["cap_weight"] = "cap_weight"
    to: CoercedOperand


class ArmCooldown(ActionBase):
    type: Literal["arm_cooldown"] = "arm_cooldown"
    days: CoercedOperand


class SetFlag(ActionBase):
    type: Literal["set_flag"] = "set_flag"
    flag: str = Field(min_length=1)


# --- PCM actions (PortfolioConstruction decision units) ---
#
# PCM rules run one unified pass per rebalance over decision units — Alpha
# insights (cand.*) and insight-quiet holdings (hold.*) — in rank order with
# shared acct.* counters. Sizing is an Operand AST (``size_expr``); these
# actions decide *whether* a unit produces a target, and ``size_scale``
# multiplies the computed size (e.g. ``ref{pyr.entry_frac}`` for phase sizing).


class Enter(ActionBase):
    """Emit a buy target for the unit: size_expr × size_scale; consumes a slot."""

    type: Literal["enter"] = "enter"
    size_scale: Operand | None = None


class Add(ActionBase):
    """Pyramid add: advance the phase state, then size_expr × size_scale."""

    type: Literal["add"] = "add"
    size_scale: Operand | None = None


class Skip(ActionBase):
    """Pass on this unit today — no target emitted. Terminal."""

    type: Literal["skip"] = "skip"


class Resize(ActionBase):
    """Emit an absolute weight target for the unit's symbol (0 = flatten)."""

    type: Literal["resize"] = "resize"
    to: CoercedOperand


class Displace(ActionBase):
    """Flatten the weakest qualifying incumbent to free a slot (non-terminal).

    The rule's ``when`` qualifies the *challenger*; these args qualify the
    *incumbent* the engine pairs with it — lowest open_r first by default, or
    lowest ``incumbent_score`` when that operand is authored (evaluated with
    ``hold.*`` bound to the incumbent). After firing, ``acct.slots_remaining``
    increments so a later ``enter`` rule can consume it. Threshold args are
    operands evaluated on the challenger unit's context — e.g.
    ``cooldown_days: cond(regime.on=0, 21, 7)`` is legal.
    """

    type: Literal["displace"] = "displace"
    min_incumbent_days: CoercedOperand = Field(
        default={"type": "lit", "value": 5}, validate_default=True
    )
    max_incumbent_r: CoercedOperand = Field(
        default={"type": "lit", "value": 1.0}, validate_default=True
    )
    immune_rs: CoercedOperand = Field(
        default={"type": "lit", "value": 95.0}, validate_default=True
    )
    cooldown_days: CoercedOperand = Field(
        default={"type": "lit", "value": 14}, validate_default=True
    )
    max_per_day: CoercedOperand = Field(
        default={"type": "lit", "value": 2}, validate_default=True
    )
    incumbent_score: Optional[Operand] = None


ActionNode = Annotated[
    Union[
        Exit,
        Trim,
        RatchetStop,
        CapWeight,
        ArmCooldown,
        SetFlag,
        Enter,
        Add,
        Skip,
        Resize,
        Displace,
    ],
    Field(discriminator="type"),
]


@dataclass(frozen=True)
class ActionSpec:
    """One entry in the bounded effect vocabulary — the ``then`` contract.

    ``version`` pins semantics (stored specs carry ``v``); ``operand_args``
    are evaluated through the site's slot evaluator with the unit/position
    context; ``literal_args`` are enums/modes/names that are *not* evaluated;
    ``state_effect`` names the engine state the action mutates.
    """

    version: int
    terminal: bool
    slots: frozenset[str]  # {"pcm", "risk"}
    operand_args: frozenset[str]
    literal_args: frozenset[str]
    state_effect: str


ACTION_REGISTRY: dict[str, ActionSpec] = {
    "exit": ActionSpec(1, True, frozenset({"risk"}), frozenset({"fraction"}), frozenset(), "position_target"),
    "trim": ActionSpec(1, True, frozenset({"risk"}), frozenset({"fraction"}), frozenset(), "position_target"),
    "ratchet_stop": ActionSpec(1, False, frozenset({"risk"}), frozenset({"to"}), frozenset({"mode"}), "stop_state"),
    "cap_weight": ActionSpec(1, False, frozenset({"risk"}), frozenset({"to"}), frozenset(), "position_target (deprecated)"),
    "arm_cooldown": ActionSpec(1, False, frozenset({"risk", "pcm"}), frozenset({"days"}), frozenset(), "cooldown_state"),
    "set_flag": ActionSpec(1, False, frozenset({"risk", "pcm"}), frozenset(), frozenset({"flag"}), "flag_state"),
    "enter": ActionSpec(1, True, frozenset({"pcm"}), frozenset({"size_scale"}), frozenset(), "order+slot+pyramid"),
    "add": ActionSpec(1, True, frozenset({"pcm"}), frozenset({"size_scale"}), frozenset(), "order+pyramid"),
    "skip": ActionSpec(1, True, frozenset({"pcm"}), frozenset(), frozenset(), "none"),
    "resize": ActionSpec(1, True, frozenset({"pcm"}), frozenset({"to"}), frozenset(), "order"),
    "displace": ActionSpec(
        1, False, frozenset({"pcm"}),
        frozenset({"min_incumbent_days", "max_incumbent_r", "immune_rs", "cooldown_days", "max_per_day", "incumbent_score"}),
        frozenset(),
        "order+slot+cooldown",
    ),
}

ACTION_TERMINAL: dict[str, bool] = {
    name: spec.terminal for name, spec in ACTION_REGISTRY.items()
}

# Per-slot action vocabularies — derived from the registry. Shared actions
# (arm_cooldown/set_flag) appear in both; the rest are slot-specific — a risk
# action in a PCM rule (or vice versa) is an authoring error worth failing loudly.
RISK_ACTIONS: frozenset[str] = frozenset(
    name for name, spec in ACTION_REGISTRY.items() if "risk" in spec.slots
)
PCM_ACTIONS: frozenset[str] = frozenset(
    name for name, spec in ACTION_REGISTRY.items() if "pcm" in spec.slots
)


def _slot_actions(slot: str) -> frozenset[str]:
    s = slot.lower()
    if s.startswith("portfolioconstruction") or s.startswith("pcm"):
        return PCM_ACTIONS
    if s.startswith("riskmanagement") or s.startswith("risk"):
        return RISK_ACTIONS
    return RISK_ACTIONS | PCM_ACTIONS


def action_vocabulary() -> dict[str, list[str]]:
    return {name: sorted(type_cls.model_fields) for name, type_cls in _ACTION_CLASSES.items()}


_ACTION_CLASSES: dict[str, type[BaseModel]] = {
    "exit": Exit,
    "trim": Trim,
    "ratchet_stop": RatchetStop,
    "cap_weight": CapWeight,
    "arm_cooldown": ArmCooldown,
    "set_flag": SetFlag,
    "enter": Enter,
    "add": Add,
    "skip": Skip,
    "resize": Resize,
    "displace": Displace,
}


class Phase(BaseModel):
    """One progressive-entry phase (PCM pyramid geometry).

    ``trigger`` gates *advancing into* this phase: a bool AST evaluated on the
    unit context (``cand``/``hold``/``acct``/``pyr``/``regime`` + T-1 row) at
    ``add``-apply time. Phase 0's trigger is ignored — entry is owned by
    ``enter`` rules. ``extra="forbid"`` — a silently-dropped key is exactly
    the dead-config residue the typed model exists to catch.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    size_pct: float = Field(gt=0.0, le=1.0)
    trigger: BoolExprItem | None = None
    # Generation-side field declared by the canonical PyramidPhase schema
    # (vera_query_core.strategy.pipeline): the phase's share of the risk
    # budget. Emitted as null across the stored corpus and not yet consumed
    # by the runtime — declared here so stored specs still parse while
    # extra="forbid" keeps catching real typos.
    risk_pct: float | None = Field(default=None, gt=0.0, le=1.0)


_PHASE_ADAPTER = TypeAdapter(list[Phase])


def validate_phases(phases: list[dict] | None) -> list[dict]:
    """Validate a ``phases`` list; returns normalized dicts (trigger ASTs kept
    as dicts — engines read raw JSON)."""
    if not phases:
        return []
    return [p.model_dump(exclude_none=True) for p in _PHASE_ADAPTER.validate_python(phases)]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    priority: int = 0
    once: bool = False
    when: BoolExprItem
    then: list[ActionNode] = Field(min_length=1)
    tag: str | None = None
    description: str | None = Field(
        default=None,
        description=(
            "Human-readable intent for the rule — what it is supposed to do in "
            "the model. Display-only; never affects evaluation."
        ),
    )

    @model_validator(mode="after")
    def _once_needs_name(self) -> Rule:
        if self.once and not self.name:
            raise ValueError("once=true requires a non-empty name")
        return self


def validate_rules(
    rules: list[dict] | None,
    *,
    slot: str,
) -> list[Rule]:
    """Validate and parse a list of rule dicts.

    Raises ``ValueError`` on the first failure so the caller can surface it as
    E202/E203/E204 at spec-save time.
    """
    if not rules:
        return []
    if not isinstance(rules, list):
        raise ValueError(f"{slot}: rules must be a list, got {type(rules).__name__}")
    out: list[Rule] = []
    seen_names: set[str] = set()
    for idx, raw in enumerate(rules):
        if not isinstance(raw, dict):
            raise ValueError(f"{slot}[{idx}]: rule must be a dict, got {type(raw).__name__}")
        name = str(raw.get("name") or f"rule_{idx}")
        if name in seen_names:
            raise ValueError(f"{slot}: duplicate rule name {name!r}")
        seen_names.add(name)
        when = raw.get("when")
        if not isinstance(when, dict):
            raise ValueError(f"{slot}[{idx}] ({name}): 'when' must be a bool AST dict")
        then = raw.get("then")
        if not isinstance(then, list) or not then:
            raise ValueError(f"{slot}[{idx}] ({name}): 'then' must be a non-empty list of actions")
        try:
            rule = Rule.model_validate(
                {
                    "name": name,
                    "priority": raw.get("priority", 0),
                    "once": raw.get("once", False),
                    "when": when,
                    "then": then,
                    "tag": raw.get("tag"),
                    "description": raw.get("description"),
                }
            )
        except Exception as exc:
            raise ValueError(f"{slot}[{idx}] ({name}): {exc}") from exc
        allowed = _slot_actions(slot)
        for action in rule.then:
            if action.type not in allowed:
                raise ValueError(
                    f"{slot}[{idx}] ({name}): action {action.type!r} is not valid "
                    f"in this slot — allowed: {sorted(allowed)}"
                )
        out.append(rule)
    return out


# Re-export the action classes for convenience.
__all__ = [
    "ACTION_REGISTRY",
    "ACTION_TERMINAL",
    "ActionBase",
    "ActionSpec",
    "CoercedOperand",
    "PCM_ACTIONS",
    "RISK_ACTIONS",
    "ActionNode",
    "Add",
    "ArmCooldown",
    "CapWeight",
    "Displace",
    "Enter",
    "Phase",
    "RatchetStop",
    "Resize",
    "Rule",
    "SetFlag",
    "Skip",
    "Trim",
    "action_vocabulary",
    "validate_phases",
    "validate_rules",
]
