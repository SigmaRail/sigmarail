-- Weekly Market Breadth Indicators
-- This table stores weekly aggregated market breadth metrics for the S&P 500.
CREATE TABLE IF NOT EXISTS broad_market_breadth_weekly
(
    `date` Date COMMENT 'The start date of the week (Monday)',
    `pct_sp500_above_sma40w` Nullable(Float64) COMMENT 'Percentage of S&P 500 stocks with price above their 40-week SMA.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: broad_market_breadth_weekly
-- Weekly Broad Market Breadth Transform
-- This transform calculates the percentage of S&P 500 stocks trading
-- above their 40-week simple moving average.
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
-- ENHANCED: Only processes dates where source data is newer than target data
-- This prevents unnecessary recalculation of weekly breadth for dates that haven't changed
--
-- CLOSED WEEKS ONLY: Same rule as weekly_metrics (Mon + 4 days <= max trading date).
--
DROP VIEW IF EXISTS xform_broad_market_breadth_weekly;

CREATE VIEW IF NOT EXISTS xform_broad_market_breadth_weekly (
    date,
    pct_sp500_above_sma40w
)
COMMENT '{"order":56,"target":"broad_market_breadth_weekly","sources":["weekly_metrics","sp500_membership_periods","daily_price_sequence"],"chunk_size":"12m"}'
AS
WITH
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as target_last_updated
    FROM broad_market_breadth_weekly FINAL
    WHERE date BETWEEN toMonday(toDate({chunk_start_date:String})) AND toMonday(toDate({chunk_end_date:String}))
    GROUP BY date
),
-- Get source freshness per date
source_date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as source_last_updated
    FROM weekly_metrics FINAL
    WHERE date BETWEEN toMonday(toDate({chunk_start_date:String})) AND toMonday(toDate({chunk_end_date:String}))
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
sp500_weekly_metrics AS (
    SELECT
        wm.date AS date,
        wm.close,
        wm.sma40w
    FROM weekly_metrics AS wm
    INNER JOIN sp500_membership_periods AS sp ON wm.ticker = sp.ticker
        AND wm.date >= sp.member_start_date AND wm.date < sp.member_end_date
    -- NEW: Only process dates that need updating
    INNER JOIN dates_needing_update dnu ON wm.date = dnu.date
    WHERE
        wm.date BETWEEN toMonday(toDate({chunk_start_date:String})) AND toMonday(toDate({chunk_end_date:String}))
        AND wm.sma40w IS NOT NULL
        AND dnu.needs_update = 1
)
SELECT
    date,
    countIf(close > sma40w) / count(*) * 100 AS pct_sp500_above_sma40w
FROM sp500_weekly_metrics
GROUP BY date
HAVING date + toIntervalDay(4) <= (SELECT max(date) FROM daily_price_sequence FINAL)
ORDER BY date;
