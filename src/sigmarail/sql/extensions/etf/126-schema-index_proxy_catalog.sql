-- Index proxy catalog: maps sectors and market buckets to tradable ETF/index proxies (SPY, XLK, …).
-- Used by `ticker_index_proxy_v1` and `daily_index_proxy_sentiment`.

CREATE TABLE IF NOT EXISTS index_proxy_catalog
(
    `proxy_ticker` LowCardinality(String),
    `proxy_type` LowCardinality(String),
    `bucket_key` LowCardinality(String),
    `priority` UInt8 DEFAULT 1,
    `provider` LowCardinality(String) DEFAULT 'unspecified',
    `notes` String DEFAULT '',
    `ingested_at` DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (proxy_type, bucket_key, proxy_ticker)
SETTINGS index_granularity = 8192;

-- Core sector labels -> normalized labels shared with ETF sector-weight snapshots.
DROP VIEW IF EXISTS sector_normalized_v1;
CREATE VIEW IF NOT EXISTS sector_normalized_v1 AS
SELECT
    ticker,
    sector AS sector_raw,
    multiIf(
        sector = 'Healthcare', 'Health Care',
        sector = 'Financial Services', 'Financials',
        sector = 'Consumer Cyclical', 'Consumer Cyclical',
        sector = 'Consumer Defensive', 'Consumer Defensive',
        sector = 'Communication Services', 'Communication Services',
        sector = 'Basic Materials', 'Basic Materials',
        sector = 'Real Estate', 'Real Estate',
        sector = '', '',
        sector
    ) AS sector_norm
FROM tickers;

-- Per-ticker index proxy memberships (many-to-many).
DROP VIEW IF EXISTS ticker_index_proxy_v1;
CREATE VIEW IF NOT EXISTS ticker_index_proxy_v1 AS
SELECT
    t.ticker AS ticker,
    c.proxy_ticker AS proxy_ticker,
    c.proxy_type AS proxy_type,
    'direct' AS mapping_kind
FROM tickers AS t
INNER JOIN index_proxy_catalog AS c
    ON c.proxy_ticker = t.ticker
UNION ALL
SELECT
    t.ticker AS ticker,
    c.proxy_ticker AS proxy_ticker,
    c.proxy_type AS proxy_type,
    'sector' AS mapping_kind
FROM tickers AS t
INNER JOIN sector_normalized_v1 AS s
    ON s.ticker = t.ticker
INNER JOIN index_proxy_catalog AS c
    ON c.proxy_type = 'sector'
   AND c.bucket_key = s.sector_norm
WHERE s.sector_norm != ''
UNION ALL
SELECT
    t.ticker AS ticker,
    c.proxy_ticker AS proxy_ticker,
    c.proxy_type AS proxy_type,
    'market' AS mapping_kind
FROM tickers AS t
INNER JOIN index_proxy_catalog AS c
    ON c.proxy_type = 'market'
   AND c.bucket_key = 'US_domestic'
WHERE t.category LIKE 'Domestic Common Stock%';
