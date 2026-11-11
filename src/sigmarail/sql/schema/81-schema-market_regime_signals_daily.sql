-- =============================================================================
-- Layer 4 (EXPERIMENTAL v3): Market Regime Signals - daily
-- =============================================================================
-- Grain: One row per trading session.
--
-- Relationship to v1/v2:
--   * Strict column SUPERSET of v2 (which is a superset of v1). v1 vs v2 vs
--     v3 is a three-way JOIN ON date.
--   * Reads weekly from `market_regime_signals` (asymmetric-hysteresis,
--     true-dwell), not v1 or v2.
--   * Keeps the v2 fix: daily `allocation_fraction` / `allocation_tier` are
--     populated from the daily checklist (v1 left these at 0).
--   * Keeps the v2 `effective_*` blend but adds:
--       - 3-of-3 persistence on daily_demote (single-day dips no longer
--         knock the weekly off)
--       - a two-speed promote path: early_promote to min(0.67, weekly+0.33)
--         on ma_stack_score>=4 + spy_above200d + breadth_200d_sma5>=0.50
--         with 2-of-3 persistence; strict breadth_thrust AND ftd still
--         required for full promote to 1.0
--       - 2-of-2 clamp hysteresis on the twitchy breadth<0.40 and VIX-z arms
--       - 3-of-3 asymmetric clamp release (unclamp requires 3 consecutive
--         days of ALL clamp conditions failing)
--       - a fifth clamp arm on risk_off_fast_flags >= 3, also with 2-of-2
--         persistence so it never fires on a single volatile day
--
-- See sql/transform/metrics/81-market-regime-signals-daily.sql for policy.
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_regime_signals_daily
(
    `date` Date COMMENT 'Trading session date (daily grain)',
    `weekly_date` Date COMMENT 'Prior closed weekly regime Monday (toMonday(d) - 7 days); join key into market_regime_signals',
    `weekly_allocation_fraction` Float32 COMMENT 'v3 weekly allocation_fraction from market_regime_signals for weekly_date (0..1)',
    `weekly_allocation_tier` UInt8 COMMENT 'v3 weekly allocation_tier from market_regime_signals for weekly_date (0/33/67/100)',
    `breadth_200d_raw` Float32 COMMENT 'Raw breadth from broad_market_breadth JOIN before staleness guard (0.0 on miss)',
    `breadth_200d` Float32 COMMENT 'Guarded breadth: fraction above 200d SMA; last-good-value fallback when raw is 0 or NULL',
    `breadth_200d_stale_flag` UInt8 DEFAULT 0 COMMENT '1 when breadth_200d was filled from prior non-zero day (populate-order staleness)',
    `breadth_50d` Float32 COMMENT 'Guarded breadth: fraction above 50d SMA (0..1)',
    `spy_close` Float64 COMMENT 'SPY official close for the session.',
    `spy_sma50d` Float64 COMMENT 'SPY 50-day simple moving average (daily_metrics.sma50d)',
    `spy_sma200d` Float64 COMMENT 'SPY 200-day simple moving average (daily_metrics.sma200d)',
    `spy_below200d` UInt8 COMMENT '1 if SPY close < SPY 200d SMA',
    `spy_below200d_3d` UInt8 COMMENT '1 if SPY below 200d for 3 consecutive days',
    `breadth55_days15` UInt8 COMMENT 'Count of days in last 15 with breadth>=0.55',
    `clamp_risk_off` UInt8 COMMENT 'v3: 1 if any daily clamp forces 0% AFTER 2-of-2 persistence on the twitchy arms and 3-of-3 asymmetric release',
    `breadth_thrust` UInt8 COMMENT 'Breadth thrust signal (10D breadth_50d_sma5 change >= 0.18 OR cross above 0.60 from <0.45)',
    `ftd` UInt8 COMMENT 'Follow-through day proxy: SPY daily return >= 1.7% and volume > 20d avg',
    `distribution_count_25d` UInt8 COMMENT 'Count of distribution days in last 25 sessions (ret<=-0.2% and volume > prior day)',
    `spy_above50d` UInt8 COMMENT '1 if SPY close > SPY 50d SMA',
    `spy_above200d` UInt8 COMMENT '1 if SPY close > SPY 200d SMA',
    `ma50_gt_ma200` UInt8 COMMENT '1 if SPY 50d SMA > SPY 200d SMA',
    `ma50_slope_pos` UInt8 COMMENT '1 if SPY 50d SMA slope over last ~5 sessions is positive',
    `ma200_slope_pos` UInt8 COMMENT '1 if SPY 200d SMA slope over last ~5 sessions is positive',
    `ma_stack_score` UInt8 COMMENT '0..5 score: sum of (price>50d, price>200d, 50d>200d, 50d slope+, 200d slope+)',
    `risk_on_fast_flags` UInt8 COMMENT '0..4 count of fast risk-on diagnostics (trend+breadth+volatility signals)',
    `risk_off_fast_flags` UInt8 COMMENT '0..4 count of fast risk-off diagnostics (breadth deterioration / SPY<200d / volatility stress)',
    `allocation_fraction` Float32 COMMENT 'Daily-only checklist fraction (0..1) from clamp/risk-on/intermediate/cautious/risk-off cascade',
    `allocation_tier` UInt8 COMMENT 'Daily allocation_fraction scaled to percent (0/33/67/100)',
    `allocation_reason` String COMMENT 'Human-readable explanation for daily allocation_fraction/tier decision',
    `weekly_allocation_fraction_v3` Float32 DEFAULT 0. COMMENT 'v3-only: forward-filled smoothed weekly fraction from market_regime_signals (alias of weekly_allocation_fraction; kept for clarity in joined v1/v2/v3 reports)',
    `weekly_allocation_tier_v3` UInt8 DEFAULT 0 COMMENT 'v3-only: forward-filled smoothed weekly tier from market_regime_signals (alias of weekly_allocation_tier)',
    `effective_allocation_fraction` Float32 DEFAULT 0. COMMENT 'v3: blended fraction computed in a dedicated CTE (no query-time self-reference). Priority: clamp > persistent daily_demote (3-of-3) > full daily_promote (weekly<1 AND thrust AND ftd) > early_promote (weekly<0.67 AND ma_stack>=4 AND spy>200d AND breadth_sma5>=0.50 with 2-of-3 persistence, cap min(0.67, weekly+0.33)) > weekly.',
    `effective_allocation_tier` UInt8 DEFAULT 0 COMMENT 'v3: round(effective_allocation_fraction*100) computed from the CTE column (fixes v2 query-time self-reference).',
    `effective_source` LowCardinality(String) DEFAULT '' COMMENT 'v3: which arm of the blend won - clamp | daily_demote | daily_promote | early_promote | weekly',
    `daily_demote_streak` UInt8 DEFAULT 0 COMMENT 'v3-only: count of consecutive days (0..N, capped) where daily_fraction < weekly_allocation_fraction. demote_persistence_days (=3) required to fire.',
    `early_promote_flag` UInt8 DEFAULT 0 COMMENT 'v3-only: 1 iff the early-promote path fired on this day (ma_stack>=4 + spy_above200d + breadth_200d_sma5>=0.50 with 2-of-3 persistence AND weekly<0.67). Diagnostic for promote-gate sensitivity.',
    `clamp_release_streak` UInt8 DEFAULT 0 COMMENT 'v3-only: count of consecutive days where ALL clamp conditions are failing (ie. the market looks healthy again). clamp_release_persistence_days (=3) required to release a latched clamp.',
    `clamp_release_eligible` UInt8 DEFAULT 0 COMMENT 'v3-only: 1 iff clamp_release_streak >= clamp_release_persistence_days. Clamp only releases on days where this is 1 (asymmetric release).',
    `tuning_bands` String DEFAULT '' COMMENT 'v3-only: JSON snapshot of the daily tuning CTE constants in effect for this row. compare_regime.py fails loudly if uniqExact(tuning_bands) > 1 per track over the scorecard window.',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `breadth_50d_zweig_thrust` UInt8 DEFAULT 0 COMMENT '1 when breadth_50d was <=0.20 within 10 sessions and is now >=0.40 (Zweig thrust)',
    `clamp_override_zweig_fires` UInt8 DEFAULT 0 COMMENT '1 when clamp_risk_off=1 and breadth_50d_zweig_thrust=1 (diagnostic for clamp exception arm)'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192
COMMENT 'EXPERIMENTAL v3 of market_regime_signals_daily: reads weekly from v3; 3-of-3 daily_demote persistence; two-speed promote; 2-of-2 clamp hysteresis; 3-of-3 asymmetric clamp release; persistent risk_off_fast clamp arm. Parallel to v1 and v2; not read by screener_ratings or daily_screener until the 5-metric scorecard gate is met.';

-- Managed transform view for target: market_regime_signals_daily
-- =============================================================================
-- SigmaRail - experimental v3 Daily Market Regime Model
-- =============================================================================
-- Parallel/experimental version of 86-market-regime-signals-daily-v2.sql.
-- v1 and v2 remain untouched.
--
-- Policy deltas vs v2:
--   1. Reads weekly regime from market_regime_signals (asymmetric-
--      hysteresis + true-dwell). Forward-fills to the trading-day grain
--      via toMonday(d)-7 (same as v2).
--   2. 3-of-3 daily_demote persistence: demote only fires after
--      daily_fraction < weekly_allocation_fraction for
--      demote_persistence_days consecutive days. Single-day dips no longer
--      knock the weekly signal off.
--   3. Two-speed promote with preconditions:
--        * FULL promote to 1.0 requires weekly<1.0 AND breadth_thrust=1
--          AND ftd=1 (same as v2's daily_promote, just with the explicit
--          weekly<1.0 gate).
--        * EARLY promote to min(0.67, weekly+0.33) fires when
--          weekly<0.67 AND ma_stack_score>=early_promote_ma_stack_min AND
--          spy_above200d=1 AND breadth_200d_sma5>=early_promote_breadth_min,
--          with 2-of-3-day persistence so a single strong day doesn't
--          upgrade the blend. This is the "earlier bull turns" arm.
--   4. 2-of-2 clamp hysteresis on the TWITCHY arms: breadth_200d_sma5<0.40
--      and (vix_z_63>=1.0 AND rv_z_252>=0.8). These re-tripped on volatile
--      days in v2 without any real regime stress.
--   5. Leading-indicator clamp arm on risk_off_fast_flags >= 3, also wrapped
--      in 2-of-2 persistence so a single volatile day never clamps on its
--      own.
--   6. 3-of-3 asymmetric clamp release: a latched clamp only releases after
--      clamp_release_persistence_days consecutive days with ALL clamp arm
--      conditions failing. Mathematically equivalent to
--      "sum(armed_today) OVER (ROWS BETWEEN 2 PRECEDING AND CURRENT) >= 1",
--      which we use to keep the SQL window-friendly.
--   7. effective_allocation_fraction is computed in a dedicated CTE
--      (`blends`), NOT as a self-referencing expression inside the final
--      SELECT. v2 self-referenced `effective_allocation_fraction` when
--      deriving `effective_allocation_tier`, which ClickHouse happens to
--      accept today but is fragile.
--   8. tuning_bands JSON snapshot column for compare-script validation.
--
DROP VIEW IF EXISTS xform_market_regime_signals_daily;

CREATE VIEW IF NOT EXISTS xform_market_regime_signals_daily (
    date,
    weekly_date,
    weekly_allocation_fraction,
    weekly_allocation_tier,
    breadth_200d_raw,
    breadth_200d,
    breadth_200d_stale_flag,
    spy_close,
    spy_sma200d,
    spy_below200d,
    spy_below200d_3d,
    breadth55_days15,
    clamp_risk_off,
    breadth_50d,
    breadth_thrust,
    breadth_50d_zweig_thrust,
    ftd,
    distribution_count_25d,
    spy_sma50d,
    spy_above50d,
    spy_above200d,
    ma50_gt_ma200,
    ma50_slope_pos,
    ma200_slope_pos,
    ma_stack_score,
    risk_on_fast_flags,
    risk_off_fast_flags,
    allocation_fraction,
    allocation_tier,
    allocation_reason,
    weekly_allocation_fraction_v3,
    weekly_allocation_tier_v3,
    effective_allocation_fraction,
    effective_allocation_tier,
    effective_source,
    daily_demote_streak,
    early_promote_flag,
    clamp_override_zweig_fires,
    clamp_release_streak,
    clamp_release_eligible,
    tuning_bands
)
COMMENT '{"order":81,"target":"market_regime_signals_daily","sources":["daily_metrics","broad_market_breadth","market_regime_signals","daily_price_sequence"],"chunk_size":"6m"}'
AS
WITH
-- -----------------------------------------------------------------------------
-- Tuning constants. Named CTEs so a single-line edit re-runs the whole policy.
-- -----------------------------------------------------------------------------
-- demote_persistence_days        : days required for daily_demote to fire
-- early_promote_persistence_days : 2-of-3 window for early promote
-- clamp_arm_persistence_days     : rolling days over which twitchy arms are
--                                  summed; require sum == window to fire
-- clamp_release_persistence_days : consecutive quiet days required to release
--                                  a latched clamp
-- risk_off_fast_flags_threshold  : risk_off_fast_flags arm threshold (>=)
date_freshness_check AS (
    SELECT
        date,
        max(lastupdated) AS target_last_updated
    FROM market_regime_signals_daily FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
source_spy AS (
    SELECT
        date,
        max(lastupdated) AS spy_last_updated
    FROM daily_metrics FINAL
    WHERE ticker = 'SPY'
      AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
source_breadth AS (
    SELECT
        date,
        max(last_populated) AS breadth_last_updated
    FROM broad_market_breadth FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY date
),
source_date_freshness_check AS (
    SELECT
        s.date,
        greatest(s.spy_last_updated, coalesce(b.breadth_last_updated, toDateTime(0))) AS source_last_updated
    FROM source_spy s
    LEFT JOIN source_breadth b ON b.date = s.date
),
dates_needing_update AS (
    SELECT
        COALESCE(s.date, t.date) AS date,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1
            WHEN s.source_last_updated > t.target_last_updated THEN 1
            ELSE 0
        END AS needs_update
    FROM source_date_freshness_check s
    FULL OUTER JOIN date_freshness_check t ON s.date = t.date
),
days_all AS (
  SELECT date
  FROM daily_metrics
  WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  GROUP BY date
  ORDER BY date
),
-- Longest rolling window in policy (rv_z_252). Preload before chunk_start so
-- clamp/demote windows at the chunk edge match full-history populate.
policy_spine_dates AS (
  SELECT date
  FROM daily_metrics
  WHERE date BETWEEN addDays(toDate({chunk_start_date:String}), -252) AND toDate({chunk_end_date:String})
  GROUP BY date
  ORDER BY date
),
days AS (
  SELECT date
  FROM daily_metrics
  INNER JOIN dates_needing_update dnu ON daily_metrics.date = dnu.date
  WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    AND (dnu.needs_update = 1 OR {force_refresh:UInt8} = 1)
  GROUP BY date
  ORDER BY date
),
-- Policy spine: preload trading days for rolling windows; INSERT uses `days` only.
map_week AS (
  SELECT d.date, toMonday(d.date) - toIntervalDay(7) AS regime_week_monday
  FROM policy_spine_dates d
),
-- v3 weekly source. Preload extra history for the prior-Monday join.
wk AS (
  SELECT date AS wdate, allocation_fraction AS wk_alloc, allocation_tier AS wk_tier
  FROM market_regime_signals FINAL
  WHERE date BETWEEN toMonday(toDate({chunk_start_date:String})) - toIntervalDay(56)
               AND toMonday(toDate({chunk_end_date:String}))
),
br_spine AS (
  SELECT
    dps.date AS date,
    toFloat32(bmb.pct_above_sma50d) AS breadth_50d_src,
    toFloat32(bmb.pct_above_sma200d) AS breadth_200d_src,
    toFloat32(bmb.pct_above_sma50d_sma5) AS breadth_50d_sma5_src,
    toFloat32(bmb.pct_above_sma200d_sma5) AS breadth_200d_sma5_src
  FROM (
    SELECT date
    FROM daily_price_sequence
    WHERE date BETWEEN addDays(toDate({chunk_start_date:String}), -252) AND toDate({chunk_end_date:String})
    GROUP BY date
  ) AS dps
  LEFT JOIN (
    SELECT
      date,
      pct_above_sma50d,
      pct_above_sma200d,
      pct_above_sma50d_sma5,
      pct_above_sma200d_sma5
    FROM broad_market_breadth FINAL
  ) AS bmb ON bmb.date = dps.date
),
br_guarded AS (
  SELECT
    date,
    coalesce(breadth_200d_src, toFloat32(0)) AS breadth_200d_raw,
    coalesce(
      if(
        coalesce(breadth_200d_src, toFloat32(0)) = toFloat32(0),
        argMaxIf(coalesce(breadth_200d_src, toFloat32(0)), date, coalesce(breadth_200d_src, toFloat32(0)) > toFloat32(0))
          OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        coalesce(breadth_200d_src, toFloat32(0))
      ),
      toFloat32(0)
    ) AS breadth_200d,
    coalesce(
      if(
        coalesce(breadth_50d_src, toFloat32(0)) = toFloat32(0),
        argMaxIf(coalesce(breadth_50d_src, toFloat32(0)), date, coalesce(breadth_50d_src, toFloat32(0)) > toFloat32(0))
          OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        coalesce(breadth_50d_src, toFloat32(0))
      ),
      toFloat32(0)
    ) AS breadth_50d,
    if(
      breadth_200d_sma5_src IS NULL OR breadth_200d_sma5_src = toFloat32(0),
      argMaxIf(breadth_200d_sma5_src, date, breadth_200d_sma5_src > toFloat32(0))
        OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
      breadth_200d_sma5_src
    ) AS breadth_200d_sma5,
    if(
      breadth_50d_sma5_src IS NULL OR breadth_50d_sma5_src = toFloat32(0),
      argMaxIf(breadth_50d_sma5_src, date, breadth_50d_sma5_src > toFloat32(0))
        OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
      breadth_50d_sma5_src
    ) AS breadth_50d_sma5
  FROM br_spine
),
br_feat AS (
  SELECT
    bg.date,
    bg.breadth_200d_raw,
    bg.breadth_200d,
    bg.breadth_50d,
    bg.breadth_50d_sma5,
    bg.breadth_200d_sma5,
    CAST(bg.breadth_200d_raw = toFloat32(0) AND bg.breadth_200d > toFloat32(0), 'UInt8') AS breadth_200d_stale_flag,
    lagInFrame(bg.breadth_50d_sma5, 5) OVER (ORDER BY bg.date) AS breadth_50d_sma5_lag5,
    lagInFrame(bg.breadth_50d_sma5, 10) OVER (ORDER BY bg.date) AS breadth_50d_sma5_lag10,
    lagInFrame(bg.breadth_50d, 1) OVER (ORDER BY bg.date) AS breadth_50d_lag1
  FROM br_guarded bg
),
spy AS (
  SELECT date, `close` AS spy_close, sma50d AS spy_sma50d, sma200d AS spy_sma200d, volume AS spy_volume
  FROM daily_metrics
  WHERE ticker = 'SPY'
    AND date BETWEEN addDays(toDate({chunk_start_date:String}), -252) AND toDate({chunk_end_date:String})
),
vix AS (
  SELECT date, `close` AS vix_close, sma50d AS vix_sma50d, sma200d AS vix_sma200d
  FROM daily_metrics
  WHERE ticker = '^VIX'
    AND date BETWEEN addDays(toDate({chunk_start_date:String}), -252) AND toDate({chunk_end_date:String})
),
vix_feat AS (
  SELECT
    v.date,
    v.vix_close,
    v.vix_sma50d,
    v.vix_sma200d,
    avg(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW) AS vix_mean_63,
    stddevPop(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW) AS vix_std_63,
    (v.vix_close - avg(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW))
      / nullIf(stddevPop(v.vix_close) OVER (ORDER BY v.date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW), 0) AS vix_z_63
  FROM vix v
),
spy_ret AS (
  SELECT
    s.date,
    s.spy_close,
    s.spy_sma50d,
    s.spy_sma200d,
    s.spy_volume,
    (s.spy_close / nullIf(lagInFrame(s.spy_close, 1) OVER (ORDER BY s.date), 0) - 1) AS ret_1d,
    CAST(s.spy_volume > coalesce(lagInFrame(s.spy_volume, 1) OVER (ORDER BY s.date), s.spy_volume), 'UInt8') AS vol_gt_prev,
    lagInFrame(s.spy_sma50d, 5) OVER (ORDER BY s.date) AS lag_sma50d_5,
    lagInFrame(s.spy_sma200d, 5) OVER (ORDER BY s.date) AS lag_sma200d_5
  FROM spy s
),
spy_feat_stage1 AS (
  SELECT
    r.date,
    r.spy_close,
    r.spy_sma50d,
    r.spy_sma200d,
    r.spy_volume,
    r.ret_1d,
    r.vol_gt_prev,
    avg(r.spy_volume) OVER (ORDER BY r.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg20_vol,
    r.lag_sma50d_5,
    r.lag_sma200d_5,
    CAST(coalesce(r.spy_sma50d,0) - coalesce(r.lag_sma50d_5, r.spy_sma50d) > 0, 'UInt8') AS ma50_slope_pos_flag,
    CAST(coalesce(r.spy_sma200d,0) - coalesce(r.lag_sma200d_5, r.spy_sma200d) > 0, 'UInt8') AS ma200_slope_pos_flag,
    stddevPop(r.ret_1d) OVER (ORDER BY r.date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS rv_10d
  FROM spy_ret r
),
spy_feat AS (
  SELECT
    f1.*,
    avg(f1.rv_10d) OVER (ORDER BY f1.date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS rv_mean_252,
    stddevPop(f1.rv_10d) OVER (ORDER BY f1.date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS rv_std_252,
    (f1.rv_10d - avg(f1.rv_10d) OVER (ORDER BY f1.date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW))
      / nullIf(stddevPop(f1.rv_10d) OVER (ORDER BY f1.date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW), 0) AS rv_z_252
  FROM spy_feat_stage1 f1
),
joined AS (
  SELECT
    mw.date AS date,
    mw.regime_week_monday AS weekly_date,
    coalesce(wk.wk_alloc, toFloat32(0)) AS weekly_allocation_fraction,
    coalesce(wk.wk_tier, toUInt8(0))    AS weekly_allocation_tier,
    coalesce(brf.breadth_200d_raw, toFloat32(0)) AS breadth_200d_raw,
    coalesce(brf.breadth_200d, toFloat32(0))     AS breadth_200d,
    coalesce(brf.breadth_200d_stale_flag, toUInt8(0)) AS breadth_200d_stale_flag,
    coalesce(brf.breadth_50d, toFloat32(0))       AS breadth_50d,
    brf.breadth_50d_sma5,
    brf.breadth_200d_sma5,
    brf.breadth_50d_sma5_lag5,
    brf.breadth_50d_sma5_lag10,
    brf.breadth_50d_lag1,
    sf.spy_close,
    sf.spy_sma50d,
    sf.spy_sma200d,
    sf.spy_volume,
    sf.ret_1d,
    sf.vol_gt_prev,
    sf.avg20_vol,
    sf.ma50_slope_pos_flag,
    sf.ma200_slope_pos_flag,
    sf.rv_10d,
    sf.rv_z_252,
    v.vix_close   AS vix_close,
    v.vix_sma50d  AS vix_sma50d,
    v.vix_sma200d AS vix_sma200d,
    vx.vix_z_63   AS vix_z_63,
    CAST(coalesce(sf.spy_close, 0) < coalesce(sf.spy_sma200d, 0), 'UInt8') AS spy_below200d_flag
  FROM map_week mw
  LEFT JOIN wk       ON wk.wdate = mw.regime_week_monday
  LEFT JOIN br_feat brf ON brf.date = mw.date
  LEFT JOIN spy_feat sf ON sf.date = mw.date
  LEFT JOIN vix       v  ON v.date = mw.date
  LEFT JOIN vix_feat  vx ON vx.date = mw.date
),
features AS (
  SELECT
    j.*,
    CAST(sum(spy_below200d_flag) OVER (ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) >= 3, 'UInt8') AS spy_below200d_3d,
    CAST(sum(CAST(coalesce(breadth_200d, 0.0) >= 0.55, 'UInt8'))
         OVER (ORDER BY date ROWS BETWEEN 14 PRECEDING AND CURRENT ROW), 'UInt8') AS breadth55_days15,
    sum(spy_below200d_flag) OVER (ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS below200d_5d_count,
    sum(CAST(((coalesce(vix_close,0) > coalesce(vix_sma50d,0)) AND (coalesce(spy_close,0) < coalesce(spy_sma50d,0))), 'UInt8'))
         OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS vix_spy50_combo_4d,
    CAST(sum(CAST((coalesce(ret_1d,0) <= -0.002) AND (coalesce(vol_gt_prev,0) = 1), 'UInt8'))
         OVER (ORDER BY date ROWS BETWEEN 24 PRECEDING AND CURRENT ROW), 'UInt8') AS distribution_count_25d,
    CAST(
      (CAST(coalesce(spy_close,0) > coalesce(spy_sma200d,0), 'UInt8') = 1)
      AND (ma200_slope_pos_flag = 1)
      AND (CAST(coalesce(spy_close,0) > coalesce(spy_sma50d,0), 'UInt8') = 1)
      AND (ma50_slope_pos_flag = 1)
      AND (coalesce(breadth_50d_sma5, 0.0) >= 0.52)
      AND ((coalesce(breadth_50d_sma5, 0.0) - coalesce(breadth_50d_sma5_lag5, breadth_50d_sma5)) > 0)
      AND ((coalesce(vix_z_63, 0) <= -0.2) OR (coalesce(rv_z_252, 0) <= -0.2))
    , 'UInt8') AS strong_risk_on_flag,
    CAST(
      (coalesce(breadth_50d, 0) >= 0.40)
      AND (
        minIf(
          coalesce(breadth_50d, toFloat32(1.0)),
          coalesce(breadth_50d, toFloat32(0)) > toFloat32(0)
        ) OVER (ORDER BY date ROWS BETWEEN 14 PRECEDING AND CURRENT ROW) <= 0.20
      )
    , 'UInt8') AS breadth_50d_zweig_thrust,
    coalesce(lagInFrame(spy_sma50d, 5) OVER (ORDER BY date), spy_sma50d)  AS spy_sma50d_lag5,
    coalesce(lagInFrame(spy_sma200d, 5) OVER (ORDER BY date), spy_sma200d) AS spy_sma200d_lag5
  FROM joined j
),
-- -----------------------------------------------------------------------------
-- Clamp arms.
-- Two of the v2 clamp arms are instantaneous on twitchy inputs. In v3 those
-- arms are wrapped in 2-of-2 rolling-sum persistence (the arm must fire on
-- TWO consecutive days to count). The two always-persistent arms (below200d
-- 5-day count, VIX>50 + SPY<50 4-of-4) are kept as-is. A fifth arm on
-- risk_off_fast_flags>=3 is added, also with 2-of-2 persistence.
-- -----------------------------------------------------------------------------
-- precursors: compute the v2 risk_off_fast_flags value here so the 2-of-2
-- wrapper window can reference it.
fast_flags AS (
  SELECT
    f.*,
    CAST(
        CAST(coalesce(f.breadth_200d_sma5, 1.0) < 0.48, 'UInt8')
      + f.spy_below200d_3d
      + CAST((coalesce(f.vix_z_63, 0) >= 0.6) AND (coalesce(f.rv_z_252, 0) >= 0.5), 'UInt8')
      + CAST((coalesce(f.vix_close, 0) > coalesce(f.vix_sma50d, 0)) AND (coalesce(f.spy_close, 0) < coalesce(f.spy_sma50d, 0)), 'UInt8')
    , 'UInt8') AS risk_off_fast_flags_v3,
    CAST(
        CAST(coalesce(f.spy_close, 0) > coalesce(f.spy_sma50d,  0), 'UInt8')
      + CAST(coalesce(f.spy_close, 0) > coalesce(f.spy_sma200d, 0), 'UInt8')
      + CAST(coalesce(f.breadth_50d_sma5, 0.0) >= 0.52,             'UInt8')
      + CAST((coalesce(f.vix_z_63, 0) <= -0.2) OR (coalesce(f.rv_z_252, 0) <= -0.2), 'UInt8')
    , 'UInt8') AS risk_on_fast_flags_v3
  FROM features f
),
clamp_arms AS (
  SELECT
    ff.*,
    -- Raw instantaneous arms
    CAST(coalesce(ff.breadth_200d_sma5, 1.0) < 0.40, 'UInt8')                                            AS arm_breadth40_raw,
    CAST(coalesce(ff.vix_z_63, 0) >= 1.0 AND coalesce(ff.rv_z_252, 0) >= 0.8, 'UInt8')                    AS arm_vixz_raw,
    CAST(ff.risk_off_fast_flags_v3 >= 3, 'UInt8')                                                         AS arm_rofast_raw,
    -- 2-of-2 persistence on the three twitchy arms: sum over (today, yesterday) >= 2
    CAST(sum(CAST(coalesce(ff.breadth_200d_sma5, 1.0) < 0.40, 'UInt8'))
         OVER (ORDER BY ff.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) >= 2, 'UInt8') AS arm_breadth40,
    CAST(sum(CAST(coalesce(ff.vix_z_63, 0) >= 1.0 AND coalesce(ff.rv_z_252, 0) >= 0.8, 'UInt8'))
         OVER (ORDER BY ff.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) >= 2, 'UInt8') AS arm_vixz,
    CAST(sum(CAST(ff.risk_off_fast_flags_v3 >= 3, 'UInt8'))
         OVER (ORDER BY ff.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) >= 2, 'UInt8') AS arm_rofast,
    -- Already-persistent arms: unchanged
    CAST(ff.below200d_5d_count >= 5, 'UInt8')      AS arm_below200d5,
    CAST(ff.vix_spy50_combo_4d >= 4, 'UInt8')      AS arm_vixspy50
  FROM fast_flags ff
),
-- Armed today = any arm fires. Clamp with 3-of-3 asymmetric release is
-- equivalent to "any armed day in the last 3 sessions" (today + 2 prior).
clamp_state AS (
  SELECT
    ca.*,
    CAST((arm_breadth40 + arm_vixz + arm_rofast + arm_below200d5 + arm_vixspy50) >= 1, 'UInt8')          AS armed_today,
    CAST(sum(CAST((arm_breadth40 + arm_vixz + arm_rofast + arm_below200d5 + arm_vixspy50) >= 1, 'UInt8'))
         OVER (ORDER BY ca.date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) >= 1, 'UInt8')                 AS clamp_risk_off,
    -- Diagnostic: consecutive quiet days since the last armed day (0 on an
    -- armed day). Implemented as row_number() within an arming-session, minus 1.
    sum(CAST((arm_breadth40 + arm_vixz + arm_rofast + arm_below200d5 + arm_vixspy50) >= 1, 'UInt32'))
         OVER (ORDER BY ca.date) AS arming_session_id
  FROM clamp_arms ca
),
-- Count consecutive quiet days within each arming session.
clamp_session_rows AS (
  SELECT
    cs.*,
    row_number() OVER (PARTITION BY arming_session_id ORDER BY date) AS session_row_num
  FROM clamp_state cs
),
clamp_diagnostics AS (
  SELECT
    csr.*,
    -- clamp_release_streak: number of consecutive quiet days ending today.
    -- 0 on armed day; k on k-th quiet day after the most recent arming.
    toUInt8(least(toUInt64(255),
      if(armed_today = 1,
         toUInt64(0),
         toUInt64(session_row_num - 1))
    )) AS clamp_release_streak,
    CAST(
      (armed_today = 0)
      AND (session_row_num - 1) >= 3
    , 'UInt8') AS clamp_release_eligible
  FROM clamp_session_rows csr
),
-- -----------------------------------------------------------------------------
-- Daily checklist (text reason + numeric fraction). Same cascade as v2 but
-- consumes the persistent `clamp_risk_off` from above.
-- -----------------------------------------------------------------------------
checklist_flags AS (
  SELECT
    cd.*,
    CAST(
      sum(strong_risk_on_flag) OVER (ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) >= 2
    , 'UInt8') AS risk_on_confirmed,
    CAST(coalesce(spy_close,0) > coalesce(spy_sma200d,0), 'UInt8') AS spy_above200d_flag,
    CAST(coalesce(breadth_200d_sma5, 0.0) >= 0.50, 'UInt8') AS breadth_intermediate_flag,
    CAST(
      (coalesce(breadth_50d_sma5, 0) - coalesce(breadth_50d_sma5_lag10, breadth_50d_sma5)) >= 0.18
      OR (coalesce(breadth_50d_lag1, breadth_50d) < 0.45 AND coalesce(breadth_50d, 0) >= 0.60)
    , 'UInt8') AS breadth_thrust,
    CAST(
      coalesce(ret_1d, 0) >= 0.017 AND coalesce(spy_volume, 0) > coalesce(avg20_vol, 0)
    , 'UInt8') AS ftd,
    -- ma_stack score (0..5) precomputed so blends CTE can gate on it.
    CAST(
        CAST(coalesce(spy_close,  0) > coalesce(spy_sma50d,  0), 'UInt8')
      + CAST(coalesce(spy_close,  0) > coalesce(spy_sma200d, 0), 'UInt8')
      + CAST(coalesce(spy_sma50d, 0) > coalesce(spy_sma200d, 0), 'UInt8')
      + CAST(coalesce(spy_sma50d, 0) - spy_sma50d_lag5  > 0,     'UInt8')
      + CAST(coalesce(spy_sma200d,0) - spy_sma200d_lag5 > 0,     'UInt8')
    , 'UInt8')                                                                  AS ma_stack_score
  FROM clamp_diagnostics cd
),
checklist AS (
  SELECT
    cf.*,
    toFloat32(multiIf(
        cf.clamp_risk_off = 1,                                                            0.0,
        cf.risk_on_confirmed = 1,                                                         1.0,
        (cf.spy_above200d_flag = 1) AND (cf.breadth_intermediate_flag = 1),               0.67,
        cf.spy_above200d_flag = 1,                                                        0.33,
        0.0
    )) AS daily_fraction
  FROM checklist_flags cf
),
-- -----------------------------------------------------------------------------
-- Blend CTE (v3). Computes effective_allocation_fraction once so the final
-- SELECT never self-references. Priority:
--   clamp (0%) unless breadth_thrust_clamp_override (Zweig → 20% during clamp)
--   > daily_demote (3-of-3) > full_promote (weekly<1 + thrust + ftd)
--   > early_promote (weekly<0.67 + standard OR thrust fast path) > weekly.
-- -----------------------------------------------------------------------------
demote_sessions AS (
  SELECT
    c.*,
    -- Each non-demote day increments the session id, so consecutive demote
    -- days share one session we can count within.
    sum(CAST(c.daily_fraction >= c.weekly_allocation_fraction, 'UInt32')) OVER (ORDER BY c.date) AS demote_session_id
  FROM checklist c
),
blends AS (
  SELECT
    c.*,
    -- daily_demote_streak: consecutive days daily_fraction < weekly_fraction.
    -- Reset to 0 on non-demote days.
    toUInt8(least(toUInt64(255),
      if(c.daily_fraction < c.weekly_allocation_fraction,
         row_number() OVER (PARTITION BY demote_session_id ORDER BY c.date),
         toUInt64(0))
    )) AS daily_demote_streak,
    CAST(
      (c.breadth_200d_stale_flag = 0)
      AND (c.daily_fraction < c.weekly_allocation_fraction)
      AND (
        if(c.daily_fraction < c.weekly_allocation_fraction,
           row_number() OVER (PARTITION BY demote_session_id ORDER BY c.date),
           toUInt64(0)) >= 3
      )
    , 'UInt8') AS daily_demote_fires,
    -- Early-promote "day condition" (daily snapshot of the promote gate).
    CAST(
      (c.ma_stack_score >= 4)
      AND (c.spy_above200d_flag = 1)
      AND (coalesce(c.breadth_200d_sma5, 0.0) >= 0.50)
    , 'UInt8') AS early_promote_day_flag,
    -- 2-of-3 persistence on the early-promote conditions.
    CAST(
      sum(CAST(
            (c.ma_stack_score >= 4)
            AND (c.spy_above200d_flag = 1)
            AND (coalesce(c.breadth_200d_sma5, 0.0) >= 0.50)
          , 'UInt8'))
          OVER (ORDER BY c.date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) >= 2
    , 'UInt8') AS early_promote_persist
  FROM demote_sessions c
),
blends2 AS (
  SELECT
    b.*,
    CAST(
      (b.ma_stack_score >= 3)
      AND (coalesce(b.breadth_200d_sma5, 0.0) >= 0.45)
      AND (
        max(CAST(b.breadth_thrust = 1, 'UInt8'))
          OVER (ORDER BY b.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) = 1
      )
    , 'UInt8') AS early_promote_thrust_fires,
    -- Full-promote gate: v2 semantics but with explicit weekly<1.0 so the
    -- formula can never demote via this arm.
    CAST(
      (b.breadth_thrust = 1) AND (b.ftd = 1) AND (b.weekly_allocation_fraction < 1.0)
    , 'UInt8') AS full_promote_fires,
    CAST(
      (b.early_promote_persist = 1 AND b.weekly_allocation_fraction < 0.67)
      OR (
        (b.ma_stack_score >= 3)
        AND (coalesce(b.breadth_200d_sma5, 0.0) >= 0.45)
        AND (
          max(CAST(b.breadth_thrust = 1, 'UInt8'))
            OVER (ORDER BY b.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) = 1
        )
        AND b.weekly_allocation_fraction < 0.67
      )
    , 'UInt8') AS early_promote_fires_raw,
    CAST(
      (b.clamp_risk_off = 1) AND (b.breadth_50d_zweig_thrust = 1)
    , 'UInt8') AS clamp_override_zweig_fires
  FROM blends b
),
blend_final AS (
  SELECT
    b2.*,
    -- early_promote_flag is emitted as-is; the blend cascade below also
    -- ensures it only influences the effective fraction when higher-priority
    -- arms don't win.
    b2.early_promote_fires_raw                                                              AS early_promote_flag,
    toFloat32(multiIf(
      b2.clamp_risk_off = 1 AND b2.clamp_override_zweig_fires = 1,                           toFloat32(0.20),
      b2.clamp_risk_off = 1,                                                                 0.0,
      b2.daily_demote_fires = 1,                                                              b2.daily_fraction,
      b2.full_promote_fires = 1,                                                              1.0,
      b2.early_promote_fires_raw = 1,                                                         least(toFloat32(0.67), b2.weekly_allocation_fraction + toFloat32(0.33)),
      b2.weekly_allocation_fraction
    ))                                                                                       AS effective_allocation_fraction,
    CAST(multiIf(
      b2.clamp_risk_off = 1 AND b2.clamp_override_zweig_fires = 1,                          'breadth_thrust_clamp_override',
      b2.clamp_risk_off = 1,                                                                 'clamp',
      b2.daily_demote_fires = 1,                                                              'daily_demote',
      b2.full_promote_fires = 1,                                                              'daily_promote',
      b2.early_promote_fires_raw = 1
        AND b2.early_promote_thrust_fires = 1
        AND b2.weekly_allocation_fraction < 0.67,                                             'early_promote_thrust',
      b2.early_promote_fires_raw = 1,                                                         'early_promote',
      'weekly'
    ) AS LowCardinality(String))                                                             AS effective_source
  FROM blends2 b2
)
SELECT
  bf.date,
  bf.weekly_date,
  bf.weekly_allocation_fraction,
  bf.weekly_allocation_tier,
  bf.breadth_200d_raw,
  bf.breadth_200d,
  bf.breadth_200d_stale_flag,
  bf.spy_close,
  bf.spy_sma200d,
  bf.spy_below200d_flag                                                                                  AS spy_below200d,
  bf.spy_below200d_3d,
  bf.breadth55_days15,
  bf.clamp_risk_off,
  bf.breadth_50d,
  bf.breadth_thrust,
  bf.breadth_50d_zweig_thrust,
  bf.ftd,
  bf.distribution_count_25d,
  bf.spy_sma50d,
  CAST(coalesce(bf.spy_close, 0) > coalesce(bf.spy_sma50d,  0), 'UInt8')                                  AS spy_above50d,
  bf.spy_above200d_flag                                                                                   AS spy_above200d,
  CAST(coalesce(bf.spy_sma50d, 0) > coalesce(bf.spy_sma200d, 0), 'UInt8')                                 AS ma50_gt_ma200,
  bf.ma50_slope_pos_flag                                                                                  AS ma50_slope_pos,
  bf.ma200_slope_pos_flag                                                                                 AS ma200_slope_pos,
  bf.ma_stack_score,
  bf.risk_on_fast_flags_v3                                                                                AS risk_on_fast_flags,
  bf.risk_off_fast_flags_v3                                                                               AS risk_off_fast_flags,
  bf.daily_fraction                                                                                       AS allocation_fraction,
  toUInt8(round(bf.daily_fraction * 100))                                                                 AS allocation_tier,
  multiIf(
      bf.clamp_risk_off = 1,    'clamp: persistent risk-off (2-of-2 arms + 3-of-3 release)',
      bf.risk_on_confirmed = 1, 'risk-on: trend+breadth+vix confirmed 2/3d',
      (bf.spy_above200d_flag = 1) AND (bf.breadth_intermediate_flag = 1),
                                'intermediate: SPY>200d & breadth>=50%',
      bf.spy_above200d_flag = 1,'cautious: SPY>200d',
                                'risk-off'
  )                                                                                                       AS allocation_reason,
  bf.weekly_allocation_fraction                                                                           AS weekly_allocation_fraction_v3,
  bf.weekly_allocation_tier                                                                               AS weekly_allocation_tier_v3,
  bf.effective_allocation_fraction,
  toUInt8(round(bf.effective_allocation_fraction * 100))                                                  AS effective_allocation_tier,
  bf.effective_source,
  bf.daily_demote_streak,
  bf.early_promote_flag,
  bf.clamp_override_zweig_fires,
  bf.clamp_release_streak,
  bf.clamp_release_eligible,
  CAST(
    '{"demote_persistence_days":3,"early_promote_persistence_days":2,"early_promote_persistence_window":3,"early_promote_ma_stack_min":4,"early_promote_breadth_200d_sma5_min":0.5,"early_promote_weekly_max":0.67,"early_promote_thrust_ma_stack_min":3,"early_promote_thrust_breadth_200d_sma5_min":0.45,"early_promote_thrust_lookback_days":5,"breadth_thrust_sma5_delta_min":0.18,"breadth_thrust_cross_low":0.45,"breadth_thrust_cross_high":0.6,"zweig_trough_max":0.2,"zweig_recovery_min":0.4,"zweig_trough_lookback_days":15,"zweig_allocation":0.2,"clamp_arm_persistence_days":2,"clamp_release_persistence_days":3,"risk_off_fast_flags_threshold":3,"breadth_40_clamp":0.4,"below200d_5d_threshold":5,"vix_z_clamp":1.0,"rv_z_clamp":0.8,"vix_spy50_combo_4d_threshold":4}'
    AS String
  )                                                                                                       AS tuning_bands

FROM blend_final bf
INNER JOIN days ins ON ins.date = bf.date
ORDER BY bf.date;
