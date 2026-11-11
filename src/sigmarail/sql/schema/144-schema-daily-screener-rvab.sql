-- =============================================================================
-- Revere RVAB: materialized table for broker BAR views (C-BROKER-ANALYTICS)
-- Formula: rvab_score = (ticker.atr_14 / spy.atr_14) * factor_beta_mkt_252d
-- Canon: docs/ai/strategies/revere-portfolio-models.yaml
-- Populated by: sql/transform/metrics/128-ticker-rvab-daily.sql (after L7)
-- Screener / MCP sizing reads the same columns from daily_screener (183).
-- =============================================================================

CREATE TABLE IF NOT EXISTS ticker_rvab_daily
(
    `ticker` LowCardinality(String) COMMENT 'Stock or ETF ticker symbol',
    `date` Date COMMENT 'Trading session (matches daily_screener.date)',
    `atr_14` Nullable(Float64) COMMENT 'ATR(14) from daily_screener',
    `closeadj` Nullable(Float64) COMMENT 'Fully adjusted close (daily_screener dm.closeadj)',
    `ema21d` Nullable(Float64) COMMENT '21-day EMA of closeadj',
    `factor_beta_mkt_252d` Nullable(Float64) COMMENT '252d market beta from factor residuals',
    `spy_atr_14` Nullable(Float64) COMMENT 'SPY ATR(14) for same session',
    `spy_atr_missing` UInt8 DEFAULT 0 COMMENT '1 when SPY ATR missing or non-positive',
    `rvab_score` Nullable(Float64) COMMENT 'Revere RVAB: (atr_14/spy_atr_14)*coalesce(beta,1)',
    `atr_stop_baseline` Nullable(Float64) COMMENT 'closeadj - atr_14 (ATR trailing stop)',
    `above_21ema` Nullable(UInt8) COMMENT '1 when closeadj > ema21d',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker)
SETTINGS index_granularity = 8192
COMMENT 'Precomputed RVAB for broker BAR views; daily_screener projects the same formula.';

-- Managed transform view for target: ticker_rvab_daily
-- =============================================================================
-- TRANSFORM: Materialize ticker_rvab_daily from L7 price/tech + factor
-- =============================================================================
-- Run after L7 screener_*_daily (120–126) on nightly populate. One session per chunk is cheap;
-- backfill uses 1-week chunks like other screener-derived metrics.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_ticker_rvab_daily;

CREATE VIEW IF NOT EXISTS xform_ticker_rvab_daily (
    ticker,
    date,
    atr_14,
    closeadj,
    ema21d,
    factor_beta_mkt_252d,
    spy_atr_14,
    spy_atr_missing,
    rvab_score,
    atr_stop_baseline,
    above_21ema,
    lastupdated
)
COMMENT '{"order":128,"target":"ticker_rvab_daily","sources":["screener_price_tech_daily","screener_factor_daily"],"chunk_size":"1w"}'
AS
WITH
    spy_atr AS (
        SELECT
            date,
            atr_14 AS spy_atr_14
        FROM screener_price_tech_daily FINAL
        WHERE ticker = 'SPY'
          AND date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    )
SELECT
    px.ticker AS ticker,
    px.date AS date,
    px.atr_14 AS atr_14,
    px.closeadj AS closeadj,
    px.ema21d AS ema21d,
    fa.factor_beta_mkt_252d AS factor_beta_mkt_252d,
    spy.spy_atr_14 AS spy_atr_14,
    toUInt8(spy.spy_atr_14 IS NULL OR spy.spy_atr_14 <= 0) AS spy_atr_missing,
    if(
        spy.spy_atr_14 IS NULL OR spy.spy_atr_14 <= 0 OR px.atr_14 IS NULL,
        NULL,
        (px.atr_14 / spy.spy_atr_14)
            * coalesce(fa.factor_beta_mkt_252d, 1.0)
    ) AS rvab_score,
    if(
        px.atr_14 IS NOT NULL AND px.closeadj IS NOT NULL,
        px.closeadj - px.atr_14,
        NULL
    ) AS atr_stop_baseline,
    if(
        px.ema21d IS NOT NULL AND px.closeadj IS NOT NULL,
        toUInt8(px.closeadj > px.ema21d),
        NULL
    ) AS above_21ema,
    now() AS lastupdated
FROM screener_price_tech_daily AS px FINAL
LEFT ANY JOIN screener_factor_daily AS fa FINAL
    ON px.ticker = fa.ticker AND px.date = fa.date
LEFT ANY JOIN spy_atr AS spy ON spy.date = px.date
WHERE px.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String});
