-- Studio-owned persistence for optimizer sweep sessions.
-- Keep application metadata in the Studio schema layer; do not add these
-- columns to SigmaRail's financial data tables or generated data contract.
CREATE TABLE IF NOT EXISTS strategy_optimizer_sessions
(
    session_id String,
    strategy_id String,
    base_ir_id String,
    title String,
    objective String,
    param_x_name String,
    param_x_values Array(Float64),
    param_y_name Nullable(String),
    param_y_values Array(Float64),
    total_combinations UInt32,
    status LowCardinality(String),
    best_run_id Nullable(String),
    best_score Nullable(Float64),
    best_parameters Nullable(String),
    strategy_type LowCardinality(String),
    oos_days UInt32,
    constraints_json String,
    max_concurrent UInt32,
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY session_id;
