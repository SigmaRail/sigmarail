"""Phase 2 relational tolerances, practitioner gates and the execution lifecycle.

The first test is the payoff from reading Lo-Mamaysky-Wang (2000): their patterns are defined as
extrema *plus tolerance relations* — head-and-shoulders requires "E1 and E5 within 1.5 percent of
their average". Applying that to our relational flags is what finally separates a split pullback from
a legitimate contraction, which two earlier attempts (a noise floor, a merge on recovery fraction)
failed to do.

Every threshold here is a parameter on `VcpConfig`, each sourced in
`docs/ai/session-notes/research/2026-09-27-vcp-external-algorithm-review.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import vcp_zigzag_reference as vcp

THRESHOLD = 0.05


def _state(series, *, idx=None, thr=THRESHOLD, **kwargs):
    n = len(series["high"])
    idx = n - 1 if idx is None else idx
    return vcp.state_at(
        list(range(n)), series["high"], series["low"], idx,
        threshold=thr, closes=series["close"], **kwargs,
    )


# ------------------------------------------------------------ the payoff: tolerance


def test_tolerance_separates_a_split_from_a_legitimate_base() -> None:
    """Measured: a split violates higher-lows by ~11%, a real contraction wobbles by <0.5%."""
    split = _state(vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.06))
    legit = _state(vcp.synth_base((0.24, 0.12, 0.06, 0.03)), thr=0.02)

    # a split breaks the relation far beyond any sane tolerance
    assert split.lows_ascending is False
    assert split.lows_ascending_tol is False

    # a legitimate contraction wobbles sub-percent: strict rejects it, the tolerance accepts it
    assert legit.lows_ascending is False, "strict comparison fails on a sub-percent wobble"
    assert legit.lows_ascending_tol is True, "the same wobble passes within 1.5%"
    assert legit.depths_descending is True


def test_tolerance_is_a_parameter_not_a_constant() -> None:
    """Different deltas are a decision, so the knob is visible."""
    legit = vcp.synth_base((0.24, 0.12, 0.06, 0.03))
    tight = vcp.VcpConfig(threshold_pct=0.02, level_tolerance=0.0001)
    assert _state(legit, thr=0.02).lows_ascending_tol is True
    assert _state(legit, thr=0.02, config=tight).lows_ascending_tol is False


# ------------------------------------------------------------ practitioner gates


def test_practitioner_gates_fire_on_the_intended_shapes() -> None:
    base = _state(vcp.synth_base((0.20, 0.10, 0.05)))
    assert base.first_leg_depth == pytest.approx(0.203, abs=0.01)
    assert base.first_leg_deep_enough is True  # 20% >= 10%
    assert base.max_contraction_ratio_ok is True  # ratios 0.51, 0.52 <= 0.70
    assert base.legs_long_enough is True  # 10 days per leg >= 5
    assert base.base_long_enough is True  # ~60 days >= 30
    assert base.wide_and_loose is False  # final leg 5.4% <= 15%

    assert _state(vcp.synth_base((0.06, 0.03))).first_leg_deep_enough is False
    assert _state(vcp.synth_base((0.10, 0.09))).max_contraction_ratio_ok is False, "0.9x > 0.70"
    assert _state(vcp.synth_base((0.20, 0.10, 0.05), bars_per_leg=3)).legs_long_enough is False
    short_base = _state(vcp.synth_base((0.20, 0.10, 0.05), bars_per_leg=3))
    assert short_base.base_long_enough is False, f"only {short_base.days_in_base} days in the base"
    assert _state(vcp.synth_base((0.10, 0.18))).wide_and_loose is True


def test_gates_are_reported_alongside_the_facts() -> None:
    """Facts and judgements stay separable: the depths are published either way."""
    wide = _state(vcp.synth_base((0.10, 0.18)))
    assert wide.depths == pytest.approx([0.10, 0.18], abs=0.01)
    assert wide.wide_and_loose is True


# ------------------------------------------------------------ ATR envelope


def test_atr_envelope_contraction_is_independent_of_percentage_depth() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    decaying = [1.0 - 0.6 * i / (n - 1) for i in range(n)]
    rising = [0.4 + 0.6 * i / (n - 1) for i in range(n)]
    assert _state(series, atr_14=decaying).atr_contracting is True
    assert _state(series, atr_14=rising).atr_contracting is False
    assert _state(series).leg_atr_ratios == [], "absent unless ATR is supplied"
    # the envelope is a second, independent read: same % depths, opposite verdicts
    assert _state(series, atr_14=decaying).depths == _state(series, atr_14=rising).depths


# ------------------------------------------------------------ proximity and breakout


def test_pivot_proximity_bands() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    before = _state(series, idx=n - 1 - 6)  # last bar before the breakout ramp
    assert before.pivot_proximity_band == 2, before.dist_to_pivot_pct
    assert before.breakout is False
    assert _state(series).pivot_proximity_band == 0  # ~12% past the pivot


def test_breakout_cross_event_fires_once_at_the_crossing() -> None:
    """An event (the cross), not a state: `close > pivot AND prev_close <= pivot`."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    events = [i for i in range(n) if _state(series, idx=i).breakout_event]
    assert len(events) == 1, events
    crossing = events[0]
    assert _state(series, idx=crossing).breakout is True
    assert _state(series, idx=crossing - 1).breakout is False
    assert _state(series, idx=crossing).breakout_clear is True


# ------------------------------------------------------------ execution lifecycle


def test_execution_state_lifecycle() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    assert _state(series, idx=n - 1 - 6).execution_state == "pre_breakout"
    crossings = [i for i in range(n) if _state(series, idx=i).breakout_event]
    assert _state(series, idx=crossings[0]).execution_state == "breakout"
    assert _state(series, idx=n - 1).execution_state in ("early_post_breakout", "extended")


def test_execution_state_ranks_damage_and_blowoff_above_actionability() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    assert _state(vcp.synth_base((0.10, 0.18))).execution_state == "damaged"
    assert _state(series, sma200=50.0).execution_state == "overextended"
    flat = {"high": [100.0] * 50, "low": [99.0] * 50, "close": [99.5] * 50}
    assert _state(flat).execution_state == "none"


def test_execution_state_is_a_stage_not_a_verdict() -> None:
    """A damaged base still reports its legs — the state is one column, not a filter."""
    damaged = _state(vcp.synth_base((0.10, 0.18)))
    assert damaged.execution_state == "damaged"
    assert damaged.contraction_count == 2
    assert damaged.pivot_line is not None


# ------------------------------------------------------------ point-in-time


def test_new_flags_are_point_in_time() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.06)
    n = len(series["high"])
    atr = [1.0 - 0.5 * i / (n - 1) for i in range(n)]
    for t in range(n):
        full = vcp.state_at(
            list(range(n)), series["high"], series["low"], t, threshold=THRESHOLD,
            closes=series["close"], atr_14=atr, sma200=100.0,
        )
        trunc = vcp.state_at(
            list(range(t + 1)), series["high"][: t + 1], series["low"][: t + 1], t,
            threshold=THRESHOLD, closes=series["close"][: t + 1], atr_14=atr[: t + 1],
            sma200=100.0,
        )
        assert (
            full.contraction_count, tuple(full.depths), full.pivot_line, full.execution_state,
            full.lows_ascending_tol, full.atr_contracting, full.breakout_event,
            full.pivot_proximity_band,
        ) == (
            trunc.contraction_count, tuple(trunc.depths), trunc.pivot_line, trunc.execution_state,
            trunc.lows_ascending_tol, trunc.atr_contracting, trunc.breakout_event,
            trunc.pivot_proximity_band,
        ), f"look-ahead at bar {t}"
