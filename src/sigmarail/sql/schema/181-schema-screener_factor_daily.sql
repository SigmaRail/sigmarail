-- =============================================================================
-- TABLE: screener_factor_daily
-- kind=delivery_projection layer=L7
-- =============================================================================
-- Sparse OK. Factor residual cols matching 91 (60d + 252d windows pivoted).
-- Populated by: sql/transform/metrics/125-screener-factor-daily.sql
-- entities.yaml: skipped for M2 (Episode A2).
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_factor_daily
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `factor_residual_60d` Nullable(Float32) COMMENT 'epsilon_t window=60',
    `factor_rolling_alpha_60d` Nullable(Float32) COMMENT 'rolling_alpha window=60',
    `factor_alpha_tstat_60d` Nullable(Float32) COMMENT 'alpha_tstat window=60',
    `factor_beta_mkt_60d` Nullable(Float32) COMMENT 'beta_mkt window=60',
    `factor_beta_sector_60d` Nullable(Float32) COMMENT 'beta_sector window=60',
    `factor_r2_60d` Nullable(Float32) COMMENT 'r2 window=60',
    `factor_residual_252d` Nullable(Float32) COMMENT 'epsilon_t window=252',
    `factor_rolling_alpha_252d` Nullable(Float32) COMMENT 'rolling_alpha window=252',
    `factor_alpha_tstat_252d` Nullable(Float32) COMMENT 'alpha_tstat window=252',
    `factor_beta_mkt_252d` Nullable(Float32) COMMENT 'beta_mkt window=252',
    `factor_beta_sector_252d` Nullable(Float32) COMMENT 'beta_sector window=252',
    `factor_r2_252d` Nullable(Float32) COMMENT 'r2 window=252'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'L7 delivery_projection: factor residual slice for daily_screener_v2 (Episode A2 M2)';

-- Managed transform view for target: screener_factor_daily
-- =============================================================================
-- TRANSFORM: Populate screener_factor_daily (L7 delivery_projection)
-- =============================================================================
-- Sparse: pivots factor_residuals windows 60 and 252 onto one row per (ticker, date).
-- Empty source → 0-row insert (valid).
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_factor_daily;

CREATE VIEW IF NOT EXISTS xform_screener_factor_daily (
    `ticker`,
    `date`,
    `lastupdated`,
    `factor_residual_60d`,
    `factor_rolling_alpha_60d`,
    `factor_alpha_tstat_60d`,
    `factor_beta_mkt_60d`,
    `factor_beta_sector_60d`,
    `factor_r2_60d`,
    `factor_residual_252d`,
    `factor_rolling_alpha_252d`,
    `factor_alpha_tstat_252d`,
    `factor_beta_mkt_252d`,
    `factor_beta_sector_252d`,
    `factor_r2_252d`
)
COMMENT '{"order":125,"target":"screener_factor_daily","sources":["factor_residuals"],"chunk_size":"1w"}'
AS
SELECT
    spine.ticker AS ticker,
    spine.date AS date,
    now() AS lastupdated,
    fr60.residual AS factor_residual_60d,
    fr60.rolling_alpha AS factor_rolling_alpha_60d,
    fr60.alpha_tstat AS factor_alpha_tstat_60d,
    fr60.beta_mkt AS factor_beta_mkt_60d,
    fr60.beta_sector AS factor_beta_sector_60d,
    fr60.r2 AS factor_r2_60d,
    fr252.residual AS factor_residual_252d,
    fr252.rolling_alpha AS factor_rolling_alpha_252d,
    fr252.alpha_tstat AS factor_alpha_tstat_252d,
    fr252.beta_mkt AS factor_beta_mkt_252d,
    fr252.beta_sector AS factor_beta_sector_252d,
    fr252.r2 AS factor_r2_252d
FROM (
    SELECT DISTINCT ticker, date
    FROM factor_residuals FINAL
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
      AND window IN (60, 252)
) AS spine
LEFT JOIN factor_residuals AS fr60 FINAL
    ON spine.ticker = fr60.ticker AND spine.date = fr60.date AND fr60.window = 60
   AND fr60.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
LEFT JOIN factor_residuals AS fr252 FINAL
    ON spine.ticker = fr252.ticker AND spine.date = fr252.date AND fr252.window = 252
   AND fr252.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
