-- Studio-owned LEAN run metadata.
-- These application records are separate from SigmaRail's Sharadar-derived
-- financial schema and are created with the rest of the Studio schema.
CREATE TABLE IF NOT EXISTS strategy_runs
(
    run_id String COMMENT 'Unique identifier for the backtest run',
    strategy_id LowCardinality(String) COMMENT 'Strategy identifier',
    strategy_repo_url String COMMENT 'Repository containing the strategy source',
    run_timestamp DateTime64(3, 'UTC') COMMENT 'Time the run completed',
    git_commit FixedString(40) COMMENT 'Strategy source commit',
    git_branch LowCardinality(String) COMMENT 'Strategy source branch',
    run_type Enum8('base' = 1, 'optimization' = 2, 'variant' = 3, 'stress_test' = 4, 'spike_hosted' = 5),
    trigger LowCardinality(String) COMMENT 'What initiated the run',
    period_start Date COMMENT 'First backtest date',
    period_end Date COMMENT 'Last backtest date',
    image String COMMENT 'LEAN runtime image',
    parameters String COMMENT 'Run parameters encoded as JSON',
    ir_id Nullable(String) COMMENT 'Strategy spec identifier',
    ir_schema_version Nullable(UInt16) COMMENT 'Strategy spec schema version',
    ir_content_hash Nullable(FixedString(64)) COMMENT 'Hash of the exact strategy spec',
    total_return Nullable(Float64) COMMENT 'Total return as a unit fraction',
    annual_return Nullable(Float64) COMMENT 'Annualized return as a unit fraction',
    sharpe_ratio Nullable(Float64),
    sortino_ratio Nullable(Float64),
    max_drawdown Nullable(Float64) COMMENT 'Maximum drawdown as a unit fraction',
    win_rate Nullable(Float64) COMMENT 'Win rate as a unit fraction',
    profit_factor Nullable(Float64),
    total_orders Nullable(UInt32),
    total_fees Nullable(Float64) COMMENT 'Fees in account currency',
    start_equity Nullable(Float64),
    end_equity Nullable(Float64),
    alpha Nullable(Float64),
    beta Nullable(Float64),
    volatility Nullable(Float64),
    information_ratio Nullable(Float64),
    market_regime Nullable(Enum8('bull' = 1, 'bear' = 2, 'neutral' = 3)),
    spy_return Nullable(Float64) COMMENT 'Benchmark return as a unit fraction',
    created_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(run_timestamp)
ORDER BY (strategy_id, run_timestamp, run_id);
