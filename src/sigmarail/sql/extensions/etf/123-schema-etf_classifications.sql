-- ETF classification overrides for rollups and screening.
--
-- Core `tickers.sector` / `tickers.industry` may be blank or too broad for funds.
-- Solution: maintain a small curated mapping for ETFs (and other fund-like tickers when needed),
-- then coalesce those values over the core ticker table via `ticker_classification_v1`.
--
-- Overwrite policy: ReplacingMergeTree on `ingested_at` so edits to the mapping replace prior rows.
CREATE TABLE IF NOT EXISTS etf_classifications
(
    `ticker` LowCardinality(String),
    `sector` LowCardinality(String) DEFAULT '',
    `industry` LowCardinality(String) DEFAULT '',
    `market_bucket` LowCardinality(String) DEFAULT '',
    `region_bucket` LowCardinality(String) DEFAULT '',
    `asset_class` LowCardinality(String) DEFAULT '',
    `provider` LowCardinality(String) DEFAULT '',
    `method` LowCardinality(String) DEFAULT '',
    `source_url` String DEFAULT '',
    `ingested_at` DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker)
SETTINGS index_granularity = 8192;

-- Unified classification view: prefer ETF overrides when present, then use core ticker values.
DROP VIEW IF EXISTS ticker_classification_v1;
CREATE VIEW IF NOT EXISTS ticker_classification_v1 AS
SELECT
    t.ticker,
    t.name,
    t.exchange,
    t.currency,
    t.category,
    nullIf(coalesce(nullIf(e.sector, ''), t.sector), '') AS sector,
    nullIf(coalesce(nullIf(e.industry, ''), t.industry), '') AS industry,
    nullIf(e.market_bucket, '') AS market_bucket,
    nullIf(e.region_bucket, '') AS region_bucket,
    nullIf(e.asset_class, '') AS asset_class,
    e.provider,
    e.method,
    e.source_url
FROM tickers AS t
LEFT JOIN etf_classifications AS e
    ON t.ticker = e.ticker;
