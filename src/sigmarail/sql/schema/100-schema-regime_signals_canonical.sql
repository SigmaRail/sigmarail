-- =============================================================================
-- Layer 1 (Canonical): Regime Signals (per ticker, per date)
-- =============================================================================
-- Grain: (ticker, date) daily.
--
-- Purpose:
--   - Provide a deterministic, point-in-time safe catalog of normalized signals
--     in [0,1] that downstream policies can compose into an allocation fraction.
--   - Separate "what we measure" (signals) from "how we decide" (policies).
--
-- Design:
--   - Wide schema (one column per signal) for ClickHouse columnar performance.
--   - For each signal, store:
--       * raw:        Nullable(Float64) (audit/debug)
--       * normalized: Float32 in [0,1]  (policy input)
--   - All normalization parameters (z_window, sigmoid_k, hold_days) are policy-
--     override-able via signal_params_json in the policies layer; defaults live
--     in the transform.
--
-- Populated by: sql/transform/metrics/100-regime-signals-canonical.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS regime_signals_canonical
(
    `ticker` String COMMENT 'Entity key: equity/ETF/index ticker. Macro signals are broadcast from SPY but stored per ticker for uniform composition.',
    `date` Date COMMENT 'Trading session date (daily grain)',
    `s_ma200_macro_raw` Nullable(Float64) COMMENT 'Raw: SPY (closeadj - sma200d)/sma200d',
    `s_ma200_macro` Float32 COMMENT 'Normalized [0,1]: macro trend strength vs SPY SMA200',
    `s_breadth200_raw` Nullable(Float64) COMMENT 'Raw: broad_market_breadth.pct_above_sma200d (0..1)',
    `s_breadth200` Float32 COMMENT 'Normalized [0,1]: breadth above 200d (pass-through)',
    `s_breadth50_raw` Nullable(Float64) COMMENT 'Raw: broad_market_breadth.pct_above_sma50d (0..1)',
    `s_breadth50` Float32 COMMENT 'Normalized [0,1]: breadth above 50d (pass-through)',
    `s_vix_raw` Nullable(Float64) COMMENT 'Raw: ^VIX close (daily_metrics.close)',
    `s_vix` Float32 COMMENT 'Normalized [0,1]: volatility stress (rolling z-score -> sigmoid; shorter window)',
    `s_thrust_raw` Nullable(Float64) COMMENT 'Raw: breadth thrust event flag (0/1)',
    `s_thrust` Float32 COMMENT 'Normalized [0,1]: event/hold decay score for breadth thrust',
    `s_risk_off_raw` Nullable(Float64) COMMENT 'Raw: composite fast risk-off indicator (0..k flags or z-score)',
    `s_risk_off` Float32 COMMENT 'Normalized [0,1]: risk-off stress score (crisis family)',
    `s_ma200_self_raw` Nullable(Float64) COMMENT 'Raw: (closeadj - sma200d)/sma200d for ticker',
    `s_ma200_self` Float32 COMMENT 'Normalized [0,1]: self trend vs SMA200 (rolling z-score -> sigmoid)',
    `s_ma50_self_raw` Nullable(Float64) COMMENT 'Raw: (closeadj - sma50d)/sma50d for ticker',
    `s_ma50_self` Float32 COMMENT 'Normalized [0,1]: self trend vs SMA50 (rolling z-score -> sigmoid)',
    `s_ma_stack_self_raw` Nullable(Float64) COMMENT 'Raw: stack score proxy (0..5 or distance combo) for ticker',
    `s_ma_stack_self` Float32 COMMENT 'Normalized [0,1]: self MA stack strength (rolling z-score -> sigmoid)',
    `s_stage_self_raw` Nullable(Float64) COMMENT 'Raw: stage_analysis.smoothed_allocation (0..1) for ticker',
    `s_stage_self` Float32 COMMENT 'Normalized [0,1]: Weinstein stage-implied allocation (pass-through)',
    `s_mom_6m_self_raw` Nullable(Float64) COMMENT 'Raw: 6m trailing return (daily_metrics_derived.perf_6m) for ticker',
    `s_mom_6m_self` Float32 COMMENT 'Normalized [0,1]: momentum (rolling z-score -> sigmoid)',
    `s_rvol_self_raw` Nullable(Float64) COMMENT 'Raw: realized vol (e.g. 10d stddev of returns) for ticker',
    `s_rvol_self` Float32 COMMENT 'Normalized [0,1]: relative volatility stress (rolling z-score -> sigmoid; shorter window)',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Canonical regime signals per (ticker,date). Wide signal catalog: raw + normalized [0,1] columns. Consumed by regime_policies -> regime_composed_daily.';

-- Managed transform view for target: regime_signals_canonical
-- NOTE: This file intentionally uses a 2-digit numeric prefix so it is
-- discovered by sigmarail-populate's transform manifest: `[0-9][0-9]-*.sql`.
-- The canonical transform implementation is below.

-- =============================================================================
-- Layer 1 (Canonical): Regime Signals (per ticker, per date)
-- =============================================================================
-- Grain: (ticker, date) daily.
--
-- This transform builds normalized canonical signals in [0,1] that can be
-- composed by policies in Layer 2.
--
-- Windowing note:
--   Rolling z-scores require long lookback. We compute a chunk-local lookback
--   start date using daily_price_sequence.trade_day_num so window functions
--   are fully populated within the chunk, then filter back to the true chunk
--   range on INSERT (same pattern as xform_daily_metrics).
--
-- =============================================================================
DROP VIEW IF EXISTS xform_regime_signals_canonical;

CREATE VIEW IF NOT EXISTS xform_regime_signals_canonical (
    ticker,
    date,
    s_ma200_macro_raw,
    s_ma200_macro,
    s_breadth200_raw,
    s_breadth200,
    s_breadth50_raw,
    s_breadth50,
    s_vix_raw,
    s_vix,
    s_thrust_raw,
    s_thrust,
    s_risk_off_raw,
    s_risk_off,
    s_ma200_self_raw,
    s_ma200_self,
    s_ma50_self_raw,
    s_ma50_self,
    s_ma_stack_self_raw,
    s_ma_stack_self,
    s_stage_self_raw,
    s_stage_self,
    s_mom_6m_self_raw,
    s_mom_6m_self,
    s_rvol_self_raw,
    s_rvol_self,
    lastupdated
)
COMMENT '{"order":99,"target":"regime_signals_canonical","sources":["daily_metrics","daily_metrics_derived","broad_market_breadth","stage_analysis","daily_price_sequence"],"chunk_size":"6m"}'
AS
WITH
-- === Default normalization parameters (override-able later via policies) ===
504 AS trend_z_days,
1.5 AS trend_sigmoid_k,
252 AS mom_z_days,
1.5 AS mom_sigmoid_k,
63 AS crisis_z_days,
2.5 AS crisis_sigmoid_k,
20 AS thrust_hold_days,
520 AS max_lookback_trade_days,   -- >= max(z_days) + a little cushion

-- === Determine lookback start date via daily_price_sequence ===
-- Important: use scalar expressions, not subquery CTE identifiers.
(SELECT trade_day_num
 FROM daily_price_sequence FINAL
 WHERE date >= toDate({chunk_start_date:String})
 ORDER BY date ASC
 LIMIT 1) AS chunk_start_trade_day_num_raw,
(chunk_start_trade_day_num_raw - max_lookback_trade_days) AS lookback_start_trade_day_num,
lookback_start_date AS (
  -- If daily_price_sequence is empty (common in minimal test fixtures),
  -- fall back to a conservative calendar-day lookback.
  SELECT
    ifNull(
      (
        SELECT date
        FROM daily_price_sequence FINAL
        WHERE trade_day_num = lookback_start_trade_day_num
        LIMIT 1
      ),
      addDays(toDate({chunk_start_date:String}), -800)
    ) AS start_date
),

-- === Base daily series (read with lookback) ===
dm AS (
  SELECT
    ticker,
    date,
    toFloat64(`close`)    AS close,
    toFloat64(sma50d)     AS sma50d,
    toFloat64(sma200d)    AS sma200d
  FROM daily_metrics FINAL
  WHERE date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
),
dmlag AS (
  -- ClickHouse forbids nesting window functions. Compute ret_1d first.
  SELECT
    d.*,
    (d.close / nullIf(lagInFrame(d.close, 1) OVER (PARTITION BY d.ticker ORDER BY d.date), 0) - 1) AS ret_1d
  FROM dm d
),
dmd AS (
  SELECT
    ticker,
    date,
    toFloat64(perf_6m)          AS perf_6m,
    toFloat64(sma50d_slope_20d) AS sma50d_slope_20d,
    toFloat64(sma200d_slope_20d) AS sma200d_slope_20d,
    toUInt8(price_above_sma50d) AS price_above_sma50d,
    toUInt8(price_above_sma200d) AS price_above_sma200d,
    toUInt8(sma50d_above_sma200d) AS sma50d_above_sma200d
  FROM daily_metrics_derived FINAL
  WHERE date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
),
br AS (
  SELECT
    date,
    toFloat64(pct_above_sma50d)      AS breadth_50d,
    toFloat64(pct_above_sma200d)     AS breadth_200d,
    toFloat64(pct_above_sma50d_sma5) AS breadth_50d_sma5,
    toFloat64(pct_above_sma200d_sma5) AS breadth_200d_sma5
  FROM broad_market_breadth FINAL
  WHERE date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
),
sa AS (
  SELECT
    ticker,
    date,
    toFloat64(smoothed_allocation) AS smoothed_allocation
  FROM stage_analysis FINAL
  WHERE date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
),

-- === Macro anchors (SPY and ^VIX) ===
spy AS (
  SELECT date, close, sma50d, sma200d
  FROM dm
  WHERE ticker = 'SPY'
),
vix AS (
  SELECT date, close AS vix_close
  FROM dm
  WHERE ticker = '^VIX'
),

-- === Macro raw features ===
macro_raw AS (
  SELECT
    s.date AS date,
    -- Trend distance (raw)
    (s.close - s.sma200d) / nullIf(s.sma200d, 0) AS s_ma200_macro_raw,
    -- Breadth raw pass-throughs
    b.breadth_200d AS s_breadth200_raw,
    b.breadth_50d  AS s_breadth50_raw,
    -- VIX raw
    v.vix_close    AS s_vix_raw,
    -- Breadth thrust (event raw flag)
    CAST(
      (b.breadth_50d_sma5 - lagInFrame(b.breadth_50d_sma5, 10) OVER (ORDER BY b.date) >= 0.18)
      OR (b.breadth_50d_sma5 >= 0.60 AND lagInFrame(b.breadth_50d_sma5, 5) OVER (ORDER BY b.date) < 0.45),
      'UInt8'
    ) AS thrust_flag,
    -- Risk-off raw (simple composite): 0..3
    (
      CAST(b.breadth_200d_sma5 < 0.45, 'UInt8')
      + CAST(s.close < s.sma200d, 'UInt8')
      + if(
          isNull(v.vix_close),
          toUInt8(0),
          CAST(
            ifNull(
              (v.vix_close - avg(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW))
              / nullIf(stddevPop(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW), 0),
              0.0
            ) > 1.0,
            'UInt8'
          )
        )
    ) AS s_risk_off_raw
  FROM spy s
  LEFT JOIN br b ON b.date = s.date
  LEFT JOIN vix v ON v.date = s.date
),

-- === Normalize macro features ===
macro_norm AS (
  SELECT
    date,
    s_ma200_macro_raw,
    CAST(
      1 / (1 + exp(-trend_sigmoid_k * (
        ifNull(
          (s_ma200_macro_raw - avg(s_ma200_macro_raw) OVER (ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_ma200_macro_raw) OVER (ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_ma200_macro,
    s_breadth200_raw,
    CAST(greatest(0.0, least(1.0, s_breadth200_raw)), 'Float32') AS s_breadth200,
    s_breadth50_raw,
    CAST(greatest(0.0, least(1.0, s_breadth50_raw)), 'Float32') AS s_breadth50,
    s_vix_raw,
    CAST(
      1 / (1 + exp(-crisis_sigmoid_k * (
        ifNull(
          (s_vix_raw - avg(s_vix_raw) OVER (ORDER BY date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_vix_raw) OVER (ORDER BY date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_vix,
    CAST(thrust_flag, 'Float64') AS s_thrust_raw,
    -- Hold (no decay yet): 1 if any thrust in last thrust_hold_days
    CAST(
      greatest(0, max(thrust_flag) OVER (ORDER BY date ROWS BETWEEN thrust_hold_days-1 PRECEDING AND CURRENT ROW)),
      'Float32'
    ) AS s_thrust,
    CAST(s_risk_off_raw, 'Float64') AS s_risk_off_raw,
    CAST(greatest(0.0, least(1.0, s_risk_off_raw / 3.0)), 'Float32') AS s_risk_off
  FROM macro_raw
),

-- === Asset-specific raw features ===
self_raw AS (
  SELECT
    d.ticker AS ticker,
    d.date AS date,
    (d.close - d.sma200d) / nullIf(d.sma200d, 0) AS s_ma200_self_raw,
    (d.close - d.sma50d) / nullIf(d.sma50d, 0) AS s_ma50_self_raw,
    -- Stack score proxy (0..5-ish): price above 50/200, 50>200, slopes positive
    (
      toUInt8(coalesce(dd.price_above_sma50d, 0))
      + toUInt8(coalesce(dd.price_above_sma200d, 0))
      + toUInt8(coalesce(dd.sma50d_above_sma200d, 0))
      + toUInt8(coalesce(dd.sma50d_slope_20d, 0) > 0)
      + toUInt8(coalesce(dd.sma200d_slope_20d, 0) > 0)
    ) AS ma_stack_score,
    st.smoothed_allocation AS s_stage_self_raw,
    dd.perf_6m AS s_mom_6m_self_raw,
    -- Realized vol proxy: 10d stddev of close-to-close returns
    stddevPop(d.ret_1d) OVER (PARTITION BY d.ticker ORDER BY d.date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS s_rvol_self_raw
  FROM dmlag d
  LEFT JOIN dmd dd ON (dd.ticker = d.ticker AND dd.date = d.date)
  LEFT JOIN sa st ON (st.ticker = d.ticker AND st.date = d.date)
),

-- === Normalize asset-specific features ===
self_norm AS (
  SELECT
    ticker,
    date,

    s_ma200_self_raw,
    CAST(
      1 / (1 + exp(-trend_sigmoid_k * (
        ifNull(
          (s_ma200_self_raw - avg(s_ma200_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_ma200_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_ma200_self,

    s_ma50_self_raw,
    CAST(
      1 / (1 + exp(-trend_sigmoid_k * (
        ifNull(
          (s_ma50_self_raw - avg(s_ma50_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_ma50_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_ma50_self,

    CAST(ma_stack_score, 'Float64') AS s_ma_stack_self_raw,
    CAST(
      1 / (1 + exp(-trend_sigmoid_k * (
        ifNull(
          (toFloat64(ma_stack_score) - avg(toFloat64(ma_stack_score)) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(toFloat64(ma_stack_score)) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN trend_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_ma_stack_self,

    s_stage_self_raw,
    CAST(greatest(0.0, least(1.0, s_stage_self_raw)), 'Float32') AS s_stage_self,

    s_mom_6m_self_raw,
    CAST(
      1 / (1 + exp(-mom_sigmoid_k * (
        ifNull(
          (s_mom_6m_self_raw - avg(s_mom_6m_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN mom_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_mom_6m_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN mom_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_mom_6m_self,

    s_rvol_self_raw,
    CAST(
      1 / (1 + exp(-crisis_sigmoid_k * (
        ifNull(
          (s_rvol_self_raw - avg(s_rvol_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW))
          / nullIf(stddevPop(s_rvol_self_raw) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN crisis_z_days-1 PRECEDING AND CURRENT ROW), 0),
          0.0
        )
      ))),
      'Float32'
    ) AS s_rvol_self
  FROM self_raw
),

-- === Broadcast macro signals to all tickers ===
joined AS (
  SELECT
    s.ticker,
    s.date,
    m.s_ma200_macro_raw,
    m.s_ma200_macro,
    m.s_breadth200_raw,
    m.s_breadth200,
    m.s_breadth50_raw,
    m.s_breadth50,
    m.s_vix_raw,
    m.s_vix,
    m.s_thrust_raw,
    m.s_thrust,
    m.s_risk_off_raw,
    m.s_risk_off,
    s.s_ma200_self_raw,
    s.s_ma200_self,
    s.s_ma50_self_raw,
    s.s_ma50_self,
    s.s_ma_stack_self_raw,
    s.s_ma_stack_self,
    s.s_stage_self_raw,
    s.s_stage_self,
    s.s_mom_6m_self_raw,
    s.s_mom_6m_self,
    s.s_rvol_self_raw,
    s.s_rvol_self
  FROM self_norm s
  LEFT JOIN macro_norm m ON m.date = s.date
)

SELECT
  ticker,
  date,

  s_ma200_macro_raw, s_ma200_macro,
  s_breadth200_raw,  s_breadth200,
  s_breadth50_raw,   s_breadth50,
  s_vix_raw,         s_vix,
  s_thrust_raw,      s_thrust,
  s_risk_off_raw,    s_risk_off,

  s_ma200_self_raw,  s_ma200_self,
  s_ma50_self_raw,   s_ma50_self,
  s_ma_stack_self_raw, s_ma_stack_self,
  s_stage_self_raw,  s_stage_self,
  s_mom_6m_self_raw, s_mom_6m_self,
  s_rvol_self_raw,   s_rvol_self,

  now() AS lastupdated
FROM joined
WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
ORDER BY ticker, date;
