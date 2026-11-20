"""Strategy authoring models and deterministic compiler for SigmaRail."""

from .compiler import compile_pipeline, compile_pipeline_prefix, compile_portfolio
from .decompiler import decompile_pipeline, decompile_portfolio
from .field_registry import FACTOR_REGISTRY, FactorInfo, list_factors, resolve_factor
from .pcm_bindings import PCM_BINDING_NAMESPACES
from .pcm_ladder import (
    generate_default_size_expr,
    generate_order_expr,
    generate_pcm_ladder,
    generate_scale_expr,
    generate_slots_expr,
)
from .position_bindings import POSITION_BINDINGS
from .pipeline import (
    AllocationPolicy,
    ExecutionConfig,
    ExitTranche,
    FilterCondition,
    FilterGroup,
    FilterNode,
    HedgeConfig,
    HedgeInstrument,
    ModelRef,
    PerformanceOverlay,
    PipelineBindings,
    PipelineDocument,
    PolicyOverride,
    PolicyRule,
    PolicyRuleRole,
    POLICY_OVERRIDE_KEYS,
    PortfolioDocument,
    PyramidPhase,
    RegimeOverlay,
    RiskConfig,
    RiskRule,
    RiskRuleType,
    SelectionRule,
    SizingConfig,
    SizingPolicy,
    SlotExpr,
    Stage,
    StageType,
    UniverseConfig,
    UniverseSource,
    VolTargetOverlay,
    bindings_to_policy_rules,
    champion_default_bindings,
    champion_default_policy_rules,
    policy_rules_to_bindings,
)
from .regime_gate import RegimeGateEvaluator, RegimeGateV1
from .presets import PRESET_METADATA, PRESETS, get_preset, list_presets
from .risk_ladder import generate_default_init_stop, generate_swing_risk_ladder
from .setup_recipes import (
    SETUP_RECIPES,
    apply_setup_recipe,
    compose_minervini_sepa_with_setup,
    get_setup_recipe,
    list_setup_recipes,
)

__all__ = [
    "AllocationPolicy", "ExecutionConfig", "ExitTranche", "FACTOR_REGISTRY",
    "FactorInfo", "FilterCondition", "FilterGroup", "FilterNode", "HedgeConfig",
    "HedgeInstrument", "ModelRef", "PerformanceOverlay", "PipelineBindings",
    "PipelineDocument", "PolicyOverride", "PolicyRule", "PolicyRuleRole",
    "POLICY_OVERRIDE_KEYS", "PortfolioDocument", "PyramidPhase", "RegimeGateEvaluator",
    "RegimeGateV1", "RegimeOverlay", "RiskConfig", "RiskRule", "RiskRuleType",
    "PCM_BINDING_NAMESPACES", "POSITION_BINDINGS",
    "PRESETS", "PRESET_METADATA",
    "SETUP_RECIPES", "SelectionRule", "SizingConfig", "SizingPolicy", "SlotExpr",
    "Stage", "StageType", "UniverseConfig", "UniverseSource", "VolTargetOverlay",
    "apply_setup_recipe", "bindings_to_policy_rules", "champion_default_bindings",
    "champion_default_policy_rules", "compile_pipeline", "compile_pipeline_prefix",
    "compile_portfolio", "compose_minervini_sepa_with_setup", "decompile_pipeline",
    "decompile_portfolio", "get_preset", "get_setup_recipe", "list_factors", "list_presets", "list_setup_recipes",
    "policy_rules_to_bindings", "resolve_factor", "generate_default_init_stop",
    "generate_default_size_expr", "generate_order_expr", "generate_pcm_ladder",
    "generate_scale_expr", "generate_slots_expr",
    "generate_swing_risk_ladder",
]
