-- kind=vendor_copy layer=L1
-- Schema for mry table (Most Recent Year metrics)
-- L1 writes vendor SF1 MRY fields only; growth/ranks live in L2 `mry_derived`.
-- Calc columns below remain for additive rollback (Episode A0); do not DROP yet.
CREATE TABLE IF NOT EXISTS mry
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar Date (fiscal year end) for which MRY data is reported.',
    `revenue` Nullable(Float64) COMMENT 'Revenues (MRY). Amount of Revenue recognised for the fiscal year.',
    `gp` Nullable(Float64) COMMENT 'Gross Profit (MRY): Revenue - CostOfRevenue for the fiscal year.',
    `ebit` Nullable(Float64) COMMENT 'Earnings Before Interest & Taxes (EBIT) (MRY) for the fiscal year.',
    `ebitda` Nullable(Float64) COMMENT 'Earnings Before Interest, Taxes, Depreciation & Amortization (EBITDA) (MRY) for the fiscal year.',
    `netinccmn` Nullable(Float64) COMMENT 'Net Income Common Stock (MRY) for the fiscal year.',
    `epsdil` Nullable(Float64) COMMENT 'Earnings per Diluted Share (MRY) for the fiscal year.',
    `fcf` Nullable(Float64) COMMENT 'Free Cash Flow (MRY): NetCashFlowFromOperations - CapitalExpenditures for the fiscal year.',
    `dps` Nullable(Float64) COMMENT 'Dividends per Basic Common Share (MRY) for the fiscal year.',
    `grossmargin` Nullable(Float64) COMMENT 'Gross Margin (MRY): GrossProfit / Revenue for the fiscal year.',
    `netmargin` Nullable(Float64) COMMENT 'Net Profit Margin (MRY): NetIncomeCommon / Revenue for the fiscal year.',
    `ebitdamargin` Nullable(Float64) COMMENT 'EBITDA Margin (MRY): EBITDA / Revenue for the fiscal year.',
    `revenue_yoy_growth` Nullable(Float64) COMMENT 'Year over year Revenue growth (Current MRY Revenue vs Prior MRY Revenue).',
    `revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY Revenue YoY Growth (0-100).',
    `revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY Revenue YoY Growth (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRY EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRY EBITDA Margin (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: mry
-- kind=vendor_copy layer=L1
-- Populates mry (SF1 MRY vendor fields only). Growth/ranks → mry_derived (L2).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mry;

CREATE VIEW IF NOT EXISTS xform_mry (
    ticker,
    date,
    revenue,
    gp,
    ebit,
    ebitda,
    netinccmn,
    epsdil,
    fcf,
    dps,
    grossmargin,
    netmargin,
    ebitdamargin,
    lastupdated
)
COMMENT '{"order":14,"target":"mry","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"MRY"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        mry.ticker,
        count() as target_row_count,
        max(mry.lastupdated) as target_last_updated
    FROM mry mry FINAL
    WHERE mry.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY mry.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM sf1 FINAL
    WHERE dimension = 'MRY'
      AND calendardate BETWEEN toDate({chunk_start_date:String}) - INTERVAL 400 DAY AND {chunk_end_date:String}
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
)
SELECT
    s1.ticker,
    s1.calendardate AS date,
    s1.revenue, s1.gp, s1.ebit, s1.ebitda, s1.netinccmn,
    s1.epsdil, s1.fcf, s1.dps, s1.grossmargin, s1.netmargin, s1.ebitdamargin,
    now() AS lastupdated
FROM sf1 s1 FINAL
WHERE s1.dimension = 'MRY'
  AND s1.calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND s1.ticker IN (
      SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
  );
