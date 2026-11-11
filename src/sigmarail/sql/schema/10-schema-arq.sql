-- kind=vendor_copy layer=L1
-- Schema for arq table (Annual Report Quarter metrics)
-- L1 writes vendor SF1 ARQ fields only; growth/acceleration live in L2 `arq_derived`.
-- Calc columns below remain for additive rollback (Episode A0); do not DROP yet.
CREATE TABLE IF NOT EXISTS arq
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar date of the quarter end for which ARQ data is reported.',
    `revenue` Nullable(Float64) COMMENT 'Revenues (ARQ). Amount of Revenue recognised for the quarter.',
    `gp` Nullable(Float64) COMMENT 'Gross Profit (ARQ): Revenue - CostOfRevenue for the quarter.',
    `ebit` Nullable(Float64) COMMENT 'Earnings Before Interest & Taxes (EBIT) (ARQ) for the quarter.',
    `ebitda` Nullable(Float64) COMMENT 'Earnings Before Interest, Taxes, Depreciation & Amortization (EBITDA) (ARQ) for the quarter.',
    `netinccmn` Nullable(Float64) COMMENT 'Net Income Common Stock (ARQ) for the quarter.',
    `epsdil` Nullable(Float64) COMMENT 'Earnings per Diluted Share (ARQ) for the quarter.',
    `fcf` Nullable(Float64) COMMENT 'Free Cash Flow (ARQ): NetCashFlowFromOperations - CapitalExpenditures for the quarter.',
    `grossmargin` Nullable(Float64) COMMENT 'Gross Margin (ARQ): GrossProfit / Revenue for the quarter.',
    `netmargin` Nullable(Float64) COMMENT 'Net Profit Margin (ARQ): NetIncomeCommon / Revenue for the quarter.',
    `ebitdamargin` Nullable(Float64) COMMENT 'EBITDA Margin (ARQ): EBITDA / Revenue for the quarter.',
    `currentratio` Nullable(Float64) COMMENT 'Current Ratio (ARQ): CurrentAssets / CurrentLiabilities at quarter end.',
    `de` Nullable(Float64) COMMENT 'Debt to Equity Ratio (ARQ): TotalLiabilities / ShareholdersEquity at quarter end.',
    `revenue_growth_yoy` Nullable(Float64) COMMENT 'Year over year Revenue growth (Current ARQ Revenue vs ARQ Revenue from 4 quarters ago).',
    `eps_growth_yoy` Nullable(Float64) COMMENT 'Year over year EPS growth (Current ARQ EPS vs ARQ EPS from 4 quarters ago).',
    `fcf_growth_yoy` Nullable(Float64) COMMENT 'Year over year FCF growth (Current ARQ FCF vs ARQ FCF from 4 quarters ago).',
    `netincome_growth_yoy` Nullable(Float64) COMMENT 'Year over year Net Income growth (Current ARQ Net Income vs ARQ Net Income from 4 quarters ago).',
    `eps_growth_qoq` Nullable(Float64) COMMENT 'Quarter-over-Quarter EPS Growth (Current ARQ EPS vs Previous ARQ EPS).',
    `eps_acceleration_qoq` Nullable(Int8) COMMENT 'EPS Growth Acceleration QoQ: 1 if current QoQ EPS growth > previous QoQ EPS growth, 0 otherwise, NULL if not determinable.',
    `revenue_growth_qoq` Nullable(Float64) COMMENT 'Quarter-over-Quarter Revenue Growth (Current ARQ Revenue vs Previous ARQ Revenue).',
    `revenue_acceleration_qoq` Nullable(Int8) COMMENT 'Revenue Growth Acceleration QoQ: 1 if current QoQ Revenue growth > previous QoQ Revenue growth, 0 otherwise, NULL if not determinable.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: arq
-- kind=vendor_copy layer=L1
-- Populates arq (SF1 ARQ vendor fields only). Growth/acceleration → arq_derived (L2).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_arq;

CREATE VIEW IF NOT EXISTS xform_arq (
    ticker,
    date,
    revenue,
    gp,
    ebit,
    ebitda,
    netinccmn,
    epsdil,
    fcf,
    grossmargin,
    netmargin,
    ebitdamargin,
    currentratio,
    de,
    lastupdated
)
COMMENT '{"order":10,"target":"arq","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"ARQ"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        arq.ticker,
        count() as target_row_count,
        max(arq.lastupdated) as target_last_updated
    FROM arq arq FINAL
    WHERE arq.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY arq.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM sf1 FINAL
    WHERE dimension = 'ARQ'
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
    s1.fcf,
    s1.grossmargin,
    s1.netmargin,
    s1.ebitdamargin,
    s1.currentratio,
    s1.de,
    now() AS lastupdated
FROM sf1 s1 FINAL
WHERE s1.dimension = 'ARQ'
  AND s1.calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND s1.ticker IN (
      SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
  );
