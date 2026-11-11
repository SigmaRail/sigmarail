-- Point-in-time ticker classification (SigmaRail core).
-- `tickers` is current-state (ORDER BY permaticker; FINAL = today's attributes),
-- so joining it stamps today's sector/industry onto all history. This table
-- snapshots the Sharadar classification labels per (ticker, date) so consumers
-- can ASOF-join for the last-known label at any historical date.
CREATE TABLE IF NOT EXISTS ticker_classification_daily
(
    `ticker` LowCardinality(String) COMMENT 'Ticker symbol.',
    `date` Date COMMENT 'Snapshot date. The 1970-01-01 seed row carries the earliest known classification (current-state backfill); daily snapshots from deployment onward are true point-in-time.',
    `sector` String COMMENT 'Sector: SIC-based classification approximating GICS (from tickers.sector).',
    `industry` String COMMENT 'Industry: SIC-based classification approximating GICS (from tickers.industry).',
    `famaindustry` String COMMENT 'Fama-French industry classification (from tickers.famaindustry).',
    `sicsector` String COMMENT 'SIC sector (from tickers.sicsector).',
    `sicindustry` String COMMENT 'SIC industry (from tickers.sicindustry).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: ticker_classification_daily
-- =============================================================================
-- Daily point-in-time ticker classification snapshot (SigmaRail core).
-- Populates ticker_classification_daily for a given date chunk.
-- Expects parameters: chunk_start_date, chunk_end_date
--
-- Emits one row per ticker per trading date present in daily_metrics, carrying
-- the current tickers classification. Snapshots accrue PIT going forward; the
-- 1970-01-01 backfill seed covers history before deployment. ~12k rows/day.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_ticker_classification_daily;

CREATE VIEW IF NOT EXISTS xform_ticker_classification_daily (
    ticker,
    date,
    sector,
    industry,
    famaindustry,
    sicsector,
    sicindustry,
    lastupdated
)
COMMENT '{"order":2,"target":"ticker_classification_daily","sources":["daily_metrics","tickers"],"chunk_size":"1m"}'
AS
WITH
-- Seed current Sharadar classification at the beginning of the timeline so an
-- ASOF lookup has a deterministic fallback before the first materialized day.
seed_rows AS (
    SELECT
        t.ticker AS ticker,
        toDate('1970-01-01') AS date,
        t.sector AS sector,
        t.industry AS industry,
        t.famaindustry AS famaindustry,
        t.sicsector AS sicsector,
        t.sicindustry AS sicindustry,
        now() AS lastupdated
    FROM tickers AS t FINAL
    LEFT ANTI JOIN (
        SELECT ticker
        FROM ticker_classification_daily FINAL
        WHERE date = toDate('1970-01-01')
    ) AS seeded USING (ticker)
),
-- Freshness: only dates whose daily_metrics data is newer than the snapshot.
updates_dates AS (
    SELECT COALESCE(s.date, t.date) AS date
    FROM (
        SELECT date, max(lastupdated) AS source_last_updated
        FROM daily_metrics FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) s
    FULL OUTER JOIN (
        SELECT date, max(lastupdated) AS target_last_updated
        FROM ticker_classification_daily FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        GROUP BY date
    ) t ON s.date = t.date
    WHERE t.target_last_updated IS NULL
       OR s.source_last_updated > t.target_last_updated
)
SELECT
    dm.ticker AS ticker,
    dm.date AS date,
    t.sector AS sector,
    t.industry AS industry,
    t.famaindustry AS famaindustry,
    t.sicsector AS sicsector,
    t.sicindustry AS sicindustry,
    now() AS lastupdated
FROM daily_metrics dm FINAL
INNER JOIN updates_dates ud ON dm.date = ud.date
INNER JOIN tickers t FINAL ON dm.ticker = t.ticker
WHERE dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND NOT startsWith(dm.ticker, '^')
UNION ALL
SELECT ticker, date, sector, industry, famaindustry, sicsector, sicindustry, lastupdated
FROM seed_rows;
