-- =============================================================================
-- TABLE: market_context_daily
-- kind=delivery_projection layer=L6
-- =============================================================================
--
-- PURPOSE: One row per trading session with market-wide context columns that
--          102-daily-screener currently denormalizes onto every ticker row
--          (regime / breadth / FTD / SPY / weekly market block).
--
-- ENGINE: ReplacingMergeTree(lastupdated)
--
-- Column names match daily_screener (91-schema-daily-screener.sql) so L7 VIEW
-- cutover can project without renames. No industry_group_strength / per-ticker
-- stage columns here.
--
-- entities.yaml: skipped for M1 (Episode A2).
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_context_daily
(
    `date` Date COMMENT 'Trading session date (daily grain)',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `weekly_date` Date COMMENT 'Weekly regime join key (prior closed weekly Monday; from market_regime_signals_daily.weekly_date)',
    `mrs.weekly_allocation_fraction` Float32 COMMENT 'Weekly allocation fraction from market_regime_signals (forward-filled via market_regime_signals_daily)',
    `mrs.weekly_allocation_tier` UInt8 COMMENT 'Weekly allocation tier from market_regime_signals (forward-filled via market_regime_signals_daily)',
    `breadth_200d` Float32 COMMENT 'Daily breadth: fraction of universe above 200d SMA (from market_regime_signals_daily)',
    `spy_close` Float64 COMMENT 'SPY official close for the session (from market_regime_signals_daily.spy_close)',
    `spy_sma200d` Float64 COMMENT 'SPY 200-day SMA (from market_regime_signals_daily.spy_sma200d)',
    `spy_below200d` UInt8 COMMENT '1 if SPY close < SPY 200d SMA (from market_regime_signals_daily.spy_below200d)',
    `spy_below200d_3d` UInt8 COMMENT '1 if SPY below 200d SMA for 3 consecutive days (from market_regime_signals_daily.spy_below200d_3d)',
    `breadth55_days15` UInt8 COMMENT 'Count of last 15 sessions with breadth_200d >= 0.55 (from market_regime_signals_daily)',
    `clamp_risk_off` UInt8 COMMENT 'Daily clamp flag forcing risk-off allocation (from market_regime_signals_daily)',
    `breadth_50d` Float32 COMMENT 'Daily breadth: fraction above 50d SMA (from market_regime_signals_daily)',
    `breadth_thrust` UInt8 COMMENT 'Breadth thrust signal (from market_regime_signals_daily)',
    `ftd` UInt8 COMMENT 'Follow-through day proxy flag (from market_regime_signals_daily)',
    `distribution_count_25d` UInt8 COMMENT 'Distribution day count over last 25 sessions (from market_regime_signals_daily)',
    `spy_sma50d` Float64 COMMENT 'SPY 50-day SMA (from market_regime_signals_daily.spy_sma50d)',
    `spy_above50d` UInt8 COMMENT '1 if SPY close > SPY 50d SMA (from market_regime_signals_daily)',
    `spy_above200d` UInt8 COMMENT '1 if SPY close > SPY 200d SMA (from market_regime_signals_daily)',
    `ma50_gt_ma200` UInt8 COMMENT '1 if SPY SMA50d > SMA200d (from market_regime_signals_daily)',
    `ma50_slope_pos` UInt8 COMMENT '1 if SPY SMA50d slope positive (from market_regime_signals_daily)',
    `ma200_slope_pos` UInt8 COMMENT '1 if SPY SMA200d slope positive (from market_regime_signals_daily)',
    `ma_stack_score` UInt8 COMMENT '0..5 MA stack score (from market_regime_signals_daily)',
    `risk_on_fast_flags` UInt8 COMMENT '0..4 count of fast risk-on diagnostics (from market_regime_signals_daily)',
    `risk_off_fast_flags` UInt8 COMMENT '0..4 count of fast risk-off diagnostics (from market_regime_signals_daily)',
    `allocation_reason` String COMMENT 'Daily allocation reason (from market_regime_signals_daily.allocation_reason)',
    `is_bear_market_enhanced` UInt8 COMMENT 'Enhanced bear-market flag (from enhanced_bear_market_signals)',
    `bear_severity` LowCardinality(String) COMMENT 'Bear-market severity label (from enhanced_bear_market_signals)',
    `bear_market_score` Float64 COMMENT 'Bear-market score (from enhanced_bear_market_signals)',
    `primary_condition` LowCardinality(String) COMMENT 'Primary bear-market condition that triggered (from enhanced_bear_market_signals)',
    `confirmation_conditions` LowCardinality(String) COMMENT 'Confirmation conditions that supported the signal (from enhanced_bear_market_signals)',
    `pct_near_52w_high` Float64 COMMENT 'Market breadth: fraction of universe near 52-week highs (from broad_market_breadth)',
    `pct_near_52w_low` Float64 COMMENT 'Market breadth: fraction of universe near 52-week lows (from broad_market_breadth)',
    `pct_above_sma20d` Float64 COMMENT 'Market breadth: fraction of universe above 20d SMA (from broad_market_breadth)',
    `pct_above_sma50d` Float64 COMMENT 'Market breadth: fraction of universe above 50d SMA (from broad_market_breadth)',
    `pct_above_sma200d` Float64 COMMENT 'Market breadth: fraction of universe above 200d SMA (from broad_market_breadth)',
    `pct_above_sma20d_sma5` Float64 COMMENT 'Market breadth: 5-day smoothed fraction above 20d SMA (from broad_market_breadth)',
    `pct_above_sma50d_sma5` Float64 COMMENT 'Market breadth: 5-day smoothed fraction above 50d SMA (from broad_market_breadth)',
    `pct_above_sma200d_sma5` Float64 COMMENT 'Market breadth: 5-day smoothed fraction above 200d SMA (from broad_market_breadth)',
    `price_vs_sma30w_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: (close/sma30w) - 1 (from market_trend_template)',
    `price_vs_sma40w_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: (close/sma40w) - 1 (from market_trend_template)',
    `sma30w_vs_sma40w_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: (sma30w/sma40w) - 1 (from market_trend_template)',
    `sma40w_slope_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: 4-week slope of sma40w (from market_trend_template)',
    `price_vs_52w_high_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: (close/high_52w) - 1 (from market_trend_template)',
    `price_vs_52w_low_pct` Nullable(Float64) COMMENT 'Market trend template magnitude: (close/low_52w) - 1 (from market_trend_template)',
    `is_price_above_sma30w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks price is above/below 30w SMA (from market_trend_template)',
    `is_price_above_sma40w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks price is above/below 40w SMA (from market_trend_template)',
    `is_sma30w_above_sma40w_duration` Nullable(UInt16) COMMENT 'Consecutive weeks 30w SMA is above/below 40w SMA (from market_trend_template)',
    `is_sma40w_trending_up_duration` Nullable(UInt16) COMMENT 'Consecutive weeks 40w SMA slope is positive/negative (from market_trend_template)',
    `trend_score` UInt8 COMMENT 'Weekly market trend template score (0-6; from market_trend_template.trend_score)',
    `pct_sp500_above_sma40w` Nullable(Float64) COMMENT 'Weekly breadth: percent of S&P 500 above 40-week SMA (from broad_market_breadth_weekly)',
    `pct_stocks_above_sma200` Float64 COMMENT 'Weekly breadth proxy used for regime scoring (from market_regime_signals.pct_stocks_above_sma200)',
    `market_sma200_trend_strength` Float64 COMMENT 'Weekly trend strength score (from market_regime_signals.market_sma200_trend_strength)',
    `composite_score_raw` Float64 COMMENT 'Weekly regime composite score raw (0..1; from market_regime_signals.composite_score_raw)',
    `composite_score_normalized` Float64 COMMENT 'Weekly regime composite score normalized (0..100; from market_regime_signals.composite_score_normalized)',
    `is_bear_market_active` UInt8 COMMENT 'Weekly bear-market override flag (from market_regime_signals.is_bear_market_active)',
    `market_regime_signal` Float32 COMMENT 'Weekly regime bucket/signal (0/50/100; from market_regime_signals.market_regime_signal)',
    `weekly_allocation_fraction` Float32 COMMENT 'Weekly allocation fraction (0..1; from market_regime_signals.allocation_fraction)',
    `weekly_allocation_tier` UInt8 COMMENT 'Weekly allocation tier (percent-scaled; from market_regime_signals.allocation_tier)',
    `allocation_note` String COMMENT 'Weekly allocation note (from market_regime_signals.allocation_note)',
    `vix_close` Nullable(Float64) COMMENT '^VIX close price',
    `vix_sma20d` Nullable(Float64) COMMENT '^VIX 20-day SMA',
    `vix_sma50d` Nullable(Float64) COMMENT '^VIX 50-day SMA',
    `vix_sma200d` Nullable(Float64) COMMENT '^VIX 200-day SMA',
    `vix_atr_14_pct` Nullable(Float64) COMMENT '^VIX ATR14 as % of close',
    `vix_vs_sma20d_pct` Nullable(Float64) COMMENT '^VIX vs SMA20 % (from daily_metrics_derived)',
    `vix_vs_sma50d_pct` Nullable(Float64) COMMENT '^VIX vs SMA50 % (from daily_metrics_derived)',
    `vix_vs_sma200d_pct` Nullable(Float64) COMMENT '^VIX vs SMA200 % (from daily_metrics_derived)',
    `uvxy_close` Nullable(Float64) COMMENT 'UVXY close price',
    `uvxy_vs_vix_basis` Nullable(Float64) COMMENT 'UVXY/VIX basis (contango proxy)',
    `svxy_close` Nullable(Float64) COMMENT 'SVXY close price',
    `svxy_vs_vix_basis` Nullable(Float64) COMMENT 'SVXY/VIX basis (backwardation proxy)',
    `vix_contango_proxy` UInt8 COMMENT '1 if UVXY basis > SVXY basis (contango)',
    `vix_spike_flag` UInt8 COMMENT '1 if VIX ATR% > 1.5x 20d avg',
    `vix_above_sma200d` UInt8 COMMENT '1 if VIX > SMA200'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192
COMMENT 'L6 delivery_projection: session-level market context (regime/breadth/FTD/SPY/weekly) extracted from 102-daily-screener join block';

-- Managed transform view for target: market_context_daily
-- =============================================================================
-- TRANSFORM: Populate market_context_daily (L6 delivery_projection)
-- =============================================================================
--
-- PURPOSE: Materialize one market-context row per trading session using the
--          same market JOIN keys as 102-daily-screener (without ticker spine,
--          industry_group_strength, or per-ticker stage regimes).
--
-- WEEKLY JOINS: market_trend_template, broad_market_breadth_weekly, and
-- market_regime_signals use the *prior closed* ISO Monday:
--   weekly_join_date = toMonday(date) - 7 days
--
-- =============================================================================
DROP VIEW IF EXISTS xform_market_context_daily;

CREATE VIEW IF NOT EXISTS xform_market_context_daily (
    `date`,
    `lastupdated`,
    `weekly_date`,
    `mrs.weekly_allocation_fraction`,
    `mrs.weekly_allocation_tier`,
    `breadth_200d`,
    `spy_close`,
    `spy_sma200d`,
    `spy_below200d`,
    `spy_below200d_3d`,
    `breadth55_days15`,
    `clamp_risk_off`,
    `breadth_50d`,
    `breadth_thrust`,
    `ftd`,
    `distribution_count_25d`,
    `spy_sma50d`,
    `spy_above50d`,
    `spy_above200d`,
    `ma50_gt_ma200`,
    `ma50_slope_pos`,
    `ma200_slope_pos`,
    `ma_stack_score`,
    `risk_on_fast_flags`,
    `risk_off_fast_flags`,
    `allocation_reason`,
    `is_bear_market_enhanced`,
    `bear_severity`,
    `bear_market_score`,
    `primary_condition`,
    `confirmation_conditions`,
    `pct_near_52w_high`,
    `pct_near_52w_low`,
    `pct_above_sma20d`,
    `pct_above_sma50d`,
    `pct_above_sma200d`,
    `pct_above_sma20d_sma5`,
    `pct_above_sma50d_sma5`,
    `pct_above_sma200d_sma5`,
    `price_vs_sma30w_pct`,
    `price_vs_sma40w_pct`,
    `sma30w_vs_sma40w_pct`,
    `sma40w_slope_pct`,
    `price_vs_52w_high_pct`,
    `price_vs_52w_low_pct`,
    `is_price_above_sma30w_duration`,
    `is_price_above_sma40w_duration`,
    `is_sma30w_above_sma40w_duration`,
    `is_sma40w_trending_up_duration`,
    `trend_score`,
    `pct_sp500_above_sma40w`,
    `pct_stocks_above_sma200`,
    `market_sma200_trend_strength`,
    `composite_score_raw`,
    `composite_score_normalized`,
    `is_bear_market_active`,
    `market_regime_signal`,
    `weekly_allocation_fraction`,
    `weekly_allocation_tier`,
    `allocation_note`,
    `vix_close`,
    `vix_sma20d`,
    `vix_sma50d`,
    `vix_sma200d`,
    `vix_atr_14_pct`,
    `vix_vs_sma20d_pct`,
    `vix_vs_sma50d_pct`,
    `vix_vs_sma200d_pct`,
    `uvxy_close`,
    `uvxy_vs_vix_basis`,
    `svxy_close`,
    `svxy_vs_vix_basis`,
    `vix_contango_proxy`,
    `vix_spike_flag`,
    `vix_above_sma200d`
)
COMMENT '{"order":110,"target":"market_context_daily","sources":["market_regime_signals_daily","broad_market_breadth","broad_market_breadth_weekly","market_regime_signals","enhanced_bear_market_signals","market_trend_template","daily_metrics","daily_metrics_derived"],"chunk_size":"1m"}'
AS
SELECT
    spine.date AS `date`,
    now() AS `lastupdated`,

    -- Market Regime Signals (from market_regime_signals_daily)
    mrs.weekly_date,
    mrs.weekly_allocation_fraction AS `mrs.weekly_allocation_fraction`,
    mrs.weekly_allocation_tier AS `mrs.weekly_allocation_tier`,
    mrs.breadth_200d,
    mrs.spy_close,
    mrs.spy_sma200d,
    mrs.spy_below200d,
    mrs.spy_below200d_3d,
    mrs.breadth55_days15,
    mrs.clamp_risk_off,
    mrs.breadth_50d,
    mrs.breadth_thrust,
    mrs.ftd,
    mrs.distribution_count_25d,
    mrs.spy_sma50d,
    mrs.spy_above50d,
    mrs.spy_above200d,
    mrs.ma50_gt_ma200,
    mrs.ma50_slope_pos,
    mrs.ma200_slope_pos,
    mrs.ma_stack_score,
    mrs.risk_on_fast_flags,
    mrs.risk_off_fast_flags,
    mrs.allocation_reason,

    -- Enhanced Bear Market Signals
    ebms.is_bear_market_enhanced,
    ebms.bear_severity,
    ebms.bear_market_score,
    ebms.primary_condition,
    ebms.confirmation_conditions,

    -- Broad Market Breadth (daily)
    bmb.pct_near_52w_high,
    bmb.pct_near_52w_low,
    bmb.pct_above_sma20d,
    bmb.pct_above_sma50d,
    bmb.pct_above_sma200d,
    bmb.pct_above_sma20d_sma5,
    bmb.pct_above_sma50d_sma5,
    bmb.pct_above_sma200d_sma5,

    -- Market Trend Template (weekly join)
    mtt.price_vs_sma30w_pct,
    mtt.price_vs_sma40w_pct,
    mtt.sma30w_vs_sma40w_pct,
    mtt.sma40w_slope_pct,
    mtt.price_vs_52w_high_pct,
    mtt.price_vs_52w_low_pct,
    mtt.is_price_above_sma30w_duration,
    mtt.is_price_above_sma40w_duration,
    mtt.is_sma30w_above_sma40w_duration,
    mtt.is_sma40w_trending_up_duration,
    mtt.trend_score,

    -- Broad Market Breadth Weekly
    bmbw.pct_sp500_above_sma40w,

    -- Market Regime Signals weekly
    mrs_weekly.pct_stocks_above_sma200,
    mrs_weekly.market_sma200_trend_strength,
    mrs_weekly.composite_score_raw,
    mrs_weekly.composite_score_normalized,
    mrs_weekly.is_bear_market_active,
    mrs_weekly.market_regime_signal,
    mrs_weekly.allocation_fraction AS weekly_allocation_fraction,
    mrs_weekly.allocation_tier AS weekly_allocation_tier,
    mrs_weekly.allocation_note,

    -- VIX / Volatility regime proxies
    vix.vix_close,
    vix.vix_sma20d,
    vix.vix_sma50d,
    vix.vix_sma200d,
    vix.vix_atr_14_pct,
    vix.vix_vs_sma20d_pct,
    vix.vix_vs_sma50d_pct,
    vix.vix_vs_sma200d_pct,
    vix.uvxy_close,
    vix.uvxy_vs_vix_basis,
    vix.svxy_close,
    vix.svxy_vs_vix_basis,
    vix.vix_contango_proxy,
    vix.vix_spike_flag,
    vix.vix_above_sma200d
FROM (
    SELECT
        date,
        toMonday(date) - toIntervalDay(7) AS weekly_join_date
    FROM market_regime_signals_daily FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
) spine
LEFT JOIN market_regime_signals_daily AS mrs FINAL
  ON spine.date = mrs.date
 AND mrs.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
LEFT JOIN enhanced_bear_market_signals AS ebms FINAL
  ON spine.date = ebms.date
 AND ebms.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
LEFT JOIN broad_market_breadth AS bmb FINAL
  ON spine.date = bmb.date
 AND bmb.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
LEFT JOIN market_trend_template AS mtt FINAL
  ON mtt.date = spine.weekly_join_date
 AND mtt.date BETWEEN toMonday(toDate({chunk_start_date:String})) - toIntervalDay(56)
            AND toMonday(toDate({chunk_end_date:String}))
LEFT JOIN broad_market_breadth_weekly AS bmbw FINAL
  ON bmbw.date = spine.weekly_join_date
 AND bmbw.date BETWEEN toMonday(toDate({chunk_start_date:String})) - toIntervalDay(56)
            AND toMonday(toDate({chunk_end_date:String}))
LEFT JOIN market_regime_signals AS mrs_weekly FINAL
  ON spine.weekly_join_date = mrs_weekly.date
 AND mrs_weekly.date BETWEEN toMonday(toDate({chunk_start_date:String})) - toIntervalDay(56)
                     AND toMonday(toDate({chunk_end_date:String}))
LEFT JOIN (
    WITH
    vix_base AS (
        SELECT
            date,
            `close` AS vix_close,
            sma20d AS vix_sma20d,
            sma50d AS vix_sma50d,
            sma200d AS vix_sma200d,
            atr_14_pct AS vix_atr_14_pct
        FROM daily_metrics FINAL
        WHERE ticker = '^VIX'
          -- 45-day input pad warms vix_atr_stats' 20-session average (>=20
          -- sessions even in holiday-thinned months); the join to spine below
          -- drops pad rows, so nothing extra is emitted.
          AND date BETWEEN addDays(toDate({chunk_start_date:String}), -45) AND {chunk_end_date:String}
    ),
    vix_derived AS (
        SELECT
            date,
            price_vs_sma20 AS vix_vs_sma20d_pct,
            price_vs_sma50 AS vix_vs_sma50d_pct,
            price_vs_sma200 AS vix_vs_sma200d_pct
        FROM daily_metrics_derived FINAL
        WHERE ticker = '^VIX'
          AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    ),
    uvxy_base AS (
        SELECT date, `close` AS uvxy_close
        FROM daily_metrics FINAL
        WHERE ticker = 'UVXY'
          AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    ),
    svxy_base AS (
        SELECT date, `close` AS svxy_close
        FROM daily_metrics FINAL
        WHERE ticker = 'SVXY'
          AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    ),
    vix_atr_stats AS (
        SELECT
            date,
            avg(vix_atr_14_pct) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vix_atr_14_pct_avg_20d
        FROM vix_base
    )
    SELECT
        vix_base.date AS date,
        vix_base.vix_close,
        vix_base.vix_sma20d,
        vix_base.vix_sma50d,
        vix_base.vix_sma200d,
        vix_base.vix_atr_14_pct,
        vix_derived.vix_vs_sma20d_pct,
        vix_derived.vix_vs_sma50d_pct,
        vix_derived.vix_vs_sma200d_pct,
        uvxy_base.uvxy_close,
        (uvxy_base.uvxy_close / vix_base.vix_close) - 1 AS uvxy_vs_vix_basis,
        svxy_base.svxy_close,
        (svxy_base.svxy_close / vix_base.vix_close) - 1 AS svxy_vs_vix_basis,
        CAST(coalesce((uvxy_base.uvxy_close / vix_base.vix_close - 1) > (svxy_base.svxy_close / vix_base.vix_close - 1), 0) AS UInt8) AS vix_contango_proxy,
        CAST(coalesce(vix_base.vix_atr_14_pct > 1.5 * vix_atr_stats.vix_atr_14_pct_avg_20d, 0) AS UInt8) AS vix_spike_flag,
        CAST(coalesce(vix_base.vix_close > vix_base.vix_sma200d, 0) AS UInt8) AS vix_above_sma200d
    FROM vix_base
    LEFT JOIN vix_derived ON vix_base.date = vix_derived.date
    LEFT JOIN uvxy_base ON vix_base.date = uvxy_base.date
    LEFT JOIN svxy_base ON vix_base.date = svxy_base.date
    LEFT JOIN vix_atr_stats ON vix_base.date = vix_atr_stats.date
) vix ON spine.date = vix.date;
