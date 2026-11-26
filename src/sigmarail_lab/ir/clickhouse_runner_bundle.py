"""Build FrameworkBundleV1 for ClickHouseUniverseAlgorithm from pipeline/graph LeanFrameworkSpec."""

from __future__ import annotations

from .lean_framework_json import FrameworkBundleV1
from .models import LeanFrameworkSpec
from .sigmarail_screener_framework_types import (
    ALPHA,
    EXECUTION,
    GRAPH_POLICY_ALPHA,
    GRAPH_POLICY_PORTFOLIO_CONSTRUCTION,
    PORTFOLIO_CONSTRUCTION,
)


def framework_bundle_for_clickhouse_pipeline(lf: LeanFrameworkSpec) -> FrameworkBundleV1:
    """
    Default store-backed runner wiring: fixed CH framework Types + Parameters from lf.

    Used when resolved spec is SigmaRailLab (pipeline or graph), not SigmaRailStrategyV1 JSON.
    """
    return FrameworkBundleV1.model_validate(
        {
            "Alpha": {
                "Type": ALPHA,
                "Parameters": lf.alpha.model_dump(),
            },
            "PortfolioConstruction": {
                "Type": PORTFOLIO_CONSTRUCTION,
                "Parameters": lf.portfolio.model_dump(),
            },
            "Execution": {"Type": EXECUTION, "Parameters": {}},
            "RiskManagement": {
                "Type": "NullRiskManagementModel",
                "Parameters": {},
            },
        }
    )


def framework_bundle_for_graph_policy(lf: LeanFrameworkSpec) -> FrameworkBundleV1:
    """Policy B graph: SigmaRailGraphPolicy* reads if/weight tree from store attachment."""
    return FrameworkBundleV1.model_validate(
        {
            "Alpha": {
                "Type": GRAPH_POLICY_ALPHA,
                "Parameters": lf.alpha.model_dump(),
            },
            "PortfolioConstruction": {
                "Type": GRAPH_POLICY_PORTFOLIO_CONSTRUCTION,
                "Parameters": lf.portfolio.model_dump(),
            },
            "Execution": {"Type": EXECUTION, "Parameters": {}},
            "RiskManagement": {
                "Type": "NullRiskManagementModel",
                "Parameters": {},
            },
        }
    )
