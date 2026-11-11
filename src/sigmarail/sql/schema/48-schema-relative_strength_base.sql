-- Staging table for relative strength calculations.
-- Stores daily performance metrics and SPY-relative ratios before percentile ranking.
CREATE TABLE IF NOT EXISTS relative_strength_base
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Date of the relative strength calculation.',
    `yearly_performance` Nullable(Float64) COMMENT '12-month price performance.',
    `performance_6m` Nullable(Float64) COMMENT '6-month price performance.',
    `performance_3m` Nullable(Float64) COMMENT '3-month price performance.',
    `performance_1m` Nullable(Float64) COMMENT '1-month price performance.',
    `performance_9m` Nullable(Float64) COMMENT '9-month price performance.',
    `performance_q1` Nullable(Float64) COMMENT 'Oldest quarter of the trailing year, days 190-252 back.',
    `performance_q2` Nullable(Float64) COMMENT 'Second quarter back, days 127-189.',
    `performance_q3` Nullable(Float64) COMMENT 'Third quarter back, days 64-126.',
    `performance_q4` Nullable(Float64) COMMENT 'Most recent quarter, days 1-63 (equals performance_3m).',
    `price_relative_ratio` Nullable(Float64) COMMENT 'Price relative ratio versus SPY (closeadj / spy_closeadj).',
    `pool` LowCardinality(String) DEFAULT 'stocks' COMMENT 'Instrument classification provenance (tickers.table: stocks or funds). relative_strength_ranks percentiles are a single shared universe (the shared Sharadar universe); pool is informational for a future fund-segmented RS.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: relative_strength_base
-- =============================================================================
-- Relative Strength Base Data
--   * Stages performance horizons and SPY-relative ratios per ticker/date
--   * Keeps incremental refresh logic aligned with daily_metrics updates
--
-- NORMALIZATION POLICY (Option A):
--   - SPY-relative price ratios are computed using split-adjusted daily_metrics.close.
--   - This aligns RS inputs with the same series used for technical signals and backtesting.
-- =============================================================================
--
DROP VIEW IF EXISTS xform_relative_strength_base;

CREATE VIEW IF NOT EXISTS xform_relative_strength_base (
    ticker,
    date,
    yearly_performance,
    performance_6m,
    performance_3m,
    performance_1m,
    performance_9m,
    performance_q1,
    performance_q2,
    performance_q3,
    performance_q4,
    price_relative_ratio,
    pool,
    lastupdated
)
COMMENT '{"order":48,"target":"relative_strength_base","sources":["daily_metrics","daily_metrics_derived","tickers"],"chunk_size":"1m"}'
AS
WITH
updates_dates AS (
    SELECT COALESCE(s.date, t.date) AS date
    FROM (
        SELECT date, max(lastupdated) AS source_last_updated
        FROM (
            SELECT date, lastupdated
            FROM daily_metrics FINAL
            WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
            UNION ALL
            -- perf_* columns come from daily_metrics_derived (#163): a derived
            -- rewrite must re-fire this transform even when daily_metrics is
            -- untouched, else staged perf values go stale.
            SELECT date, lastupdated
            FROM daily_metrics_derived FINAL
            WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        )
        GROUP BY date
    ) s
    FULL OUTER JOIN (
        SELECT date, max(lastupdated) AS target_last_updated
        FROM relative_strength_base FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) t ON s.date = t.date
    WHERE t.target_last_updated IS NULL
       OR s.source_last_updated > t.target_last_updated
),
spy_prices AS (
    SELECT
        dm.date,
        dm.`close` AS spy_close
    FROM daily_metrics dm FINAL
    WHERE dm.ticker = 'SPY'
      AND dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
),
-- Single shared RS universe (the shared Sharadar universe): every instrument with a
-- daily_metrics bar ranks against the same cohort — stocks and ETFs together,
-- matching IBD's RS Rating semantics (leveraged/inverse ETFs included). The
-- broad_market_constituents membership filter is gone: it exists to keep the
-- breadth/regime universe stock-only, not to gate RS eligibility.
-- `pool` is emitted for provenance only (tickers.table classification) so a
-- future fund-specific RS can segment without re-deriving membership.
base AS (
    SELECT
        dm.ticker AS ticker,
        dm.date AS date,
        dmd.perf_1y AS perf_1y,
        dmd.perf_6m AS perf_6m,
        dmd.perf_3m AS perf_3m,
        dmd.perf_1m AS perf_1m,
        dmd.perf_9m AS perf_9m,
        dmd.perf_q1 AS perf_q1,
        dmd.perf_q2 AS perf_q2,
        dmd.perf_q3 AS perf_q3,
        dmd.perf_q4 AS perf_q4,
        if(sp.spy_close > 0, dm.`close` / sp.spy_close, NULL) AS price_relative_ratio_raw,
        coalesce(t.`table`, 'stocks') AS pool
    FROM daily_metrics dm FINAL
    INNER JOIN updates_dates ud ON dm.date = ud.date
    LEFT JOIN tickers t FINAL ON dm.ticker = t.ticker
    LEFT JOIN daily_metrics_derived dmd FINAL ON dm.ticker = dmd.ticker AND dm.date = dmd.date
    LEFT JOIN spy_prices sp ON dm.date = sp.date
    WHERE dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND NOT startsWith(dm.ticker, '^')
)
SELECT
    base.ticker,
    base.date,
    base.perf_1y,
    base.perf_6m,
    base.perf_3m,
    base.perf_1m,
    base.perf_9m,
    base.perf_q1,
    base.perf_q2,
    base.perf_q3,
    base.perf_q4,
    base.price_relative_ratio_raw,
    base.pool,
    now()
FROM base;
