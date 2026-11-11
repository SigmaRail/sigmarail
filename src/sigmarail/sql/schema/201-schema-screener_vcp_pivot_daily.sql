-- =============================================================================
-- VCP pivot satellite: successive contractions, dry-up and breakout (Phase 2, finding V4)
-- =============================================================================
-- Canon: docs/plans/Mark Minervini SEPA & VCP Algorithmic Framework Architecture.md (Node D/E)
-- Findings: docs/decisions/2026-09-25-120539-screener-stage-vcp-math-conformance/episode.md (V1-V4)
-- Method:  docs/ai/session-notes/research/2026-09-27-vcp-external-algorithm-review.md
-- Reference: VeraBase/scripts/vcp_zigzag.py (38 tests), fold verified against it on 7/7 tickers
-- Fold evidence: VeraBase/sql/admin/vcp_zigzag_fold_check.sql (SQL fold == pandas reference, 7/7)
-- Populated by: NOT YET. Planned producer is sql/transform/metrics/131-screener-vcp-pivot-daily.sql
--   (after L7; fold must start at a FIXED floor date, not the chunk boundary, or the same
--   (ticker, date) would get a different answer depending on which chunk computed it).
--   Until that file exists, this table has no producer and stays empty.
-- Registration: registered in sql/schema/screener_l7_join.yaml (2026-09-27) as table
--   screener_vcp_pivot_daily, prefix `vp`, grain [ticker, date] — which is how the L7 join path
--   (l7_from.column_homes / l7_from_sql), the ADM security entities and query_table_v1 discover it.
--   Gate check_table_query_v1_catalog validates the manifest's internals; it cannot detect a table
--   that is missing from it, so that entry is the registration. `atr_14` is deliberately NOT a column
--   here: the spine already owns that name and the join graph needs one owner per column.
--   Contract note still owed on this slice: C-TEMPLATE-CATALOG-V1.
--
-- Why a separate table: VCP as specified is a *sequence* — successive swing highs and lows with each
-- pullback compressing roughly by half, on drying volume, confirmed by a volume breakout. Every
-- shipped vcp_* column is a per-date *level* proxy ("current 5d vs current 90d"), which is finding
-- V4: nothing compared contraction i+1 to i. Those columns stay exactly as they are (392 files
-- reference has_vcp_setup); this table adds the sequence alongside them.
--
-- Design rule: **facts stay facts, judgements stay flags.** Leg depths, the pivot line and its
-- confirmation date, per-leg volume and ATR envelopes are reported as measured. The UInt8 flags are
-- separate, parameterised judgements (VcpConfig), so a messy base degrades into flags being false
-- plus numbers that show why — never into a confidently wrong breakout level.
-- =============================================================================

CREATE TABLE IF NOT EXISTS screener_vcp_pivot_daily
(
    `ticker` LowCardinality(String) COMMENT 'Stock or ETF ticker symbol',
    `date` Date COMMENT 'Trading session (matches screener_price_tech_daily.date)',
    `zigzag_threshold_pct` Nullable(Float64) COMMENT 'Reversal threshold that confirmed the last swing at this date (ATR-scaled when configured, so it varies)',
    `contraction_count` UInt8 DEFAULT 0 COMMENT 'Counted contractions (<= max_contractions, newest last)',
    `contraction_depths` Array(Float32) COMMENT 'Counted leg depths, newest last: (H_i - L_i) / H_i',
    `leg_depths` Array(Float32) COMMENT 'Every completed leg including noise below the floor — the raw facts',
    `leg_days` Array(UInt16) COMMENT 'Sessions per counted leg, newest last',
    `leg_highs` Array(Float32) COMMENT 'High pivot price per counted leg, newest last',
    `ignored_legs` UInt8 DEFAULT 0 COMMENT 'Legs below the noise floor: reported in leg_depths, not counted',
    `contraction_depth_last` Nullable(Float32) COMMENT 'Most recent counted leg depth',
    `contraction_depth_prev` Nullable(Float32) COMMENT 'Previous counted leg depth',
    `contraction_ratio` Nullable(Float32) COMMENT 'last / prev; <= 1 compressing, ~0.5 is Node D halving',
    `first_leg_depth` Nullable(Float32) COMMENT 'Depth of the first counted leg — the base opener',
    `base_high` Nullable(Float32) COMMENT 'High that opened the counted base',
    `base_depth` Nullable(Float32) COMMENT 'base_high to the newest confirmed low, as a fraction',
    `days_in_base` UInt16 DEFAULT 0 COMMENT 'Sessions from the base-opening high to this date',
    `last_pivot_low` Nullable(Float32) COMMENT 'Newest confirmed swing low',
    `pivot_line` Nullable(Float32) COMMENT 'Most recent *confirmed* swing high — the level to break',
    `pivot_line_date` Nullable(Date) COMMENT 'Date of that high',
    `pivot_confirm_date` Nullable(Date) COMMENT 'Date it became knowable (always after pivot_line_date): the point-in-time proof',
    `days_since_pivot` Nullable(UInt16) COMMENT 'Sessions since that high',
    `dist_to_pivot_pct` Nullable(Float32) COMMENT 'close / pivot_line - 1 at this date',
    `leg_volume_ratios` Array(Float32) COMMENT 'Per counted leg: leg mean volume / 50d baseline, market-neutral',
    `volume_dryup_ratio` Nullable(Float32) COMMENT 'Newest leg volume ratio — supply absorbed when falling',
    `breakout_volume_ratio` Nullable(Float32) COMMENT 'volume / avg_vol_50d at this date',
    `leg_atr_ratios` Array(Float32) COMMENT 'Per counted leg: leg mean ATR / 50d baseline — the Substack envelope read',
    `depths_descending` UInt8 DEFAULT 0 COMMENT 'Strictly shallower each leg',
    `depths_descending_tol` UInt8 DEFAULT 0 COMMENT 'Shallower within level_tolerance (Lo-Mamaysky-Wang style)',
    `highs_descending` UInt8 DEFAULT 0 COMMENT 'Strictly lower highs',
    `highs_descending_tol` UInt8 DEFAULT 0 COMMENT 'Lower highs within tolerance',
    `lows_ascending` UInt8 DEFAULT 0 COMMENT 'Strictly higher lows',
    `lows_ascending_tol` UInt8 DEFAULT 0 COMMENT 'Higher lows within tolerance — the measured split discriminant',
    `halving` UInt8 DEFAULT 0 COMMENT 'Newest leg within 0.40-1.60x the previous (Node D "roughly half")',
    `max_contraction_ratio_ok` UInt8 DEFAULT 0 COMMENT 'Every leg <= 0.70x the previous',
    `first_leg_deep_enough` UInt8 DEFAULT 0 COMMENT 'First leg >= 10%',
    `legs_long_enough` UInt8 DEFAULT 0 COMMENT 'Every leg >= 5 sessions',
    `base_long_enough` UInt8 DEFAULT 0 COMMENT 'Base >= 30 sessions',
    `base_qualified` UInt8 DEFAULT 0 COMMENT 'Depth and duration within limits, at least two legs',
    `wide_and_loose` UInt8 DEFAULT 0 COMMENT 'Final contraction > 15% — not a tight pivot',
    `has_shakeout` UInt8 DEFAULT 0 COMMENT 'A leg 1.25x deeper than its predecessor',
    `volume_dryup_compressing` UInt8 DEFAULT 0 COMMENT 'Per-leg volume ratios declining',
    `atr_contracting` UInt8 DEFAULT 0 COMMENT 'Per-leg ATR envelope shrinking (independent of % depth)',
    `breakout` UInt8 DEFAULT 0 COMMENT 'close > pivot_line',
    `breakout_clear` UInt8 DEFAULT 0 COMMENT 'close > pivot_line * 1.005 — clearance, not a hair',
    `breakout_event` UInt8 DEFAULT 0 COMMENT 'The cross itself: close > pivot_line AND prev_close <= pivot_line',
    `breakout_on_volume` UInt8 DEFAULT 0 COMMENT 'breakout with volume >= breakout_volume_mult x avg_vol_50d',
    `pivot_proximity_band` UInt8 DEFAULT 0 COMMENT '2 = within 4% of the pivot, 1 = within 8%, else 0',
    `execution_state` LowCardinality(String) DEFAULT '' COMMENT 'pre_breakout | breakout | early_post_breakout | extended | overextended | damaged | forming | none',
    `lastupdated` DateTime DEFAULT now() COMMENT 'ReplacingMergeTree version column'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker)
SETTINGS index_granularity = 8192
COMMENT 'VCP sequence facts (contractions, pivot line, per-leg volume/ATR) plus parameterised flags; the level proxies on screener_price_tech_daily are unchanged.';

-- Managed transform view for target: screener_vcp_pivot_daily
-- =============================================================================
-- TRANSFORM: materialize screener_vcp_pivot_daily from the L7 px spine
-- =============================================================================
-- Run after L7 screener_*_daily (120-126) on nightly populate.
-- PRODUCTION COST, MEASURED 2026-09-27 (read-only, no rows written): the current unbounded fold does
-- NOT fit. For a single one-week chunk against the prod spine (63.1M rows, 32,881 tickers) the fold must
-- process 30,963,105 bars, and it exceeds the populate's 4 GiB limit in ~5s. The first failure was in
-- ARRAY JOIN'ing arrayEnumerate(b) un-filtered, which materialised every bar of every emitting ticker;
-- restricting that join to the chunk's own bars is a pure optimisation (no semantic change) and is still
-- the right change. But the second measurement still fails, in the aggregation itself
-- (ConvertingAggregatedToChunksWithMergingSource), because groupArray holds every ticker's whole history
-- at once. So T6 is BLOCKED until the fold window is bounded -- a fixed calendar floor, not a per-chunk
-- one, or the same (ticker, date) answers differently depending on the chunk. That is a semantic change
-- and needs re-validation against the reference (the test's oracle must then be sliced to the same floor).
-- Production has partial rows (max date observed 2026-10-21), not verified full coverage; keep the
-- transform on_hold in the schedule until a production-sized run fits and passes its coverage checks.
--   that reference on 7/7 real tickers in sql/admin/vcp_zigzag_fold_check.sql.
-- WHY THE FOLD STARTS AT THE TICKER'S FIRST BAR, NOT THE CHUNK BOUNDARY
--   The ZigZag state machine is path-dependent: it carries a running extreme and a confirmation
--   state. Starting it at a chunk boundary would give the same (ticker, date) different answers
--   depending on which chunk computed it. So the window is the ticker's whole history and the chunk
--   only selects which rows are *emitted*. Cost: the nightly re-reads each ticker's history (~60M
--   rows for the full universe), which ClickHouse handles; correctness first.
--   1,482 fixture rows (2021-01-01..2021-02-28) across all 29 compared columns: contraction_count,
--   contraction_depths, leg_days, leg_depths_len, pivot_line, dist_to_pivot_pct, execution_state,
--   ignored_legs, and every UInt8 flag including the tolerance variants and the breakout family.
--   The 3-bar known-answer reproducer below also matches: three bars (13.65/12.96, 13.44/13.09,
--   13.24/12.59) give ('low', pos 3, 12.59, confirmed bar 3) on both sides.
--   THE LAST BUG, worth recording because it was invisible to four earlier passes: condition 1 tested the
--   *stale* running low (`tupleElement(acc, 6)`) where the reference compares the UPDATED one
--   (`min(plo, low_i)`). Condition 2 already had its inline max; condition 1 never got its inline min —
--   the update-before-test ordering was half-applied. On a wide bar, which sets a new extreme and
--   reverses within the same bar, the low-confirmation therefore failed where the reference's succeeded,
--   and the bar fell through to the high-confirmation and confirmed a high at itself. That single
--   omission produced every symptom chased across four passes: the 12% leg-set divergence, the NVDA
--   first-pivot mismatch, and the "identical expressions decide differently inside and outside a lambda"
--   paradox (they did not — the fold's expression was not the one tested outside it).
--   LANDED AS A TEST: tests/vera/test_131_vcp_pivot_daily.py — the whole-window comparison against
--   scripts/vcp_zigzag.py plus the 3-bar known-answer case. Both pass (2 passed).
--   STILL OUTSTANDING before this table can be trusted in production:
--     T3/T4  wire into populate and rehearse via vera-populate on the test instance (26.5.7.64 vs prod
--            26.6.1.121 — re-verified there, not assumed portable)
--     T6     prod backfill (bounded window first), T7 smoke kit with invariants, T8 lineage,
--            T9 contract note, T10 close. Production rows remain partial; max observed date was 2026-10-21.
DROP VIEW IF EXISTS xform_screener_vcp_pivot_daily;

CREATE VIEW IF NOT EXISTS xform_screener_vcp_pivot_daily (
    ticker,
    date,
    zigzag_threshold_pct,
    contraction_count,
    contraction_depths,
    leg_depths,
    leg_days,
    leg_highs,
    ignored_legs,
    contraction_depth_last,
    contraction_depth_prev,
    contraction_ratio,
    first_leg_depth,
    base_high,
    base_depth,
    days_in_base,
    last_pivot_low,
    pivot_line,
    pivot_line_date,
    pivot_confirm_date,
    days_since_pivot,
    dist_to_pivot_pct,
    leg_volume_ratios,
    volume_dryup_ratio,
    breakout_volume_ratio,
    leg_atr_ratios,
    depths_descending,
    depths_descending_tol,
    highs_descending,
    highs_descending_tol,
    lows_ascending,
    lows_ascending_tol,
    halving,
    max_contraction_ratio_ok,
    first_leg_deep_enough,
    legs_long_enough,
    base_long_enough,
    base_qualified,
    wide_and_loose,
    has_shakeout,
    volume_dryup_compressing,
    atr_contracting,
    breakout,
    breakout_clear,
    breakout_event,
    breakout_on_volume,
    pivot_proximity_band,
    execution_state
)
COMMENT '{"order":131,"target":"screener_vcp_pivot_daily","sources":["screener_price_tech_daily"],"chunk_size":"1w","max_memory_usage":6500000000,"max_memory_usage_for_user":7000000000,"on_hold":true}'
AS
WITH
    -- Parameters of the shipped reference defaults. Kept as literals rather than hidden constants so
    -- the mapping to VcpConfig is auditable in one glance.
    0.05  AS thr_pct,
    0.015 AS level_tolerance,
    0.70  AS max_contraction_ratio,
    0.10  AS first_leg_min_depth,
    5     AS min_contraction_days,
    30    AS base_duration_min,
    0.15  AS wide_and_loose_depth,
    0.005 AS breakout_clearance,
    0.04  AS pre_breakout_pct,
    0.05  AS extended_pct,
    0.50  AS overextended_sma200_pct,
    1.40  AS breakout_volume_mult,
    0.35  AS max_base_depth,
    520   AS max_base_bars,
    50    AS volume_baseline_bars,
    40    AS halving_lo,
    160   AS halving_hi,
    125   AS shakeout_factor_pct,
    4     AS max_contractions,
    780   AS trail_bars,

    -- Rows this chunk must publish.
    emit AS
    (
        SELECT ticker, date
        FROM screener_price_tech_daily FINAL
        WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String})
    ),

    -- Every bar of every emitting ticker, ascending. `arraySort` is required: groupArray preserves
    -- scan order, which is not date order.
    bars AS
    (
        SELECT
            ticker,
            arraySort(
                x -> tupleElement(x, 1),
                groupArray(
                    tuple(
                        date,
                        toFloat64(assumeNotNull(high)),
                        toFloat64(assumeNotNull(low)),
                        toFloat64(assumeNotNull(close)),
                        toFloat64(assumeNotNull(volume)),
                        toFloat64(assumeNotNull(avg_vol_50d)),
                        toFloat64(assumeNotNull(atr_14)),
                        toFloat64(assumeNotNull(sma200d))
                    )
                )
            ) AS b
        FROM screener_price_tech_daily FINAL
        WHERE ticker IN (SELECT ticker FROM emit)
          -- The fold runs per emitted row over a trailing `trail_bars` window (below), so the bar
          -- array must reach trail_bars sessions back — ~1150 days — before the chunk. Bounded by
          -- the emit set, not the whole universe, so memory stays proportional to emitted tickers.
          --
          -- Contract, stated plainly: the fold origin is (emitted row - 780 bars), i.e. a trailing
          -- per-row window — deterministic under ANY chunk boundary: two populate runs that split
          -- the same dates differently emit byte-identical rows, because each emitted row's fold
          -- sees exactly the same input bars. 780 = 1.5× max_base_bars, so a maximum-length base
          -- still gets ~260 bars of fold warmup before its first leg.
          AND date >= toDate({chunk_start_date:String}) - INTERVAL 1150 DAY
          -- Upper bound too: without it an EARLY chunk reads from its own lookback all the way to
          -- the present. The 1997 chunk asked for 1997-04-15..2026-09-23, ~62M bars across 8,468
          -- tickers, and blew the memory limit -- the first chunk of the full-history backfill.
          -- Bounding at the chunk end is also more correct: a point-in-time fold must never read
          -- past the rows it is emitting.
          AND date <= toDate({chunk_end_date:String})
        GROUP BY ticker
    ),

    -- Per-ticker bar/volume/ATR arrays. The zigzag fold itself runs per emitted row over the
    -- trailing `trail_bars` window (in `exploded` below), which is what makes the transform
    -- chunk-invariant: every emitted date's pivot history is computed from exactly the same
    -- trailing bars regardless of where the populate chunk began.
    folded AS
    (
        SELECT
            ticker,
            b,
            -- Per-bar volume and ATR, built once per ticker. The derivation below slices these per
            -- leg; building them inline there copied the whole bar array for every leg of every
            -- emitted row, which is what exhausted memory on production data (7.85 GiB for one week).
            arrayMap(v -> tupleElement(v, 5), b) AS vols,
            arrayMap(v -> tupleElement(v, 7), b) AS atrs
        FROM bars
    ),

    -- One row per (ticker, bar): the derivation runs per emitted bar, over the pivots *confirmed by
    -- then*, which is exactly the reference's point-in-time contract.
    exploded AS
    (
        SELECT
            ticker,
            b,
            vols,
            atrs,
            pos,
            greatest(1, toInt64(pos) - trail_bars + 1) AS wstart,
            tupleElement(b[pos], 1) AS date,
            tupleElement(b[pos], 2) AS high,
            tupleElement(b[pos], 3) AS low,
            tupleElement(b[pos], 4) AS close,
            tupleElement(b[pos], 5) AS volume,
            tupleElement(b[pos], 6) AS avg_vol_50d,
            tupleElement(b[pos], 7) AS atr_14,
            tupleElement(b[pos], 8) AS sma200d,
            if(pos > 1, tupleElement(b[pos - 1], 4), tupleElement(b[pos], 4)) AS prev_close,
            -- Trailing-window fold: identical accumulator and transitions to
            -- sql/admin/vcp_zigzag_fold_check.sql, but seeded from b[wstart] and iterated to pos —
            -- the pivots it emits are already confirmed-by-pos, so no further pos filter is needed.
            tupleElement(
                arrayFold(
                    (acc, i) -> multiIf(
                        tupleElement(acc, 1) = 0,
                          multiIf(
                            tupleElement(b[i], 2) >= if(tupleElement(b[i], 3) < tupleElement(acc, 6), tupleElement(b[i], 3), tupleElement(acc, 6)) * (1 + thr_pct),
                              (toInt8(1), toUInt32(i), tupleElement(b[i], 2),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), tupleElement(b[i], 2), tupleElement(acc, 4)),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), toUInt32(i), tupleElement(acc, 5)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), tupleElement(b[i], 3), tupleElement(acc, 6)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), toUInt32(i), tupleElement(acc, 7)),
                               arrayPushBack(tupleElement(acc, 8),
                                 tuple(CAST('low' AS String),
                                       if(tupleElement(b[i], 3) < tupleElement(acc, 6), toUInt32(i), tupleElement(acc, 7)),
                                       if(tupleElement(b[i], 3) < tupleElement(acc, 6), tupleElement(b[i], 3), tupleElement(acc, 6)),
                                       toUInt32(i)))),
                            tupleElement(b[i], 3) <= if(tupleElement(b[i], 2) > tupleElement(acc, 4), tupleElement(b[i], 2), tupleElement(acc, 4)) * (1 - thr_pct),
                              (toInt8(-1), toUInt32(i), tupleElement(b[i], 3),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), tupleElement(b[i], 2), tupleElement(acc, 4)),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), toUInt32(i), tupleElement(acc, 5)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), tupleElement(b[i], 3), tupleElement(acc, 6)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), toUInt32(i), tupleElement(acc, 7)),
                               arrayPushBack(tupleElement(acc, 8),
                                 tuple(CAST('high' AS String),
                                       if(tupleElement(b[i], 2) > tupleElement(acc, 4), toUInt32(i), tupleElement(acc, 5)),
                                       if(tupleElement(b[i], 2) > tupleElement(acc, 4), tupleElement(b[i], 2), tupleElement(acc, 4)),
                                       toUInt32(i)))),
                              (toInt8(0), tupleElement(acc, 2), tupleElement(acc, 3),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), tupleElement(b[i], 2), tupleElement(acc, 4)),
                               if(tupleElement(b[i], 2) > tupleElement(acc, 4), toUInt32(i), tupleElement(acc, 5)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), tupleElement(b[i], 3), tupleElement(acc, 6)),
                               if(tupleElement(b[i], 3) < tupleElement(acc, 6), toUInt32(i), tupleElement(acc, 7)),
                               tupleElement(acc, 8))
                          ),
                        tupleElement(acc, 1) = 1,
                          if(tupleElement(b[i], 2) > tupleElement(acc, 3),
                             (toInt8(1), toUInt32(i), tupleElement(b[i], 2),
                              tupleElement(acc, 4), tupleElement(acc, 5), tupleElement(acc, 6), tupleElement(acc, 7), tupleElement(acc, 8)),
                             if(tupleElement(b[i], 3) <= tupleElement(acc, 3) * (1 - thr_pct),
                                (toInt8(-1), toUInt32(i), tupleElement(b[i], 3),
                                 tupleElement(acc, 4), tupleElement(acc, 5), tupleElement(acc, 6), tupleElement(acc, 7),
                                 arrayPushBack(tupleElement(acc, 8),
                                   tuple(CAST('high' AS String), tupleElement(acc, 2), tupleElement(acc, 3), toUInt32(i)))),
                                acc)),
                          if(tupleElement(b[i], 3) < tupleElement(acc, 3),
                             (toInt8(-1), toUInt32(i), tupleElement(b[i], 3),
                              tupleElement(acc, 4), tupleElement(acc, 5), tupleElement(acc, 6), tupleElement(acc, 7), tupleElement(acc, 8)),
                             if(tupleElement(b[i], 2) >= tupleElement(acc, 3) * (1 + thr_pct),
                                (toInt8(1), toUInt32(i), tupleElement(b[i], 2),
                                 tupleElement(acc, 4), tupleElement(acc, 5), tupleElement(acc, 6), tupleElement(acc, 7),
                                 arrayPushBack(tupleElement(acc, 8),
                                   tuple(CAST('low' AS String), tupleElement(acc, 2), tupleElement(acc, 3), toUInt32(i)))),
                                acc))
                    ),
                    -- Iterate from the SECOND bar, exactly as the reference does: its loop is
                    -- `for i in range(1, len(...))` over 0-based bars, with phi/plo seeded from bar 0.
                    -- Folding over arrayEnumerate(b) starts one bar earlier instead, which lets the
                    -- opening bar confirm a pivot at itself (^VIX 2021-01-04: the SQL reported confirm
                    -- at bar 1, the reference at bar 2) and shifts the sequence after it.
                    -- Iterate from the SECOND bar of the trailing window, exactly as the
                    -- reference does over 0-based bars: folding from the first index would let
                    -- the opening bar confirm a pivot at itself (the divergence T5 catches).
                    arraySlice(arrayEnumerate(b), toUInt64(wstart + 1), toUInt64(pos - wstart)),
                    -- Seeded with the WINDOW's first bar high/low (phi = highs[wstart],
                    -- plo = lows[wstart]) — positions stay absolute indices into `b`.
                    (toInt8(0), toUInt32(wstart), toFloat64(tupleElement(b[wstart], 2)),
                     toFloat64(tupleElement(b[wstart], 2)), toUInt32(wstart),
                     toFloat64(tupleElement(b[wstart], 3)), toUInt32(wstart),
                     CAST([] AS Array(Tuple(String, UInt32, Float64, UInt32))))
                ),
                8
            ) AS pv
        FROM folded
        -- Only the chunk's own bars are exploded. The fold still processes the trailing window per
        -- emitted bar (path-dependent), but exploding all bars materialised ~31M rows for a
        -- one-week chunk. Pure optimisation: identical emitted rows, far fewer of them.
        ARRAY JOIN arrayFilter(
            i -> tupleElement(b[i], 1) >= toDate({chunk_start_date:String})
                 AND tupleElement(b[i], 1) <= toDate({chunk_end_date:String}),
            arrayEnumerate(b)
        ) AS pos
    ),

    -- High→low leg starts. The `if` guards the neighbour lookup: ClickHouse does not guarantee
    -- short-circuit evaluation, so an unguarded pivots[i+1] would be an out-of-bounds read.
    legged AS
    (
        SELECT
            *,
            arrayFilter(
                i -> if(i < length(pv),
                        tupleElement(pv[i], 1) = 'high' AND tupleElement(pv[i + 1], 1) = 'low',
                        toUInt8(0)),
                arrayEnumerate(pv)
            ) AS leg_starts
        FROM exploded
    ),

    -- Every completed leg as (depth, high_price, low_price, high_pos, low_pos).
    legs AS
    (
        SELECT
            *,
            arrayMap(
                i -> tuple(
                    (tupleElement(pv[i], 3) - tupleElement(pv[i + 1], 3)) / tupleElement(pv[i], 3),
                    tupleElement(pv[i], 3),
                    tupleElement(pv[i + 1], 3),
                    tupleElement(pv[i], 2),
                    tupleElement(pv[i + 1], 2)
                ),
                leg_starts
            ) AS all_legs
        FROM legged
    ),

    -- The counted window: the newest `max_contractions` legs (Node D's 2-4). No noise floor in v1
    -- (VcpConfig.min_leg_depth defaults to 0), so counted == all_legs.
    counted AS
    (
        SELECT
            *,
            arraySlice(all_legs, -1 * max_contractions) AS c_legs,
            arrayMap(x -> tupleElement(x, 1), arraySlice(all_legs, -1 * max_contractions)) AS depths
        FROM legs
    ),

    -- Last confirmed swing high = the pivot line (the level to break).
    pivot_line AS
    (
        SELECT
            *,
            arraySlice(arrayFilter(p -> tupleElement(p, 1) = 'high', pv), -1) AS ph
        FROM counted
    ),

    derived AS
    (
        SELECT
            ticker,
            date,
            b,
            pos,
            close,
            prev_close,
            volume,
            avg_vol_50d,
            sma200d,
            pv,
            all_legs,
            c_legs,
            depths,
            length(depths) AS n,
            -- Gated on n >= 1 for the same reason the reference returns early when it has no completed
            -- leg: without a contraction there is no base, so there is no meaningful pivot line. Left
            -- ungated, the SQL publishes a level the reference reports as None (and every dependent
            -- column — distance, proximity band, breakout flags, execution state — diverges with it).
            if(n >= 1 AND length(ph) > 0, tupleElement(ph[1], 3), NULL) AS piv_price,
            if(n >= 1 AND length(ph) > 0, tupleElement(ph[1], 2), NULL) AS piv_pos,
            if(n >= 1 AND length(ph) > 0, tupleElement(ph[1], 4), NULL) AS piv_confirm,
            -- per-leg volume ratios: leg mean over the 50-bar baseline at the leg's start.
            -- Plain Array(Nullable(Float64)) — not an array of tuples: the flags index it directly.
            arrayMap(
                l -> arrayAvg(arraySlice(vols,
                                         toUInt32(tupleElement(l, 4)),
                                         toUInt32(tupleElement(l, 5) - tupleElement(l, 4) + 1)))
                     / nullIf(arrayAvg(arraySlice(vols,
                                         toUInt32(greatest(1, toInt32(tupleElement(l, 4)) - volume_baseline_bars)),
                                         toUInt32(tupleElement(l, 4) - greatest(1, toInt32(tupleElement(l, 4)) - volume_baseline_bars) + 1))), 0),
                c_legs
            ) AS vol_ratios,
            -- per-leg ATR envelope ratios, same shape
            arrayMap(
                l -> arrayAvg(arraySlice(atrs,
                                         toUInt32(tupleElement(l, 4)),
                                         toUInt32(tupleElement(l, 5) - tupleElement(l, 4) + 1)))
                     / nullIf(arrayAvg(arraySlice(atrs,
                                         toUInt32(greatest(1, toInt32(tupleElement(l, 4)) - volume_baseline_bars)),
                                         toUInt32(tupleElement(l, 4) - greatest(1, toInt32(tupleElement(l, 4)) - volume_baseline_bars) + 1))), 0),
                c_legs
            ) AS atr_ratios
        FROM pivot_line
    ),

    flags AS
    (
        SELECT
            *,
            -- shape relations, strict and LMW-tolerance variants
            -- Every relational flag is guarded on arity, because `arrayAll` over an empty range is
            -- vacuously TRUE while the reference fails CLOSED (its early return leaves the defaults,
            -- all False). Without the guard, 0- and 1-leg rows claim properties they cannot have.
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 1) <= tupleElement(c_legs[i], 1),
                     range(1, n))) AS depths_descending,
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 1) <= tupleElement(c_legs[i], 1) * (1 + level_tolerance),
                     range(1, n))) AS depths_descending_tol,
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 2) < tupleElement(c_legs[i], 2),
                     range(1, n))) AS highs_descending,
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 2) <= tupleElement(c_legs[i], 2) * (1 + level_tolerance),
                     range(1, n))) AS highs_descending_tol,
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 3) > tupleElement(c_legs[i], 3),
                     range(1, n))) AS lows_ascending,
            toUInt8(n >= 1 AND arrayAll(i -> tupleElement(c_legs[i + 1], 3) >= tupleElement(c_legs[i], 3) * (1 - level_tolerance),
                     range(1, n))) AS lows_ascending_tol,
            toUInt8(n >= 2 AND arrayAll(i -> tupleElement(c_legs[i + 1], 1) <= tupleElement(c_legs[i], 1) * max_contraction_ratio,
                     range(1, n))) AS max_contraction_ratio_ok,
            toUInt8(n >= 2 AND arrayAll(i -> tupleElement(c_legs[i + 1], 1) <= tupleElement(c_legs[i], 1) * shakeout_factor_pct / 100,
                     range(1, n))) AS no_leg_deeper_than_prev_x,
            if(n >= 2,
               tupleElement(c_legs[n], 1) / nullIf(tupleElement(c_legs[n - 1], 1), 0),
               NULL) AS ratio,
            if(n >= 1, tupleElement(c_legs[1], 1), NULL) AS first_depth,
            if(n >= 1, tupleElement(c_legs[n], 1), NULL) AS last_depth,
            if(n >= 2, tupleElement(c_legs[n - 1], 1), NULL) AS prev_depth,
            if(n >= 1, tupleElement(c_legs[1], 2), NULL) AS base_high,
            if(n >= 1, tupleElement(c_legs[n], 3), NULL) AS last_low,
            if(n >= 1, pos - tupleElement(c_legs[1], 4), 0) AS days_in_base,
            arrayMap(x -> toUInt16(tupleElement(x, 5) - tupleElement(x, 4)), c_legs) AS leg_day_counts,
            arrayMap(x -> tupleElement(x, 2), c_legs) AS leg_high_prices,
            toUInt16(0) AS ignored_legs,   -- v1: no noise floor configured, so nothing is ignored
            -- volume / ATR contraction sequences: same arity guard, and the reference requires
            -- len(ratios) >= 2 before it will call either sequence contracting.
            toUInt8(length(vol_ratios) >= 2 AND arrayAll(i -> ifNull(vol_ratios[i + 1], 1e18) < ifNull(vol_ratios[i], -1e18),
                     range(1, length(vol_ratios)))) AS volume_dryup_compressing,
            toUInt8(length(atr_ratios) >= 2 AND arrayAll(i -> ifNull(atr_ratios[i + 1], 1e18) < ifNull(atr_ratios[i], -1e18),
                     range(1, length(atr_ratios)))) AS atr_contracting
        FROM derived
    )

SELECT
    ticker AS ticker,
    date AS date,
    thr_pct AS zigzag_threshold_pct,
    toUInt8(n) AS contraction_count,
    arrayMap(x -> toFloat32(x), depths) AS contraction_depths,
    arrayMap(x -> toFloat32(tupleElement(x, 1)), all_legs) AS leg_depths,   -- every leg, incl. any beyond the counted window
    arrayMap(x -> toFloat32(x), leg_day_counts) AS leg_days,
    arrayMap(x -> toFloat32(x), leg_high_prices) AS leg_highs,
    toUInt8(ignored_legs) AS ignored_legs,
    if(last_depth IS NULL, NULL, toFloat32(last_depth)) AS contraction_depth_last,
    if(prev_depth IS NULL, NULL, toFloat32(prev_depth)) AS contraction_depth_prev,
    if(ratio IS NULL, NULL, toFloat32(ratio)) AS contraction_ratio,
    if(first_depth IS NULL, NULL, toFloat32(first_depth)) AS first_leg_depth,
    if(base_high IS NULL, NULL, toFloat32(base_high)) AS base_high,
    if(last_low IS NULL, NULL, toFloat32((base_high - last_low) / base_high)) AS base_depth,
    toUInt16(days_in_base) AS days_in_base,
    if(last_low IS NULL, NULL, toFloat32(last_low)) AS last_pivot_low,
    if(piv_price IS NULL, NULL, toFloat32(piv_price)) AS pivot_line,
    if(piv_pos IS NULL, NULL, tupleElement(b[piv_pos], 1)) AS pivot_line_date,
    if(piv_confirm IS NULL, NULL, tupleElement(b[piv_confirm], 1)) AS pivot_confirm_date,
    if(piv_pos IS NULL, NULL, toUInt16(pos - piv_pos)) AS days_since_pivot,
    if(piv_price IS NULL, NULL, toFloat32(close / piv_price - 1)) AS dist_to_pivot_pct,
    arrayMap(x -> toFloat32(assumeNotNull(x)), vol_ratios) AS leg_volume_ratios,
    if(length(vol_ratios) = 0, NULL, toFloat32(assumeNotNull(vol_ratios[length(vol_ratios)]))) AS volume_dryup_ratio,
    if(avg_vol_50d > 0, toFloat32(volume / avg_vol_50d), NULL) AS breakout_volume_ratio,
    arrayMap(x -> toFloat32(assumeNotNull(x)), atr_ratios) AS leg_atr_ratios,
    toUInt8(depths_descending) AS depths_descending,
    toUInt8(depths_descending_tol) AS depths_descending_tol,
    toUInt8(highs_descending) AS highs_descending,
    toUInt8(highs_descending_tol) AS highs_descending_tol,
    toUInt8(lows_ascending) AS lows_ascending,
    toUInt8(lows_ascending_tol) AS lows_ascending_tol,
    toUInt8(if(n >= 2, ratio >= halving_lo / 100 AND ratio <= halving_hi / 100, 0)) AS halving,
    toUInt8(n >= 2 AND max_contraction_ratio_ok) AS max_contraction_ratio_ok,
    toUInt8(first_depth >= first_leg_min_depth) AS first_leg_deep_enough,
    toUInt8(length(leg_day_counts) > 0 AND arrayAll(d -> d >= min_contraction_days, leg_day_counts)) AS legs_long_enough,
    toUInt8(days_in_base >= base_duration_min) AS base_long_enough,
    toUInt8(n >= 2 AND (base_high - last_low) / base_high <= max_base_depth AND days_in_base <= max_base_bars) AS base_qualified,
    toUInt8(last_depth > wide_and_loose_depth) AS wide_and_loose,
    toUInt8(n >= 2 AND NOT no_leg_deeper_than_prev_x) AS has_shakeout,
    toUInt8(volume_dryup_compressing) AS volume_dryup_compressing,
    toUInt8(atr_contracting) AS atr_contracting,
    toUInt8(piv_price IS NOT NULL AND close > piv_price) AS breakout,
    toUInt8(piv_price IS NOT NULL AND close > piv_price * (1 + breakout_clearance)) AS breakout_clear,
    toUInt8(piv_price IS NOT NULL AND close > piv_price AND prev_close <= piv_price) AS breakout_event,
    toUInt8(piv_price IS NOT NULL AND close > piv_price
            AND avg_vol_50d > 0 AND volume / avg_vol_50d >= breakout_volume_mult) AS breakout_on_volume,
    toUInt8(if(piv_price IS NULL, 0,
               multiIf(abs(close / piv_price - 1) <= 0.04, 2,
                       abs(close / piv_price - 1) <= 0.08, 1, 0))) AS pivot_proximity_band,
    -- Lifecycle state. Order matters: damage and blow-off dominate, because a damaged base or a name
    -- 50% past its 200-day average is not a buy point at any price. has_shakeout is reported as a
    -- flag but does NOT by itself damage the base (decision dec-f8739dd6e92867ec).
    multiIf(
        n = 0 OR piv_price IS NULL, 'none',
        last_depth > wide_and_loose_depth, 'damaged',
        NOT (n >= 2 AND (base_high - last_low) / base_high <= max_base_depth AND days_in_base <= max_base_bars), 'forming',
        sma200d > 0 AND close > sma200d * (1 + overextended_sma200_pct), 'overextended',
        close > piv_price AND prev_close <= piv_price, 'breakout',
        close > piv_price, if(close / piv_price - 1 > extended_pct, 'extended', 'early_post_breakout'),
        close / piv_price - 1 >= -pre_breakout_pct, 'pre_breakout',
        'forming'
    ) AS execution_state
FROM flags
WHERE date BETWEEN toDate({chunk_start_date:String}) AND toDate({chunk_end_date:String});
