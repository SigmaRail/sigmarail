-- kind=sigmarail_derived layer=L2
-- MRT YoY growth, industry/sector ranks, and CapEx ratios from L1 `mrt` FINAL history.
CREATE TABLE IF NOT EXISTS mrt_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'TTM calendar date (aligned with mrt.date).',
    `roa_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY ROA growth (TTM vs 4Q ago).',
    `roe_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY ROE growth (TTM vs 4Q ago).',
    `roic_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY ROIC growth (TTM vs 4Q ago).',
    `roa_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for TTM ROA (0-100).',
    `roe_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for TTM ROE (0-100).',
    `roic_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for TTM ROIC (0-100).',
    `roa_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for TTM ROA (0-100).',
    `roe_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for TTM ROE (0-100).',
    `roic_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for TTM ROIC (0-100).',
    `ocf_margin` Nullable(Float64) COMMENT 'kind=sigmarail_derived. ncfo / nullIf(revenue, 0).',
    `fcf_margin` Nullable(Float64) COMMENT 'kind=sigmarail_derived. fcf / nullIf(revenue, 0).',
    `capex_to_ocf` Nullable(Float64) COMMENT 'kind=sigmarail_derived. capex_abs / nullIf(ncfo, 0).',
    `fcf_to_ocf` Nullable(Float64) COMMENT 'kind=sigmarail_derived. fcf / nullIf(ncfo, 0).',
    `capex_to_da` Nullable(Float64) COMMENT 'kind=sigmarail_derived. capex_abs / nullIf(abs(depamor), 0).',
    `fcf_recon_gap` Nullable(Float64) COMMENT 'kind=sigmarail_derived. fcf - (ncfo + capex); expect ~0 when SF1 fields present.',
    `capex_yoy_growth` Nullable(Float64) COMMENT 'kind=sigmarail_derived. (capex_abs - lag4(capex_abs)) / nullIf(abs(lag4(capex_abs)), 0) when >=5 TTM points.',
    `capex_vs_5y` Nullable(Float64) COMMENT 'kind=sigmarail_derived. capex_abs / nullIf(avg(capex_abs) over prior 20 TTM rows, 0) when >=20 points.',
    `capex_to_ocf_industry_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Industry percentile rank for capex_to_ocf (0-100).',
    `capex_to_ocf_sector_rank` Nullable(Float64) COMMENT 'kind=sigmarail_derived. Sector percentile rank for capex_to_ocf (0-100).',
    `cash_posture` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 2=high_reinvestment (capex_to_ocf>=0.5 & ncfo>0); 1=moderate (0.2<=ratio<0.5); 0=low_capex (ratio<0.2 & ncfo>0); NULL if ncfo null/<=0.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=mrt_derived';

-- Managed transform view for target: mrt_derived
-- kind=sigmarail_derived layer=L2
-- Populates mrt_derived YoY growth + ranks + CapEx ratios from L1 mrt FINAL.
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mrt_derived;

CREATE VIEW IF NOT EXISTS xform_mrt_derived (
    ticker,
    date,
    roa_yoy_growth,
    roe_yoy_growth,
    roic_yoy_growth,
    roa_industry_rank,
    roe_industry_rank,
    roic_industry_rank,
    roa_sector_rank,
    roe_sector_rank,
    roic_sector_rank,
    ocf_margin,
    fcf_margin,
    capex_to_ocf,
    fcf_to_ocf,
    capex_to_da,
    fcf_recon_gap,
    capex_yoy_growth,
    capex_vs_5y,
    capex_to_ocf_industry_rank,
    capex_to_ocf_sector_rank,
    cash_posture,
    lastupdated
)
COMMENT '{"order":19,"target":"mrt_derived","sources":["mrt","tickers"],"chunk_size":"6m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        d.ticker,
        count() as target_row_count,
        max(d.lastupdated) as target_last_updated
    FROM mrt_derived d FINAL
    WHERE d.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY d.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM mrt FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 2000 DAY AND {chunk_end_date:String}
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
mrt_history AS (
    SELECT
        ticker,
        date,
        roa,
        roe,
        roic,
        revenue,
        fcf,
        ncfo,
        capex,
        depamor,
        capex_abs
    FROM mrt FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 2000 DAY AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
tickers_info AS (
    SELECT ticker, industry, sector FROM tickers
),
mrt_with_yoy AS (
    SELECT
        m.ticker,
        m.date,
        m.roa,
        m.roe,
        m.roic,
        m.revenue,
        m.fcf,
        m.ncfo,
        m.capex,
        m.depamor,
        m.capex_abs,
        t.industry,
        t.sector,
        CASE WHEN COUNT(m.roa) OVER w_yoy_4q >= 5
             THEN (m.roa - lagInFrame(m.roa, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(m.roa, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as roa_yoy_growth_calc,
        CASE WHEN COUNT(m.roe) OVER w_yoy_4q >= 5
             THEN (m.roe - lagInFrame(m.roe, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(m.roe, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as roe_yoy_growth_calc,
        CASE WHEN COUNT(m.roic) OVER w_yoy_4q >= 5
             THEN (m.roic - lagInFrame(m.roic, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(m.roic, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as roic_yoy_growth_calc,
        m.ncfo / nullIf(m.revenue, 0) AS ocf_margin_calc,
        m.fcf / nullIf(m.revenue, 0) AS fcf_margin_calc,
        m.capex_abs / nullIf(m.ncfo, 0) AS capex_to_ocf_calc,
        m.fcf / nullIf(m.ncfo, 0) AS fcf_to_ocf_calc,
        m.capex_abs / nullIf(abs(m.depamor), 0) AS capex_to_da_calc,
        m.fcf - (m.ncfo + m.capex) AS fcf_recon_gap_calc,
        CASE WHEN COUNT(m.capex_abs) OVER w_yoy_4q >= 5
             THEN (m.capex_abs - lagInFrame(m.capex_abs, 4) OVER w_yoy_4q)
                  / nullIf(abs(lagInFrame(m.capex_abs, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as capex_yoy_growth_calc,
        CASE WHEN COUNT(m.capex_abs) OVER w_5y >= 20
             THEN m.capex_abs / nullIf(avg(m.capex_abs) OVER w_5y, 0)
             ELSE NULL END as capex_vs_5y_calc,
        CASE
            WHEN m.ncfo IS NULL OR m.ncfo <= 0 OR m.capex_abs IS NULL THEN NULL
            WHEN (m.capex_abs / nullIf(m.ncfo, 0)) >= 0.5 THEN toInt8(2)
            WHEN (m.capex_abs / nullIf(m.ncfo, 0)) >= 0.2 THEN toInt8(1)
            ELSE toInt8(0)
        END AS cash_posture_calc
    FROM mrt_history m
    JOIN tickers_info t ON m.ticker = t.ticker
    WINDOW
        w_yoy_4q AS (PARTITION BY m.ticker ORDER BY m.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w_5y AS (PARTITION BY m.ticker ORDER BY m.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
),
mrt_with_ranks AS (
    SELECT
        y.*,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roa ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roa ASC) * 100, NULL) as roa_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roe ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roe ASC) * 100, NULL) as roe_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roic ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.roic ASC) * 100, NULL) as roic_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roa ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roa ASC) * 100, NULL) as roa_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roe ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roe ASC) * 100, NULL) as roe_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roic ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.roic ASC) * 100, NULL) as roic_sector_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.capex_to_ocf_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.industry ORDER BY y.capex_to_ocf_calc ASC) * 100, NULL) as capex_to_ocf_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.capex_to_ocf_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY y.date, y.sector ORDER BY y.capex_to_ocf_calc ASC) * 100, NULL) as capex_to_ocf_sector_rank_calc
    FROM mrt_with_yoy y
)
SELECT
    ticker,
    date,
    roa_yoy_growth_calc AS roa_yoy_growth,
    roe_yoy_growth_calc AS roe_yoy_growth,
    roic_yoy_growth_calc AS roic_yoy_growth,
    roa_industry_rank_calc AS roa_industry_rank,
    roe_industry_rank_calc AS roe_industry_rank,
    roic_industry_rank_calc AS roic_industry_rank,
    roa_sector_rank_calc AS roa_sector_rank,
    roe_sector_rank_calc AS roe_sector_rank,
    roic_sector_rank_calc AS roic_sector_rank,
    ocf_margin_calc AS ocf_margin,
    fcf_margin_calc AS fcf_margin,
    capex_to_ocf_calc AS capex_to_ocf,
    fcf_to_ocf_calc AS fcf_to_ocf,
    capex_to_da_calc AS capex_to_da,
    fcf_recon_gap_calc AS fcf_recon_gap,
    capex_yoy_growth_calc AS capex_yoy_growth,
    capex_vs_5y_calc AS capex_vs_5y,
    capex_to_ocf_industry_rank_calc AS capex_to_ocf_industry_rank,
    capex_to_ocf_sector_rank_calc AS capex_to_ocf_sector_rank,
    cash_posture_calc AS cash_posture,
    now() AS lastupdated
FROM mrt_with_ranks
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
