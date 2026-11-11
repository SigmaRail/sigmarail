-- kind=vendor_copy layer=L1
-- Schema for ary table (Annual Report Year metrics)
-- L1 writes vendor SF1 ARY fields only; growth/ranks/CAGR live in L2 `ary_derived`.
-- Calc columns below remain for additive rollback (Episode A0); do not DROP yet.
CREATE TABLE IF NOT EXISTS ary
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar date of the fiscal year end for which ARY data is reported.',
    `revenue` Nullable(Float64) COMMENT 'Revenues (ARY). Amount of Revenue recognised for the fiscal year.',
    `gp` Nullable(Float64) COMMENT 'Gross Profit (ARY): Revenue - CostOfRevenue for the fiscal year.',
    `ebit` Nullable(Float64) COMMENT 'Earnings Before Interest & Taxes (EBIT) (ARY) for the fiscal year.',
    `ebitda` Nullable(Float64) COMMENT 'Earnings Before Interest, Taxes, Depreciation & Amortization (EBITDA) (ARY) for the fiscal year.',
    `netinccmn` Nullable(Float64) COMMENT 'Net Income Common Stock (ARY) for the fiscal year.',
    `epsdil` Nullable(Float64) COMMENT 'Earnings per Diluted Share (ARY) for the fiscal year.',
    `fcf` Nullable(Float64) COMMENT 'Free Cash Flow (ARY): NetCashFlowFromOperations - CapitalExpenditures for the fiscal year.',
    `dps` Nullable(Float64) COMMENT 'Dividends per Basic Common Share (ARY) for the fiscal year.',
    `grossmargin` Nullable(Float64) COMMENT 'Gross Margin (ARY): GrossProfit / Revenue for the fiscal year.',
    `netmargin` Nullable(Float64) COMMENT 'Net Profit Margin (ARY): NetIncomeCommon / Revenue for the fiscal year.',
    `ebitdamargin` Nullable(Float64) COMMENT 'EBITDA Margin (ARY): EBITDA / Revenue for the fiscal year.',
    `currentratio` Nullable(Float64) COMMENT 'Current Ratio (ARY): CurrentAssets / CurrentLiabilities at fiscal year end.',
    `de` Nullable(Float64) COMMENT 'Debt to Equity Ratio (ARY): TotalLiabilities / ShareholdersEquity at fiscal year end.',
    `revenue_yoy_growth` Nullable(Float64) COMMENT 'Year over year Revenue growth (Current ARY Revenue vs Prior ARY Revenue).',
    `eps_growth_yoy` Nullable(Float64) COMMENT 'Year over year EPS growth (Current ARY EPS vs Prior ARY EPS).',
    `revenue_yoy_growth_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY Revenue YoY Growth (0-100).',
    `revenue_yoy_growth_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY Revenue YoY Growth (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for ARY EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for ARY EBITDA Margin (0-100).',
    `eps_growth_3y_cagr` Nullable(Float64) COMMENT '3-Year EPS Growth Compound Annual Growth Rate (ARY).',
    `eps_acceleration_fy` Nullable(Int8) COMMENT 'EPS Growth Acceleration Fiscal Year: 1 if current ARY YoY EPS growth > previous ARY YoY EPS growth, 0 otherwise, NULL if not determinable.',
    `revenue_growth_3y_cagr` Nullable(Float64) COMMENT '3-Year Revenue Growth Compound Annual Growth Rate (ARY).',
    `revenue_acceleration_fy` Nullable(Int8) COMMENT 'Revenue Growth Acceleration Fiscal Year: 1 if current ARY YoY Revenue growth > previous ARY YoY Revenue growth, 0 otherwise, NULL if not determinable.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: ary
-- kind=vendor_copy layer=L1
-- Populates ary (SF1 ARY vendor fields only). Growth/ranks/CAGR → ary_derived (L2).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_ary;

CREATE VIEW IF NOT EXISTS xform_ary (
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
    currentratio,
    de,
    lastupdated
)
COMMENT '{"order":11,"target":"ary","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"ARY"}'
AS
SELECT
    ticker,
    calendardate AS date,
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
    currentratio,
    de,
    now() AS lastupdated
FROM sf1 FINAL
WHERE dimension = 'ARY'
  AND calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
