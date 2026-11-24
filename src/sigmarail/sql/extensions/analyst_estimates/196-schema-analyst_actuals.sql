-- =============================================================================
-- TABLE: analyst_actuals
-- kind=raw_fact layer=L4
-- Reported vs estimate-at-print (surprise).
-- =============================================================================

CREATE TABLE IF NOT EXISTS analyst_actuals
(
    `ticker` LowCardinality(String) COMMENT 'Equity ticker',
    `period_end_date` Date COMMENT 'Fiscal period end',
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
ORDER BY (ticker, period_end_date, metric, vendor)
SETTINGS index_granularity = 8192
COMMENT 'Actual vs estimate-at-print; surprise_pct';
