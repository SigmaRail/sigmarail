-- Schema for the Minervini Trend Template table
-- Stores individual Trend Template condition flags and composite scores per ticker/date.

CREATE TABLE IF NOT EXISTS minervini_trend_template
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date for the observation',
    `price_above_sma150_and_sma200` UInt8 COMMENT '1 when price is above both SMA150 and SMA200',
    `sma150_above_sma200` UInt8 COMMENT '1 when SMA150 is greater than SMA200',
    `sma200_rising_30d` UInt8 COMMENT '1 when SMA200 is higher than 30 trading days ago',
    `sma200_rising_150d` UInt8 COMMENT '1 when SMA200 is higher than 150 trading days ago',
    `sma50_above_long_smas` UInt8 COMMENT '1 when SMA50 is above both SMA150 and SMA200',
    `price_above_sma50` UInt8 COMMENT '1 when price is above SMA50',
    `price_30pct_above_52w_low` UInt8 COMMENT '1 when price is at least 30% above the 52-week low',
    `price_70pct_above_52w_low` UInt8 COMMENT '1 when price is at least 70% above the 52-week low',
    `price_within_25pct_52w_high` UInt8 COMMENT '1 when price is within 25% of the 52-week high',
    `rs_rating_at_least_70` UInt8 COMMENT '1 when relative strength rating is 70 or higher',
    `tt_score_full` UInt8 COMMENT 'Count of all eight Trend Template conditions met',
    `tt_score_light` UInt8 COMMENT 'Count excluding price above SMA50 and enhanced SMA200 duration',
    `tt_score_enhanced` UInt8 COMMENT 'Count using the 150-day SMA200 uptrend requirement',
    `tt_all_conditions_full` UInt8 COMMENT '1 when all eight standard conditions are satisfied',
    `tt_all_conditions_light` UInt8 COMMENT '1 when light-mode conditions are satisfied',
    `tt_all_conditions_enhanced` UInt8 COMMENT '1 when enhanced (150d) conditions are satisfied',
    `tt_buy_signal` UInt8 COMMENT '1 when Trend Template conditions are met alongside a SMA20 crossover',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: minervini_trend_template
-- ============================================================================
-- Minervini Trend Template Transform (1-month chunks)
-- Populates minervini_trend_template with condition flags and scores derived
-- from daily_metrics_derived and relative_strength.
-- Expects SQL variables: chunk_start_date, chunk_end_date
-- ============================================================================
--
DROP VIEW IF EXISTS xform_minervini_trend_template;

CREATE VIEW IF NOT EXISTS xform_minervini_trend_template (
    ticker,
    date,
    lastupdated,
    price_above_sma150_and_sma200,
    sma150_above_sma200,
    sma200_rising_30d,
    sma200_rising_150d,
    sma50_above_long_smas,
    price_above_sma50,
    price_30pct_above_52w_low,
    price_70pct_above_52w_low,
    price_within_25pct_52w_high,
    rs_rating_at_least_70,
    tt_score_full,
    tt_score_light,
    tt_score_enhanced,
    tt_all_conditions_full,
    tt_all_conditions_light,
    tt_all_conditions_enhanced,
    tt_buy_signal
)
COMMENT '{"order":68,"target":"minervini_trend_template","sources":["daily_metrics_derived","relative_strength"],"chunk_size":"1m"}'
AS
WITH
-- Determine freshness of existing records
ticker_freshness_check AS (
    SELECT
        mtt.ticker,
        count() AS target_row_count,
        max(mtt.lastupdated) AS target_last_updated
    FROM minervini_trend_template mtt FINAL
    WHERE mtt.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY mtt.ticker
),
-- Source freshness from daily_metrics_derived and relative_strength
source_freshness_check AS (
    SELECT
        src.ticker,
        count() AS source_row_count,
        max(src.lastupdated) AS source_last_updated
    FROM (
        SELECT ticker, lastupdated
        FROM daily_metrics_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}

        UNION ALL

        SELECT ticker, lastupdated
        FROM relative_strength FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    ) src
    GROUP BY src.ticker
),
-- Decide which tickers require recalculation
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) AS ticker,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1
            WHEN s.source_row_count > t.target_row_count THEN 1
            WHEN s.source_last_updated > t.target_last_updated THEN 1
            ELSE 0
        END AS needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
)
SELECT
    metrics.ticker,
    metrics.date,
    now() AS lastupdated,

    metrics.cond_price_above_sma150_and_sma200,
    metrics.cond_sma150_above_sma200,
    metrics.cond_sma200_rising_30d,
    metrics.cond_sma200_rising_150d,
    metrics.cond_sma50_above_long_smas,
    metrics.cond_price_above_sma50,
    metrics.cond_price_30pct_above_52w_low,
    metrics.cond_price_70pct_above_52w_low,
    metrics.cond_price_within_25pct_52w_high,
    metrics.cond_rs_rating_ge_70,

    toUInt8(
        metrics.cond_price_above_sma150_and_sma200 +
        metrics.cond_sma150_above_sma200 +
        metrics.cond_sma200_rising_30d +
        metrics.cond_sma50_above_long_smas +
        metrics.cond_price_above_sma50 +
        metrics.cond_price_30pct_above_52w_low +
        metrics.cond_price_within_25pct_52w_high +
        metrics.cond_rs_rating_ge_70
    ) AS tt_score_full,

    toUInt8(
        metrics.cond_price_above_sma150_and_sma200 +
        metrics.cond_sma150_above_sma200 +
        metrics.cond_sma200_rising_30d +
        metrics.cond_sma50_above_long_smas +
        metrics.cond_price_30pct_above_52w_low +
        metrics.cond_price_within_25pct_52w_high +
        metrics.cond_rs_rating_ge_70
    ) AS tt_score_light,

    toUInt8(
        metrics.cond_price_above_sma150_and_sma200 +
        metrics.cond_sma150_above_sma200 +
        metrics.cond_sma200_rising_150d +
        metrics.cond_sma50_above_long_smas +
        metrics.cond_price_above_sma50 +
        metrics.cond_price_30pct_above_52w_low +
        metrics.cond_price_within_25pct_52w_high +
        metrics.cond_rs_rating_ge_70
    ) AS tt_score_enhanced,

    CAST(
        metrics.cond_price_above_sma150_and_sma200 = 1
        AND metrics.cond_sma150_above_sma200 = 1
        AND metrics.cond_sma200_rising_30d = 1
        AND metrics.cond_sma50_above_long_smas = 1
        AND metrics.cond_price_above_sma50 = 1
        AND metrics.cond_price_30pct_above_52w_low = 1
        AND metrics.cond_price_within_25pct_52w_high = 1
        AND metrics.cond_rs_rating_ge_70 = 1
    AS UInt8) AS tt_all_conditions_full,

    CAST(
        metrics.cond_price_above_sma150_and_sma200 = 1
        AND metrics.cond_sma150_above_sma200 = 1
        AND metrics.cond_sma200_rising_30d = 1
        AND metrics.cond_sma50_above_long_smas = 1
        AND metrics.cond_price_30pct_above_52w_low = 1
        AND metrics.cond_price_within_25pct_52w_high = 1
        AND metrics.cond_rs_rating_ge_70 = 1
    AS UInt8) AS tt_all_conditions_light,

    CAST(
        metrics.cond_price_above_sma150_and_sma200 = 1
        AND metrics.cond_sma150_above_sma200 = 1
        AND metrics.cond_sma200_rising_150d = 1
        AND metrics.cond_sma50_above_long_smas = 1
        AND metrics.cond_price_above_sma50 = 1
        AND metrics.cond_price_30pct_above_52w_low = 1
        AND metrics.cond_price_within_25pct_52w_high = 1
        AND metrics.cond_rs_rating_ge_70 = 1
    AS UInt8) AS tt_all_conditions_enhanced,

    CAST(
        coalesce(metrics.sma20d_crossover_up, 0) = 1
        AND metrics.cond_price_above_sma150_and_sma200 = 1
        AND metrics.cond_sma150_above_sma200 = 1
        AND metrics.cond_sma200_rising_30d = 1
        AND metrics.cond_sma50_above_long_smas = 1
        AND metrics.cond_price_30pct_above_52w_low = 1
        AND metrics.cond_price_within_25pct_52w_high = 1
        AND metrics.cond_rs_rating_ge_70 = 1
    AS UInt8) AS tt_buy_signal
FROM (
    SELECT
        dmd.ticker AS ticker,
        dmd.date AS date,
        dmd.sma20d_crossover_up,
        CAST((coalesce(dmd.price_above_sma150d, 0) = 1 AND coalesce(dmd.price_above_sma200d, 0) = 1) AS UInt8) AS cond_price_above_sma150_and_sma200,
        CAST((coalesce(dmd.sma150d_above_sma200d, 0) = 1) AS UInt8) AS cond_sma150_above_sma200,
        CAST((coalesce(dmd.sma200d_rising_30d, 0) = 1) AS UInt8) AS cond_sma200_rising_30d,
        CAST((coalesce(dmd.sma200d_rising_150d, 0) = 1) AS UInt8) AS cond_sma200_rising_150d,
        CAST((coalesce(dmd.sma50d_above_sma150d, 0) = 1 AND coalesce(dmd.sma50d_above_sma200d, 0) = 1) AS UInt8) AS cond_sma50_above_long_smas,
        CAST((coalesce(dmd.price_above_sma50d, 0) = 1) AS UInt8) AS cond_price_above_sma50,
        CAST((coalesce(dmd.price_30pct_above_52w_low, 0) = 1) AS UInt8) AS cond_price_30pct_above_52w_low,
        CAST((coalesce(dmd.price_70pct_above_52w_low, 0) = 1) AS UInt8) AS cond_price_70pct_above_52w_low,
        CAST((coalesce(dmd.price_within_25pct_52w_high, 0) = 1) AS UInt8) AS cond_price_within_25pct_52w_high,
        CAST((coalesce(rs.rs_rating, 0) >= 70) AS UInt8) AS cond_rs_rating_ge_70
    FROM daily_metrics_derived dmd FINAL
    LEFT JOIN relative_strength rs FINAL
        ON dmd.ticker = rs.ticker AND dmd.date = rs.date
    INNER JOIN tickers_needing_update tnu
        ON dmd.ticker = tnu.ticker
    WHERE dmd.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND tnu.needs_update = 1
) AS metrics;
