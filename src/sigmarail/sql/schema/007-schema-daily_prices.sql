-- kind=vendor_copy layer=L1
-- Unified equity+fund OHLCV spine (sep routed by tickers.table=SEP, sfp by SFP).
-- Episode B: L3 (01/03) may later read this instead of re-joining L0.
CREATE TABLE IF NOT EXISTS daily_prices
(
    `ticker` String COMMENT 'kind=vendor_copy layer=L1 ticker',
    `date` Date COMMENT 'kind=vendor_copy layer=L1 session date',
    `lastupdated` DateTime('America/New_York') DEFAULT now(),
    `source_table` LowCardinality(String) COMMENT 'SEP or SFP',
    `open` Nullable(Float64) COMMENT 'Split-adjusted open',
    `high` Nullable(Float64) COMMENT 'Split-adjusted high',
    `low` Nullable(Float64) COMMENT 'Split-adjusted low',
    `close` Nullable(Float64) COMMENT 'Split-adjusted close',
    `volume` Nullable(Float64) COMMENT 'Split-adjusted volume',
    `closeadj` Nullable(Float64) COMMENT 'Fully adjusted close',
    `closeunadj` Nullable(Float64) COMMENT 'Unadjusted close'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_prices
-- kind=vendor_copy layer=L1
-- Episode B: unified OHLCV from sep/sfp routed by tickers.table (same policy as 01).
--
DROP VIEW IF EXISTS xform_daily_prices;

CREATE VIEW IF NOT EXISTS xform_daily_prices (
    ticker,
    date,
    lastupdated,
    source_table,
    open,
    high,
    low,
    close,
    volume,
    closeadj,
    closeunadj
)
COMMENT '{"order":0,"target":"daily_prices","sources":["sep","tickers","sfp"],"chunk_size":"1m"}'
AS
SELECT
    p.ticker,
    p.date,
    now() AS lastupdated,
    'SEP' AS source_table,
    p.open, p.high, p.low, p.close, p.volume, p.closeadj, p.closeunadj
FROM sep AS p FINAL
INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
WHERE p.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
UNION ALL
SELECT
    p.ticker,
    p.date,
    now() AS lastupdated,
    'SFP' AS source_table,
    p.open, p.high, p.low, p.close, p.volume, p.closeadj, p.closeunadj
FROM sfp AS p FINAL
INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
WHERE p.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String});
