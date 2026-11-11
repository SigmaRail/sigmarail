-- =============================================================================
-- TABLE: screener_forward_returns_daily
-- kind=evaluation layer=L7.5
-- =============================================================================
--
-- PURPOSE: Pre-computed point-in-time forward returns per (ticker, date) plus the
--          active-universe equal-weighted return vector for the same horizons.
--          Used by vera_query_core.alpha_evaluation (Issue #70) to score factor
--          columns (screener_factor_daily et al.) against the un-tilted universe
--          BEFORE committing compute to a LEAN backtest.
--
-- CONVENTIONS:
--   * `close` is the split-adjusted close on signal date t (informational).
--   * Forward returns are computed on the FULLY-ADJUSTED basis
--     (coalesce(closeadj, close)) so dividend drops do not read as negative
--     forward alpha. fwd_ret_Nd = adj[t+N trading bars] / adj[t] - 1.
--   * N counts trading bars (rows), not calendar days.
--   * NULL fwd_ret when the forward bar does not exist (end of history) or
--     the adjusted base is not positive.
--   * ew_universe_ret_Nd = mean of fwd_ret_Nd across all tickers with a
--     computable forward return on that date (the daily-rebalanced
--     equal-weighted active universe; comparator only).
--
-- Populated by: sql/transform/metrics/132-screener-forward-returns-daily.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_forward_returns_daily
(
    `date` Date COMMENT 'Signal date t',
    `ticker` String COMMENT 'Ticker symbol',
    `close` Float32 COMMENT 'Split-adjusted close on date t (informational)',
    `fwd_ret_5d` Nullable(Float32) COMMENT '5-bar forward total return (closeadj basis)',
    `fwd_ret_21d` Nullable(Float32) COMMENT '21-bar forward total return (closeadj basis)',
    `ew_universe_ret_5d` Nullable(Float32) COMMENT 'Equal-weight mean of fwd_ret_5d across active universe on date',
    `ew_universe_ret_21d` Nullable(Float32) COMMENT 'Equal-weight mean of fwd_ret_21d across active universe on date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker)
SETTINGS index_granularity = 8192
COMMENT 'Pre-computed forward returns + EW universe vector for pre-LEAN alpha evaluation (Issue #70)';

-- Managed transform view for target: screener_forward_returns_daily
-- =============================================================================
-- TRANSFORM: Populate screener_forward_returns_daily (evaluation mart, #70)
-- =============================================================================
-- Grain: (date, ticker)
--
-- Forward returns on the fully-adjusted basis (coalesce(closeadj, close)).
-- The price window extends FORWARD past chunk_end_date so leadInFrame() still
-- resolves bars beyond the chunk boundary; the INSERT emits only chunk rows.
-- No lookback padding is needed (forward-only metric).
--
-- ew_universe_ret_* is the cross-sectional mean over emitted rows per date —
-- i.e. the daily-rebalanced equal-weighted active universe (comparator only).
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_forward_returns_daily;

CREATE VIEW IF NOT EXISTS xform_screener_forward_returns_daily (
    date,
    ticker,
    close,
    fwd_ret_5d,
    fwd_ret_21d,
    ew_universe_ret_5d,
    ew_universe_ret_21d,
    lastupdated
)
COMMENT '{"order":132,"target":"screener_forward_returns_daily","sources":["screener_price_tech_daily"],"chunk_size":"3m"}'
AS
WITH
  toDate({chunk_start_date:String}) AS cs,
  toDate({chunk_end_date:String}) AS ce,
  -- +40 calendar days covers >21 trading bars of forward lookahead
  addDays(ce, 40) AS fwd_end,

prices AS (
  SELECT
    ticker,
    date,
    toFloat64(`close`) AS px,
    coalesce(toFloat64(closeadj), toFloat64(`close`)) AS px_adj
  FROM screener_price_tech_daily FINAL
  WHERE date BETWEEN cs AND fwd_end
    AND ticker IN (
      SELECT DISTINCT ticker
      FROM screener_price_tech_daily
      WHERE date BETWEEN cs AND ce
    )
),

fwd AS (
  SELECT
    ticker,
    date,
    px,
    px_adj,
    -- leadInFrame needs a forward-visible frame; past the last seeded bar it
    -- returns 0 for non-Nullable Float64, and the > 0 guards below convert
    -- that sentinel to NULL.
    leadInFrame(px_adj, 5)  OVER (
      PARTITION BY ticker ORDER BY date
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS px_adj_5,
    leadInFrame(px_adj, 21) OVER (
      PARTITION BY ticker ORDER BY date
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS px_adj_21
  FROM prices
),

rets AS (
  SELECT
    date,
    ticker,
    px,
    if(px_adj > 0 AND px_adj_5 > 0,  px_adj_5  / px_adj - 1.0, NULL) AS fwd_ret_5d,
    if(px_adj > 0 AND px_adj_21 > 0, px_adj_21 / px_adj - 1.0, NULL) AS fwd_ret_21d
  FROM fwd
  WHERE date BETWEEN cs AND ce
)

SELECT
  date,
  ticker,
  toFloat32(px) AS close,
  toFloat32(fwd_ret_5d) AS fwd_ret_5d,
  toFloat32(fwd_ret_21d) AS fwd_ret_21d,
  toFloat32(avg(fwd_ret_5d)  OVER (PARTITION BY date)) AS ew_universe_ret_5d,
  toFloat32(avg(fwd_ret_21d) OVER (PARTITION BY date)) AS ew_universe_ret_21d,
  now() AS lastupdated
FROM rets
ORDER BY date, ticker
SETTINGS do_not_merge_across_partitions_select_final = 1;
