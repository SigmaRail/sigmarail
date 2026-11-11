-- =============================================================================
-- TABLE: screener_ownership_daily
-- kind=delivery_projection layer=L7
-- =============================================================================
-- Sparse OK. Ownership cols matching 91 / ownership_signals_daily.
-- Populated by: sql/transform/metrics/124-screener-ownership-daily.sql
-- entities.yaml: skipped for M2 (Episode A2).
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_ownership_daily
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `inst_calendardate` Nullable(Date) COMMENT '13F holdings as-of quarter end',
    `inst_public_asof_date` Nullable(Date) COMMENT 'First public session for 13F quarter',
    `inst_calendardate_complete` UInt8 COMMENT '1 when 13F quarter passes quality gate',
    `inst_data_lag_days` UInt16 COMMENT 'Session date minus inst_public_asof_date',
    `inst_holdings_lag_days` UInt16 COMMENT 'Session date minus inst_calendardate',
    `inst_shrholders` UInt32 COMMENT 'Institutional holder count',
    `inst_shrholders_qoq_delta` Int32 COMMENT 'QoQ change in holders',
    `inst_shrholders_qoq_pct` Float32 COMMENT 'QoQ pct change in holders',
    `inst_sponsor_trend` Enum8('stable' = 0, 'rising' = 1, 'falling' = 2) COMMENT 'Sponsorship trend',
    `insider_open_buys_90d` UInt16 COMMENT 'Open-market insider buys 90d',
    `insider_open_sells_90d` UInt16 COMMENT 'Open-market insider sells 90d',
    `insider_net_buy_value_90d` Float64 COMMENT 'Net insider buy value 90d',
    `insider_officer_buys_90d` UInt16 COMMENT 'Officer buys 90d',
    `insider_officer_sells_90d` UInt16 COMMENT 'Officer sells 90d',
    `insider_cluster_buy_flag` UInt8 COMMENT 'Cluster buy flag',
    `insider_days_since_open_buy` UInt16 COMMENT 'Days since last buy; 65535 if none',
    `insider_sentiment_90d` Enum8('neutral' = 0, 'net_buy' = 1, 'net_sell' = 2) COMMENT 'Insider sentiment 90d',
    `insider_last_filingdate` Nullable(Date) COMMENT 'Latest Form 4 filingdate in window'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'L7 delivery_projection: ownership slice for daily_screener_v2 (Episode A2 M2)';

-- Managed transform view for target: screener_ownership_daily
-- =============================================================================
-- TRANSFORM: Populate screener_ownership_daily (L7 delivery_projection)
-- =============================================================================
-- Sparse: inserts only when ownership_signals_daily has rows in the chunk.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_ownership_daily;

CREATE VIEW IF NOT EXISTS xform_screener_ownership_daily (
    `ticker`,
    `date`,
    `lastupdated`,
    `inst_calendardate`,
    `inst_public_asof_date`,
    `inst_calendardate_complete`,
    `inst_data_lag_days`,
    `inst_holdings_lag_days`,
    `inst_shrholders`,
    `inst_shrholders_qoq_delta`,
    `inst_shrholders_qoq_pct`,
    `inst_sponsor_trend`,
    `insider_open_buys_90d`,
    `insider_open_sells_90d`,
    `insider_net_buy_value_90d`,
    `insider_officer_buys_90d`,
    `insider_officer_sells_90d`,
    `insider_cluster_buy_flag`,
    `insider_days_since_open_buy`,
    `insider_sentiment_90d`,
    `insider_last_filingdate`
)
COMMENT '{"order":124,"target":"screener_ownership_daily","sources":["ownership_signals_daily"],"chunk_size":"1w"}'
AS
SELECT
    os.ticker,
    os.date,
    now() AS lastupdated,
    os.inst_calendardate,
    os.inst_public_asof_date,
    os.inst_calendardate_complete,
    os.inst_data_lag_days,
    os.inst_holdings_lag_days,
    os.inst_shrholders,
    os.inst_shrholders_qoq_delta,
    os.inst_shrholders_qoq_pct,
    os.inst_sponsor_trend,
    os.insider_open_buys_90d,
    os.insider_open_sells_90d,
    os.insider_net_buy_value_90d,
    os.insider_officer_buys_90d,
    os.insider_officer_sells_90d,
    os.insider_cluster_buy_flag,
    os.insider_days_since_open_buy,
    os.insider_sentiment_90d,
    os.insider_last_filingdate
FROM ownership_signals_daily AS os FINAL
WHERE os.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
