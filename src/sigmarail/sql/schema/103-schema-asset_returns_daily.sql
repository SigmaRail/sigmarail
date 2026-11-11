-- =============================================================================
-- Layer 3 (Backtest): Per-asset daily returns cache
-- =============================================================================

CREATE TABLE IF NOT EXISTS asset_returns_daily
(
    `ticker` String COMMENT 'Asset identifier (equity/ETF/index).',
    `date` Date COMMENT 'Trading session date (daily grain).',
    `close_ret` Float32 COMMENT 'Close-to-close return for ticker on date (t / t-1 - 1).',
    `cash_ret` Float32 COMMENT 'Cash proxy return for the same date (BIL close-to-close); 0 if unavailable.',
    `cash_source` LowCardinality(String) COMMENT 'cash_ret provenance: bil | zero',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Daily close-to-close returns per ticker plus matched cash return series for regime backtests.';

-- Managed transform view for target: asset_returns_daily
-- =============================================================================
-- Layer 3 (Backtest): Populate asset_returns_daily
-- =============================================================================
-- Grain: (ticker, date)
--
-- close_ret: close-to-close return (t / t-1 - 1)
-- cash_ret: BIL close-to-close return, broadcast to all tickers; 0 when unavailable.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_asset_returns_daily;

CREATE VIEW IF NOT EXISTS xform_asset_returns_daily (
    ticker,
    date,
    close_ret,
    cash_ret,
    cash_source,
    lastupdated
)
COMMENT '{"order":98,"target":"asset_returns_daily","sources":["daily_metrics"],"chunk_size":"6m"}'
AS
WITH
  -- Minimal lookback for lag() inside a chunk
  addDays(toDate({chunk_start_date:String}), -5) AS lookback_start,

  dm AS (
    SELECT
      ticker,
      date,
      toFloat64(`close`) AS close
    FROM daily_metrics FINAL
    WHERE date BETWEEN lookback_start AND toDate({chunk_end_date:String})
  ),

  dm_ret AS (
    SELECT
      ticker,
      date,
      toFloat32(close / nullIf(lagInFrame(close, 1) OVER (PARTITION BY ticker ORDER BY date), 0) - 1) AS close_ret
    FROM dm
  ),

  bil AS (
    SELECT
      date,
      close_ret AS bil_close_ret
    FROM dm_ret
    WHERE ticker = 'BIL'
  )

SELECT
  r.ticker,
  r.date,
  r.close_ret,
  toFloat32(ifNull(b.bil_close_ret, 0.0)) AS cash_ret,
  CAST(if(isNull(b.bil_close_ret), 'zero', 'bil') AS LowCardinality(String)) AS cash_source,
  now() AS lastupdated
FROM dm_ret r
LEFT JOIN bil b ON b.date = r.date
WHERE r.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
ORDER BY ticker, date;
