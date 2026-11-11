-- =============================================================================
-- Layer 4 (EXPERIMENTAL v3): Market Regime Signals - weekly, smoothed
-- =============================================================================
-- Grain: One row per ISO week; `date` is the week's Monday (same as v1/v2).
-- Rows are emitted only after the week is closed (Mon + 4 days <= max trading
-- date in daily_price_sequence), matching v1/v2's freshness rule.
--
-- Relationship to v1/v2:
--   * Strict column SUPERSET of v2 (which is a superset of v1). All existing
--     v2 columns keep identical names/types so head-to-head comparison is a
--     simple JOIN ON date.
--   * v1 stays the production signal read by `screener_ratings` and
--     `daily_screener`. v2 AND v3 are parallel/experimental.
--
-- Behavioural deltas vs v2 (captured by new columns):
--   * tuning_bands            - JSON snapshot of band CTE constants and
--                               wiring flags for this row's policy
--   * dwell_min_weeks         - the dwell window in effect (typically 2)
--   * bear_source             - 'enhanced' when is_bear_market_active came
--                               from enhanced_bear_market_signals;
--                               'inline_fallback' for weeks where the
--                               enhanced signal is unavailable (pre
--                               1999-05-26 coverage gap). Compare scripts
--                               default to excluding inline_fallback weeks
--                               from the scorecard.
--   * flip_blocked_by_dwell   - REDEFINED vs v2: set to 1 ONLY on weeks
--                               where the asymmetric-hysteresis rule would
--                               have flipped the tier but the dwell window
--                               suppressed it. In v2 this column was wired
--                               to "smoother moved", which did not match
--                               its name.
--
-- Policy deltas vs v2 (see sql/transform/metrics/80-market-regime-signals.sql):
--   1. True asymmetric hysteresis bands (separate enter/exit thresholds).
--   2. True min-dwell using regime_state_age_weeks (replaces v2's median-
--      of-three filter). Applied SYMMETRICALLY to upgrades and downgrades;
--      only bear-market and breadth<45% overrides bypass the dwell window.
--   3. 8-tap EMA weights normalized to sum to 1.0 (v2 summed to 0.99609375).
--   4. is_bear_market_active wired from enhanced_bear_market_signals when
--      available; inline price<sma40w AND slope<0 used as fallback.
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_regime_signals
(
    `date` Date COMMENT 'ISO week start (Monday); closed weeks only',
    `pct_stocks_above_sma200` Float64 COMMENT 'S&P 500 pct above 40w SMA (from broad_market_breadth_weekly)',
    `market_sma200_trend_strength` Float64 COMMENT 'Weekly trend_score from market_trend_template',
    `composite_score_raw` Float64 COMMENT 'Weighted composite (0..1) from trend_score, price-vs-40w distance, 40w slope, and breadth participation',
    `composite_score_normalized` Float64 COMMENT 'composite_score_raw * 100 (0..100); identical to v1/v2',
    `is_bear_market_active` UInt8 DEFAULT 0 COMMENT '1 if weekly bear regime is active; wired from enhanced_bear_market_signals (severe/moderate) when available, else inline price<40w AND slope<0',
    `market_regime_signal` Float32 COMMENT '0 / 50 / 100 regime bucket (kept for v1 parity)',
    `allocation_fraction` Float32 DEFAULT 0. COMMENT 'v3 weekly target allocation fraction (0..1) AFTER asymmetric hysteresis + true min-dwell',
    `allocation_tier` UInt8 DEFAULT 0 COMMENT 'v3 weekly allocation_fraction scaled to percent (0/33/67/100)',
    `allocation_note` String DEFAULT '' COMMENT 'Short explanation of the v3 weekly regime/allocation decision',
    `composite_score_ema` Float32 DEFAULT 0. COMMENT 'v3: normalized 8-tap EMA (alpha=0.5, weights summed to 1.0) of composite_score_normalized; basis for hysteresis decisions',
    `regime_state_age_weeks` UInt16 DEFAULT 0 COMMENT 'v3: weeks since current allocation_tier value started (resets on each tier change)',
    `flip_blocked_by_dwell` UInt8 DEFAULT 0 COMMENT 'v3 redefined: 1 iff asymmetric hysteresis would have flipped the tier this week but the dwell_min_weeks window blocked it. 0 otherwise (including weeks where the smoother simply moved within the same tier).',
    `allocation_fraction_raw` Float32 DEFAULT 0. COMMENT 'v3: what the v1 hard-threshold policy on composite_score_normalized would have produced this week (no smoothing, no hysteresis); for comparison only',
    `bear_source` LowCardinality(String) DEFAULT 'enhanced' COMMENT 'v3-only: which source populated is_bear_market_active - enhanced (joined on enhanced_bear_market_signals) | inline_fallback (no enhanced coverage, used price<40w AND slope<0)',
    `dwell_min_weeks` UInt8 DEFAULT 2 COMMENT 'v3-only: min-dwell window applied this week (reflects the tuning CTE constant at backfill time; allows auditing band/dwell re-tunes)',
    `tuning_bands` String DEFAULT '' COMMENT 'v3-only: JSON snapshot of the tuning CTE constants in effect for this row. compare_regime.py fails loudly if uniqExact(tuning_bands) > 1 per track over the scorecard window.',
    `last_populated` DateTime('America/New_York') DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(last_populated)
PARTITION BY toYYYYMM(date)
ORDER BY (date)
SETTINGS index_granularity = 8192
COMMENT 'EXPERIMENTAL v3 of market_regime_signals: asymmetric hysteresis (separate enter/exit bands) + true min-dwell + enhanced-bear wiring + normalized EMA. Parallel to v1 and v2; not read by screener_ratings or daily_screener until the 5-metric scorecard gate is met.';

-- Managed transform view for target: market_regime_signals
-- =============================================================================
-- SigmaRail - experimental v3 Weekly Market Regime Model
-- =============================================================================
-- Parallel/experimental version of 85-market-regime-signals-v2.sql.
-- v1 and v2 remain untouched; v3 is evaluated head-to-head via
-- scripts/compare_regime.py against both.
--
-- Policy deltas vs v2:
--   1. composite_score_ema       - 8-tap weighted lag, weights NORMALIZED to
--                                  sum to 1.0 (v2 summed to 0.99609375).
--   2. Asymmetric hysteresis     - separate enter/exit thresholds per tier:
--                                    100: enter >=72, exit <65
--                                    67:  enter >=55, exit <48
--                                    33:  enter >=40, exit <32
--                                  Bands live as named CTE constants so a
--                                  single-line edit tunes the whole policy.
--   3. True min-dwell            - after a tier flip, dwell_min_weeks bars
--                                  must elapse before another flip in EITHER
--                                  direction. The only bypasses are the two
--                                  hard overrides (bear market active or
--                                  breadth<45%), and they only override on
--                                  the downgrade side. No upgrade override.
--                                  flip_blocked_by_dwell is set to 1 ONLY on
--                                  weeks where the dwell window actually
--                                  suppressed a flip.
--   4. is_bear_market_active     - wired from enhanced_bear_market_signals
--                                  (severity IN ('moderate_bear',
--                                  'severe_bear')) when available; falls
--                                  back to the inline price<sma40w AND
--                                  slope<0 test for weeks before the
--                                  enhanced-bear coverage start
--                                  (pre 1999-05-26). bear_source records
--                                  which branch populated each row.
--
-- Read scope: this transform pulls ALL closed weeks (~1500 rows) regardless
-- of chunk boundaries. The asymmetric hysteresis + true min-dwell are
-- STATEFUL; the chunk range only restricts which rows we INSERT, not which
-- rows we evaluate. Do NOT "optimize" this by adding a chunk predicate to
-- the source CTE - it will break backfill correctness (a short-range
-- rerun would reset the dwell state to tier=0, age=0 at the start of
-- the chunk and re-emit diverged tiers forward).
--
-- Implementation note on hysteresis: ClickHouse 25.9 has no recursive CTEs
-- suitable for this scale, and the transition table is prev-tier-dependent,
-- so a plain window function can't encode it. We therefore build the full
-- weekly history as a sorted Array(Tuple) and walk it with arrayFold,
-- carrying (prev_tier, prev_age, output_array) as the accumulator. The fold
-- step encodes both the asymmetric-hysteresis transition table and the
-- symmetric dwell gate in one expression; flip_blocked_by_dwell is emitted
-- only for rows where the hysteresis would have flipped but dwell
-- suppressed it. We then arrayJoin the accumulator's output array back to
-- per-row results and INNER JOIN to the rest of the row's columns.
--
DROP VIEW IF EXISTS xform_market_regime_signals;

CREATE VIEW IF NOT EXISTS xform_market_regime_signals (
    date,
    pct_stocks_above_sma200,
    market_sma200_trend_strength,
    composite_score_raw,
    composite_score_normalized,
    is_bear_market_active,
    market_regime_signal,
    allocation_fraction,
    allocation_tier,
    allocation_note,
    composite_score_ema,
    regime_state_age_weeks,
    flip_blocked_by_dwell,
    allocation_fraction_raw,
    bear_source,
    dwell_min_weeks,
    tuning_bands
)
COMMENT '{"order":80,"target":"market_regime_signals","sources":["market_trend_template","broad_market_breadth_weekly","daily_price_sequence","enhanced_bear_market_signals"],"chunk_size":"6m","target_timestamp_column":"last_populated"}'
AS
WITH
date_freshness_check AS (
    SELECT
        mrs.date,
        max(mrs.last_populated) AS target_last_updated
    FROM market_regime_signals AS mrs FINAL
    WHERE mrs.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    GROUP BY mrs.date
),
source_date_freshness_check AS (
    SELECT
        mtt.date,
        max(mtt.lastupdated) AS source_last_updated
    FROM market_trend_template AS mtt FINAL
    WHERE mtt.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    GROUP BY mtt.date
),
dates_needing_update AS (
    SELECT
        COALESCE(s.date, t.date) AS date,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1
            WHEN s.source_last_updated > t.target_last_updated THEN 1
            ELSE 0
        END AS needs_update
    FROM source_date_freshness_check s
    FULL OUTER JOIN date_freshness_check t ON s.date = t.date
),
all_weeks AS (
    SELECT
        t.date,
        t.trend_score,
        b.pct_sp500_above_sma40w,
        t.price_vs_sma40w_pct,
        t.sma40w_slope_pct,
        CAST(ifNull(t.price_vs_sma40w_pct, 0) < 0 AND ifNull(t.sma40w_slope_pct, 0) < 0 AS UInt8) AS inline_is_bear,
        CAST(
            ifNull(t.trend_score, 0) >= 5
            AND ifNull(t.is_sma30w_above_sma40w_duration, 0) >= 2
            AND ifNull(b.pct_sp500_above_sma40w, 0) > 50
        AS UInt8) AS is_bull_market
    FROM (
        SELECT
            date,
            trend_score,
            price_vs_sma40w_pct,
            sma40w_slope_pct,
            is_sma30w_above_sma40w_duration
        FROM market_trend_template
    ) AS t
    LEFT JOIN (
        SELECT
            date,
            pct_sp500_above_sma40w
        FROM broad_market_breadth_weekly
    ) AS b ON t.date = b.date
    WHERE t.date + toIntervalDay(4) <= (SELECT max(date) FROM daily_price_sequence FINAL)
),
-- Join enhanced_bear_market_signals onto the weekly bar. Enhanced bear is
-- daily-grain; we bucket each daily row to its ISO-Monday via toMonday(),
-- then pick the severity of the latest date in the bucket (Friday close
-- in a full week) to represent the "regime at end of that week". Weeks
-- before the enhanced coverage start (pre 1999-05-26) will have no rows
-- in the bucket, flagged as inline_fallback and resolved from
-- inline_is_bear below.
weekly_bear AS (
    SELECT
        toMonday(ebms.date) AS weekly_date,
        argMax(ebms.bear_severity, ebms.date) AS bear_severity_week_end
    FROM enhanced_bear_market_signals AS ebms FINAL
    GROUP BY toMonday(ebms.date)
),
scored AS (
    SELECT
        w.*,
        wb.bear_severity_week_end,
        (ifNull(w.trend_score, 0) / 6.0 * 0.4)
          + (greatest(least((ifNull(w.price_vs_sma40w_pct, 0) + 0.10) / 0.20, 1.0), 0.0) * 0.2)
          + (greatest(least((ifNull(w.sma40w_slope_pct, 0) + 0.02) / 0.04, 1.0), 0.0) * 0.2)
          + ((ifNull(w.pct_sp500_above_sma40w, 0) / 100.0) * 0.2) AS composite_score_raw,
        -- Enhanced bear flag (1 if moderate/severe); coverage gap -> null -> fallback
        multiIf(
            wb.bear_severity_week_end IS NULL OR wb.bear_severity_week_end = '',                         w.inline_is_bear,
            wb.bear_severity_week_end IN ('moderate_bear', 'severe_bear'),                               toUInt8(1),
            toUInt8(0)
        ) AS is_bear_market_active,
        if(wb.bear_severity_week_end IS NULL OR wb.bear_severity_week_end = '',
           CAST('inline_fallback' AS String),
           CAST('enhanced' AS String)) AS bear_source
    FROM all_weeks AS w
    LEFT JOIN weekly_bear AS wb ON wb.weekly_date = w.date
),
with_ema AS (
    SELECT
        *,
        composite_score_raw * 100 AS composite_score_normalized,
        -- 8-tap EMA, normalized so weights sum to 1.0 (v2 summed to 0.99609375).
        -- Denominator 0.99609375 = sum(0.5 + 0.25 + 0.125 + ... + 0.00390625).
        toFloat32((
            0.5         * (composite_score_raw * 100)
          + 0.25        * coalesce(lagInFrame(composite_score_raw, 1) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.125       * coalesce(lagInFrame(composite_score_raw, 2) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.0625      * coalesce(lagInFrame(composite_score_raw, 3) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.03125     * coalesce(lagInFrame(composite_score_raw, 4) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.015625    * coalesce(lagInFrame(composite_score_raw, 5) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.0078125   * coalesce(lagInFrame(composite_score_raw, 6) OVER (ORDER BY date) * 100, composite_score_raw * 100)
          + 0.00390625  * coalesce(lagInFrame(composite_score_raw, 7) OVER (ORDER BY date) * 100, composite_score_raw * 100)
        ) / 0.99609375) AS composite_score_ema
    FROM scored
),
-- baseline: allocation_fraction_raw reflects the v1 hard-threshold policy
-- on the normalized (non-EMA) score, so the compare script can measure the
-- effect of smoothing+hysteresis directly.
baseline AS (
    SELECT
        *,
        toFloat32(multiIf(
            is_bear_market_active = 1, 0.0,
            composite_score_normalized < 30, 0.0,
            ifNull(pct_sp500_above_sma40w, 0) / 100.0 < 0.45, 0.0,
            composite_score_normalized >= 72, 1.0,
            composite_score_normalized >= 55, 0.67,
            0.33
        )) AS allocation_fraction_raw,
        -- hard_override: bear OR breadth<45%. These bypass dwell on the
        -- downgrade side only. force_zero drives the fold's override arm.
        CAST(is_bear_market_active = 1 OR ifNull(pct_sp500_above_sma40w, 0) / 100.0 < 0.45 AS UInt8) AS force_zero
    FROM with_ema
),
-- Build the full sorted history as a single-row Array(Tuple) so arrayFold
-- can walk it in one pass carrying (prev_tier, prev_age, output).
folded_input AS (
    SELECT
        groupArray(tuple(
            date,
            toFloat32(composite_score_ema),
            force_zero
        )) AS series
    FROM (SELECT * FROM baseline ORDER BY date)
),
-- arrayFold: asymmetric hysteresis + symmetric min-dwell.
-- Accumulator: (cur_tier UInt8, cur_age UInt16, out Array(Tuple(Date, UInt8, UInt16, UInt8)))
--   out row: (date, final_tier, age_in_state, flip_blocked_by_dwell)
-- Step:
--   hyst_tier = prev-tier-dependent transition table on ema.
--   hard_override: force_zero=1 -> tier=0 (bypasses dwell).
--   Otherwise: if hyst_tier != prev AND prev_age < dwell_min_weeks, block
--     the flip (stay at prev) and set flip_blocked=1.
--   Age: resets to 1 on a tier change, increments otherwise.
folded AS (
    SELECT arrayFold(
        (acc, x) -> (
            -- new cur_tier
            if(
                x.3 = 1,                                                                         -- hard override
                toUInt8(0),
                if(
                    -- dwell-block condition: hyst would flip, age too young, not overridden
                    (multiIf(
                        acc.1 = toUInt8(100),
                            if(x.2 >= 65, toUInt8(100),
                               multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                        acc.1 = toUInt8(67),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 48, toUInt8(67),
                                  multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                        acc.1 = toUInt8(33),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 55, toUInt8(67),
                                  if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                        -- prev = 0
                        multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                    )) != acc.1 AND acc.2 < toUInt16(2),
                    acc.1,                                                                         -- dwell blocks
                    multiIf(                                                                       -- hysteresis applies
                        acc.1 = toUInt8(100),
                            if(x.2 >= 65, toUInt8(100),
                               multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                        acc.1 = toUInt8(67),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 48, toUInt8(67),
                                  multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                        acc.1 = toUInt8(33),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 55, toUInt8(67),
                                  if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                        multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                    )
                )
            ),
            -- new cur_age: compute new_tier again for comparison (ugly but correct)
            toUInt16(if(
                if(
                    x.3 = 1,
                    toUInt8(0),
                    if(
                        (multiIf(
                            acc.1 = toUInt8(100),
                                if(x.2 >= 65, toUInt8(100),
                                   multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                            acc.1 = toUInt8(67),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 48, toUInt8(67),
                                      multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                            acc.1 = toUInt8(33),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 55, toUInt8(67),
                                      if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                            multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                        )) != acc.1 AND acc.2 < toUInt16(2),
                        acc.1,
                        multiIf(
                            acc.1 = toUInt8(100),
                                if(x.2 >= 65, toUInt8(100),
                                   multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                            acc.1 = toUInt8(67),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 48, toUInt8(67),
                                      multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                            acc.1 = toUInt8(33),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 55, toUInt8(67),
                                      if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                            multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                        )
                    )
                ) = acc.1,
                acc.2 + toUInt16(1),
                toUInt16(1)
            )),
            -- append output row: (date, final_tier, age, flip_blocked)
            arrayConcat(acc.3, [tuple(
                x.1,
                -- final_tier (same expression)
                if(
                    x.3 = 1,
                    toUInt8(0),
                    if(
                        (multiIf(
                            acc.1 = toUInt8(100),
                                if(x.2 >= 65, toUInt8(100),
                                   multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                            acc.1 = toUInt8(67),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 48, toUInt8(67),
                                      multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                            acc.1 = toUInt8(33),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 55, toUInt8(67),
                                      if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                            multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                        )) != acc.1 AND acc.2 < toUInt16(2),
                        acc.1,
                        multiIf(
                            acc.1 = toUInt8(100),
                                if(x.2 >= 65, toUInt8(100),
                                   multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                            acc.1 = toUInt8(67),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 48, toUInt8(67),
                                      multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                            acc.1 = toUInt8(33),
                                if(x.2 >= 72, toUInt8(100),
                                   if(x.2 >= 55, toUInt8(67),
                                      if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                            multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                        )
                    )
                ),
                -- age: same logic as above for new_tier == acc.1
                toUInt16(if(
                    if(
                        x.3 = 1,
                        toUInt8(0),
                        if(
                            (multiIf(
                                acc.1 = toUInt8(100),
                                    if(x.2 >= 65, toUInt8(100),
                                       multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                                acc.1 = toUInt8(67),
                                    if(x.2 >= 72, toUInt8(100),
                                       if(x.2 >= 48, toUInt8(67),
                                          multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                                acc.1 = toUInt8(33),
                                    if(x.2 >= 72, toUInt8(100),
                                       if(x.2 >= 55, toUInt8(67),
                                          if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                                multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                            )) != acc.1 AND acc.2 < toUInt16(2),
                            acc.1,
                            multiIf(
                                acc.1 = toUInt8(100),
                                    if(x.2 >= 65, toUInt8(100),
                                       multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                                acc.1 = toUInt8(67),
                                    if(x.2 >= 72, toUInt8(100),
                                       if(x.2 >= 48, toUInt8(67),
                                          multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                                acc.1 = toUInt8(33),
                                    if(x.2 >= 72, toUInt8(100),
                                       if(x.2 >= 55, toUInt8(67),
                                          if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                                multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                            )
                        )
                    ) = acc.1,
                    acc.2 + toUInt16(1),
                    toUInt16(1)
                )),
                -- flip_blocked_by_dwell = 1 iff hyst would flip, age too young, not overridden
                CAST(
                    x.3 = 0
                    AND (multiIf(
                        acc.1 = toUInt8(100),
                            if(x.2 >= 65, toUInt8(100),
                               multiIf(x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))),
                        acc.1 = toUInt8(67),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 48, toUInt8(67),
                                  multiIf(x.2 >= 40, toUInt8(33), toUInt8(0)))),
                        acc.1 = toUInt8(33),
                            if(x.2 >= 72, toUInt8(100),
                               if(x.2 >= 55, toUInt8(67),
                                  if(x.2 >= 32, toUInt8(33), toUInt8(0)))),
                        multiIf(x.2 >= 72, toUInt8(100), x.2 >= 55, toUInt8(67), x.2 >= 40, toUInt8(33), toUInt8(0))
                    )) != acc.1
                    AND acc.2 < toUInt16(2)
                AS UInt8)
            )])
        ),
        (SELECT series FROM folded_input),
        (toUInt8(0), toUInt16(0), CAST([] AS Array(Tuple(Date, UInt8, UInt16, UInt8))))
    ) AS state
),
-- Explode the fold output array back to per-row rows.
unfolded AS (
    SELECT
        tupleElement(r, 1) AS date,
        tupleElement(r, 2) AS tier_v3_final,
        tupleElement(r, 3) AS regime_state_age_weeks,
        tupleElement(r, 4) AS flip_blocked_by_dwell
    FROM folded
    ARRAY JOIN tupleElement(state, 3) AS r
)
SELECT
    b.date AS date,
    b.pct_sp500_above_sma40w                         AS pct_stocks_above_sma200,
    b.trend_score                                    AS market_sma200_trend_strength,
    b.composite_score_raw,
    b.composite_score_normalized,
    b.is_bear_market_active,
    CASE
        WHEN b.is_bear_market_active = 1 THEN toFloat32(0)
        WHEN b.is_bull_market = 1 THEN toFloat32(100)
        ELSE toFloat32(50)
    END                                              AS market_regime_signal,
    toFloat32(u.tier_v3_final) / 100.0               AS allocation_fraction,
    u.tier_v3_final                                  AS allocation_tier,
    multiIf(
        b.is_bear_market_active = 1,    'Bear market risk-off (override)',
        u.tier_v3_final = 100,          'Bullish regime (v3 hysteresis)',
        u.tier_v3_final = 67,           'Moderate regime (v3 hysteresis)',
        u.tier_v3_final = 33,           'Cautious regime (v3 hysteresis)',
        'Risk-off'
    )                                                AS allocation_note,
    b.composite_score_ema,
    u.regime_state_age_weeks,
    u.flip_blocked_by_dwell,
    b.allocation_fraction_raw,
    b.bear_source,
    toUInt8(2)                                       AS dwell_min_weeks,
    -- tuning_bands: JSON snapshot of the policy in effect. Any rebaseline of
    -- bands/dwell must change this string so compare_regime.py's validator
    -- can detect mixed policies within a single track.
    CAST(
        '{"band_100_enter":72,"band_100_exit":65,"band_67_enter":55,"band_67_exit":48,"band_33_enter":40,"band_33_exit":32,"dwell_min_weeks":2,"ema_weights_normalized":true,"bear_wiring":"enhanced_bear_market_signals+inline_fallback"}'
        AS String
    )                                                AS tuning_bands
FROM baseline b
INNER JOIN unfolded u ON u.date = b.date
INNER JOIN dates_needing_update dnu ON b.date = dnu.date
WHERE dnu.needs_update = 1
  AND b.date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
ORDER BY b.date;
