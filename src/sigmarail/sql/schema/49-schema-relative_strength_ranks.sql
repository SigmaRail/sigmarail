-- Staging table for relative strength percentile rankings.
CREATE TABLE IF NOT EXISTS relative_strength_ranks
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Date of the relative strength calculation.',
    `yearly_pct` Nullable(Float64) COMMENT 'Percentile rank of yearly performance.',
    `performance_6m_pct` Nullable(Float64) COMMENT 'Percentile rank of 6-month performance.',
    `performance_3m_pct` Nullable(Float64) COMMENT 'Percentile rank of 3-month performance.',
    `performance_1m_pct` Nullable(Float64) COMMENT 'Percentile rank of 1-month performance.',
    `performance_9m_pct` Nullable(Float64) COMMENT 'Shared-universe percentile of 9-month performance per date (0-1).',
    `performance_q1_pct` Nullable(Float64) COMMENT 'Shared-universe percentile of the oldest-quarter performance per date (0-1).',
    `performance_q2_pct` Nullable(Float64) COMMENT 'Shared-universe percentile of the second-quarter-back performance per date (0-1).',
    `performance_q3_pct` Nullable(Float64) COMMENT 'Shared-universe percentile of the third-quarter-back performance per date (0-1).',
    `performance_q4_pct` Nullable(Float64) COMMENT 'Shared-universe percentile of the most-recent-quarter performance per date (0-1).',
    `blended_pct` Nullable(Float64) COMMENT 'Weighted composite percentile (40/20/20/20).',
    `rs_rating` Nullable(Float64) COMMENT 'Final RS rating percentile scaled 0-100.',
    `momentum_rank` Nullable(UInt32) COMMENT 'Rank by blended percentile (1 = highest momentum).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: relative_strength_ranks
-- =============================================================================
-- Relative Strength Percentile Rankings
--   * Reads staged performance data
--   * Computes per-horizon percentiles and blended RS scores per date
--
-- NULL POLICY:
--   - A NULL horizon perf emits a NULL pct — never a rank. Window ASC ordering
--     puts NULLs last, so an unguarded row_number() ranks missing history in
--     the top band and the coalesce() fallback chain never fires.
--   - Percentile denominators count only non-NULL perfs per date:
--     countIf(perf IS NOT NULL), so short-history rows do not stretch valid
--     members' percentiles.
--   - blended_pct renormalizes weights over available components: the yearly
--     0.4 weight leaves the denominator when yearly_pct is NULL; each 0.2
--     sub-horizon weight stays while its own pct OR the yearly fallback exists.
--   - rs_rating emits NULL when blended_pct is NULL. momentum_rank stays
--     populated (relative_strength.momentum_rank is non-Nullable UInt32) —
--     NULL-blend rows rank last via ORDER BY (blended_pct IS NULL, DESC).
-- =============================================================================
--
DROP VIEW IF EXISTS xform_relative_strength_ranks;

CREATE VIEW IF NOT EXISTS xform_relative_strength_ranks (
    ticker,
    date,
    yearly_pct,
    performance_6m_pct,
    performance_3m_pct,
    performance_1m_pct,
    performance_9m_pct,
    performance_q1_pct,
    performance_q2_pct,
    performance_q3_pct,
    performance_q4_pct,
    blended_pct,
    rs_rating,
    momentum_rank,
    lastupdated
)
COMMENT '{"order":49,"target":"relative_strength_ranks","sources":["relative_strength_base"],"chunk_size":"1m"}'
AS
WITH
updates_dates AS (
    SELECT COALESCE(s.date, t.date) AS date
    FROM (
        SELECT date, max(lastupdated) AS source_last_updated
        FROM relative_strength_base FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) s
    FULL OUTER JOIN (
        SELECT date, max(lastupdated) AS target_last_updated
        FROM relative_strength_ranks FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) t ON s.date = t.date
    WHERE t.target_last_updated IS NULL
       OR s.source_last_updated > t.target_last_updated
),
base AS (
    -- One row per (ticker, date): pre-#174 base may carry dual-pool rows whose
    -- perf values are identical anyway; argMax(lastupdated) mirrors the
    -- ReplacingMergeTree key so the winner is deterministic even then.
    SELECT
        ticker,
        date,
        argMax(yearly_performance, lastupdated) AS yearly_performance,
        argMax(performance_6m, lastupdated) AS performance_6m,
        argMax(performance_3m, lastupdated) AS performance_3m,
        argMax(performance_1m, lastupdated) AS performance_1m,
        argMax(performance_9m, lastupdated) AS performance_9m,
        argMax(performance_q1, lastupdated) AS performance_q1,
        argMax(performance_q2, lastupdated) AS performance_q2,
        argMax(performance_q3, lastupdated) AS performance_q3,
        argMax(performance_q4, lastupdated) AS performance_q4,
        argMax(price_relative_ratio, lastupdated) AS price_relative_ratio
    FROM relative_strength_base FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND date IN (SELECT date FROM updates_dates)
    GROUP BY ticker, date
),
-- Single shared universe (the shared Sharadar universe): percentiles are computed across
-- all instruments per date — stocks and ETFs rank together (IBD RS semantics).
rank_inputs AS (
    SELECT
        ticker,
        date,
        yearly_performance,
        performance_6m,
        performance_3m,
        performance_1m,
        price_relative_ratio,
        if(yearly_performance IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY yearly_performance ASC) - 1)
            / greatest(countIf(yearly_performance IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS yearly_pct,
        if(performance_6m IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_6m ASC) - 1)
            / greatest(countIf(performance_6m IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_6m_pct,
        if(performance_3m IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_3m ASC) - 1)
            / greatest(countIf(performance_3m IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_3m_pct,
        if(performance_1m IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_1m ASC) - 1)
            / greatest(countIf(performance_1m IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_1m_pct,
        -- #163 sub-period components: same NULL-safe shared-universe percentile;
        -- blend ingredients for rs_blend_profile (#161), not rs_rating inputs.
        if(performance_9m IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_9m ASC) - 1)
            / greatest(countIf(performance_9m IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_9m_pct,
        if(performance_q1 IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_q1 ASC) - 1)
            / greatest(countIf(performance_q1 IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_q1_pct,
        if(performance_q2 IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_q2 ASC) - 1)
            / greatest(countIf(performance_q2 IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_q2_pct,
        if(performance_q3 IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_q3 ASC) - 1)
            / greatest(countIf(performance_q3 IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_q3_pct,
        if(performance_q4 IS NULL, NULL,
            (row_number() OVER (PARTITION BY date ORDER BY performance_q4 ASC) - 1)
            / greatest(countIf(performance_q4 IS NOT NULL) OVER (PARTITION BY date) - 1, 1)) AS performance_q4_pct
    FROM base
),
scored AS (
    SELECT
        ticker,
        date,
        yearly_pct,
        performance_6m_pct,
        performance_3m_pct,
        performance_1m_pct,
        performance_9m_pct,
        performance_q1_pct,
        performance_q2_pct,
        performance_q3_pct,
        performance_q4_pct,
        (
            coalesce(yearly_pct, 0.0) * 0.4
            + coalesce(performance_6m_pct, yearly_pct, 0.0) * 0.2
            + coalesce(performance_3m_pct, yearly_pct, 0.0) * 0.2
            + coalesce(performance_1m_pct, yearly_pct, 0.0) * 0.2
        ) / nullIf(
            0.4 * (yearly_pct IS NOT NULL)
            + 0.2 * (performance_6m_pct IS NOT NULL OR yearly_pct IS NOT NULL)
            + 0.2 * (performance_3m_pct IS NOT NULL OR yearly_pct IS NOT NULL)
            + 0.2 * (performance_1m_pct IS NOT NULL OR yearly_pct IS NOT NULL),
            0.0
        ) AS blended_pct
    FROM rank_inputs
)
SELECT
    ticker,
    date,
    yearly_pct,
    performance_6m_pct,
    performance_3m_pct,
    performance_1m_pct,
    performance_9m_pct,
    performance_q1_pct,
    performance_q2_pct,
    performance_q3_pct,
    performance_q4_pct,
    blended_pct,
    if(blended_pct IS NULL, NULL,
        (row_number() OVER (PARTITION BY date ORDER BY blended_pct ASC) - 1)
        / greatest(countIf(blended_pct IS NOT NULL) OVER (PARTITION BY date) - 1, 1) * 100) AS rs_rating,
    rank() OVER (PARTITION BY date ORDER BY blended_pct IS NULL ASC, blended_pct DESC) AS momentum_rank,
    now()
FROM scored;
