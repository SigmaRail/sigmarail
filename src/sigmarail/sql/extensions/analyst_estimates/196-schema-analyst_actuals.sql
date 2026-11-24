-- =============================================================================
-- TABLE: ext_analyst_estimates_analyst_actuals
-- kind=raw_fact layer=L4
-- Reported vs estimate-at-print (surprise).
-- =============================================================================

CREATE TABLE IF NOT EXISTS ext_analyst_estimates_analyst_actuals
(
    `ticker` LowCardinality(String) COMMENT 'Equity ticker',
    `period_end_date` Date COMMENT 'Fiscal period end',
    `available_at` DateTime64(3, 'America/New_York') DEFAULT toDateTime64(0, 3, 'America/New_York') COMMENT 'Public release timestamp for this reported value; zero means unavailable and is excluded from historical projections',
    `metric` LowCardinality(String) COMMENT 'eps | sales',
    `vendor` LowCardinality(String) DEFAULT 'unspecified' COMMENT 'Feed identifier selected by the user',
    `reported` Float64 DEFAULT 0 COMMENT 'Reported value',
    `estimate_at_print` Float64 DEFAULT 0 COMMENT 'Consensus at print',
    `surprise_pct` Float64 DEFAULT 0 COMMENT '(reported - estimate) / abs(estimate)',
    `eps_basis` LowCardinality(String) DEFAULT 'street' COMMENT 'street | gaap | bnri | unknown',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(period_end_date)
ORDER BY (ticker, period_end_date, metric, vendor, available_at)
SETTINGS index_granularity = 8192
COMMENT 'Actual vs estimate-at-print; surprise_pct';
