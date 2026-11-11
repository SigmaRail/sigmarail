-- ============================================================================
-- Technical Ratings Table Schema
-- ============================================================================
-- Purpose: Pre-calculated technical and setup quality ratings for all tickers
--
-- This table stores ChartMill-style technical ratings to avoid on-the-fly
-- calculations in queries. All heavy computation is done once in
-- transform 65-technical-ratings-3m.sql and stored here for fast queries.
--
-- Attribution:
-- - technical_rating: Combines RS (O'Neil), trend analysis (Weinstein),
--   and MA alignment (Multiple traders)
-- - setup_quality_rating: VCP pattern quality (Minervini), consolidation,
--   volatility compression
--
-- Dependencies:
-- - daily_metrics: Price, volume, moving averages, ATR
-- - daily_metrics_derived: VCP metrics, trends, slopes
-- - relative_strength: RS rating (O'Neil methodology)
--
-- Storage: ~50 MB per year (~15 columns × ~8000 tickers × 252 days)
-- Performance: 40x faster than calculating in view (50ms vs 2000ms)
-- ============================================================================

CREATE TABLE IF NOT EXISTS technical_ratings
(
    `ticker` String COMMENT 'Equity ticker symbol',
    `date` Date COMMENT 'Trading session date',
    `rs_component` Float32 COMMENT 'Relative Strength component (O\'Neil) - 25 points max',
    `long_term_trend_component` Float32 COMMENT 'Long-term trend vs 200d MA (Weinstein) - 25 points max',
    `short_term_trend_component` Float32 COMMENT 'Short-term momentum vs 50d MA - 20 points max',
    `ma_alignment_component` Float32 COMMENT 'MA hierarchy alignment (50d>150d>200d) - 15 points max',
    `position_in_range_component` Float32 COMMENT 'Position in 52-week range - 10 points max',
    `volume_component` Float32 COMMENT 'Volume confirmation - 5 points max',
    `consolidation_component` Float32 COMMENT 'Price consolidation quality (Minervini) - 30 points max',
    `volatility_compression_component` Float32 COMMENT 'ATR compression - 25 points max',
    `volume_dryup_component` Float32 COMMENT 'Volume decreasing in consolidation - 20 points max',
    `support_quality_component` Float32 COMMENT 'Number of consolidation days - 15 points max',
    `breakout_proximity_component` Float32 COMMENT 'Proximity to 90d high - 10 points max',
    `technical_rating` Float32 COMMENT 'Overall technical health (0-100) - RS, trend, MA alignment',
    `setup_quality_rating` Float32 COMMENT 'Entry pattern quality (0-100) - VCP, consolidation',
    `technical_composite` Float32 COMMENT 'Average of technical + setup ratings (0-100)',
    `lastupdated` DateTime DEFAULT now() COMMENT 'Timestamp when this record was calculated and inserted'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Pre-calculated technical and setup quality ratings - ChartMill-style';

-- ============================================================================
-- Usage Example:
-- ============================================================================
-- SELECT ticker, date, technical_rating, setup_quality_rating
-- FROM technical_ratings
-- WHERE date = today() AND technical_rating >= 8.0 AND setup_quality_rating >= 8.0
-- ORDER BY technical_composite DESC
-- LIMIT 20;
-- ============================================================================

-- Managed transform view for target: technical_ratings
-- ============================================================================
-- Technical Ratings Transform (3-month chunks)
-- ============================================================================
-- Purpose: Calculate technical_rating and setup_quality_rating for all tickers
--
-- Attribution:
-- - RS Rating component: William O'Neil (IBD, 1988)
-- - Stage/trend analysis: Stan Weinstein (1988)
-- - VCP pattern: Mark Minervini (2013)
-- - MA alignment: Multiple traders (Weinstein, O'Neil, Darvas)
--
-- Processing: Date-based freshness checking (only update when source data changes)
-- Chunk size: 3 months (optimized for performance and memory)
-- Rating Scale: 0-100 (IBD/Deepvue-aligned, not ChartMill 0-10)
-- ============================================================================
--
DROP VIEW IF EXISTS xform_technical_ratings;

CREATE VIEW IF NOT EXISTS xform_technical_ratings (
    ticker,
    date,
    rs_component,
    long_term_trend_component,
    short_term_trend_component,
    ma_alignment_component,
    position_in_range_component,
    volume_component,
    consolidation_component,
    volatility_compression_component,
    volume_dryup_component,
    support_quality_component,
    breakout_proximity_component,
    technical_rating,
    setup_quality_rating,
    technical_composite,
    lastupdated
)
COMMENT '{"order":65,"target":"technical_ratings","sources":["daily_metrics","daily_metrics_derived","relative_strength"],"chunk_size":"3m"}'
AS
SELECT
    dm.ticker AS ticker,
    dm.date AS date,

    -- ====================================================================
    -- TECHNICAL RATING COMPONENTS (Total: 100.0 points)
    -- ====================================================================

    -- 1. RS Component (25 points, 25% weight) - O'Neil
    CASE
        WHEN rs.rs_rating IS NULL THEN 0.0
        WHEN rs.rs_rating >= 90 THEN 25.0
        WHEN rs.rs_rating >= 80 THEN 20.0
        WHEN rs.rs_rating >= 70 THEN 15.0
        WHEN rs.rs_rating >= 60 THEN 10.0
        WHEN rs.rs_rating >= 50 THEN 5.0
        ELSE 0.0
    END AS rs_component,

    -- 2. Long-term Trend Component (25 points, 25% weight) - Weinstein
    CASE
        WHEN dm.close > dm.sma200d * 1.10 AND dmd.sma200d_slope_20d > 0.02 THEN 25.0
        WHEN dm.close > dm.sma200d AND dmd.sma200d_slope_20d > 0 THEN 20.0
        WHEN dm.close > dm.sma200d * 0.98 THEN 10.0
        WHEN dm.close < dm.sma200d * 0.90 THEN 0.0
        ELSE 5.0
    END AS long_term_trend_component,

    -- 3. Short-term Trend Component (20 points, 20% weight)
    CASE
        WHEN dm.close > dm.sma50d * 1.05 AND dmd.sma50d_slope_20d > 0.01 THEN 20.0
        WHEN dm.close > dm.sma50d AND dmd.sma50d_slope_20d > 0 THEN 15.0
        WHEN dm.close > dm.sma50d * 0.98 THEN 10.0
        WHEN dm.close < dm.sma50d * 0.95 THEN 0.0
        ELSE 5.0
    END AS short_term_trend_component,

    -- 4. MA Alignment Component (15 points, 15% weight) - Multiple traders
    CASE
        WHEN dm.sma10d > dm.sma20d AND dm.sma20d > dm.sma50d
            AND dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 15.0
        WHEN dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 10.0
        WHEN dm.sma50d > dm.sma200d THEN 5.0
        ELSE 0.0
    END AS ma_alignment_component,

    -- 5. Position in 52-Week Range Component (10 points, 10% weight)
    CASE
        WHEN dm.high_52w IS NULL OR dm.low_52w IS NULL THEN 0.0
        WHEN dm.high_52w = dm.low_52w THEN 0.0
        ELSE LEAST(10.0, 10.0 * (dm.close - dm.low_52w) / nullIf(dm.high_52w - dm.low_52w, 0))
    END AS position_in_range_component,

    -- 6. Volume Component (5 points, 5% weight)
    CASE
        WHEN dm.volume > dm.avg_vol_20d * 1.5 AND dm.close > dm.sma50d THEN 5.0
        WHEN dm.volume > dm.avg_vol_20d * 1.2 AND dm.close > dm.sma50d THEN 3.0
        WHEN dm.volume < dm.avg_vol_20d * 0.7 AND dm.close < dm.sma50d THEN 2.0
        ELSE 0.0
    END AS volume_component,

    -- ====================================================================
    -- SETUP QUALITY RATING COMPONENTS (Total: 100.0 points)
    -- ====================================================================

    -- 1. Consolidation Component (30 points, 30% weight) - Minervini VCP
    CASE
        WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0
        WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 5 AND 20 THEN 30.0
        WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 21 AND 30 THEN 20.0
        WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 3 AND 4 THEN 15.0
        WHEN dmd.vcp_consolidation_days_5pct_30d > 30 THEN 10.0
        ELSE 0.0
    END AS consolidation_component,

    -- 2. Volatility Compression Component (25 points, 25% weight)
    CASE
        WHEN dmd.vcp_atr_compression_5d_90d IS NULL THEN 0.0
        WHEN dmd.vcp_atr_compression_5d_90d < 0.4 THEN 25.0
        WHEN dmd.vcp_atr_compression_5d_90d < 0.6 THEN 20.0
        WHEN dmd.vcp_atr_compression_5d_90d < 0.8 THEN 10.0
        ELSE 0.0
    END AS volatility_compression_component,

    -- 3. Volume Dry-up Component (20 points, 20% weight)
    CASE
        WHEN dmd.vcp_volume_dryup_5d_90d IS NULL THEN 0.0
        WHEN dmd.vcp_volume_dryup_5d_90d < 0.5 THEN 20.0
        WHEN dmd.vcp_volume_dryup_5d_90d < 0.7 THEN 15.0
        WHEN dmd.vcp_volume_dryup_5d_90d < 0.9 THEN 10.0
        ELSE 0.0
    END AS volume_dryup_component,

    -- 4. Support Quality Component (15 points, 15% weight)
    CASE
        WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0
        WHEN dmd.vcp_consolidation_days_5pct_30d >= 20 THEN 15.0
        WHEN dmd.vcp_consolidation_days_5pct_30d >= 15 THEN 12.0
        WHEN dmd.vcp_consolidation_days_5pct_30d >= 10 THEN 8.0
        WHEN dmd.vcp_consolidation_days_5pct_30d >= 5 THEN 5.0
        ELSE 0.0
    END AS support_quality_component,

    -- 5. Breakout Proximity Component (10 points, 10% weight)
    CASE
        WHEN dmd.vcp_proximity_90d IS NULL THEN 0.0
        WHEN dmd.vcp_proximity_90d <= 0.02 THEN 10.0
        WHEN dmd.vcp_proximity_90d <= 0.05 THEN 8.0
        WHEN dmd.vcp_proximity_90d <= 0.10 THEN 5.0
        WHEN dmd.vcp_proximity_90d <= 0.15 THEN 3.0
        ELSE 0.0
    END AS breakout_proximity_component,

    -- ====================================================================
    -- FINAL RATINGS (Calculated inline to avoid CTE complexity)
    -- ====================================================================

    -- Technical Rating (0-100): Sum of technical components
    LEAST(100.0, GREATEST(0.0,
        CASE
            WHEN rs.rs_rating IS NULL THEN 0.0
            WHEN rs.rs_rating >= 90 THEN 25.0
            WHEN rs.rs_rating >= 80 THEN 20.0
            WHEN rs.rs_rating >= 70 THEN 15.0
            WHEN rs.rs_rating >= 60 THEN 10.0
            WHEN rs.rs_rating >= 50 THEN 5.0
            ELSE 0.0
        END +
        CASE
            WHEN dm.close > dm.sma200d * 1.10 AND dmd.sma200d_slope_20d > 0.02 THEN 25.0
            WHEN dm.close > dm.sma200d AND dmd.sma200d_slope_20d > 0 THEN 20.0
            WHEN dm.close > dm.sma200d * 0.98 THEN 10.0
            WHEN dm.close < dm.sma200d * 0.90 THEN 0.0
            ELSE 5.0
        END +
        CASE
            WHEN dm.close > dm.sma50d * 1.05 AND dmd.sma50d_slope_20d > 0.01 THEN 20.0
            WHEN dm.close > dm.sma50d AND dmd.sma50d_slope_20d > 0 THEN 15.0
            WHEN dm.close > dm.sma50d * 0.98 THEN 10.0
            WHEN dm.close < dm.sma50d * 0.95 THEN 0.0
            ELSE 5.0
        END +
        CASE
            WHEN dm.sma10d > dm.sma20d AND dm.sma20d > dm.sma50d
                AND dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 15.0
            WHEN dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 10.0
            WHEN dm.sma50d > dm.sma200d THEN 5.0
            ELSE 0.0
        END +
        CASE
            WHEN dm.high_52w IS NULL OR dm.low_52w IS NULL THEN 0.0
            WHEN dm.high_52w = dm.low_52w THEN 0.0
            ELSE LEAST(10.0, 10.0 * (dm.close - dm.low_52w) / nullIf(dm.high_52w - dm.low_52w, 0))
        END +
        CASE
            WHEN dm.volume > dm.avg_vol_20d * 1.5 AND dm.close > dm.sma50d THEN 5.0
            WHEN dm.volume > dm.avg_vol_20d * 1.2 AND dm.close > dm.sma50d THEN 3.0
            WHEN dm.volume < dm.avg_vol_20d * 0.7 AND dm.close < dm.sma50d THEN 2.0
            ELSE 0.0
        END
    )) AS technical_rating,

    -- Setup Quality Rating (0-100): Sum of setup components
    LEAST(100.0, GREATEST(0.0,
        CASE
            WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0
            WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 5 AND 20 THEN 30.0
            WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 21 AND 30 THEN 20.0
            WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 3 AND 4 THEN 15.0
            WHEN dmd.vcp_consolidation_days_5pct_30d > 30 THEN 10.0
            ELSE 0.0
        END +
        CASE
            WHEN dmd.vcp_atr_compression_5d_90d IS NULL THEN 0.0
            WHEN dmd.vcp_atr_compression_5d_90d < 0.4 THEN 25.0
            WHEN dmd.vcp_atr_compression_5d_90d < 0.6 THEN 20.0
            WHEN dmd.vcp_atr_compression_5d_90d < 0.8 THEN 10.0
            ELSE 0.0
        END +
        CASE
            WHEN dmd.vcp_volume_dryup_5d_90d IS NULL THEN 0.0
            WHEN dmd.vcp_volume_dryup_5d_90d < 0.5 THEN 20.0
            WHEN dmd.vcp_volume_dryup_5d_90d < 0.7 THEN 15.0
            WHEN dmd.vcp_volume_dryup_5d_90d < 0.9 THEN 10.0
            ELSE 0.0
        END +
        CASE
            WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0
            WHEN dmd.vcp_consolidation_days_5pct_30d >= 20 THEN 15.0
            WHEN dmd.vcp_consolidation_days_5pct_30d >= 15 THEN 12.0
            WHEN dmd.vcp_consolidation_days_5pct_30d >= 10 THEN 8.0
            WHEN dmd.vcp_consolidation_days_5pct_30d >= 5 THEN 5.0
            ELSE 0.0
        END +
        CASE
            WHEN dmd.vcp_proximity_90d IS NULL THEN 0.0
            WHEN dmd.vcp_proximity_90d <= 0.02 THEN 10.0
            WHEN dmd.vcp_proximity_90d <= 0.05 THEN 8.0
            WHEN dmd.vcp_proximity_90d <= 0.10 THEN 5.0
            WHEN dmd.vcp_proximity_90d <= 0.15 THEN 3.0
            ELSE 0.0
        END
    )) AS setup_quality_rating,

    -- Technical Composite (0-100): Average of both ratings
    (
        LEAST(100.0, GREATEST(0.0,
            CASE WHEN rs.rs_rating IS NULL THEN 0.0 WHEN rs.rs_rating >= 90 THEN 25.0 WHEN rs.rs_rating >= 80 THEN 20.0 WHEN rs.rs_rating >= 70 THEN 15.0 WHEN rs.rs_rating >= 60 THEN 10.0 WHEN rs.rs_rating >= 50 THEN 5.0 ELSE 0.0 END +
            CASE WHEN dm.close > dm.sma200d * 1.10 AND dmd.sma200d_slope_20d > 0.02 THEN 25.0 WHEN dm.close > dm.sma200d AND dmd.sma200d_slope_20d > 0 THEN 20.0 WHEN dm.close > dm.sma200d * 0.98 THEN 10.0 WHEN dm.close < dm.sma200d * 0.90 THEN 0.0 ELSE 5.0 END +
            CASE WHEN dm.close > dm.sma50d * 1.05 AND dmd.sma50d_slope_20d > 0.01 THEN 20.0 WHEN dm.close > dm.sma50d AND dmd.sma50d_slope_20d > 0 THEN 15.0 WHEN dm.close > dm.sma50d * 0.98 THEN 10.0 WHEN dm.close < dm.sma50d * 0.95 THEN 0.0 ELSE 5.0 END +
            CASE WHEN dm.sma10d > dm.sma20d AND dm.sma20d > dm.sma50d AND dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 15.0 WHEN dm.sma50d > dm.sma150d AND dm.sma150d > dm.sma200d THEN 10.0 WHEN dm.sma50d > dm.sma200d THEN 5.0 ELSE 0.0 END +
            CASE WHEN dm.high_52w IS NULL OR dm.low_52w IS NULL THEN 0.0 WHEN dm.high_52w = dm.low_52w THEN 0.0 ELSE LEAST(10.0, 10.0 * (dm.close - dm.low_52w) / nullIf(dm.high_52w - dm.low_52w, 0)) END +
            CASE WHEN dm.volume > dm.avg_vol_20d * 1.5 AND dm.close > dm.sma50d THEN 5.0 WHEN dm.volume > dm.avg_vol_20d * 1.2 AND dm.close > dm.sma50d THEN 3.0 WHEN dm.volume < dm.avg_vol_20d * 0.7 AND dm.close < dm.sma50d THEN 2.0 ELSE 0.0 END
        )) +
        LEAST(100.0, GREATEST(0.0,
            CASE WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0 WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 5 AND 20 THEN 30.0 WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 21 AND 30 THEN 20.0 WHEN dmd.vcp_consolidation_days_5pct_30d BETWEEN 3 AND 4 THEN 15.0 WHEN dmd.vcp_consolidation_days_5pct_30d > 30 THEN 10.0 ELSE 0.0 END +
            CASE WHEN dmd.vcp_atr_compression_5d_90d IS NULL THEN 0.0 WHEN dmd.vcp_atr_compression_5d_90d < 0.4 THEN 25.0 WHEN dmd.vcp_atr_compression_5d_90d < 0.6 THEN 20.0 WHEN dmd.vcp_atr_compression_5d_90d < 0.8 THEN 10.0 ELSE 0.0 END +
            CASE WHEN dmd.vcp_volume_dryup_5d_90d IS NULL THEN 0.0 WHEN dmd.vcp_volume_dryup_5d_90d < 0.5 THEN 20.0 WHEN dmd.vcp_volume_dryup_5d_90d < 0.7 THEN 15.0 WHEN dmd.vcp_volume_dryup_5d_90d < 0.9 THEN 10.0 ELSE 0.0 END +
            CASE WHEN dmd.vcp_consolidation_days_5pct_30d IS NULL THEN 0.0 WHEN dmd.vcp_consolidation_days_5pct_30d >= 20 THEN 15.0 WHEN dmd.vcp_consolidation_days_5pct_30d >= 15 THEN 12.0 WHEN dmd.vcp_consolidation_days_5pct_30d >= 10 THEN 8.0 WHEN dmd.vcp_consolidation_days_5pct_30d >= 5 THEN 5.0 ELSE 0.0 END +
            CASE WHEN dmd.vcp_proximity_90d IS NULL THEN 0.0 WHEN dmd.vcp_proximity_90d <= 0.02 THEN 10.0 WHEN dmd.vcp_proximity_90d <= 0.05 THEN 8.0 WHEN dmd.vcp_proximity_90d <= 0.10 THEN 5.0 WHEN dmd.vcp_proximity_90d <= 0.15 THEN 3.0 ELSE 0.0 END
        ))
    ) / 2.0 AS technical_composite,

    now() AS lastupdated

FROM daily_metrics dm FINAL
LEFT JOIN daily_metrics_derived dmd FINAL ON dm.ticker = dmd.ticker AND dm.date = dmd.date
LEFT JOIN relative_strength rs FINAL ON dm.ticker = rs.ticker AND dm.date = rs.date
WHERE dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND dm.close IS NOT NULL
  AND dm.sma200d IS NOT NULL

-- ============================================================================
-- Simplified version: No CTEs, direct calculation
-- This avoids CTE column scoping issues
-- Rating Scale: 0-100 (consistent with IBD/Deepvue, not ChartMill 0-10)
-- ============================================================================;
