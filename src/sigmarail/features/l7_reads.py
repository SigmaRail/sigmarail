"""Shared L7 SELECT fragments (screener_price_tech_daily + screener_ratings_daily)."""

from __future__ import annotations

# Price + ratings (screen presets, research_context, rank_candidates).
# Do not put FINAL on the right side of LEFT ANY JOIN — ClickHouse can error
# with NOT_FOUND_COLUMN_IN_BLOCK when filtering joined FINAL tables.
PX_RT_FROM = (
    "screener_price_tech_daily AS px FINAL "
    "LEFT ANY JOIN screener_ratings_daily AS rt "
    "ON px.ticker = rt.ticker AND px.date = rt.date"
)

PX_RT_SELECT = (
    "px.ticker AS ticker, px.date AS date, "
    "rt.overall_score AS overall_score, px.rs_rating AS rs_rating, "
    "rt.classification AS classification, "
    "px.industry_group_rank AS industry_group_rank, "
    "rt.minervini_score AS minervini_score, "
    "rt.oneil_score AS oneil_score, "
    "px.closeadj AS closeadj, px.close AS close"
)

PX_RT_SCORE_SELECT = (
    "px.ticker AS ticker, px.date AS date, "
    "rt.overall_score AS overall_score, px.rs_rating AS rs_rating, "
    "rt.classification AS classification, "
    "px.industry_group_rank AS industry_group_rank, "
    "rt.minervini_score AS minervini_score"
)
