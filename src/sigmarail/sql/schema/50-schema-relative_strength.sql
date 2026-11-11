-- =============================================================================
-- Relative Strength Table Schema
-- Stores relative strength metrics including IBD RS Rating and derived calculations
-- =============================================================================

CREATE TABLE IF NOT EXISTS relative_strength
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Date of the relative strength calculation.',
    `yearly_performance` Nullable(Float64) COMMENT '12-month price performance: (current_price / price_12_months_ago) - 1. IBD method.',
    `performance_6m` Nullable(Float64) COMMENT '6-month price performance.',
    `performance_3m` Nullable(Float64) COMMENT '3-month price performance.',
    `performance_1m` Nullable(Float64) COMMENT '1-month price performance.',
    `composite_performance` Nullable(Float64) COMMENT 'Weighted composite performance (40/20/20/20 across 12m/6m/3m/1m).',
    `rs_rating` Nullable(Float64) COMMENT 'Relative strength rating (0-100 percentile of the blended 1y/6m/3m/1m momentum score within the shared instrument universe — stocks and ETFs ranked together).',
    `rs_rating_12m` Nullable(Float64) COMMENT 'RS Rating for the 12-month horizon (0-100): yearly_pct * 100 within the shared instrument universe.',
    `rs_rating_6m` Nullable(Float64) COMMENT 'RS Rating for the 6-month horizon (0-100): performance_6m_pct * 100 within the shared instrument universe.',
    `rs_rating_3m` Nullable(Float64) COMMENT 'RS Rating for the 3-month horizon (0-100): performance_3m_pct * 100 within the shared instrument universe.',
    `rs_rating_1m` Nullable(Float64) COMMENT 'RS Rating for the 1-month horizon (0-100): performance_1m_pct * 100 within the shared instrument universe.',
    `sma10d_rs_rating` Nullable(Float64) COMMENT '10-day simple moving average of the rs_rating.',
    `sma21d_rs_rating` Nullable(Float64) COMMENT '21-day simple moving average of the rs_rating.',
    `sma50d_rs_rating` Nullable(Float64) COMMENT '50-day simple moving average of the rs_rating.',
    `sma200d_rs_rating` Nullable(Float64) COMMENT '200-day simple moving average of the rs_rating.',
    `momentum_rank` UInt32 COMMENT 'Rank by blended_pct within the shared universe for the date (1 = highest momentum; rows with no performance history rank last).',
    `price_relative_ratio` Nullable(Float64) COMMENT 'Price relative ratio versus SPY (closeadj / spy_closeadj).',
    `price_relative_ratio_rebased` Nullable(Float64) COMMENT 'Price relative ratio rebased to 100 using the first available value.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: relative_strength
-- =============================================================================
-- Relative Strength Final Assembly
--   * Joins staged base data with percentile rankings
--   * Computes composite scores, RS moving averages, and rebased ratios
-- =============================================================================
--
DROP VIEW IF EXISTS xform_relative_strength;

CREATE VIEW IF NOT EXISTS xform_relative_strength (
    ticker,
    date,
    yearly_performance,
    performance_6m,
    performance_3m,
    performance_1m,
    composite_performance,
    rs_rating,
    rs_rating_12m,
    rs_rating_6m,
    rs_rating_3m,
    rs_rating_1m,
    sma10d_rs_rating,
    sma21d_rs_rating,
    sma50d_rs_rating,
    sma200d_rs_rating,
    momentum_rank,
    price_relative_ratio,
    price_relative_ratio_rebased,
    lastupdated
)
COMMENT '{"order":50,"target":"relative_strength","sources":["relative_strength_ranks","relative_strength_base"],"chunk_size":"1m"}'
AS
WITH
updates_dates AS (
    SELECT COALESCE(s.date, t.date) AS date
    FROM (
        SELECT date, max(lastupdated) AS source_last_updated
        FROM relative_strength_ranks FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) s
    FULL OUTER JOIN (
        SELECT date, max(lastupdated) AS target_last_updated
        FROM relative_strength FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) t ON s.date = t.date
    WHERE t.target_last_updated IS NULL
       OR s.source_last_updated > t.target_last_updated
),
dataset AS (
    SELECT
        b.ticker,
        b.date,
        b.yearly_performance,
        b.performance_6m,
        b.performance_3m,
        b.performance_1m,
        b.price_relative_ratio,
        r.blended_pct,
        r.rs_rating,
        r.yearly_pct,
        r.performance_6m_pct,
        r.performance_3m_pct,
        r.performance_1m_pct,
        r.momentum_rank
    FROM relative_strength_base b FINAL
    INNER JOIN relative_strength_ranks r FINAL
        ON b.ticker = r.ticker AND b.date = r.date
    WHERE b.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND b.date IN (SELECT date FROM updates_dates)
),
scored AS (
    SELECT
        ticker,
        date,
        yearly_performance,
        performance_6m,
        performance_3m,
        performance_1m,
        blended_pct AS composite_performance,
        rs_rating,
        yearly_pct * 100 AS rs_rating_12m,
        performance_6m_pct * 100 AS rs_rating_6m,
        performance_3m_pct * 100 AS rs_rating_3m,
        performance_1m_pct * 100 AS rs_rating_1m,
        momentum_rank,
        price_relative_ratio,
        avg(rs_rating) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS sma10d_rs_rating,
        avg(rs_rating) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS sma21d_rs_rating,
        avg(rs_rating) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50d_rs_rating,
        avg(rs_rating) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200d_rs_rating,
        price_relative_ratio / nullIf(argMin(price_relative_ratio, date) OVER (PARTITION BY ticker), 0) * 100 AS price_relative_ratio_rebased
    FROM dataset
)
SELECT
    ticker,
    date,
    yearly_performance,
    performance_6m,
    performance_3m,
    performance_1m,
    composite_performance,
    rs_rating,
    rs_rating_12m,
    rs_rating_6m,
    rs_rating_3m,
    rs_rating_1m,
    sma10d_rs_rating,
    sma21d_rs_rating,
    sma50d_rs_rating,
    sma200d_rs_rating,
    momentum_rank,
    price_relative_ratio,
    price_relative_ratio_rebased,
    now()
FROM scored;
