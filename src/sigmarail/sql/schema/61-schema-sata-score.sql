-- Schema for the SATA (Stage Analysis Technical Attribute) Score table
-- This table stores the daily SATA score for each ticker, which is a quantitative
-- measure of how well a stock conforms to the Stage 2 uptrend criteria.
-- The SATA score is a 0-10 scale based on the number of Stage 2 criteria met.

CREATE TABLE IF NOT EXISTS sata_score
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'The date the score was calculated for',
    `sata_score` UInt8 COMMENT 'The SATA score (0-10), representing the number of met criteria',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: sata_score
-- Populates the sata_score table with the Stage Analysis Technical Attribute score.
-- Expects SQL variables: chunk_start_date, chunk_end_date
--
-- NORMALIZATION POLICY (Option A):
--   - SATA checks are based on split-adjusted daily_metrics.close vs split-adjusted SMAs/highs/lows.
--   - Adjusted fields remain available in daily_metrics for analytics but are not used for SATA scoring.
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of SATA scores for tickers that haven't changed
--
DROP VIEW IF EXISTS xform_sata_score;

CREATE VIEW IF NOT EXISTS xform_sata_score (
    ticker,
    date,
    sata_score,
    lastupdated
)
COMMENT '{"order":61,"target":"sata_score","sources":["daily_metrics","relative_strength"],"chunk_size":"6m"}'
AS
WITH
-- Check freshness per ticker - only process tickers where source data is newer
ticker_freshness_check AS (
    SELECT
        sata.ticker,
        count() as target_row_count,
        max(sata.lastupdated) as target_last_updated
    FROM sata_score sata FINAL
    WHERE sata.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY sata.ticker
),
-- Get source freshness per ticker
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM daily_metrics FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY ticker
),
-- Check freshness per date - only process dates where source data is newer
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) as target_last_updated
    FROM sata_score FINAL
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
-- Determine which tickers need updating
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1  -- New ticker
            WHEN s.source_row_count > t.target_row_count THEN 1  -- Missing rows in target for this chunk
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
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
-- lagInFrame windows evaluate on the post-WHERE row set, so the lag input must
-- be padded (>=21 sessions; 45d covers holiday-thinned months) and the emit
-- filter applied only after the lag is computed — otherwise the first ~20
-- emitted sessions per ticker under-count.
daily_lagged AS (
    SELECT
        d.ticker,
        d.date,
        d.`close`,
        d.sma200d,
        d.sma150d,
        d.sma50d,
        d.low_52w,
        d.high_52w,
        lagInFrame(d.sma200d, 20) OVER (PARTITION BY d.ticker ORDER BY d.date) AS sma200d_lag_20d
    FROM daily_metrics AS d
    INNER JOIN tickers_needing_update tnu ON d.ticker = tnu.ticker
    WHERE d.date BETWEEN addDays(toDate({chunk_start_date:String}), -45) AND toDate({chunk_end_date:String})
      AND tnu.needs_update = 1
)
SELECT
    l.ticker AS ticker,
    l.date AS date,
    (
        (l.`close` > l.sma200d) +
        (l.`close` > l.sma150d) +
        (l.sma150d > l.sma200d) +
        (l.sma200d > l.sma200d_lag_20d) +
        (l.`close` > l.sma50d) +
        (l.`close` > l.low_52w * 1.25) +
        (l.`close` > l.high_52w * 0.75) +
        (rs.rs_rating > 70)
        -- Point 9 for RS Line trend and Point 10 for Industry Rank are more complex
        -- and will be added in a future iteration. This provides an 8-point version for now.
    ) AS sata_score,
    now() as lastupdated
FROM daily_lagged l
LEFT JOIN relative_strength AS rs ON l.ticker = rs.ticker AND l.date = rs.date
-- NEW: Only process dates that need updating
INNER JOIN dates_needing_update dnu ON l.date = dnu.date
WHERE l.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND dnu.needs_update = 1;
