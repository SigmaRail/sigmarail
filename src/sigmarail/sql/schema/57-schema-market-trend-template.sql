-- Market Trend Template (Weekly) - Enhanced with Magnitude and Duration
-- This table stores a weekly scorecard for the overall market trend, including
-- the magnitude of each indicator and the duration of its state.
CREATE TABLE IF NOT EXISTS market_trend_template
(
    `date` Date COMMENT 'The start date of the week (Monday)',
    `price_vs_sma30w_pct` Nullable(Float64) COMMENT 'Price distance from 30w SMA: (close/sma30w) - 1',
    `price_vs_sma40w_pct` Nullable(Float64) COMMENT 'Price distance from 40w SMA: (close/sma40w) - 1',
    `sma30w_vs_sma40w_pct` Nullable(Float64) COMMENT 'Distance between 30w and 40w SMAs: (sma30w/sma40w) - 1',
    `sma40w_slope_pct` Nullable(Float64) COMMENT '4-week slope of the 40-week SMA as a percentage',
    `price_vs_52w_high_pct` Nullable(Float64) COMMENT 'Price distance from 52w high: (close/high_52w) - 1',
    `price_vs_52w_low_pct` Nullable(Float64) COMMENT 'Price distance from 52w low: (close/low_52w) - 1',
    `is_price_above_sma30w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks price is above/below 30w SMA',
    `is_price_above_sma40w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks price is above/below 40w SMA',
    `is_sma30w_above_sma40w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks 30w SMA is above/below 40w SMA',
    `is_sma40w_trending_up_duration` Nullable(UInt16) COMMENT 'Consecutive weeks 40w SMA is trending up/down',
    `trend_score` UInt8 COMMENT 'The total score (0-6) based on how many criteria are met.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: market_trend_template
-- Market Trend Template Transform (Weekly) - Enhanced with Magnitude and Duration
-- This script calculates the weekly market trend scorecard for the S&P 500 index.
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
-- ENHANCED: Only processes dates where source data is newer than target data
-- This prevents unnecessary recalculation of trend template for dates that haven't changed
--
-- CLOSED WEEKS ONLY: Aligns with weekly_metrics (Mon + 4 days <= max trading date).
--
DROP VIEW IF EXISTS xform_market_trend_template;

CREATE VIEW IF NOT EXISTS xform_market_trend_template
COMMENT '{"order":57,"target":"market_trend_template","sources":["weekly_metrics","daily_price_sequence"],"chunk_size":"12m"}'
AS
WITH
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as target_last_updated
    FROM market_trend_template FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    GROUP BY date
),
-- Get source freshness per date
source_date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as source_last_updated
    FROM weekly_metrics FINAL
    WHERE ticker = 'SPY'
      AND date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
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
),
-- 1. Get base data and calculate raw magnitudes.
--    The state/duration chain below is path-dependent: a market-trend state can
--    persist far longer than any read pad. Read the full SPY weekly history
--    (one ticker, ~1.9k rows) and apply the freshness filter at emit instead.
spy_weekly_data AS (
    SELECT
        date,
        close,
        sma30w,
        sma40w,
        (close / nullIf(sma30w, 0)) - 1 AS price_vs_sma30w_pct,
        (close / nullIf(sma40w, 0)) - 1 AS price_vs_sma40w_pct,
        (sma30w / nullIf(sma40w, 0)) - 1 AS sma30w_vs_sma40w_pct,
        ((sma40w - lagInFrame(sma40w, 4) OVER (ORDER BY date)) / nullIf(lagInFrame(sma40w, 4) OVER (ORDER BY date), 0)) AS sma40w_slope_pct,
        max(close) OVER (ORDER BY date ROWS BETWEEN 51 PRECEDING AND CURRENT ROW) AS high_52w,
        min(close) OVER (ORDER BY date ROWS BETWEEN 51 PRECEDING AND CURRENT ROW) AS low_52w
    FROM weekly_metrics FINAL
    WHERE ticker = 'SPY'
      AND date <= toDate({chunk_end_date:String})
),
-- 2. Determine the boolean state for each criterion
trend_states AS (
    SELECT
        date,
        price_vs_sma30w_pct,
        price_vs_sma40w_pct,
        sma30w_vs_sma40w_pct,
        sma40w_slope_pct,
        (close / nullIf(high_52w, 0)) - 1 AS price_vs_52w_high_pct,
        (close / nullIf(low_52w, 0)) - 1 AS price_vs_52w_low_pct,

        -- Boolean state flags, now safely wrapped at the source
        CAST(ifNull(price_vs_sma30w_pct, 0) > 0 AS UInt8) AS state_price_sma30,
        CAST(ifNull(price_vs_sma40w_pct, 0) > 0 AS UInt8) AS state_price_sma40,
        CAST(ifNull(sma30w_vs_sma40w_pct, 0) > 0 AS UInt8) AS state_sma30_sma40,
        CAST(ifNull(sma40w_slope_pct, 0) > 0 AS UInt8) AS state_sma40_slope
    FROM spy_weekly_data
),
-- 3. Detect when each state changes to create grouping keys
state_changes AS (
    SELECT
        *,
        state_price_sma30 != lagInFrame(state_price_sma30, 1, state_price_sma30) OVER (ORDER BY date) AS changed_price_sma30,
        state_price_sma40 != lagInFrame(state_price_sma40, 1, state_price_sma40) OVER (ORDER BY date) AS changed_price_sma40,
        state_sma30_sma40 != lagInFrame(state_sma30_sma40, 1, state_sma30_sma40) OVER (ORDER BY date) AS changed_sma30_sma40,
        state_sma40_slope != lagInFrame(state_sma40_slope, 1, state_sma40_slope) OVER (ORDER BY date) AS changed_sma40_slope
    FROM trend_states
),
-- 4. Create groups for each consecutive state period
state_groups AS (
    SELECT
        *,
        sum(changed_price_sma30) OVER (ORDER BY date) AS group_price_sma30,
        sum(changed_price_sma40) OVER (ORDER BY date) AS group_price_sma40,
        sum(changed_sma30_sma40) OVER (ORDER BY date) AS group_sma30_sma40,
        sum(changed_sma40_slope) OVER (ORDER BY date) AS group_sma40_slope
    FROM state_changes
),
-- 5. Calculate the duration within each group over the FULL history — ClickHouse
--    evaluates window functions on the post-WHERE row set, so the emit-range and
--    freshness filters must live in the outer SELECT, not alongside the OVERs.
scored AS (
    SELECT
        date,
        price_vs_sma30w_pct,
        price_vs_sma40w_pct,
        sma30w_vs_sma40w_pct,
        sma40w_slope_pct,
        price_vs_52w_high_pct,
        price_vs_52w_low_pct,

        count() OVER (PARTITION BY group_price_sma30 ORDER BY date) AS is_price_above_sma30w_duration,
        count() OVER (PARTITION BY group_price_sma40 ORDER BY date) AS is_price_above_sma40w_duration,
        count() OVER (PARTITION BY group_sma30_sma40 ORDER BY date) AS is_sma30w_above_sma40w_duration,
        count() OVER (PARTITION BY group_sma40_slope ORDER BY date) AS is_sma40w_trending_up_duration,

        -- Final Trend Score (based on the original simple boolean conditions)
        state_price_sma30 + state_price_sma40 + state_sma30_sma40 + state_sma40_slope
        + CAST(ifNull(price_vs_52w_high_pct, 0) > -0.25 AS UInt8)
        + CAST(ifNull(price_vs_52w_low_pct, 0) > 0.25 AS UInt8) AS trend_score
    FROM state_groups
)
SELECT
    date,
    price_vs_sma30w_pct,
    price_vs_sma40w_pct,
    sma30w_vs_sma40w_pct,
    sma40w_slope_pct,
    price_vs_52w_high_pct,
    price_vs_52w_low_pct,
    is_price_above_sma30w_duration,
    is_price_above_sma40w_duration,
    is_sma30w_above_sma40w_duration,
    is_sma40w_trending_up_duration,
    trend_score,
    now() as lastupdated
FROM scored
WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
  AND date + toIntervalDay(4) <= (SELECT max(date) FROM daily_price_sequence FINAL)
  AND date IN (SELECT date FROM dates_needing_update WHERE needs_update = 1);
