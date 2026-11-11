-- Weekly Metrics Derived Table
-- This table stores weekly lagged metrics, Weinstein stages, and other derived indicators
-- that require access to previously calculated weekly values. It includes weekly-based
-- Weinstein stage detection and other weekly momentum indicators.
-- Data is populated by the weekly metrics derived transform scripts.

CREATE TABLE IF NOT EXISTS weekly_metrics_derived
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Start of the week (Monday)',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record',
    `sma20w_slope` Nullable(Float64) COMMENT '1-week slope of 20-week SMA',
    `sma30w_slope` Nullable(Float64) COMMENT '1-week slope of 30-week SMA',
    `sma50w_slope` Nullable(Float64) COMMENT '1-week slope of 50-week SMA',
    `sma20w_slope_4w` Nullable(Float64) COMMENT '4-week slope of 20-week SMA',
    `sma50w_slope_4w` Nullable(Float64) COMMENT '4-week slope of 50-week SMA',
    `trend_strength_10w_20w` Nullable(Float64) COMMENT 'Trend strength between 10w and 20w SMAs (ADX-like)',
    `trend_strength_20w_50w` Nullable(Float64) COMMENT 'Trend strength between 20w and 50w SMAs',
    `momentum_4w` Nullable(Float64) COMMENT '4-week momentum: (current_week_close / 4_weeks_ago_close) - 1',
    `momentum_8w` Nullable(Float64) COMMENT '8-week momentum: (current_week_close / 8_weeks_ago_close) - 1',
    `momentum_12w` Nullable(Float64) COMMENT '12-week momentum: (current_week_close / 12_weeks_ago_close) - 1',
    `momentum_26w` Nullable(Float64) COMMENT '26-week momentum: (current_week_close / 26_weeks_ago_close) - 1',
    `momentum_acceleration_4w` Nullable(Float64) COMMENT 'Acceleration of 4-week momentum: current - previous',
    `momentum_acceleration_8w` Nullable(Float64) COMMENT 'Acceleration of 8-week momentum: current - previous',
    `momentum_acceleration_12w` Nullable(Float64) COMMENT 'Acceleration of 12-week momentum: current - previous',
    `macd_line` Nullable(Float64) COMMENT 'MACD Line: EMA(12) - EMA(26) using weekly data',
    `macd_signal` Nullable(Float64) COMMENT 'MACD Signal Line: EMA(9) of MACD Line using weekly data',
    `macd_histogram` Nullable(Float64) COMMENT 'MACD Histogram: MACD Line - Signal Line using weekly data',
    `rsi14w` Nullable(Float64) COMMENT 'Weekly RSI (14-period) calculated from weekly data',
    `stoch_k_14w` Nullable(Float64) COMMENT 'Weekly Stochastic Oscillator %K (14-period)',
    `stoch_d_14w` Nullable(Float64) COMMENT 'Weekly Stochastic Oscillator %D (3-period SMA of %K)',
    `williams_r_14w` Nullable(Float64) COMMENT 'Weekly Williams %R (14-period)',
    `bb20w_middle` Nullable(Float64) COMMENT '20-week Bollinger Band middle line (SMA)',
    `bb20w_upper` Nullable(Float64) COMMENT '20-week Bollinger Band upper line (+2 std dev)',
    `bb20w_lower` Nullable(Float64) COMMENT '20-week Bollinger Band lower line (-2 std dev)',
    `bb20w_width` Nullable(Float64) COMMENT 'Bollinger Band width: (upper - lower) / middle',
    `bb20w_position` Nullable(Float64) COMMENT 'Price position within BB: (close - lower) / (upper - lower)',
    `wcr_pct` Nullable(Float64) COMMENT 'Weekly Closing Range as a percentage. (close-low)/(high-low). 100% is a close at the high.',
    `atr_10w_pct` Nullable(Float64) COMMENT '10-week Average True Range as a percentage of the weekly closing price.',
    `perf_1w` Nullable(Float64) COMMENT '1-week split-adjusted price return ((close / lag(close, 1)) - 1)',
    `perf_4w` Nullable(Float64) COMMENT '4-week split-adjusted price return ((close / lag(close, 4)) - 1)',
    `perf_8w` Nullable(Float64) COMMENT '8-week price performance: (current_week_close / 8_weeks_ago_close - 1)',
    `perf_12w` Nullable(Float64) COMMENT '12-week price performance: (current_week_close / 12_weeks_ago_close - 1)',
    `perf_26w` Nullable(Float64) COMMENT '26-week price performance: (current_week_close / 26_weeks_ago_close - 1)',
    `total_return_1w` Nullable(Float64) COMMENT 'Dividend-adjusted 1-week total return from closeadj.',
    `total_return_4w` Nullable(Float64) COMMENT 'Dividend-adjusted 4-week total return from closeadj.',
    `total_return_8w` Nullable(Float64) COMMENT 'Dividend-adjusted 8-week total return from closeadj.',
    `total_return_12w` Nullable(Float64) COMMENT 'Dividend-adjusted 12-week total return from closeadj.',
    `total_return_26w` Nullable(Float64) COMMENT 'Dividend-adjusted 26-week total return from closeadj.',
    `perf_1w_acceleration` Nullable(Float64) COMMENT 'Acceleration of 1-week performance',
    `perf_4w_acceleration` Nullable(Float64) COMMENT 'Acceleration of 4-week performance',
    `perf_8w_acceleration` Nullable(Float64) COMMENT 'Acceleration of 8-week performance',
    `perf_12w_acceleration` Nullable(Float64) COMMENT 'Acceleration of 12-week performance',
    `stage_code` Nullable(String) COMMENT 'Completed-week stage token, including substage when available',
    `stage_duration` Nullable(UInt16) COMMENT 'Consecutive completed weekly observations in the current stage token',
    `stage_transition_state` Tuple(
        UInt8,
        Array(UInt32),
        Float64,
        UInt32,
        UInt8) DEFAULT tuple(toUInt8(0), arrayWithConstant(8, toUInt32(0)), toFloat64(1000000000.), toUInt32(0), toUInt8(0)) COMMENT 'Internal completed-week transition checkpoint: stage id, eight transition counters, stage-4A low watermark, current-stage duration, and initialized marker.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Derived Weekly Metrics Transform
-- Populates weekly_metrics_derived with derived indicators calculated from the base weekly_metrics table.
-- This includes EMAs, MACD, Bollinger Bands, momentum, performance, volatility, and oscillator metrics.
-- Expects SQL variables: chunk_start_date, chunk_end_date, force_refresh
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of weekly derived metrics for tickers that haven't changed
--
DROP VIEW IF EXISTS xform_weekly_metrics_derived;

CREATE VIEW IF NOT EXISTS xform_weekly_metrics_derived (
    ticker,
    date,
    lastupdated,
    sma20w_slope,
    sma30w_slope,
    sma50w_slope,
    sma20w_slope_4w,
    sma50w_slope_4w,
    trend_strength_10w_20w,
    trend_strength_20w_50w,
    momentum_4w,
    momentum_8w,
    momentum_12w,
    momentum_26w,
    momentum_acceleration_4w,
    momentum_acceleration_8w,
    momentum_acceleration_12w,
    perf_1w,
    perf_4w,
    perf_8w,
    perf_12w,
    perf_26w,
    total_return_1w,
    total_return_4w,
    total_return_8w,
    total_return_12w,
    total_return_26w,
    perf_1w_acceleration,
    perf_4w_acceleration,
    perf_8w_acceleration,
    perf_12w_acceleration,
    macd_line,
    macd_signal,
    macd_histogram,
    rsi14w,
    stoch_k_14w,
    stoch_d_14w,
    williams_r_14w,
    bb20w_middle,
    bb20w_upper,
    bb20w_lower,
    bb20w_width,
    bb20w_position,
    wcr_pct,
    atr_10w_pct,
    stage_code,
    stage_duration,
    stage_transition_state
)
COMMENT '{"order":4,"target":"weekly_metrics_derived","sources":["weekly_metrics"],"chunk_size":"6m"}'
AS
WITH
-- Fold the recovered eight-state weekly calculation in its original ordered
-- checks. Each weekly bar runs transitions 1 through 8, then appends its output
-- at step 9. State is checkpointed on the target row so later view chunks only
-- fold their own weekly bars.
    (counts, target, resets) -> arrayMap(
        (value, index) -> toUInt32(if(index = target, value + toUInt32(1), if(has(resets, index), toUInt32(0), value))),
        counts,
        arrayEnumerate(counts)
    ) AS stage_set_counts,
    (acc, step, bar) -> multiIf(
        step = 1,
            if(
                (tupleElement(acc, 1) IN (0, 1, 7, 8))
                    AND tupleElement(bar, 2) > tupleElement(bar, 4)
                    AND tupleElement(bar, 2) > tupleElement(bar, 5)
                    AND tupleElement(bar, 2) < tupleElement(bar, 6),
                (toUInt8(1), stage_set_counts(tupleElement(acc, 2), 1, [2, 3, 4, 5, 6, 7, 8]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 2,
            if(
                (tupleElement(acc, 1) IN (0, 2, 1)) AND tupleElement(acc, 2)[1] >= 10,
                (toUInt8(2), stage_set_counts(tupleElement(acc, 2), 2, [1, 3, 4, 5, 6, 7, 8]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 3,
            if(
                (tupleElement(acc, 1) IN (0, 3, 1, 2, 5, 6, 7, 8))
                    AND tupleElement(bar, 2) > tupleElement(bar, 4)
                    AND tupleElement(bar, 2) > tupleElement(bar, 5)
                    AND tupleElement(bar, 2) > tupleElement(bar, 6),
                (toUInt8(3), stage_set_counts(tupleElement(acc, 2), 3, [1, 2, 4, 5, 6, 7, 8]), toFloat64(1e9), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 4,
            if(
                (tupleElement(acc, 1) IN (0, 4, 3)) AND tupleElement(acc, 2)[3] >= 10,
                (toUInt8(4), stage_set_counts(tupleElement(acc, 2), 4, [1, 2, 3, 5, 6, 7, 8]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 5,
            if(
                (tupleElement(acc, 1) IN (0, 5, 3, 4))
                    AND tupleElement(bar, 2) < tupleElement(bar, 4)
                    AND tupleElement(bar, 2) > tupleElement(bar, 5)
                    AND tupleElement(bar, 2) > tupleElement(bar, 6),
                (toUInt8(5), stage_set_counts(tupleElement(acc, 2), 5, [1, 2, 3, 4, 6, 7, 8]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 6,
            if(
                (tupleElement(acc, 1) IN (0, 6, 5))
                    AND tupleElement(bar, 2) < tupleElement(bar, 4)
                    AND tupleElement(bar, 2) < tupleElement(bar, 5)
                    AND tupleElement(bar, 2) > tupleElement(bar, 6),
                (toUInt8(6), stage_set_counts(tupleElement(acc, 2), 6, [1, 2, 3, 4, 5, 7, 8]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 7,
            if(
                tupleElement(bar, 2) < tupleElement(bar, 4)
                    AND tupleElement(bar, 2) < tupleElement(bar, 5)
                    AND tupleElement(bar, 2) < tupleElement(bar, 6)
                    AND tupleElement(bar, 2) <= tupleElement(acc, 3),
                (toUInt8(7), stage_set_counts(tupleElement(acc, 2), 7, [1, 2, 3, 4, 5, 6, 8]), least(tupleElement(acc, 3), tupleElement(bar, 3)), tupleElement(acc, 4), tupleElement(acc, 5)),
                if(
                    tupleElement(acc, 1) = 7,
                    (tupleElement(acc, 1), tupleElement(acc, 2), least(tupleElement(acc, 3), tupleElement(bar, 3)), tupleElement(acc, 4), tupleElement(acc, 5)),
                    acc
                )
            ),
        step = 8,
            if(
                tupleElement(acc, 1) = 7
                    AND tupleElement(bar, 2) > tupleElement(bar, 4)
                    AND tupleElement(bar, 2) < tupleElement(bar, 5)
                    AND tupleElement(bar, 2) < tupleElement(bar, 6),
                (toUInt8(8), stage_set_counts(tupleElement(acc, 2), 8, [1, 2, 3, 4, 5, 6, 7]), tupleElement(acc, 3), tupleElement(acc, 4), tupleElement(acc, 5)),
                acc
            ),
        step = 9,
            (
                tupleElement(acc, 1),
                tupleElement(acc, 2),
                tupleElement(acc, 3),
                arrayPushBack(
                    tupleElement(acc, 4),
                    tuple(
                        tupleElement(bar, 1),
                        tupleElement(acc, 1),
                        if(
                            tupleElement(acc, 1) = 0,
                            toUInt32(0),
                            if(
                                tupleElement(tupleElement(acc, 5), 1) = tupleElement(acc, 1),
                                toUInt32(tupleElement(tupleElement(acc, 5), 2) + toUInt32(1)),
                                toUInt32(1)
                            )
                        ),
                        tupleElement(acc, 2),
                        tupleElement(acc, 3)
                    )
                ),
                tuple(
                    tupleElement(acc, 1),
                    if(
                        tupleElement(acc, 1) = 0,
                        toUInt32(0),
                        if(
                            tupleElement(tupleElement(acc, 5), 1) = tupleElement(acc, 1),
                            toUInt32(tupleElement(tupleElement(acc, 5), 2) + toUInt32(1)),
                            toUInt32(1)
                        )
                    )
                )
            ),
        acc
    ) AS stage_fold_step,
-- Check freshness per ticker - only process tickers where source data is newer
ticker_freshness_check AS (
    SELECT
        wmd.ticker,
        count() as target_row_count,
        max(wmd.lastupdated) as target_last_updated
    FROM weekly_metrics_derived wmd FINAL
    WHERE wmd.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    GROUP BY wmd.ticker
),
-- Get source freshness per ticker
source_freshness_check AS (
    SELECT
        wm.ticker,
        count() as source_row_count,
        max(wm.lastupdated) as source_last_updated
    FROM weekly_metrics wm FINAL
    WHERE wm.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    GROUP BY wm.ticker
),
-- Determine which tickers need updating
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1  -- New ticker
            WHEN {force_refresh:UInt8} = 1 THEN 1  -- Force historical backfill after schema or calculation changes
            WHEN s.source_row_count > t.target_row_count THEN 1  -- Missing rows in target for this chunk
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
),
-- Step 1: Get base weekly data and add lagged values needed for subsequent calculations.
base_data AS (
    SELECT
        *,
        lagInFrame(close, 1) OVER (PARTITION BY ticker ORDER BY date) AS close_lag1,
        lagInFrame(closeadj, 1) OVER (PARTITION BY ticker ORDER BY date) AS closeadj_lag1,
        lagInFrame(closeadj, 4) OVER (PARTITION BY ticker ORDER BY date) AS closeadj_lag4,
        lagInFrame(closeadj, 8) OVER (PARTITION BY ticker ORDER BY date) AS closeadj_lag8,
        lagInFrame(closeadj, 12) OVER (PARTITION BY ticker ORDER BY date) AS closeadj_lag12,
        lagInFrame(closeadj, 26) OVER (PARTITION BY ticker ORDER BY date) AS closeadj_lag26,
        lagInFrame(sma20w, 1) OVER (PARTITION BY ticker ORDER BY date) AS sma20w_lag1,
        lagInFrame(sma30w, 1) OVER (PARTITION BY ticker ORDER BY date) AS sma30w_lag1,
        lagInFrame(sma50w, 1) OVER (PARTITION BY ticker ORDER BY date) AS sma50w_lag1,
        lagInFrame(sma20w, 4) OVER (PARTITION BY ticker ORDER BY date) AS sma20w_lag4,
        lagInFrame(sma50w, 4) OVER (PARTITION BY ticker ORDER BY date) AS sma50w_lag4,
        row_number() OVER (PARTITION BY ticker ORDER BY date) AS week_rn
    FROM weekly_metrics FINAL
    WHERE date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    AND ticker IN (
        SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
    )
),

-- Step 2: Calculate MACD line, ATR, and Bollinger Band standard deviation.
metrics_step2 AS (
    SELECT
        *,
        (ema12w - ema26w) AS macd_line,
        avg(weekly_tr) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS atr_10w,
        stddevSamp(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS bb_stddev
    FROM base_data
),

-- Step 3: Calculate MACD Signal line.
metrics_step3 AS (
    SELECT
        *,
        exponentialMovingAverage(2 / (9 + 1))(macd_line, week_rn) OVER (PARTITION BY ticker ORDER BY date) AS macd_signal
    FROM metrics_step2
),

-- Step 4: Calculate performance, momentum, and final MACD histogram.
metrics_step4 AS (
    SELECT
        *,
        (macd_line - macd_signal) AS macd_histogram,
        (close / nullIf(lagInFrame(close, 4) OVER (PARTITION BY ticker ORDER BY date), 0)) - 1 AS momentum_4w,
        (close / nullIf(lagInFrame(close, 8) OVER (PARTITION BY ticker ORDER BY date), 0)) - 1 AS momentum_8w,
        (close / nullIf(lagInFrame(close, 12) OVER (PARTITION BY ticker ORDER BY date), 0)) - 1 AS momentum_12w,
        (close / nullIf(lagInFrame(close, 26) OVER (PARTITION BY ticker ORDER BY date), 0)) - 1 AS momentum_26w,
        (close / nullIf(close_lag1, 0)) - 1 AS perf_1w,
        (closeadj / nullIf(closeadj_lag1, 0)) - 1 AS total_return_1w,
        (closeadj / nullIf(closeadj_lag4, 0)) - 1 AS total_return_4w,
        (closeadj / nullIf(closeadj_lag8, 0)) - 1 AS total_return_8w,
        (closeadj / nullIf(closeadj_lag12, 0)) - 1 AS total_return_12w,
        (closeadj / nullIf(closeadj_lag26, 0)) - 1 AS total_return_26w
    FROM metrics_step3
),

-- Step 5: Calculate weekly RSI components (average gain and loss).
weekly_rsi_components AS (
    SELECT
        ticker,
        date,
        avg(greatest(close - close_lag1, 0)) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
        avg(greatest(close_lag1 - close, 0)) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
    FROM base_data
),

-- Step 6: Calculate final weekly RSI.
weekly_rsi AS (
    SELECT
        ticker,
        date,
        100 - (100 / (1 + (avg_gain / nullIf(avg_loss, 0)))) AS rsi14w
    FROM weekly_rsi_components
),

-- Step 7: Calculate weekly Stochastics and Williams %R components.
weekly_oscillators_base AS (
    SELECT
        ticker,
        date,
        close,
        100 * (close - min(low) OVER w14) / nullIf(max(high) OVER w14 - min(low) OVER w14, 0) AS stoch_k_14w,
        -100 * (max(high) OVER w14 - close) / nullIf(max(high) OVER w14 - min(low) OVER w14, 0) AS williams_r_14w
    FROM base_data
    WINDOW w14 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)
),

-- Step 8: Calculate final Stochastics %D.
weekly_oscillators AS (
    SELECT
        ticker,
        date,
        stoch_k_14w,
        avg(stoch_k_14w) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as stoch_d_14w,
        williams_r_14w
    FROM weekly_oscillators_base
),

-- Step 9: Join the bounded-window oscillator columns onto the metric chain.
stage_conditions AS (
    SELECT
        *
    FROM metrics_step4
    LEFT JOIN weekly_rsi USING (ticker, date)
    LEFT JOIN weekly_oscillators USING (ticker, date)
),

-- Seed from the latest initialized checkpoint before this chunk. Do not impose
-- a time cutoff: stage duration and transition state persist across any gap in
-- observations, matching the original full-history fold exactly.
stage_seed_state AS (
    SELECT
        wmd.ticker,
        -- ReplacingMergeTree(lastupdated) may hold several physical versions
        -- of a ticker/week while a refresh is in flight. Resolve the latest
        -- version in argMax instead of FINAL, which otherwise materializes the
        -- entire prior history for every chunk.
        argMax(wmd.stage_transition_state, (wmd.date, wmd.lastupdated)) AS state
    FROM weekly_metrics_derived AS wmd
    WHERE wmd.date < toMonday(CAST({chunk_start_date:String}, 'Date'))
      AND tupleElement(wmd.stage_transition_state, 5) = 1
      AND wmd.ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
    GROUP BY wmd.ticker
),
stage_tickers AS (
    SELECT DISTINCT sc.ticker
    FROM stage_conditions AS sc
    INNER JOIN tickers_needing_update AS tnu ON sc.ticker = tnu.ticker
    WHERE tnu.needs_update = 1
      AND sc.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date'))
                      AND toMonday(CAST({chunk_end_date:String}, 'Date'))
),
-- Stage transition inputs are only this chunk's completed weekly bars. The
-- Monday-normalized bounds match the output grain and prevent a Tuesday-Friday
-- start date from both seeding and recalculating the same Monday row.
stage_hist_base AS (
    SELECT
        ticker,
        date,
        close,
        low,
        sma10w,
        sma30w,
        sma40w
    FROM weekly_metrics FINAL
    WHERE date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date'))
                   AND toMonday(CAST({chunk_end_date:String}, 'Date'))
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
stage_bar_arrays AS (
    SELECT
        ticker,
        arraySort(x -> tupleElement(x, 1), groupArray(tuple(
            date,
            assumeNotNull(close),
            assumeNotNull(low),
            assumeNotNull(sma10w),
            assumeNotNull(sma30w),
            assumeNotNull(sma40w)
        ))) AS bars
    FROM stage_hist_base
    WHERE isNotNull(close)
      AND isNotNull(low)
      AND isNotNull(sma10w)
      AND isNotNull(sma30w)
      AND isNotNull(sma40w)
    GROUP BY ticker
),
stage_code_input AS (
    SELECT
        st.ticker AS ticker,
        if(
            ifNull(seed.ticker, '') = '',
            tuple(toUInt8(0), arrayWithConstant(8, toUInt32(0)), toFloat64(1e9), toUInt32(0), toUInt8(0)),
            seed.state
        ) AS checkpoint,
        ifNull(
            bars.bars,
            CAST([], 'Array(Tuple(Date, Float64, Float64, Float64, Float64, Float64))')
        ) AS bars
    FROM stage_tickers AS st
    LEFT JOIN stage_seed_state AS seed ON st.ticker = seed.ticker
    LEFT JOIN stage_bar_arrays AS bars ON st.ticker = bars.ticker
),
stage_code_folded AS (
    SELECT
        ticker,
        arrayFold(
            (acc, bar) -> arrayFold(
                (state, step) -> stage_fold_step(state, step, bar),
                range(1, 10),
                acc
            ),
            bars,
            (
                tupleElement(checkpoint, 1),
                tupleElement(checkpoint, 2),
                tupleElement(checkpoint, 3),
                CAST([], 'Array(Tuple(Date, UInt8, UInt32, Array(UInt32), Float64))'),
                tuple(tupleElement(checkpoint, 1), tupleElement(checkpoint, 4))
            )
        ) AS stage_state
    FROM stage_code_input
),
stage_code_rows AS (
    SELECT
        ticker,
        tupleElement(stage_result, 1) AS date,
        tupleElement(stage_result, 2) AS stage_id,
        tupleElement(stage_result, 3) AS stage_duration,
        tupleElement(stage_result, 4) AS stage_transition_counts,
        tupleElement(stage_result, 5) AS stage_4a_low_watermark
    FROM stage_code_folded
    ARRAY JOIN tupleElement(stage_state, 4) AS stage_result
),
stage_code_history AS (
    SELECT
        ticker, date,
        multiIf(
            stage_id = 1, '1A',
            stage_id = 2, '1B',
            stage_id = 3, '2A',
            stage_id = 4, '2B',
            stage_id = 5, '3A',
            stage_id = 6, '3B',
            stage_id = 7, '4A',
            stage_id = 8, '4B',
            NULL
        ) AS stage_code,
        if(stage_id = 0, NULL, stage_duration) AS stage_duration
    FROM stage_code_rows
),
stage_state_checkpoint AS (
    SELECT
        ticker,
        date,
        tuple(
            stage_id,
            stage_transition_counts,
            stage_4a_low_watermark,
            stage_duration,
            toUInt8(1)
        ) AS stage_transition_state
    FROM stage_code_rows
),

-- Step 10: Calculate final performance accelerations.
final_calcs AS (
    SELECT
        *,
        momentum_4w - lagInFrame(momentum_4w, 1) OVER (PARTITION BY ticker ORDER BY date) as momentum_acceleration_4w,
        momentum_8w - lagInFrame(momentum_8w, 1) OVER (PARTITION BY ticker ORDER BY date) as momentum_acceleration_8w,
        momentum_12w - lagInFrame(momentum_12w, 1) OVER (PARTITION BY ticker ORDER BY date) as momentum_acceleration_12w,
        perf_1w - lagInFrame(perf_1w, 1) OVER (PARTITION BY ticker ORDER BY date) as perf_1w_acceleration
    FROM stage_conditions
),

-- Step 11: Calculate final performance accelerations.
final_data AS (
    SELECT
        *,
        perf_1w_acceleration - lagInFrame(perf_1w_acceleration, 4) OVER (PARTITION BY ticker ORDER BY date) AS perf_4w_acceleration_final,
        perf_1w_acceleration - lagInFrame(perf_1w_acceleration, 8) OVER (PARTITION BY ticker ORDER BY date) AS perf_8w_acceleration_final,
        perf_1w_acceleration - lagInFrame(perf_1w_acceleration, 12) OVER (PARTITION BY ticker ORDER BY date) AS perf_12w_acceleration_final
    FROM final_calcs
)

-- Final SELECT to insert into the derived table.
SELECT
    final_data.ticker AS ticker,                                                                                -- Ticker symbol
    final_data.date AS date,                                                                                    -- The date of the Monday of the week for the metric
    now() as lastupdated,                                                                                       -- Timestamp of the update

    -- SMA Slope & Trend Strength
    (sma20w / nullIf(sma20w_lag1, 0)) - 1 AS sma20w_slope,                                                       -- 1-week slope of the 20-week SMA
    (sma30w / nullIf(sma30w_lag1, 0)) - 1 AS sma30w_slope,                                                       -- 1-week slope of the 30-week SMA
    (sma50w / nullIf(sma50w_lag1, 0)) - 1 AS sma50w_slope,                                                       -- 1-week slope of the 50-week SMA
    (sma20w / nullIf(sma20w_lag4, 0)) - 1 AS sma20w_slope_4w,                                                     -- 4-week slope of the 20-week SMA
    (sma50w / nullIf(sma50w_lag4, 0)) - 1 AS sma50w_slope_4w,                                                     -- 4-week slope of the 50-week SMA
    abs(sma10w - sma20w) / nullIf(((sma10w + sma20w) / 2), 0) * 100 AS trend_strength_10w_20w,                   -- Pct difference between 10w and 20w SMAs, indicates trend strength
    abs(sma20w - sma50w) / nullIf(((sma20w + sma50w) / 2), 0) * 100 AS trend_strength_20w_50w,                   -- Pct difference between 20w and 50w SMAs, indicates trend strength

    -- Momentum and perf_* use split-adjusted price. total_return_* uses dividend-adjusted closeadj.
    momentum_4w,                                                                                                -- 4-week price momentum (rate of change)
    momentum_8w,                                                                                                -- 8-week price momentum
    momentum_12w,                                                                                               -- 12-week price momentum
    momentum_26w,                                                                                               -- 26-week price momentum
    momentum_acceleration_4w,                                                                                   -- 1-week acceleration of 4-week momentum
    momentum_acceleration_8w,                                                                                   -- 1-week acceleration of 8-week momentum
    momentum_acceleration_12w,                                                                                  -- 1-week acceleration of 12-week momentum
    perf_1w,                                                                                                    -- 1-week total return
    momentum_4w AS perf_4w,                                                                                     -- 4-week total return
    momentum_8w AS perf_8w,                                                                                     -- 8-week total return
    momentum_12w AS perf_12w,                                                                                   -- 12-week total return
    momentum_26w AS perf_26w,                                                                                   -- 26-week total return
    total_return_1w,
    total_return_4w,
    total_return_8w,
    total_return_12w,
    total_return_26w,
    perf_1w_acceleration,                                                                                       -- 1-week acceleration of 1-week performance
    perf_4w_acceleration_final AS perf_4w_acceleration,                                                         -- 4-week acceleration of 1-week performance
    perf_8w_acceleration_final AS perf_8w_acceleration,                                                         -- 8-week acceleration of 1-week performance
    perf_12w_acceleration_final AS perf_12w_acceleration,                                                       -- 12-week acceleration of 1-week performance

    -- Oscillators (Indicators that move between high and low bands)
    macd_line,                                                                                                  -- MACD Line (12w EMA - 26w EMA)
    macd_signal,                                                                                                -- MACD Signal Line (9w EMA of MACD Line)
    macd_histogram,                                                                                             -- MACD Histogram (MACD Line - Signal Line)
    rsi14w,                                                                                                     -- 14-week Relative Strength Index
    stoch_k_14w,                                                                                                -- 14-week Stochastic Oscillator %K
    stoch_d_14w,                                                                                                -- 3-week SMA of Stochastic %K (known as %D)
    williams_r_14w,                                                                                             -- 14-week Williams %R

    -- Bollinger Bands (Based on 20-week SMA)
    sma20w AS bb20w_middle,                                                                                     -- Middle Band (the 20-week SMA)
    sma20w + (2 * bb_stddev) AS bb20w_upper,                                                                     -- Upper Band (2 standard deviations above Middle)
    sma20w - (2 * bb_stddev) AS bb20w_lower,                                                                     -- Lower Band (2 standard deviations below Middle)
    (bb20w_upper - bb20w_lower) / nullIf(bb20w_middle, 0) AS bb20w_width,                                        -- Width of the bands as a percentage of the middle band
    (close - bb20w_lower) / nullIf(bb20w_upper - bb20w_lower, 0) AS bb20w_position,                             -- Price position within the bands (0-1), aka %B

    -- Volatility & Price Action
    (close - low) / nullIf(high - low, 0) * 100 AS wcr_pct,                                                      -- Weekly Close Range Percentage (where close is within the week's high-low range)
    (atr_10w / nullIf(close, 0)) * 100 AS atr_10w_pct,                                                          -- 10-week Average True Range as a percentage of the close price
    sch.stage_code AS stage_code,
    sch.stage_duration AS stage_duration,
    ifNull(
        ssc.stage_transition_state,
        tuple(toUInt8(0), arrayWithConstant(8, toUInt32(0)), toFloat64(1e9), toUInt32(0), toUInt8(0))
    ) AS stage_transition_state

FROM final_data
LEFT JOIN stage_code_history AS sch
    ON (final_data.ticker = sch.ticker) AND (final_data.date = sch.date)
LEFT JOIN stage_state_checkpoint AS ssc
    ON (final_data.ticker = ssc.ticker) AND (final_data.date = ssc.date)
WHERE final_data.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) AND toMonday(CAST({chunk_end_date:String}, 'Date'));
