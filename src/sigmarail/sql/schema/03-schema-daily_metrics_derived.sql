CREATE TABLE IF NOT EXISTS daily_metrics_derived
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record',
    `sma10d_trend` Nullable(Float64) COMMENT 'Formula: (close - sma10d) / sma10d. Normalized distance from price to the 10-day SMA. Positive means price is above SMA.',
    `sma20d_trend` Nullable(Float64) COMMENT 'Formula: (close - sma20d) / sma20d. Normalized distance from price to the 20-day SMA.',
    `sma50d_trend` Nullable(Float64) COMMENT 'Formula: (close - sma50d) / sma50d. Normalized distance from price to the 50-day SMA.',
    `sma150d_trend` Nullable(Float64) COMMENT 'Formula: (close - sma150d) / sma150d. Normalized distance from price to the 150-day SMA.',
    `sma200d_trend` Nullable(Float64) COMMENT 'Formula: (close - sma200d) / sma200d. Normalized distance from price to the 200-day SMA.',
    `sma50d_slope_20d` Nullable(Float64) COMMENT 'Formula: (sma50d / sma50d_lag_20d) - 1. The 20-day slope of the 50-day SMA.',
    `sma200d_slope_20d` Nullable(Float64) COMMENT 'Formula: (sma200d / sma200d_lag_20d) - 1. The 20-day slope of the 200-day SMA.',
    `perf_5d` Nullable(Float64) COMMENT 'Formula: (close / close_lag_5d) - 1. 5-day split-adjusted price return.',
    `perf_10d` Nullable(Float64) COMMENT 'Formula: (close / close_lag_10d) - 1. 10-day split-adjusted price return.',
    `perf_1m` Nullable(Float64) COMMENT 'Formula: (close / close_lag_21d) - 1. 1-month (21 trading days) split-adjusted price return.',
    `perf_3m` Nullable(Float64) COMMENT 'Formula: (close / close_lag_63d) - 1. 3-month (63 trading days) split-adjusted price return.',
    `perf_6m` Nullable(Float64) COMMENT 'Formula: (close / close_lag_126d) - 1. 6-month (126 trading days) split-adjusted price return.',
    `perf_1y` Nullable(Float64) COMMENT 'Formula: (close / close_lag_252d) - 1. 1-year (252 trading days) split-adjusted price return.',
    `perf_9m` Nullable(Float64) COMMENT 'Formula: (close / close_lag_189d) - 1. 9-month (189 trading days) split-adjusted price return.',
    `perf_q1` Nullable(Float64) COMMENT 'Formula: (close_lag_189d / close_lag_252d) - 1. Oldest quarter of the trailing year (days 190-252 back).',
    `perf_q2` Nullable(Float64) COMMENT 'Formula: (close_lag_126d / close_lag_189d) - 1. Second quarter back (days 127-189).',
    `perf_q3` Nullable(Float64) COMMENT 'Formula: (close_lag_63d / close_lag_126d) - 1. Third quarter back (days 64-126).',
    `perf_q4` Nullable(Float64) COMMENT 'Formula: (close / close_lag_63d) - 1. Most recent quarter (days 1-63); equals perf_3m.',
    `total_return_5d` Nullable(Float64) COMMENT 'Dividend-adjusted 5-session total return: closeadj / closeadj_lag_5d - 1.',
    `total_return_10d` Nullable(Float64) COMMENT 'Dividend-adjusted 10-session total return: closeadj / closeadj_lag_10d - 1.',
    `total_return_1m` Nullable(Float64) COMMENT 'Dividend-adjusted 21-session total return: closeadj / closeadj_lag_21d - 1.',
    `total_return_3m` Nullable(Float64) COMMENT 'Dividend-adjusted 63-session total return: closeadj / closeadj_lag_63d - 1.',
    `total_return_6m` Nullable(Float64) COMMENT 'Dividend-adjusted 126-session total return: closeadj / closeadj_lag_126d - 1.',
    `total_return_9m` Nullable(Float64) COMMENT 'Dividend-adjusted 189-session total return: closeadj / closeadj_lag_189d - 1.',
    `total_return_1y` Nullable(Float64) COMMENT 'Dividend-adjusted 252-session total return: closeadj / closeadj_lag_252d - 1.',
    `total_return_q1` Nullable(Float64) COMMENT 'Dividend-adjusted oldest quarter of the trailing year.',
    `total_return_q2` Nullable(Float64) COMMENT 'Dividend-adjusted second quarter of the trailing year.',
    `total_return_q3` Nullable(Float64) COMMENT 'Dividend-adjusted third quarter of the trailing year.',
    `total_return_q4` Nullable(Float64) COMMENT 'Dividend-adjusted most recent quarter of the trailing year.',
    `price_vs_sma50` Nullable(Float64) COMMENT 'Formula: (close / sma50d) * 100. Price as percentage of 50-day SMA.',
    `price_vs_sma150` Nullable(Float64) COMMENT 'Formula: (close / sma150d) * 100. Price as percentage of 150-day SMA.',
    `price_vs_sma200` Nullable(Float64) COMMENT 'Formula: (close / sma200d) * 100. Price as percentage of 200-day SMA.',
    `sma50_vs_sma150` Nullable(Float64) COMMENT 'Formula: (sma50d / sma150d) * 100. 50-day SMA as percentage of 150-day SMA.',
    `sma150_vs_sma200` Nullable(Float64) COMMENT 'Formula: (sma150d / sma200d) * 100. 150-day SMA as percentage of 200-day SMA.',
    `price_vs_52w_high` Nullable(Float64) COMMENT 'Formula: (close / high_52w) * 100. Price as percentage of 52-week high.',
    `atr_to_sma50` Nullable(Float64) COMMENT 'Formula: (atr_14 / sma50d) * 100. ATR as percentage of 50-day SMA.',
    `price_vs_sma20` Nullable(Float64) COMMENT 'Formula: (close / sma20d) * 100. Price as percentage of 20-day SMA.',
    `price_vs_52w_low` Nullable(Float64) COMMENT 'Formula: (close / low_52w) * 100. Price as percentage of 52-week low.',
    `volume_sma20_vs_sma50` Nullable(Float64) COMMENT 'Formula: (avg_vol_20d / avg_vol_50d) * 100. 20-day volume SMA as percentage of 50-day volume SMA.',
    `volume_trend_pct` Nullable(Float64) COMMENT 'Formula: ((avg_vol_20d / avg_vol_50d) - 1) * 100. Volume trend percentage change.',
    `price_range_52w_pct` Nullable(Float64) COMMENT 'Formula: ((high_52w - low_52w) / close) * 100. 52-week range as percentage of current price.',
    `price_to_52w_low_pct` Nullable(Float64) COMMENT 'Formula: (close / low_52w) - 1. Percentage distance of current price from its 52-week low.',
    `price_to_52w_high_pct` Nullable(Float64) COMMENT 'Formula: (close / high_52w) - 1. Percentage distance of current price from its 52-week high.',
    `vcp_tightness_5d_90d` Nullable(Float64) COMMENT 'Formula: (high_5d - low_5d) / high_90d. VCP: Volatility Contraction Pattern, measures 5-day range vs 90-day high.',
    `vcp_volume_dryup_5d_90d` Nullable(Float64) COMMENT 'Formula: avg_vol_5d / avg_vol_90d. VCP: Compares recent volume to longer-term average volume.',
    `vcp_proximity_90d` Nullable(Float64) COMMENT 'Formula: close / high_90d. VCP: Proximity of current price to the 90-day high.',
    `vcp_atr_compression_5d_90d` Nullable(Float64) COMMENT 'Formula: (high_5d - low_5d) / (high_90d - low_90d). VCP: Compares 5-day vs 90-day Average True Range.',
    `vcp_max_drawdown_90d` Nullable(Float64) COMMENT 'Formula: (high_90d - low_90d) / high_90d. VCP: 90-day range as fraction of 90d high (0–1), not standard (trough−peak)/peak drawdown.',
    `vcp_consolidation_days_5pct_30d` Nullable(UInt32) COMMENT 'VCP: Number of days in the last 30 where the daily range was less than 5% of the 30-day high.',
    `breakout_signal` Nullable(UInt8) COMMENT 'Signal (1/0) indicating if the current day high is a new 90-day high.',
    `sma200_lag_30d` Nullable(Float64) COMMENT '200-day SMA lagged 30 sessions (soft TT rising).',
    `sma200d_rising_30d` Nullable(UInt8) COMMENT '1 when SMA200 is higher than 30 trading days ago.',
    `sma200d_rising_150d` Nullable(UInt8) COMMENT '1 when SMA200 is higher than 150 trading days ago.',
    `sma20d_crossover_up` Nullable(UInt8) COMMENT '1 when price crosses up through the 20-day SMA.',
    `price_above_sma20d` Nullable(UInt8) COMMENT '1 when price is above the 20-day SMA.',
    `price_above_sma50d` Nullable(UInt8) COMMENT '1 when price is above the 50-day SMA.',
    `price_above_sma150d` Nullable(UInt8) COMMENT '1 when price is above the 150-day SMA.',
    `price_above_sma200d` Nullable(UInt8) COMMENT '1 when price is above the 200-day SMA.',
    `sma50d_above_sma150d` Nullable(UInt8) COMMENT '1 when SMA50 is above SMA150.',
    `sma50d_above_sma200d` Nullable(UInt8) COMMENT '1 when SMA50 is above SMA200.',
    `sma150d_above_sma200d` Nullable(UInt8) COMMENT '1 when SMA150 is above SMA200.',
    `price_30pct_above_52w_low` Nullable(UInt8) COMMENT '1 when price is at least 30% above the 52-week low.',
    `price_70pct_above_52w_low` Nullable(UInt8) COMMENT '1 when price is at least 70% above the 52-week low.',
    `price_within_25pct_52w_high` Nullable(UInt8) COMMENT '1 when price is within 25% of the 52-week high.',
    `stage_code` Nullable(String) COMMENT 'Detailed daily stage token from the frozen OHLCV transition replay (1A, 1B, 2A, 2B, 3A, 3B, 4A, 4B); NULL until sufficient daily moving-average history is available.',
    `stage_duration` Nullable(UInt32) COMMENT 'Consecutive valid daily observations in the current detailed stage_code.',
    `stage_transition_state` Tuple(
        UInt32,
        UInt32,
        Float64) DEFAULT tuple(toUInt32(0), toUInt32(0), toFloat64(1000000000)) COMMENT 'Internal transition checkpoint: consecutive 1A/2A counters and stage-4A low watermark for resuming the causal stage fold at chunk boundaries.',
    `stage_slope30_atr` Nullable(Float64) COMMENT '(sma150d - sma150d_lag_30d) / (atr_14 * sqrt(30)): normalized 30-session slope diagnostic; not a stage classifier.',
    `volatility_risk_pct` Nullable(Float64) COMMENT 'Volatility risk score from ATR14/close percent bands (inline; SSOT atr is daily_metrics.atr_14_pct)',
    `liquidity_risk_pct` Nullable(Float64) COMMENT 'Liquidity risk percentage based on volume patterns and average volume',
    `sector_risk_pct` Nullable(Float64) COMMENT 'Sector risk percentage based on sector volatility',
    `technical_risk_pct` Nullable(Float64) COMMENT 'Technical risk percentage based on chart patterns and technical levels',
    `fundamental_risk_pct` Nullable(Float64) COMMENT 'Fundamental risk percentage based on fundamental metrics',
    `independent_risk_score` Nullable(Float64) COMMENT 'Overall independent risk score (average of all risk factors)'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_metrics_derived
-- Populates daily_metrics_derived with derived metrics that require access to previously calculated values from daily_metrics.
-- Expects SQL variables: chunk_start_date, chunk_end_date
--
-- NORMALIZATION POLICY (Option A):
--   - Derived ratios/flags/performance are computed using split-adjusted prices from daily_metrics (`close`, `high`, `low`).
--   - This keeps derived signals consistent with the OHLCV series used in chart-based research/backtesting.
--   - Price performance uses split-adjusted close; total_return_* uses fully dividend-adjusted closeadj.
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of derived metrics for tickers that haven't changed
--
DROP VIEW IF EXISTS xform_daily_metrics_derived;

CREATE VIEW IF NOT EXISTS xform_daily_metrics_derived (
    ticker,
    date,
    lastupdated,
    sma10d_trend,
    sma20d_trend,
    sma50d_trend,
    sma150d_trend,
    sma200d_trend,
    sma50d_slope_20d,
    sma200d_slope_20d,
    perf_5d,
    perf_10d,
    perf_1m,
    perf_3m,
    perf_6m,
    perf_1y,
    perf_9m,
    perf_q1,
    perf_q2,
    perf_q3,
    perf_q4,
    total_return_5d,
    total_return_10d,
    total_return_1m,
    total_return_3m,
    total_return_6m,
    total_return_9m,
    total_return_1y,
    total_return_q1,
    total_return_q2,
    total_return_q3,
    total_return_q4,
    price_vs_sma50,
    price_vs_sma150,
    price_vs_sma200,
    sma50_vs_sma150,
    sma150_vs_sma200,
    price_vs_52w_high,
    atr_to_sma50,
    price_vs_sma20,
    price_vs_52w_low,
    volume_sma20_vs_sma50,
    volume_trend_pct,
    price_range_52w_pct,
    price_to_52w_low_pct,
    price_to_52w_high_pct,
    vcp_tightness_5d_90d,
    vcp_volume_dryup_5d_90d,
    vcp_proximity_90d,
    vcp_atr_compression_5d_90d,
    vcp_max_drawdown_90d,
    vcp_consolidation_days_5pct_30d,
    breakout_signal,
    sma200_lag_30d,
    sma200d_rising_30d,
    sma200d_rising_150d,
    sma20d_crossover_up,
    price_above_sma20d,
    price_above_sma50d,
    price_above_sma150d,
    price_above_sma200d,
    sma50d_above_sma150d,
    sma50d_above_sma200d,
    sma150d_above_sma200d,
    price_30pct_above_52w_low,
    price_70pct_above_52w_low,
    price_within_25pct_52w_high,
    stage_code,
    stage_duration,
    stage_transition_state,
    stage_slope30_atr,
    volatility_risk_pct,
    liquidity_risk_pct,
    sector_risk_pct,
    technical_risk_pct,
    fundamental_risk_pct,
    independent_risk_score
)
COMMENT '{"order":5,"target":"daily_metrics_derived","sources":["daily_metrics"],"chunk_size":"1m"}'
AS
WITH
-- BEGIN DETAILED STAGE MACHINE
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('1A', '4A', '4B'))
    AND b.2 > b.4 AND b.2 > b.5 AND b.2 < b.6 AS daily_stage_is_1a,
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('1B', '1A'))
    AND toUInt32(s.2 + toUInt32(daily_stage_is_1a(s, b))) >= 10 AS daily_stage_is_1b,
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('2A', '1A', '1B', '3A', '3B', '4A', '4B'))
    AND b.2 > b.4 AND b.2 > b.5 AND b.2 > b.6 AS daily_stage_is_2a,
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('2B', '2A'))
    AND toUInt32(if(s.1 = '2A', s.3 + toUInt32(daily_stage_is_2a(s, b)), toUInt32(daily_stage_is_2a(s, b)))) >= 10 AS daily_stage_is_2b,
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('3A', '2A', '2B'))
    AND b.2 < b.4 AND b.2 > b.5 AND b.2 > b.6 AS daily_stage_is_3a,
(s, b) -> b.7 = 1 AND (s.1 = '' OR s.1 IN ('3B', '3A'))
    AND b.2 < b.4 AND b.2 < b.5 AND b.2 > b.6 AS daily_stage_is_3b,
(s, b) -> b.7 = 1 AND s.1 IN ('', '4A', '1A', '1B', '2A', '2B', '3A', '3B', '4B')
    AND b.2 < b.4 AND b.2 < b.5 AND b.2 < b.6 AND b.2 <= s.4 AS daily_stage_is_4a,
(s, b) -> b.7 = 1 AND s.1 = '4A'
    AND b.2 > b.4 AND b.2 < b.5 AND b.2 < b.6 AS daily_stage_is_4b,
(s, b) -> multiIf(
    daily_stage_is_4b(s, b), '4B',
    daily_stage_is_4a(s, b), '4A',
    daily_stage_is_3b(s, b), '3B',
    daily_stage_is_3a(s, b), '3A',
    daily_stage_is_2b(s, b), '2B',
    daily_stage_is_2a(s, b), '2A',
    daily_stage_is_1b(s, b), '1B',
    daily_stage_is_1a(s, b), '1A',
    s.1
) AS daily_stage_next_code,
(s, b) -> if(
    b.7 = 0,
    tuple(s.1, s.2, s.3, s.4, toUInt32(0)),
    tuple(
        daily_stage_next_code(s, b),
        toUInt32(if(daily_stage_next_code(s, b) = '1A', if(daily_stage_is_1a(s, b), if(s.1 = '1A', s.2 + 1, 1), s.2), 0)),
        toUInt32(if(daily_stage_next_code(s, b) = '2A', if(daily_stage_is_2a(s, b), if(s.1 = '2A', s.3 + 1, 1), s.3), 0)),
        if(daily_stage_is_2a(s, b), toFloat64(1000000000), if(daily_stage_is_4a(s, b) OR s.1 = '4A', least(s.4, b.3), s.4)),
        if(daily_stage_next_code(s, b) = '', toUInt32(0), toUInt32(if(daily_stage_next_code(s, b) = s.1 AND s.5 > 0, s.5 + 1, 1)))
    )
) AS daily_stage_transition,
-- END DETAILED STAGE MACHINE,

-- Check freshness per ticker - only process tickers where source data is newer
ticker_freshness_check AS (
    SELECT
        dmd.ticker,
        count() as target_row_count,
        max(dmd.lastupdated) as target_last_updated
    FROM daily_metrics_derived dmd FINAL
    WHERE dmd.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY dmd.ticker
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
-- Determine which tickers need updating
-- {force_refresh:UInt8}=1 bypasses per-ticker freshness (split rewrite / repair runs).
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN {force_refresh:UInt8} = 1 THEN 1
            WHEN t.target_last_updated IS NULL THEN 1  -- New ticker
            WHEN s.source_row_count > t.target_row_count THEN 1  -- Missing rows in target for this chunk
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
),

-- Carry the transition state forward from the last row before this chunk.
-- The public code/duration are stored in their canonical columns; the tuple
-- stores only the 1A/2A counters and 4A low watermark needed by the reducer.
stage_seed_state AS (
    SELECT
        dmd.ticker,
        argMax(ifNull(dmd.stage_code, ''), dmd.date) AS prior_stage_code,
        argMax(tupleElement(dmd.stage_transition_state, 1), dmd.date) AS prior_1a_days,
        argMax(tupleElement(dmd.stage_transition_state, 2), dmd.date) AS prior_2a_days,
        argMax(tupleElement(dmd.stage_transition_state, 3), dmd.date) AS prior_4a_low,
        argMax(ifNull(dmd.stage_duration, toUInt32(0)), dmd.date) AS prior_stage_duration
    FROM daily_metrics_derived AS dmd FINAL
    -- Bound checkpoint lookup to the transform's existing 400-day source pad.
    -- A valid 200-session stage requires recent source bars; the latest emitted
    -- row in this interval already carries cumulative duration and reducer state.
    -- Without this bound, the ticker/date-ordered target is scanned from the
    -- beginning of history for every 30-day chunk, recreating the original cost.
    WHERE dmd.date >= toDate({chunk_start_date:String}) - INTERVAL 400 DAY
      AND dmd.date < toDate({chunk_start_date:String})
      AND dmd.ticker IN (SELECT ticker FROM source_freshness_check)
    GROUP BY dmd.ticker
),
stage_history_arrays AS (
    SELECT
        d.ticker AS ticker,
        if(
            ifNull(any(seed.ticker), '') = '',
            tuple('', toUInt32(0), toUInt32(0), toFloat64(1000000000), toUInt32(0)),
            tuple(
                ifNull(any(seed.prior_stage_code), ''),
                ifNull(any(seed.prior_1a_days), toUInt32(0)),
                ifNull(any(seed.prior_2a_days), toUInt32(0)),
                ifNull(any(seed.prior_4a_low), toFloat64(1000000000)),
                ifNull(any(seed.prior_stage_duration), toUInt32(0))
            )
        ) AS initial_state,
        arraySort(
            bar -> bar.1,
            groupArray(tuple(
                d.date,
                d.`close`,
                ifNull(d.low, toFloat64(1000000000)),
                d.sma50d,
                d.sma150d,
                d.sma200d,
                toUInt8(d.sma50d IS NOT NULL AND d.sma150d IS NOT NULL AND d.sma200d IS NOT NULL)
            ))
        ) AS bars
    FROM daily_metrics AS d FINAL
    INNER JOIN tickers_needing_update AS tnu ON d.ticker = tnu.ticker
    LEFT JOIN stage_seed_state AS seed ON d.ticker = seed.ticker
    WHERE d.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
      AND tnu.needs_update = 1
    GROUP BY d.ticker
),
daily_stage_history_folded AS (
    SELECT
        stage_history_arrays.ticker AS ticker,
        bars,
        initial_state,
        arrayFold(
            (states, bar) -> arrayPushBack(
                states,
                daily_stage_transition(arrayElement(states, -1), bar)
            ),
            bars,
            [initial_state]
        ) AS states
    FROM stage_history_arrays
),
stage_history AS (
    SELECT
        folded.ticker,
        arrayMap(
            (bar, state) -> tuple(bar.1, nullIf(state.1, ''), nullIf(state.5, 0), tuple(state.2, state.3, state.4)),
            folded.bars,
            arraySlice(folded.states, 2)
        ) AS stage_rows
    FROM daily_stage_history_folded AS folded
),
base_data AS (
    SELECT
        daily_metrics.ticker,
        daily_metrics.date,
        daily_metrics.`close`,
        daily_metrics.closeadj,
        daily_metrics.high,
        daily_metrics.low,
        daily_metrics.volume,
        daily_metrics.sma10d,
        daily_metrics.sma20d,
        daily_metrics.sma50d,
        daily_metrics.sma150d,
        daily_metrics.sma200d,
        daily_metrics.high_5d,
        daily_metrics.low_5d,
        daily_metrics.high_30d,
        daily_metrics.low_30d,
        daily_metrics.high_90d,
        daily_metrics.low_90d,
        daily_metrics.high_52w,
        daily_metrics.low_52w,
        daily_metrics.avg_vol_5d,
        daily_metrics.avg_vol_20d,
        daily_metrics.avg_vol_50d,
        daily_metrics.avg_vol_60d,
        daily_metrics.avg_vol_90d,
        -- ATR-14 SSOT (daily_metrics) — normalizes the stage slope diagnostic using the
        -- pandas prototype and the flip-flop KPI read.
        daily_metrics.atr_14,

        -- Lagged prices for performance calculations
        lagInFrame(`close`, 5) OVER (PARTITION BY ticker ORDER BY date) AS price_5d_ago,
        lagInFrame(`close`, 10) OVER (PARTITION BY ticker ORDER BY date) AS price_10d_ago,
        lagInFrame(`close`, 21) OVER (PARTITION BY ticker ORDER BY date) AS price_21d_ago,
        lagInFrame(`close`, 63) OVER (PARTITION BY ticker ORDER BY date) AS price_63d_ago,
        lagInFrame(`close`, 126) OVER (PARTITION BY ticker ORDER BY date) AS price_126d_ago,
        lagInFrame(`close`, 189) OVER (PARTITION BY ticker ORDER BY date) AS price_189d_ago,
        lagInFrame(`close`, 252) OVER (PARTITION BY ticker ORDER BY date) AS price_252d_ago,
        lagInFrame(closeadj, 5) OVER (PARTITION BY ticker ORDER BY date) AS total_return_5d_ago,
        lagInFrame(closeadj, 10) OVER (PARTITION BY ticker ORDER BY date) AS total_return_10d_ago,
        lagInFrame(closeadj, 21) OVER (PARTITION BY ticker ORDER BY date) AS total_return_21d_ago,
        lagInFrame(closeadj, 63) OVER (PARTITION BY ticker ORDER BY date) AS total_return_63d_ago,
        lagInFrame(closeadj, 126) OVER (PARTITION BY ticker ORDER BY date) AS total_return_126d_ago,
        lagInFrame(closeadj, 189) OVER (PARTITION BY ticker ORDER BY date) AS total_return_189d_ago,
        lagInFrame(closeadj, 252) OVER (PARTITION BY ticker ORDER BY date) AS total_return_252d_ago,

        -- Lagged SMAs for slope calculations
        lagInFrame(sma200d, 1) OVER (PARTITION BY ticker ORDER BY date) AS sma200_lag_1d,
        lagInFrame(sma50d, 20) OVER (PARTITION BY ticker ORDER BY date) AS sma50_lag_20d,
        lagInFrame(sma200d, 20) OVER (PARTITION BY ticker ORDER BY date) AS sma200_lag_20d,
        lagInFrame(sma200d, 30) OVER (PARTITION BY ticker ORDER BY date) AS sma200_lag_30d,
        lagInFrame(sma200d, 150) OVER (PARTITION BY ticker ORDER BY date) AS sma200_lag_150d,
        lagInFrame(sma20d, 1) OVER (PARTITION BY ticker ORDER BY date) AS sma20_lag_1d,
        -- 30-session lag of the 150-day moving average for the stage slope diagnostic
        lagInFrame(sma150d, 30) OVER (PARTITION BY ticker ORDER BY date) AS sma150_lag_30d,

        -- Previous close for True Range calculation
        lagInFrame(`close`, 1) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
    FROM daily_metrics FINAL
    -- NEW: Only process tickers that need updating
    INNER JOIN tickers_needing_update tnu ON daily_metrics.ticker = tnu.ticker
    -- LOOKBACK CONTRACT: lagInFrame(close, 252) needs 252 *trading* rows of lead-in —
    -- ~365 calendar days — or perf_1y writes NULL for the first ~12 sessions of every
    -- chunk. 400 days of pad keeps the full 1y leg inside the read window.
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 400 DAY AND {chunk_end_date:String}
      AND tnu.needs_update = 1
),
base_data_with_true_range AS (
    SELECT
        ticker,
        date,
        `close`,
        closeadj,
        high,
        low,
        volume,
        sma10d,
        sma20d,
        sma50d,
        sma150d,
        sma200d,
        high_5d,
        low_5d,
        high_30d,
        low_30d,
        high_90d,
        low_90d,
        high_52w,
        low_52w,
        avg_vol_5d,
        avg_vol_20d,
        avg_vol_50d,
        avg_vol_60d,
        avg_vol_90d,
        price_5d_ago,
        price_10d_ago,
        price_21d_ago,
        price_63d_ago,
        price_126d_ago,
        price_189d_ago,
        price_252d_ago,
        total_return_5d_ago,
        total_return_10d_ago,
        total_return_21d_ago,
        total_return_63d_ago,
        total_return_126d_ago,
        total_return_189d_ago,
        total_return_252d_ago,
        sma200_lag_1d,
        sma50_lag_20d,
        sma200_lag_20d,
        sma200_lag_30d,
        sma200_lag_150d,
        sma20_lag_1d,
        sma150_lag_30d,
        atr_14,
        prev_close,
        -- True Range calculation: MAX(high-low, |high-prev_close|, |low-prev_close|)
        greatest(
            base_data.high - base_data.low,
            abs(base_data.high - base_data.prev_close),
            abs(base_data.low - base_data.prev_close)
        ) AS true_range
    FROM base_data base_data
),
calculated_metrics AS (
    SELECT
        ticker,
        date,
        `close`,
        closeadj,
        high,
        low,
        volume,
        sma10d,
        sma20d,
        sma50d,
        sma150d,
        sma200d,
        high_5d,
        low_5d,
        high_30d,
        low_30d,
        high_90d,
        low_90d,
        high_52w,
        low_52w,
        avg_vol_5d,
        avg_vol_20d,
        avg_vol_50d,
        avg_vol_60d,
        avg_vol_90d,
        price_5d_ago,
        price_10d_ago,
        price_21d_ago,
        price_63d_ago,
        price_126d_ago,
        price_189d_ago,
        price_252d_ago,
        total_return_5d_ago,
        total_return_10d_ago,
        total_return_21d_ago,
        total_return_63d_ago,
        total_return_126d_ago,
        total_return_189d_ago,
        total_return_252d_ago,
        sma200_lag_1d,
        sma50_lag_20d,
        sma200_lag_20d,
        sma200_lag_30d,
        sma200_lag_150d,
        sma20_lag_1d,
        prev_close,
        true_range,
        -- VCP: Count of days with small range
        countIf((high - low) < (high_30d * 0.05)) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as vcp_consolidation_days_5pct_30d,
        -- Weinstein Stage (daily version)
        -- Normalized 30-session change in the 150-day moving average, retained as a
        -- diagnostic only; it does not participate in stage classification.
        (sma150d - sma150_lag_30d) / nullIf(atr_14 * sqrt(30), 0) AS stage_slope30_atr
    FROM base_data_with_true_range
),

stage_positions AS (
    SELECT * FROM calculated_metrics
),
final_metrics AS (
SELECT
    stage_positions.ticker AS ticker,                                                        -- Ticker symbol
    stage_positions.date AS date,                                                           -- Date of the metric
    now() as lastupdated,                                                              -- Timestamp of the update

    -- Trend Indicators: Price distance from various SMAs. Positive means price is above SMA.
    (`close` - sma10d) / nullIf(sma10d, 0) AS sma10d_trend,                            -- Formula: (close - sma10d) / sma10d. Normalized distance from price to the 10-day SMA. Positive means price is above SMA.
    (`close` - sma20d) / nullIf(sma20d, 0) AS sma20d_trend,                            -- Formula: (close - sma20d) / sma20d. Normalized distance from price to the 20-day SMA.
    (`close` - sma50d) / nullIf(sma50d, 0) AS sma50d_trend,                            -- Formula: (close - sma50d) / sma50d. Normalized distance from price to the 50-day SMA.
    (`close` - sma150d) / nullIf(sma150d, 0) AS sma150d_trend,                         -- Formula: (close - sma150d) / sma150d. Normalized distance from price to the 150-day SMA.
    (`close` - sma200d) / nullIf(sma200d, 0) AS sma200d_trend,                         -- Formula: (close - sma200d) / sma200d. Normalized distance from price to the 200-day SMA.

    -- Slope Indicators: Rate of change of key SMAs.
    (sma50d / sma50_lag_20d) - 1 AS sma50d_slope_20d,                                   -- Formula: (sma50d / sma50d_lag_20d) - 1. The 20-day slope of the 50-day SMA.
    (sma200d / sma200_lag_20d) - 1 AS sma200d_slope_20d,                                -- Formula: (sma200d / sma200d_lag_20d) - 1. The 20-day slope of the 200-day SMA.

    -- Price performance uses split-adjusted OHLC close; total return uses closeadj.
    (`close` / price_5d_ago) - 1 AS perf_5d,                                           -- 5-session split-adjusted price return.
    (`close` / price_10d_ago) - 1 AS perf_10d,                                         -- 10-session split-adjusted price return.
    (`close` / price_21d_ago) - 1 AS perf_1m,                                          -- 21-session split-adjusted price return.
    (`close` / price_63d_ago) - 1 AS perf_3m,                                          -- 63-session split-adjusted price return.
    (`close` / price_126d_ago) - 1 AS perf_6m,                                         -- 126-session split-adjusted price return.
    (`close` / price_252d_ago) - 1 AS perf_1y,                                         -- 252-session split-adjusted price return.
    (`close` / price_189d_ago) - 1 AS perf_9m,                                         -- 189-session split-adjusted price return.
    -- Quarterly sub-period decomposition of perf_1y (SigmaRail derived returns): q1 is the
    -- oldest quarter, q4 the most recent. (1+perf_q1)...(1+perf_q4) = 1+perf_1y.
    (price_189d_ago / price_252d_ago) - 1 AS perf_q1,                                  -- Formula: (close_lag_189d / close_lag_252d) - 1. Oldest quarter of the trailing year (days 190-252 back).
    (price_126d_ago / price_189d_ago) - 1 AS perf_q2,                                  -- Formula: (close_lag_126d / close_lag_189d) - 1. Second quarter back (days 127-189).
    (price_63d_ago / price_126d_ago) - 1 AS perf_q3,                                   -- Formula: (close_lag_63d / close_lag_126d) - 1. Third quarter back (days 64-126).
    (`close` / price_63d_ago) - 1 AS perf_q4,                                          -- Formula: (close / close_lag_63d) - 1. Most recent quarter (days 1-63); equals perf_3m.
    (closeadj / nullIf(total_return_5d_ago, 0)) - 1 AS total_return_5d,
    (closeadj / nullIf(total_return_10d_ago, 0)) - 1 AS total_return_10d,
    (closeadj / nullIf(total_return_21d_ago, 0)) - 1 AS total_return_1m,
    (closeadj / nullIf(total_return_63d_ago, 0)) - 1 AS total_return_3m,
    (closeadj / nullIf(total_return_126d_ago, 0)) - 1 AS total_return_6m,
    (closeadj / nullIf(total_return_189d_ago, 0)) - 1 AS total_return_9m,
    (closeadj / nullIf(total_return_252d_ago, 0)) - 1 AS total_return_1y,
    (total_return_189d_ago / nullIf(total_return_252d_ago, 0)) - 1 AS total_return_q1,
    (total_return_126d_ago / nullIf(total_return_189d_ago, 0)) - 1 AS total_return_q2,
    (total_return_63d_ago / nullIf(total_return_126d_ago, 0)) - 1 AS total_return_q3,
    (closeadj / nullIf(total_return_63d_ago, 0)) - 1 AS total_return_q4,

    -- Technical Ratios (Price vs Moving Averages): Key ratios for trend analysis
    -- ATR percent SSOT is daily_metrics.atr_14_pct; atr_to_sma50 keeps an inline ATR/sma50 ratio only.
    (`close` / nullIf(sma50d, 0)) * 100 AS price_vs_sma50,                              -- Formula: (close / sma50d) * 100. Price as percentage of 50-day SMA.
    (`close` / nullIf(sma150d, 0)) * 100 AS price_vs_sma150,                            -- Formula: (close / sma150d) * 100. Price as percentage of 150-day SMA.
    (`close` / nullIf(sma200d, 0)) * 100 AS price_vs_sma200,                            -- Formula: (close / sma200d) * 100. Price as percentage of 200-day SMA.
    (sma50d / nullIf(sma150d, 0)) * 100 AS sma50_vs_sma150,                              -- Formula: (sma50d / sma150d) * 100. 50-day SMA as percentage of 150-day SMA.
    (sma150d / nullIf(sma200d, 0)) * 100 AS sma150_vs_sma200,                            -- Formula: (sma150d / sma200d) * 100. 150-day SMA as percentage of 200-day SMA.
    (`close` / nullIf(high_52w, 0)) * 100 AS price_vs_52w_high,                         -- Formula: (close / high_52w) * 100. Price as percentage of 52-week high.
    (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(sma50d, 0) * 100 AS atr_to_sma50,  -- Formula: (atr_14 / sma50d) * 100. ATR as percentage of 50-day SMA.

    -- Additional Technical Ratios for Enhanced Analysis
    (`close` / nullIf(sma20d, 0)) * 100 AS price_vs_sma20,                              -- Formula: (close / sma20d) * 100. Price as percentage of 20-day SMA.
    (`close` / nullIf(low_52w, 0)) * 100 AS price_vs_52w_low,                           -- Formula: (close / low_52w) * 100. Price as percentage of 52-week low.
            (avg_vol_20d / nullIf(avg_vol_50d, 0)) * 100 AS volume_sma20_vs_sma50,           -- Formula: (avg_vol_20d / avg_vol_50d) * 100. 20-day volume SMA as percentage of 50-day volume SMA.
        (avg_vol_20d / nullIf(avg_vol_50d, 0) - 1) * 100 AS volume_trend_pct,            -- Formula: ((avg_vol_20d / avg_vol_50d) - 1) * 100. Volume trend percentage change.
    ((high_52w - low_52w) / nullIf(`close`, 0)) * 100 AS price_range_52w_pct,           -- Formula: ((high_52w - low_52w) / close) * 100. 52-week range as percentage of current price.

    -- Volatility & Price Action Indicators
    (`close` / nullIf(low_52w, 0)) - 1 AS price_to_52w_low_pct,                        -- Formula: (close / low_52w) - 1. Percentage distance of current price from its 52-week low.
    (`close` / nullIf(high_52w, 0)) - 1 AS price_to_52w_high_pct,                      -- Formula: (close / high_52w) - 1. Percentage distance of current price from its 52-week high.
    (high_5d - low_5d) / nullIf(high_90d, 0) AS vcp_tightness_5d_90d,                   -- Formula: (high_5d - low_5d) / high_90d. VCP: Volatility Contraction Pattern, measures 5-day range vs 90-day high.
    avg_vol_5d / nullIf(avg_vol_90d, 0) AS vcp_volume_dryup_5d_90d,                     -- Formula: avg_vol_5d / avg_vol_90d. VCP: Compares recent volume to longer-term average volume.
    `close` / nullIf(high_90d, 0) AS vcp_proximity_90d,                                -- Formula: close / high_90d. VCP: Proximity of current price to the 90-day high.
    (high_5d - low_5d) / nullIf(high_90d - low_90d, 0) AS vcp_atr_compression_5d_90d,   -- Formula: (high_5d - low_5d) / (high_90d - low_90d). VCP: Compares 5-day vs 90-day Average True Range.
    (high_90d - low_90d) / nullIf(high_90d, 0) AS vcp_max_drawdown_90d,                 -- Formula: (high_90d - low_90d) / high_90d. VCP: Max drawdown over the last 90 days.
    vcp_consolidation_days_5pct_30d,                                                    -- VCP: Number of days in the last 30 where the daily range was less than 5% of the 30-day high.
    (high = high_90d) AS breakout_signal,                                               -- Signal (1/0) indicating if the current day high is a new 90-day high.

    -- Minervini Helper Flags (stored as UInt8 0/1 values)
    sma200_lag_30d AS sma200_lag_30d,
    CAST((sma200d IS NOT NULL AND sma200_lag_30d IS NOT NULL AND sma200_lag_30d > 0 AND sma200d > sma200_lag_30d) AS UInt8) AS sma200d_rising_30d,
    CAST((sma200d IS NOT NULL AND sma200_lag_150d IS NOT NULL AND sma200_lag_150d > 0 AND sma200d > sma200_lag_150d) AS UInt8) AS sma200d_rising_150d,
    CAST((`close` > sma20d AND prev_close IS NOT NULL AND sma20_lag_1d IS NOT NULL AND prev_close <= sma20_lag_1d) AS UInt8) AS sma20d_crossover_up,
    CAST((`close` > sma20d) AS UInt8) AS price_above_sma20d,
    CAST((`close` > sma50d) AS UInt8) AS price_above_sma50d,
    CAST((`close` > sma150d) AS UInt8) AS price_above_sma150d,
    CAST((`close` > sma200d) AS UInt8) AS price_above_sma200d,
    CAST((sma50d > sma150d) AS UInt8) AS sma50d_above_sma150d,
    CAST((sma50d > sma200d) AS UInt8) AS sma50d_above_sma200d,
    CAST((sma150d > sma200d) AS UInt8) AS sma150d_above_sma200d,
    CAST((low_52w IS NOT NULL AND `close` >= low_52w * 1.30) AS UInt8) AS price_30pct_above_52w_low,
    CAST((low_52w IS NOT NULL AND `close` >= low_52w * 1.70) AS UInt8) AS price_70pct_above_52w_low,
    CAST((high_52w IS NOT NULL AND `close` >= high_52w * 0.75) AS UInt8) AS price_within_25pct_52w_high,

    -- Canonical detailed stage series (daily grain). Broad stage is derived by
    -- consumers from the leading character of stage_code.
    tupleElement(arrayFirst(row -> row.1 = stage_positions.date, detail.stage_rows), 2) AS stage_code,
    tupleElement(arrayFirst(row -> row.1 = stage_positions.date, detail.stage_rows), 3) AS stage_duration,
    tupleElement(arrayFirst(row -> row.1 = stage_positions.date, detail.stage_rows), 4) AS stage_transition_state,
    stage_slope30_atr,

    -- Independent Risk Factors (for strategy risk analysis)
    -- 1. VOLATILITY RISK: ATR14 as percent of close (same unit as daily_metrics.atr_14_pct)
    CASE
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 5 THEN 0.9
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 3 THEN 0.7
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 2 THEN 0.5
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 1 THEN 0.3
        ELSE 0.1
    END AS volatility_risk_pct,

    -- 2. LIQUIDITY RISK: Based on volume patterns and average volume
    CASE
        WHEN volume < avg_vol_20d * 0.5 THEN 0.9  -- High liquidity risk (very low volume)
        WHEN volume < avg_vol_20d * 0.7 THEN 0.7  -- Medium-high liquidity risk
        WHEN volume < avg_vol_20d * 0.9 THEN 0.5  -- Medium liquidity risk
        WHEN volume < avg_vol_20d * 1.1 THEN 0.3  -- Low liquidity risk
        ELSE 0.1  -- Very low liquidity risk (good volume)
    END AS liquidity_risk_pct,

    -- 3. SECTOR RISK: Based on sector volatility (placeholder - would need sector data)
    CASE
        WHEN ticker LIKE '^%' THEN 0.1  -- Index/ETF - low sector risk
        WHEN ticker IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA') THEN 0.2  -- Large cap tech - low sector risk
        ELSE 0.4  -- Default sector risk (would be calculated from sector volatility)
    END AS sector_risk_pct,

    -- 4. TECHNICAL RISK: Based on chart patterns and technical levels
    CASE
        WHEN `close` < sma200d THEN 0.8  -- High technical risk (below 200-day MA)
        WHEN `close` < sma150d THEN 0.6  -- Medium-high technical risk (below 150-day MA)
        WHEN `close` < sma50d THEN 0.4   -- Medium technical risk (below 50-day MA)
        WHEN `close` < sma20d THEN 0.2   -- Low technical risk (below 20-day MA)
        ELSE 0.1  -- Very low technical risk (above all MAs)
    END AS technical_risk_pct,

    -- 5. FUNDAMENTAL RISK: Based on fundamental metrics (placeholder - would need fundamental data)
    CASE
        WHEN ticker LIKE '^%' THEN 0.1  -- Index/ETF - low fundamental risk
        WHEN ticker IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA') THEN 0.2  -- Large cap - low fundamental risk
        ELSE 0.4  -- Default fundamental risk (would be calculated from P/E, debt, etc.)
    END AS fundamental_risk_pct,

    -- Overall independent risk score (average of all risk factors)
    (CASE
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 5 THEN 0.9
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 3 THEN 0.7
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 2 THEN 0.5
        WHEN (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 > 1 THEN 0.3
        ELSE 0.1
    END +
    CASE
        WHEN volume < avg_vol_20d * 0.5 THEN 0.9
        WHEN volume < avg_vol_20d * 0.7 THEN 0.7
        WHEN volume < avg_vol_20d * 0.9 THEN 0.5
        WHEN volume < avg_vol_20d * 1.1 THEN 0.3
        ELSE 0.1
    END +
    CASE
        WHEN ticker LIKE '^%' THEN 0.1
        WHEN ticker IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA') THEN 0.2
        ELSE 0.4
    END +
    CASE
        WHEN `close` < sma200d THEN 0.8
        WHEN `close` < sma150d THEN 0.6
        WHEN `close` < sma50d THEN 0.4
        WHEN `close` < sma20d THEN 0.2
        ELSE 0.1
    END +
    CASE
        WHEN ticker LIKE '^%' THEN 0.1
        WHEN ticker IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA') THEN 0.2
        ELSE 0.4
    END) / 5.0 AS independent_risk_score

FROM stage_positions
LEFT JOIN stage_history AS detail ON stage_positions.ticker = detail.ticker
)
SELECT
    *
FROM final_metrics
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
