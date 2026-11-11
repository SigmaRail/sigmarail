-- ============================================================================
-- Screener Ratings Table Schema (CONSOLIDATED)
-- ============================================================================
-- Purpose: Pre-calculated fundamental ratings, methodology scores, and screen flags
--
-- This consolidated table combines what would have been 3 separate tables:
-- 1. Fundamental ratings (growth, valuation, health, profitability, dividend)
-- 2. Methodology scores (Weinstein, O'Neil, Minervini)
-- 3. Screen flags (fundamental screens, patterns, environment)
--
-- Consolidation Benefits:
-- - ONE table instead of 3 (fewer JOINs in queries)
-- - ONE transform to maintain (66-screener-ratings-3m.sql)
-- - All ratings calculated together (share CTEs, atomic updates)
-- - Follows existing pattern (daily_fundamentals consolidates MRT/MRQ/ARY/ARQ)
--
-- Attribution:
-- - Growth Rating: O'Neil CAN SLIM "E" (Earnings) and "S" (Sales)
-- - Weinstein Score: Stan Weinstein's Stage Analysis (1988)
-- - O'Neil Score: William O'Neil's CAN SLIM system (1988)
-- - Minervini Score: Mark Minervini's SEPA framework (2013)
-- - High Growth Momentum: SigmaRail near-term / multi-year / margin blend (CAN SLIM / Minervini oriented)
--
-- Dependencies:
-- - daily_fundamentals: All fundamental metrics (EPS, revenue, ratios)
-- - technical_ratings: setup_quality_rating, technical_composite
-- - stage_analysis: stage_primary, stage_quality (Weinstein)
-- - market_regime_signals_daily: Bull/bear market state
-- - industry_group_strength: Industry rankings
-- - daily_metrics_derived: VCP breakout signals (Minervini)
--
-- Storage: ~100 MB per year (~35 columns × ~8000 tickers × 252 days)
-- ============================================================================

CREATE TABLE IF NOT EXISTS screener_ratings
(
    `ticker` String COMMENT 'Equity ticker symbol',
    `date` Date COMMENT 'Trading session date',
    `growth_rating` Float32 COMMENT 'Long-term steady growth rating (0-100) - 3-year EPS/Revenue CAGR, YoY acceleration [O\'Neil CAN SLIM "E" & "S"]',
    `valuation_rating` Float32 COMMENT 'Valuation rating (0-100) - P/E, PEG, Price/Book ratios vs industry',
    `health_rating` Float32 COMMENT 'Financial health rating (0-100) - Balance sheet, debt/equity, liquidity',
    `profitability_rating` Float32 COMMENT 'Profitability rating (0-100) - ROE, ROA, ROIC, margins',
    `dividend_rating` Float32 COMMENT 'Dividend quality rating (0-100) - Yield, payout ratio, growth consistency',
    `high_growth_momentum_rating` Float32 COMMENT 'High-growth momentum (0-100) - SigmaRail blend of ARQ YoY/QoQ growth, 3y CAGR, and TTM margins [CAN SLIM / Minervini oriented]',
    `fundamental_composite` Float32 COMMENT 'Average of 5 core ratings (0-100) - growth, valuation, health, profitability, dividend; excludes high_growth_momentum (specialty rating)',
    `weinstein_score` Float32 COMMENT 'Weinstein Stage Analysis quality (0-100) - Stage 2 advancing strength [Stan Weinstein 1988]',
    `oneil_score` Float32 COMMENT 'O\'Neil CAN SLIM score (0-100) - Growth + RS rating quality [William O\'Neil 1988]',
    `minervini_score` Float32 COMMENT 'Minervini SEPA score (0-100) - (Weinstein + O\'Neil + VCP setup) / 3 [Mark Minervini 2013]',
    `overall_score` Nullable(Float32) COMMENT 'Overall quality score (0-100); NULL if non-finite (NaN/Inf)',
    `classification` Enum8('STRONG_BUY' = 1, 'BUY' = 2, 'WATCHLIST' = 3, 'MONITOR' = 4, 'AVOID' = 5) COMMENT 'Overall classification based on composite scores',
    `screen_eps_yearly` Bool COMMENT 'Passes yearly EPS growth screen (25%+ 3-year) [O\'Neil "A"]',
    `screen_eps_quarterly` Bool COMMENT 'Passes quarterly EPS growth screen (25%+ QoQ) [O\'Neil "C"]',
    `screen_revenue_yearly` Bool COMMENT 'Passes yearly revenue growth screen (25%+ 3-year) [O\'Neil "S"]',
    `screen_revenue_quarterly` Bool COMMENT 'Passes quarterly revenue growth screen (25%+ QoQ)',
    `screen_combo_yearly` Bool COMMENT 'Passes both EPS + Revenue yearly screens [Minervini]',
    `screen_combo_quarterly` Bool COMMENT 'Passes both EPS + Revenue quarterly screens [Minervini]',
    `screens_passed` UInt8 COMMENT 'Count of fundamental screens passed (0-6)',
    `has_vcp_setup` Bool COMMENT 'Has Volatility Contraction Pattern forming [Minervini]',
    `has_vcp_breakout` Bool COMMENT 'Has VCP breakout signal [Minervini]',
    `is_bull_market` Bool COMMENT 'Market in bull regime (from market_regime_signals)',
    `is_leading_industry` Bool COMMENT 'Industry in top quartile (industry_group_rank >= 75; percent_rank of industry avg RS, higher = stronger)',
    `is_stage_2_advancing` Bool COMMENT 'In Weinstein Stage 2 [Stan Weinstein]',
    `lastupdated` DateTime DEFAULT now() COMMENT 'Timestamp when this record was calculated and inserted'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Consolidated ratings table - fundamental ratings, methodology scores, and screen flags';

-- ============================================================================
-- Usage Examples:
-- ============================================================================

-- Example 1: Find Minervini SEPA candidates
-- SELECT ticker, date, minervini_score, screens_passed, has_vcp_setup
-- FROM screener_ratings
-- WHERE date = today()
--   AND minervini_score >= 7.5
--   AND screens_passed >= 2
--   AND has_vcp_setup = true
--   AND is_bull_market = true
-- ORDER BY minervini_score DESC
-- LIMIT 20;

-- Example 2: Find O'Neil CAN SLIM candidates
-- SELECT ticker, date, oneil_score, growth_rating, classification
-- FROM screener_ratings
-- WHERE date = today()
--   AND oneil_score >= 7.0
--   AND growth_rating >= 8.0
--   AND classification IN ('STRONG_BUY', 'BUY')
-- ORDER BY oneil_score DESC
-- LIMIT 20;

-- Example 3: Find Weinstein Stage 2 candidates
-- SELECT ticker, date, weinstein_score, is_stage_2_advancing, is_leading_industry
-- FROM screener_ratings
-- WHERE date = today()
--   AND weinstein_score >= 7.0
--   AND is_stage_2_advancing = true
-- ORDER BY weinstein_score DESC
-- LIMIT 20;

-- ============================================================================

-- Managed transform view for target: screener_ratings
-- Screener Ratings Transform - Fundamental ratings and methodology scores
-- Rating Scale: 0-100 (IBD/Deepvue-aligned)
--
-- overall_score is Nullable(Float32): non-finite raw values become NULL.
--
DROP VIEW IF EXISTS xform_screener_ratings;

CREATE VIEW IF NOT EXISTS xform_screener_ratings (
    ticker,
    date,
    growth_rating,
    valuation_rating,
    health_rating,
    profitability_rating,
    dividend_rating,
    high_growth_momentum_rating,
    fundamental_composite,
    weinstein_score,
    oneil_score,
    minervini_score,
    overall_score,
    classification,
    screen_eps_yearly,
    screen_eps_quarterly,
    screen_revenue_yearly,
    screen_revenue_quarterly,
    screen_combo_yearly,
    screen_combo_quarterly,
    screens_passed,
    has_vcp_setup,
    has_vcp_breakout,
    is_bull_market,
    is_leading_industry,
    is_stage_2_advancing,
    lastupdated
)
COMMENT '{"order":82,"target":"screener_ratings","sources":["daily_fundamentals","stage_analysis","daily_metrics_derived","market_regime_signals_daily","technical_ratings","daily_valuation","tickers","industry_group_strength"],"chunk_size":"3m"}'
AS
SELECT
    ticker,
    date,
    growth_rating,
    valuation_rating,
    health_rating,
    profitability_rating,
    dividend_rating,
    high_growth_momentum_rating,
    fundamental_composite,
    weinstein_score,
    oneil_score,
    minervini_score,
    CAST(if(isFinite(_overall_raw), toFloat32(_overall_raw), NULL) AS Nullable(Float32)) AS overall_score,
    classification,
    screen_eps_yearly,
    screen_eps_quarterly,
    screen_revenue_yearly,
    screen_revenue_quarterly,
    screen_combo_yearly,
    screen_combo_quarterly,
    screens_passed,
    has_vcp_setup,
    has_vcp_breakout,
    is_bull_market,
    is_leading_industry,
    is_stage_2_advancing,
    lastupdated
FROM (
    SELECT
        df.ticker AS ticker,
        df.date AS date,

        -- Growth Rating (0-100 scale): long-term steady growth from 3y CAGRs
        -- isFinite: CH NaN is not NULL; COALESCE alone does not neutralize it.
        LEAST(100.0, GREATEST(0.0,
            (if(isFinite(df.ary_eps_growth_3y_cagr), df.ary_eps_growth_3y_cagr, 0) * 100) +
            (if(isFinite(df.ary_revenue_growth_3y_cagr), df.ary_revenue_growth_3y_cagr, 0) * 100)
        ) / 2.0) AS growth_rating,

        -- Valuation Rating (0-100): cheaper absolute PE/PB/PS → higher score.
        -- Source: daily_valuation (Sharadar daily). No industry-relative PE/PB/PS
        -- ranks exist on daily_fundamentals; use transparent CASE buckets.
        -- Negative/zero/non-finite ratios are excluded from the average; if none
        -- usable, fall back to neutral 50.
        COALESCE(
            (
                if(dv.pe IS NULL OR NOT isFinite(dv.pe) OR dv.pe <= 0, 0.0,
                    multiIf(
                        dv.pe < 10, 100.0,
                        dv.pe < 15, 85.0,
                        dv.pe < 20, 70.0,
                        dv.pe < 25, 55.0,
                        dv.pe < 35, 40.0,
                        dv.pe < 50, 25.0,
                        10.0
                    )
                ) +
                if(dv.pb IS NULL OR NOT isFinite(dv.pb) OR dv.pb <= 0, 0.0,
                    multiIf(
                        dv.pb < 1, 100.0,
                        dv.pb < 2, 85.0,
                        dv.pb < 3, 70.0,
                        dv.pb < 5, 55.0,
                        dv.pb < 8, 40.0,
                        dv.pb < 15, 25.0,
                        10.0
                    )
                ) +
                if(dv.ps IS NULL OR NOT isFinite(dv.ps) OR dv.ps <= 0, 0.0,
                    multiIf(
                        dv.ps < 1, 100.0,
                        dv.ps < 2, 85.0,
                        dv.ps < 4, 70.0,
                        dv.ps < 6, 55.0,
                        dv.ps < 10, 40.0,
                        dv.ps < 15, 25.0,
                        10.0
                    )
                )
            ) / nullIf(
                if(dv.pe IS NULL OR NOT isFinite(dv.pe) OR dv.pe <= 0, 0, 1) +
                if(dv.pb IS NULL OR NOT isFinite(dv.pb) OR dv.pb <= 0, 0, 1) +
                if(dv.ps IS NULL OR NOT isFinite(dv.ps) OR dv.ps <= 0, 0, 1),
                0
            ),
            50.0
        ) AS valuation_rating,

        LEAST(100.0, COALESCE(df.mrt_currentratio * 20, 0)) AS health_rating,
        LEAST(100.0, COALESCE(df.mrt_roe * 200, 0)) AS profitability_rating,
        0.0 AS dividend_rating,

        -- High Growth Momentum (0-100): SigmaRail near-term / multi-year / margin blend.
        --   ~40% near-term: ARQ YoY EPS+Rev (primary), QoQ secondary, FCF YoY +
        --                   acceleration flags when present on df
        --   ~30% multi-year: ARY 3y EPS+Rev CAGR
        --   ~30% margins: TTM gross/net (fractions → 0-100; net scaled ×200 so ~50%→100)
        -- isFinite on growth/margin inputs: NaN must not poison the blend.
        LEAST(100.0, GREATEST(0.0,
            0.40 * LEAST(100.0, GREATEST(0.0,
                (
                    0.70 * (
                        LEAST(100.0, GREATEST(0.0, if(isFinite(df.arq_eps_growth_yoy), df.arq_eps_growth_yoy, 0) * 100)) +
                        LEAST(100.0, GREATEST(0.0, if(isFinite(df.arq_revenue_growth_yoy), df.arq_revenue_growth_yoy, 0) * 100))
                    ) / 2.0 +
                    0.20 * (
                        LEAST(100.0, GREATEST(0.0, if(isFinite(df.arq_eps_growth_qoq), df.arq_eps_growth_qoq, 0) * 100)) +
                        LEAST(100.0, GREATEST(0.0, if(isFinite(df.arq_revenue_growth_qoq), df.arq_revenue_growth_qoq, 0) * 100))
                    ) / 2.0 +
                    0.10 * LEAST(100.0, GREATEST(0.0, if(isFinite(df.arq_fcf_growth_yoy), df.arq_fcf_growth_yoy, 0) * 100))
                ) + (COALESCE(df.arq_eps_acceleration_qoq, 0) + COALESCE(df.arq_revenue_acceleration_qoq, 0)) * 5.0
            )) +
            0.30 * LEAST(100.0, GREATEST(0.0,
                (
                    LEAST(100.0, GREATEST(0.0, if(isFinite(df.ary_eps_growth_3y_cagr), df.ary_eps_growth_3y_cagr, 0) * 100)) +
                    LEAST(100.0, GREATEST(0.0, if(isFinite(df.ary_revenue_growth_3y_cagr), df.ary_revenue_growth_3y_cagr, 0) * 100))
                ) / 2.0
            )) +
            0.30 * LEAST(100.0, GREATEST(0.0,
                (
                    LEAST(100.0, GREATEST(0.0, if(isFinite(df.mrt_grossmargin), df.mrt_grossmargin, 0) * 100)) +
                    LEAST(100.0, GREATEST(0.0, if(isFinite(df.mrt_netmargin), df.mrt_netmargin, 0) * 200))
                ) / 2.0
            ))
        )) AS high_growth_momentum_rating,

        -- Fundamental composite: average of 5 core pillars (excludes HGM specialty)
        (
            growth_rating +
            valuation_rating +
            health_rating +
            profitability_rating +
            dividend_rating
        ) / 5.0 AS fundamental_composite,

        LEAST(100.0, COALESCE(sa.stage_quality * 100.0 / 90.0, 0)) AS weinstein_score,
        LEAST(100.0, GREATEST(0.0, if(isFinite(df.ary_eps_growth_3y_cagr), df.ary_eps_growth_3y_cagr, 0) * 100)) AS oneil_score,

        LEAST(100.0, GREATEST(0.0,
            (
                LEAST(100.0, COALESCE(sa.stage_quality * 100.0 / 90.0, 0)) +
                LEAST(100.0, GREATEST(0.0, if(isFinite(df.ary_eps_growth_3y_cagr), df.ary_eps_growth_3y_cagr, 0) * 100)) +
                CASE
                    WHEN COALESCE(dmd.breakout_signal, 0) = 1 THEN 100.0
                    WHEN COALESCE(dmd.vcp_consolidation_days_5pct_30d, 0) >= 10 THEN 75.0
                    WHEN COALESCE(dmd.vcp_consolidation_days_5pct_30d, 0) >= 5 THEN 50.0
                    ELSE 0.0
                END
            ) / 3.0
        )) AS minervini_score,

        LEAST(100.0, GREATEST(0.0,
            (COALESCE(tr.technical_composite, 0) * 0.6) +
            (fundamental_composite * 0.4)
        )) AS _overall_raw,

        CASE
            WHEN if(isFinite(_overall_raw), _overall_raw, -1.0) >= 80 THEN 'STRONG_BUY'
            WHEN if(isFinite(_overall_raw), _overall_raw, -1.0) >= 65 THEN 'BUY'
            WHEN if(isFinite(_overall_raw), _overall_raw, -1.0) >= 50 THEN 'WATCHLIST'
            WHEN if(isFinite(_overall_raw), _overall_raw, -1.0) >= 35 THEN 'MONITOR'
            ELSE 'AVOID'
        END AS classification,

        (COALESCE(df.ary_eps_growth_3y_cagr, 0) >= 0.25) AS screen_eps_yearly,
        (COALESCE(df.arq_eps_growth_qoq, 0) >= 0.25) AS screen_eps_quarterly,
        (COALESCE(df.ary_revenue_growth_3y_cagr, 0) >= 0.25) AS screen_revenue_yearly,
        (COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25) AS screen_revenue_quarterly,
        (COALESCE(df.ary_eps_growth_3y_cagr, 0) >= 0.25 AND COALESCE(df.ary_revenue_growth_3y_cagr, 0) >= 0.25) AS screen_combo_yearly,
        (COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25 AND COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25) AS screen_combo_quarterly,

        CAST(
            if(COALESCE(df.ary_eps_growth_3y_cagr, 0) >= 0.25, 1, 0) +
            if(COALESCE(df.arq_eps_growth_qoq, 0) >= 0.25, 1, 0) +
            if(COALESCE(df.ary_revenue_growth_3y_cagr, 0) >= 0.25, 1, 0) +
            if(COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25, 1, 0) +
            if(COALESCE(df.ary_eps_growth_3y_cagr, 0) >= 0.25 AND COALESCE(df.ary_revenue_growth_3y_cagr, 0) >= 0.25, 1, 0) +
            if(COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25 AND COALESCE(df.arq_revenue_growth_qoq, 0) >= 0.25, 1, 0)
        AS UInt8) AS screens_passed,

        (
            COALESCE(dmd.vcp_atr_compression_5d_90d, 1) <= 0.40
            AND COALESCE(dmd.vcp_volume_dryup_5d_90d, 1) <= 0.70
            AND COALESCE(dmd.vcp_proximity_90d, 0) >= 0.90
        ) AS has_vcp_setup,
        (COALESCE(dmd.breakout_signal, 0) = 1) AS has_vcp_breakout,
        (COALESCE(mrs.weekly_allocation_fraction, 0) >= 0.50) AS is_bull_market,
        -- industry_group_rank = percent_rank of industry avg RS **across industries** (0-100,
        -- higher = stronger). The cut below is the top quartile OF INDUSTRY GROUPS, which is what
        -- "leading industry group" means: measured 2026-09-23 there were 298 industries with ranks
        -- evenly spread (p25 = 25, p50 = 50, p75 = 75) and 25.2% of industries passed >= 75.
        -- Because industry sizes differ this is NOT a quartile of tickers — it passes ~63% of the
        -- ticker-weighted universe (ticker-weighted p75 was 80.1 that day). For a ticker-level
        -- quartile, cut at the ticker-weighted p75 computed per date instead of the literal 75.
        -- Missing rank => false (fails closed, which is correct).
        (COALESCE(igs.industry_group_rank, 0) >= 75) AS is_leading_industry,
        (left(ifNull(sa.stage_code, ''), 1) = '2') AS is_stage_2_advancing,

        now() AS lastupdated

    FROM daily_fundamentals df FINAL
    LEFT JOIN stage_analysis sa FINAL ON df.ticker = sa.ticker AND df.date = sa.date
    LEFT JOIN daily_metrics_derived dmd FINAL ON df.ticker = dmd.ticker AND df.date = dmd.date
    LEFT JOIN market_regime_signals_daily mrs FINAL ON df.date = mrs.date
    LEFT JOIN technical_ratings tr FINAL ON df.ticker = tr.ticker AND df.date = tr.date
    LEFT JOIN daily_valuation dv FINAL ON df.ticker = dv.ticker AND df.date = dv.date
    LEFT JOIN tickers t FINAL ON df.ticker = t.ticker
    LEFT JOIN industry_group_strength igs FINAL
        ON df.date = igs.date AND t.sicindustry = igs.industry
    WHERE df.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
) AS _sr_inner;
