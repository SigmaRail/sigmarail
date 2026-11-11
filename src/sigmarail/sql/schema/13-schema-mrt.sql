-- kind=vendor_copy layer=L1
-- Schema for mrt table (Most Recent Trailing metrics)
-- L1 writes vendor SF1 MRT fields only; YoY growth/ranks live in L2 `mrt_derived`.
-- Calc columns below remain for additive rollback (Episode A0); do not DROP yet.
CREATE TABLE IF NOT EXISTS mrt
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar Date (e.g., end of quarter) for which TTM data is reported.',
    `roa` Nullable(Float64) COMMENT 'Return on Average Assets (TTM): NetIncomeCommon / AverageTotalAssets.',
    `roe` Nullable(Float64) COMMENT 'Return on Average Equity (TTM): NetIncomeCommon / AverageShareholdersEquity.',
    `roic` Nullable(Float64) COMMENT 'Return on Invested Capital (TTM): EBIT / AverageInvestedCapital.',
    `revenue` Nullable(Float64) COMMENT 'Revenues (TTM). The amount of Revenue recognised from goods sold or services rendered.',
    `gp` Nullable(Float64) COMMENT 'Gross Profit (TTM): Revenue - CostOfRevenue.',
    `ebit` Nullable(Float64) COMMENT 'Earnings Before Interest & Taxes (EBIT) (TTM): Revenue - COGS - OperatingExpenses.',
    `ebitda` Nullable(Float64) COMMENT 'Earnings Before Interest, Taxes, Depreciation & Amortization (EBITDA) (TTM): EBIT + DepreciationAndAmortization.',
    `netinccmn` Nullable(Float64) COMMENT 'Net Income Common Stock (TTM): Net income available to common shareholders.',
    `epsdil` Nullable(Float64) COMMENT 'Earnings per Diluted Share (TTM): NetIncomeCommon / WeightedAverageSharesDiluted.',
    `fcf` Nullable(Float64) COMMENT 'Free Cash Flow (TTM): NetCashFlowFromOperations - CapitalExpenditures.',
    `ncfo` Nullable(Float64) COMMENT 'kind=vendor_copy. Net Cash Flow from Operations (TTM) from SF1 MRT.',
    `capex` Nullable(Float64) COMMENT 'kind=vendor_copy. Capital Expenditures (TTM) from SF1 MRT. Typically negative (cash outflow).',
    `depamor` Nullable(Float64) COMMENT 'kind=vendor_copy. Depreciation, Amortization & Accretion (TTM) from SF1 MRT.',
    `fxusd` Nullable(Float64) COMMENT 'kind=vendor_copy. Foreign currency to USD exchange rate from SF1 MRT (1.0 for USD reporters).',
    `capex_abs` Nullable(Float64) COMMENT 'kind=vendor_copy. Absolute CapEx spend: abs(capex).',
    `assetsavg` Nullable(Float64) COMMENT 'Average Total Assets (TTM). Used in ROA calculation.',
    `equityavg` Nullable(Float64) COMMENT 'Average Shareholders Equity (TTM). Used in ROE calculation.',
    `invcapavg` Nullable(Float64) COMMENT 'Average Invested Capital (TTM). Used in ROIC calculation.',
    `currentratio` Nullable(Float64) COMMENT 'Current Ratio (TTM): CurrentAssets / CurrentLiabilities.',
    `de` Nullable(Float64) COMMENT 'Debt to Equity Ratio (TTM): TotalLiabilities / ShareholdersEquity.',
    `grossmargin` Nullable(Float64) COMMENT 'Gross Margin (TTM): GrossProfit / Revenue.',
    `netmargin` Nullable(Float64) COMMENT 'Net Profit Margin (TTM): NetIncomeCommon / Revenue.',
    `roa_yoy_growth` Nullable(Float64) COMMENT 'Year over year ROA growth (Current TTM ROA vs Prior Year TTM ROA).',
    `roe_yoy_growth` Nullable(Float64) COMMENT 'Year over year ROE growth (Current TTM ROE vs Prior Year TTM ROE).',
    `roic_yoy_growth` Nullable(Float64) COMMENT 'Year over year ROIC growth (Current TTM ROIC vs Prior Year TTM ROIC).',
    `roa_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROA (0-100).',
    `roe_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROE (0-100).',
    `roic_industry_rank` Nullable(Float64) COMMENT 'Industry percentile rank for TTM ROIC (0-100).',
    `roa_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROA (0-100).',
    `roe_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROE (0-100).',
    `roic_sector_rank` Nullable(Float64) COMMENT 'Sector percentile rank for TTM ROIC (0-100).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: mrt
-- kind=vendor_copy layer=L1
-- Populates mrt (SF1 MRT vendor fields only). YoY growth/ranks → mrt_derived (L2).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_mrt;

CREATE VIEW IF NOT EXISTS xform_mrt (
    ticker,
    date,
    roa,
    roe,
    roic,
    revenue,
    ebit,
    netinccmn,
    assetsavg,
    equityavg,
    invcapavg,
    currentratio,
    de,
    grossmargin,
    netmargin,
    gp,
    ebitda,
    epsdil,
    fcf,
    ncfo,
    capex,
    depamor,
    fxusd,
    capex_abs,
    lastupdated
)
COMMENT '{"order":13,"target":"mrt","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"MRT"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        mrt.ticker,
        count() as target_row_count,
        max(mrt.lastupdated) as target_last_updated
    FROM mrt mrt FINAL
    WHERE mrt.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY mrt.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM sf1 FINAL
    WHERE dimension = 'MRT'
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
    s1.roa,
    s1.roe,
    s1.roic,
    s1.revenue,
    s1.ebit,
    s1.netinccmn,
    s1.assetsavg,
    s1.equityavg,
    s1.invcapavg,
    s1.currentratio,
    s1.de,
    s1.grossmargin,
    s1.netmargin,
    s1.gp,
    s1.ebitda,
    s1.epsdil,
    s1.fcf,
    s1.ncfo,
    s1.capex,
    s1.depamor,
    s1.fxusd,
    abs(s1.capex) AS capex_abs,
    now() AS lastupdated
FROM sf1 s1 FINAL
WHERE s1.dimension = 'MRT'
  AND s1.calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND s1.ticker IN (
      SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
  );
