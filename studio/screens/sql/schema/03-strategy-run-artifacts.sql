-- Studio-owned LEAN run artifacts; payloads stay separate from financial data.
CREATE TABLE IF NOT EXISTS strategy_run_artifacts
(
    run_id String COMMENT 'Backtest run identifier',
    strategy_id LowCardinality(String) COMMENT 'Strategy identifier',
    run_timestamp DateTime64(3, 'UTC') COMMENT 'Run timestamp for partitioning',
    artifact_type Enum8(
        'summary' = 1,
        'backtest_results' = 2,
        'order_events' = 3,
        'algorithm_log' = 4,
        'live_snapshot' = 5,
        'backtest_day_snapshots' = 6,
        'accounting_ledger' = 7
    ),
    artifact_json String COMMENT 'Artifact payload encoded as JSON',
    created_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(run_timestamp)
ORDER BY (run_id, artifact_type);
