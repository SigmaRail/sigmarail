-- kind=vendor_copy layer=L1
-- Spine copy of Sharadar `daily` valuation (PE/PB/mktcap/…). Episode B.
CREATE TABLE IF NOT EXISTS daily_valuation
(
    `ticker` String COMMENT 'kind=vendor_copy layer=L1',
    `date` Date COMMENT 'kind=vendor_copy layer=L1',
    `lastupdated` DateTime('America/New_York') DEFAULT now(),
    `ev` Nullable(Float64),
    `evebit` Nullable(Float64),
    `evebitda` Nullable(Float64),
    `marketcap` Nullable(Float64),
    `pb` Nullable(Float64),
    `pe` Nullable(Float64),
    `ps` Nullable(Float64)
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_valuation
-- kind=vendor_copy layer=L1
-- Episode B: copy Sharadar daily valuation onto (ticker, date) spine.
--
DROP VIEW IF EXISTS xform_daily_valuation;

CREATE VIEW IF NOT EXISTS xform_daily_valuation (
    ticker,
    date,
    lastupdated,
    ev,
    evebit,
    evebitda,
    marketcap,
    pb,
    pe,
    ps
)
COMMENT '{"order":0,"target":"daily_valuation","sources":["daily"],"chunk_size":"1m"}'
AS
SELECT
    d.ticker,
    d.date,
    now() AS lastupdated,
    d.ev, d.evebit, d.evebitda, d.marketcap, d.pb, d.pe, d.ps
FROM daily AS d FINAL
WHERE d.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String});
