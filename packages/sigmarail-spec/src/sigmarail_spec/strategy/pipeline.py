"""Staged pipeline document model: the user-facing strategy representation.

A ``PipelineDocument`` is a directed sequence of stages. Each stage is one of
``filter`` / ``screener`` / ``score`` / ``signal`` / ``watch`` / ``pyramid`` /
``hedge`` / ``exit`` and compiles into the VeraLabV1 framework slots (see
``compiler.py``).

The document is JSON-serialized Pydantic — no YAML, no intermediary format.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sigmarail_spec.universe_query import UniverseQueryV1
from .regime_gate import RegimeGateV1


class StageType(str, Enum):
    FILTER = "filter"
    SCORE = "score"
    SIGNAL = "signal"
    CONFIRM = "confirm"  # meta-labeling: a secondary gate over the signal
    WATCH = "watch"
    PYRAMID = "pyramid"
    HEDGE = "hedge"
    EXIT = "exit"


class ModelRef(BaseModel):
    """An explicit LEAN model reference — the flexible-slot primitive.

    Any slot (Universe / Alpha / PortfolioConstruction / RiskManagement /
    Execution) can be filled either by a *named concept* (compiled to a known
    LEAN class) or by a raw ``ModelRef`` naming *any* LEAN class — including new
    ones we author — with its ``parameters`` passed through verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    parameters: dict = Field(default_factory=dict)


class FilterCondition(BaseModel):
    """A single boolean filter: ``{op: gt, left: close, right: 10}``.

    ``left`` is a column name string or an Operand dict.
    ``right`` is a literal, a column name (with ``right_kind: col``), or an Operand dict.
    ``expr`` is an optional human-readable formula string.
    ``id`` is a stable chip identity for agent patch ops.
    ``annotation`` is UI/agent provenance (stripped before SQL WHERE).
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal["gt", "gte", "lt", "lte", "eq", "neq"] = "gte"
    left: str | dict
    right: float | int | str | bool | dict
    right_kind: Literal["lit", "col", "formula"] = "lit"
    expr: str | None = None
    id: str | None = None
    annotation: dict | None = None


class FilterGroup(BaseModel):
    """A boolean group (AND / OR) of filter conditions and/or sub-groups."""

    model_config = ConfigDict(extra="forbid")

    logic: Literal["and", "or"] = "and"
    name: str | None = None
    conditions: list[FilterNode] = Field(default_factory=list)


class FilterNot(BaseModel):
    """A negated filter subtree, in the document's own terms.

    The compiled where-AST has always been able to express `not`, but the document model
    could only hold one negated shape — `neq`, i.e. `not(eq(...))`. Every other `not` was
    silently rewritten as a *positive* AND of its child, so "not above the 50-day" loaded
    back as "above the 50-day": the negation inverted. This node keeps it explicit.
    """

    model_config = ConfigDict(extra="forbid")

    item: FilterNode


FilterNode = FilterCondition | FilterGroup | FilterNot
FilterGroup.model_rebuild()
FilterNot.model_rebuild()


class FactorWeight(BaseModel):
    """One weighted factor in a score/watch stage."""

    model_config = ConfigDict(extra="forbid")

    name: str  # semantic factor name (resolved via field_registry)
    weight: float = Field(gt=0, le=1.0)


class SelectionRule(BaseModel):
    """How scored candidates are selected."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["top_n", "top_n_per_sector", "threshold"] = "top_n"
    n: int | None = Field(default=None, ge=1)
    sectors: int | None = Field(default=None, ge=1)
    per_sector: int | None = Field(default=None, ge=1)
    min_score: float | None = None

    @model_validator(mode="after")
    def _shape(self) -> "SelectionRule":
        if self.method == "top_n" and self.n is None:
            raise ValueError("top_n selection requires n")
        if self.method == "top_n_per_sector" and (self.sectors is None or self.per_sector is None):
            raise ValueError("top_n_per_sector selection requires sectors and per_sector")
        if self.method == "threshold" and self.min_score is None:
            raise ValueError("threshold selection requires min_score")
        return self


class EntryTrigger(BaseModel):
    """A specific entry signal condition."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "pivot_breakout",
        "pullback_to_sma",
        "vcp_complete",
        "rsi_cross",
        "macd",
        "ema_cross",
        "breakout",
    ]
    # pivot breakout / breakout (swing)
    lookback_days: int | None = None
    volume_multiplier: float | None = None
    consolidation_days: int | None = None
    volume_surge_multiplier: float | None = None
    leader_rs_threshold: float | None = None
    # pullback / moving-average
    sma_period: int | None = None
    max_deviation_pct: float | None = None
    # vcp
    contraction_count: int | None = None
    # oscillators (rsi / macd / ema)
    period: int | None = None
    fast_period: int | None = None
    slow_period: int | None = None
    signal_period: int | None = None
    oversold: float | None = None
    overbought: float | None = None


class StopLossRule(BaseModel):
    """Initial stop-loss placement."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["atr", "fixed_pct"] = "atr"
    multiplier: float | None = Field(default=None, gt=0)
    pct: float | None = Field(default=None, gt=0)
    initial_risk_pct: float | None = Field(default=None, gt=0, le=1.0)
    max_stop_loss_pct: float | None = Field(
        default=None,
        gt=0,
        le=1.0,
        description="Cap on ATR stop distance as fraction of entry (e.g. 0.05 = 5%)",
    )


class PyramidPhase(BaseModel):
    """One phase of progressive position scaling (test -> add -> full)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    size_pct: float = Field(gt=0, le=1.0)
    risk_pct: float | None = Field(default=None, gt=0, le=1.0)
    trigger: dict | None = None  # free-form trigger; validated downstream


class ExitTranche(BaseModel):
    """One profit-taking tranche (sell into strength)."""

    model_config = ConfigDict(extra="forbid")

    trigger_r: float = Field(gt=0)  # R-multiple trigger
    sell_pct: float = Field(ge=0, le=1.0)  # 0 = degenerate tranche in legacy specs
    stop_ratchet: str = "BE"  # BE | +1R | +2R | +4R | None


class HedgeInstrument(BaseModel):
    """One hedge instrument (inverse ETF)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    max_allocation: float = Field(gt=0, le=1.0)


class HedgeConfig(BaseModel):
    """Portfolio hedge configuration during risk-off regimes."""

    model_config = ConfigDict(extra="forbid")

    instruments: list[HedgeInstrument] = Field(default_factory=list)
    trigger: Literal["regime_risk_off"] = "regime_risk_off"
    unwind: dict | None = None


class RiskRuleType(str, Enum):
    """Stackable risk rules (mapped to LEAN risk models)."""

    PROGRESSIVE = "progressive"
    TRAILING = "trailing"
    MAX_DRAWDOWN = "max_drawdown"
    SECTOR_EXPOSURE = "sector_exposure"


class RiskRule(BaseModel):
    """One risk rule; multiple rules compile to ``CompositeRiskManagementModel``."""

    model_config = ConfigDict(extra="forbid")

    type: RiskRuleType
    # progressive
    take_profit_r: float | None = Field(default=None, gt=0)
    trailing_stop_pct: float | None = Field(default=None, gt=0, le=1.0)
    max_holding_days: int | None = Field(default=None, ge=1)
    # trailing / max_drawdown
    maximum_drawdown_percent: float | None = Field(default=None, gt=0)
    # sector exposure
    maximum_sector_exposure: float | None = Field(default=None, gt=0, le=1.0)


class RiskConfig(BaseModel):
    """Portfolio-level risk controls."""

    model_config = ConfigDict(extra="forbid")

    circuit_breaker: dict | None = None
    regime_gate: RegimeGateV1 | dict | None = None
    max_positions: int | None = Field(default=None, ge=1)
    max_sector_exposure: float | None = Field(default=None, gt=0, le=1.0)
    rules: list[RiskRule] = Field(default_factory=list)
    model: ModelRef | None = None  # raw LEAN risk class passthrough (overrides rules)
    time_stop_skip_if: dict | None = Field(
        default=None,
        description="Risk binding: skip breakeven time-stop when e.g. above_entry and named bools.",
    )


class ExecutionConfig(BaseModel):
    """Order execution method."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["market_order", "vwap", "std_dev", "immediate"] = "market_order"
    fill_session: Literal["moo", "moc"] = "moo"
    model: ModelRef | None = None  # raw LEAN execution class passthrough


class StageDocumentation(BaseModel):
    """Structured documentation for a pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    inputs: list[str] = Field(default_factory=list)
    expression: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    confirmation: str | None = None
    effect: str | None = None
    notes: str | None = None


_STAGE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class Stage(BaseModel):
    """One pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    name: str
    id: str | None = Field(
        default=None,
        description="Stable binding id (screen_1, setup_pass). Defaults to slug of name.",
    )
    mode: StageType
    depends_on: str | None = None
    filters: list[FilterNode] = Field(default_factory=list)
    factors: list[FactorWeight] = Field(default_factory=list)
    selection: SelectionRule | None = None
    entry_triggers: list[EntryTrigger] = Field(default_factory=list)
    phases: list[PyramidPhase] = Field(default_factory=list)
    tranches: list[ExitTranche] = Field(default_factory=list)
    instruments: list[HedgeInstrument] = Field(default_factory=list)
    max_candidates: int | None = Field(default=None, ge=1)
    max_positions: int | None = Field(default=None, ge=1)
    stop_loss: StopLossRule | None = None
    max_hold_days: int | None = Field(default=None, ge=1)
    trailing_stop_pct: float | None = Field(default=None, gt=0, le=1.0)
    stop_cooldown_days: int | None = Field(default=None, ge=0)
    add_trigger_pct: float | None = Field(default=None, ge=0, le=1.0)
    atr_stop_multiplier: float | None = Field(default=None, gt=0)
    max_stop_loss_pct: float | None = Field(default=None, gt=0, le=1.0)
    use_atr_stops: bool | None = None
    breakeven_time_stop_days: int | None = Field(default=None, ge=1)
    max_single_weight: float | None = Field(default=None, gt=0, le=1.0)
    breakeven_r_trigger: float | None = Field(default=None, gt=0)
    as_gate: bool = False
    count_as_signal: bool = True
    signal_weight: float = Field(
        default=1.0,
        gt=0,
        description="Weight for count_as_signal gates in screens_hit_w (unweighted screens_hit stays Σ 1).",
    )
    computed_expr: dict | None = Field(
        default=None,
        description=(
            "Number Operand AST for Universe.computed[] (kind=number, expr=…). "
            "Authors aggregate measure aliases / L7 cols; not a gate bool."
        ),
    )
    measure_filter: FilterCondition | None = Field(
        default=None,
        description=(
            "Optional exclude-if filter on this measure alias → Universe.post_where. "
            "Independent of Insight ✓ / ORDER BY."
        ),
    )
    optional_score_fields: list[str] = Field(default_factory=list)
    optional_min: dict[str, float] = Field(default_factory=dict)
    omit_tt: bool = False
    require_flag: str | None = None
    rules: list[dict] = Field(
        default_factory=list,
        description=(
            "Ordered rule-driven control flow (C-FW-RULES): alpha stages carry "
            "their entries in Alpha.Parameters.stages; exit-stage rules compile "
            "to RiskManagement.Parameters.rules."
        ),
    )
    init_stop: dict | None = Field(
        default=None,
        description=(
            "Initial-stop Operand AST (C-VERA-EXPR-V2): exit-stage value "
            "compiles to RiskManagement.Parameters.init_stop."
        ),
    )
    documentation: StageDocumentation = Field(default_factory=StageDocumentation)

    @model_validator(mode="after")
    def _validate_id(self) -> "Stage":
        if self.id is not None and not _STAGE_ID_RE.match(self.id):
            raise ValueError(
                f"stage id {self.id!r} must match {_STAGE_ID_RE.pattern}"
            )
        return self


Stage.model_rebuild()


class PipelineDocumentation(BaseModel):
    """Structured documentation for the pipeline."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    purpose: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    version: str | None = None


class SlotExpr(BaseModel):
    """Bool or number expression over the Alpha computed + L7 column bag.

    Bool slots use the same ``vera_bool_expr`` / where AST as stage filters.
    Number slots use Operand / formula AST (``col`` / ``lit`` / ``formula``).
    ``__position.*`` cols are runtime-only (Risk); not probeable.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bool", "number"]
    where: dict | None = None
    expr: dict | None = None

    @model_validator(mode="after")
    def _kind_payload(self) -> "SlotExpr":
        if self.kind == "bool" and self.where is None:
            raise ValueError("bool SlotExpr requires where AST")
        if self.kind == "number" and self.expr is None:
            raise ValueError("number SlotExpr requires expr AST")
        return self


PolicyRuleRole = Literal[
    "alpha_eligibility",
    "alpha_setup",
    "alpha_confidence",
    "pcm_allow_entry",
    "pcm_scale",
    "risk_skip_time_stop",
    "risk_allow_pyramid_add",
]

_BOOL_POLICY_ROLES: tuple[PolicyRuleRole, ...] = (
    "alpha_eligibility",
    "alpha_setup",
    "pcm_allow_entry",
    "risk_skip_time_stop",
    "risk_allow_pyramid_add",
)

_NUMBER_POLICY_ROLES: tuple[PolicyRuleRole, ...] = (
    "alpha_confidence",
    "pcm_scale",
)


class PolicyRule(BaseModel):
    """One policy-rule chain link: role + SlotExpr payload (Studio SSOT)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    role: PolicyRuleRole
    slot: SlotExpr


# Allowlisted knob names for PolicyOverride.set (PCM + Risk). Last matching override wins.
POLICY_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "risk_per_trade_pct",
        "max_position_weight",
        "trailing_stop_pct",
        "atr_stop_multiplier",
        "breakeven_time_stop_days",
        "max_holding_days",
        "max_hold_days",
    }
)


class PolicyOverride(BaseModel):
    """Conditional knob override: when bool chips match, set allowlisted PCM/Risk params.

    Applied in chain order at runtime (last-wins per param). Knobs on sizing/exit
    stages remain defaults.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    when: SlotExpr
    set: dict[str, float | int | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _when_bool_and_allowlist(self) -> "PolicyOverride":
        if self.when.kind != "bool":
            raise ValueError("PolicyOverride.when must be kind=bool")
        unknown = sorted(k for k in self.set if k not in POLICY_OVERRIDE_KEYS)
        if unknown:
            raise ValueError(
                f"PolicyOverride.set unknown keys {unknown}; "
                f"allowlist={sorted(POLICY_OVERRIDE_KEYS)}"
            )
        if not self.set:
            raise ValueError("PolicyOverride.set must be non-empty")
        return self


class PipelineBindings(BaseModel):
    """Named slot expressions compiled onto Alpha / PCM / Risk Parameters.

    Authored here (with stages); never persisted as a whole-strategy
    ``VeraBase.Pipeline`` blob (C-STRATEGY-PIPELINE-SSOT).
    """

    model_config = ConfigDict(extra="forbid")

    alpha_eligibility: SlotExpr | None = None
    alpha_setup: SlotExpr | None = None
    alpha_rank: list[str] | None = None
    alpha_rank_directions: dict[str, Literal["asc", "desc"]] | None = Field(
        default=None,
        description="Optional ASC/DESC per alpha_rank field (default desc).",
    )
    alpha_confidence: SlotExpr | None = None
    alpha_direction: SlotExpr | None = None
    alpha_magnitude: SlotExpr | None = None
    alpha_weight: SlotExpr | None = None
    alpha_insight_period_days: int | None = Field(
        default=None,
        description="Insight.Period in days (default 1 when unset).",
        ge=1,
    )
    pcm_scale: SlotExpr | None = None
    pcm_allow_entry: SlotExpr | None = None
    risk_skip_time_stop: SlotExpr | None = None
    risk_allow_pyramid_add: SlotExpr | None = None


def _merge_bool_wheres(wheres: list[dict]) -> dict | None:
    """AND-merge vera_bool_expr where ASTs (``all`` / ``items``)."""
    items = [w for w in wheres if w]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return {"type": "all", "items": items}


def champion_default_bindings(
    *,
    min_screens: int = 1,
    min_rs_rating: float | None = None,
    rank_by_rs: bool = False,
    setup_col: str = "setup_pass",
    hit_col: str = "screens_hit",
    rank_tie: str = "rs_rating",
    scale_denom: float = 5.0,
    include_setup: bool = True,
    direction_col: str = "insight_dir",
    magnitude_col: str = "mag_thrust",
    weight_col: str = "w_conviction",
    confidence_col: str = "conf_scale",
    insight_period_days: int = 1,
) -> PipelineBindings:
    """Champion preset expressions (not compiler name inference).

    ``include_setup=False`` for the bare ``minervini_sepa`` seed (setup applied via
    ``setup_recipes.compose_minervini_sepa_with_setup``).

    Insight properties bind to Measure aliases authored in the preset stages
    (``insight_dir``, ``mag_thrust``, ``w_conviction``, ``conf_scale``).
    """
    min_n = max(1, int(min_screens))
    hit_ref = {"type": "col", "name": hit_col}
    setup_eq = {
        "type": "eq",
        "left": {"type": "col", "name": setup_col},
        "right": {"type": "lit", "value": 1},
    }
    if min_rs_rating is not None:
        eligibility_where = {
            "type": "any",
            "items": [
                {
                    "type": "gte",
                    "left": hit_ref,
                    "right": {"type": "lit", "value": min_n},
                },
                {
                    "type": "gte",
                    "left": {"type": "col", "name": rank_tie},
                    "right": {"type": "lit", "value": float(min_rs_rating)},
                },
            ],
        }
    else:
        eligibility_where = {
            "type": "gte",
            "left": hit_ref,
            "right": {"type": "lit", "value": min_n},
        }

    if rank_by_rs:
        alpha_rank = [rank_tie, hit_col]
        alpha_rank_directions = {rank_tie: "desc", hit_col: "desc"}
    else:
        alpha_rank = [hit_col, rank_tie]
        alpha_rank_directions = {hit_col: "desc", rank_tie: "desc"}

    skip_stop = {
        "type": "gt",
        "left": {"type": "col", "name": "__position.price"},
        "right": {"type": "col", "name": "__position.entry"},
    }
    return PipelineBindings(
        alpha_eligibility=SlotExpr(kind="bool", where=eligibility_where),
        alpha_setup=SlotExpr(kind="bool", where=setup_eq) if include_setup else None,
        alpha_rank=alpha_rank,
        alpha_rank_directions=alpha_rank_directions,
        alpha_direction=SlotExpr(
            kind="number", expr={"type": "col", "name": direction_col}
        ),
        alpha_magnitude=SlotExpr(
            kind="number", expr={"type": "col", "name": magnitude_col}
        ),
        alpha_weight=SlotExpr(
            kind="number", expr={"type": "col", "name": weight_col}
        ),
        alpha_confidence=SlotExpr(
            kind="number", expr={"type": "col", "name": confidence_col}
        ),
        alpha_insight_period_days=max(1, int(insight_period_days)),
        # pcm_scale left empty: Champion sizes via Insight.Confidence (honor_insight).
        risk_skip_time_stop=SlotExpr(kind="bool", where=skip_stop),
    )


def champion_default_policy_rules(
    *,
    min_screens: int = 1,
    min_rs_rating: float | None = None,
    rank_by_rs: bool = False,
    setup_col: str = "setup_pass",
    hit_col: str = "screens_hit",
    rank_tie: str = "rs_rating",
    scale_denom: float = 5.0,
    include_setup: bool = True,
) -> list[PolicyRule]:
    """Champion preset policy chain (same semantics as ``champion_default_bindings``)."""
    bindings = champion_default_bindings(
        min_screens=min_screens,
        min_rs_rating=min_rs_rating,
        rank_by_rs=rank_by_rs,
        setup_col=setup_col,
        hit_col=hit_col,
        rank_tie=rank_tie,
        scale_denom=scale_denom,
        include_setup=include_setup,
    )
    rules: list[PolicyRule] = []
    if bindings.alpha_eligibility is not None:
        rules.append(
            PolicyRule(
                id="eligibility",
                label="Screen hit floor",
                role="alpha_eligibility",
                slot=bindings.alpha_eligibility,
            )
        )
    if bindings.alpha_setup is not None:
        rules.append(
            PolicyRule(
                id="setup",
                label="Setup pass",
                role="alpha_setup",
                slot=bindings.alpha_setup,
            )
        )
    if bindings.alpha_confidence is not None:
        rules.append(
            PolicyRule(
                id="confidence",
                label="Confidence ← conf_scale",
                role="alpha_confidence",
                slot=bindings.alpha_confidence,
            )
        )
    if bindings.risk_skip_time_stop is not None:
        rules.append(
            PolicyRule(
                id="risk_skip_time_stop",
                label="Skip time stop above entry",
                role="risk_skip_time_stop",
                slot=bindings.risk_skip_time_stop,
            )
        )
    return rules


def policy_rules_to_bindings(
    rules: list[PolicyRule],
    base: PipelineBindings | None = None,
) -> PipelineBindings:
    """Fold an ordered policy-rule chain into flat ``PipelineBindings``.

    Bool roles: AND-merge ``where`` ASTs per role (``type: all``).
    Number roles: last rule wins for ``expr``.
    ``alpha_rank`` / ``alpha_rank_directions`` are preserved from ``base`` when present.
    """
    by_role: dict[PolicyRuleRole, list[PolicyRule]] = {}
    for rule in rules:
        by_role.setdefault(rule.role, []).append(rule)

    out = PipelineBindings()
    if base is not None and base.alpha_rank:
        out.alpha_rank = list(base.alpha_rank)
    if base is not None and base.alpha_rank_directions:
        out.alpha_rank_directions = dict(base.alpha_rank_directions)
    # Insight property bindings are authored on PipelineBindings (not PolicyRule roles).
    if base is not None:
        out.alpha_direction = base.alpha_direction
        out.alpha_magnitude = base.alpha_magnitude
        out.alpha_weight = base.alpha_weight
        out.alpha_insight_period_days = base.alpha_insight_period_days

    for role in _BOOL_POLICY_ROLES:
        role_rules = by_role.get(role, [])
        if role_rules:
            merged = _merge_bool_wheres(
                [r.slot.where for r in role_rules if r.slot.where is not None]
            )
            if merged is not None:
                setattr(out, role, SlotExpr(kind="bool", where=merged))
        elif base is not None:
            setattr(out, role, getattr(base, role))

    for role in _NUMBER_POLICY_ROLES:
        role_rules = by_role.get(role, [])
        if role_rules:
            last = role_rules[-1]
            if last.slot.expr is not None:
                setattr(out, role, SlotExpr(kind="number", expr=last.slot.expr))
        elif base is not None:
            setattr(out, role, getattr(base, role))

    if base is not None and out.alpha_rank is None and base.alpha_rank:
        out.alpha_rank = list(base.alpha_rank)
    if base is not None and out.alpha_rank_directions is None and base.alpha_rank_directions:
        out.alpha_rank_directions = dict(base.alpha_rank_directions)

    return out


def bindings_to_policy_rules(bindings: PipelineBindings) -> list[PolicyRule]:
    """Best-effort inverse: flat bindings → ordered policy-rule chain."""
    labels: dict[PolicyRuleRole, str] = {
        "alpha_eligibility": "Eligibility",
        "alpha_setup": "Setup",
        "alpha_confidence": "Confidence scale",
        "pcm_allow_entry": "Allow entry",
        "pcm_scale": "PCM scale",
        "risk_skip_time_stop": "Skip time stop",
        "risk_allow_pyramid_add": "Allow pyramid add",
    }
    order: list[PolicyRuleRole] = [
        "alpha_eligibility",
        "alpha_setup",
        "alpha_confidence",
        "pcm_allow_entry",
        "pcm_scale",
        "risk_skip_time_stop",
        "risk_allow_pyramid_add",
    ]
    rules: list[PolicyRule] = []
    for role in order:
        slot = getattr(bindings, role)
        if slot is None:
            continue
        rules.append(
            PolicyRule(
                id=role,
                label=labels.get(role),
                role=role,
                slot=slot,
            )
        )
    return rules


class PipelineDocument(BaseModel):
    """Top-level staged strategy document (a single leg of a portfolio)."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    stages: list[Stage] = Field(default_factory=list)  # empty when alpha is a raw passthrough
    gate_combine: str | None = None
    min_screens: int | None = Field(default=None, ge=1)
    min_rs_rating: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_by_rs: bool = Field(default=True)
    max_entry_atr_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    universe: UniverseConfig = Field(default_factory=lambda: UniverseConfig())
    sizing: SizingConfig = Field(default_factory=lambda: SizingConfig())
    alpha: ModelRef | None = None  # raw LEAN alpha class passthrough (overrides stages)
    hedge: HedgeConfig | None = None
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    documentation: PipelineDocumentation = Field(default_factory=PipelineDocumentation)
    bindings: PipelineBindings | None = None
    policy_rules: list[PolicyRule] = Field(default_factory=list)
    policy_overrides: list[PolicyOverride] = Field(default_factory=list)
    regime_gate: dict | None = Field(
        default=None,
        description=(
            "Cross-slot regime policy → VeraBase.DataSources.regime + uses[] "
            "routed to PCM/Alpha. Preferred home; risk.regime_gate is the "
            "deprecated pre-migration location."
        ),
    )

    @model_validator(mode="after")
    def _stage_names_unique(self) -> "PipelineDocument":
        names = [s.name for s in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("stage names must be unique")
        return self

    @model_validator(mode="after")
    def _depends_on_valid(self) -> "PipelineDocument":
        names = {s.name for s in self.stages}
        for s in self.stages:
            if s.depends_on is not None and s.depends_on not in names:
                raise ValueError(
                    f"stage {s.name!r} depends_on {s.depends_on!r} which is not a stage name"
                )
        return self


# --- Portfolio layer (Level 2): ensemble + dynamic allocation --------------

class UniverseSource(str, Enum):
    SCREENER = "screener"
    MANUAL = "manual"
    COMPOSITE = "composite"


class UniverseConfig(BaseModel):
    """Which securities a strategy runs over."""

    model_config = ConfigDict(extra="forbid")

    source: UniverseSource = UniverseSource.SCREENER
    symbols: list[str] = Field(default_factory=list)
    select: list[str] | None = None  # explicit select columns (must satisfy required columns)
    screen: list[FilterNode] = Field(default_factory=list)
    limit_per_day: int | None = Field(default=None, ge=1)
    model: ModelRef | None = None  # raw LEAN universe class passthrough


class SizingPolicy(str, Enum):
    ATR_RISK = "atr_risk"
    RISK_BUDGETED = "risk_budgeted"
    RISK_PARITY = "risk_parity"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    EQUAL_WEIGHT = "equal_weight"


class SizingConfig(BaseModel):
    """Position-sizing policy (maps to a LEAN portfolio-construction model)."""

    model_config = ConfigDict(extra="forbid")

    policy: SizingPolicy = SizingPolicy.ATR_RISK
    max_positions: int | None = Field(default=None, ge=1)
    max_weight: float | None = Field(default=None, gt=0, le=1.0)
    min_weight: float | None = Field(default=None, gt=0, le=1.0)
    target_atr_risk: float | None = Field(default=None, gt=0)
    risk_per_trade_pct: float | None = Field(default=None, gt=0)
    rebalance: str | None = None
    use_regime_scaling: bool | None = None
    min_regime_fraction: float | None = Field(default=None, ge=0, le=1.0)
    regime_neutral_fraction: float | None = Field(default=None, ge=0, le=1.0)
    regime_bull_fraction: float | None = Field(default=None, ge=0, le=1.0)
    scaled_max_positions_floor: int | None = Field(default=None, ge=0)
    honor_insight_confidence: bool | None = None
    allow_adds_on_invested: bool | None = None
    default_stop_loss_pct: float | None = Field(default=None, ge=0, le=1.0)
    enable_displacement: bool | None = None
    displacement_min_hold_days: int | None = Field(default=None, ge=1)
    displacement_max_incumbent_r: float | None = Field(default=None)
    displacement_min_challenger_rs: float | None = Field(default=None, ge=0, le=100.0)
    displacement_min_challenger_screens: int | None = Field(default=None, ge=0)
    displacement_immune_rs: float | None = Field(default=None, ge=0, le=100.0)
    enable_surrogates: bool | None = None
    surrogate_sizing_mode: str | None = None
    prefer_capital_efficient_surrogates: bool | None = None
    min_surrogate_adv: float | None = None
    rules: list[dict] = Field(
        default_factory=list,
        description=(
            "Unified rules pass (C-FW-RULES): ordered rule table over insight "
            "candidates + insight-quiet holdings → PCM Parameters.rules."
        ),
    )
    size_expr: dict | None = Field(
        default=None,
        description="Base sizing Operand AST → PCM Parameters.size_expr.",
    )
    scale_expr: dict | None = Field(
        default=None,
        description="Book-level scale AST → PCM Parameters.scale_expr.",
    )
    slots_expr: dict | None = Field(
        default=None,
        description="Book-level slot-count AST → PCM Parameters.slots_expr.",
    )
    order_expr: dict | None = Field(
        default=None,
        description="Unit ordering-key AST → PCM Parameters.order_expr.",
    )
    model: ModelRef | None = None  # raw LEAN PCM class passthrough


class RegimeOverlay(BaseModel):
    """Regime-conditional exposure. ``map`` reweights legs per regime;
    ``global_exposure`` scales the whole book (Minervini)."""

    model_config = ConfigDict(extra="forbid")

    signal: str = "technical_breadth"  # technical_breadth | economic_environment | <custom>
    map: dict[str, dict[str, float]] = Field(default_factory=dict)
    global_exposure: dict[str, float] | None = None


class PerformanceOverlay(BaseModel):
    """Performance-adaptive allocation (strategy momentum / drawdown control)."""

    model_config = ConfigDict(extra="forbid")

    metric: Literal["trailing_return", "sharpe"] = "trailing_return"
    lookback_days: int = Field(gt=0)
    floor: float = Field(default=0.0, ge=0.0, le=1.0)
    ceiling: float = Field(default=1.0, gt=0.0, le=1.0)
    rebalance_days: int = Field(default=1, ge=1)


class VolTargetOverlay(BaseModel):
    """Volatility targeting — scale the book to a target vol."""

    model_config = ConfigDict(extra="forbid")

    target_vol: float = Field(gt=0)
    band: float = Field(default=0.02, ge=0)


class AllocationPolicy(BaseModel):
    """Composable allocation stack: base allocator + regime + performance + vol."""

    model_config = ConfigDict(extra="forbid")

    base: Literal["weights", "risk_parity", "hrp", "black_litterman"] = "weights"
    weights: dict[str, float] = Field(default_factory=dict)  # leg name -> weight
    rebalance: str = "weekly"  # daily | weekly | monthly (PCM rebalance cadence)
    regime: RegimeOverlay | None = None
    performance: PerformanceOverlay | None = None
    vol_target: VolTargetOverlay | None = None


class PortfolioDocument(BaseModel):
    """One model, one persistence: N legs + an allocation policy.

    A single-leg portfolio with default allocation is equivalent to the legacy
    ``PipelineDocument`` (which remains the per-leg document).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    legs: list[PipelineDocument] = Field(min_length=1)
    allocation: AllocationPolicy = Field(default_factory=AllocationPolicy)

    @model_validator(mode="after")
    def _leg_names_unique(self) -> "PortfolioDocument":
        names = [leg.strategy_name for leg in self.legs]
        if len(names) != len(set(names)):
            raise ValueError("leg strategy names must be unique")
        return self
