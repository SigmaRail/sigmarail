-- Schema for industry_group_strength table
-- This table stores the calculated relative strength for each industry group.
CREATE TABLE IF NOT EXISTS industry_group_strength
(
    `date` Date COMMENT 'Date of the calculation.',
    `industry` String COMMENT 'The industry group name, derived from tickers.sicindustry.',
    `avg_rs_rating` Nullable(Float64) COMMENT 'The average rs_rating of all stocks in the industry group for that day.',
    `industry_group_rank` Nullable(Float64) COMMENT 'The percentile rank of the industry group\'s avg_rs_rating against all other groups for that day (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (industry, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: industry_group_strength
-- =============================================================================
-- Populates industry_group_strength for a given date chunk.
-- Expects parameters: chunk_start_date, chunk_end_date
--
-- ENHANCED: Only processes dates where source data is newer than target data
-- This prevents unnecessary recalculation of industry strength for dates that haven't changed
-- =============================================================================
--
DROP VIEW IF EXISTS xform_industry_group_strength;

CREATE VIEW IF NOT EXISTS xform_industry_group_strength (
    date,
    industry,
    avg_rs_rating,
    industry_group_rank
)
COMMENT '{"order":55,"target":"industry_group_strength","sources":["relative_strength","ticker_classification_daily"],"chunk_size":"12m"}'
AS
WITH
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as target_last_updated
    FROM industry_group_strength FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    GROUP BY date
),
-- Get source freshness per date
source_date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as source_last_updated
    FROM relative_strength FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
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
industry_daily_rs AS (
    SELECT
        c.sicindustry AS industry,
        rs.date AS date,
        avg(rs.rs_rating) AS avg_daily_rs_rating
    FROM relative_strength AS rs
    -- PIT labels via daily classification snapshots (#164) — no lookahead
    -- from current-state tickers.
    ASOF LEFT JOIN ticker_classification_daily AS c
        ON c.ticker = rs.ticker AND rs.date >= c.date
    -- NEW: Only process dates that need updating
    INNER JOIN dates_needing_update dnu ON rs.date = dnu.date
    WHERE rs.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
      AND c.sicindustry IS NOT NULL
      AND c.sicindustry != ''
      AND dnu.needs_update = 1
    GROUP BY
        c.sicindustry,
        rs.date
)
SELECT
    date,
    industry,
    avg_daily_rs_rating AS avg_rs_rating,
    percent_rank() OVER (PARTITION BY date ORDER BY avg_daily_rs_rating ASC) * 100 AS industry_group_rank
FROM industry_daily_rs;
