-- kind=sigmarail_derived layer=L2
-- ARY growth / CAGR / acceleration / industry-sector ranks from L1 `ary`.
CREATE TABLE IF NOT EXISTS ary_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Fiscal year end date (aligned with ary.date).',
    `revenue_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY Revenue growth (ARY).',
    `eps_growth_yoy` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY EPS growth (ARY).',
    `revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for ARY Revenue YoY Growth (0-100).',
    `revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for ARY Revenue YoY Growth (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for ARY Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for ARY Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for ARY EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for ARY EBITDA Margin (0-100).',
    `eps_growth_3y_cagr` Nullable(Float64) COMMENT 'kind=sigmarail_derived. 3-Year EPS CAGR (ARY).',
    `eps_acceleration_fy` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 1 if current ARY YoY EPS growth > prior year.',
    `revenue_growth_3y_cagr` Nullable(Float64) COMMENT 'kind=sigmarail_derived. 3-Year Revenue CAGR (ARY).',
    `revenue_acceleration_fy` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 1 if current ARY YoY Revenue growth > prior year.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=ary_derived';

-- Managed transform view for target: ary_derived
-- kind=sigmarail_derived layer=L2
-- Populates ary_derived from L1 ary FINAL (+ tickers for ranks).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_ary_derived;

CREATE VIEW IF NOT EXISTS xform_ary_derived (
    ticker,
    date,
    revenue_yoy_growth,
    eps_growth_yoy,
    revenue_yoy_growth_industry_rank,
    revenue_yoy_growth_sector_rank,
    netmargin_industry_rank,
    netmargin_sector_rank,
    ebitdamargin_industry_rank,
    ebitdamargin_sector_rank,
    eps_growth_3y_cagr,
    eps_acceleration_fy,
    revenue_growth_3y_cagr,
    revenue_acceleration_fy,
    lastupdated
)
COMMENT '{"order":17,"target":"ary_derived","sources":["ary","tickers"],"chunk_size":"6m"}'
AS
WITH
ary_history AS (
    SELECT
        ticker, date,
        revenue, epsdil, netmargin, ebitdamargin
    FROM ary FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 1500 DAY AND {chunk_end_date:String}
),
ary_calcs AS (
    SELECT
        a.ticker,
        a.date,
        a.netmargin,
        a.ebitdamargin,
        CASE WHEN COUNT(a.revenue) OVER w_yoy >= 2 AND lagInFrame(a.revenue, 1) OVER w_yoy > 0
             THEN (a.revenue - lagInFrame(a.revenue, 1) OVER w_yoy) / lagInFrame(a.revenue, 1) OVER w_yoy
             ELSE NULL END as revenue_yoy_growth,
        CASE WHEN COUNT(a.epsdil) OVER w_yoy >= 2 AND lagInFrame(a.epsdil, 1) OVER w_yoy > 0
             THEN (a.epsdil - lagInFrame(a.epsdil, 1) OVER w_yoy) / lagInFrame(a.epsdil, 1) OVER w_yoy
             ELSE NULL END as eps_growth_yoy,
        CASE WHEN COUNT(a.epsdil) OVER w_3y >= 4 AND lagInFrame(a.epsdil, 3) OVER w_3y > 0
             THEN pow(a.epsdil / lagInFrame(a.epsdil, 3) OVER w_3y, 1/3.0) - 1
             ELSE NULL END as eps_growth_3y_cagr,
        CASE WHEN COUNT(a.revenue) OVER w_3y >= 4 AND lagInFrame(a.revenue, 3) OVER w_3y > 0
             THEN pow(a.revenue / lagInFrame(a.revenue, 3) OVER w_3y, 1/3.0) - 1
             ELSE NULL END as revenue_growth_3y_cagr
    FROM ary_history a
    WINDOW
        w_yoy AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),
        w_3y AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
),
ary_with_tickers AS (
    SELECT
        c.*,
        t.industry,
        t.sector
    FROM ary_calcs c
    JOIN tickers t ON c.ticker = t.ticker
),
ary_with_ranks AS (
    SELECT
        ticker, date,
        revenue_yoy_growth, eps_growth_yoy,
        if(isFinite(percent_rank() OVER (PARTITION BY date, industry ORDER BY revenue_yoy_growth ASC) * 100),
           percent_rank() OVER (PARTITION BY date, industry ORDER BY revenue_yoy_growth ASC) * 100, NULL) as revenue_yoy_growth_industry_rank,
        if(isFinite(percent_rank() OVER (PARTITION BY date, sector ORDER BY revenue_yoy_growth ASC) * 100),
           percent_rank() OVER (PARTITION BY date, sector ORDER BY revenue_yoy_growth ASC) * 100, NULL) as revenue_yoy_growth_sector_rank,
        if(isFinite(percent_rank() OVER (PARTITION BY date, industry ORDER BY netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY date, industry ORDER BY netmargin ASC) * 100, NULL) as netmargin_industry_rank,
        if(isFinite(percent_rank() OVER (PARTITION BY date, sector ORDER BY netmargin ASC) * 100),
           percent_rank() OVER (PARTITION BY date, sector ORDER BY netmargin ASC) * 100, NULL) as netmargin_sector_rank,
        if(isFinite(percent_rank() OVER (PARTITION BY date, industry ORDER BY ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY date, industry ORDER BY ebitdamargin ASC) * 100, NULL) as ebitdamargin_industry_rank,
        if(isFinite(percent_rank() OVER (PARTITION BY date, sector ORDER BY ebitdamargin ASC) * 100),
           percent_rank() OVER (PARTITION BY date, sector ORDER BY ebitdamargin ASC) * 100, NULL) as ebitdamargin_sector_rank,
        eps_growth_3y_cagr,
        revenue_growth_3y_cagr,
        CASE WHEN COUNT(eps_growth_yoy) OVER w_accel >= 2 AND eps_growth_yoy > lagInFrame(eps_growth_yoy, 1) OVER w_accel
             THEN 1 ELSE 0 END as eps_acceleration_fy,
        CASE WHEN COUNT(revenue_yoy_growth) OVER w_accel >= 2 AND revenue_yoy_growth > lagInFrame(revenue_yoy_growth, 1) OVER w_accel
             THEN 1 ELSE 0 END as revenue_acceleration_fy
    FROM ary_with_tickers
    WINDOW w_accel AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
)
SELECT
    ticker,
    date,
    revenue_yoy_growth,
    eps_growth_yoy,
    revenue_yoy_growth_industry_rank,
    revenue_yoy_growth_sector_rank,
    netmargin_industry_rank,
    netmargin_sector_rank,
    ebitdamargin_industry_rank,
    ebitdamargin_sector_rank,
    eps_growth_3y_cagr,
    eps_acceleration_fy,
    revenue_growth_3y_cagr,
    revenue_acceleration_fy,
    now() AS lastupdated
FROM ary_with_ranks
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
