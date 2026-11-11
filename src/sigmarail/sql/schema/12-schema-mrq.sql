-- kind=vendor_copy layer=L1
-- Schema for mrq table (Most Recent Quarter metrics)
-- L1 writes vendor SF1 MRQ fields only; margin ranks live in L2 `mrq_derived`.
-- Source dimension is MRQ (not ARQ). MRQ may be sparser than ARQ in SF1; still use MRQ per Episode A0.
-- Calc columns below remain for additive rollback; do not DROP yet.
CREATE TABLE IF NOT EXISTS mrq
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar Date (end of quarter) for which MRQ data is reported.',
    `revenue` Nullable(Float64) COMMENT 'Revenues (MRQ). Amount of Revenue recognised for the quarter.',
    `gp` Nullable(Float64) COMMENT 'Gross Profit (MRQ): Revenue - CostOfRevenue for the quarter.',
    `ebit` Nullable(Float64) COMMENT 'Earnings Before Interest & Taxes (EBIT) (MRQ) for the quarter.',
    `ebitda` Nullable(Float64) COMMENT 'Earnings Before Interest, Taxes, Depreciation & Amortization (EBITDA) (MRQ) for the quarter.',
    `netinccmn` Nullable(Float64) COMMENT 'Net Income Common Stock (MRQ) for the quarter.',
    `epsdil` Nullable(Float64) COMMENT 'Earnings per Diluted Share (MRQ) for the quarter.',
    `grossmargin` Nullable(Float64) COMMENT 'Gross Margin (MRQ): GrossProfit / Revenue for the quarter.',
    `netmargin` Nullable(Float64) COMMENT 'Net Profit Margin (MRQ): NetIncomeCommon / Revenue for the quarter.',
    `ebitdamargin` Nullable(Float64) COMMENT 'EBITDA Margin (MRQ): EBITDA / Revenue for the quarter.',
    `currentratio` Nullable(Float64) COMMENT 'Current Ratio (MRQ): CurrentAssets / CurrentLiabilities at quarter end.',
    `de` Nullable(Float64) COMMENT 'Debt to Equity Ratio (MRQ): TotalLiabilities / ShareholdersEquity at quarter end.',
    `fcf` Nullable(Float64) COMMENT 'Free Cash Flow (MRQ): NetCashFlowFromOperations - CapitalExpenditures for the quarter.',
    `grossmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ Gross Margin (0-100).',
    `grossmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ Gross Margin (0-100).',
    `netmargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ Net Margin (0-100).',
    `netmargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ Net Margin (0-100).',
    `ebitdamargin_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for MRQ EBITDA Margin (0-100).',
    `ebitdamargin_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for MRQ EBITDA Margin (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: mrq
-- kind=vendor_copy layer=L1
-- Populates mrq from SF1 dimension = 'MRQ' (vendor fields only).
-- Margin industry/sector ranks → mrq_derived (L2).
--
-- NOTE (Episode A0): Previously this transform incorrectly filtered dimension = 'ARQ'.
-- Prefer MRQ even when SF1 MRQ coverage is sparser than ARQ — do not fall back to ARQ.
--
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mrq;

CREATE VIEW IF NOT EXISTS xform_mrq (
    ticker,
    date,
    revenue,
    gp,
    ebit,
    ebitda,
    netinccmn,
    epsdil,
    grossmargin,
    netmargin,
    ebitdamargin,
    currentratio,
    de,
    fcf,
    lastupdated
)
COMMENT '{"order":12,"target":"mrq","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"MRQ"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        mrq.ticker,
        count() as target_row_count,
        max(mrq.lastupdated) as target_last_updated
    FROM mrq mrq FINAL
    WHERE mrq.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY mrq.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM sf1 FINAL
    WHERE dimension = 'MRQ'
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
    s1.revenue,
    s1.gp,
    s1.ebit,
    s1.ebitda,
    s1.netinccmn,
    s1.epsdil,
    s1.grossmargin,
    s1.netmargin,
    s1.ebitdamargin,
    s1.currentratio,
    s1.de,
    s1.fcf,
    now() AS lastupdated
FROM sf1 s1 FINAL
WHERE s1.dimension = 'MRQ'
  AND s1.calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND s1.ticker IN (
      SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
  );
