-- kind=sigmarail_derived layer=L2
-- MRY revenue YoY growth and margin ranks from L1 `mry`.
CREATE TABLE IF NOT EXISTS mry_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Fiscal year end date (aligned with mry.date).',
    `revenue_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY Revenue growth (MRY).',
    `revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRY Revenue YoY Growth (0-100).',
    `revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRY Revenue YoY Growth (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRY Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRY Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for MRY EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for MRY EBITDA Margin (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=mry_derived';

-- Managed transform view for target: mry_derived
-- kind=sigmarail_derived layer=L2
-- Populates mry_derived growth/ranks from L1 mry FINAL (+ tickers).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mry_derived;

CREATE VIEW IF NOT EXISTS xform_mry_derived (
    ticker,
    date,
    revenue_yoy_growth,
    revenue_yoy_growth_industry_rank,
    revenue_yoy_growth_sector_rank,
    netmargin_industry_rank,
    netmargin_sector_rank,
    ebitdamargin_industry_rank,
    ebitdamargin_sector_rank,
    lastupdated
)
COMMENT '{"order":20,"target":"mry_derived","sources":["mry","tickers"],"chunk_size":"6m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        d.ticker,
        count() as target_row_count,
        max(d.lastupdated) as target_last_updated
    FROM mry_derived d FINAL
    WHERE d.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY d.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM mry FINAL
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
mry_history AS (
    SELECT ticker, date, revenue, netmargin, ebitdamargin
    FROM mry FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 400 DAY AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
tickers_info AS (
    SELECT ticker, industry, sector FROM tickers
),
mry_with_yoy AS (
    SELECT
        m.ticker,
        m.date,
        m.revenue,
        m.netmargin,
        m.ebitdamargin,
        CASE WHEN COUNT(m.revenue) OVER w_yoy_1y >= 2
             THEN (m.revenue - lagInFrame(m.revenue, 1) OVER w_yoy_1y) / nullIf(abs(lagInFrame(m.revenue, 1) OVER w_yoy_1y), 0)
             ELSE NULL END as revenue_yoy_growth_calc
    FROM mry_history m
    WINDOW w_yoy_1y AS (PARTITION BY m.ticker ORDER BY m.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
),
mry_with_ranks AS (
    SELECT
        y.*,
        t.industry,
        t.sector,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.revenue_yoy_growth_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.revenue_yoy_growth_calc ASC) * 100, NULL) as revenue_yoy_growth_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.revenue_yoy_growth_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.revenue_yoy_growth_calc ASC) * 100, NULL) as revenue_yoy_growth_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.netmargin ASC) * 100, NULL) as netmargin_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.netmargin ASC) * 100, NULL) as netmargin_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.industry ORDER BY y.ebitdamargin ASC) * 100, NULL) as ebitdamargin_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, t.sector ORDER BY y.ebitdamargin ASC) * 100, NULL) as ebitdamargin_sector_rank_calc
    FROM mry_with_yoy y
    JOIN tickers_info t ON y.ticker = t.ticker
)
SELECT
    ticker,
    date,
    revenue_yoy_growth_calc AS revenue_yoy_growth,
    revenue_yoy_growth_industry_rank_calc AS revenue_yoy_growth_industry_rank,
    revenue_yoy_growth_sector_rank_calc AS revenue_yoy_growth_sector_rank,
    netmargin_industry_rank_calc AS netmargin_industry_rank,
    netmargin_sector_rank_calc AS netmargin_sector_rank,
    ebitdamargin_industry_rank_calc AS ebitdamargin_industry_rank,
    ebitdamargin_sector_rank_calc AS ebitdamargin_sector_rank,
    now() AS lastupdated
FROM mry_with_ranks
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
