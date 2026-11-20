"""
JSON ``Framework.Type`` ids for Vera screener-backed QC models (``main.py`` + ``SigmaRailFrameworkStore``).

Canonical ids use the ``VeraScreener*`` prefix (no "Store" in the name). Older specs may still use
``ScreenerStore*`` or ``ClickHouse*`` — both remain accepted.
"""

from __future__ import annotations

# Canonical (preferred in new specs and synthesized pipeline bundles)
UNIVERSE_SELECTION = "VeraScreenerUniverseSelectionModel"
ALPHA = "VeraScreenerAlphaModel"
COMPOSITE_ALPHA = "VeraCompositeAlphaModel"
PORTFOLIO_CONSTRUCTION = "VeraScreenerPortfolioConstructionModel"
EXECUTION = "VeraScreenerExecutionModel"

# Legacy: intermediate ScreenerStore* ids
LEGACY_UNIVERSE_SCREENER_STORE = "ScreenerStoreUniverseSelectionModel"
LEGACY_ALPHA_SCREENER_STORE = "ScreenerStoreAlphaModel"
LEGACY_PORTFOLIO_SCREENER_STORE = "ScreenerStorePortfolioConstructionModel"
LEGACY_EXECUTION_SCREENER_STORE = "ScreenerStoreExecutionModel"

# Legacy: original ClickHouse* ids
LEGACY_UNIVERSE_CLICKHOUSE = "ClickHouseUniverseSelectionModel"
LEGACY_ALPHA_CLICKHOUSE = "ClickHouseAlphaModel"
LEGACY_PORTFOLIO_CLICKHOUSE = "ClickHousePortfolioConstructionModel"
LEGACY_EXECUTION_CLICKHOUSE = "ClickHouseExecutionModel"

# Sector allocation model types (stock-based)
SECTOR_ALPHA = "VeraSectorAlphaModel"
SECTOR_PORTFOLIO_CONSTRUCTION = "VeraSectorPortfolioConstructionModel"

# Sector ETF model types (ETF-based with leverage + inverse tiers)
SECTOR_ETF_ALPHA = "VeraSectorEtfAlphaModel"
SECTOR_ETF_PORTFOLIO_CONSTRUCTION = "VeraSectorEtfPortfolioConstructionModel"

# TQQQ tactical sleeve (legacy — prefer graph policy)
TQQQ_TACTICAL_ALPHA = "VeraTqqqTacticalAlphaModel"
TQQQ_TACTICAL_PORTFOLIO_CONSTRUCTION = "VeraTqqqTacticalPortfolioConstructionModel"

# Declarative graph policy (Policy B if/weight)
GRAPH_POLICY_ALPHA = "VeraGraphPolicyAlphaModel"
GRAPH_POLICY_PORTFOLIO_CONSTRUCTION = "VeraGraphPolicyPortfolioConstructionModel"

# High-ROE large-cap rolling cohort (CH fundamentals; Lean bars)
HIGH_ROE_UNIVERSE_SELECTION = "HighRoeQualityUniverseSelectionModel"

# Tactical Swing Trading models
SWING_BREAKOUT_ALPHA = "SwingBreakoutAlphaModel"
SWING_PULLBACK_ALPHA = "SwingPullbackAlphaModel"
RISK_BUDGETED_PORTFOLIO_CONSTRUCTION = "RiskBudgetedPortfolioConstructionModel"
PERFORMANCE_PORTFOLIO_CONSTRUCTION = "PerformanceWeightedPortfolioConstructionModel"
VOL_TARGET_PORTFOLIO_CONSTRUCTION = "VolatilityTargetingPortfolioConstructionModel"
REGIME_WEIGHTED_PORTFOLIO_CONSTRUCTION = "RegimeWeightedPortfolioConstructionModel"
SWING_PROGRESSIVE_RISK = "SwingProgressiveRiskManagementModel"

# Progressive pyramid entry + market hedge models
PYRAMID_ALPHA = "VeraPyramidAlphaModel"
HEDGE_RISK = "VeraHedgeModel"

MANUAL_UNIVERSE_SELECTION = "ManualUniverseSelectionModel"
COMPOSITE_UNIVERSE_SELECTION = "CompositeUniverseSelectionModel"
COARSE_UNIVERSE_SELECTION = "CoarseFundamentalUniverseSelectionModel"

ALLOWED_UNIVERSE_SELECTION_TYPES = frozenset(
    {
        UNIVERSE_SELECTION,
        LEGACY_UNIVERSE_SCREENER_STORE,
        LEGACY_UNIVERSE_CLICKHOUSE,
        HIGH_ROE_UNIVERSE_SELECTION,
        MANUAL_UNIVERSE_SELECTION,
        COMPOSITE_UNIVERSE_SELECTION,
        COARSE_UNIVERSE_SELECTION,
    }
)
ALLOWED_ALPHA_TYPES = frozenset(
    {
        ALPHA,
        COMPOSITE_ALPHA,
        LEGACY_ALPHA_SCREENER_STORE,
        LEGACY_ALPHA_CLICKHOUSE,
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
        LEGACY_PORTFOLIO_SCREENER_STORE,
        LEGACY_PORTFOLIO_CLICKHOUSE,
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
ALLOWED_EXECUTION_TYPES = frozenset(
    {EXECUTION, LEGACY_EXECUTION_SCREENER_STORE, LEGACY_EXECUTION_CLICKHOUSE}
)

# main.py: use manual rebalance + screener OHLC injection for these execution types
STORE_BACKED_EXECUTION_TYPES = frozenset(
    {
        EXECUTION,
        LEGACY_EXECUTION_SCREENER_STORE,
        LEGACY_EXECUTION_CLICKHOUSE,
    }
)
