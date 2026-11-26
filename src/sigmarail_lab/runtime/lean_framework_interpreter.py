"""
Allowlisted interpreter: LeanFrameworkV1Document / FrameworkBundleV1 -> QCAlgorithm set_* wiring.

- **Lean-only** (`store is None`): standard QC `AlgorithmImports` models, ctor `Type(**params)`.
- **SigmaRail / ClickHouse extension** (`store` set): default registry pairs **store-backed** universe
  (and optional full store alpha/PCM/execution) with **standard QC** types where JSON uses
  LeanFrameworkV1 class names (hybrid ``SigmaRailStrategyV1``). Custom ``registry=`` keeps the older
  behavior (every Type maps to ``(store, params) -> instance``).

Uses QuantConnect Lean Python types at runtime. For unit tests, pass `registry=` stubs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sigmarail_lab.ir.lean_framework_json import FrameworkBundleV1, FrameworkSlotSpec, LeanFrameworkV1Document


class LeanFrameworkInterpreterError(RuntimeError):
    """Unknown Type, bad parameters, or missing AlgorithmImports (non-Lean host)."""


@dataclass(frozen=True)
class WiredFrameworkV1:
    """Concrete framework instances after wiring (for custom schedules / debugging)."""

    alpha: Any
    portfolio_construction: Any
    execution: Any
    risk_management: Any


def _resolution_from_name(name: str, resolution_cls: Any) -> Any:
    u = (name or "").strip().upper().replace("-", "_")
    if not hasattr(resolution_cls, u):
        raise LeanFrameworkInterpreterError(f"Unknown resolution {name!r}")
    return getattr(resolution_cls, u)


def _normalize_parameters(
    type_id: str,
    params: dict[str, Any],
    *,
    symbol_cls: Any,
    security_type_cls: Any,
    market_cls: Any,
    resolution_cls: Any,
) -> dict[str, Any]:
    """Map JSON-friendly parameters to Lean Python ctor kwargs."""
    if type_id in ("RsiAlphaModel", "MacdAlphaModel", "EmaCrossAlphaModel"):
        out = dict(params)
        if "resolution" in out and isinstance(out["resolution"], str):
            out["resolution"] = _resolution_from_name(out["resolution"], resolution_cls)
        # Normalize snake_case to camelCase kwargs for QC Python models if needed
        if "fast_period" in out:
            out["fastPeriod"] = int(out.pop("fast_period"))
        if "slow_period" in out:
            out["slowPeriod"] = int(out.pop("slow_period"))
        if "signal_period" in out:
            out["signalPeriod"] = int(out.pop("signal_period"))
        if "period" in out:
            out["period"] = int(out["period"])
        return out

    if type_id == "ConstantAlphaModel":
        # Map JSON knobs → QC ConstantAlphaModel(InsightType, InsightDirection, timedelta, magnitude, confidence)
        # Use PRICE/UP (QC Python convention); construct positionally in the wire path (no ``type=`` kwarg).
        from datetime import timedelta as _td

        try:
            from AlgorithmImports import InsightDirection, InsightType  # type: ignore
        except ImportError:
            return dict(params)
        period_days = int(params.get("period_days") or 30)
        magnitude = float(params.get("magnitude") or 0.02)
        insight_type = getattr(InsightType, "PRICE", None) or getattr(InsightType, "Price")
        insight_dir = getattr(InsightDirection, "UP", None) or getattr(InsightDirection, "Up")
        return {
            "_positional": (
                insight_type,
                insight_dir,
                _td(days=period_days),
                magnitude,
                None,
            )
        }

    if type_id in (
        "EqualWeightingPortfolioConstructionModel",
        "InsightWeightingPortfolioConstructionModel",
        "ConfidenceWeightedPortfolioConstructionModel",
        "RiskParityPortfolioConstructionModel",
        "SectorWeightingPortfolioConstructionModel",
    ):
        out: dict[str, Any] = {}
        if "rebalance" in params and isinstance(params["rebalance"], str):
            out["rebalance"] = _resolution_from_name(params["rebalance"], resolution_cls)
        elif "rebalance" in params:
            out["rebalance"] = params["rebalance"]
        if "portfolioBias" in params:
            out["portfolioBias"] = params["portfolioBias"]
        elif "portfolio_bias" in params:
            out["portfolioBias"] = params["portfolio_bias"]
        return out

    if type_id in (
        "MaximumDrawdownPercentPerSecurity",
        "TrailingStopRiskManagementModel",
    ):
        out = dict(params)
        val = out.get("maximum_drawdown_percent") if out.get("maximum_drawdown_percent") is not None else out.get("maximumDrawdownPercent")
        if val is not None:
            out = {"maximumDrawdownPercent": float(val)}
        return out

    if type_id == "MaximumSectorExposureRiskManagementModel":
        out = dict(params)
        val = out.get("maximum_sector_exposure") if out.get("maximum_sector_exposure") is not None else out.get("maximumSectorExposure")
        if val is not None:
            out = {"maximumSectorExposure": float(val)}
        return out

    if type_id == "MaximumUnrealizedProfitPercentPerSecurity":
        out = dict(params)
        val = out.get("maximum_unrealized_profit_percent") if out.get("maximum_unrealized_profit_percent") is not None else out.get("maximumUnrealizedProfitPercent")
        if val is not None:
            out = {"maximumUnrealizedProfitPercent": float(val)}
        return out

    if type_id == "StandardDeviationExecutionModel":
        out = dict(params)
        if "resolution" in out and isinstance(out["resolution"], str):
            out["resolution"] = _resolution_from_name(out["resolution"], resolution_cls)
        return out

    return dict(params)


def _default_lean_registry() -> dict[str, type]:
    try:
        from AlgorithmImports import (  # type: ignore[import-not-found]
            CompositeAlphaModel,
            CompositeRiskManagementModel,
            ConfidenceWeightedPortfolioConstructionModel,
            ConstantAlphaModel,
            EmaCrossAlphaModel,
            EqualWeightingPortfolioConstructionModel,
            ImmediateExecutionModel,
            InsightWeightingPortfolioConstructionModel,
            MacdAlphaModel,
            MaximumDrawdownPercentPerSecurity,
            MaximumSectorExposureRiskManagementModel,
            MaximumUnrealizedProfitPercentPerSecurity,
            NullRiskManagementModel,
            RiskParityPortfolioConstructionModel,
            RsiAlphaModel,
            SectorWeightingPortfolioConstructionModel,
            StandardDeviationExecutionModel,
            TrailingStopRiskManagementModel,
            VolumeWeightedAveragePriceExecutionModel,
        )
    except ImportError as e:
        raise LeanFrameworkInterpreterError(
            "AlgorithmImports not available (run inside Lean / QC container)"
        ) from e

    from .qc_swing_alpha import SwingBreakoutAlphaModel, SwingPullbackAlphaModel
    from .qc_risk_budgeted_pcm import RiskBudgetedPortfolioConstructionModel
    from .qc_swing_risk import SwingProgressiveRiskManagementModel

    return {
        "CompositeAlphaModel": CompositeAlphaModel,
        "CompositeRiskManagementModel": CompositeRiskManagementModel,
        "RsiAlphaModel": RsiAlphaModel,
        "MacdAlphaModel": MacdAlphaModel,
        "EmaCrossAlphaModel": EmaCrossAlphaModel,
        "ConstantAlphaModel": ConstantAlphaModel,
        "SwingBreakoutAlphaModel": SwingBreakoutAlphaModel,
        "SwingPullbackAlphaModel": SwingPullbackAlphaModel,
        "EqualWeightingPortfolioConstructionModel": EqualWeightingPortfolioConstructionModel,
        "InsightWeightingPortfolioConstructionModel": InsightWeightingPortfolioConstructionModel,
        "ConfidenceWeightedPortfolioConstructionModel": ConfidenceWeightedPortfolioConstructionModel,
        "RiskParityPortfolioConstructionModel": RiskParityPortfolioConstructionModel,
        "SectorWeightingPortfolioConstructionModel": SectorWeightingPortfolioConstructionModel,
        "RiskBudgetedPortfolioConstructionModel": RiskBudgetedPortfolioConstructionModel,
        "ImmediateExecutionModel": ImmediateExecutionModel,
        "VolumeWeightedAveragePriceExecutionModel": VolumeWeightedAveragePriceExecutionModel,
        "StandardDeviationExecutionModel": StandardDeviationExecutionModel,
        "MaximumDrawdownPercentPerSecurity": MaximumDrawdownPercentPerSecurity,
        "TrailingStopRiskManagementModel": TrailingStopRiskManagementModel,
        "MaximumSectorExposureRiskManagementModel": MaximumSectorExposureRiskManagementModel,
        "MaximumUnrealizedProfitPercentPerSecurity": MaximumUnrealizedProfitPercentPerSecurity,
        "SwingProgressiveRiskManagementModel": SwingProgressiveRiskManagementModel,
        "NullRiskManagementModel": NullRiskManagementModel,
    }


# Keep in sync with keys of ``_default_lean_registry()``.
_DEFAULT_STOCK_LEAN_WIRED_TYPE_IDS: frozenset[str] = frozenset(
    {
        "CompositeAlphaModel",
        "CompositeRiskManagementModel",
        "RsiAlphaModel",
        "MacdAlphaModel",
        "EmaCrossAlphaModel",
        "ConstantAlphaModel",
        "SwingBreakoutAlphaModel",
        "SwingPullbackAlphaModel",
        "EqualWeightingPortfolioConstructionModel",
        "InsightWeightingPortfolioConstructionModel",
        "ConfidenceWeightedPortfolioConstructionModel",
        "RiskParityPortfolioConstructionModel",
        "SectorWeightingPortfolioConstructionModel",
        "RiskBudgetedPortfolioConstructionModel",
        "ImmediateExecutionModel",
        "VolumeWeightedAveragePriceExecutionModel",
        "StandardDeviationExecutionModel",
        "MaximumDrawdownPercentPerSecurity",
        "TrailingStopRiskManagementModel",
        "MaximumSectorExposureRiskManagementModel",
        "MaximumUnrealizedProfitPercentPerSecurity",
        "SwingProgressiveRiskManagementModel",
        "NullRiskManagementModel",
    }
)


def default_stock_lean_wired_type_ids() -> frozenset[str]:
    """
    `Type` ids constructible via the stock Lean class registry (no SigmaRail store in ctor).
    When ``AlgorithmImports`` is unavailable, falls back to a static frozenset.
    """

    try:
        return frozenset(_default_lean_registry().keys())
    except LeanFrameworkInterpreterError:
        return _DEFAULT_STOCK_LEAN_WIRED_TYPE_IDS


def all_default_wirable_type_ids() -> frozenset[str]:
    """
    `Type` ids the default `wire_framework_bundle_v1` registries accept (stock Lean + SigmaRail store
    plugin ids + hybrid risk). Used for discovery / ``sigmarail_lab_wired``; does not require Lean import.
    """

    from ..ir import sigmarail_screener_framework_types as t

    out: set[str] = set(default_stock_lean_wired_type_ids())
    out |= t.ALLOWED_ALPHA_TYPES
    out |= t.ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES
    out |= t.ALLOWED_EXECUTION_TYPES
    out |= {
        "NullRiskManagementModel",
        "MaximumDrawdownPercentPerSecurity",
        "SigmaRailRiskManagementModel",
    }
    return frozenset(out)


def _default_sigmarail_store_builders() -> dict[str, Callable[[Any, dict[str, Any]], Any]]:
    """(store, parameters_dict) -> model instance."""
    try:
        from AlgorithmImports import (  # type: ignore[import-not-found]
            MaximumDrawdownPercentPerSecurity,
            NullRiskManagementModel,
        )
    except ImportError as e:
        raise LeanFrameworkInterpreterError(
            "AlgorithmImports not available (run inside Lean / QC container)"
        ) from e

    from .qc_sigmarail_screener_framework import (
        SigmaRailCompositeAlphaModel,
        SigmaRailRiskManagementModel,
        SigmaRailScreenerAlphaModel,
        SigmaRailScreenerExecutionModel,
        SigmaRailScreenerPortfolioConstructionModel,
    )
    from .qc_pyramid_alpha import SigmaRailPyramidAlphaModel
    from .qc_hedge_model import SigmaRailHedgeModel
    from .qc_sector_allocation import (
        SigmaRailSectorAlphaModel,
        SigmaRailSectorPortfolioConstructionModel,
    )
    from .qc_sector_etf import (
        SigmaRailSectorEtfAlphaModel,
        SigmaRailSectorEtfPortfolioConstructionModel,
    )
    from .qc_graph_policy import (
        SigmaRailGraphPolicyAlphaModel,
        SigmaRailGraphPolicyPortfolioConstructionModel,
    )
    from .qc_tqqq_tactical import (
        SigmaRailTqqqTacticalAlphaModel,
        SigmaRailTqqqTacticalPortfolioConstructionModel,
    )
    from .qc_swing_alpha import (
        SwingBreakoutAlphaModel,
        SwingPullbackAlphaModel,
    )
    from .qc_risk_budgeted_pcm import (
        RiskBudgetedPortfolioConstructionModel,
    )
    from .qc_performance_pcm import PerformanceWeightedPortfolioConstructionModel
    from .qc_vol_target_pcm import VolatilityTargetingPortfolioConstructionModel
    from .qc_regime_weighted_pcm import RegimeWeightedPortfolioConstructionModel
    from .qc_swing_risk import (
        SwingProgressiveRiskManagementModel,
    )
    from sigmarail_lab.ir.sigmarail_screener_framework_types import (
        ALPHA,
        COMPOSITE_ALPHA,
        EXECUTION,
        HEDGE_RISK,
        PYRAMID_ALPHA,
        PORTFOLIO_CONSTRUCTION,
        PERFORMANCE_PORTFOLIO_CONSTRUCTION,
        VOL_TARGET_PORTFOLIO_CONSTRUCTION,
        REGIME_WEIGHTED_PORTFOLIO_CONSTRUCTION,
        SECTOR_ALPHA,
        SECTOR_ETF_ALPHA,
        SECTOR_ETF_PORTFOLIO_CONSTRUCTION,
        SECTOR_PORTFOLIO_CONSTRUCTION,
        GRAPH_POLICY_ALPHA,
        GRAPH_POLICY_PORTFOLIO_CONSTRUCTION,
        TQQQ_TACTICAL_ALPHA,
        TQQQ_TACTICAL_PORTFOLIO_CONSTRUCTION,
    )

    def _alpha(s: Any, p: dict[str, Any]) -> Any:
        return SigmaRailScreenerAlphaModel(s, **p)

    def _pcm(s: Any, p: dict[str, Any]) -> Any:
        return SigmaRailScreenerPortfolioConstructionModel(s, **p)

    def _exe(s: Any, p: dict[str, Any]) -> Any:
        return SigmaRailScreenerExecutionModel(s, **(p or {}))

    return {
        ALPHA: _alpha,
        COMPOSITE_ALPHA: lambda s, p: SigmaRailCompositeAlphaModel(s, **p),
        PYRAMID_ALPHA: lambda s, p: SigmaRailPyramidAlphaModel(s, **p),
        PORTFOLIO_CONSTRUCTION: _pcm,
        EXECUTION: _exe,
        SECTOR_ALPHA: lambda s, p: SigmaRailSectorAlphaModel(s, **p),
        SECTOR_PORTFOLIO_CONSTRUCTION: lambda s, p: SigmaRailSectorPortfolioConstructionModel(s, **p),
        SECTOR_ETF_ALPHA: lambda s, p: SigmaRailSectorEtfAlphaModel(s, **p),
        SECTOR_ETF_PORTFOLIO_CONSTRUCTION: lambda s, p: SigmaRailSectorEtfPortfolioConstructionModel(s, **p),
        GRAPH_POLICY_ALPHA: lambda s, p: SigmaRailGraphPolicyAlphaModel(s, **p),
        GRAPH_POLICY_PORTFOLIO_CONSTRUCTION: lambda s, p: SigmaRailGraphPolicyPortfolioConstructionModel(
            s, **p
        ),
        TQQQ_TACTICAL_ALPHA: lambda s, p: SigmaRailTqqqTacticalAlphaModel(s, **p),
        TQQQ_TACTICAL_PORTFOLIO_CONSTRUCTION: lambda s, p: SigmaRailTqqqTacticalPortfolioConstructionModel(
            s, **p
        ),
        "SwingBreakoutAlphaModel": lambda s, p: SwingBreakoutAlphaModel(store=s, **p) if "store" not in p else SwingBreakoutAlphaModel(**p),
        "SwingPullbackAlphaModel": lambda s, p: SwingPullbackAlphaModel(store=s, **p) if "store" not in p else SwingPullbackAlphaModel(**p),
        "RiskBudgetedPortfolioConstructionModel": lambda s, p: RiskBudgetedPortfolioConstructionModel(store=s, **p) if "store" not in p else RiskBudgetedPortfolioConstructionModel(**p),
        "PerformanceWeightedPortfolioConstructionModel": lambda s, p: PerformanceWeightedPortfolioConstructionModel(store=s, **p) if "store" not in p else PerformanceWeightedPortfolioConstructionModel(**p),
        "VolatilityTargetingPortfolioConstructionModel": lambda s, p: VolatilityTargetingPortfolioConstructionModel(store=s, **p) if "store" not in p else VolatilityTargetingPortfolioConstructionModel(**p),
        "RegimeWeightedPortfolioConstructionModel": lambda s, p: RegimeWeightedPortfolioConstructionModel(store=s, **p) if "store" not in p else RegimeWeightedPortfolioConstructionModel(**p),
        "SwingProgressiveRiskManagementModel": lambda s, p: SwingProgressiveRiskManagementModel(store=s, **p) if "store" not in p else SwingProgressiveRiskManagementModel(**p),
        HEDGE_RISK: lambda s, p: SigmaRailHedgeModel(s, **p),
        "NullRiskManagementModel": lambda s, p: NullRiskManagementModel(),
        # Strategy authors always name the fixed SigmaRail risk slot. An empty
        # rule set has the explicit no-risk behavior; rules remain slot data.
        "SigmaRailRiskManagementModel": lambda s, p: _build_sigmarail_risk_model(p, s),
        "MaximumDrawdownPercentPerSecurity": lambda s, p: MaximumDrawdownPercentPerSecurity(**p),
    }


def _build_sigmarail_risk_model(parameters: dict[str, Any], store: Any) -> Any:
    """Translate declarative SigmaRail risk rules to the fixed internal risk adapter."""
    rules = parameters.get("rules")
    if not isinstance(rules, list):
        raise LeanFrameworkInterpreterError(
            "SigmaRailRiskManagementModel.Parameters.rules must be a list"
        )
    from AlgorithmImports import (  # type: ignore[import-not-found]
        MaximumSectorExposureRiskManagementModel,
        MaximumUnrealizedProfitPercentPerSecurity,
        RiskManagementModel,
        TrailingStopRiskManagementModel,
        MaximumDrawdownPercentPerSecurity,
    )

    from .qc_swing_risk import SwingProgressiveRiskManagementModel
    from .qc_hedge_model import SigmaRailHedgeModel

    factories = {
        "trailing_stop": TrailingStopRiskManagementModel,
        "max_drawdown_per_security": MaximumDrawdownPercentPerSecurity,
        "max_sector_exposure": MaximumSectorExposureRiskManagementModel,
        "max_unrealized_profit_per_security": MaximumUnrealizedProfitPercentPerSecurity,
    }
    models = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise LeanFrameworkInterpreterError("risk rule entries must be objects")
        kind = str(rule.get("kind") or "")
        rule_params = dict(rule.get("parameters") or {})
        if kind == "progressive":
            models.append(SwingProgressiveRiskManagementModel(store=store, **rule_params))
        elif kind == "hedge":
            models.append(SigmaRailHedgeModel(store, **rule_params))
        elif kind in factories:
            models.append(factories[kind](**rule_params))
        else:
            raise LeanFrameworkInterpreterError(f"unsupported SigmaRail risk rule: {kind!r}")

    from .qc_sigmarail_screener_framework import SigmaRailRiskManagementModel

    return SigmaRailRiskManagementModel(models)


def _build_framework_model_instance(
    type_id: str,
    params: dict[str, Any],
    store: Any,
    store_builders: dict[str, Any],
    lean_reg: dict[str, Any],
    *,
    normalize: bool,
) -> Any:
    type_id = (type_id or "").strip()

    # Check for Composite Model Types
    if type_id in ("CompositeAlphaModel", "CompositeRiskManagementModel"):
        cls = lean_reg[type_id]
        sub_specs = params.get("models") or params.get("sub_models") or []
        sub_instances = []
        for sub in sub_specs:
            if isinstance(sub, dict):
                st = sub.get("Type") or sub.get("type") or ""
                sp = dict(sub.get("Parameters") or sub.get("parameters") or {})
                sub_instances.append(
                    _build_framework_model_instance(
                        st, sp, store, store_builders, lean_reg, normalize=normalize
                    )
                )
        return cls(*sub_instances)

    if type_id in store_builders:
        try:
            return store_builders[type_id](store, params)
        except TypeError as e:
            raise LeanFrameworkInterpreterError(
                f"Failed to construct {type_id} with store and parameters {params!r}: {e}"
            ) from e

    if type_id in lean_reg:
        cls = lean_reg[type_id]
        norm_params = params
        if normalize:
            from AlgorithmImports import (  # type: ignore[import-not-found]
                Market,
                Resolution,
                SecurityType,
                Symbol,
            )

            norm_params = _normalize_parameters(
                type_id,
                params,
                symbol_cls=Symbol,
                security_type_cls=SecurityType,
                market_cls=Market,
                resolution_cls=Resolution,
            )
        try:
            if type_id == "ConstantAlphaModel" and "_positional" in norm_params:
                return cls(*norm_params["_positional"])
            elif not norm_params:
                return cls()
            else:
                return cls(**norm_params)
        except Exception as e:
            raise LeanFrameworkInterpreterError(
                f"Failed to construct {type_id} with parameters {norm_params!r}: {e}"
            ) from e

    raise LeanFrameworkInterpreterError(
        f"Unknown framework Type {type_id!r} for store-backed wiring. "
        "Expected SigmaRailScreener* plugins, standard "
        "LeanFrameworkV1 Types (RsiAlphaModel, …), Composite models, or risk models."
    )


def _wire_store_hybrid_default(
    algorithm: Any,
    bundle: FrameworkBundleV1,
    store: Any,
    *,
    normalize: bool,
) -> WiredFrameworkV1:
    """Default registry: store-backed plugins + standard QC types (no store in ctor)."""
    store_builders = _default_sigmarail_store_builders()
    lean_reg = _default_lean_registry()
    instances: list[Any] = []
    for spec, setter in _slot_setters(algorithm, bundle):
        type_id = (spec.type or "").strip()
        params = dict(spec.parameters or {})
        instance = _build_framework_model_instance(
            type_id, params, store, store_builders, lean_reg, normalize=normalize
        )
        setter(instance)
        instances.append(instance)
    return WiredFrameworkV1(*instances)


def _slot_setters(algorithm: Any, fb: FrameworkBundleV1) -> list[tuple[FrameworkSlotSpec, Any]]:
    return [
        (fb.alpha, algorithm.set_alpha),
        (fb.portfolio_construction, algorithm.set_portfolio_construction),
        (fb.execution, algorithm.set_execution),
        (fb.risk_management, algorithm.set_risk_management),
    ]


def wire_framework_bundle_v1(
    algorithm: Any,
    bundle: FrameworkBundleV1,
    *,
    store: Any | None = None,
    registry: dict[str, Any] | None = None,
    normalize: bool = True,
) -> WiredFrameworkV1:
    """
    Wire the four framework models consumed by ``ClickHouseUniverseAlgorithm``. For
    ``SigmaRailStrategyV1``, the five slot class names are fixed by the strategy schema;
    the ClickHouse query AST in ``Framework.UniverseSelection`` supplies its universe.
    Pass **store** for SigmaRail framework model configuration.

    ``registry``:
      - Lean path: ``Type`` -> class (``cls(**params)``).
      - Store path: ``Type`` -> ``lambda store, params: instance`` (or pass ``registry=None``
        for the default SigmaRail store + Lean risk builders).
    """
    if store is not None:
        if registry is not None:
            builders = registry
            instances: list[Any] = []
            for spec, setter in _slot_setters(algorithm, bundle):
                type_id = (spec.type or "").strip()
                if type_id not in builders:
                    raise LeanFrameworkInterpreterError(
                        f"Unknown framework Type {type_id!r} for store-backed wiring. "
                        "Expected SigmaRailScreener* plugin Types, or "
                        "NullRiskManagementModel / MaximumDrawdownPercentPerSecurity."
                    )
                params = dict(spec.parameters or {})
                try:
                    instance = builders[type_id](store, params)
                except TypeError as e:
                    raise LeanFrameworkInterpreterError(
                        f"Failed to construct {type_id} with store and parameters {params!r}: {e}"
                    ) from e
                setter(instance)
                instances.append(instance)
            return WiredFrameworkV1(*instances)
        return _wire_store_hybrid_default(algorithm, bundle, store, normalize=normalize)

    reg: dict[str, type] = registry if registry is not None else _default_lean_registry()
    instances_lean: list[Any] = []
    for spec, setter in _slot_setters(algorithm, bundle):
        type_id = (spec.type or "").strip()
        if type_id not in reg:
            raise LeanFrameworkInterpreterError(
                f"Unknown framework Type {type_id!r} (not in allowlist). "
                "See ir/registry_catalog.json and docs/LEAN_FRAMEWORK_V1.md."
            )
        cls = reg[type_id]
        params = spec.parameters or {}
        if normalize and registry is None:
            from AlgorithmImports import (  # type: ignore[import-not-found]
                Market,
                Resolution,
                SecurityType,
                Symbol,
            )

            params = _normalize_parameters(
                type_id,
                params,
                symbol_cls=Symbol,
                security_type_cls=SecurityType,
                market_cls=Market,
                resolution_cls=Resolution,
            )
        try:
            instance = cls(**params)
        except TypeError as e:
            raise LeanFrameworkInterpreterError(
                f"Failed to construct {type_id} with parameters {params!r}: {e}"
            ) from e
        setter(instance)
        instances_lean.append(instance)
    return WiredFrameworkV1(*instances_lean)


def wire_lean_framework_v1(
    algorithm: Any,
    doc: LeanFrameworkV1Document,
    *,
    store: Any | None = None,
    registry: dict[str, Any] | None = None,
    normalize: bool = True,
) -> WiredFrameworkV1:
    """
    Same as ``wire_framework_bundle_v1(algorithm, doc.framework, ...)``.

    Pass **store** to use the ClickHouse/SigmaRail extension (screener store + CH framework Types).
    """
    return wire_framework_bundle_v1(
        algorithm,
        doc.framework,
        store=store,
        registry=registry,
        normalize=normalize,
    )


def apply_lean_framework_v1_algorithm_hints(algorithm: Any, doc: LeanFrameworkV1Document) -> None:
    """Optional Algorithm block: StartCash, BenchmarkSymbol when present."""
    block = doc.algorithm
    if not block:
        return
    if "StartCash" in block and block["StartCash"] is not None:
        algorithm.set_cash(float(block["StartCash"]))
    sym = block.get("BenchmarkSymbol")
    if sym and isinstance(sym, str) and sym.strip():
        algorithm.set_benchmark(sym.strip())
