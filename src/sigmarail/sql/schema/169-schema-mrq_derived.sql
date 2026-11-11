-- kind=sigmarail_derived layer=L2
-- MRQ margin industry/sector ranks from L1 `mrq` (SF1 dimension MRQ).
CREATE TABLE IF NOT EXISTS mrq_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Quarter end date (aligned with mrq.date).',
    `grossmargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRQ Gross Margin (0-100).',
    `grossmargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRQ Gross Margin (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRQ Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRQ Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRQ EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRQ EBITDA Margin (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=mrq_derived';

-- Managed transform view for target: mrq_derived
-- kind=sigmarail_derived layer=L2
-- Populates mrq_derived margin ranks from L1 mrq (+ tickers).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mrq_derived;

CREATE VIEW IF NOT EXISTS xform_mrq_derived (
    ticker,
    date,
    grossmargin_industry_rank,
    grossmargin_sector_rank,
    netmargin_industry_rank,
    netmargin_sector_rank,
    ebitdamargin_industry_rank,
    ebitdamargin_sector_rank,
    lastupdated
)
COMMENT '{"order":18,"target":"mrq_derived","sources":["mrq","tickers"],"chunk_size":"6m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        d.ticker,
        count() as target_row_count,
        max(d.lastupdated) as target_last_updated
    FROM mrq_derived d FINAL
    WHERE d.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY d.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM mrq FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 400 DAY AND {chunk_end_date:String}
    GROUP BY ticker
),
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1
            WHEN s.source_row_count > t.target_row_count THEN 1
            WHEN s.source_last_updated > t.target_last_updated THEN 1
            ELSE 0
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
),
mrq_filtered AS (
    SELECT ticker, date, grossmargin, netmargin, ebitdamargin
    FROM mrq FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 400 DAY AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
tickers_info AS (
    SELECT ticker, industry, sector FROM tickers
),
mrq_with_ranks AS (
    SELECT
        m.ticker,
        m.date,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.grossmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.grossmargin ASC) * 100, NULL) as grossmargin_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.grossmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.grossmargin ASC) * 100, NULL) as grossmargin_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.netmargin ASC) * 100, NULL) as netmargin_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.netmargin ASC) * 100, NULL) as netmargin_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.industry ORDER BY m.ebitdamargin ASC) * 100, NULL) as ebitdamargin_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY m.date, t.sector ORDER BY m.ebitdamargin ASC) * 100, NULL) as ebitdamargin_sector_rank_calc
    FROM mrq_filtered m
    JOIN tickers_info t ON m.ticker = t.ticker
)
SELECT
    ticker,
    date,
    grossmargin_industry_rank_calc AS grossmargin_industry_rank,
    grossmargin_sector_rank_calc AS grossmargin_sector_rank,
    netmargin_industry_rank_calc AS netmargin_industry_rank,
    netmargin_sector_rank_calc AS netmargin_sector_rank,
    ebitdamargin_industry_rank_calc AS ebitdamargin_industry_rank,
    ebitdamargin_sector_rank_calc AS ebitdamargin_sector_rank,
    now() AS lastupdated
FROM mrq_with_ranks
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
