"""
JSON ``Framework.Type`` ids for SigmaRail screener-backed QC models.
"""

from __future__ import annotations

# Canonical SigmaRail framework identifiers. Universe membership comes from the
# SigmaRail query AST, not a LEAN framework model slot.
ALPHA = "SigmaRailScreenerAlphaModel"
COMPOSITE_ALPHA = "SigmaRailCompositeAlphaModel"
PORTFOLIO_CONSTRUCTION = "SigmaRailScreenerPortfolioConstructionModel"
EXECUTION = "SigmaRailScreenerExecutionModel"

# Sector allocation model types (stock-based)
SECTOR_ALPHA = "SigmaRailSectorAlphaModel"
SECTOR_PORTFOLIO_CONSTRUCTION = "SigmaRailSectorPortfolioConstructionModel"

# Sector ETF model types (ETF-based with leverage + inverse tiers)
SECTOR_ETF_ALPHA = "SigmaRailSectorEtfAlphaModel"
SECTOR_ETF_PORTFOLIO_CONSTRUCTION = "SigmaRailSectorEtfPortfolioConstructionModel"

# TQQQ tactical sleeve (legacy — prefer graph policy)
TQQQ_TACTICAL_ALPHA = "SigmaRailTqqqTacticalAlphaModel"
TQQQ_TACTICAL_PORTFOLIO_CONSTRUCTION = "SigmaRailTqqqTacticalPortfolioConstructionModel"

# Declarative graph policy (Policy B if/weight)
GRAPH_POLICY_ALPHA = "SigmaRailGraphPolicyAlphaModel"
GRAPH_POLICY_PORTFOLIO_CONSTRUCTION = "SigmaRailGraphPolicyPortfolioConstructionModel"

# Tactical Swing Trading models
SWING_BREAKOUT_ALPHA = "SwingBreakoutAlphaModel"
SWING_PULLBACK_ALPHA = "SwingPullbackAlphaModel"
RISK_BUDGETED_PORTFOLIO_CONSTRUCTION = "RiskBudgetedPortfolioConstructionModel"
PERFORMANCE_PORTFOLIO_CONSTRUCTION = "PerformanceWeightedPortfolioConstructionModel"
VOL_TARGET_PORTFOLIO_CONSTRUCTION = "VolatilityTargetingPortfolioConstructionModel"
REGIME_WEIGHTED_PORTFOLIO_CONSTRUCTION = "RegimeWeightedPortfolioConstructionModel"
SWING_PROGRESSIVE_RISK = "SwingProgressiveRiskManagementModel"

# Progressive pyramid entry + market hedge models
PYRAMID_ALPHA = "SigmaRailPyramidAlphaModel"
HEDGE_RISK = "SigmaRailHedgeModel"

ALLOWED_ALPHA_TYPES = frozenset(
    {
        ALPHA,
        COMPOSITE_ALPHA,
        SECTOR_ALPHA,
        SECTOR_ETF_ALPHA,
        TQQQ_TACTICAL_ALPHA,
        GRAPH_POLICY_ALPHA,
        PYRAMID_ALPHA,
    }
)
ALLOWED_PORTFOLIO_CONSTRUCTION_TYPES = frozenset(
    {
        PORTFOLIO_CONSTRUCTION,
        SECTOR_PORTFOLIO_CONSTRUCTION,
        SECTOR_ETF_PORTFOLIO_CONSTRUCTION,
        TQQQ_TACTICAL_PORTFOLIO_CONSTRUCTION,
        GRAPH_POLICY_PORTFOLIO_CONSTRUCTION,
        PERFORMANCE_PORTFOLIO_CONSTRUCTION,
        VOL_TARGET_PORTFOLIO_CONSTRUCTION,
        REGIME_WEIGHTED_PORTFOLIO_CONSTRUCTION,
    }
)
ALLOWED_RISK_MANAGEMENT_TYPES = frozenset(
    {
        SWING_PROGRESSIVE_RISK,
        HEDGE_RISK,
        "TrailingStopRiskManagementModel",
        "MaximumDrawdownPercentPerSecurity",
        "MaximumSectorExposureRiskManagementModel",
        "MaximumUnrealizedProfitPercentPerSecurity",
        "NullRiskManagementModel",
        "CompositeRiskManagementModel",
    }
)
ALLOWED_EXECUTION_TYPES = frozenset({EXECUTION})

# main.py: use manual rebalance + screener OHLC injection for these execution types
STORE_BACKED_EXECUTION_TYPES = frozenset(
    {
        EXECUTION,
    }
)
