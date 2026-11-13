"""Typed Parameters per allowlisted LeanFrameworkV1 Type (plan §8.5 — Phase-1 slice).

Unknown Type values skip shape validation here; interpreter allowlist still applies at wire time.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManualUniverseSelectionModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str]


class RsiAlphaModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: int = Field(ge=1)
    resolution: str = Field(min_length=1)


class ConstantAlphaModelParams(BaseModel):
    """QC ConstantAlphaModel — long all universe members for equal-weight hybrids."""

    model_config = ConfigDict(extra="forbid")

    period_days: int = Field(default=30, ge=1)
    magnitude: float = Field(default=0.02, gt=0)


class EqualWeightingPortfolioConstructionModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rebalance: str | None = None


class ImmediateExecutionModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NullRiskManagementModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaximumDrawdownPercentPerSecurityParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maximum_drawdown_percent: float = Field(gt=0, le=1.0)


class HighRoeUniverseSelectionModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_assets_per_month: int = Field(default=2, ge=1, le=20)
    min_market_cap_millions: float = Field(default=500.0, gt=0)
    min_ipo_days: int = Field(default=180, ge=0)


class VeraCompositeAlphaModelParams(BaseModel):
    """Parameters for VeraCompositeAlphaModel — multi-factor weighted z-score blending."""

    model_config = ConfigDict(extra="forbid")

    max_positions: int = Field(default=10, ge=1, le=100)
    min_hold_days: int = Field(default=5, ge=1)
    stop_loss_pct: float = Field(default=0.05, ge=0, le=1.0)
    stop_cooldown_days: int = Field(default=10, ge=0)
    circuit_drawdown_threshold: float = Field(default=0.10, ge=0, le=1.0)
    circuit_pause_days: int = Field(default=20, ge=0)
    hold_buffer_rank: int = Field(default=30, ge=0)
    field_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "rs_rating": 0.40,
            "valuation_rating": 0.20,
            "mrt_roe": 0.20,
            "perf_1y": 0.20,
        },
        description="{column_name: weight} — columns must be in the VeraBase.Universe select clause",
    )
    setup_where: dict | None = Field(
        default=None,
        description="Entry-signal AST; not membership pushdown",
    )
    gates: list[dict] = Field(
        default_factory=list,
        description="Parallel score/where evaluations; union before setup_where",
    )
    membership: dict | None = Field(
        default=None,
        description="Legacy Alpha copy; runtime prefers UniverseSelection.Parameters.membership",
    )
    named_groups: dict[str, dict] = Field(
        default_factory=dict,
        description="Legacy Alpha copy; runtime prefers UniverseSelection.Parameters.named_groups",
    )
    stages: list[dict] = Field(
        default_factory=list,
        description="Alpha-card stages (filter/score/signal/pyramid) for Studio round-trip",
    )
    uses: list[str] = Field(
        default_factory=list,
        description="Regime uses this Alpha honors",
    )


class VeraPyramidAlphaModelParams(BaseModel):
    """Parameters for VeraPyramidAlphaModel — progressive entry scaling."""

    model_config = ConfigDict(extra="forbid")

    max_positions: int = Field(default=10, ge=1, le=100)
    min_hold_days: int = Field(default=5, ge=1)
    stop_loss_pct: float = Field(default=0.05, ge=0, le=1.0)
    stop_cooldown_days: int = Field(default=10, ge=0)
    field_weights: dict[str, float] = Field(default_factory=lambda: {"rs_rating": 1.0})
    selection: dict = Field(default_factory=lambda: {"method": "top_n", "n": 10})
    entry_triggers: list[dict] = Field(default_factory=list)
    stop_loss: dict | None = Field(default=None)
    # Screen ASTs live on UniverseSelection; these fields accept legacy Alpha copies
    membership: dict | None = Field(
        default=None,
        description="Legacy Alpha copy; interpreter injects UniverseSelection.Parameters.membership when omitted",
    )
    named_groups: dict[str, dict] = Field(
        default_factory=dict,
        description="Legacy Alpha copy; interpreter injects UniverseSelection.Parameters.named_groups when omitted",
    )
    stages: list[dict] = Field(
        default_factory=list,
        description="Alpha-card stages (filter/score/signal/pyramid) for Studio round-trip",
    )
    uses: list[str] = Field(
        default_factory=list,
        description="Regime uses this Alpha honors (block_new_longs)",
    )
    setup_where: dict | None = Field(
        default=None,
        description="Entry-signal AST; not membership pushdown",
    )
    gates: list[dict] = Field(
        default_factory=list,
        description="Parallel evaluations from as_gate score stages; union or count before setup_where",
    )
    gate_combine: str = Field(
        default="union",
        description='How to combine gate hits: "union" (top_k union) or "count" (screens_hit rank)',
    )
    min_screens: int = Field(
        default=1,
        ge=0,
        description="Minimum screens_hit when gate_combine is count",
    )
    # Legacy IR may still send phases / add_trigger_pct on Alpha — ignore at runtime.
    phases: list[dict] | None = Field(
        default=None,
        description="Deprecated: scale-in phases now live on RiskBudgeted PCM Parameters",
    )
    add_trigger_pct: float | None = Field(
        default=None,
        ge=0,
        le=1.0,
        description="Deprecated: add_trigger_pct now lives on RiskBudgeted PCM Parameters",
    )
    setup_col: str | None = Field(
        default=None,
        description="SQL bool column for setup (setup_pass); preferred over setup_where when present on row",
    )
    setup_expr: dict | None = Field(
        default=None,
        description="Bool SlotExpr AST for setup gate (preferred over setup_col when set)",
    )
    eligibility_expr: dict | None = Field(
        default=None,
        description="Bool SlotExpr AST for shortlist eligibility floor",
    )
    confidence_expr: dict | None = Field(
        default=None,
        description="Number SlotExpr AST for Insight.Confidence (e.g. screens_hit/5)",
    )
    direction_expr: dict | None = Field(
        default=None,
        description="Number SlotExpr → Int8 Direction (1 Up / -1 Down / 0 Flat)",
    )
    magnitude_expr: dict | None = Field(
        default=None,
        description="Number SlotExpr for Insight.Magnitude (signed; from Measures)",
    )
    weight_expr: dict | None = Field(
        default=None,
        description="Number SlotExpr for Insight.Weight (0–1 hint; from Measures)",
    )
    insight_period_days: int | None = Field(
        default=None,
        ge=1,
        description="Insight.Period in calendar days (default 1)",
    )
    risk_allow_pyramid_add_expr: dict | None = Field(
        default=None,
        description="Deprecated: prefer PCM risk_allow_pyramid_add_expr",
    )
    row_rank: dict | None = Field(
        default=None,
        description="Rank binding: {by: [screens_hit, ...], min: {screens_hit: N}}",
    )
    row_scale_denom: float | None = Field(
        default=None,
        gt=0,
        description="Denominator for Insight.Confidence = screens_hit / denom (Champion: 5)",
    )
    max_entry_atr_pct: float = Field(
        default=3.5,
        ge=0,
        description=(
            "Skip new entries when L7 atr_14_pct (absolute percent of close) "
            "exceeds this. 0 disables the cap."
        ),
    )


class VeraScreenerExecutionModelParams(BaseModel):
    """Parameters for VeraScreenerExecutionModel daily fill."""

    model_config = ConfigDict(extra="forbid")

    fill_session: str = Field(
        default="moo",
        description=(
            "moo = market_on_open_order scheduled BeforeMarketOpen(30); "
            "moc = market_on_close_order scheduled BeforeMarketClose(10). "
            "Minutes must be >0 so the order is submitted while the auction is still open. "
            "Python Lean has no MarketOnOpen attribute."
        ),
    )


class VeraHedgeModelParams(BaseModel):
    """Parameters for VeraHedgeModel — inverse ETF deployment."""

    model_config = ConfigDict(extra="forbid")

    instruments: list[dict] = Field(
        default_factory=lambda: [{"ticker": "SH", "max_allocation": 0.25}],
    )


_LEAN_FRAMEWORK_V1_PARAMETER_MODELS: dict[str, type[BaseModel]] = {
    "ManualUniverseSelectionModel": ManualUniverseSelectionModelParams,
    "RsiAlphaModel": RsiAlphaModelParams,
    "ConstantAlphaModel": ConstantAlphaModelParams,
    "EqualWeightingPortfolioConstructionModel": EqualWeightingPortfolioConstructionModelParams,
    "ImmediateExecutionModel": ImmediateExecutionModelParams,
    "NullRiskManagementModel": NullRiskManagementModelParams,
    "MaximumDrawdownPercentPerSecurity": MaximumDrawdownPercentPerSecurityParams,
    "HighRoeQualityUniverseSelectionModel": HighRoeUniverseSelectionModelParams,
    "VeraCompositeAlphaModel": VeraCompositeAlphaModelParams,
    "VeraPyramidAlphaModel": VeraPyramidAlphaModelParams,
    "VeraScreenerExecutionModel": VeraScreenerExecutionModelParams,
    "VeraHedgeModel": VeraHedgeModelParams,
}


def lean_framework_v1_pydantic_type_ids() -> frozenset[str]:
    """`Type` strings with a Pydantic `Parameters` model in this module (IR validation)."""

    return frozenset(_LEAN_FRAMEWORK_V1_PARAMETER_MODELS.keys())


def validate_slot_parameters_for_type(type_id: str, parameters: dict[str, Any] | None) -> None:
    """
    Validate Parameters dict for a known Phase-1 Type; no-op for unknown types.

    Raises pydantic.ValidationError on mismatch.
    """
    tid = (type_id or "").strip()
    model = _LEAN_FRAMEWORK_V1_PARAMETER_MODELS.get(tid)
    if model is None:
        return
    model.model_validate(parameters or {})
