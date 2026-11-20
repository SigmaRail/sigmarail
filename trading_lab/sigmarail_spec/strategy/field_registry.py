"""Semantic factor registry: maps human factor names to L7 screener columns.

The pipeline compiler resolves factor names through this registry so that
the user-facing ``factors`` blocks never carry raw column names. Each entry
records the physical L7 column, the owning table, and the sorting direction
(``asc`` = higher is better, ``desc`` = lower is better).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorInfo:
    """One semantic factor -> one L7 column mapping."""

    column: str
    table: str
    direction: str = "asc"  # asc = higher is better; desc = lower is better
    description: str = ""
    kind: str = "score"  # score | filter | meta


# Canonical factor registry. Column names are the bare physical L7 names.
FACTOR_REGISTRY: dict[str, FactorInfo] = {
    # --- price / technical (screener_price_tech_daily) ---------------------
    "momentum": FactorInfo(
        column="rs_rating",
        table="screener_price_tech_daily",
        description="Relative strength rating (0-99 percentile)",
    ),
    "trend_1y": FactorInfo(
        column="perf_1y",
        table="screener_price_tech_daily",
        description="1-year price performance",
    ),
    "trend_6m": FactorInfo(
        column="perf_6m",
        table="screener_price_tech_daily",
        description="6-month price performance",
    ),
    "trend_3m": FactorInfo(
        column="perf_3m",
        table="screener_price_tech_daily",
        description="3-month price performance",
    ),
    "trend_1m": FactorInfo(
        column="perf_1m",
        table="screener_price_tech_daily",
        description="1-month price performance",
    ),
    "reversal_5d": FactorInfo(
        column="perf_5d",
        table="screener_price_tech_daily",
        direction="desc",
        description="5-day performance (lower = deeper pullback for reversal entry)",
    ),
    # --- ratings (screener_ratings_daily) ----------------------------------
    "value": FactorInfo(
        column="valuation_rating",
        table="screener_ratings_daily",
        description="Valuation rating (0-99; higher = cheaper)",
    ),
    "technical": FactorInfo(
        column="technical_rating",
        table="screener_ratings_daily",
        description="Technical rating (0-99)",
    ),
    "setup": FactorInfo(
        column="setup_quality_rating",
        table="screener_ratings_daily",
        description="Setup quality / VCP rating (0-99)",
    ),
    "accumulation": FactorInfo(
        column="accumulation_distribution_rating",
        table="screener_ratings_daily",
        description="Accumulation/distribution (institutional sponsorship) rating",
    ),
    "growth_momentum": FactorInfo(
        column="high_growth_momentum_rating",
        table="screener_ratings_daily",
        description="High-growth momentum rating",
    ),
    "composite": FactorInfo(
        column="overall_score",
        table="screener_ratings_daily",
        description="Composite overall score",
    ),
    # --- fundamentals (screener_fundamentals_daily) ------------------------
    "roe": FactorInfo(
        column="mrt_roe",
        table="screener_fundamentals_daily",
        description="Return on equity (TTM)",
    ),
    "eps_growth": FactorInfo(
        column="arq_eps_growth_yoy",
        table="screener_fundamentals_daily",
        description="YoY EPS growth (ARQ)",
    ),
    "revenue_growth": FactorInfo(
        column="arq_revenue_growth_yoy",
        table="screener_fundamentals_daily",
        description="YoY revenue growth (ARQ)",
    ),
    "net_margin": FactorInfo(
        column="mrt_netmargin",
        table="screener_fundamentals_daily",
        description="Net margin (TTM)",
    ),
    "gross_margin": FactorInfo(
        column="mrt_grossmargin",
        table="screener_fundamentals_daily",
        description="Gross margin (TTM)",
    ),
    "fcf": FactorInfo(
        column="mrt_fcf",
        table="screener_fundamentals_daily",
        description="Free cash flow (TTM)",
    ),
    "debt_equity": FactorInfo(
        column="mrt_de",
        table="screener_fundamentals_daily",
        direction="desc",
        description="Debt-to-equity (lower is better)",
    ),
    # --- factor residuals (screener_factor_daily) --------------------------
    "factor_alpha": FactorInfo(
        column="factor_rolling_alpha_60d",
        table="screener_factor_daily",
        description="60-day rolling factor alpha (residual return)",
    ),
    "factor_tstat": FactorInfo(
        column="factor_alpha_tstat_60d",
        table="screener_factor_daily",
        description="60-day factor alpha t-statistic",
    ),
}


def resolve_factor(name: str) -> FactorInfo:
    """Resolve a semantic factor name to its registry entry.

    Raises ValueError for unknown names so the compiler fails loudly.
    """
    key = (name or "").strip()
    if key not in FACTOR_REGISTRY:
        raise ValueError(f"unknown factor {name!r}; known: {sorted(FACTOR_REGISTRY)}")
    return FACTOR_REGISTRY[key]


def list_factors() -> dict[str, dict[str, str]]:
    """Registry as a plain dict for API/CLI surfaces."""
    return {
        name: {
            "column": info.column,
            "table": info.table,
            "direction": info.direction,
            "description": info.description,
        }
        for name, info in sorted(FACTOR_REGISTRY.items())
    }
