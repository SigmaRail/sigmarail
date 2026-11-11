-- Schema for broad_market_breadth table
-- Stores market breadth indicators for a custom defined broad market universe.

CREATE TABLE IF NOT EXISTS broad_market_breadth
(
    `date` Date COMMENT 'Trading date for which the breadth metrics are calculated',
    `pct_above_sma20d` Float64 COMMENT 'Percentage of stocks in the custom universe above their 20-day SMA',
    `pct_above_sma50d` Float64 COMMENT 'Percentage of stocks in the custom universe above their 50-day SMA',
    `pct_above_sma200d` Float64 COMMENT 'Percentage of stocks in the custom universe above their 200-day SMA',
    `pct_above_sma20d_sma5` Float64 COMMENT '5-day average of pct_above_sma20d',
    `pct_above_sma50d_sma5` Float64 COMMENT '5-day average of pct_above_sma50d',
    `pct_above_sma200d_sma5` Float64 COMMENT '5-day average of pct_above_sma200d',
    `pct_new_highs` Float64 COMMENT 'Percentage of stocks in the custom universe making new 52-week highs',
    `pct_new_lows` Float64 COMMENT 'Percentage of stocks in the custom universe making new 52-week lows',
    `pct_near_52w_low` Float64 COMMENT 'Percentage of stocks in the custom universe making new 52-week lows',
    `pct_near_52w_high` Float64 COMMENT 'Percentage of stocks in the custom universe making new 52-week highs',
    `last_populated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp when this record was calculated and inserted'
)
ENGINE = ReplacingMergeTree(last_populated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192
COMMENT 'Stores daily market breadth indicators for a custom broad market universe (e.g., non-penny, major exchange stocks).';

-- Managed transform view for target: broad_market_breadth
-- Populates the daily broad_market_breadth table
--
-- ENHANCED: Only processes dates where source data is newer than target data
-- This prevents unnecessary recalculation of market breadth for dates that haven't changed
--
-- NORMALIZATION POLICY (Option A):
--   - Breadth percentages (above SMA, near 52w high/low) are computed using split-adjusted daily_metrics.close.
--   - This keeps market breadth consistent with the core technical signal series used elsewhere.
--
DROP VIEW IF EXISTS xform_broad_market_breadth;

CREATE VIEW IF NOT EXISTS xform_broad_market_breadth (
    date,
    pct_near_52w_high,
    pct_near_52w_low,
    pct_above_sma20d,
    pct_above_sma50d,
    pct_above_sma200d,
    pct_above_sma20d_sma5,
    pct_above_sma50d_sma5,
    pct_above_sma200d_sma5
)
COMMENT '{"order":54,"target":"broad_market_breadth","sources":["daily_metrics","broad_market_constituents"],"chunk_size":"12m","target_timestamp_column":"last_populated"}'
AS
WITH
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(last_populated) as target_last_updated
    FROM broad_market_breadth FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
-- Get source freshness per date
source_date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as source_last_updated
    FROM daily_metrics FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
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
MarketBreadthDaily AS (
    SELECT
        dm.date AS calc_date,
        countIf(dm.`close` > dm.high_52w * 0.9) / nullIf(countDistinct(dm.ticker), 0) AS pct_near_52w_high,
        countIf(dm.`close` < dm.low_52w * 1.1) / nullIf(countDistinct(dm.ticker), 0) AS pct_near_52w_low,
        -- Use SMA-ready denominators to avoid denominator drift
        countIf(dm.sma20d IS NOT NULL AND dm.`close` > dm.sma20d) / nullIf(countIf(dm.sma20d IS NOT NULL), 0) AS pct_above_sma20d,
        countIf(dm.sma50d IS NOT NULL AND dm.`close` > dm.sma50d) / nullIf(countIf(dm.sma50d IS NOT NULL), 0) AS pct_above_sma50d,
        countIf(dm.sma200d IS NOT NULL AND dm.`close` > dm.sma200d) / nullIf(countIf(dm.sma200d IS NOT NULL), 0) AS pct_above_sma200d
    FROM daily_metrics AS dm
    JOIN broad_market_constituents AS bmc ON dm.ticker = bmc.ticker AND dm.date = bmc.date
    -- NEW: Only process dates that need updating
    INNER JOIN dates_needing_update dnu ON dm.date = dnu.date
    WHERE dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND dnu.needs_update = 1
    GROUP BY dm.date
),
Smoothed AS (
    SELECT
        calc_date,
        pct_near_52w_high,
        pct_near_52w_low,
        pct_above_sma20d,
        pct_above_sma50d,
        pct_above_sma200d,
        avg(pct_above_sma20d) OVER (ORDER BY calc_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS pct_above_sma20d_sma5,
        avg(pct_above_sma50d) OVER (ORDER BY calc_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS pct_above_sma50d_sma5,
        avg(pct_above_sma200d) OVER (ORDER BY calc_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS pct_above_sma200d_sma5
    FROM MarketBreadthDaily
)
SELECT
    calc_date,
    pct_near_52w_high,
    pct_near_52w_low,
    pct_above_sma20d,
    pct_above_sma50d,
    pct_above_sma200d,
    pct_above_sma20d_sma5,
    pct_above_sma50d_sma5,
    pct_above_sma200d_sma5
FROM Smoothed;
