-- Enhanced Bear Market Signals Schema
-- This table provides more sophisticated bear market detection with severity levels

CREATE TABLE IF NOT EXISTS enhanced_bear_market_signals
(
    `date` Date COMMENT 'Trading date for bear market signals',
    `is_bear_market_enhanced` UInt8 COMMENT '1 if enhanced bear market conditions are met, 0 otherwise',
    `bear_severity` LowCardinality(String) COMMENT 'Bear market severity: severe_bear, moderate_bear, mild_bear, not_bear',
    `bear_market_score` Float64 COMMENT 'Bear market severity score (0-100, higher = more severe)',
    `primary_condition` LowCardinality(String) COMMENT 'Primary condition that triggered bear market detection',
    `confirmation_conditions` LowCardinality(String) COMMENT 'Additional conditions that confirmed bear market',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp when this record was calculated and inserted'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192
COMMENT 'Enhanced bear market detection with severity levels and diagnostic information';

-- Managed transform view for target: enhanced_bear_market_signals
-- Enhanced Bear Market Classification Implementation V2
-- This transform adds more sophisticated bear market detection with better confirmation logic
--
-- ENHANCED: Only processes dates where source data is newer than target data
-- This prevents unnecessary recalculation of bear market signals for dates that haven't changed
--
-- NORMALIZATION POLICY (Option A):
--   - Bear market classification uses split-adjusted SPY close (daily_metrics.close) vs split-adjusted SMAs.
--   - This avoids dividend-adjustment artifacts in regime thresholds and keeps behavior consistent with core technicals.
--
-- Enhanced bear market detection logic with improved confirmation
DROP VIEW IF EXISTS xform_enhanced_bear_market_signals;

CREATE VIEW IF NOT EXISTS xform_enhanced_bear_market_signals (
    date,
    is_bear_market_enhanced,
    bear_severity,
    bear_market_score,
    primary_condition,
    confirmation_conditions
)
COMMENT '{"order":79,"target":"enhanced_bear_market_signals","sources":["daily_metrics","daily_metrics_derived","broad_market_breadth"],"chunk_size":"6m"}'
AS
WITH
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as target_last_updated
    FROM enhanced_bear_market_signals FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
-- Get source freshness per date
source_date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as source_last_updated
    FROM daily_metrics FINAL
    WHERE ticker = 'SPY'
      AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
-- Determine which dates need updating
dates_needing_update AS (
    SELECT
        COALESCE(s.date, t.date) as date,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1  -- New date
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_date_freshness_check s
    FULL OUTER JOIN date_freshness_check t ON s.date = t.date
)
SELECT
    spy.date AS date,
    -- Enhanced bear market detection with better confirmation
    CAST(
        -- Primary: SPY below 200-day SMA
        (spy.`close` < spy.sma200d) AND
        -- Confirmation 1: Use SMA trend fields instead of days below (handle NULLs)
        (COALESCE(COALESCE(derived.sma200d_trend, 0), 0) < -0.02) AND  -- Price 2%+ below 200-day SMA
        -- Confirmation 2: Either breadth deterioration OR momentum breakdown
        (
            -- Enhanced Breadth Deterioration: Consider percentage and 5-day averages
            (
                -- Breadth percentage is weak
                COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 OR
                COALESCE(breadth.pct_above_sma50d, 0.5) < 0.40 OR
                -- AND/OR 5-day average breadth is deteriorating
                COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50 OR
                COALESCE(breadth.pct_above_sma50d_sma5, 0.5) < 0.45
            ) OR
            -- Momentum breakdown: Price below 50-day SMA AND 50-day SMA declining (handle NULLs)
            (COALESCE(derived.sma50d_trend, 0) < -0.01 AND COALESCE(derived.sma50d_slope_20d, 0) < -0.01)
        )
    AS UInt8) AS is_bear_market_enhanced,

    -- Bear market severity classification with better thresholds
    multiIf(
        -- Severe Bear: Extended weakness + very poor breadth
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.05) AND  -- Price 5%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.30 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.35
        ), 'severe_bear',

        -- Moderate Bear: Sustained weakness + poor breadth
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.02) AND  -- Price 2%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50
        ), 'moderate_bear',

        -- Mild Bear: Basic bear market conditions met
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.01) AND  -- Price 1%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 OR
            COALESCE(breadth.pct_above_sma50d, 0.5) < 0.40 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50 OR
            (derived.sma50d_trend < -0.01 AND derived.sma50d_slope_20d < -0.01)
        ), 'mild_bear',

        'not_bear'
    ) AS bear_severity,

    -- Bear market severity score (0-100, higher = more severe)
    multiIf(
        -- Severe Bear: Extended weakness + very poor breadth
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.05) AND  -- Price 5%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.30 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.35
        ), 100,

        -- Moderate Bear: Sustained weakness + poor breadth
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.02) AND  -- Price 2%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50
        ), 75,

        -- Mild Bear: Basic bear market conditions met
        (spy.`close` < spy.sma200d) AND
        (COALESCE(derived.sma200d_trend, 0) < -0.01) AND  -- Price 1%+ below 200-day SMA
        (
            COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 OR
            COALESCE(breadth.pct_above_sma50d, 0.5) < 0.40 OR
            COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50 OR
            (derived.sma50d_trend < -0.01 AND derived.sma50d_slope_20d < -0.01)
        ), 50,

        0
    ) AS bear_market_score,

    -- Primary condition that triggered bear market
    multiIf(
        spy.`close` < spy.sma200d AND COALESCE(derived.sma200d_trend, 0) < -0.02, 'sustained_below_200d',
        'no_bear_market'
    ) AS primary_condition,

    -- Additional confirmation conditions with available fields
    multiIf(
        COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45 AND
        COALESCE(breadth.pct_above_sma200d_sma5, 0.5) < 0.50, 'breadth_200d_weak_declining',
        COALESCE(breadth.pct_above_sma50d, 0.5) < 0.40 AND
        COALESCE(breadth.pct_above_sma50d_sma5, 0.5) < 0.45, 'breadth_50d_weak_declining',
        COALESCE(breadth.pct_above_sma200d, 0.5) < 0.45, 'breadth_200d_weak',
        COALESCE(breadth.pct_above_sma50d, 0.5) < 0.40, 'breadth_50d_weak',
        derived.sma50d_trend < -0.01 AND derived.sma50d_slope_20d < -0.01, 'momentum_breakdown',
        'no_confirmation'
    ) AS confirmation_conditions

FROM daily_metrics spy
LEFT JOIN daily_metrics_derived derived ON spy.date = derived.date AND spy.ticker = derived.ticker
LEFT JOIN broad_market_breadth breadth ON spy.date = breadth.date
-- NEW: Only process dates that need updating
INNER JOIN dates_needing_update dnu ON spy.date = dnu.date
WHERE spy.ticker = 'SPY'
  AND spy.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND dnu.needs_update = 1
ORDER BY spy.date;
