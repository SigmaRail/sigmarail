-- External ETF holdings and sector-weight snapshots.

CREATE TABLE IF NOT EXISTS etf_holdings_snapshot
(
    `etf_ticker` LowCardinality(String),
    `as_of_date` Date,
    `holding_symbol` String,
    `holding_name` String DEFAULT '',
    `weight` Float32,
    `provider` LowCardinality(String) DEFAULT 'unspecified',
    `fetched_at` DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(fetched_at)
PARTITION BY toYYYYMM(as_of_date)
ORDER BY (etf_ticker, as_of_date, holding_symbol)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS etf_sector_weights_snapshot
(
    `etf_ticker` LowCardinality(String),
    `as_of_date` Date,
    `sector` LowCardinality(String),
    `weight` Float32,
    `provider` LowCardinality(String) DEFAULT 'unspecified',
    `fetched_at` DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(fetched_at)
PARTITION BY toYYYYMM(as_of_date)
ORDER BY (etf_ticker, as_of_date, sector)
SETTINGS index_granularity = 8192;
