-- =============================================================================
-- TABLE: screener_stage_weekly_daily
-- kind=delivery_projection layer=L7
-- =============================================================================
-- Sparse OK. Legacy daily-keyed stage/weekly compatibility projection from stage_analysis.
-- Canonical detailed completed-week stage_code/stage_duration remain at their native
-- weekly_metrics_derived grain and are intentionally not copied into this table.
-- Populated by: sql/transform/metrics/123-screener-stage-weekly-daily.sql
-- entities.yaml: skipped for M2 (Episode A2).
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_stage_weekly_daily
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `stage_primary` Nullable(Enum8('1' = 1, '2' = 2, '3' = 3, '4' = 4)) COMMENT 'Deprecated broad-stage compatibility projection from stage_analysis.stage_code.',
    `stage_quality` Float32 COMMENT 'Stage quality 0-100',
    `allocation_fraction` Float32 COMMENT 'Stage allocation fraction',
    `sma30w_slope` Float32 COMMENT '30w SMA slope from stage_analysis',
    `sma50w_slope` Float32 COMMENT '50w SMA slope from stage_analysis',
    `sma50d_slope_20d` Float32 COMMENT '50d SMA slope ~20d from stage_analysis',
    `sma10w_slope` Float32 COMMENT '10w SMA slope from stage_analysis',
    `sma200d_trend` Float32 COMMENT '200d trend from stage_analysis',
    `price_vs_sma30w` Float32 COMMENT 'Price vs 30w SMA',
    `price_vs_sma50w` Float32 COMMENT 'Price vs 50w SMA',
    `price_vs_sma50d` Float32 COMMENT 'Price vs 50d SMA',
    `price_vs_sma10w` Float32 COMMENT 'Price vs 10w SMA',
    `volume_trend` Float32 COMMENT 'Volume trend',
    `volume_sma_ratio` Float32 COMMENT 'Volume vs MA ratio',
    `volume_breakout_ratio` Float32 COMMENT 'Breakout volume ratio',
    `volume_accumulation` Float32 COMMENT 'Volume accumulation',
    `volume_divergence` Float32 COMMENT 'Volume divergence',
    `volume_breakout_strength` Float32 COMMENT 'Breakout strength',
    `relative_strength_vs_spy` Float32 COMMENT 'RS vs SPY (stage_analysis)',
    `relative_strength_vs_sector` Float32 COMMENT 'RS vs sector (stage_analysis)',
    `days_in_stage` UInt16 COMMENT 'Days in current stage',
    `days_in_substage` UInt16 COMMENT 'Days in current substage',
    `stage_transition` String COMMENT 'Stage transition label',
    `trend_duration_weeks` UInt16 COMMENT 'Weeks in trend',
    `ma_alignment_score` Float32 COMMENT 'MA alignment score',
    `trend_consistency` Float32 COMMENT 'Trend consistency',
    `risk_level` Enum8('Low' = 0, 'Medium' = 1, 'High' = 2, 'Very High' = 3, 'Unknown' = 4) COMMENT 'Risk level',
    `volatility_regime` Enum8('Low Volatility' = 0, 'Normal Volatility' = 1, 'High Volatility' = 2) COMMENT 'Volatility regime',
    `trend_regime` Enum8('Bull Market' = 0, 'Bear Market' = 1, 'Neutral' = 2) COMMENT 'Trend regime',
    `breakout_strength` Float32 COMMENT 'Breakout strength'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'L7 compatibility projection: legacy daily-keyed stage/weekly fields for existing consumers; canonical completed-week stage outputs remain in weekly_metrics_derived.';

-- Managed transform view for target: screener_stage_weekly_daily
-- =============================================================================
-- TRANSFORM: Populate screener_stage_weekly_daily (L7 delivery_projection)
-- =============================================================================
-- Sparse: inserts only when stage_analysis has rows in the chunk.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_stage_weekly_daily;

CREATE VIEW IF NOT EXISTS xform_screener_stage_weekly_daily (
    `ticker`,
    `date`,
    `lastupdated`,
    `stage_primary`,
    `stage_quality`,
    `allocation_fraction`,
    `sma30w_slope`,
    `sma50w_slope`,
    `sma50d_slope_20d`,
    `sma10w_slope`,
    `sma200d_trend`,
    `price_vs_sma30w`,
    `price_vs_sma50w`,
    `price_vs_sma50d`,
    `price_vs_sma10w`,
    `volume_trend`,
    `volume_sma_ratio`,
    `volume_breakout_ratio`,
    `volume_accumulation`,
    `volume_divergence`,
    `volume_breakout_strength`,
    `relative_strength_vs_spy`,
    `relative_strength_vs_sector`,
    `days_in_stage`,
    `days_in_substage`,
    `stage_transition`,
    `trend_duration_weeks`,
    `ma_alignment_score`,
    `trend_consistency`,
    `risk_level`,
    `volatility_regime`,
    `trend_regime`,
    `breakout_strength`
)
COMMENT '{"order":123,"target":"screener_stage_weekly_daily","sources":["stage_analysis"],"chunk_size":"1w"}'
AS
SELECT
    sa.ticker,
    sa.date,
    now() AS lastupdated,
    sa.stage_primary,
    sa.stage_quality,
    sa.allocation_fraction AS `allocation_fraction`,
    sa.sma30w_slope AS `sma30w_slope`,
    sa.sma50w_slope AS `sma50w_slope`,
    sa.sma50d_slope_20d AS `sma50d_slope_20d`,
    sa.sma10w_slope,
    sa.sma200d_trend AS `sma200d_trend`,
    sa.price_vs_sma30w,
    sa.price_vs_sma50w,
    sa.price_vs_sma50d,
    sa.price_vs_sma10w,
    sa.volume_trend,
    sa.volume_sma_ratio,
    sa.volume_breakout_ratio,
    sa.volume_accumulation,
    sa.volume_divergence,
    sa.volume_breakout_strength,
    sa.relative_strength_vs_spy,
    sa.relative_strength_vs_sector,
    sa.days_in_stage,
    sa.days_in_substage,
    sa.stage_transition,
    sa.trend_duration_weeks,
    sa.ma_alignment_score,
    sa.trend_consistency,
    sa.risk_level,
    sa.volatility_regime,
    sa.trend_regime,
    sa.breakout_strength
FROM stage_analysis AS sa FINAL
WHERE sa.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
