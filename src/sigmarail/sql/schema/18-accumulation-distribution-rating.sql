-- ============================================================================
-- Accumulation/Distribution Rating Table Schema
-- ============================================================================
-- Purpose: IBD-style institutional sponsorship rating (1-99 scale)
--
-- This rating identifies institutional buying and selling pressure through
-- volume analysis. It's the "I" in O'Neil's CAN SLIM system.
--
-- Attribution:
-- - Accumulation/Distribution concept: William O'Neil (IBD/CAN SLIM, 1988)
-- - Pocket Pivots: Gil Morales & Chris Kacher (2007)
-- - Volume analysis: Multiple traders (Wyckoff, O'Neil, Minervini)
--
-- Why this is critical:
-- - Institutions move 75%+ of market volume
-- - Accumulation often precedes breakouts by weeks/months
-- - Distribution signals weakening support
-- - Key signal for both O'Neil (CAN SLIM "I") and Minervini (SEPA)
--
-- Rating Scale (1-99, IBD-style):
-- - 90-99: Extreme accumulation (institutions aggressively buying)
-- - 70-89: Strong accumulation
-- - 50-69: Moderate accumulation
-- - 30-49: Neutral (mixed or low volume)
-- - 10-29: Distribution (selling pressure)
-- - 1-9: Extreme distribution
--
-- Dependencies:
-- - daily_metrics: volume, close, avg_vol_20d, sma10d, sma50d
-- - OBV is computed in transform 67 (not a stored daily_metrics column)
-- - Volume patterns: pocket pivots, volume surges, dry-ups
--
-- Storage: ~20 MB per year (~6 columns × ~8000 tickers × 252 days)
-- ============================================================================

CREATE TABLE IF NOT EXISTS accumulation_distribution_rating
(
    `ticker` String COMMENT 'Equity ticker symbol',
    `date` Date COMMENT 'Trading session date',
    `volume_score` Float32 COMMENT 'Volume characteristics (40 points) - Up days with volume vs down days',
    `pocket_pivot_score` Float32 COMMENT 'Pocket pivot signal (0 or 30) - Up day, vol > max of prior ~10 down days, price near/through sma10d/sma50d [Morales & Kacher]',
    `volume_ratio_score` Float32 COMMENT 'Up/Down volume ratio 50-day (20 points) - Cumulative buying pressure',
    `obv_score` Float32 COMMENT 'OBV SMA-stack score (+10/0/-10) - Rising/falling Granville OBV via sma50/150/200 of cumulative OBV [computed in transform 67]',
    `accumulation_distribution_rating` UInt8 COMMENT 'Institutional sponsorship rating (1-99) - The "I" in CAN SLIM [William O\'Neil]',
    `lastupdated` DateTime DEFAULT now() COMMENT 'Timestamp when this record was calculated and inserted'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Accumulation/Distribution Rating (1-99) - Institutional buying/selling pressure (CAN SLIM "I")';

-- ============================================================================
-- Calculation Logic (implemented in 67-accumulation-distribution-rating.sql):
-- ============================================================================
--
-- volume_score (40 points):
--   +40: Volume > 2.0× avg_vol_20d AND price up (Huge accumulation)
--   +30: Volume > 1.5× avg AND price up (Strong accumulation)
--   +20: Volume > 1.2× avg AND price up (Moderate accumulation)
--   +10: Volume < 0.8× avg AND price down (Good - low volume decline)
--   -30: Volume > 1.5× avg AND price down (Distribution!)
--    0: Neutral/mixed
--
-- pocket_pivot_score (30 points) [Morales & Kacher]:
--   +30 when ALL of:
--     - Up day (close > prior close)
--     - Today's volume > max volume of the prior ~10 down days
--       (down days collected over a 60-session lookback, then last 10)
--     - Price near/through short MA: close >= 0.98×sma10d OR close >= 0.98×sma50d
--    0: No pocket pivot
--   (Institutions stepping in near support / short MA)
--
-- volume_ratio_score (20 points):
--   +20: 50d up/down volume ratio > 2.0 (2:1 buying)
--   +15: Ratio > 1.5
--   +10: Ratio > 1.2
--   -15: Ratio < 0.8 (More selling)
--    0: Neutral
--
-- obv_score (10 points) [Granville OBV, scored via SMA stack]:
--   Cumulative OBV_t = OBV_{t-1} + sign(close_t - close_{t-1}) × volume_t
--   Compare SMAs of that series (computed in transform, not stored):
--   +10: obv_sma50 > obv_sma150 > obv_sma200 (Rising OBV = accumulation)
--   -10: obv_sma50 < obv_sma150 < obv_sma200 (Falling OBV = distribution)
--    0: Mixed
--   Screen tip: filter obv_score > 0 for accumulation stack.
--
-- Final rating = 50 + sum(all scores), clamped to 1-99
-- ============================================================================

-- ============================================================================
-- Usage Examples:
-- ============================================================================

-- Example 1: Find stocks with strong institutional sponsorship
-- SELECT ticker, date, accumulation_distribution_rating, volume_score, pocket_pivot_score
-- FROM accumulation_distribution_rating
-- WHERE date = today()
--   AND accumulation_distribution_rating >= 80
-- ORDER BY accumulation_distribution_rating DESC
-- LIMIT 20;

-- Example 2: Find recent pocket pivots (institutional buying on pullback)
-- SELECT ticker, date, accumulation_distribution_rating, pocket_pivot_score
-- FROM accumulation_distribution_rating
-- WHERE date >= today() - INTERVAL 5 DAY
--   AND pocket_pivot_score >= 30
-- ORDER BY date DESC, accumulation_distribution_rating DESC;

-- Example 3: Identify distribution (selling pressure)
-- SELECT ticker, date, accumulation_distribution_rating, volume_score, obv_score
-- FROM accumulation_distribution_rating
-- WHERE date = today()
--   AND accumulation_distribution_rating <= 30
-- ORDER BY accumulation_distribution_rating ASC
-- LIMIT 20;

-- Example 4: Join with technical ratings for complete analysis
-- SELECT
--     adr.ticker,
--     adr.date,
--     adr.accumulation_distribution_rating,
--     tr.technical_rating,
--     tr.setup_quality_rating
-- FROM accumulation_distribution_rating adr
-- JOIN technical_ratings tr ON adr.ticker = tr.ticker AND adr.date = tr.date
-- WHERE adr.date = today()
--   AND adr.accumulation_distribution_rating >= 70
--   AND tr.technical_rating >= 8.0
-- ORDER BY adr.accumulation_distribution_rating DESC
-- LIMIT 20;

-- ============================================================================

-- Managed transform view for target: accumulation_distribution_rating
-- ============================================================================
-- Accumulation/Distribution Rating Transform
-- ============================================================================
-- Attribution:
--   - Accumulation/Distribution concept: William O'Neil (CAN SLIM "I", 1988)
--   - Pocket Pivots: Gil Morales & Chris Kacher (2007)
--   - On-Balance Volume: Joseph Granville
--
-- Component weights (sum into final rating via 50 + sum, clamped 1–99):
--   volume_score          ±40  — up-day volume vs avg, down-day dry-up / distribution
--   pocket_pivot_score      30  — Morales/Kacher pocket pivot event (0 or 30)
--   volume_ratio_score    ±20  — 50d up/down volume ratio
--   obv_score             ±10  — OBV SMA stack (50d / 150d / 200d of cumulative OBV)
--
-- OBV is computed inside this transform from daily_metrics (sign of close change
-- × volume, Granville). No separate `obv` column is required.
--
-- Chunk lookback: ~400 calendar days so OBV SMA200 and the prior-10 down-day
-- volume window are populated at chunk boundaries (see outer date filter).
-- ============================================================================
--
DROP VIEW IF EXISTS xform_accumulation_distribution_rating;

CREATE VIEW IF NOT EXISTS xform_accumulation_distribution_rating (
    ticker,
    date,
    volume_score,
    pocket_pivot_score,
    volume_ratio_score,
    obv_score,
    accumulation_distribution_rating,
    lastupdated
)
COMMENT '{"order":67,"target":"accumulation_distribution_rating","sources":["daily_metrics"],"chunk_size":"3m"}'
AS
WITH
-- ----------------------------------------------------------------------------
-- 1) Base bars + 1-day price change (lookback beyond chunk for windows below)
-- ----------------------------------------------------------------------------
price_changes AS (
    SELECT
        ticker,
        date,
        close,
        volume,
        avg_vol_20d,
        sma10d,
        sma50d,
        close - lagInFrame(close, 1) OVER (PARTITION BY ticker ORDER BY date) AS price_change
    FROM daily_metrics FINAL
    WHERE date >= addDays(toDate({chunk_start_date:String}), -400)
      AND date <= toDate({chunk_end_date:String})
      AND volume IS NOT NULL
      AND avg_vol_20d IS NOT NULL
),

-- ----------------------------------------------------------------------------
-- 2) Cumulative OBV (Granville) — no nested windows; next CTE averages this
-- ----------------------------------------------------------------------------
with_obv AS (
    SELECT
        ticker,
        date,
        close,
        volume,
        avg_vol_20d,
        sma10d,
        sma50d,
        price_change,
        sum(
            multiIf(
                price_change > 0, toFloat64(volume),
                price_change < 0, -toFloat64(volume),
                0.0
            )
        ) OVER (
            PARTITION BY ticker
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS obv
    FROM price_changes
),

-- ----------------------------------------------------------------------------
-- 3) Prior down-day volume array (for pocket pivot) + 50d up/down + OBV SMAs
-- ----------------------------------------------------------------------------
enriched AS (
    SELECT
        ticker,
        date,
        close,
        volume,
        avg_vol_20d,
        sma10d,
        sma50d,
        price_change,
        obv,

        -- Down-day volumes over prior 60 sessions (excludes today), chronological.
        arrayFilter(
            x -> isNotNull(x),
            groupArray(if(price_change < 0, toFloat64(volume), NULL)) OVER (
                PARTITION BY ticker
                ORDER BY date
                ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
            )
        ) AS prior_down_vols,

        sum(if(price_change > 0, toFloat64(volume), 0.0)) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) AS up_vol_50d,
        sum(if(price_change < 0, toFloat64(volume), 0.0)) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) AS down_vol_50d,

        avg(obv) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) AS obv_sma50,
        avg(obv) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
        ) AS obv_sma150,
        avg(obv) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
        ) AS obv_sma200
    FROM with_obv
),

-- ----------------------------------------------------------------------------
-- 4) Component scores (point contributions; see header / schema 18 comments)
-- ----------------------------------------------------------------------------
scored AS (
    SELECT
        ticker,
        date,

        -- volume_score (40 pts): up-day volume expansion / down-day dry-up vs distribution
        CASE
            WHEN (volume / nullIf(avg_vol_20d, 0)) > 2.0 AND price_change > 0 THEN 40.0
            WHEN (volume / nullIf(avg_vol_20d, 0)) > 1.5 AND price_change > 0 THEN 30.0
            WHEN (volume / nullIf(avg_vol_20d, 0)) > 1.2 AND price_change > 0 THEN 20.0
            WHEN (volume / nullIf(avg_vol_20d, 0)) < 0.8 AND price_change < 0 THEN 10.0
            WHEN (volume / nullIf(avg_vol_20d, 0)) > 1.5 AND price_change < 0 THEN -30.0
            ELSE 0.0
        END AS volume_score,

        -- pocket_pivot_score (30 pts):
        --   Morales/Kacher: up day, volume > max of prior ~10 down-day volumes,
        --   and price near/through short MA (sma10d or sma50d, within 2% below or above).
        CASE
            WHEN price_change > 0
             AND notEmpty(prior_down_vols)
             AND volume > arrayMax(
                    arraySlice(
                        prior_down_vols,
                        greatest(toInt64(1), toInt64(length(prior_down_vols)) - 9)
                    )
                 )
             AND (
                    (sma10d IS NOT NULL AND close >= sma10d * 0.98)
                 OR (sma50d IS NOT NULL AND close >= sma50d * 0.98)
             )
            THEN 30.0
            ELSE 0.0
        END AS pocket_pivot_score,

        -- volume_ratio_score (20 pts): 50d cumulative up/down volume
        CASE
            WHEN down_vol_50d = 0 AND up_vol_50d > 0 THEN 20.0
            WHEN down_vol_50d = 0 THEN 0.0
            WHEN (up_vol_50d / down_vol_50d) > 2.0 THEN 20.0
            WHEN (up_vol_50d / down_vol_50d) > 1.5 THEN 15.0
            WHEN (up_vol_50d / down_vol_50d) > 1.2 THEN 10.0
            WHEN (up_vol_50d / down_vol_50d) < 0.8 THEN -15.0
            ELSE 0.0
        END AS volume_ratio_score,

        -- obv_score (10 pts): rising/falling OBV via SMA stack of cumulative OBV
        --   Screen tip: obv_score > 0 ⇒ accumulation stack; < 0 ⇒ distribution stack.
        CASE
            WHEN obv_sma50 > obv_sma150 AND obv_sma150 > obv_sma200 THEN 10.0
            WHEN obv_sma50 < obv_sma150 AND obv_sma150 < obv_sma200 THEN -10.0
            ELSE 0.0
        END AS obv_score
    FROM enriched
    WHERE date >= toDate({chunk_start_date:String})
      AND date <= toDate({chunk_end_date:String})
)

SELECT
    ticker,
    date,
    volume_score,
    pocket_pivot_score,
    volume_ratio_score,
    obv_score,
    CAST(
        least(99, greatest(1,
            50
            + volume_score
            + pocket_pivot_score
            + volume_ratio_score
            + obv_score
        )) AS UInt8
    ) AS accumulation_distribution_rating,
    now() AS lastupdated
FROM scored;
