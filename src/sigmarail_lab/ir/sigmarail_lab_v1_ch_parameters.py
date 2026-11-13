"""ClickHouse runner framework slots for Kind VeraLabV1: Type allowlists + typed Parameters."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .lean_framework_json import FrameworkBundleV1
from .lean_framework_parameters import (
    ConstantAlphaModelParams,
    EqualWeightingPortfolioConstructionModelParams,
    HighRoeUniverseSelectionModelParams,
    ImmediateExecutionModelParams,
    ManualUniverseSelectionModelParams,
    MaximumDrawdownPercentPerSecurityParams,
    RsiAlphaModelParams,
    VeraCompositeAlphaModelParams,
    VeraPyramidAlphaModelParams,
)
from .models import (
    AlphaSpec,
    PortfolioSpec,
    SectorAlphaSpec,
    SectorEtfAlphaSpec,
    SectorEtfPortfolioSpec,
    SectorPortfolioSpec,
    TqqqTacticalSpec,
)
from .sigmarail_screener_framework_types import (
    ALLOWED_ALPHA_TYPES,
    ALLOWED_EXECUTION_TYPES,
    ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES,
    ALLOWED_UNIVERSE_SELECTION_TYPES,
    COMPOSITE_ALPHA,
    HIGH_ROE_UNIVERSE_SELECTION,
    PYRAMID_ALPHA,
    SECTOR_ALPHA,
    SECTOR_ETF_ALPHA,
    SECTOR_ETF_PORTFOLIO_CONSTRUCTION,
    SECTOR_PORTFOLIO_CONSTRUCTION,
    TQQQ_TACTICAL_ALPHA,
)

_CH_RISK = frozenset({
    "NullRiskManagementModel",
    "MaximumDrawdownPercentPerSecurity",
    "TrailingStopRiskManagementModel",
    "MaximumSectorExposureRiskManagementModel",
    "MaximumUnrealizedProfitPercentPerSecurity",
    "CompositeRiskManagementModel",
    "SwingProgressiveRiskManagementModel",
})

# VeraLabV1 hybrid & composite: store universe + stock QC types supported by runtime framework interpreter.
_HYBRID_ALPHA_TYPES = frozenset({
    "RsiAlphaModel",
    "ConstantAlphaModel",
    "MacdAlphaModel",
    "EmaCrossAlphaModel",
    "CompositeAlphaModel",
    "SwingBreakoutAlphaModel",
    "SwingPullbackAlphaModel",
})
_HYBRID_PORTFOLIO_TYPES = frozenset({
    "EqualWeightingPortfolioConstructionModel",
    "ConfidenceWeightedPortfolioConstructionModel",
    "InsightWeightingPortfolioConstructionModel",
    "RiskParityPortfolioConstructionModel",
    "SectorWeightingPortfolioConstructionModel",
    "RiskBudgetedPortfolioConstructionModel",
})
_HYBRID_EXECUTION_TYPES = frozenset({
    "ImmediateExecutionModel",
    "VolumeWeightedAveragePriceExecutionModel",
    "StandardDeviationExecutionModel",
})


class EmptyParameters(BaseModel):
    """ClickHouse plugin slots that take no JSON parameters (v1)."""

    model_config = ConfigDict(extra="forbid")


class VeraScreenerUniverseSelectionModelParams(BaseModel):
    """Universe screen tree (same ownership as Studio section 1)."""

    model_config = ConfigDict(extra="forbid")

    screen: dict | None = Field(
        default=None,
        description="Boolean where tree compiled from universe.screen (root all/any)",
    )
    hygiene_where: dict | None = Field(
        default=None,
        description="Legacy hygiene AST; omitted on new compiles",
    )
    membership: dict | None = Field(
        default=None,
        description="Derived named membership subtree for Alpha in_membership flags",
    )
    named_groups: dict[str, dict] = Field(
        default_factory=dict,
        description="Derived named group subtrees (e.g. code_33) for Alpha flags",
    )

def _assert_slot_type(slot: str, type_id: str, allowed: frozenset[str]) -> None:
    tid = (type_id or "").strip()
    if tid not in allowed:
        raise ValueError(
            f"VeraLabV1 {slot}: Type {type_id!r} is not allowlisted for the ClickHouse runner "
            f"(allowed: {sorted(allowed)})"
        )


def validate_sigmarail_lab_v1_framework_bundle(fb: FrameworkBundleV1) -> None:
    """
    Validate Framework bundle for main.py / ClickHouseUniverseAlgorithm.

    **Full screener-backed slots** — VeraScreener* (or legacy ScreenerStore* / ClickHouse*) Alpha, PCM, Execution + AlphaSpec /
    PortfolioSpec / empty execution params.

    **Hybrid / Composite** — store universe only; standard QC framework models (RSI, MACD, EMA Cross,
    ConfidenceWeighted, RiskParity, TrailingStop, VWAP, etc.) wired via LeanFrameworkInterpreter.

    Raises ValueError (wrapped as ValidationError by Pydantic when called from VeraLabV1Document).
    """
    _assert_slot_type(
        "Framework.UniverseSelection", fb.universe_selection.type, ALLOWED_UNIVERSE_SELECTION_TYPES
    )
    _assert_slot_type("Framework.RiskManagement", fb.risk_management.type, _CH_RISK)

    u_type = (fb.universe_selection.type or "").strip()
    if u_type == HIGH_ROE_UNIVERSE_SELECTION:
        HighRoeUniverseSelectionModelParams.model_validate(
            fb.universe_selection.parameters or {}
        )
    elif u_type == "ManualUniverseSelectionModel":
        ManualUniverseSelectionModelParams.model_validate(
            fb.universe_selection.parameters or {}
        )
    elif u_type in ("CompositeUniverseSelectionModel", "CoarseFundamentalUniverseSelectionModel"):
        pass
    elif u_type in (
        "VeraScreenerUniverseSelectionModel",
        "ScreenerStoreUniverseSelectionModel",
        "ClickHouseUniverseSelectionModel",
    ):
        VeraScreenerUniverseSelectionModelParams.model_validate(
            fb.universe_selection.parameters or {}
        )
    else:
        EmptyParameters.model_validate(fb.universe_selection.parameters or {})

    rtype = (fb.risk_management.type or "").strip()
    if rtype == "NullRiskManagementModel":
        EmptyParameters.model_validate(fb.risk_management.parameters or {})
    elif rtype == "MaximumDrawdownPercentPerSecurity":
        MaximumDrawdownPercentPerSecurityParams.model_validate(
            fb.risk_management.parameters or {}
        )

    a_type = (fb.alpha.type or "").strip()
    pcm_type = (fb.portfolio_construction.type or "").strip()
    exe_type = (fb.execution.type or "").strip()

    all_alpha_types = ALLOWED_ALPHA_TYPES | _HYBRID_ALPHA_TYPES
    all_pcm_types = ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES | _HYBRID_PORTFOLIO_TYPES
    all_exe_types = ALLOWED_EXECUTION_TYPES | _HYBRID_EXECUTION_TYPES

    _assert_slot_type("Framework.Alpha", a_type, all_alpha_types)
    _assert_slot_type("Framework.PortfolioConstruction", pcm_type, all_pcm_types)
    _assert_slot_type("Framework.Execution", exe_type, all_exe_types)

    # Composite / pyramid models have their own parameter schemas (field_weights,
    # phases, selection, entry_triggers) that differ from the legacy AlphaSpec.
    if a_type == COMPOSITE_ALPHA:
        VeraCompositeAlphaModelParams.model_validate(fb.alpha.parameters or {})
    elif a_type == PYRAMID_ALPHA:
        VeraPyramidAlphaModelParams.model_validate(fb.alpha.parameters or {})
    elif a_type in ALLOWED_ALPHA_TYPES:
        # Sector and ETF models use different parameter schemas — no max_positions cross-check.
        if a_type == SECTOR_ETF_ALPHA:
            SectorEtfAlphaSpec.model_validate(fb.alpha.parameters or {})
            if pcm_type in ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES:
                SectorEtfPortfolioSpec.model_validate(fb.portfolio_construction.parameters or {})
        elif a_type == SECTOR_ALPHA:
            SectorAlphaSpec.model_validate(fb.alpha.parameters or {})
            if pcm_type in ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES:
                SectorPortfolioSpec.model_validate(fb.portfolio_construction.parameters or {})
        elif a_type == TQQQ_TACTICAL_ALPHA:
            TqqqTacticalSpec.model_validate(fb.alpha.parameters or {})
            if pcm_type in ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES:
                TqqqTacticalSpec.model_validate(fb.portfolio_construction.parameters or {})
        else:
            AlphaSpec.model_validate(fb.alpha.parameters or {})
            if pcm_type in ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES:
                PortfolioSpec.model_validate(fb.portfolio_construction.parameters or {})
                a_max = AlphaSpec.model_validate(fb.alpha.parameters or {}).max_positions
                p_max = PortfolioSpec.model_validate(
                    fb.portfolio_construction.parameters or {}
                ).max_positions
                if a_max != p_max:
                    raise ValueError("alpha max_positions must equal portfolio max_positions")
    elif a_type == "ConstantAlphaModel":
        ConstantAlphaModelParams.model_validate(fb.alpha.parameters or {})
    elif a_type == "RsiAlphaModel":
        RsiAlphaModelParams.model_validate(fb.alpha.parameters or {})

    if pcm_type == "EqualWeightingPortfolioConstructionModel":
        EqualWeightingPortfolioConstructionModelParams.model_validate(
            fb.portfolio_construction.parameters or {}
        )
    if exe_type == "ImmediateExecutionModel":
        ImmediateExecutionModelParams.model_validate(fb.execution.parameters or {})
    return

    if a_type == "ConstantAlphaModel":
        ConstantAlphaModelParams.model_validate(fb.alpha.parameters or {})
    elif a_type == "RsiAlphaModel":
        RsiAlphaModelParams.model_validate(fb.alpha.parameters or {})
    if pcm_type == "EqualWeightingPortfolioConstructionModel":
        EqualWeightingPortfolioConstructionModelParams.model_validate(
            fb.portfolio_construction.parameters or {}
        )
    if exe_type == "ImmediateExecutionModel":
        ImmediateExecutionModelParams.model_validate(fb.execution.parameters or {})
