-- =============================================================================
-- TABLE: analyst_consensus_asof
-- kind=raw_fact layer=L4
-- Vendor-neutral street consensus snapshots (I/B/E/S / FactSet grain).
-- Vendor-specific identifiers belong to the selected local data source.
-- =============================================================================

CREATE TABLE IF NOT EXISTS analyst_consensus_asof
(
    `ticker` LowCardinality(String) COMMENT 'Equity ticker',
    `asof_date` Date COMMENT 'Point-in-time snapshot date',
    `vendor` LowCardinality(String) DEFAULT 'unspecified' COMMENT 'Feed identifier selected by the user',
    `metric` LowCardinality(String) COMMENT 'eps | sales',
    `periodicity` LowCardinality(String) COMMENT 'Q | A',
    `relative_period` UInt8 COMMENT '0=current unreported, 1=next',
    `period_end_date` Date DEFAULT toDate(0) COMMENT 'Fiscal period end',
    `mean` Float64 DEFAULT 0 COMMENT 'Consensus mean supplied by the selected vendor',
    `median` Float64 DEFAULT 0 COMMENT 'Consensus median when vendor supplies',
    `high` Float64 DEFAULT 0 COMMENT 'Highest estimate in nest',
    `low` Float64 DEFAULT 0 COMMENT 'Lowest estimate in nest',
    `stdev` Float64 DEFAULT 0 COMMENT 'Stdev of nest',
    `n_estimates` UInt16 DEFAULT 0 COMMENT 'Analyst count',
    `recent` Float64 DEFAULT 0 COMMENT 'Most recent estimate when supplied',
    `eps_basis` LowCardinality(String) DEFAULT 'unknown' COMMENT 'street | gaap | bnri | unknown',
    `currency` LowCardinality(String) DEFAULT 'USD' COMMENT 'Estimate currency',
    `n_up` UInt16 DEFAULT 0 COMMENT 'Up revisions in vendor window',
    `n_down` UInt16 DEFAULT 0 COMMENT 'Down revisions in vendor window',
    `rev_window_days` UInt16 DEFAULT 0 COMMENT 'Vendor revision window days',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(asof_date)
ORDER BY (ticker, asof_date, metric, periodicity, relative_period, vendor)
SETTINGS index_granularity = 8192
COMMENT 'Point-in-time analyst consensus snapshots';
