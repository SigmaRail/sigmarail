-- kind=sigmarail_derived layer=L2
-- ARQ growth / QoQ acceleration computed from L1 `arq` (vendor_copy).
-- Additive: L1 `arq` retains legacy calc columns for rollback; L2 is the write path.
CREATE TABLE IF NOT EXISTS arq_derived
(
    `ticker` String COMMENT 'Ticker Symbol. Unique identifier for a security.',
    `date` Date COMMENT 'Calendar date of the quarter end (aligned with arq.date).',
    `revenue_growth_yoy` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY Revenue growth (ARQ vs 4Q ago).',
    `eps_growth_yoy` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY EPS growth (ARQ vs 4Q ago).',
    `fcf_growth_yoy` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY FCF growth (ARQ vs 4Q ago).',
    `netincome_growth_yoy` Nullable(Float64) COMMENT 'kind=sigmarail_derived. YoY Net Income growth (ARQ vs 4Q ago).',
    `eps_growth_qoq` Nullable(Float64) COMMENT 'kind=sigmarail_derived. QoQ EPS growth.',
    `eps_acceleration_qoq` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 1 if current QoQ EPS growth > prior QoQ EPS growth.',
    `revenue_growth_qoq` Nullable(Float64) COMMENT 'kind=sigmarail_derived. QoQ Revenue growth.',
    `revenue_acceleration_qoq` Nullable(Int8) COMMENT 'kind=sigmarail_derived. 1 if current QoQ Revenue growth > prior QoQ Revenue growth.',
    `eps_acceleration_q2` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_epsaQ2: 1 iff YoY EPS growth increased for 2 consecutive quarters; NULL if fewer than 3 YoY values.',
    `eps_acceleration_q3` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_epsaQ3: 1 iff YoY EPS growth increased for 3 consecutive quarters; NULL if fewer than 4 YoY values.',
    `revenue_acceleration_q2` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_revaQ2: 1 iff YoY revenue growth increased for 2 consecutive quarters; NULL if fewer than 3 YoY values.',
    `revenue_acceleration_q3` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_revaQ3: 1 iff YoY revenue growth increased for 3 consecutive quarters; NULL if fewer than 4 YoY values.',
    `pmi_up_q2` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_pmiQ2: 1 iff ARQ net margin increased for 2 consecutive quarters; NULL if incomplete window.',
    `pmi_up_q3` Nullable(Int8) COMMENT 'kind=sigmarail_derived. ChartMill s_pmiQ3: 1 iff ARQ net margin increased for 3 consecutive quarters; NULL if incomplete window.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'kind=sigmarail_derived layer=L2 target=arq_derived';

-- Managed transform view for target: arq_derived
-- kind=sigmarail_derived layer=L2
-- Populates arq_derived from L1 arq FINAL history (growth + QoQ / Q2 / Q3 acceleration + PMI).
-- Expects SQL variables: history_start_date, chunk_start_date, chunk_end_date
-- Q2/Q3 YoY accel needs ~8 quarters of raw ARQ (4 YoY points, each vs 4Q ago) → 800d lookback.
--
DROP VIEW IF EXISTS xform_arq_derived;

CREATE VIEW IF NOT EXISTS xform_arq_derived (
    ticker,
    date,
    revenue_growth_yoy,
    eps_growth_yoy,
    fcf_growth_yoy,
    netincome_growth_yoy,
    eps_growth_qoq,
    eps_acceleration_qoq,
    revenue_growth_qoq,
    revenue_acceleration_qoq,
    eps_acceleration_q2,
    eps_acceleration_q3,
    revenue_acceleration_q2,
    revenue_acceleration_q3,
    pmi_up_q2,
    pmi_up_q3,
    lastupdated
)
COMMENT '{"order":16,"target":"arq_derived","sources":["arq"],"chunk_size":"6m"}'
AS
WITH
ticker_freshness_check AS (
    SELECT
        d.ticker,
        count() as target_row_count,
        max(d.lastupdated) as target_last_updated
    FROM arq_derived d FINAL
    WHERE d.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY d.ticker
),
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM arq FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 800 DAY AND {chunk_end_date:String}
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
arq_history AS (
    SELECT ticker, date, revenue, epsdil, fcf, netinccmn
    FROM arq FINAL
    WHERE date BETWEEN toDate({chunk_start_date:String}) - INTERVAL 800 DAY AND {chunk_end_date:String}
      AND ticker IN (SELECT ticker FROM tickers_needing_update WHERE needs_update = 1)
),
arq_with_calcs AS (
    SELECT
        a.ticker,
        a.date,
        CASE WHEN COUNT(a.revenue) OVER w_yoy_4q >= 5
             THEN (a.revenue - lagInFrame(a.revenue, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(a.revenue, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as revenue_growth_yoy_calc,
        CASE WHEN COUNT(a.epsdil) OVER w_yoy_4q >= 5
             THEN (a.epsdil - lagInFrame(a.epsdil, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(a.epsdil, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as eps_growth_yoy_calc,
        CASE WHEN COUNT(a.fcf) OVER w_yoy_4q >= 5
             THEN (a.fcf - lagInFrame(a.fcf, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(a.fcf, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as fcf_growth_yoy_calc,
        CASE WHEN COUNT(a.netinccmn) OVER w_yoy_4q >= 5
             THEN (a.netinccmn - lagInFrame(a.netinccmn, 4) OVER w_yoy_4q) / nullIf(abs(lagInFrame(a.netinccmn, 4) OVER w_yoy_4q), 0)
             ELSE NULL END as netincome_growth_yoy_calc,
        CASE WHEN COUNT(a.epsdil) OVER w_qoq >= 2
             THEN (a.epsdil - lagInFrame(a.epsdil, 1) OVER w_qoq) / nullIf(abs(lagInFrame(a.epsdil, 1) OVER w_qoq), 0)
             ELSE NULL END as eps_growth_qoq_calc,
        CASE WHEN COUNT(a.revenue) OVER w_qoq >= 2
             THEN (a.revenue - lagInFrame(a.revenue, 1) OVER w_qoq) / nullIf(abs(lagInFrame(a.revenue, 1) OVER w_qoq), 0)
             ELSE NULL END as revenue_growth_qoq_calc,
        a.netinccmn / nullIf(abs(a.revenue), 0) as netmargin_calc
    FROM arq_history a
    WINDOW
        w_yoy_4q AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w_qoq AS (PARTITION BY a.ticker ORDER BY a.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
),
arq_with_final_calcs AS (
    SELECT
        c.*,
        CASE WHEN COUNT(c.eps_growth_qoq_calc) OVER w_qoq_accel < 2
             THEN NULL
             WHEN c.eps_growth_qoq_calc > lagInFrame(c.eps_growth_qoq_calc, 1) OVER w_qoq_accel
             THEN 1 ELSE 0 END as eps_acceleration_qoq_calc,
        CASE WHEN COUNT(c.revenue_growth_qoq_calc) OVER w_qoq_accel < 2
             THEN NULL
             WHEN c.revenue_growth_qoq_calc > lagInFrame(c.revenue_growth_qoq_calc, 1) OVER w_qoq_accel
             THEN 1 ELSE 0 END as revenue_acceleration_qoq_calc,
        CASE WHEN COUNT(c.eps_growth_yoy_calc) OVER w_accel_q2 < 3
             THEN NULL
             WHEN c.eps_growth_yoy_calc > lagInFrame(c.eps_growth_yoy_calc, 1) OVER w_accel_q2
              AND lagInFrame(c.eps_growth_yoy_calc, 1) OVER w_accel_q2 > lagInFrame(c.eps_growth_yoy_calc, 2) OVER w_accel_q2
             THEN 1 ELSE 0 END as eps_acceleration_q2_calc,
        CASE WHEN COUNT(c.eps_growth_yoy_calc) OVER w_accel_q3 < 4
             THEN NULL
             WHEN c.eps_growth_yoy_calc > lagInFrame(c.eps_growth_yoy_calc, 1) OVER w_accel_q3
              AND lagInFrame(c.eps_growth_yoy_calc, 1) OVER w_accel_q3 > lagInFrame(c.eps_growth_yoy_calc, 2) OVER w_accel_q3
              AND lagInFrame(c.eps_growth_yoy_calc, 2) OVER w_accel_q3 > lagInFrame(c.eps_growth_yoy_calc, 3) OVER w_accel_q3
             THEN 1 ELSE 0 END as eps_acceleration_q3_calc,
        CASE WHEN COUNT(c.revenue_growth_yoy_calc) OVER w_accel_q2 < 3
             THEN NULL
             WHEN c.revenue_growth_yoy_calc > lagInFrame(c.revenue_growth_yoy_calc, 1) OVER w_accel_q2
              AND lagInFrame(c.revenue_growth_yoy_calc, 1) OVER w_accel_q2 > lagInFrame(c.revenue_growth_yoy_calc, 2) OVER w_accel_q2
             THEN 1 ELSE 0 END as revenue_acceleration_q2_calc,
        CASE WHEN COUNT(c.revenue_growth_yoy_calc) OVER w_accel_q3 < 4
             THEN NULL
             WHEN c.revenue_growth_yoy_calc > lagInFrame(c.revenue_growth_yoy_calc, 1) OVER w_accel_q3
              AND lagInFrame(c.revenue_growth_yoy_calc, 1) OVER w_accel_q3 > lagInFrame(c.revenue_growth_yoy_calc, 2) OVER w_accel_q3
              AND lagInFrame(c.revenue_growth_yoy_calc, 2) OVER w_accel_q3 > lagInFrame(c.revenue_growth_yoy_calc, 3) OVER w_accel_q3
             THEN 1 ELSE 0 END as revenue_acceleration_q3_calc,
        CASE WHEN COUNT(c.netmargin_calc) OVER w_accel_q2 < 3
             THEN NULL
             WHEN c.netmargin_calc > lagInFrame(c.netmargin_calc, 1) OVER w_accel_q2
              AND lagInFrame(c.netmargin_calc, 1) OVER w_accel_q2 > lagInFrame(c.netmargin_calc, 2) OVER w_accel_q2
             THEN 1 ELSE 0 END as pmi_up_q2_calc,
        CASE WHEN COUNT(c.netmargin_calc) OVER w_accel_q3 < 4
             THEN NULL
             WHEN c.netmargin_calc > lagInFrame(c.netmargin_calc, 1) OVER w_accel_q3
              AND lagInFrame(c.netmargin_calc, 1) OVER w_accel_q3 > lagInFrame(c.netmargin_calc, 2) OVER w_accel_q3
              AND lagInFrame(c.netmargin_calc, 2) OVER w_accel_q3 > lagInFrame(c.netmargin_calc, 3) OVER w_accel_q3
             THEN 1 ELSE 0 END as pmi_up_q3_calc
    FROM arq_with_calcs c
    WINDOW
        w_qoq_accel AS (PARTITION BY c.ticker ORDER BY c.date ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),
        w_accel_q2 AS (PARTITION BY c.ticker ORDER BY c.date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
        w_accel_q3 AS (PARTITION BY c.ticker ORDER BY c.date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
)
SELECT
    ticker,
    date,
    revenue_growth_yoy_calc AS revenue_growth_yoy,
    eps_growth_yoy_calc AS eps_growth_yoy,
    fcf_growth_yoy_calc AS fcf_growth_yoy,
    netincome_growth_yoy_calc AS netincome_growth_yoy,
    eps_growth_qoq_calc AS eps_growth_qoq,
    eps_acceleration_qoq_calc AS eps_acceleration_qoq,
    revenue_growth_qoq_calc AS revenue_growth_qoq,
    revenue_acceleration_qoq_calc AS revenue_acceleration_qoq,
    eps_acceleration_q2_calc AS eps_acceleration_q2,
    eps_acceleration_q3_calc AS eps_acceleration_q3,
    revenue_acceleration_q2_calc AS revenue_acceleration_q2,
    revenue_acceleration_q3_calc AS revenue_acceleration_q3,
    pmi_up_q2_calc AS pmi_up_q2,
    pmi_up_q3_calc AS pmi_up_q3,
    now() AS lastupdated
FROM arq_with_final_calcs
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
