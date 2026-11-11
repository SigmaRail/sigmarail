-- =============================================================================
-- L4 ASOF fund daily (kind=delivery_projection) — Episode A0+
-- Populated by transform 25-daily-fundamentals.sql (ASOF L1 + L2 *_derived).
-- =============================================================================

CREATE TABLE IF NOT EXISTS daily_fundamentals
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date for technicals / Calendar date for fundamentals',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the latest underlying data used for this record',
    `company_name` String COMMENT 'Company name (from tickers)',
    `sector` String COMMENT 'Company sector (from tickers)',
    `industry` String COMMENT 'Company industry (from tickers)',
    `mrt_roa` Float64 COMMENT 'Return on Assets (TTM)',
    `mrt_roe` Float64 COMMENT 'Return on Equity (TTM)',
    `mrt_roic` Float64 COMMENT 'Return on Invested Capital (TTM)',
    `mrt_revenue` Float64 COMMENT 'Revenue (TTM)',
    `mrt_gp` Float64 COMMENT 'Gross Profit (TTM)',
    `mrt_ebit` Float64 COMMENT 'EBIT (TTM)',
    `mrt_ebitda` Float64 COMMENT 'EBITDA (TTM)',
    `mrt_netinccmn` Float64 COMMENT 'Net Income Common (TTM)',
    `mrt_epsdil` Float64 COMMENT 'Diluted EPS (TTM)',
    `mrt_fcf` Float64 COMMENT 'Free Cash Flow (TTM)',
    `mrt_assetsavg` Float64 COMMENT 'Average Assets (TTM context)',
    `mrt_equityavg` Float64 COMMENT 'Average Equity (TTM context)',
    `mrt_invcapavg` Float64 COMMENT 'Average Invested Capital (TTM context)',
    `mrt_currentratio` Float64 COMMENT 'Current Ratio (TTM)',
    `mrt_de` Float64 COMMENT 'Debt to Equity Ratio (TTM)',
    `mrt_grossmargin` Float64 COMMENT 'Gross Margin (TTM)',
    `mrt_netmargin` Float64 COMMENT 'Net Margin (TTM)',
    `mrt_roa_yoy_growth` Float64 COMMENT 'Year over year ROA growth (TTM vs TTM)',
    `mrt_roe_yoy_growth` Float64 COMMENT 'Year over year ROE growth (TTM vs TTM)',
    `mrt_roic_yoy_growth` Float64 COMMENT 'Year over year ROIC growth (TTM vs TTM)',
    `mrt_roa_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROA',
    `mrt_roe_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROE',
    `mrt_roic_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROIC',
    `mrt_roa_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROA',
    `mrt_roe_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROE',
    `mrt_roic_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROIC',
    `mrt_ncfo` Nullable(Float64) COMMENT 'kind=delivery_projection. Net Cash Flow from Operations (TTM) from mrt.',
    `mrt_capex` Nullable(Float64) COMMENT 'kind=delivery_projection. CapEx (TTM) from mrt; typically negative.',
    `mrt_depamor` Nullable(Float64) COMMENT 'kind=delivery_projection. Depreciation/Amortization (TTM) from mrt.',
    `mrt_fxusd` Nullable(Float64) COMMENT 'kind=delivery_projection. FXUSD from mrt.',
    `mrt_capex_abs` Nullable(Float64) COMMENT 'kind=delivery_projection. abs(capex) from mrt.',
    `mrt_ocf_margin` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: ncfo/revenue.',
    `mrt_fcf_margin` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: fcf/revenue.',
    `mrt_capex_to_ocf` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: capex_abs/ncfo.',
    `mrt_fcf_to_ocf` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: fcf/ncfo.',
    `mrt_capex_to_da` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: capex_abs/abs(depamor).',
    `mrt_fcf_recon_gap` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived: fcf-(ncfo+capex).',
    `mrt_capex_yoy_growth` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived CapEx YoY.',
    `mrt_capex_vs_5y` Nullable(Float64) COMMENT 'kind=delivery_projection. From mrt_derived CapEx vs 5y avg.',
    `mrt_capex_to_ocf_industry_rank` Nullable(Float64) COMMENT 'kind=delivery_projection. Industry rank of capex_to_ocf.',
    `mrt_capex_to_ocf_sector_rank` Nullable(Float64) COMMENT 'kind=delivery_projection. Sector rank of capex_to_ocf.',
    `mrt_cash_posture` Nullable(Int8) COMMENT 'kind=delivery_projection. From mrt_derived cash_posture.',
    `mrq_revenue` Float64 COMMENT 'Revenue (Most Recent Quarter)',
    `mrq_gp` Float64 COMMENT 'Gross Profit (Most Recent Quarter)',
    `mrq_ebit` Float64 COMMENT 'EBIT (Most Recent Quarter)',
    `mrq_ebitda` Float64 COMMENT 'EBITDA (Most Recent Quarter)',
    `mrq_netinccmn` Float64 COMMENT 'Net Income Common (Most Recent Quarter)',
    `mrq_epsdil` Float64 COMMENT 'Diluted EPS (Most Recent Quarter)',
    `mrq_grossmargin` Float64 COMMENT 'Gross Margin (MRQ context)',
    `mrq_netmargin` Float64 COMMENT 'Net Margin (MRQ context)',
    `mrq_ebitdamargin` Float64 COMMENT 'EBITDA Margin (MRQ context)',
    `mrq_currentratio` Float64 COMMENT 'Current Ratio (MRQ context)',
    `mrq_de` Float64 COMMENT 'Debt to Equity Ratio (MRQ context)',
    `mrq_fcf` Float64 COMMENT 'Free Cash Flow (MRQ context)',
    `mrq_grossmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ Gross Margin',
    `mrq_grossmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ Gross Margin',
    `mrq_netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ Net Margin',
    `mrq_netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ Net Margin',
    `mrq_ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ EBITDA Margin',
    `mrq_ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ EBITDA Margin',
    `arq_revenue` Float64 COMMENT 'Revenue (As Reported Quarter)',
    `arq_gp` Float64 COMMENT 'Gross Profit (As Reported Quarter)',
    `arq_ebit` Float64 COMMENT 'EBIT (As Reported Quarter)',
    `arq_ebitda` Float64 COMMENT 'EBITDA (As Reported Quarter)',
    `arq_netinccmn` Float64 COMMENT 'Net Income Common (As Reported Quarter)',
    `arq_epsdil` Float64 COMMENT 'Diluted EPS (As Reported Quarter)',
    `arq_fcf` Float64 COMMENT 'Free Cash Flow (As Reported Quarter)',
    `arq_grossmargin` Float64 COMMENT 'Gross Margin (ARQ context)',
    `arq_netmargin` Float64 COMMENT 'Net Margin (ARQ context)',
    `arq_ebitdamargin` Float64 COMMENT 'EBITDA Margin (ARQ context)',
    `arq_currentratio` Float64 COMMENT 'Current Ratio (ARQ context)',
    `arq_de` Float64 COMMENT 'Debt to Equity Ratio (ARQ context)',
    `arq_revenue_growth_yoy` Float64 COMMENT 'Year over year Revenue growth (ARQ vs ARQ)',
    `arq_eps_growth_yoy` Float64 COMMENT 'Year over year EPS growth (ARQ vs ARQ)',
    `arq_fcf_growth_yoy` Float64 COMMENT 'Year over year FCF growth (ARQ vs ARQ)',
    `arq_netincome_growth_yoy` Float64 COMMENT 'Year over year Net Income growth (ARQ vs ARQ)',
    `arq_eps_growth_qoq` Nullable(Float64) COMMENT 'Quarter-over-Quarter EPS Growth (ARQ vs Prev ARQ)',
    `arq_eps_acceleration_qoq` Nullable(Int8) COMMENT 'EPS Growth Acceleration QoQ (1 if QoQ growth > prev QoQ growth, 0 otherwise)',
    `arq_revenue_growth_qoq` Nullable(Float64) COMMENT 'Quarter-over-Quarter Revenue Growth (ARQ vs Prev ARQ)',
    `arq_revenue_acceleration_qoq` Nullable(Int8) COMMENT 'Revenue Growth Acceleration QoQ (1 if QoQ growth > prev QoQ growth, 0 otherwise)',
    `arq_eps_acceleration_q2` Nullable(Int8) COMMENT 'ChartMill s_epsaQ2: 1 iff YoY EPS growth increased for 2 consecutive quarters; NULL if incomplete window',
    `arq_eps_acceleration_q3` Nullable(Int8) COMMENT 'ChartMill s_epsaQ3: 1 iff YoY EPS growth increased for 3 consecutive quarters; NULL if incomplete window',
    `arq_revenue_acceleration_q2` Nullable(Int8) COMMENT 'ChartMill s_revaQ2: 1 iff YoY revenue growth increased for 2 consecutive quarters; NULL if incomplete window',
    `arq_revenue_acceleration_q3` Nullable(Int8) COMMENT 'ChartMill s_revaQ3: 1 iff YoY revenue growth increased for 3 consecutive quarters; NULL if incomplete window',
    `arq_pmi_up_q2` Nullable(Int8) COMMENT 'ChartMill s_pmiQ2: 1 iff ARQ net margin increased for 2 consecutive quarters; NULL if incomplete window',
    `arq_pmi_up_q3` Nullable(Int8) COMMENT 'ChartMill s_pmiQ3: 1 iff ARQ net margin increased for 3 consecutive quarters; NULL if incomplete window',
    `mry_revenue` Float64 COMMENT 'Revenue (Most Recent Year)',
    `mry_gp` Float64 COMMENT 'Gross Profit (Most Recent Year)',
    `mry_ebit` Float64 COMMENT 'EBIT (Most Recent Year)',
    `mry_ebitda` Float64 COMMENT 'EBITDA (Most Recent Year)',
    `mry_netinccmn` Float64 COMMENT 'Net Income Common (Most Recent Year)',
    `mry_epsdil` Float64 COMMENT 'Diluted EPS (Most Recent Year)',
    `mry_fcf` Float64 COMMENT 'Free Cash Flow (Most Recent Year)',
    `mry_dps` Float64 COMMENT 'Dividends Per Share (Most Recent Year)',
    `mry_grossmargin` Float64 COMMENT 'Gross Margin (MRY context)',
    `mry_netmargin` Float64 COMMENT 'Net Margin (MRY context)',
    `mry_ebitdamargin` Float64 COMMENT 'EBITDA Margin (MRY context)',
    `mry_revenue_yoy_growth` Float64 COMMENT 'Year over year Revenue growth (MRY vs MRY)',
    `mry_revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY Revenue YoY Growth',
    `mry_revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY Revenue YoY Growth',
    `mry_netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY Net Margin',
    `mry_netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY Net Margin',
    `mry_ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY EBITDA Margin',
    `mry_ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY EBITDA Margin',
    `ary_revenue` Float64 COMMENT 'Revenue (ARY)',
    `ary_gp` Float64 COMMENT 'Gross Profit (ARY)',
    `ary_ebit` Float64 COMMENT 'EBIT (ARY)',
    `ary_ebitda` Float64 COMMENT 'EBITDA (ARY)',
    `ary_netinccmn` Float64 COMMENT 'Net Income Common (ARY)',
    `ary_epsdil` Float64 COMMENT 'Diluted EPS (ARY)',
    `ary_fcf` Float64 COMMENT 'Free Cash Flow (ARY)',
    `ary_dps` Float64 COMMENT 'Dividends Per Share (ARY)',
    `ary_grossmargin` Float64 COMMENT 'Gross Margin (ARY context)',
    `ary_netmargin` Float64 COMMENT 'Net Margin (ARY context)',
    `ary_ebitdamargin` Float64 COMMENT 'EBITDA Margin (ARY context)',
    `ary_currentratio` Float64 COMMENT 'Current Ratio (ARY context)',
    `ary_de` Float64 COMMENT 'Debt to Equity Ratio (ARY context)',
    `ary_revenue_yoy_growth` Float64 COMMENT 'Year over year Revenue growth (ARY vs ARY)',
    `ary_revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY Revenue YoY Growth',
    `ary_revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY Revenue YoY Growth',
    `ary_netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY Net Margin',
    `ary_netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY Net Margin',
    `ary_ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY EBITDA Margin',
    `ary_ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY EBITDA Margin',
    `ary_eps_growth_yoy` Nullable(Float64) COMMENT 'Year over year EPS growth (ARY vs ARY)',
    `ary_eps_growth_3y_cagr` Nullable(Float64) COMMENT '3-Year EPS Growth CAGR (ARY)',
    `ary_eps_acceleration_fy` Nullable(Int8) COMMENT 'EPS Growth Acceleration Fiscal Year (1 if YOY growth > prev YOY growth, 0 otherwise)',
    `ary_revenue_growth_3y_cagr` Nullable(Float64) COMMENT '3-Year Revenue Growth CAGR (ARY)',
    `ary_revenue_acceleration_fy` Nullable(Int8) COMMENT 'Revenue Growth Acceleration Fiscal Year (1 if YOY growth > prev YOY growth, 0 otherwise)',
    `art_ncfo` Nullable(Float64) COMMENT 'kind=delivery_projection. Net Cash Flow from Operations (ART) from art.',
    `art_capex` Nullable(Float64) COMMENT 'kind=delivery_projection. CapEx (ART) from art; typically negative.',
    `art_depamor` Nullable(Float64) COMMENT 'kind=delivery_projection. Depreciation/Amortization (ART) from art.',
    `art_fxusd` Nullable(Float64) COMMENT 'kind=delivery_projection. FXUSD from art.',
    `art_capex_abs` Nullable(Float64) COMMENT 'kind=delivery_projection. abs(capex) from art.',
    `art_fcf` Nullable(Float64) COMMENT 'kind=delivery_projection. Free Cash Flow (ART) from art.',
    `art_revenue` Nullable(Float64) COMMENT 'kind=delivery_projection. Revenue (ART) from art.',
    `art_roic` Nullable(Float64) COMMENT 'kind=delivery_projection. ROIC (ART) from art.',
    `art_ocf_margin` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: ncfo/revenue.',
    `art_fcf_margin` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: fcf/revenue.',
    `art_capex_to_ocf` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: capex_abs/ncfo.',
    `art_fcf_to_ocf` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: fcf/ncfo.',
    `art_capex_to_da` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: capex_abs/abs(depamor).',
    `art_fcf_recon_gap` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived: fcf-(ncfo+capex).',
    `art_capex_yoy_growth` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived CapEx YoY.',
    `art_capex_vs_5y` Nullable(Float64) COMMENT 'kind=delivery_projection. From art_derived CapEx vs 5y avg.',
    `art_capex_to_ocf_industry_rank` Nullable(Float64) COMMENT 'kind=delivery_projection. Industry rank of ART capex_to_ocf.',
    `art_capex_to_ocf_sector_rank` Nullable(Float64) COMMENT 'kind=delivery_projection. Sector rank of ART capex_to_ocf.',
    `art_cash_posture` Nullable(Int8) COMMENT 'kind=delivery_projection. From art_derived cash_posture.',
    `art_cash_posture_disagree` Nullable(Int8) COMMENT 'kind=delivery_projection. From art_derived: ART vs MRT cash_posture disagree.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_fundamentals
-- kind=layer=L4 (daily join of fund L1 vendor_copy + L2 sigmarail_derived)
-- Populates daily_fundamentals for a given date chunk.
-- Public column names (mrt_*, arq_*, art_*, …) unchanged for existing; CapEx/ART added Episode A1.
-- Expects ClickHouse params: chunk_start_date, chunk_end_date, force_refresh
--
DROP VIEW IF EXISTS xform_daily_fundamentals;

CREATE VIEW IF NOT EXISTS xform_daily_fundamentals (
    ticker,
    date,
    lastupdated,
    company_name,
    sector,
    industry,
    mrt_roa,
    mrt_roe,
    mrt_roic,
    mrt_revenue,
    mrt_gp,
    mrt_ebit,
    mrt_ebitda,
    mrt_netinccmn,
    mrt_epsdil,
    mrt_fcf,
    mrt_assetsavg,
    mrt_equityavg,
    mrt_invcapavg,
    mrt_currentratio,
    mrt_de,
    mrt_grossmargin,
    mrt_netmargin,
    mrt_roa_yoy_growth,
    mrt_roe_yoy_growth,
    mrt_roic_yoy_growth,
    mrt_roa_industry_rank,
    mrt_roe_industry_rank,
    mrt_roic_industry_rank,
    mrt_roa_sector_rank,
    mrt_roe_sector_rank,
    mrt_roic_sector_rank,
    mrt_ncfo,
    mrt_capex,
    mrt_depamor,
    mrt_fxusd,
    mrt_capex_abs,
    mrt_ocf_margin,
    mrt_fcf_margin,
    mrt_capex_to_ocf,
    mrt_fcf_to_ocf,
    mrt_capex_to_da,
    mrt_fcf_recon_gap,
    mrt_capex_yoy_growth,
    mrt_capex_vs_5y,
    mrt_capex_to_ocf_industry_rank,
    mrt_capex_to_ocf_sector_rank,
    mrt_cash_posture,
    mrq_revenue,
    mrq_gp,
    mrq_ebit,
    mrq_ebitda,
    mrq_netinccmn,
    mrq_epsdil,
    mrq_grossmargin,
    mrq_netmargin,
    mrq_ebitdamargin,
    mrq_currentratio,
    mrq_de,
    mrq_fcf,
    mrq_grossmargin_industry_rank,
    mrq_grossmargin_sector_rank,
    mrq_netmargin_industry_rank,
    mrq_netmargin_sector_rank,
    mrq_ebitdamargin_industry_rank,
    mrq_ebitdamargin_sector_rank,
    arq_revenue,
    arq_gp,
    arq_ebit,
    arq_ebitda,
    arq_netinccmn,
    arq_epsdil,
    arq_fcf,
    arq_grossmargin,
    arq_netmargin,
    arq_ebitdamargin,
    arq_currentratio,
    arq_de,
    arq_revenue_growth_yoy,
    arq_eps_growth_yoy,
    arq_fcf_growth_yoy,
    arq_netincome_growth_yoy,
    arq_eps_growth_qoq,
    arq_eps_acceleration_qoq,
    arq_revenue_growth_qoq,
    arq_revenue_acceleration_qoq,
    arq_eps_acceleration_q2,
    arq_eps_acceleration_q3,
    arq_revenue_acceleration_q2,
    arq_revenue_acceleration_q3,
    arq_pmi_up_q2,
    arq_pmi_up_q3,
    mry_revenue,
    mry_gp,
    mry_ebit,
    mry_ebitda,
    mry_netinccmn,
    mry_epsdil,
    mry_fcf,
    mry_dps,
    mry_grossmargin,
    mry_netmargin,
    mry_ebitdamargin,
    mry_revenue_yoy_growth,
    mry_revenue_yoy_growth_industry_rank,
    mry_revenue_yoy_growth_sector_rank,
    mry_netmargin_industry_rank,
    mry_netmargin_sector_rank,
    mry_ebitdamargin_industry_rank,
    mry_ebitdamargin_sector_rank,
    ary_revenue,
    ary_gp,
    ary_ebit,
    ary_ebitda,
    ary_netinccmn,
    ary_epsdil,
    ary_fcf,
    ary_dps,
    ary_grossmargin,
    ary_netmargin,
    ary_ebitdamargin,
    ary_currentratio,
    ary_de,
    ary_revenue_yoy_growth,
    ary_eps_growth_yoy,
    ary_revenue_yoy_growth_industry_rank,
    ary_revenue_yoy_growth_sector_rank,
    ary_netmargin_industry_rank,
    ary_netmargin_sector_rank,
    ary_ebitdamargin_industry_rank,
    ary_ebitdamargin_sector_rank,
    ary_eps_growth_3y_cagr,
    ary_eps_acceleration_fy,
    ary_revenue_growth_3y_cagr,
    ary_revenue_acceleration_fy,
    art_ncfo,
    art_capex,
    art_depamor,
    art_fxusd,
    art_capex_abs,
    art_fcf,
    art_revenue,
    art_roic,
    art_ocf_margin,
    art_fcf_margin,
    art_capex_to_ocf,
    art_fcf_to_ocf,
    art_capex_to_da,
    art_fcf_recon_gap,
    art_capex_yoy_growth,
    art_capex_vs_5y,
    art_capex_to_ocf_industry_rank,
    art_capex_to_ocf_sector_rank,
    art_cash_posture,
    art_cash_posture_disagree
)
COMMENT '{"order":25,"target":"daily_fundamentals","sources":["daily_metrics","mrt","mrt_derived","art","art_derived","mrq","mrq_derived","arq","arq_derived","mry","mry_derived","ary","ary_derived","tickers"],"chunk_size":"1m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        df.ticker,
        count() as target_row_count,
        max(df.lastupdated) as target_last_updated
    FROM daily_fundamentals df FINAL
    WHERE df.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY df.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM (
        SELECT ticker, lastupdated FROM daily_metrics FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mrt FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mrt_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM art FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM art_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mrq FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mrq_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM arq FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM arq_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mry FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM mry_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM ary FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
        UNION ALL
        SELECT ticker, lastupdated FROM ary_derived FINAL
        WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    ) s
    GROUP BY ticker
),
-- {force_refresh:UInt8}=1 rewrites the chunk even when arq_derived has no
-- quarter-end date in-range and daily_metrics.lastupdated is older than target.
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN {force_refresh:UInt8} = 1 THEN 1
            WHEN t.target_last_updated IS NULL THEN 1
            WHEN s.source_row_count > t.target_row_count THEN 1
            WHEN s.source_last_updated > t.target_last_updated THEN 1
            ELSE 0
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
)
SELECT
    dm.ticker AS ticker,
    dm.date AS date,
    now() as lastupdated,
    t.name as company_name,
    t.sector,
    t.industry,

    -- TTM Metrics (L1 vendor)
    mrt.roa AS mrt_roa,
    mrt.roe AS mrt_roe,
    mrt.roic AS mrt_roic,
    mrt.revenue AS mrt_revenue,
    mrt.gp AS mrt_gp,
    mrt.ebit AS mrt_ebit,
    mrt.ebitda AS mrt_ebitda,
    mrt.netinccmn AS mrt_netinccmn,
    mrt.epsdil AS mrt_epsdil,
    mrt.fcf AS mrt_fcf,
    mrt.assetsavg AS mrt_assetsavg,
    mrt.equityavg AS mrt_equityavg,
    mrt.invcapavg AS mrt_invcapavg,
    mrt.currentratio AS mrt_currentratio,
    mrt.de AS mrt_de,
    mrt.grossmargin AS mrt_grossmargin,
    mrt.netmargin AS mrt_netmargin,
    -- TTM growth/ranks (L2)
    mrt_derived.roa_yoy_growth AS mrt_roa_yoy_growth,
    mrt_derived.roe_yoy_growth AS mrt_roe_yoy_growth,
    mrt_derived.roic_yoy_growth AS mrt_roic_yoy_growth,
    mrt_derived.roa_industry_rank AS mrt_roa_industry_rank,
    mrt_derived.roe_industry_rank AS mrt_roe_industry_rank,
    mrt_derived.roic_industry_rank AS mrt_roic_industry_rank,
    mrt_derived.roa_sector_rank AS mrt_roa_sector_rank,
    mrt_derived.roe_sector_rank AS mrt_roe_sector_rank,
    mrt_derived.roic_sector_rank AS mrt_roic_sector_rank,
    mrt.ncfo AS mrt_ncfo,
    mrt.capex AS mrt_capex,
    mrt.depamor AS mrt_depamor,
    mrt.fxusd AS mrt_fxusd,
    mrt.capex_abs AS mrt_capex_abs,
    mrt_derived.ocf_margin AS mrt_ocf_margin,
    mrt_derived.fcf_margin AS mrt_fcf_margin,
    mrt_derived.capex_to_ocf AS mrt_capex_to_ocf,
    mrt_derived.fcf_to_ocf AS mrt_fcf_to_ocf,
    mrt_derived.capex_to_da AS mrt_capex_to_da,
    mrt_derived.fcf_recon_gap AS mrt_fcf_recon_gap,
    mrt_derived.capex_yoy_growth AS mrt_capex_yoy_growth,
    mrt_derived.capex_vs_5y AS mrt_capex_vs_5y,
    mrt_derived.capex_to_ocf_industry_rank AS mrt_capex_to_ocf_industry_rank,
    mrt_derived.capex_to_ocf_sector_rank AS mrt_capex_to_ocf_sector_rank,
    mrt_derived.cash_posture AS mrt_cash_posture,

    -- MRQ Metrics (L1 vendor)
    mrq.revenue AS mrq_revenue,
    mrq.gp AS mrq_gp,
    mrq.ebit AS mrq_ebit,
    mrq.ebitda AS mrq_ebitda,
    mrq.netinccmn AS mrq_netinccmn,
    mrq.epsdil AS mrq_epsdil,
    mrq.grossmargin AS mrq_grossmargin,
    mrq.netmargin AS mrq_netmargin,
    mrq.ebitdamargin AS mrq_ebitdamargin,
    mrq.currentratio AS mrq_currentratio,
    mrq.de AS mrq_de,
    mrq.fcf AS mrq_fcf,
    -- MRQ ranks (L2)
    mrq_derived.grossmargin_industry_rank AS mrq_grossmargin_industry_rank,
    mrq_derived.grossmargin_sector_rank AS mrq_grossmargin_sector_rank,
    mrq_derived.netmargin_industry_rank AS mrq_netmargin_industry_rank,
    mrq_derived.netmargin_sector_rank AS mrq_netmargin_sector_rank,
    mrq_derived.ebitdamargin_industry_rank AS mrq_ebitdamargin_industry_rank,
    mrq_derived.ebitdamargin_sector_rank AS mrq_ebitdamargin_sector_rank,

    -- ARQ Metrics (L1 vendor)
    arq.revenue AS arq_revenue,
    arq.gp AS arq_gp,
    arq.ebit AS arq_ebit,
    arq.ebitda AS arq_ebitda,
    arq.netinccmn AS arq_netinccmn,
    arq.epsdil AS arq_epsdil,
    arq.fcf AS arq_fcf,
    arq.grossmargin AS arq_grossmargin,
    arq.netmargin AS arq_netmargin,
    arq.ebitdamargin AS arq_ebitdamargin,
    arq.currentratio AS arq_currentratio,
    arq.de AS arq_de,
    -- ARQ growth (L2)
    arq_derived.revenue_growth_yoy AS arq_revenue_growth_yoy,
    arq_derived.eps_growth_yoy AS arq_eps_growth_yoy,
    arq_derived.fcf_growth_yoy AS arq_fcf_growth_yoy,
    arq_derived.netincome_growth_yoy AS arq_netincome_growth_yoy,
    arq_derived.eps_growth_qoq AS arq_eps_growth_qoq,
    arq_derived.eps_acceleration_qoq AS arq_eps_acceleration_qoq,
    arq_derived.revenue_growth_qoq AS arq_revenue_growth_qoq,
    arq_derived.revenue_acceleration_qoq AS arq_revenue_acceleration_qoq,
    arq_derived.eps_acceleration_q2 AS arq_eps_acceleration_q2,
    arq_derived.eps_acceleration_q3 AS arq_eps_acceleration_q3,
    arq_derived.revenue_acceleration_q2 AS arq_revenue_acceleration_q2,
    arq_derived.revenue_acceleration_q3 AS arq_revenue_acceleration_q3,
    arq_derived.pmi_up_q2 AS arq_pmi_up_q2,
    arq_derived.pmi_up_q3 AS arq_pmi_up_q3,

    -- MRY Metrics (L1 vendor)
    mry.revenue AS mry_revenue,
    mry.gp AS mry_gp,
    mry.ebit AS mry_ebit,
    mry.ebitda AS mry_ebitda,
    mry.netinccmn AS mry_netinccmn,
    mry.epsdil AS mry_epsdil,
    mry.fcf AS mry_fcf,
    mry.dps AS mry_dps,
    mry.grossmargin AS mry_grossmargin,
    mry.netmargin AS mry_netmargin,
    mry.ebitdamargin AS mry_ebitdamargin,
    -- MRY growth/ranks (L2)
    mry_derived.revenue_yoy_growth AS mry_revenue_yoy_growth,
    mry_derived.revenue_yoy_growth_industry_rank AS mry_revenue_yoy_growth_industry_rank,
    mry_derived.revenue_yoy_growth_sector_rank AS mry_revenue_yoy_growth_sector_rank,
    mry_derived.netmargin_industry_rank AS mry_netmargin_industry_rank,
    mry_derived.netmargin_sector_rank AS mry_netmargin_sector_rank,
    mry_derived.ebitdamargin_industry_rank AS mry_ebitdamargin_industry_rank,
    mry_derived.ebitdamargin_sector_rank AS mry_ebitdamargin_sector_rank,

    -- ARY Metrics (L1 vendor)
    ary.revenue AS ary_revenue,
    ary.gp AS ary_gp,
    ary.ebit AS ary_ebit,
    ary.ebitda AS ary_ebitda,
    ary.netinccmn AS ary_netinccmn,
    ary.epsdil AS ary_epsdil,
    ary.fcf AS ary_fcf,
    ary.dps AS ary_dps,
    ary.grossmargin AS ary_grossmargin,
    ary.netmargin AS ary_netmargin,
    ary.ebitdamargin AS ary_ebitdamargin,
    ary.currentratio AS ary_currentratio,
    ary.de AS ary_de,
    -- ARY growth/ranks (L2)
    ary_derived.revenue_yoy_growth AS ary_revenue_yoy_growth,
    ary_derived.eps_growth_yoy AS ary_eps_growth_yoy,
    ary_derived.revenue_yoy_growth_industry_rank AS ary_revenue_yoy_growth_industry_rank,
    ary_derived.revenue_yoy_growth_sector_rank AS ary_revenue_yoy_growth_sector_rank,
    ary_derived.netmargin_industry_rank AS ary_netmargin_industry_rank,
    ary_derived.netmargin_sector_rank AS ary_netmargin_sector_rank,
    ary_derived.ebitdamargin_industry_rank AS ary_ebitdamargin_industry_rank,
    ary_derived.ebitdamargin_sector_rank AS ary_ebitdamargin_sector_rank,
    ary_derived.eps_growth_3y_cagr AS ary_eps_growth_3y_cagr,
    ary_derived.eps_acceleration_fy AS ary_eps_acceleration_fy,
    ary_derived.revenue_growth_3y_cagr AS ary_revenue_growth_3y_cagr,
    ary_derived.revenue_acceleration_fy AS ary_revenue_acceleration_fy,

    -- ART CapEx (L1 + L2)
    art.ncfo AS art_ncfo,
    art.capex AS art_capex,
    art.depamor AS art_depamor,
    art.fxusd AS art_fxusd,
    art.capex_abs AS art_capex_abs,
    art.fcf AS art_fcf,
    art.revenue AS art_revenue,
    art.roic AS art_roic,
    art_derived.ocf_margin AS art_ocf_margin,
    art_derived.fcf_margin AS art_fcf_margin,
    art_derived.capex_to_ocf AS art_capex_to_ocf,
    art_derived.fcf_to_ocf AS art_fcf_to_ocf,
    art_derived.capex_to_da AS art_capex_to_da,
    art_derived.fcf_recon_gap AS art_fcf_recon_gap,
    art_derived.capex_yoy_growth AS art_capex_yoy_growth,
    art_derived.capex_vs_5y AS art_capex_vs_5y,
    art_derived.capex_to_ocf_industry_rank AS art_capex_to_ocf_industry_rank,
    art_derived.capex_to_ocf_sector_rank AS art_capex_to_ocf_sector_rank,
    art_derived.cash_posture AS art_cash_posture,
    art_derived.cash_posture_disagree AS art_cash_posture_disagree

FROM daily_metrics dm FINAL
INNER JOIN tickers t FINAL ON dm.ticker = t.ticker
INNER JOIN tickers_needing_update tnu ON dm.ticker = tnu.ticker
ASOF LEFT JOIN mrt FINAL ON dm.ticker = mrt.ticker AND dm.date >= mrt.date
ASOF LEFT JOIN mrt_derived FINAL ON dm.ticker = mrt_derived.ticker AND dm.date >= mrt_derived.date
ASOF LEFT JOIN art FINAL ON dm.ticker = art.ticker AND dm.date >= art.date
ASOF LEFT JOIN art_derived FINAL ON dm.ticker = art_derived.ticker AND dm.date >= art_derived.date
ASOF LEFT JOIN mrq FINAL ON dm.ticker = mrq.ticker AND dm.date >= mrq.date
ASOF LEFT JOIN mrq_derived FINAL ON dm.ticker = mrq_derived.ticker AND dm.date >= mrq_derived.date
ASOF LEFT JOIN arq FINAL ON dm.ticker = arq.ticker AND dm.date >= arq.date
ASOF LEFT JOIN arq_derived FINAL ON dm.ticker = arq_derived.ticker AND dm.date >= arq_derived.date
ASOF LEFT JOIN mry FINAL ON dm.ticker = mry.ticker AND dm.date >= mry.date
ASOF LEFT JOIN mry_derived FINAL ON dm.ticker = mry_derived.ticker AND dm.date >= mry_derived.date
ASOF LEFT JOIN ary FINAL ON dm.ticker = ary.ticker AND dm.date >= ary.date
ASOF LEFT JOIN ary_derived FINAL ON dm.ticker = ary_derived.ticker AND dm.date >= ary_derived.date
WHERE dm.date >= toDate({chunk_start_date:String}) AND dm.date <= toDate({chunk_end_date:String})
AND tnu.needs_update = 1;
