-- Defines the schema for the broad_market_constituents table.
-- This table stores a daily record for each ticker that meets the broad market criteria on that specific day.
CREATE TABLE IF NOT EXISTS broad_market_constituents
(
    `date` Date COMMENT 'The specific date the ticker met the criteria.',
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol.'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: broad_market_constituents
-- Populates sigmarail.broad_market_constituents with daily records of tickers meeting broad market criteria.
-- This transform runs once for the entire dataset (no chunking).
--
-- NORMALIZATION POLICY (Option A):
--   - Constituent inclusion thresholds (min price, dollar-volume ADV) use split-adjusted sep.close.
--   - This keeps the investable universe definition aligned with the same price series used for technical signals.
--
DROP VIEW IF EXISTS xform_broad_market_constituents;

CREATE VIEW IF NOT EXISTS xform_broad_market_constituents (
    date,
    ticker
)
COMMENT '{"order":0,"target":"broad_market_constituents","sources":["sep","tickers"],"source_timestamp_column":"lastupdated","target_timestamp_column":"none","max_partitions_per_insert_block":400}'
AS
WITH volume_20d AS (
    SELECT
        ticker,
        date,
        `close`,
        volume,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_vol_20d,
        avg(`close` * volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20_dollar
    FROM sep
)
SELECT
    v.date,
    v.ticker
FROM volume_20d AS v
JOIN tickers AS t ON v.ticker = t.ticker
WHERE
    v.`close` >= 10.0
    AND v.avg_vol_20d >= 400000
    AND v.adv20_dollar >= 20000000
    AND t.exchange IN ('NASDAQ', 'NYSE', 'NYSE ARCA', 'NYSE MKT', 'BATS')
    AND t.currency = 'USD'
    AND NOT startsWith(v.ticker, '^')
    AND lowerUTF8(t.category) LIKE '%domestic%'  -- IBD: Exclude Canadian stocks, focus on US market
    AND lowerUTF8(t.relatedtickers) NOT LIKE '%etf%'
    AND toDateOrNull(t.firstpricedate) > CAST('1000-01-01' AS Date) AND v.date >= toDateOrNull(t.firstpricedate)
    AND toDateOrNull(t.lastpricedate) > CAST('1000-01-01' AS Date) AND v.date <= toDateOrNull(t.lastpricedate)
GROUP BY v.date, v.ticker
ORDER BY v.date, v.ticker;
