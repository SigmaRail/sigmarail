-- kind=sigmarail_derived layer=L2
-- ART CapEx ratios / history / cash_posture; cash_posture_disagree vs MRT twin.
CREATE TABLE IF NOT EXISTS art_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'ART calendar date (aligned with art.date).',
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
    `cash_posture` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 2=high_reinvestment; 1=moderate; 0=low_capex; NULL if ncfo null/<=0.',
    `cash_posture_disagree` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 1 when ART cash_posture != MRT cash_posture (both non-null on same date); else 0; NULL if either missing.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=art_derived';

-- Managed transform view for target: art_derived
-- kind=sigmarail_derived layer=L2
-- Populates art_derived CapEx ratios + cash_posture_disagree vs mrt_derived.
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_art_derived;

CREATE VIEW IF NOT EXISTS xform_art_derived (
    ticker,
    date,
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
    cash_posture_disagree,
    lastupdated
)
COMMENT '{"order":22,"target":"art_derived","sources":["art","mrt_derived","tickers"],"chunk_size":"6m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        d.ticker,
        count() as target_row_count,
        max(d.lastupdated) as target_last_updated
    FROM art_derived d FINAL
    WHERE d.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY d.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM (
        SELECT ticker, lastupdated FROM art FINAL
        WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 2000 DAY AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mrt_derived FINAL
        WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 2000 DAY AND {chunk_end_date:String}
    ) s
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
art_history AS (
    SELECT
        ticker,
        date,
        revenue,
        fcf,
        ncfo,
        capex,
        depamor,
        capex_abs
    FROM art FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 2000 DAY AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
tickers_info AS (
    SELECT ticker, industry, sector FROM tickers
),
art_with_ratios AS (
    SELECT
        a.ticker,
        a.date,
        a.revenue,
        a.fcf,
        a.ncfo,
        a.capex,
        a.depamor,
        a.capex_abs,
        t.industry,
        t.sector,
        a.ncfo / nullIf(a.revenue, 0) AS ocf_margin_calc,
        a.fcf / nullIf(a.revenue, 0) AS fcf_margin_calc,
        a.capex_abs / nullIf(a.ncfo, 0) AS capex_to_ocf_calc,
        a.fcf / nullIf(a.ncfo, 0) AS fcf_to_ocf_calc,
        a.capex_abs / nullIf(abs(a.depamor), 0) AS capex_to_da_calc,
        a.fcf - (a.ncfo + a.capex) AS fcf_recon_gap_calc,
        CASE WHEN COUNT(a.capex_abs) OVER w_yoy_4q >= 5
             THEN (a.capex_abs - lagInFrame(a.capex_abs, 4) OVER w_yoy_4q)
                  / nullIf(abs(lagInFrame(a.capex_abs, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as capex_yoy_growth_calc,
        CASE WHEN COUNT(a.capex_abs) OVER w_5y >= 20
             THEN a.capex_abs / nullIf(avg(a.capex_abs) OVER w_5y, 0)
             ELSE NULL END as capex_vs_5y_calc,
        CASE
            WHEN a.ncfo IS NULL OR a.ncfo <= 0 OR a.capex_abs IS NULL THEN NULL
            WHEN (a.capex_abs / nullIf(a.ncfo, 0)) >= 0.5 THEN toInt8(2)
            WHEN (a.capex_abs / nullIf(a.ncfo, 0)) >= 0.2 THEN toInt8(1)
            ELSE toInt8(0)
        END AS cash_posture_calc
    FROM art_history a
    JOIN tickers_info t ON a.ticker = t.ticker
    WINDOW
        w_yoy_4q AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w_5y AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
),
art_with_ranks AS (
    SELECT
        r.*,
        if(isFinite(percent_rank() OVER (PARTITION BY r.date, r.industry ORDER BY r.capex_to_ocf_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY r.date, r.industry ORDER BY r.capex_to_ocf_calc ASC) * 100, NULL) as capex_to_ocf_industry_rank_calc,
        if(isFinite(percent_rank() OVER (PARTITION BY r.date, r.sector ORDER BY r.capex_to_ocf_calc ASC) * 100),
           percent_rank() OVER (PARTITION BY r.date, r.sector ORDER BY r.capex_to_ocf_calc ASC) * 100, NULL) as capex_to_ocf_sector_rank_calc
    FROM art_with_ratios r
),
art_with_mrt AS (
    SELECT
        a.*,
        md.cash_posture AS mrt_cash_posture,
        CASE
            WHEN a.cash_posture_calc IS NULL OR md.cash_posture IS NULL THEN NULL
            WHEN a.cash_posture_calc != md.cash_posture THEN toInt8(1)
            ELSE toInt8(0)
        END AS cash_posture_disagree_calc
    FROM art_with_ranks a
    LEFT JOIN mrt_derived md FINAL
        ON a.ticker = md.ticker AND a.date = md.date
)
SELECT
    ticker,
    date,
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
    cash_posture_disagree_calc AS cash_posture_disagree,
    now() AS lastupdated
FROM art_with_mrt
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
