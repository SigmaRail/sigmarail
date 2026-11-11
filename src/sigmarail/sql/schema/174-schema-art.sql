-- kind=vendor_copy layer=L1
-- Schema for art table (As-Reported Trailing / SF1 dimension ART).
-- Episode A1 CapEx path: vendor_copy only (no derived ratios or ranks).
CREATE TABLE IF NOT EXISTS art
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar Date (e.g., end of quarter) for which ART data is reported.',
    `roa` Nullable(Float64) COMMENT 'kind=vendor_copy. Return on Average Assets (ART).',
    `roe` Nullable(Float64) COMMENT 'kind=vendor_copy. Return on Average Equity (ART).',
    `roic` Nullable(Float64) COMMENT 'kind=vendor_copy. Return on Invested Capital (ART).',
    `revenue` Nullable(Float64) COMMENT 'kind=vendor_copy. Revenues (ART).',
    `gp` Nullable(Float64) COMMENT 'kind=vendor_copy. Gross Profit (ART).',
    `ebit` Nullable(Float64) COMMENT 'kind=vendor_copy. EBIT (ART).',
    `ebitda` Nullable(Float64) COMMENT 'kind=vendor_copy. EBITDA (ART).',
    `netinccmn` Nullable(Float64) COMMENT 'kind=vendor_copy. Net Income Common Stock (ART).',
    `epsdil` Nullable(Float64) COMMENT 'kind=vendor_copy. Earnings per Diluted Share (ART).',
    `fcf` Nullable(Float64) COMMENT 'kind=vendor_copy. Free Cash Flow (ART): typically NCFO + CapEx (CapEx signed negative).',
    `assetsavg` Nullable(Float64) COMMENT 'kind=vendor_copy. Average Total Assets (ART).',
    `equityavg` Nullable(Float64) COMMENT 'kind=vendor_copy. Average Shareholders Equity (ART).',
    `invcapavg` Nullable(Float64) COMMENT 'kind=vendor_copy. Average Invested Capital (ART).',
    `currentratio` Nullable(Float64) COMMENT 'kind=vendor_copy. Current Ratio (ART).',
    `de` Nullable(Float64) COMMENT 'kind=vendor_copy. Debt to Equity Ratio (ART).',
    `grossmargin` Nullable(Float64) COMMENT 'kind=vendor_copy. Gross Margin (ART).',
    `netmargin` Nullable(Float64) COMMENT 'kind=vendor_copy. Net Profit Margin (ART).',
    `ncfo` Nullable(Float64) COMMENT 'kind=vendor_copy. Net Cash Flow from Operations (ART) from SF1.',
    `capex` Nullable(Float64) COMMENT 'kind=vendor_copy. Capital Expenditures (ART) from SF1. Typically negative (cash outflow).',
    `depamor` Nullable(Float64) COMMENT 'kind=vendor_copy. Depreciation, Amortization & Accretion (ART) from SF1.',
    `fxusd` Nullable(Float64) COMMENT 'kind=vendor_copy. Foreign currency to USD exchange rate from SF1 ART.',
    `capex_abs` Nullable(Float64) COMMENT 'kind=vendor_copy. Absolute CapEx spend: abs(capex).',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=vendor_copy layer=L1 target=art sf1_dimension=ART';

-- Managed transform view for target: art
-- kind=vendor_copy layer=L1
-- Populates art (SF1 ART vendor fields only). CapEx ratios → art_derived (L2).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
--
DROP VIEW IF EXISTS xform_art;

CREATE VIEW IF NOT EXISTS xform_art (
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
COMMENT '{"order":15,"target":"art","sources":["sf1"],"chunk_size":"6m","sf1_dimension":"ART"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        art.ticker,
        count() as target_row_count,
        max(art.lastupdated) as target_last_updated
    FROM art art FINAL
    WHERE art.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY art.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM sf1 FINAL
    WHERE dimension = 'ART'
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
WHERE s1.dimension = 'ART'
  AND s1.calendardate BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
  AND s1.ticker IN (
      SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
  );
