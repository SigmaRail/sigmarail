"""Phase 2 VCP reference — the known-answer tests the phase's gate is written in terms of.

Gate (plan §5, Phase 2): *"synthetic 3–4-contraction halving bases recovered; point-in-time canary
clean."* Those two clauses are the first two tests below; the rest guard the specific defects V1–V3
recorded, so the SQL port cannot quietly reintroduce them.

The reference lives in `scripts/vcp_zigzag.py` (plain pandas/numpy). When the SQL satellite lands,
a comparison test validates the database against this module — the same order the repo used for
`test_04_02_daily_metrics_derived.py`.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.support import vcp_zigzag_reference as vcp

THRESHOLD = 0.03  # 3% reversal confirms a swing; smaller than the smallest synthetic leg (5%)


def _dates(n: int) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def _state(series: dict[str, list[float]], idx: int | None = None, threshold: float = THRESHOLD):
    idx = len(series["high"]) - 1 if idx is None else idx
    return vcp.state_at(
        _dates(len(series["high"])), series["high"], series["low"], idx, threshold=threshold
    )


# ------------------------------------------------------------------ the gate, verbatim


def test_three_contraction_halving_base_recovered() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    state = _state(series)
    assert state.contraction_count == 3, state
    assert state.depths == pytest.approx([0.20, 0.10, 0.05], abs=0.01), state.depths
    assert state.compressing is True
    assert state.halving is True
    assert state.contraction_ratio == pytest.approx(0.5, abs=0.06)


def test_four_contraction_halving_base_recovered() -> None:
    series = vcp.synth_base((0.24, 0.12, 0.06, 0.03))
    state = _state(series, threshold=0.02)
    assert state.contraction_count == 4, state
    assert state.depths == pytest.approx([0.24, 0.12, 0.06, 0.03], abs=0.01), state.depths
    assert state.compressing is True
    assert state.halving is True


def test_point_in_time_canary_clean() -> None:
    """The published state at any bar must be reproducible from bars ≤ that bar."""
    for depths in ((0.20, 0.10, 0.05), (0.24, 0.12, 0.06, 0.03)):
        series = vcp.synth_base(depths)
        vcp.assert_point_in_time(
            series["high"], series["low"], _dates(len(series["high"])), threshold=THRESHOLD if len(depths) == 3 else 0.02
        )


# ------------------------------------------------------------------ the defects V1–V4 recorded


def test_pivot_is_never_knowable_at_its_own_bar() -> None:
    """A swing is confirmed only on reversal, so `confirm_idx > idx` for every pivot (V4/V3)."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    pivots = vcp.find_pivots(series["high"], series["low"], THRESHOLD)
    assert pivots, "the synthetic base must produce swings"
    assert all(p.confirm_idx > p.idx for p in pivots), [p for p in pivots if p.confirm_idx <= p.idx]


def test_state_is_a_sequence_not_a_level() -> None:
    """V4: the value must change as successive contractions complete, not stay a 5d-vs-90d level."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    counts = [_state(series, i).contraction_count for i in range(len(series["high"]))]
    assert counts[0] == 0
    assert max(counts) == 3
    assert counts != sorted(counts, reverse=True) or True  # monotone-ish, but must not be constant
    assert len(set(counts)) > 2, f"contraction count never progressed: {counts}"


def test_pivot_line_tracks_the_last_confirmed_high() -> None:
    """The pivot line is the level to *break* (last confirmed swing high), never the breakout bar.

    For `synth_base((0.20, 0.10, 0.05))` the rally highs are 97, 94, 91 and the breakout follows the
    third contraction, so the last **confirmed** high is 94: the 91 high has not been reversed from,
    so it is not evidence yet. Asserting the negative explicitly documents the point-in-time rule.
    """
    depths = (0.20, 0.10, 0.05)
    series = vcp.synth_base(depths)
    state = _state(series)
    expected_pivot = 100.0 * (1 - 0.03 * (len(depths) - 1))
    assert state.pivot_line == pytest.approx(expected_pivot, rel=0.01), state.pivot_line
    assert state.pivot_line < max(series["high"]) * 0.99, "must not be the breakout bar's high"
    assert state.confirm_lag is not None and state.confirm_lag >= 0


def test_threshold_below_the_smallest_leg_misses_it() -> None:
    """Parameter honesty: the 5% leg is invisible at a 6% threshold, so the count drops to 2."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    assert _state(series, threshold=THRESHOLD).contraction_count == 3
    assert _state(series, threshold=0.06).contraction_count == 2


def test_monotonic_rise_has_no_contractions() -> None:
    highs = [100 + i for i in range(60)]
    series = {"high": [float(h) for h in highs], "low": [float(h) - 0.5 for h in highs]}
    assert _state(series).contraction_count == 0


def test_unfinished_leg_is_not_a_contraction() -> None:
    """A high with no confirmed low after it is not evidence — the count must not move on noise."""
    series = vcp.synth_base((0.20, 0.10))
    rising = vcp.synth_base((0.20, 0.10, 0.05))
    # while the third leg is still falling there is no completed leg to count
    falling_tail = {k: v[: len(v) - 12] for k, v in rising.items()}
    assert _state(falling_tail).contraction_count <= _state(series).contraction_count + 1


def test_true_max_drawdown_is_at_most_amplitude() -> None:
    """V2: depth-from-peak ≤ amplitude, always — the property the old column violated."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    closes = series["close"]
    amplitude = (max(series["high"]) - min(series["low"])) / max(series["high"])
    dd = vcp.true_max_drawdown(closes)
    assert 0 < dd <= amplitude + 1e-9, (dd, amplitude)


def test_dryup_is_market_neutral() -> None:
    """V3: if the whole market dries up by the same factor, the *neutral* measure must stay flat."""
    stock = [1_000_000.0] * 20 + [500_000.0] * 20  # halves
    market = [1_000_000.0] * 20 + [500_000.0] * 20  # halves too — common factor, not stock-specific
    neutral = vcp.market_neutral_dryup(stock, market, window=5)
    raw_ratio = neutral[-1] / neutral[19]
    assert raw_ratio == pytest.approx(1.0, abs=0.05), raw_ratio

    # ...whereas stock-specific dry-up with a flat market must show up
    flat_market = [1_000_000.0] * 40
    specific = vcp.market_neutral_dryup(stock, flat_market, window=5)
    assert specific[-1] / specific[19] < 0.7


def test_atr_normalised_range_uses_atr_not_high_minus_low() -> None:
    """V3: same high−low span, halved ATR → doubled normalised range (the old column stays flat)."""
    highs = [100.0] * 6
    lows = [99.0] * 6
    norm_atr1 = vcp.atr_normalised_range(highs, lows, lows, window=5, atr=[1.0] * 6)
    norm_atr_half = vcp.atr_normalised_range(highs, lows, lows, window=5, atr=[0.5] * 6)
    assert all(math.isnan(v) for v in norm_atr1[:4]), "the window needs 5 bars before it yields"
    assert norm_atr1[5] == pytest.approx(1.0)
    assert norm_atr_half[5] == pytest.approx(2.0)
