-- =============================================================================
-- Layer 3 (Backtest): Per-stock rolling factor-adjusted alpha / residual
-- =============================================================================
-- Grain: (date, ticker, window)
--
-- Two-factor rolling OLS per ticker: excess_ret = alpha
--   + beta_mkt * SPY_excess
--   + beta_sector * sector_orth   (market-orthogonalized sector, see sector_factor_residuals_daily)
--   + epsilon
--
-- alpha is the regression intercept (Jensen's alpha): the return left over
-- after the known factors are stripped. residual is today's epsilon_t.
-- NOTE: alpha_tstat is plain OLS, NOT Newey-West/HAC (ClickHouse has no native
-- rolling HAC). Re-check significance out-of-DB before any live use.
-- =============================================================================

CREATE TABLE IF NOT EXISTS factor_residuals
(
    `date` Date COMMENT 'Trading session date.',
    `ticker` LowCardinality(String) COMMENT 'Equity identifier.',
    `window` UInt16 COMMENT 'Rolling window length in trading rows (60 | 252).',
    `residual` Float32 COMMENT 'Today\'s unexplained excess return (epsilon_t).',
    `rolling_alpha` Float32 COMMENT 'Regression intercept over the window (per-day excess units).',
    `alpha_tstat` Float32 COMMENT 'Plain-OLS t-stat on alpha (NOT HAC; see episode 2026-06-09-factor-residuals).',
    `beta_mkt` Float32 COMMENT 'Beta vs SPY excess.',
    `beta_sector` Float32 COMMENT 'Beta vs market-orthogonalized sector excess.',
    `r2` Float32 COMMENT 'Window R-squared (low is healthy for return prediction).',
    `n_obs` UInt16 COMMENT 'Observations used in the window (= window).',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker, window)
SETTINGS index_granularity = 8192
COMMENT 'Per-stock rolling factor-adjusted alpha/residual (market + orthogonalized sector).';

-- Managed transform view for target: factor_residuals
-- =============================================================================
-- Layer 3 (Backtest): Per-stock rolling factor-adjusted alpha / residual
-- =============================================================================
-- Stage 2 of the factor-residual pipeline. Two-factor rolling OLS per ticker:
--   excess_ret = alpha + beta_mkt * SPY_excess + beta_sector * sector_orth + eps
-- where sector_orth (market-orthogonalized sector return) comes from stage 1
-- (sector_factor_residuals_daily). Closed-form 2x2 OLS via rolling window sums.
--
-- alpha (intercept) is the candidate edge; residual is today's eps_t.
-- alpha_tstat is plain OLS, NOT Newey-West/HAC.
--
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
-- =============================================================================
DROP VIEW IF EXISTS xform_factor_residuals;

CREATE VIEW IF NOT EXISTS xform_factor_residuals (
    date,
    ticker,
    window,
    residual,
    rolling_alpha,
    alpha_tstat,
    beta_mkt,
    beta_sector,
    r2,
    n_obs,
    lastupdated
)
COMMENT '{"order":101,"target":"factor_residuals","sources":["asset_returns_daily","tickers","sector_factor_residuals_daily"],"chunk_size":"6m"}'
AS
WITH
  addDays(toDate({chunk_start_date:String}), -430) AS lookback_start,

  -- Bounded SPY excess series (Float64 to protect the rolling cross-products).
  spy AS (
    SELECT
      date,
      toFloat64(close_ret - cash_ret) AS x1
    FROM asset_returns_daily FINAL
    WHERE ticker = 'SPY'
      AND date BETWEEN lookback_start AND toDate({chunk_end_date:String})
  ),

  base AS (
    SELECT
      r.ticker                            AS ticker,
      r.date                              AS date,
      sfr.window                          AS window,
      toFloat64(r.close_ret - r.cash_ret) AS y,    -- stock excess return
      spy.x1                              AS x1,   -- market excess (SPY)
      toFloat64(sfr.sector_orth)          AS x2    -- market-orthogonalized sector excess
    FROM asset_returns_daily AS r FINAL
    INNER JOIN tickers AS t FINAL
      ON t.ticker = r.ticker
    INNER JOIN spy ON spy.date = r.date
    INNER JOIN sector_factor_residuals_daily AS sfr FINAL
      ON sfr.date = r.date
     AND sfr.date BETWEEN lookback_start AND toDate({chunk_end_date:String})
     AND sfr.etf_ticker = multiIf(
           t.sector = 'Technology',             'XLK',
           t.sector = 'Healthcare',             'XLV',
           t.sector = 'Financial Services',     'XLF',
           t.sector = 'Consumer Cyclical',      'XLY',
           t.sector = 'Consumer Defensive',     'XLP',
           t.sector = 'Industrials',            'XLI',
           t.sector = 'Energy',                 'XLE',
           t.sector = 'Utilities',              'XLU',
           t.sector = 'Real Estate',            'XLRE',
           t.sector = 'Communication Services', 'XLC',
           t.sector = 'Basic Materials',        'XLB',
           '')
    WHERE t.isdelisted = 'N'
      AND t.category   = 'Domestic Common Stock'
      AND t.sector    != ''
      AND toUInt8OrZero(extract(t.scalemarketcap, '^(\\d+)')) >= 3   -- Small-cap and above
      AND r.date BETWEEN lookback_start AND toDate({chunk_end_date:String})
  ),

  win AS (
    SELECT
      ticker, date, toUInt16(60) AS window, y, x1, x2,
      count()    OVER f AS n,
      sum(y)     OVER f AS Sy,
      sum(x1)    OVER f AS Sx1,
      sum(x2)    OVER f AS Sx2,
      sum(y*y)   OVER f AS Syy,
      sum(x1*x1) OVER f AS Sx1x1,
      sum(x2*x2) OVER f AS Sx2x2,
      sum(x1*x2) OVER f AS Sx1x2,
      sum(x1*y)  OVER f AS Sx1y,
      sum(x2*y)  OVER f AS Sx2y
    FROM (SELECT * FROM base WHERE window = 60)
    WINDOW f AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
    UNION ALL
    SELECT
      ticker, date, toUInt16(252) AS window, y, x1, x2,
      count()    OVER f AS n,
      sum(y)     OVER f AS Sy,
      sum(x1)    OVER f AS Sx1,
      sum(x2)    OVER f AS Sx2,
      sum(y*y)   OVER f AS Syy,
      sum(x1*x1) OVER f AS Sx1x1,
      sum(x2*x2) OVER f AS Sx2x2,
      sum(x1*x2) OVER f AS Sx1x2,
      sum(x1*y)  OVER f AS Sx1y,
      sum(x2*y)  OVER f AS Sx2y
    FROM (SELECT * FROM base WHERE window = 252)
    WINDOW f AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
  ),

  coef AS (
    SELECT
      ticker, date, window, y, x1, x2, n,
      Sy/n  AS my, Sx1/n AS m1, Sx2/n AS m2,
      Sx1x1 - Sx1*Sx1/n AS cxx1,
      Sx2x2 - Sx2*Sx2/n AS cxx2,
      Sx1x2 - Sx1*Sx2/n AS cx12,
      Sx1y  - Sx1*Sy/n  AS c1y,
      Sx2y  - Sx2*Sy/n  AS c2y,
      Syy   - Sy*Sy/n   AS cyy,
      (cxx1*cxx2 - cx12*cx12) AS det
    FROM win
    WHERE (window = 60 AND n = 60) OR (window = 252 AND n = 252)
  )

SELECT
  date,
  ticker,
  window,
  toFloat32(y - (alpha + b1*x1 + b2*x2)) AS residual,
  toFloat32(alpha)                       AS rolling_alpha,
  toFloat32(alpha / sqrt(varAlpha))      AS alpha_tstat,
  toFloat32(b1)                          AS beta_mkt,
  toFloat32(b2)                          AS beta_sector,
  toFloat32(1 - rss/cyy)                 AS r2,
  toUInt16(n)                            AS n_obs,
  now() AS lastupdated
FROM
(
  SELECT
    date, ticker, window, y, x1, x2, n, cyy, det,
    (cxx2*c1y - cx12*c2y)/det AS b1,
    (cxx1*c2y - cx12*c1y)/det AS b2,
    my - ((cxx2*c1y - cx12*c2y)/det)*m1 - ((cxx1*c2y - cx12*c1y)/det)*m2 AS alpha,
    cyy - ((cxx2*c1y - cx12*c2y)/det)*c1y - ((cxx1*c2y - cx12*c1y)/det)*c2y AS rss,
    rss/(n-3) AS s2,
    s2 * (1.0/n + (cxx2*m1*m1 - 2*cx12*m1*m2 + cxx1*m2*m2)/det) AS varAlpha
  FROM coef
  WHERE det != 0
)
WHERE varAlpha > 0 AND cyy > 0
ORDER BY date, ticker, window
SETTINGS do_not_merge_across_partitions_select_final = 1;
