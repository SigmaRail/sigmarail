-- Per-symbol tactical technical features (SMA proxies; daily EMA deferred).
-- Populated by 84-symbol-technical-features-daily.sql

CREATE TABLE IF NOT EXISTS symbol_technical_features_daily
(
    `ticker` String COMMENT 'Ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Row update timestamp',
    `pct_from_sma10d` Nullable(Float64) COMMENT 'close/sma10d - 1',
    `pct_from_sma20d` Nullable(Float64) COMMENT 'close/sma20d - 1 (SMA proxy for IBD 21 EMA distance)',
    `drawdown_from_20d_high` Nullable(Float64) COMMENT 'close/rolling_max(high,20) - 1',
    `drawdown_from_50d_high` Nullable(Float64) COMMENT 'close/rolling_max(high,50) - 1',
    `drawdown_from_63d_high` Nullable(Float64) COMMENT 'close/rolling_max(high,63) - 1',
    `consecutive_up_days` Nullable(UInt16) COMMENT 'Streak of closes above prior close (0 if today down/flat)',
    `up_days_last_3` Nullable(UInt8) COMMENT 'Count of up days in last 3 sessions incl today',
    `up_days_last_5` Nullable(UInt8) COMMENT 'Count of up days in last 5 sessions incl today',
    `close_location_pct` Nullable(Float64) COMMENT '(close-low)/(high-low) for session; NULL if range=0',
    `downside_reversal_flag` Nullable(UInt8) COMMENT '1 when new high vs prior day and close in lower 50% of range',
    `extended_above_sma20_flag` Nullable(UInt8) COMMENT '1 when pct_from_sma20d >= 0.10',
    `near_sma20_flag` Nullable(UInt8) COMMENT '1 when abs(pct_from_sma20d) <= 0.04',
    `closes_below_sma20_streak` Nullable(UInt16) COMMENT 'Consecutive closes below sma20d',
    `two_closes_below_sma20` Nullable(UInt8) COMMENT '1 when closes_below_sma20_streak >= 2',
    `first_up_day_low` Nullable(Float64) COMMENT 'Low of first up day after pullback cycle (guide stop)',
    `first_up_day_date` Nullable(Date) COMMENT 'Date of first up day after pullback cycle',
    `pullback_ready` Nullable(UInt8) COMMENT '1 when drawdown_from_50d_high <= -0.05',
    `three_up_days` Nullable(UInt8) COMMENT '1 when up_days_last_3 = 3',
    `entry_gate` Nullable(UInt8) COMMENT '1 when pullback_ready AND three_up_days AND spy_above200d'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: symbol_technical_features_daily
-- Symbol-level tactical technical features (SMA proxies for IBD-style rules).
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_symbol_technical_features_daily;

CREATE VIEW IF NOT EXISTS xform_symbol_technical_features_daily
COMMENT '{"order":84,"target":"symbol_technical_features_daily","sources":["daily_metrics","market_regime_signals_daily"],"chunk_size":"1w"}'
AS
SELECT
    ticker,
    date,
    now() AS lastupdated,
    pct_from_sma10d,
    pct_from_sma20d,
    drawdown_from_20d_high,
    drawdown_from_50d_high,
    drawdown_from_63d_high,
    consecutive_up_days,
    up_days_last_3,
    up_days_last_5,
    close_location_pct,
    downside_reversal_flag,
    extended_above_sma20_flag,
    near_sma20_flag,
    closes_below_sma20_streak,
    two_closes_below_sma20,
    first_up_day_low,
    first_up_day_date,
    pullback_ready,
    three_up_days,
    entry_gate
FROM (
    WITH
    enriched AS (
        SELECT
            dm.ticker,
            dm.date,
            dm.close,
            dm.high,
            dm.low,
            dm.sma10d,
            dm.sma20d,
            lagInFrame(dm.close, 1) OVER (PARTITION BY dm.ticker ORDER BY dm.date) AS prev_close,
            lagInFrame(dm.high, 1) OVER (PARTITION BY dm.ticker ORDER BY dm.date) AS prev_high,
            max(dm.high) OVER (
                PARTITION BY dm.ticker ORDER BY dm.date
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS high_20d,
            max(dm.high) OVER (
                PARTITION BY dm.ticker ORDER BY dm.date
                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
            ) AS high_50d,
            max(dm.high) OVER (
                PARTITION BY dm.ticker ORDER BY dm.date
                ROWS BETWEEN 62 PRECEDING AND CURRENT ROW
            ) AS high_63d,
            coalesce(mrs.spy_above200d, toUInt8(0)) AS spy_above200d
        FROM daily_metrics AS dm FINAL
        LEFT JOIN market_regime_signals_daily AS mrs FINAL
            ON dm.date = mrs.date
        -- 63-session frames plus counter warmup need more than 90d of pad in
        -- holiday-thinned months; 120d keeps every emitted row fully warmed.
        WHERE dm.date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 120 DAY
                          AND toDate({chunk_end_date:String})
    ),
    flags AS (
        SELECT
            *,
            (`close` / nullIf(sma10d, 0)) - 1 AS pct_from_sma10d,
            (`close` / nullIf(sma20d, 0)) - 1 AS pct_from_sma20d,
            (`close` / nullIf(high_20d, 0)) - 1 AS drawdown_from_20d_high,
            (`close` / nullIf(high_50d, 0)) - 1 AS drawdown_from_50d_high,
            (`close` / nullIf(high_63d, 0)) - 1 AS drawdown_from_63d_high,
            toUInt8(prev_close IS NOT NULL AND `close` > prev_close) AS is_up,
            toUInt8(`close` < sma20d) AS below_sma20,
            if(
                high > low,
                (`close` - low) / nullIf(high - low, 0),
                CAST(NULL AS Nullable(Float64))
            ) AS close_location_pct,
            toUInt8(
                prev_high IS NOT NULL
                AND high > prev_high
                AND high > low
                AND (`close` - low) / nullIf(high - low, 0) <= 0.5
            ) AS downside_reversal_flag
        FROM enriched
    ),
    streaks AS (
        SELECT
            *,
            sum(if(NOT is_up, 1, 0)) OVER (
                PARTITION BY ticker ORDER BY date ROWS UNBOUNDED PRECEDING
            ) AS up_streak_grp,
            sum(if(NOT below_sma20, 1, 0)) OVER (
                PARTITION BY ticker ORDER BY date ROWS UNBOUNDED PRECEDING
            ) AS below_sma20_grp,
            sum(if(drawdown_from_50d_high > -0.05, 1, 0)) OVER (
                PARTITION BY ticker ORDER BY date ROWS UNBOUNDED PRECEDING
            ) AS pullback_cycle_grp
        FROM flags
    ),
    streak_counts AS (
        SELECT
            *,
            if(
                is_up,
                toUInt16(row_number() OVER (PARTITION BY ticker, up_streak_grp ORDER BY date)),
                toUInt16(0)
            ) AS consecutive_up_days,
            toUInt8(countIf(is_up) OVER (
                PARTITION BY ticker ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            )) AS up_days_last_3,
            toUInt8(countIf(is_up) OVER (
                PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            )) AS up_days_last_5,
            if(
                below_sma20,
                toUInt16(row_number() OVER (PARTITION BY ticker, below_sma20_grp ORDER BY date)),
                toUInt16(0)
            ) AS closes_below_sma20_streak
        FROM streaks
    ),
    first_up AS (
        SELECT
            *,
            toUInt8(pct_from_sma20d >= 0.10) AS extended_above_sma20_flag,
            toUInt8(abs(pct_from_sma20d) <= 0.04) AS near_sma20_flag,
            toUInt8(closes_below_sma20_streak >= 2) AS two_closes_below_sma20,
            toUInt8(drawdown_from_50d_high <= -0.05) AS pullback_ready,
            toUInt8(up_days_last_3 = 3) AS three_up_days,
            toUInt8(
                drawdown_from_50d_high <= -0.05
                AND up_days_last_3 = 3
                AND spy_above200d = 1
            ) AS entry_gate,
            if(
                is_up AND consecutive_up_days = 1 AND drawdown_from_50d_high <= -0.03,
                low,
                CAST(NULL AS Nullable(Float64))
            ) AS first_up_low_today,
            if(
                is_up AND consecutive_up_days = 1 AND drawdown_from_50d_high <= -0.03,
                date,
                CAST(NULL AS Nullable(Date))
            ) AS first_up_date_today
        FROM streak_counts
    ),
    -- Seed for the path-dependent state: pullback cycles run ~1y and streak
    -- groups can predate the 90-day read pad. The last emitted row per ticker
    -- hands (streak counters, first-up markers) across the chunk boundary.
    feature_seed AS (
        SELECT
            ticker,
            argMax(consecutive_up_days, date) AS seed_consec_up,
            argMax(closes_below_sma20_streak, date) AS seed_below_streak,
            argMax(first_up_day_low, date) AS seed_first_low,
            argMax(first_up_day_date, date) AS seed_first_date,
            max(date) AS seed_date
        FROM symbol_technical_features_daily FINAL
        WHERE date < toDate({chunk_start_date:String})
        GROUP BY ticker
    ),
    marked AS (
        SELECT
            fu.*,
            ss.seed_consec_up,
            ss.seed_below_streak,
            ss.seed_first_low,
            ss.seed_first_date,
            ss.seed_date,
            min(fu.date) OVER (PARTITION BY fu.ticker, fu.up_streak_grp) AS up_grp_start,
            min(fu.date) OVER (PARTITION BY fu.ticker, fu.below_sma20_grp) AS below_grp_start,
            min(fu.date) OVER (PARTITION BY fu.ticker, fu.pullback_cycle_grp) AS cycle_grp_start,
            countIf(fu.date <= ss.seed_date) OVER (PARTITION BY fu.ticker, fu.up_streak_grp) AS up_grp_pre_seed,
            countIf(fu.date <= ss.seed_date) OVER (PARTITION BY fu.ticker, fu.below_sma20_grp) AS below_grp_pre_seed,
            anyLast(fu.first_up_low_today) OVER (
                PARTITION BY fu.ticker, fu.pullback_cycle_grp ORDER BY fu.date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS marker_low_inwin,
            anyLast(fu.first_up_date_today) OVER (
                PARTITION BY fu.ticker, fu.pullback_cycle_grp ORDER BY fu.date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS marker_date_inwin
        FROM first_up fu
        LEFT JOIN feature_seed ss ON fu.ticker = ss.ticker
    )
    SELECT
        ticker,
        date,
        pct_from_sma10d,
        pct_from_sma20d,
        drawdown_from_20d_high,
        drawdown_from_50d_high,
        drawdown_from_63d_high,
        -- Continue streak counters/markers from the seed row when the detected
        -- group boundary is at-or-before it (no reset observed between them).
        -- The seed's effective position is its group-row count when it is the
        -- group opener (a non-flag row records 0 but occupies position 1).
        -- `consecutive_up_days`/`closes_below_sma20_streak` inside each if
        -- resolve to the SOURCE columns (in-window row_number position), so
        -- `seed_pos + pos - pre_seed` continues the true count.
        if(
            is_up AND up_grp_start <= seed_date,
            toUInt16(if(seed_consec_up > 0, seed_consec_up, up_grp_pre_seed)
                + consecutive_up_days - up_grp_pre_seed),
            consecutive_up_days
        ) AS consecutive_up_days,
        up_days_last_3,
        up_days_last_5,
        close_location_pct,
        downside_reversal_flag,
        extended_above_sma20_flag,
        near_sma20_flag,
        if(
            below_sma20 AND below_grp_start <= seed_date,
            toUInt16(if(seed_below_streak > 0, seed_below_streak, below_grp_pre_seed)
                + closes_below_sma20_streak - below_grp_pre_seed),
            closes_below_sma20_streak
        ) AS closes_below_sma20_streak,
        toUInt8(closes_below_sma20_streak >= 2) AS two_closes_below_sma20,
        if(
            cycle_grp_start <= seed_date,
            coalesce(marker_low_inwin, seed_first_low),
            marker_low_inwin
        ) AS first_up_day_low,
        if(
            cycle_grp_start <= seed_date,
            coalesce(marker_date_inwin, seed_first_date),
            marker_date_inwin
        ) AS first_up_day_date,
        pullback_ready,
        three_up_days,
        entry_gate
    FROM marked
    WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
);
