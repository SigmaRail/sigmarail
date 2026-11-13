"""Allowlisted daily_screener column names for predicates and SELECT projection."""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of StrEnum for Python < 3.11."""

        def __str__(self) -> str:
            return self.value


class ScreenerColumn(StrEnum):
    """Subset aligned with VeraBase daily_screener; expand as compilers gain coverage."""

    TICKER = "ticker"
    CLOSE = "close"
    VOLUME = "volume"
    HAS_VCP_SETUP = "has_vcp_setup"
    IS_STAGE_2_ADVANCING = "is_stage_2_advancing"
    MINERVINI_TT_SCORE_FULL = "minervini_tt_score_full"
    OVERALL_SCORE = "overall_score"
    ATR_PCT_14D = "atr_pct_14d"
    SMA200D = "sma200d"
    PCT_FROM_SMA20D = "pct_from_sma20d"
    DRAWDOWN_FROM_50D_HIGH = "drawdown_from_50d_high"
    UP_DAYS_LAST_3 = "up_days_last_3"
    DOWNSIDE_REVERSAL_FLAG = "downside_reversal_flag"
    TWO_CLOSES_BELOW_SMA20 = "two_closes_below_sma20"
    NEAR_SMA20_FLAG = "near_sma20_flag"
    DM_OPEN = "open"
    DM_HIGH = "high"
    DM_LOW = "low"
    SECTOR = "sector"
    RS_RATING = "rs_rating"
    FACTOR_RESIDUAL_60D = "factor_residual_60d"
    FACTOR_ROLLING_ALPHA_60D = "factor_rolling_alpha_60d"
    FACTOR_ALPHA_TSTAT_60D = "factor_alpha_tstat_60d"
    FACTOR_BETA_MKT_60D = "factor_beta_mkt_60d"
    FACTOR_BETA_SECTOR_60D = "factor_beta_sector_60d"
    FACTOR_R2_60D = "factor_r2_60d"
    FACTOR_RESIDUAL_252D = "factor_residual_252d"
    FACTOR_ROLLING_ALPHA_252D = "factor_rolling_alpha_252d"
    FACTOR_ALPHA_TSTAT_252D = "factor_alpha_tstat_252d"
    FACTOR_BETA_MKT_252D = "factor_beta_mkt_252d"
    FACTOR_BETA_SECTOR_252D = "factor_beta_sector_252d"
    FACTOR_R2_252D = "factor_r2_252d"


# Columns allowed in predicate atoms (row filters). Use in_tickers for ticker membership.
PREDICATE_COLUMNS: frozenset[ScreenerColumn] = frozenset(
    {
        ScreenerColumn.CLOSE,
        ScreenerColumn.VOLUME,
        ScreenerColumn.HAS_VCP_SETUP,
        ScreenerColumn.IS_STAGE_2_ADVANCING,
        ScreenerColumn.MINERVINI_TT_SCORE_FULL,
        ScreenerColumn.OVERALL_SCORE,
        ScreenerColumn.PCT_FROM_SMA20D,
        ScreenerColumn.DRAWDOWN_FROM_50D_HIGH,
        ScreenerColumn.UP_DAYS_LAST_3,
        ScreenerColumn.DOWNSIDE_REVERSAL_FLAG,
        ScreenerColumn.TWO_CLOSES_BELOW_SMA20,
        ScreenerColumn.NEAR_SMA20_FLAG,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_60D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_60D,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_252D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_252D,
        ScreenerColumn.FACTOR_BETA_MKT_60D,
        ScreenerColumn.FACTOR_BETA_SECTOR_60D,
        ScreenerColumn.FACTOR_R2_60D,
        ScreenerColumn.FACTOR_R2_252D,
    }
)

# Columns allowed in SELECT projection (plus fixed date alias)
PROJECTION_COLUMNS: frozenset[ScreenerColumn] = frozenset(
    {
        ScreenerColumn.TICKER,
        ScreenerColumn.OVERALL_SCORE,
        ScreenerColumn.ATR_PCT_14D,
        ScreenerColumn.SMA200D,
        ScreenerColumn.DM_OPEN,
        ScreenerColumn.DM_HIGH,
        ScreenerColumn.DM_LOW,
        ScreenerColumn.CLOSE,
        ScreenerColumn.VOLUME,
        ScreenerColumn.SECTOR,
        ScreenerColumn.RS_RATING,
        ScreenerColumn.FACTOR_RESIDUAL_60D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_60D,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_60D,
        ScreenerColumn.FACTOR_BETA_MKT_60D,
        ScreenerColumn.FACTOR_BETA_SECTOR_60D,
        ScreenerColumn.FACTOR_R2_60D,
        ScreenerColumn.FACTOR_RESIDUAL_252D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_252D,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_252D,
        ScreenerColumn.FACTOR_BETA_MKT_252D,
        ScreenerColumn.FACTOR_BETA_SECTOR_252D,
        ScreenerColumn.FACTOR_R2_252D,
    }
)

SORTABLE_COLUMNS: frozenset[ScreenerColumn] = frozenset(
    {
        ScreenerColumn.OVERALL_SCORE,
        ScreenerColumn.CLOSE,
        ScreenerColumn.VOLUME,
        ScreenerColumn.MINERVINI_TT_SCORE_FULL,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_60D,
        ScreenerColumn.FACTOR_ALPHA_TSTAT_252D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_60D,
        ScreenerColumn.FACTOR_ROLLING_ALPHA_252D,
    }
)


def sql_ident(column: ScreenerColumn) -> str:
    """ClickHouse identifier (quote dotted names)."""
    v = column.value
    if "." in v:
        return f"`{v}`"
    return v
