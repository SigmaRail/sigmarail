"""Phase 2 robustness — what the VCP reference does when the base is *not* clean.

Real bases are messy, so these are the shapes that matter in production: wiggles, rising highs,
shallow final legs, shakeouts, market-wide volume drift. Each one is a regression fixture.

The design rule under test: **facts stay facts, judgements stay flags.** A messy base must degrade
into flags being false plus numbers that show *why* — never into a confidently wrong pivot line,
which is the failure mode measurement found (a too-high threshold silently drops the tightest leg and
moves the breakout level up).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import vcp_zigzag_reference as vcp

THRESHOLD = 0.05


def _state(series, *, threshold: float = THRESHOLD, config=None, **kwargs):
    n = len(series["high"])
    return vcp.state_at(
        list(range(n)), series["high"], series["low"], n - 1,
        threshold=threshold, config=config, **kwargs,
    )


def _declining_volumes(n: int, start: float = 1.0, end: float = 0.4) -> list[float]:
    return [start + (end - start) * i / max(1, n - 1) for i in range(n)]


# ------------------------------------------------------------ wiggles and noise


def test_wiggle_below_threshold_is_invisible() -> None:
    """Noise immunity: a 4% counter-move never becomes a leg at a 5% threshold."""
    clean = _state(vcp.synth_base((0.20, 0.10, 0.05)))
    wiggled = _state(vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.04))
    assert wiggled.contraction_count == clean.contraction_count == 3
    assert wiggled.depths == clean.depths


def test_wiggle_above_threshold_invents_a_leg() -> None:
    """The documented hazard — but note *how*: a mid-leg wiggle **splits** the leg rather than
    adding a shallow one, which is why a noise floor alone cannot repair it (see the next test)."""
    clean = _state(vcp.synth_base((0.20, 0.10, 0.05)))
    state = _state(vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.06))
    assert state.contraction_count == 4, state.depths
    assert state.depths_descending is False, "a phantom leg must not read as compressing"
    assert state.depths[0] < clean.depths[0], "the 20% leg was split into two shallower ones"
    assert state.ignored_legs == 0, "both halves clear an 8% floor — a floor is not the fix here"


def test_no_fixed_threshold_can_fix_a_split_leg() -> None:
    """The measured tension, and the case for volatility scaling.

    A 6% wiggle needs a threshold *above* 6% to disappear, while the 5.4% final contraction needs one
    *below* 5.4% to survive. Both cannot hold, so the sweep never lands on the correct count of 3 — a
    fixed threshold cannot separate noise from the tightest real leg. That is exactly why
    `threshold_atr_k` (per-stock, ATR-scaled) exists, and why a structural leg merge is the next
    mitigation rather than more threshold tuning.
    """
    wiggled = vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.06)
    clean = _state(vcp.synth_base((0.20, 0.10, 0.05)), threshold=0.05)
    clean_shape = (clean.contraction_count, tuple(round(d, 3) for d in clean.depths))
    counts = {t: _state(wiggled, threshold=t).contraction_count for t in (0.05, 0.055, 0.06, 0.062, 0.065, 0.07, 0.08, 0.09)}
    # the tension, measured: below ~6.2% the 20% leg is split into two, at 6.5%+ the tightest real
    # leg disappears. No threshold in between recovers the correct shape.
    assert counts[0.05] == 4, "below the wiggle: the 20% leg is split (depths 10.4 / 16.5)"
    assert counts[0.065] == 2, "above the wiggle: the 5.4% final leg is gone too"
    for t in counts:
        shape = (
            _state(wiggled, threshold=t).contraction_count,
            tuple(round(d, 3) for d in _state(wiggled, threshold=t).depths),
        )
        assert shape != clean_shape, f"threshold {t} unexpectedly recovered {clean_shape}"
    assert clean_shape[0] == 3


def test_noise_floor_ignores_a_genuinely_shallow_leg() -> None:
    """What the floor *is* for: a leg shallower than it is reported but not counted."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    assert _state(series).contraction_count == 3
    config = vcp.VcpConfig(threshold_pct=THRESHOLD, min_leg_depth=0.06)
    state = _state(series, config=config)
    assert state.contraction_count == 2, state.depths
    assert state.ignored_legs == 1
    assert state.depths_descending is True
    assert len(state.leg_depths_all) == 3, "the ignored leg is still reported — just not counted"


def test_atr_scaled_threshold_adapts_to_volatility() -> None:
    """A fixed % treats a quiet name and a volatile one alike; ATR scaling fixes that."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    calm = [0.005] * n
    volatile = [0.03] * n
    fixed = _state(series)
    scaled_calm = _state(series, config=vcp.VcpConfig(threshold_atr_k=2.0), atr_pct=calm)
    scaled_volatile = _state(series, config=vcp.VcpConfig(threshold_atr_k=2.0), atr_pct=volatile)
    assert fixed.contraction_count == 3
    assert scaled_calm.contraction_count == 3, "calm: 2×0.5% < 5%, so the fixed floor governs"
    assert scaled_volatile.contraction_count == 2, "volatile: 2×3% = 6% hides the 5% leg"


# ------------------------------------------------------------ shape


def test_sloppy_but_monotone_base_still_compresses() -> None:
    """0.6× per leg is not textbook halving but is still a VCP — the tolerance is deliberate."""
    state = _state(vcp.synth_base((0.20, 0.13, 0.07)))
    assert state.depths_descending is True
    assert state.halving is True
    assert state.contraction_ratio == pytest.approx(0.55, abs=0.05)


def test_higher_high_is_flagged_separately_from_depths() -> None:
    """Rising highs with shrinking depths is a continuation, not a base — now visible, not silent."""
    state = _state(vcp.synth_base((0.20, 0.10, 0.05), rally_highs=(0.97, 1.03, 0.99)))
    assert state.depths_descending is True
    assert state.highs_descending is False, "the rising high must be reported, not assumed away"


def test_threshold_decides_whether_the_tightest_leg_exists() -> None:
    """The last contraction is the tightest, so the threshold moves the *breakout level*."""
    series = vcp.synth_base((0.20, 0.10, 0.04))
    permissive = _state(series, threshold=0.03)
    strict = _state(series, threshold=THRESHOLD)
    assert permissive.contraction_count == 3
    assert strict.contraction_count == 2
    assert strict.pivot_line > permissive.pivot_line, "dropping the leg raises the pivot line"


def test_shakeout_is_flagged_not_hidden() -> None:
    """A 28% leg mid-base is reported as a shakeout rather than averaged into a clean story."""
    state = _state(vcp.synth_base((0.20, 0.28, 0.05)))
    assert state.has_shakeout is True
    assert state.depths_descending is False
    assert max(state.depths) > 0.25
    assert state.execution_state != "damaged", "a shakeout is flagged, not a damage cause"


def test_base_qualification_rejects_a_deep_base() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    assert _state(series).base_qualified is True
    tight = vcp.VcpConfig(threshold_pct=THRESHOLD, max_base_depth=0.10)
    assert _state(series, config=tight).base_qualified is False


# ------------------------------------------------------------ volume


def test_volume_dryup_is_per_leg_and_declining() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    state = _state(series, volumes=_declining_volumes(n), market_volumes=[1.0] * n)
    assert len(state.leg_volume_ratios) == state.contraction_count
    assert state.leg_volume_ratios == sorted(state.leg_volume_ratios, reverse=True), state.leg_volume_ratios
    assert state.volume_dryup_compressing is True


def test_volume_dryup_is_market_neutral() -> None:
    """A market-wide volume decline must not read as stock-specific dry-up (finding V3)."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    declining = _declining_volumes(n)
    state = _state(series, volumes=declining, market_volumes=list(declining))
    assert all(abs(r - 1.0) < 0.25 for r in state.leg_volume_ratios), state.leg_volume_ratios
    assert state.volume_dryup_compressing is False, "nothing stock-specific happened"


def test_breakout_needs_both_price_and_volume() -> None:
    """Node E: clearing the pivot line on +40% volume. Price alone is not a breakout signal."""
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    avg = [1.0] * n
    on_volume = _state(series, closes=series["close"], volumes=[1.0] * (n - 1) + [1.5], market_volumes=None, avg_vol_50d=avg)
    weak = _state(series, closes=series["close"], volumes=[1.0] * n, market_volumes=None, avg_vol_50d=avg)
    assert on_volume.breakout is True and weak.breakout is True
    assert on_volume.breakout_volume_ratio == pytest.approx(1.5)
    assert on_volume.breakout_on_volume is True
    assert weak.breakout_on_volume is False, "1.0× is below the +40% requirement"


def test_breakout_volume_threshold_is_a_parameter() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05))
    n = len(series["high"])
    strict = vcp.VcpConfig(threshold_pct=THRESHOLD, breakout_volume_mult=1.50)
    state = _state(
        series, volumes=[1.0] * (n - 1) + [1.45], avg_vol_50d=[1.0] * n, config=strict
    )
    assert state.breakout_volume_ratio == pytest.approx(1.45)
    assert state.breakout_on_volume is False, "1.45× fails a 1.50 requirement"


# ------------------------------------------------------------ canary with the new inputs


def test_point_in_time_canary_clean_with_volume_and_atr() -> None:
    series = vcp.synth_base((0.20, 0.10, 0.05), wiggle_at=0, wiggle_pct=0.06)
    n = len(series["high"])
    config = vcp.VcpConfig(threshold_pct=THRESHOLD, min_leg_depth=0.08)
    volumes = _declining_volumes(n)
    for t in range(n):
        full = vcp.state_at(
            list(range(n)), series["high"], series["low"], t, threshold=THRESHOLD, config=config,
            volumes=volumes, market_volumes=[1.0] * n, avg_vol_50d=[1.0] * n, closes=series["close"],
        )
        trunc = vcp.state_at(
            list(range(t + 1)), series["high"][: t + 1], series["low"][: t + 1], t,
            threshold=THRESHOLD, config=config, volumes=volumes[: t + 1],
            market_volumes=[1.0] * (t + 1), avg_vol_50d=[1.0] * (t + 1), closes=series["close"][: t + 1],
        )
        assert (full.contraction_count, tuple(full.depths), full.pivot_line, full.breakout_on_volume) == (
            trunc.contraction_count, tuple(trunc.depths), trunc.pivot_line, trunc.breakout_on_volume
        ), f"look-ahead at bar {t}"
