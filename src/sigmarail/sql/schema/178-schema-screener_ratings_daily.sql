-- =============================================================================
-- TABLE: screener_ratings_daily
-- kind=delivery_projection layer=L7
-- =============================================================================
-- Sparse OK. Columns match 91-schema-daily-screener ratings block.
-- Populated by: sql/transform/metrics/122-screener-ratings-daily.sql
-- entities.yaml: skipped for M2 (Episode A2).
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_ratings_daily
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column',
    `technical_rating` Float32 COMMENT 'From technical_ratings',
    `setup_quality_rating` Float32 COMMENT 'From technical_ratings',
    `technical_composite` Float32 COMMENT 'From technical_ratings',
    `growth_rating` Float32 COMMENT 'From screener_ratings',
    `valuation_rating` Float32 COMMENT 'From screener_ratings',
    `health_rating` Float32 COMMENT 'From screener_ratings',
    `profitability_rating` Float32 COMMENT 'From screener_ratings',
    `dividend_rating` Float32 COMMENT 'From screener_ratings',
    `high_growth_momentum_rating` Float32 COMMENT 'From screener_ratings',
    `fundamental_composite` Float32 COMMENT 'From screener_ratings',
    `weinstein_score` Float32 COMMENT 'From screener_ratings',
    `oneil_score` Float32 COMMENT 'From screener_ratings',
    `minervini_score` Float32 COMMENT 'From screener_ratings',
    `overall_score` Nullable(Float32) COMMENT 'From screener_ratings',
    `classification` Enum8('STRONG_BUY' = 1, 'BUY' = 2, 'WATCHLIST' = 3, 'MONITOR' = 4, 'AVOID' = 5) COMMENT 'From screener_ratings',
    `screen_eps_yearly` Bool COMMENT 'From screener_ratings',
    `screen_eps_quarterly` Bool COMMENT 'From screener_ratings',
    `screen_revenue_yearly` Bool COMMENT 'From screener_ratings',
    `screen_revenue_quarterly` Bool COMMENT 'From screener_ratings',
    `screen_combo_yearly` Bool COMMENT 'From screener_ratings',
    `screen_combo_quarterly` Bool COMMENT 'From screener_ratings',
    `screens_passed` UInt8 COMMENT 'From screener_ratings',
    `has_vcp_setup` Bool COMMENT 'From screener_ratings',
    `has_vcp_breakout` Bool COMMENT 'From screener_ratings',
    `is_bull_market` Bool COMMENT 'From screener_ratings',
    `is_leading_industry` Bool COMMENT 'From screener_ratings',
    `is_stage_2_advancing` Bool COMMENT 'From screener_ratings',
    `accumulation_distribution_rating` UInt8 COMMENT 'From accumulation_distribution_rating',
    `volume_score` Float32 COMMENT 'ADR volume_score',
    `pocket_pivot_score` Float32 COMMENT 'ADR pocket_pivot_score',
    `volume_ratio_score` Float32 COMMENT 'ADR volume_ratio_score',
    `obv_score` Float32 COMMENT 'ADR obv_score'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'L7 delivery_projection: ratings slice for daily_screener_v2 (Episode A2 M2)';

-- Managed transform view for target: screener_ratings_daily
-- =============================================================================
-- TRANSFORM: Populate screener_ratings_daily (L7 delivery_projection)
-- =============================================================================
-- Sparse: inserts only when screener_ratings has rows in the chunk.
-- Empty source → 0-row insert (valid).
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_ratings_daily;

CREATE VIEW IF NOT EXISTS xform_screener_ratings_daily (
    `ticker`,
    `date`,
    `lastupdated`,
    `technical_rating`,
    `setup_quality_rating`,
    `technical_composite`,
    `growth_rating`,
    `valuation_rating`,
    `health_rating`,
    `profitability_rating`,
    `dividend_rating`,
    `high_growth_momentum_rating`,
    `fundamental_composite`,
    `weinstein_score`,
    `oneil_score`,
    `minervini_score`,
    `overall_score`,
    `classification`,
    `screen_eps_yearly`,
    `screen_eps_quarterly`,
    `screen_revenue_yearly`,
    `screen_revenue_quarterly`,
    `screen_combo_yearly`,
    `screen_combo_quarterly`,
    `screens_passed`,
    `has_vcp_setup`,
    `has_vcp_breakout`,
    `is_bull_market`,
    `is_leading_industry`,
    `is_stage_2_advancing`,
    `accumulation_distribution_rating`,
    `volume_score`,
    `pocket_pivot_score`,
    `volume_ratio_score`,
    `obv_score`
)
COMMENT '{"order":122,"target":"screener_ratings_daily","sources":["screener_ratings","technical_ratings","accumulation_distribution_rating"],"chunk_size":"1w"}'
AS
SELECT
    sr.ticker AS ticker,
    sr.date AS date,
    now() AS lastupdated,
    coalesce(tr.technical_rating, 0) AS technical_rating,
    coalesce(tr.setup_quality_rating, 0) AS setup_quality_rating,
    coalesce(tr.technical_composite, 0) AS technical_composite,
    sr.growth_rating,
    sr.valuation_rating,
    sr.health_rating,
    sr.profitability_rating,
    sr.dividend_rating,
    sr.high_growth_momentum_rating,
    sr.fundamental_composite,
    sr.weinstein_score,
    sr.oneil_score,
    sr.minervini_score,
    sr.overall_score,
    sr.classification,
    sr.screen_eps_yearly,
    sr.screen_eps_quarterly,
    sr.screen_revenue_yearly,
    sr.screen_revenue_quarterly,
    sr.screen_combo_yearly,
    sr.screen_combo_quarterly,
    sr.screens_passed,
    sr.has_vcp_setup,
    sr.has_vcp_breakout,
    sr.is_bull_market,
    sr.is_leading_industry,
    sr.is_stage_2_advancing,
    coalesce(adr.accumulation_distribution_rating, 0) AS accumulation_distribution_rating,
    coalesce(adr.volume_score, 0) AS volume_score,
    coalesce(adr.pocket_pivot_score, 0) AS pocket_pivot_score,
    coalesce(adr.volume_ratio_score, 0) AS volume_ratio_score,
    coalesce(adr.obv_score, 0) AS obv_score
FROM screener_ratings AS sr FINAL
LEFT JOIN technical_ratings AS tr FINAL
    ON sr.ticker = tr.ticker AND sr.date = tr.date
   AND tr.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
LEFT JOIN accumulation_distribution_rating AS adr FINAL
    ON sr.ticker = adr.ticker AND sr.date = adr.date
   AND adr.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
WHERE sr.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
