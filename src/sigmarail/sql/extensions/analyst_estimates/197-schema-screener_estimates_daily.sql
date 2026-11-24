-- =============================================================================
-- TABLE: ext_analyst_estimates_screener_estimates_daily
-- kind=delivery_projection layer=L7
-- Wide daily consensus for universe_query_v1 (prefix es).
-- =============================================================================

CREATE TABLE IF NOT EXISTS ext_analyst_estimates_screener_estimates_daily
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date (asof last snapshot <= date)',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version',
    `eps_cq_mean` Float64 DEFAULT 0 COMMENT 'EPS current-quarter mean',
    `eps_nq_mean` Float64 DEFAULT 0 COMMENT 'EPS next-quarter mean',
    `eps_cy_mean` Float64 DEFAULT 0 COMMENT 'EPS current-year mean',
    `eps_ny_mean` Float64 DEFAULT 0 COMMENT 'EPS next-year mean',
    `eps_cq_median` Float64 DEFAULT 0 COMMENT 'EPS CQ median',
    `eps_nq_median` Float64 DEFAULT 0 COMMENT 'EPS NQ median',
    `eps_cy_median` Float64 DEFAULT 0 COMMENT 'EPS CY median',
    `eps_ny_median` Float64 DEFAULT 0 COMMENT 'EPS NY median',
    `eps_cq_n` UInt16 DEFAULT 0 COMMENT 'EPS CQ estimate count',
    `eps_nq_n` UInt16 DEFAULT 0 COMMENT 'EPS NQ estimate count',
    `eps_cy_n` UInt16 DEFAULT 0 COMMENT 'EPS CY estimate count',
    `eps_ny_n` UInt16 DEFAULT 0 COMMENT 'EPS NY estimate count',
    `eps_cq_high` Float64 DEFAULT 0 COMMENT 'EPS CQ high',
    `eps_nq_high` Float64 DEFAULT 0 COMMENT 'EPS NQ high',
    `eps_cy_high` Float64 DEFAULT 0 COMMENT 'EPS CY high',
    `eps_ny_high` Float64 DEFAULT 0 COMMENT 'EPS NY high',
    `eps_cq_low` Float64 DEFAULT 0 COMMENT 'EPS CQ low',
    `eps_nq_low` Float64 DEFAULT 0 COMMENT 'EPS NQ low',
    `eps_cy_low` Float64 DEFAULT 0 COMMENT 'EPS CY low',
    `eps_ny_low` Float64 DEFAULT 0 COMMENT 'EPS NY low',
    `sales_cq_mean` Float64 DEFAULT 0 COMMENT 'Sales CQ mean',
    `sales_nq_mean` Float64 DEFAULT 0 COMMENT 'Sales NQ mean',
    `sales_cy_mean` Float64 DEFAULT 0 COMMENT 'Sales CY mean',
    `sales_ny_mean` Float64 DEFAULT 0 COMMENT 'Sales NY mean',
    `sales_cq_median` Float64 DEFAULT 0 COMMENT 'Sales CQ median',
    `sales_nq_median` Float64 DEFAULT 0 COMMENT 'Sales NQ median',
    `sales_cy_median` Float64 DEFAULT 0 COMMENT 'Sales CY median',
    `sales_ny_median` Float64 DEFAULT 0 COMMENT 'Sales NY median',
    `sales_cq_n` UInt16 DEFAULT 0 COMMENT 'Sales CQ count',
    `sales_nq_n` UInt16 DEFAULT 0 COMMENT 'Sales NQ count',
    `sales_cy_n` UInt16 DEFAULT 0 COMMENT 'Sales CY count',
    `sales_ny_n` UInt16 DEFAULT 0 COMMENT 'Sales NY count',
    `sales_cq_high` Float64 DEFAULT 0 COMMENT 'Sales CQ high',
    `sales_nq_high` Float64 DEFAULT 0 COMMENT 'Sales NQ high',
    `sales_cy_high` Float64 DEFAULT 0 COMMENT 'Sales CY high',
    `sales_ny_high` Float64 DEFAULT 0 COMMENT 'Sales NY high',
    `sales_cq_low` Float64 DEFAULT 0 COMMENT 'Sales CQ low',
    `sales_nq_low` Float64 DEFAULT 0 COMMENT 'Sales NQ low',
    `sales_cy_low` Float64 DEFAULT 0 COMMENT 'Sales CY low',
    `sales_ny_low` Float64 DEFAULT 0 COMMENT 'Sales NY low',
    `eps_cq_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'EPS CQ mean Δ vs asof-90d / abs(prior)',
    `eps_nq_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'EPS NQ 90d revision',
    `eps_cy_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'EPS CY 90d revision',
    `eps_ny_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'EPS NY 90d revision',
    `sales_nq_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'Sales NQ 90d revision',
    `sales_ny_rev_pct_90d` Float64 DEFAULT 0 COMMENT 'Sales NY 90d revision',
    `eps_last_reported` Float64 DEFAULT 0 COMMENT 'Latest reported EPS at print',
    `eps_last_estimate` Float64 DEFAULT 0 COMMENT 'Latest EPS consensus estimate at print',
    `eps_last_surprise_pct` Float64 DEFAULT 0 COMMENT 'Latest reported EPS surprise vs estimate-at-print',
    `eps_beat_flag` Int8 DEFAULT 0 COMMENT 'Latest EPS print: 1 = Beat, -1 = Miss, 0 = In-line / none',
    `sales_last_reported` Float64 DEFAULT 0 COMMENT 'Latest reported sales at print',
    `sales_last_estimate` Float64 DEFAULT 0 COMMENT 'Latest sales consensus estimate at print',
    `sales_last_surprise_pct` Float64 DEFAULT 0 COMMENT 'Latest reported sales surprise vs estimate-at-print',
    `sales_beat_flag` Int8 DEFAULT 0 COMMENT 'Latest sales print: 1 = Beat, -1 = Miss, 0 = In-line / none',
    `est_vendor` LowCardinality(String) DEFAULT '' COMMENT 'Active vendor on this date',
    `eps_basis` LowCardinality(String) DEFAULT 'unknown' COMMENT 'street | gaap | bnri | unknown'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'L7 wide consensus; Alpha/Studio never see vendor period labels';

-- Managed transform view for target: ext_analyst_estimates_screener_estimates_daily
-- =============================================================================
-- TRANSFORM: Populate ext_analyst_estimates_screener_estimates_daily (L7 consensus delivery)
-- =============================================================================
--
-- Asof-align last consensus snapshot publicly available by the trading close.
-- 90d revision = Δ mean vs a same-period snapshot available at least 90 days
-- earlier (not a CQ/NQ slot roll, and not a later backfill keyed to old asof_date).
-- Surprise = latest actual period_end <= date. Px spine is restricted to
-- tickers present in ext_analyst_estimates_analyst_consensus_asof.
-- snaps/rev_tall are bounded to [chunk_start - 180d, chunk_end] so weekly
-- populate chunks prune monthly partitions instead of ASOF-joining 14M rows.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_estimates_daily;
CREATE VIEW IF NOT EXISTS xform_screener_estimates_daily (
    ticker,
    date,
    lastupdated,
    eps_cq_mean,
    eps_nq_mean,
    eps_cy_mean,
    eps_ny_mean,
    eps_cq_median,
    eps_nq_median,
    eps_cy_median,
    eps_ny_median,
    eps_cq_n,
    eps_nq_n,
    eps_cy_n,
    eps_ny_n,
    eps_cq_high,
    eps_nq_high,
    eps_cy_high,
    eps_ny_high,
    eps_cq_low,
    eps_nq_low,
    eps_cy_low,
    eps_ny_low,
    sales_cq_mean,
    sales_nq_mean,
    sales_cy_mean,
    sales_ny_mean,
    sales_cq_median,
    sales_nq_median,
    sales_cy_median,
    sales_ny_median,
    sales_cq_n,
    sales_nq_n,
    sales_cy_n,
    sales_ny_n,
    sales_cq_high,
    sales_nq_high,
    sales_cy_high,
    sales_ny_high,
    sales_cq_low,
    sales_nq_low,
    sales_cy_low,
    sales_ny_low,
    eps_cq_rev_pct_90d,
    eps_nq_rev_pct_90d,
    eps_cy_rev_pct_90d,
    eps_ny_rev_pct_90d,
    sales_nq_rev_pct_90d,
    sales_ny_rev_pct_90d,
    eps_last_surprise_pct,
    est_vendor,
    eps_basis,
    eps_last_reported,
    eps_last_estimate,
    eps_beat_flag,
    sales_last_reported,
    sales_last_estimate,
    sales_last_surprise_pct,
    sales_beat_flag
)
COMMENT '{"order":130,"target":"ext_analyst_estimates_screener_estimates_daily","sources":["ext_analyst_estimates_analyst_consensus_asof","ext_analyst_estimates_analyst_actuals","screener_price_tech_daily"],"chunk_size":"1w"}'
AS
WITH snaps AS (
    SELECT
        ticker,
        asof_date,
        available_at,
        metric,
        periodicity,
        relative_period,
        mean,
        median,
        high,
        low,
        n_estimates,
        vendor,
        eps_basis,
        period_end_date
    FROM ext_analyst_estimates_analyst_consensus_asof FINAL
    WHERE asof_date >= toDate({chunk_start_date:String}) - INTERVAL 180 DAY
      AND asof_date <= toDate({chunk_end_date:String})
      AND available_at > toDateTime64(0, 3, 'America/New_York')
),
snaps_single_vendor AS (
    -- If multiple feeds share a publication time, choose one complete,
    -- deterministic source rather than mixing fields across vendors.
    SELECT s.*
    FROM snaps AS s
    INNER JOIN (
        SELECT ticker, available_at, min(vendor) AS vendor
        FROM snaps
        GROUP BY ticker, available_at
    ) AS chosen USING (ticker, available_at, vendor)
),
rev_tall AS (
    SELECT
        cur.ticker,
        cur.asof_date,
        cur.available_at,
        cur.metric,
        cur.periodicity,
        cur.relative_period,
        cur.mean,
        cur.median,
        cur.high,
        cur.low,
        cur.n_estimates,
        cur.vendor,
        cur.eps_basis,
        if(prior.mean = 0, 0, (cur.mean - prior.mean) / abs(prior.mean)) AS rev_pct_90d
    FROM snaps_single_vendor AS cur
    ASOF LEFT JOIN snaps_single_vendor AS prior
        ON cur.ticker = prior.ticker
        AND cur.metric = prior.metric
        AND cur.periodicity = prior.periodicity
        AND cur.period_end_date = prior.period_end_date
        AND (cur.available_at - INTERVAL 90 DAY) >= prior.available_at
),
pivoted AS (
    SELECT
        ticker,
        available_at,
        anyIf(mean, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_mean,
        anyIf(mean, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_mean,
        anyIf(mean, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_mean,
        anyIf(mean, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_mean,
        anyIf(median, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_median,
        anyIf(median, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_median,
        anyIf(median, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_median,
        anyIf(median, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_median,
        anyIf(n_estimates, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_n,
        anyIf(n_estimates, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_n,
        anyIf(n_estimates, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_n,
        anyIf(n_estimates, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_n,
        anyIf(high, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_high,
        anyIf(high, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_high,
        anyIf(high, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_high,
        anyIf(high, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_high,
        anyIf(low, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_low,
        anyIf(low, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_low,
        anyIf(low, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_low,
        anyIf(low, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_low,
        anyIf(mean, metric = 'sales' AND periodicity = 'Q' AND relative_period = 0) AS sales_cq_mean,
        anyIf(mean, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_mean,
        anyIf(mean, metric = 'sales' AND periodicity = 'A' AND relative_period = 0) AS sales_cy_mean,
        anyIf(mean, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_mean,
        anyIf(median, metric = 'sales' AND periodicity = 'Q' AND relative_period = 0) AS sales_cq_median,
        anyIf(median, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_median,
        anyIf(median, metric = 'sales' AND periodicity = 'A' AND relative_period = 0) AS sales_cy_median,
        anyIf(median, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_median,
        anyIf(n_estimates, metric = 'sales' AND periodicity = 'Q' AND relative_period = 0) AS sales_cq_n,
        anyIf(n_estimates, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_n,
        anyIf(n_estimates, metric = 'sales' AND periodicity = 'A' AND relative_period = 0) AS sales_cy_n,
        anyIf(n_estimates, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_n,
        anyIf(high, metric = 'sales' AND periodicity = 'Q' AND relative_period = 0) AS sales_cq_high,
        anyIf(high, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_high,
        anyIf(high, metric = 'sales' AND periodicity = 'A' AND relative_period = 0) AS sales_cy_high,
        anyIf(high, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_high,
        anyIf(low, metric = 'sales' AND periodicity = 'Q' AND relative_period = 0) AS sales_cq_low,
        anyIf(low, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_low,
        anyIf(low, metric = 'sales' AND periodicity = 'A' AND relative_period = 0) AS sales_cy_low,
        anyIf(low, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_low,
        anyIf(rev_pct_90d, metric = 'eps' AND periodicity = 'Q' AND relative_period = 0) AS eps_cq_rev_pct_90d,
        anyIf(rev_pct_90d, metric = 'eps' AND periodicity = 'Q' AND relative_period = 1) AS eps_nq_rev_pct_90d,
        anyIf(rev_pct_90d, metric = 'eps' AND periodicity = 'A' AND relative_period = 0) AS eps_cy_rev_pct_90d,
        anyIf(rev_pct_90d, metric = 'eps' AND periodicity = 'A' AND relative_period = 1) AS eps_ny_rev_pct_90d,
        anyIf(rev_pct_90d, metric = 'sales' AND periodicity = 'Q' AND relative_period = 1) AS sales_nq_rev_pct_90d,
        anyIf(rev_pct_90d, metric = 'sales' AND periodicity = 'A' AND relative_period = 1) AS sales_ny_rev_pct_90d,
        any(vendor) AS est_vendor,
        any(eps_basis) AS eps_basis
    FROM rev_tall
    GROUP BY ticker, available_at
    ORDER BY ticker, available_at
),
surp_eps AS (
    SELECT
        ticker,
        available_at,
        argMax(period_end_date, (period_end_date, vendor, lastupdated)) AS period_end_date,
        argMax(reported, (period_end_date, vendor, lastupdated)) AS eps_last_reported,
        argMax(estimate_at_print, (period_end_date, vendor, lastupdated)) AS eps_last_estimate,
        argMax(surprise_pct, (period_end_date, vendor, lastupdated)) AS eps_last_surprise_pct,
        multiIf(eps_last_reported > eps_last_estimate, 1, eps_last_reported < eps_last_estimate, -1, 0) AS eps_beat_flag
    FROM ext_analyst_estimates_analyst_actuals FINAL
    WHERE metric = 'eps'
      AND available_at > toDateTime64(0, 3, 'America/New_York')
    GROUP BY ticker, available_at
    ORDER BY ticker, available_at
),
surp_sales AS (
    SELECT
        ticker,
        available_at,
        argMax(period_end_date, (period_end_date, vendor, lastupdated)) AS period_end_date,
        argMax(reported, (period_end_date, vendor, lastupdated)) AS sales_last_reported,
        argMax(estimate_at_print, (period_end_date, vendor, lastupdated)) AS sales_last_estimate,
        argMax(surprise_pct, (period_end_date, vendor, lastupdated)) AS sales_last_surprise_pct,
        multiIf(sales_last_reported > sales_last_estimate, 1, sales_last_reported < sales_last_estimate, -1, 0) AS sales_beat_flag
    FROM ext_analyst_estimates_analyst_actuals FINAL
    WHERE metric = 'sales'
      AND available_at > toDateTime64(0, 3, 'America/New_York')
    GROUP BY ticker, available_at
    ORDER BY ticker, available_at
)
SELECT
    px.ticker AS ticker,
    px.date AS date,
    now() AS lastupdated,
    e.eps_cq_mean,
    e.eps_nq_mean,
    e.eps_cy_mean,
    e.eps_ny_mean,
    e.eps_cq_median,
    e.eps_nq_median,
    e.eps_cy_median,
    e.eps_ny_median,
    e.eps_cq_n,
    e.eps_nq_n,
    e.eps_cy_n,
    e.eps_ny_n,
    e.eps_cq_high,
    e.eps_nq_high,
    e.eps_cy_high,
    e.eps_ny_high,
    e.eps_cq_low,
    e.eps_nq_low,
    e.eps_cy_low,
    e.eps_ny_low,
    e.sales_cq_mean,
    e.sales_nq_mean,
    e.sales_cy_mean,
    e.sales_ny_mean,
    e.sales_cq_median,
    e.sales_nq_median,
    e.sales_cy_median,
    e.sales_ny_median,
    e.sales_cq_n,
    e.sales_nq_n,
    e.sales_cy_n,
    e.sales_ny_n,
    e.sales_cq_high,
    e.sales_nq_high,
    e.sales_cy_high,
    e.sales_ny_high,
    e.sales_cq_low,
    e.sales_nq_low,
    e.sales_cy_low,
    e.sales_ny_low,
    e.eps_cq_rev_pct_90d,
    e.eps_nq_rev_pct_90d,
    e.eps_cy_rev_pct_90d,
    e.eps_ny_rev_pct_90d,
    e.sales_nq_rev_pct_90d,
    e.sales_ny_rev_pct_90d,
    ifNull(se.eps_last_surprise_pct, 0) AS eps_last_surprise_pct,
    ifNull(e.est_vendor, '') AS est_vendor,
    ifNull(e.eps_basis, 'unknown') AS eps_basis,
    ifNull(se.eps_last_reported, 0) AS eps_last_reported,
    ifNull(se.eps_last_estimate, 0) AS eps_last_estimate,
    ifNull(se.eps_beat_flag, 0) AS eps_beat_flag,
    ifNull(ss.sales_last_reported, 0) AS sales_last_reported,
    ifNull(ss.sales_last_estimate, 0) AS sales_last_estimate,
    ifNull(ss.sales_last_surprise_pct, 0) AS sales_last_surprise_pct,
    ifNull(ss.sales_beat_flag, 0) AS sales_beat_flag
FROM (
    SELECT ticker, date
    FROM screener_price_tech_daily FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM ext_analyst_estimates_analyst_consensus_asof GROUP BY ticker)
) AS px
ASOF LEFT JOIN pivoted AS e
    ON px.ticker = e.ticker
   AND toDateTime64(concat(toString(px.date), ' 15:59:59.999'), 3, 'America/New_York') >= e.available_at
ASOF LEFT JOIN surp_eps AS se
    ON px.ticker = se.ticker
   AND toDateTime64(concat(toString(px.date), ' 15:59:59.999'), 3, 'America/New_York') >= se.available_at
ASOF LEFT JOIN surp_sales AS ss
    ON px.ticker = ss.ticker
   AND toDateTime64(concat(toString(px.date), ' 15:59:59.999'), 3, 'America/New_York') >= ss.available_at;
