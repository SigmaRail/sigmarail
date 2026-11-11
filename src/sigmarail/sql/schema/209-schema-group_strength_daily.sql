-- Multi-level x multi-horizon group-strength grid (VeraProjects#165).
-- One row per (level, group_name, horizon, date): member aggregate of the
-- shared-universe component percentiles from relative_strength_ranks over
-- PIT-classified, tradeable-gated members. Replaces the single-level
-- industry_group_strength semantics; the legacy table stays populated by
-- transform 55 until consumers migrate.
CREATE TABLE IF NOT EXISTS group_strength_daily
(
    `date` Date COMMENT 'Trading date of the group score.',
    `level` LowCardinality(String) COMMENT 'Classification level: sector | famaindustry | industry (Sharadar columns; gic_* levels added when #166 lands).',
    `group_name` String COMMENT 'Group name at the level (e.g. Energy, Trading, Semiconductors).',
    `horizon` LowCardinality(String) COMMENT 'Component horizon the score aggregates: perf_1y | perf_6m | perf_3m | perf_1m.',
    `member_count` UInt32 COMMENT 'Tradeable-gated members with a non-NULL component pct for this horizon and a PIT classification at this level.',
    `score` Nullable(Float64) COMMENT 'Blended group score [0,1]: mean of score_mean and score_breadth.',
    `score_mean` Nullable(Float64) COMMENT 'Method 1 — mean of member component percentiles [0,1].',
    `score_breadth` Nullable(Float64) COMMENT 'Method 2 — share of members with component pct >= 0.80 [0,1].',
    `group_rank` Nullable(Float64) COMMENT 'Percentile rank of score across groups within (date, level, horizon), scaled 0-100.',
    `rank_change_1d` Nullable(Int32) COMMENT 'group_rank(today) - group_rank(prior session); NULL on the first populated session.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (level, group_name, horizon, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: group_strength_daily
-- =============================================================================
-- Multi-level x multi-horizon group-strength grid (VeraProjects#165).
-- Populates group_strength_daily for a given date chunk.
-- Expects parameters: chunk_start_date, chunk_end_date
--
-- Members: shared-universe ranks rows gated to tradeable names
-- (close >= 10 AND close*avg_vol_20d >= $20M, matching the
-- broad_market_constituents liquidity bar) and PIT-classified via
-- ASOF-joined ticker_classification_daily (#164) — no lookahead.
-- Score = mean of method-1 (mean member component pct) and method-2
-- (breadth: share of members at pct >= 0.80), mirroring Deepvue's two
-- methodologies. group_rank percentiles score across groups within
-- (date, level, horizon); rank_change_1d diffs the prior session.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_group_strength_daily;

CREATE VIEW IF NOT EXISTS xform_group_strength_daily (
    date,
    level,
    group_name,
    horizon,
    member_count,
    score,
    score_mean,
    score_breadth,
    group_rank,
    rank_change_1d,
    lastupdated
)
COMMENT '{"order":134,"target":"group_strength_daily","sources":["relative_strength_ranks","daily_metrics","ticker_classification_daily"],"chunk_size":"1m"}'
AS
WITH
-- Freshness: only dates whose ranks data is newer than the grid.
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
        FROM group_strength_daily FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) t ON s.date = t.date
    WHERE t.target_last_updated IS NULL
       OR s.source_last_updated > t.target_last_updated
),
members AS (
    SELECT
        r.ticker AS ticker,
        r.date AS trade_date,
        r.yearly_pct,
        r.performance_6m_pct,
        r.performance_3m_pct,
        r.performance_1m_pct,
        c.sector,
        c.famaindustry,
        c.industry
    FROM relative_strength_ranks r FINAL
    INNER JOIN updates_dates ud ON r.date = ud.date
    ASOF LEFT JOIN ticker_classification_daily c
        ON c.ticker = r.ticker AND r.date >= c.date
    INNER JOIN daily_metrics dm FINAL
        ON dm.ticker = r.ticker AND dm.date = r.date
    WHERE r.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND dm.`close` >= 10.0
      AND dm.`close` * dm.avg_vol_20d >= 20000000
),
-- Long form: one row per member x (level, horizon). Unclassified members
-- (empty/NULL group names) drop out per level; members with a NULL pct for
-- the horizon drop out of that horizon's group.
long AS (
    SELECT
        m.trade_date AS date,
        lh.1 AS level,
        lh.2 AS group_name,
        lh.3 AS horizon,
        lh.4 AS pct
    FROM members AS m
    ARRAY JOIN [
        ('sector',      sector,      'perf_1y', yearly_pct),
        ('sector',      sector,      'perf_6m', performance_6m_pct),
        ('sector',      sector,      'perf_3m', performance_3m_pct),
        ('sector',      sector,      'perf_1m', performance_1m_pct),
        ('famaindustry', famaindustry, 'perf_1y', yearly_pct),
        ('famaindustry', famaindustry, 'perf_6m', performance_6m_pct),
        ('famaindustry', famaindustry, 'perf_3m', performance_3m_pct),
        ('famaindustry', famaindustry, 'perf_1m', performance_1m_pct),
        ('industry',    industry,    'perf_1y', yearly_pct),
        ('industry',    industry,    'perf_6m', performance_6m_pct),
        ('industry',    industry,    'perf_3m', performance_3m_pct),
        ('industry',    industry,    'perf_1m', performance_1m_pct)
    ] AS lh
    WHERE lh.2 IS NOT NULL AND lh.2 != ''
      AND lh.4 IS NOT NULL
),
agg AS (
    SELECT
        date,
        level,
        group_name,
        horizon,
        count() AS member_count,
        avg(pct) AS score_mean,
        countIf(pct >= 0.80) / count() AS score_breadth
    FROM long
    GROUP BY date, level, group_name, horizon
),
ranked AS (
    SELECT
        date,
        level,
        group_name,
        horizon,
        member_count,
        (score_mean + score_breadth) / 2.0 AS score,
        score_mean,
        score_breadth,
        (row_number() OVER (PARTITION BY date, level, horizon ORDER BY (score_mean + score_breadth) / 2.0 ASC) - 1)
            / greatest(count() OVER (PARTITION BY date, level, horizon) - 1, 1)
            * 100 AS group_rank
    FROM agg
),
-- rank_change_1d diffs the prior emitted session. Self-joining the target
-- table cannot see rows from this same INSERT, so union the ranked chunk
-- with already-stored prior rows and take lagInFrame per group.
session_chain AS (
    SELECT
        date, level, group_name, horizon,
        member_count, score, score_mean, score_breadth, group_rank,
        lagInFrame(group_rank) OVER (
            PARTITION BY level, group_name, horizon ORDER BY date
        ) AS prior_group_rank
    FROM (
        SELECT date, level, group_name, horizon,
               member_count, score, score_mean, score_breadth, group_rank
        FROM ranked
        UNION ALL
        SELECT date, level, group_name, horizon,
               member_count, score, score_mean, score_breadth, group_rank
        FROM group_strength_daily FINAL
        WHERE date < toDate({chunk_start_date:String})
    )
)
SELECT
    date,
    level,
    group_name,
    horizon,
    member_count,
    score,
    score_mean,
    score_breadth,
    group_rank,
    if(prior_group_rank IS NULL, NULL,
       toInt32(round(group_rank - prior_group_rank))) AS rank_change_1d,
    now() AS lastupdated
FROM session_chain
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
