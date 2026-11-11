-- Daily-grain stage analysis projection and supporting research/allocation metrics.
-- Canonical stage_code/stage_duration are projected from daily_metrics_derived.
-- Stage Analysis Projection
-- The canonical daily stage machine is owned by daily_metrics_derived (transform 402).
-- This daily-grain table projects that result and adds research/allocation context; it
-- must not calculate another daily or weekly stage classifier.

CREATE TABLE IF NOT EXISTS stage_analysis
(
    `ticker` String COMMENT 'Equity ticker symbol',
    `date` Date COMMENT 'Trading session date',
    `lastupdated` DateTime COMMENT 'Timestamp when this record was calculated and inserted',
    `stage_code` Nullable(String) COMMENT 'Canonical daily stage token, including substage when available (for example 2B); projected from daily_metrics_derived.stage_code.',
    `stage_duration` Nullable(UInt32) COMMENT 'Consecutive valid daily observations in the current detailed stage_code; projected from daily_metrics_derived.stage_duration.',
    `stage_primary` Nullable(Enum8('1' = 1, '2' = 2, '3' = 3, '4' = 4)) COMMENT 'Temporary broad-stage compatibility alias derived from the canonical daily stage_code.',
    `allocation_fraction` Float32 COMMENT 'Allocation fraction (0..1) implied by stage_primary',
    `smoothed_allocation` Float32 COMMENT 'Smoothed allocation fraction (0..1) for stability',
    `sma30w` Float32 COMMENT 'SPY-equivalent 30-week simple moving average (primary trend)',
    `sma50w` Float32 COMMENT '50-week simple moving average (long-term trend filter)',
    `sma50d` Float32 COMMENT '50-day simple moving average',
    `sma10w` Float32 COMMENT '10-week simple moving average',
    `sma200d` Float32 COMMENT '200-day simple moving average (long-term trend)',
    `sma30w_slope` Float32 COMMENT '30-week SMA slope',
    `sma50w_slope` Float32 COMMENT '50-week SMA slope',
    `sma50d_slope_20d` Float32 COMMENT '50-day SMA slope over ~20 trading days',
    `sma10w_slope` Float32 COMMENT '10-week SMA slope',
    `sma200d_trend` Float32 COMMENT '200-day SMA trend metric',
    `price_vs_sma30w` Float32 COMMENT 'Price distance from 30-week SMA (ratio or percent, transform-defined)',
    `price_vs_sma50w` Float32 COMMENT 'Price distance from 50-week SMA (ratio or percent, transform-defined)',
    `price_vs_sma50d` Float32 COMMENT 'Price distance from 50-day SMA (ratio or percent, transform-defined)',
    `price_vs_sma10w` Float32 COMMENT 'Price distance from 10-week SMA (ratio or percent, transform-defined)',
    `volume_trend` Float32 COMMENT 'Volume trend metric (accumulation/distribution proxy)',
    `volume_sma_ratio` Float32 COMMENT 'Current volume vs its moving average',
    `volume_breakout_ratio` Float32 COMMENT 'Volume on breakout days vs baseline',
    `volume_accumulation` Float32 COMMENT 'Volume accumulation score',
    `volume_divergence` Float32 COMMENT 'Volume divergence vs price trend',
    `volume_breakout_strength` Float32 COMMENT 'Strength of volume breakout confirmation',
    `relative_strength_vs_spy` Float32 COMMENT 'Relative strength vs SPY benchmark',
    `relative_strength_vs_sector` Nullable(Float32) COMMENT 'Percentile rank (0-100) of the tickers 3m performance within its PIT sector (ticker_classification_daily). NULL when unclassified, when fewer than 5 sector members have perf_3m, or when the tickers own perf_3m is NULL.',
    `days_in_stage` UInt16 COMMENT 'Days in the current primary stage',
    `days_in_substage` UInt16 COMMENT 'Days in the current substage',
    `stage_transition` String COMMENT 'Transition type (NEW, CONTINUING, CHANGING)',
    `trend_duration_weeks` UInt16 COMMENT 'Weeks in the current trend direction',
    `ma_alignment_score` Float32 COMMENT 'Moving-average alignment score (0-100)',
    `trend_consistency` Float32 COMMENT 'Trend consistency score',
    `momentum_4w` Float32 COMMENT '4-week momentum metric',
    `momentum_12w` Float32 COMMENT '12-week momentum metric',
    `momentum_26w` Float32 COMMENT '26-week momentum metric',
    `risk_level` Enum8('Low' = 0, 'Medium' = 1, 'High' = 2, 'Very High' = 3, 'Unknown' = 4) COMMENT 'Risk level classification (enum; transform-defined mapping)',
    `volatility_regime` Enum8('Low Volatility' = 0, 'Normal Volatility' = 1, 'High Volatility' = 2) COMMENT 'Volatility regime classification (enum; transform-defined mapping)',
    `trend_regime` Enum8('Bull Market' = 0, 'Bear Market' = 1, 'Neutral' = 2) COMMENT 'Trend regime classification (enum; based on long-term trend filter)',
    `stage_quality` Float32 COMMENT 'Quality score for current stage (0-100)',
    `breakout_strength` Float32 COMMENT 'Strength of breakout (if applicable)',
    `closeadj` Float32 COMMENT 'Split-adjusted close',
    `volume` UInt64 COMMENT 'Share volume',
    `high` Float32 COMMENT 'Session high',
    `low` Float32 COMMENT 'Session low',
    `open` Float32 COMMENT 'Session open'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- NORMALIZATION POLICY (Option A):
--   - Stage classification and related ratios use split-adjusted price series (daily_metrics.close and weekly_metrics.close).
--   - This avoids dividend-adjustment artifacts in stage transitions and keeps behavior consistent with core OHLCV.
--   - closeadj remains available as a passthrough field for analytics, but does not drive stage logic.
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of stage analysis for tickers that haven't changed
--
-- SMOOTHING & CHUNK LOOKBACK:
--   - smoothed_allocation is a 5-day SMA of allocation_fraction, computed with a
--     PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW window.
--   - To avoid chunk-boundary underfill, the source rows are read with a 10-day lookback
--     beyond chunk_start, and the outer query then filters rows back to the real chunk range
--     before INSERT. This guarantees the 5-day window is always fully populated within chunk.
--
-- Detailed daily duration comes from the full-history canonical stage sequence;
-- it is independent of the current populate chunk.
-- Source tables use monthly partitions and replacement keys include date, so
-- evaluating FINAL one partition at a time preserves results while bounding
-- memory when the ASOF inputs span the full historical series.
-- Weekly ASOF inputs retain the 21-day carry-in needed to cover the daily
-- transform's 14-day smoothing lookback plus the prior completed-week value.
-- Tickers whose first daily row has no match in that window get one exact
-- historical seed row, preserving ASOF behavior across sparse weekly history.
-- Use 3-month base chunks; the populate runner reduces failed ranges through
-- its existing recovery ladder, avoiding repeated 6-month attempts on dense
-- history while retaining larger work units where the data permits them.
-- Convert weekly availability cutoffs to native week-key bounds so ClickHouse
-- can prune weekly source partitions.
--
DROP VIEW IF EXISTS xform_stage_analysis;

CREATE VIEW IF NOT EXISTS xform_stage_analysis
COMMENT '{"order":64,"target":"stage_analysis","sources":["daily_metrics","weekly_metrics_derived","weekly_metrics","daily_metrics_derived","relative_strength","ticker_classification_daily"],"chunk_size":"3m","do_not_merge_across_partitions_select_final":1}'
AS
WITH
chunk_stock_first AS (
    SELECT ticker, min(date) AS first_stock_date
    FROM daily_metrics FINAL
    WHERE date BETWEEN addDays(toDate({chunk_start_date:String}), -14)
                   AND toDate({chunk_end_date:String})
    GROUP BY ticker
),
weekly_derived_recent AS (
    SELECT
        ticker,
        date + toIntervalDay(4) AS available_date,
        stage_code,
        sma30w_slope,
        sma50w_slope
    FROM weekly_metrics_derived FINAL
    WHERE date <= addDays(toDate({chunk_end_date:String}), -4)
      AND date >= addDays(toDate({chunk_start_date:String}), -25)
),
weekly_derived_missing AS (
    SELECT stock.ticker
    FROM chunk_stock_first AS stock
    ASOF LEFT JOIN (
        SELECT ticker, available_date
        FROM weekly_derived_recent
        ORDER BY ticker, available_date
    ) AS recent
      ON (stock.ticker = recent.ticker)
     AND (stock.first_stock_date >= recent.available_date)
    WHERE recent.available_date = toDate(0)
),
weekly_derived_seed AS (
    SELECT
        ticker,
        tupleElement(seed, 1) + toIntervalDay(4) AS available_date,
        tupleElement(seed, 2) AS stage_code,
        tupleElement(seed, 3) AS sma30w_slope,
        tupleElement(seed, 4) AS sma50w_slope
    FROM (
        SELECT
            ticker,
            argMax(tuple(date, stage_code, sma30w_slope, sma50w_slope), date) AS seed
        FROM weekly_metrics_derived FINAL
        WHERE date < addDays(toDate({chunk_start_date:String}), -25)
          AND ticker IN (SELECT ticker FROM weekly_derived_missing)
        GROUP BY ticker
    )
),
weekly_derived_inputs AS (
    SELECT ticker, available_date, stage_code, sma30w_slope, sma50w_slope
    FROM weekly_derived_recent
    UNION ALL
    SELECT ticker, available_date, stage_code, sma30w_slope, sma50w_slope
    FROM weekly_derived_seed
),
weekly_sma_recent AS (
    SELECT
        ticker,
        date + toIntervalDay(4) AS available_date,
        sma10w,
        sma30w,
        sma50w
    FROM weekly_metrics FINAL
    WHERE date <= addDays(toDate({chunk_end_date:String}), -4)
      AND date >= addDays(toDate({chunk_start_date:String}), -25)
),
weekly_sma_missing AS (
    SELECT stock.ticker
    FROM chunk_stock_first AS stock
    ASOF LEFT JOIN (
        SELECT ticker, available_date
        FROM weekly_sma_recent
        ORDER BY ticker, available_date
    ) AS recent
      ON (stock.ticker = recent.ticker)
     AND (stock.first_stock_date >= recent.available_date)
    WHERE recent.available_date = toDate(0)
),
weekly_sma_seed AS (
    SELECT
        ticker,
        tupleElement(seed, 1) + toIntervalDay(4) AS available_date,
        tupleElement(seed, 2) AS sma10w,
        tupleElement(seed, 3) AS sma30w,
        tupleElement(seed, 4) AS sma50w
    FROM (
        SELECT
            ticker,
            argMax(tuple(date, sma10w, sma30w, sma50w), date) AS seed
        FROM weekly_metrics FINAL
        WHERE date < addDays(toDate({chunk_start_date:String}), -25)
          AND ticker IN (SELECT ticker FROM weekly_sma_missing)
        GROUP BY ticker
    )
),
weekly_sma_inputs AS (
    SELECT ticker, available_date, sma10w, sma30w, sma50w
    FROM weekly_sma_recent
    UNION ALL
    SELECT ticker, available_date, sma10w, sma30w, sma50w
    FROM weekly_sma_seed
)
SELECT *
FROM (
SELECT
    stock.ticker AS ticker,
    stock.date AS date,
    now() AS lastupdated,

    -- Canonical daily stage projection from the timeframe-native owner.
    derived.stage_code AS stage_code,
    derived.stage_duration AS stage_duration,
    -- One broad-stage compatibility alias remains for established callers.
    CAST(nullIf(left(ifNull(derived.stage_code, ''), 1), ''), 'Nullable(Enum8(\'1\'=1,\'2\'=2,\'3\'=3,\'4\'=4))') AS stage_primary,

    -- Preserve the existing allocation mapping and its weekly decision clock.
    -- The input now comes from the canonical completed-week series, not a
    -- separately calculated weekly classifier.
    CASE
        -- Stage 1: Basing - 0 allocation (avoid trading)
        WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '1' THEN 0.0

        -- Stage 2: Advancing - Trend regime affects allocation
        WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '2' THEN
            CASE
                WHEN weekly.sma50w_slope > 0.002 THEN 1.0    -- Bull market: Full allocation
                WHEN weekly.sma50w_slope < -0.002 THEN 0.3   -- Bear market: Reduced allocation
                ELSE 0.7  -- Neutral: Moderate allocation
            END

        -- Stage 3: Topping - Trend regime affects exit urgency
        WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '3' THEN
            CASE
                WHEN weekly.sma50w_slope > 0.002 THEN 0.2    -- Bull market: Hold some position
                WHEN weekly.sma50w_slope < -0.002 THEN 0.0   -- Bear market: Exit immediately
                ELSE 0.1  -- Neutral: Minimal allocation
            END

        -- Stage 4: Declining - 0 allocation (no long positions)
        WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '4' THEN 0.0

        ELSE 0.0
    END AS allocation_fraction,

    -- Smoothed allocation: 5-day trailing SMA of allocation_fraction
    -- Dampens single-day stage flips. Chunk lookback (-10 days in outer WHERE)
    -- ensures this window is always fully populated for rows actually INSERTed.
    avg(
        CASE
            WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '1' THEN 0.0
            WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '2' THEN
                CASE
                    WHEN weekly.sma50w_slope > 0.002 THEN 1.0
                    WHEN weekly.sma50w_slope < -0.002 THEN 0.3
                    ELSE 0.7
                END
            WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '3' THEN
                CASE
                    WHEN weekly.sma50w_slope > 0.002 THEN 0.2
                    WHEN weekly.sma50w_slope < -0.002 THEN 0.0
                    ELSE 0.1
                END
            WHEN substring(ifNull(weekly.stage_code, ''), 1, 1) = '4' THEN 0.0
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY stock.ticker
        ORDER BY stock.date
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
    ) AS smoothed_allocation,

    -- Moving Average Values (required by schema)
    COALESCE(weekly_sma.sma30w, 0.0) AS sma30w,
    COALESCE(weekly_sma.sma50w, 0.0) AS sma50w,
    COALESCE(stock.sma50d, 0.0) AS sma50d,
    COALESCE(weekly_sma.sma10w, 0.0) AS sma10w,
    COALESCE(stock.sma200d, 0.0) AS sma200d,

    -- Moving Average Slopes
    COALESCE(weekly.sma30w_slope, 0.0) AS sma30w_slope,
    COALESCE(weekly.sma50w_slope, 0.0) AS sma50w_slope,
    COALESCE(derived.sma50d_slope_20d, 0.0) AS sma50d_slope_20d,
    0.0 AS sma10w_slope,
    COALESCE(derived.sma200d_trend, 0.0) AS sma200d_trend,

    -- Price relationships to MAs
    CASE
        WHEN weekly_sma.sma30w > 0 THEN (stock.close - weekly_sma.sma30w) / weekly_sma.sma30w
        ELSE 0.0
    END AS price_vs_sma30w,
    CASE
        WHEN weekly_sma.sma50w > 0 THEN (stock.close - weekly_sma.sma50w) / weekly_sma.sma50w
        ELSE 0.0
    END AS price_vs_sma50w,
    CASE
        WHEN stock.sma50d > 0 THEN (stock.close - stock.sma50d) / stock.sma50d
        ELSE 0.0
    END AS price_vs_sma50d,
    CASE
        WHEN weekly_sma.sma10w > 0 THEN (stock.close - weekly_sma.sma10w) / weekly_sma.sma10w
        ELSE 0.0
    END AS price_vs_sma10w,

    -- Enhanced Volume Analysis
    CASE
        WHEN stock.volume > stock.avg_vol_20d * 1.5 THEN 1.0  -- Strong accumulation
        WHEN stock.volume > stock.avg_vol_20d * 1.2 THEN 0.5  -- Moderate accumulation
        WHEN stock.volume < stock.avg_vol_20d * 0.7 THEN -0.5 -- Distribution
        WHEN stock.volume < stock.avg_vol_20d * 0.5 THEN -1.0 -- Strong distribution
        ELSE 0.0
    END AS volume_trend,

    stock.volume / coalesce(stock.avg_vol_20d, stock.volume) AS volume_sma_ratio,

    CASE
        WHEN stock.volume > stock.avg_vol_20d * 2.0 THEN 2.0
        WHEN stock.volume > stock.avg_vol_20d * 1.5 THEN 1.5
        ELSE 1.0
    END AS volume_breakout_ratio,

    -- Volume accumulation score (cumulative)
    CASE
        WHEN stock.volume > stock.avg_vol_20d * 1.3 AND stock.close > stock.open THEN 1.0
        WHEN stock.volume > stock.avg_vol_20d * 1.3 AND stock.close < stock.open THEN -1.0
        ELSE 0.0
    END AS volume_accumulation,

    -- Volume divergence vs price
    CASE
        WHEN stock.close > stock.open AND stock.volume < stock.avg_vol_20d * 0.8 THEN -1.0
        WHEN stock.close < stock.open AND stock.volume > stock.avg_vol_20d * 1.2 THEN 1.0
        ELSE 0.0
    END AS volume_divergence,

    -- Volume breakout strength
    CASE
        WHEN stock.volume > stock.avg_vol_20d * 2.5 THEN 3.0
        WHEN stock.volume > stock.avg_vol_20d * 2.0 THEN 2.0
        WHEN stock.volume > stock.avg_vol_20d * 1.5 THEN 1.0
        ELSE 0.0
    END AS volume_breakout_strength,

    -- Relative Strength
    CASE
        WHEN rs.rs_rating IS NOT NULL THEN rs.rs_rating - 1.0
        ELSE 0.0
    END AS relative_strength_vs_spy,
    -- #168: percentile of the ticker's 3m performance among its PIT sector
    -- peers (0-100). NULL when the sector is unclassified, when fewer than 5
    -- sector members have perf_3m, or when the ticker's own perf_3m is NULL.
    -- ASC ordering puts NULL perfs last; the denominator counts only members
    -- with perf_3m so NULLs never stretch valid members' percentiles.
    if(
        cls.sector IS NULL OR cls.sector = ''
        OR countIf(rs.performance_3m IS NOT NULL) OVER (PARTITION BY stock.date, cls.sector) < 5
        OR rs.performance_3m IS NULL,
        NULL,
        (row_number() OVER (
            PARTITION BY stock.date, cls.sector
            ORDER BY rs.performance_3m ASC, stock.ticker ASC
        ) - 1)
        / greatest(countIf(rs.performance_3m IS NOT NULL) OVER (PARTITION BY stock.date, cls.sector) - 1, 1)
        * 100
    ) AS relative_strength_vs_sector,

    -- Compatibility duration fields now reflect the canonical detailed stage.
    toUInt16(least(coalesce(derived.stage_duration, 0), toUInt32(65535))) AS days_in_stage,
    toUInt16(least(coalesce(derived.stage_duration, 0), toUInt32(65535))) AS days_in_substage,
    multiIf(
        isNull(derived.stage_duration), 'UNKNOWN',
        derived.stage_duration = 1, 'NEW',
        'CONTINUING'
    ) AS stage_transition,
    0 AS trend_duration_weeks,

    -- MA alignment score (0-100)
    CASE
        WHEN weekly.sma30w_slope > 0.002 AND derived.sma50d_slope_20d > 0.001 AND stock.close > weekly_sma.sma30w AND stock.close > stock.sma50d THEN 100
        WHEN weekly.sma30w_slope < -0.002 AND derived.sma50d_slope_20d < -0.001 AND stock.close < weekly_sma.sma30w AND stock.close < stock.sma50d THEN 0
        WHEN weekly.sma30w_slope > 0.001 AND stock.close > weekly_sma.sma30w THEN 75
        WHEN weekly.sma30w_slope < -0.001 AND stock.close < weekly_sma.sma30w THEN 25
        ELSE 50
    END AS ma_alignment_score,

    -- Trend consistency score
    CASE
        WHEN abs(COALESCE(weekly.sma30w_slope, 0.0)) > 0.002 AND abs(COALESCE(derived.sma50d_slope_20d, 0.0)) > 0.001 THEN 1.0
        WHEN abs(COALESCE(weekly.sma30w_slope, 0.0)) > 0.001 OR abs(COALESCE(derived.sma50d_slope_20d, 0.0)) > 0.001 THEN 0.5
        ELSE 0.0
    END AS trend_consistency,

    -- Momentum metrics (required by schema)
    COALESCE(derived.perf_1m, 0.0) AS momentum_4w,  -- 4 weeks ≈ 1 month
    COALESCE(derived.perf_3m, 0.0) AS momentum_12w,  -- 12 weeks ≈ 3 months
    COALESCE(derived.perf_6m, 0.0) AS momentum_26w,  -- 26 weeks ≈ 6 months

    -- Risk level (SSOT: daily_metrics.atr_14; schema 199 removed derived ATR dupes)
    CASE
        WHEN (coalesce(stock.atr_14, 0.0) / nullIf(stock.close, 0)) > 0.05 THEN 3
        WHEN (coalesce(stock.atr_14, 0.0) / nullIf(stock.close, 0)) > 0.03 THEN 2
        WHEN (coalesce(stock.atr_14, 0.0) / nullIf(stock.close, 0)) > 0.015 THEN 1
        ELSE 0
    END AS risk_level,

    -- Volatility regime
    CASE
        WHEN (coalesce(stock.atr_14, 0.0) / nullIf(stock.close, 0)) > 0.03 THEN 2
        WHEN (coalesce(stock.atr_14, 0.0) / nullIf(stock.close, 0)) < 0.015 THEN 0
        ELSE 1
    END AS volatility_regime,

    -- Trend regime based on 50-week SMA
    CASE
        WHEN weekly.sma50w_slope IS NOT NULL AND weekly.sma50w_slope > 0.002 THEN 0  -- Bull Market: 50w SMA rising
        WHEN weekly.sma50w_slope IS NOT NULL AND weekly.sma50w_slope < -0.002 THEN 1  -- Bear Market: 50w SMA falling
        ELSE 2  -- Neutral: 50w SMA flat or insufficient data
    END AS trend_regime,

    -- Stage quality and breakout strength
    CASE
        WHEN derived.stage_code = '2A' AND stock.volume > stock.avg_vol_20d * 1.5 THEN 90
        WHEN derived.stage_code = '2A' THEN 80
        WHEN derived.stage_code = '2B' THEN 60
        WHEN derived.stage_code = '1B' THEN 70
        WHEN derived.stage_code = '3A' THEN 40
        WHEN derived.stage_code = '4A' THEN 20
        ELSE 50
    END AS stage_quality,

    CASE
        WHEN stock.volume > stock.avg_vol_20d * 2.0 AND stock.close > stock.open THEN 3.0
        WHEN stock.volume > stock.avg_vol_20d * 1.5 AND stock.close > stock.open THEN 2.0
        WHEN stock.volume > stock.avg_vol_20d * 1.2 AND stock.close > stock.open THEN 1.0
        ELSE 0.0
    END AS breakout_strength,

    -- Basic stock metrics
    stock.closeadj AS closeadj,
    stock.volume AS volume,
    stock.high AS high,
    stock.low AS low,
    stock.open AS open

FROM daily_metrics AS stock FINAL
LEFT JOIN daily_metrics_derived AS derived FINAL ON (stock.ticker = derived.ticker) AND (stock.date = derived.date)
-- weekly_metrics rows are keyed by the week's Monday but contain the completed
-- bar. Make them visible only at the conservative Friday cutoff so Monday-
-- Thursday daily history cannot see that week's eventual close. For a holiday
-- shortened week this delays use until the next session, which is causal.
ASOF LEFT JOIN (
    SELECT ticker, available_date, stage_code, sma30w_slope, sma50w_slope
    FROM weekly_derived_inputs
    ORDER BY ticker, available_date
) AS weekly ON (stock.ticker = weekly.ticker) AND (stock.date >= weekly.available_date)
ASOF LEFT JOIN (
    SELECT ticker, available_date, sma10w, sma30w, sma50w
    FROM weekly_sma_inputs
    ORDER BY ticker, available_date
) AS weekly_sma ON (stock.ticker = weekly_sma.ticker) AND (stock.date >= weekly_sma.available_date)
LEFT JOIN relative_strength AS rs FINAL ON (stock.ticker = rs.ticker) AND (stock.date = rs.date)
-- PIT sector labels for relative_strength_vs_sector (#168) — no lookahead
-- from current-state tickers.
ASOF LEFT JOIN (
    SELECT ticker, date, sector
    FROM ticker_classification_daily
    WHERE date <= toDate({chunk_end_date:String})
) AS cls ON (cls.ticker = stock.ticker) AND (stock.date >= cls.date)
-- Read 10 trading-day lookback beyond the chunk so the 5-day smoothing window
-- inside the subquery is always fully populated for the rows we actually INSERT.
WHERE stock.date >= addDays(toDate({chunk_start_date:String}), -14)
  AND stock.date <= toDate({chunk_end_date:String})
) AS scored
-- Outer filter drops the lookback rows so only the real chunk range is inserted.
WHERE scored.date >= toDate({chunk_start_date:String});
