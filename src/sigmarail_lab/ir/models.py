from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sigmarail_spec import BoolExprItem, validate_bool_expr_depth
from .screener_columns import SORTABLE_COLUMNS, ScreenerColumn

# --- Pipeline sections (explicit; no hidden trading defaults) ---


class MetaBlock(BaseModel):
    """Non-authoritative metadata; does not replace required pipeline fields."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    rebalance: str | None = None
    rebalance_corridor_width: float | None = None
    oos_start_date: str | None = None


class UniverseSpec(BaseModel):
    """Logical daily_screener universe: legacy flat fields and/or explicit criteria AST.

    ``source`` stays ``daily_screener``; compiled SQL joins L7 ``screener_*`` tables.
    """

    source: Literal["screener_price_tech_daily", "screener", "daily_screener"] = "screener_price_tech_daily"
    spine: str | None = "screener_price_tech_daily"
    joins: list[dict[str, Any]] | None = None
    criteria: BoolExprItem | None = None
    projection: list[ScreenerColumn] | None = Field(
        default=None,
        description=(
            "daily_screener SELECT columns. If omitted, default is ticker + overall_score + "
            "atr_14_pct only (no OHLC in the result set). Filters may still use close/volume. "
            "Set explicitly to pull extra columns (e.g. close, sma200d) for custom logic."
        ),
    )

    min_close: float | None = Field(default=None, ge=0)
    min_volume: int | None = Field(default=None, ge=0)
    require_has_vcp_setup: bool = True
    require_is_stage_2_advancing: bool = True
    min_minervini_tt_score_full: float | None = None
    limit_per_day: int | None = Field(default=None, ge=1, le=500)
    always_include_tickers: list[str] = Field(
        default_factory=lambda: ["SPY"],
        description="Always include these tickers (e.g. SPY for benchmark/regime).",
    )
    sort_field: ScreenerColumn = Field(default=ScreenerColumn.OVERALL_SCORE)
    sort_direction: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def _universe_shape(self) -> UniverseSpec:
        if self.sort_field not in SORTABLE_COLUMNS:
            raise ValueError(f"sort_field {self.sort_field!r} is not sortable")
        if self.criteria is not None:
            validate_bool_expr_depth(self.criteria)
            if self.limit_per_day is None:
                raise ValueError("limit_per_day is required when criteria is set")
            return self
        missing: list[str] = []
        if self.min_close is None:
            missing.append("min_close")
        if self.min_volume is None:
            missing.append("min_volume")
        if self.min_minervini_tt_score_full is None:
            missing.append("min_minervini_tt_score_full")
        if self.limit_per_day is None:
            missing.append("limit_per_day")
        if missing:
            raise ValueError(
                f"legacy universe requires {missing} when criteria is omitted"
            )
        return self

    def to_screener_range_sql(self, start_date_iso: str, end_date_iso: str) -> str:
        """Bulk backtest load SQL for daily_screener (LIMIT n BY date)."""
        from .query_compile import compile_screener_range_query

        return compile_screener_range_query(self, start_date_iso, end_date_iso)

    def to_screener_single_day_sql(self, today_iso: str) -> str:
        """Single-calendar-day universe SQL for live reload."""
        from .query_compile import compile_screener_single_day_query

        return compile_screener_single_day_query(self, today_iso)


class AlphaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_positions: int = Field(ge=1, le=100)
    min_hold_days: int = Field(ge=0, le=365)
    stop_loss_pct: float = Field(ge=0, le=1)
    stop_cooldown_days: int = Field(ge=0, le=365)
    circuit_drawdown_threshold: float = Field(ge=0, le=1)
    circuit_pause_days: int = Field(ge=1, le=365)
    field_weights: dict[str, float] | None = Field(
        default=None,
        description="Multi-factor column weights for VeraCompositeAlphaModel",
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
    setup_where: dict | None = Field(
        default=None,
        description="Entry-signal AST; not membership pushdown",
    )
    gates: list[dict] = Field(
        default_factory=list,
        description="Parallel evaluations from as_gate score stages",
    )


class PortfolioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_positions: int = Field(ge=1, le=100)
    max_weight: float = Field(gt=0, le=1)
    min_weight: float = Field(gt=0, le=1)
    target_atr_risk: float = Field(gt=0, le=0.1)
    # C-REGIME-POLICY-V1 thermostat + hold policy knobs
    uses: list[str] = Field(default_factory=list)
    hold_policy: str | None = Field(default=None)
    max_total_exposure: float | None = Field(default=None, gt=0, le=1)
    exit_when_no_bars: bool | None = Field(default=None)
    enable_surrogates: bool | None = Field(
        default=False,
        description="Route eligible single-stock insights to leveraged ETF surrogates",
    )
    surrogate_sizing_mode: str | None = Field(
        default="dollar_risk_parity",
        description="Sizing mode for leveraged surrogates: dollar_risk_parity (1/leverage) or nominal",
    )
    prefer_capital_efficient_surrogates: bool | None = Field(
        default=True,
        description="Allow surrogate entry when available cash is below full stock weight but sufficient for surrogate",
    )
    min_surrogate_adv: float | None = Field(
        default=1_000_000,
        description="Minimum average dollar volume for surrogate routing safety floor",
    )


class SectorAlphaSpec(BaseModel):
    """Parameter schema for VeraSectorAlphaModel."""

    model_config = ConfigDict(extra="forbid")

    sector_top_n: int = Field(default=4, ge=1, le=20)
    stocks_per_sector: int = Field(default=5, ge=1, le=50)
    min_hold_days: int = Field(default=5, ge=0, le=365)
    stop_loss_pct: float = Field(default=0.05, ge=0, le=1)
    stop_cooldown_days: int = Field(default=10, ge=0, le=365)
    circuit_drawdown_threshold: float = Field(default=0.10, ge=0, le=1)
    circuit_pause_days: int = Field(default=20, ge=1, le=365)


class SectorPortfolioSpec(BaseModel):
    """Parameter schema for VeraSectorPortfolioConstructionModel."""

    model_config = ConfigDict(extra="forbid")

    sector_top_n: int = Field(default=4, ge=1, le=20)
    stocks_per_sector: int = Field(default=5, ge=1, le=50)
    max_total_exposure: float = Field(default=0.90, gt=0, le=1)
    max_weight_per_stock: float = Field(default=0.12, gt=0, le=1)
    min_weight: float = Field(default=0.02, gt=0, le=1)
    target_atr_risk: float = Field(default=0.003, gt=0, le=0.1)


class SectorEtfAlphaSpec(BaseModel):
    """Parameter schema for VeraSectorEtfAlphaModel."""

    model_config = ConfigDict(extra="forbid")

    sector_long_n: int = Field(default=4, ge=1, le=11)
    sector_short_n: int = Field(default=3, ge=1, le=11)
    broad_inverse_etf: str = Field(default="SPXS")
    etf_map: dict[str, dict[str, str | None]] | None = Field(default=None)


class SectorEtfPortfolioSpec(BaseModel):
    """Parameter schema for VeraSectorEtfPortfolioConstructionModel."""

    model_config = ConfigDict(extra="forbid")

    max_long_exposure: float = Field(default=0.90, gt=0, le=1)
    max_inverse_exposure: float = Field(default=0.40, gt=0, le=1)
    max_weight_per_etf: float = Field(default=0.30, gt=0, le=1)
    min_weight: float = Field(default=0.05, gt=0, le=1)


class TqqqTacticalSpec(BaseModel):
    """Parameter schema for VeraTqqqTacticalAlphaModel / PCM (shared kwargs)."""

    model_config = ConfigDict(extra="forbid")

    signal_ticker: str = Field(default="QQQ")
    trade_ticker: str = Field(default="TQQQ")
    base_weight: float = Field(default=0.10, gt=0, le=1)
    max_weight: float = Field(default=0.20, gt=0, le=1)
    qqq_pullback_min: float = Field(default=0.05, ge=0, le=1)
    max_pct_from_sma20_entry: float = Field(default=0.08, ge=0, le=1)
    trim_pct_from_sma20: float = Field(default=0.10, ge=0, le=1)
    trim_fraction_on_reversal: float = Field(default=0.15, ge=0, le=1)
    exit_on_two_closes_below_sma20: bool = Field(default=True)
    exit_on_close_below_first_up_day_low: bool = Field(default=True)
    require_spy_bull: bool = Field(default=True)
    buyhold_mode: bool = Field(default=False)


class RegimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Prefer Vera-native naming over warehouse jargon ("mart").
    # Backward-compat: accept legacy "mart" and map to the canonical value.
    source: Literal["screener", "market_regime_signals_daily"]

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_source(cls, data: Any) -> Any:
        if isinstance(data, dict):
            src = data.get("source")
            if isinstance(src, str) and src.strip().lower() == "mart":
                data = dict(data)
                data["source"] = "market_regime_signals_daily"
        return data


class ExitsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["topn", "deterioration"]
    deterioration_loss_threshold: float = Field(
        default=0.02,
        ge=0,
        le=1,
        description="Used when mode=deterioration.",
    )


class LeanFrameworkSpec(BaseModel):
    """LEAN framework knobs for graph mode (Policy B); mirrors pipeline alpha/portfolio/regime/exits."""

    model_config = ConfigDict(extra="forbid")

    alpha: AlphaSpec
    portfolio: PortfolioSpec
    regime: RegimeSpec
    exits: ExitsSpec

    @model_validator(mode="after")
    def _positions(self) -> LeanFrameworkSpec:
        if self.alpha.max_positions != self.portfolio.max_positions:
            raise ValueError("alpha.max_positions must equal portfolio.max_positions")
        return self

    def lean_set_parameter_map(self) -> dict[str, str]:
        """Keys/values passed to QCAlgorithm.SetParameter for VeraScreenerAlphaModel.Update."""
        return {
            "regime-source": self.regime.source,
            "exit-mode": self.exits.mode,
            "deterioration-loss-threshold": str(self.exits.deterioration_loss_threshold),
        }

    def alpha_model_kwargs(self) -> dict[str, Any]:
        """Kwargs for VeraScreenerAlphaModel(store, **kwargs) after shared store is bound."""
        return cast(dict[str, Any], self.alpha.model_dump())

    def portfolio_model_kwargs(self) -> dict[str, Any]:
        """Kwargs for VeraScreenerPortfolioConstructionModel(store, **kwargs)."""
        return cast(dict[str, Any], self.portfolio.model_dump())


# --- Graph nodes ---


class SortFieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: ScreenerColumn
    direction: Literal["asc", "desc"]

    @model_validator(mode="after")
    def _sortable(self) -> SortFieldSpec:
        if self.field not in SORTABLE_COLUMNS:
            raise ValueError(f"sort field {self.field!r} is not sortable")
        return self


class FilterStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: Literal["filter"] = Field(alias="type")
    source: Literal["screener_price_tech_daily", "screener", "daily_screener"] = "screener_price_tech_daily"
    preset: str = ""
    sort: SortFieldSpec
    criteria: BoolExprItem | None = None
    projection: list[ScreenerColumn] | None = Field(
        default=None,
        description=(
            "Same as pipeline universe.projection: omit for default metrics-only SELECT; "
            "set to include OHLC or other columns when needed."
        ),
    )
    limit_per_day: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def _preset_xor_criteria(self) -> FilterStep:
        has_p = bool(self.preset and self.preset.strip())
        has_c = self.criteria is not None
        if has_p == has_c:
            raise ValueError(
                "filter requires exactly one of: non-empty preset, or inline criteria"
            )
        return self


class GroupStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: Literal["group"] = Field(alias="type")
    children: list["GraphStep"]


class WeightStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: Literal["weight"] = Field(alias="type")
    mode: Literal["equal", "specified"]
    children: list["GraphStep"] = Field(default_factory=list)
    weights: dict[str, str] | None = None


class IfStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: Literal["if"] = Field(alias="type")
    condition: BoolExprItem
    then: "GraphStep"
    else_: "GraphStep" = Field(alias="else")


class SelectStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: Literal["select"] = Field(alias="type")
    top_k: int = Field(ge=1)
    from_: "GraphStep" = Field(alias="from")


GraphStep = Annotated[
    Union[FilterStep, GroupStep, WeightStep, IfStep, SelectStep],
    Field(discriminator="step"),
]

GroupStep.model_rebuild()
WeightStep.model_rebuild()
IfStep.model_rebuild()
SelectStep.model_rebuild()


class VeraLab(BaseModel):
    """
    Unified algorithm JSON.
    Pipeline mode: root is null; universe, alpha, portfolio, regime, exits are set.
    Graph mode (Policy B): root is set; lean_framework is set; pipeline sections omitted.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, description="Bump only on breaking JSON changes.")
    meta: MetaBlock | None = None
    universe: UniverseSpec | None = None
    alpha: AlphaSpec | None = None
    portfolio: PortfolioSpec | None = None
    regime: RegimeSpec | None = None
    exits: ExitsSpec | None = None
    lean_framework: LeanFrameworkSpec | None = None
    root: Optional[GraphStep] = None

    @model_validator(mode="after")
    def _policy_and_required(self) -> VeraLab:
        if self.root is not None:
            if any(
                x is not None
                for x in (
                    self.universe,
                    self.alpha,
                    self.portfolio,
                    self.regime,
                    self.exits,
                )
            ):
                raise ValueError(
                    "Policy A: when 'root' is set, omit universe, alpha, portfolio, regime, exits"
                )
            if self.lean_framework is None:
                raise ValueError(
                    "Policy B: graph mode requires 'lean_framework' "
                    "(alpha, portfolio, regime, exits)"
                )
            return self
        if self.lean_framework is not None:
            raise ValueError(
                "lean_framework is only allowed when 'root' is set (graph mode)"
            )
        for name, sec in (
            ("universe", self.universe),
            ("alpha", self.alpha),
            ("portfolio", self.portfolio),
            ("regime", self.regime),
            ("exits", self.exits),
        ):
            if sec is None:
                raise ValueError(f"Pipeline mode requires '{name}'")
        assert self.alpha is not None and self.portfolio is not None
        if self.alpha.max_positions != self.portfolio.max_positions:
            raise ValueError("alpha.max_positions must equal portfolio.max_positions")
        return self

    def is_graph_mode(self) -> bool:
        return self.root is not None

    def effective_lean_framework(self) -> LeanFrameworkSpec:
        """Normalize pipeline vs graph mode to a single LeanFrameworkSpec."""
        if self.root is not None:
            if self.lean_framework is None:
                raise ValueError("graph mode requires lean_framework")
            return self.lean_framework
        assert self.alpha is not None
        assert self.portfolio is not None
        assert self.regime is not None
        assert self.exits is not None
        return LeanFrameworkSpec(
            alpha=self.alpha,
            portfolio=self.portfolio,
            regime=self.regime,
            exits=self.exits,
        )

    def effective_universe(self) -> dict[str, Any] | None:
        """Pipeline: validated universe. Graph: lowered universe_query_v1 or None if unsupported."""
        if self.root is None:
            if self.universe is None:
                return None
            raise ValueError(
                "Pipeline VeraLab universe was removed; use Kind VeraLabV1 with universe_query_v1"
            )
        from .graph_runtime import lower_graph_to_universe

        return lower_graph_to_universe(self.root)
