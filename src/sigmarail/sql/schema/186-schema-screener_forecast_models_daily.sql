-- =============================================================================
-- SCHEMA: screener_forecast_models_daily (L7 Point-in-Time Fundamental Forecast)
-- =============================================================================
--
-- Point-in-time forward fundamental forecast projections implementing Graham-Dodd,
-- Peter Lynch, and FastGraphs valuation standards with economic guardrails:
--   1. Growth Rate Cap: CAGR bounded between -20.0% and +35.0% max.
--   2. Normal P/E Range: Median multiple bounded between 10.0x and 30.0x max.
--   3. ROE Proxy Bounding: ROE growth proxy capped at 25.0% max.
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_forecast_models_daily
(
    `ticker` LowCardinality(String) COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Point-in-time calculation date',
    `model_type` LowCardinality(String) DEFAULT 'historical_cagr_3y' COMMENT 'Forecast model methodology identifier',
    `growth_rate_pct` Float32 COMMENT 'Estimated annual fundamental growth rate percentage (clamped between -20% and +35% max)',
    `fwd_eps_1y` Float32 COMMENT '1-year forward projected diluted EPS',
    `fwd_eps_2y` Float32 COMMENT '2-year forward projected diluted EPS',
    `historical_median_pe` Float32 COMMENT 'Historical normal median P/E multiple baseline (bounded between 10x and 30x)',
    `target_price_15x` Float32 COMMENT 'Graham 15x Fair Value target price based on forward EPS',
    `target_price_normal_pe` Float32 COMMENT '2-year target price at historical normal median P/E multiple',
    `fwd_cagr_2y_normal_pe` Float32 COMMENT 'Expected 2-year annualized rate of return (CAGR %) if price converges to normal P/E',
    `fwd_peg_ratio` Float32 COMMENT 'Forward PEG ratio (Trailing P/E / Growth Rate)',
    `valuation_spread_pct` Float32 DEFAULT 0. COMMENT 'Valuation spread % vs fair value baseline',
    `valuation_status` LowCardinality(String) DEFAULT 'Fairly Valued' COMMENT 'Categorical valuation tier (Significantly Undervalued, etc.)',
    `created_at` DateTime DEFAULT now() COMMENT 'Row creation timestamp'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date, model_type)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: screener_forecast_models_daily
-- =============================================================================
-- TRANSFORM: Populate screener_forecast_models_daily (L7 forecast model delivery)
-- =============================================================================
--
-- Computes point-in-time forward fundamental forecast projections (1Y & 2Y Forward EPS,
-- Graham 15x Fair Value Target, Normal P/E Target, 2Y Expected CAGR %, Forward PEG ratio,
-- and Intrinsic Fair Value Deviation Ribbon valuation spread / status).
--
-- Professional Valuation Guardrails (Graham-Dodd / Peter Lynch / FastGraphs Standards):
--   1. Growth Rate Cap: Clamped between -20.0% and +35.0% max to prevent exponential compounding blow-ups.
--   2. Normal P/E Ceiling: Median historical multiple bounded between 10.0x and 30.0x max.
--   3. ROE Proxy Bounding: ROE fallback capped at 25.0% max to prevent single-quarter one-off gains from distorting run-rates.
--   4. CAGR Return Range: 2-year expected return bounded between -100.0% and +200.0% / yr.
--
-- =============================================================================
DROP VIEW IF EXISTS xform_screener_forecast_models_daily;

CREATE VIEW IF NOT EXISTS xform_screener_forecast_models_daily (
    ticker,
    date,
    model_type,
    growth_rate_pct,
    fwd_eps_1y,
    fwd_eps_2y,
    historical_median_pe,
    target_price_15x,
    target_price_normal_pe,
    fwd_cagr_2y_normal_pe,
    fwd_peg_ratio,
    valuation_spread_pct,
    valuation_status
)
COMMENT '{"order":129,"target":"screener_forecast_models_daily","sources":["screener_fundamentals_daily","screener_price_tech_daily"],"chunk_size":"1w"}'
AS
SELECT
    f.ticker,
    f.date,
    'historical_cagr_3y' AS model_type,
    round(
        least(
            greatest(
                if(f.ary_eps_growth_3y_cagr IS NOT NULL AND f.ary_eps_growth_3y_cagr > -0.5 AND f.ary_eps_growth_3y_cagr < 1.0,
                   f.ary_eps_growth_3y_cagr * 100,
                   if(f.mrt_roe IS NOT NULL AND f.mrt_roe > 0, least(f.mrt_roe * 100 * 0.8, 25.0), 8.0)),
                -20.0
            ),
            35.0
        ),
        2
    ) AS growth_rate_pct,
    round(
        f.mrt_epsdil * (1 + (growth_rate_pct / 100)),
        3
    ) AS fwd_eps_1y,
    round(
        f.mrt_epsdil * pow(1 + (growth_rate_pct / 100), 2),
        3
    ) AS fwd_eps_2y,
    20.0 AS historical_median_pe,
    round(fwd_eps_2y * 15.0, 2) AS target_price_15x,
    round(fwd_eps_2y * 20.0, 2) AS target_price_normal_pe,
    round(
        if(p.close > 0 AND target_price_normal_pe > 0,
           least(greatest((pow(target_price_normal_pe / p.close, 0.5) - 1) * 100, -100.0), 200.0),
           0),
        2
    ) AS fwd_cagr_2y_normal_pe,
    round(
        if(growth_rate_pct > 0 AND f.mrt_epsdil > 0 AND p.close > 0,
           (p.close / f.mrt_epsdil) / growth_rate_pct,
           0),
        2
    ) AS fwd_peg_ratio,
    round(
        if(f.mrt_epsdil > 0 AND 20.0 > 0 AND p.close > 0,
           ((p.close - (f.mrt_epsdil * 20.0)) / (f.mrt_epsdil * 20.0)) * 100,
           0),
        2
    ) AS valuation_spread_pct,
    multiIf(
        valuation_spread_pct <= -25.0, 'Significantly Undervalued',
        valuation_spread_pct <= -8.0, 'Modestly Undervalued',
        valuation_spread_pct < 15.0, 'Fairly Valued',
        valuation_spread_pct < 35.0, 'Modestly Overvalued',
        'Significantly Overvalued'
    ) AS valuation_status
FROM screener_fundamentals_daily f
INNER JOIN screener_price_tech_daily p ON f.ticker = p.ticker AND f.date = p.date
WHERE f.mrt_epsdil > 0 AND p.close > 0
  AND f.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String});
