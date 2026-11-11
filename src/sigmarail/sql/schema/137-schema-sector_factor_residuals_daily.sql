-- =============================================================================
-- Layer 3 (Backtest): Sector ETF returns with market beta removed
-- =============================================================================
-- Grain: (etf_ticker, window, date)
--
-- Stage-1 input for factor_residuals: rolling OLS of each sector SPDR ETF's
-- excess return on SPY's excess return; sector_orth is the residual (sector
-- return with market beta stripped), used as the orthogonalized second factor.
-- =============================================================================

CREATE TABLE IF NOT EXISTS sector_factor_residuals_daily
(
    `date` Date COMMENT 'Trading session date.',
    `etf_ticker` LowCardinality(String) COMMENT 'Sector SPDR ETF (XLK, XLF, ...).',
    `window` UInt16 COMMENT 'Rolling window length in trading rows (60 | 252).',
    `sector_orth` Float32 COMMENT 'Sector ETF excess return orthogonalized to SPY (rolling OLS residual).',
    `beta_to_market` Float32 COMMENT 'Rolling beta of sector ETF excess vs SPY excess.',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (etf_ticker, window, date)
SETTINGS index_granularity = 8192
COMMENT 'Sector ETF returns with market beta removed (factor-2 input for factor_residuals).';

-- Managed transform view for target: sector_factor_residuals_daily
-- =============================================================================
-- Layer 3 (Backtest): Sector ETF returns orthogonalized to the market
-- =============================================================================
-- Stage 1 of the factor-residual pipeline. For each sector SPDR ETF, run a
-- rolling OLS of the ETF excess return on SPY excess return and store the
-- residual (sector_orth) = market-neutral sector return, plus the rolling beta.
--
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
-- =============================================================================
DROP VIEW IF EXISTS xform_sector_factor_residuals;

CREATE VIEW IF NOT EXISTS xform_sector_factor_residuals (
    date,
    etf_ticker,
    window,
    sector_orth,
    beta_to_market,
    lastupdated
)
COMMENT '{"order":100,"target":"sector_factor_residuals_daily","sources":["asset_returns_daily"],"chunk_size":"6m"}'
AS
WITH
  -- 430 calendar days safely covers the 252-trading-row window at chunk start.
  addDays(toDate({chunk_start_date:String}), -430) AS lookback_start,

  -- Bounded SPY excess series (Float64 to protect the rolling cross-products).
  spy AS (
    SELECT
      date,
      toFloat64(close_ret - cash_ret) AS x
    FROM asset_returns_daily FINAL
    WHERE ticker = 'SPY'
      AND date BETWEEN lookback_start AND toDate({chunk_end_date:String})
  ),

  base AS (
    SELECT
      e.ticker                            AS etf_ticker,
      e.date                              AS date,
      toFloat64(e.close_ret - e.cash_ret) AS y,   -- sector ETF excess return
      spy.x                               AS x    -- SPY excess return (market)
    FROM asset_returns_daily AS e FINAL
    INNER JOIN spy ON spy.date = e.date
    WHERE e.ticker IN ('XLK','XLV','XLF','XLY','XLP','XLI','XLE','XLU','XLRE','XLC','XLB')
      AND e.date BETWEEN lookback_start AND toDate({chunk_end_date:String})
  ),

  win AS (
    SELECT
      etf_ticker, date, y, x, toUInt16(60) AS window,
      count()  OVER f AS n,
      sum(x)   OVER f AS Sx,
      sum(y)   OVER f AS Sy,
      sum(x*x) OVER f AS Sxx,
      sum(x*y) OVER f AS Sxy
    FROM base
    WINDOW f AS (PARTITION BY etf_ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
    UNION ALL
    SELECT
      etf_ticker, date, y, x, toUInt16(252) AS window,
      count()  OVER f AS n,
      sum(x)   OVER f AS Sx,
      sum(y)   OVER f AS Sy,
      sum(x*x) OVER f AS Sxx,
      sum(x*y) OVER f AS Sxy
    FROM base
    WINDOW f AS (PARTITION BY etf_ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
  ),

  fit AS (
    SELECT
      etf_ticker, date, window, y, x,
      (n*Sxy - Sx*Sy) / nullIf(n*Sxx - Sx*Sx, 0)                                AS b,
      (Sy - ((n*Sxy - Sx*Sy) / nullIf(n*Sxx - Sx*Sx, 0)) * Sx) / n              AS a
    FROM win
    WHERE (window = 60 AND n = 60) OR (window = 252 AND n = 252)
  )

SELECT
  date,
  etf_ticker,
  window,
  toFloat32(y - (a + b*x)) AS sector_orth,
  toFloat32(b)             AS beta_to_market,
  now() AS lastupdated
FROM fit
WHERE isNotNull(b)
  AND date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
ORDER BY etf_ticker, window, date
SETTINGS do_not_merge_across_partitions_select_final = 1;
