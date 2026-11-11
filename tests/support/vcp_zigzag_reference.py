"""VCP reference implementation — successive contractions, dry-up, breakout (Phase 2, V1–V4).

This is the *reference*, in plain pandas/numpy: the SQL satellite must reproduce it, and
`tests/vera/test_vcp_zigzag_reference.py` holds the known-answer tests. The house pattern for
metrics work is exactly this order — prototype, then SQL, then a test that validates the database
against the prototype (see `test_04_02_daily_metrics_derived.py`).

Why it exists: the shipped `vcp_*` columns are **per-date level proxies** ("current 5d vs current
90d"). VCP as specified in `docs/plans/Mark Minervini SEPA & VCP Algorithmic Framework Architecture.md`
Node D is a *sequence*: "traces successive local swing highs and swing lows… each pullback
compressing roughly by half", on volume that dries up through the base, with the breakout itself
confirmed by volume (Node E, "+40–50% over the 50-day average"). Nothing in the platform compares
contraction *i+1* to *i* — finding V4 — and that gap is what this module answers.

Design rule: **facts stay facts, judgements stay flags.** Leg depths, highs, the pivot line and its
confirmation are reported as measured; "is this a VCP?" is a separate, parameterised judgement.
Real bases are messy, so messiness must degrade into flags being false plus numbers that show why —
never into a confidently wrong breakout level.

Conventions that matter:

* **Point-in-time.** A swing is only *confirmed* when price reverses by at least the threshold from
  the running extreme, so a pivot is knowable at the bar that reverses, never at its own bar. Every
  published value is reproducible from bars ≤ the row's date; `assert_point_in_time()` enforces this
  by recomputation, not inspection.
* **Thresholds are parameters.** `VcpConfig` carries them, so the tuning is visible and testable
  rather than a magic constant baked into a boolean (finding V3 on `has_vcp_setup`'s 0.40/0.70/0.90
  trio, 48.7% base rate).
* **ATR-scaled pivots.** A fixed 5% reversal treats a quiet name and a volatile one alike, and the
  *last* contraction of a VCP is the tightest — so a fixed threshold silently drops the very leg the
  pattern is named for. `threshold_atr_k` scales the reversal to the stock's own volatility.
* **Noise floor.** A wiggle larger than the threshold inside a leg would otherwise invent a
  contraction and flip `depths_descending` false on a textbook base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

# ---------------------------------------------------------------- config


@dataclass(frozen=True)
class VcpConfig:
    """Every threshold in one place. Defaults reproduce the plain fixed-threshold behaviour."""

    threshold_pct: float = 0.05  # fixed fractional reversal that confirms a swing
    threshold_atr_k: float | None = None  # if set, threshold = max(threshold_pct, k · atr_pct)
    min_leg_depth: float = 0.0  # noise floor: shallower legs are not contractions
    noise_floor_atr_k: float = 0.0  # ...or k · atr_pct, whichever is larger
    max_base_depth: float = 0.35  # base qualification — a 40% slide is not a base
    max_base_bars: int = 520  # base qualification — nor is a two-year drift
    max_contractions: int = 4  # Node D: 2–4, counted newest-last
    halving_lo: float = 0.40  # "roughly half" band
    halving_hi: float = 1.60
    shakeout_factor: float = 1.25  # a leg this much deeper than its predecessor is a shakeout
    breakout_volume_mult: float = 1.40  # Node E: +40% over the 50-day average
    volume_baseline_bars: int = 50

    # --- relational tolerance (Lo-Mamaysky-Wang's pattern formalism: compare levels within a
    # tolerance of their average, not strictly — their published value is 1.5 percent)
    level_tolerance: float = 0.015

    # --- practitioner gates, each sourced in
    # docs/ai/session-notes/research/2026-09-27-vcp-external-algorithm-review.md
    max_contraction_ratio: float = 0.70  # each contraction <= 0.70x the previous (JadeGate)
    first_leg_min_depth: float = 0.10  # the base must begin with a real correction (JadeGate)
    min_contraction_days: int = 5  # legs shorter than this are flickers (JadeGate)
    base_duration_min: int = 30  # minimum days in the base (Substack)
    wide_and_loose_depth: float = 0.15  # a final contraction this deep is not a tight pivot
    breakout_clearance: float = 0.005  # a close a hair above the pivot is not a breakout

    # --- execution lifecycle (JadeGate: the state a strategy actually trades)
    pre_breakout_pct: float = 0.04  # within this far below the pivot = actionable
    extended_pct: float = 0.05  # this far above the pivot = the entry is gone
    overextended_sma200_pct: float = 0.50  # extension past the 200-day MA


# ---------------------------------------------------------------- zigzag


@dataclass(frozen=True)
class Pivot:
    """A confirmed swing extreme. ``confirm_idx`` is when it became knowable, ``idx`` where it is."""

    idx: int
    confirm_idx: int
    kind: str  # "high" | "low"
    price: float

    @property
    def lag(self) -> int:
        return self.confirm_idx - self.idx


def _threshold_at(idx: int, highs: Sequence[float], config: VcpConfig, atr_pct: Sequence[float] | None) -> float:
    """Reversal threshold at the *extreme's* bar — knowable then, so point-in-time safe."""
    thr = config.threshold_pct
    if config.threshold_atr_k and atr_pct is not None:
        value = atr_pct[idx]
        if value is not None and np.isfinite(float(value)):
            thr = max(thr, config.threshold_atr_k * float(value))
    return thr


def find_pivots(
    highs: Sequence[float],
    lows: Sequence[float],
    threshold: float | None = None,
    *,
    config: VcpConfig | None = None,
    atr_pct: Sequence[float] | None = None,
) -> list[Pivot]:
    """ZigZag swings, confirmed on reversal (no look-ahead).

    ``threshold`` is a fractional reversal (0.05 = 5%) and is kept for compatibility; passing
    ``config`` with ``threshold_atr_k`` makes the reversal volatility-scaled per bar.

    Direction is undetermined until the first threshold move, so the opening extreme is confirmed as
    the *opposite* kind — honest rather than assuming the series starts in an uptrend. While
    undetermined the running high and low are tracked **separately**: collapsing them into one
    variable makes a monotonic move self-referential (a running low can never be 5% below itself),
    so nothing confirms and every base reads as empty.
    """
    cfg = config or VcpConfig(threshold_pct=threshold if threshold is not None else VcpConfig.threshold_pct)
    if cfg.threshold_pct <= 0:
        raise ValueError("threshold must be > 0")
    if not highs:
        return []

    pivots: list[Pivot] = []
    direction = 0  # 0 undetermined, +1 seeking a high, -1 seeking a low
    ext_idx = 0
    ext_price = float(highs[0])
    phi, phi_idx = float(highs[0]), 0
    plo, plo_idx = float(lows[0]), 0

    for i in range(1, len(highs)):
        hi, lo = float(highs[i]), float(lows[i])
        if direction == 0:
            if hi > phi:
                phi, phi_idx = hi, i
            if lo < plo:
                plo, plo_idx = lo, i
            if hi >= plo * (1 + _threshold_at(plo_idx, highs, cfg, atr_pct)):
                pivots.append(Pivot(plo_idx, i, "low", plo))
                direction, ext_idx, ext_price = 1, i, hi
            elif lo <= phi * (1 - _threshold_at(phi_idx, highs, cfg, atr_pct)):
                pivots.append(Pivot(phi_idx, i, "high", phi))
                direction, ext_idx, ext_price = -1, i, lo
            continue

        if direction == 1:
            if hi > ext_price:
                ext_idx, ext_price = i, hi
            elif lo <= ext_price * (1 - _threshold_at(ext_idx, highs, cfg, atr_pct)):
                pivots.append(Pivot(ext_idx, i, "high", ext_price))
                direction, ext_idx, ext_price = -1, i, lo
        else:
            if lo < ext_price:
                ext_idx, ext_price = i, lo
            elif hi >= ext_price * (1 + _threshold_at(ext_idx, highs, cfg, atr_pct)):
                pivots.append(Pivot(ext_idx, i, "low", ext_price))
                direction, ext_idx, ext_price = 1, i, hi
    return pivots


# ---------------------------------------------------------------- legs


@dataclass(frozen=True)
class Leg:
    """One completed high→low contraction."""

    depth: float
    high: Pivot
    low: Pivot
    ignored: bool = False  # below the noise floor — reported, not counted


def legs_from_pivots(
    pivots: Iterable[Pivot], *, noise_floor: float = 0.0
) -> list[Leg]:
    """Completed high→low legs as `Leg`s. A trailing high with no confirmed low is not a leg."""
    legs: list[Leg] = []
    previous: Pivot | None = None
    for pivot in pivots:
        if previous is not None and previous.kind == "high" and pivot.kind == "low":
            depth = (previous.price - pivot.price) / previous.price
            legs.append(Leg(depth, previous, pivot, ignored=depth < noise_floor))
        previous = pivot
    return legs


def contractions(pivots: Iterable[Pivot], noise_floor: float = 0.0) -> list[tuple[float, Pivot, Pivot]]:
    """Back-compat view: counted (non-ignored) legs as `(depth, high, low)`."""
    return [(leg.depth, leg.high, leg.low) for leg in legs_from_pivots(pivots, noise_floor=noise_floor) if not leg.ignored]


# ---------------------------------------------------------------- state at a date


@dataclass
class VcpState:
    """Everything the satellite publishes for one (ticker, date) — facts and flags kept apart."""

    # --- facts
    contraction_count: int = 0
    depths: list[float] = field(default_factory=list)  # counted legs, newest last
    leg_depths_all: list[float] = field(default_factory=list)  # every leg, incl. ignored noise
    ignored_legs: int = 0  # legs below the noise floor
    leg_highs: list[float] = field(default_factory=list)
    pivot_line: float | None = None  # most recent confirmed swing high — the level to break
    pivot_line_idx: int | None = None
    pivot_confirm_idx: int | None = None
    as_of_idx: int | None = None
    last_pivot_low: float | None = None
    base_high: float | None = None
    base_depth: float | None = None
    days_in_base: int = 0

    # --- volume
    leg_volume_ratios: list[float] = field(default_factory=list)  # per counted leg, market-neutral
    volume_dryup_ratio: float | None = None  # newest leg ÷ 50d baseline
    breakout_volume_ratio: float | None = None  # volume ÷ avg_vol_50d on the latest bar
    dist_to_pivot_pct: float | None = None  # close vs pivot line

    # --- flags (separate from the facts, so a screener can require what it wants)
    depths_descending: bool = False
    highs_descending: bool = False
    halving: bool = False
    has_shakeout: bool = False
    volume_dryup_compressing: bool = False
    base_qualified: bool = False
    breakout: bool = False
    breakout_on_volume: bool = False

    # --- relational facts, tolerance-based (Lo-Mamaysky-Wang's pattern formalism)
    leg_days: list[int] = field(default_factory=list)
    leg_atr_ratios: list[float] = field(default_factory=list)
    first_leg_depth: float | None = None
    days_since_pivot: int | None = None
    pivot_proximity_band: int = 0  # 2 = within 4% of the pivot, 1 = within 8%, else 0
    execution_state: str = "none"  # pre_breakout | breakout | early_post_breakout | extended |
    #                                overextended | damaged | forming | none

    # --- relational and gate flags
    depths_descending_tol: bool = False
    highs_descending_tol: bool = False
    lows_ascending: bool = False
    lows_ascending_tol: bool = False
    max_contraction_ratio_ok: bool = False
    first_leg_deep_enough: bool = False
    legs_long_enough: bool = False
    base_long_enough: bool = False
    wide_and_loose: bool = False
    atr_contracting: bool = False
    breakout_clear: bool = False
    breakout_event: bool = False

    @property
    def compressing(self) -> bool:
        """Back-compat alias for `depths_descending`."""
        return self.depths_descending

    @property
    def confirm_lag(self) -> int | None:
        """Bars since the pivot line became knowable (point-in-time evidence)."""
        if self.as_of_idx is None or self.pivot_confirm_idx is None:
            return None
        return self.as_of_idx - self.pivot_confirm_idx

    @property
    def contraction_ratio(self) -> float | None:
        """Newest depth ÷ previous depth. ≤ 1 compressing; ≈ 0.5 is Node D's halving."""
        if len(self.depths) < 2 or self.depths[-2] == 0:
            return None
        return self.depths[-1] / self.depths[-2]


def _mean(values: Sequence[float]) -> float:
    finite = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return sum(finite) / len(finite) if finite else float("nan")


def execution_state(
    state: "VcpState",
    cfg: VcpConfig,
    closes: Sequence[float] | None,
    as_of_idx: int,
    sma200: float | None,
) -> str:
    """Where the pattern sits in its lifecycle — the thing a strategy actually trades (JadeGate).

    Order matters: damage and blow-off conditions dominate, because a damaged base, or a name already
    50% past its 200-day average, is not a buy point at any price. Every input is point-in-time, so
    the state is reproducible from bars ≤ ``as_of_idx``.
    """
    if state.contraction_count == 0 or state.pivot_line is None:
        return "none"
    if state.wide_and_loose:
        return "damaged"
    if not state.base_qualified:
        return "forming"
    if closes is None:
        return "forming"
    price = float(closes[as_of_idx])
    if (
        sma200 is not None
        and float(sma200) > 0
        and price > float(sma200) * (1 + cfg.overextended_sma200_pct)
    ):
        return "overextended"
    if state.breakout_event:
        return "breakout"
    if state.breakout:
        distance = state.dist_to_pivot_pct or 0.0
        return "extended" if distance > cfg.extended_pct else "early_post_breakout"
    if state.dist_to_pivot_pct is not None and state.dist_to_pivot_pct >= -cfg.pre_breakout_pct:
        return "pre_breakout"
    return "forming"


def state_at(
    dates: Sequence[object],
    highs: Sequence[float],
    lows: Sequence[float],
    as_of_idx: int,
    *,
    threshold: float | None = None,
    config: VcpConfig | None = None,
    closes: Sequence[float] | None = None,
    volumes: Sequence[float] | None = None,
    market_volumes: Sequence[float] | None = None,
    avg_vol_50d: Sequence[float] | None = None,
    atr_pct: Sequence[float] | None = None,
    atr_14: Sequence[float] | None = None,
    sma200: float | None = None,
    max_contractions: int | None = None,
) -> VcpState:
    """VCP state using **only** bars ≤ ``as_of_idx`` (the point-in-time contract)."""
    cfg = config or VcpConfig(threshold_pct=threshold if threshold is not None else VcpConfig.threshold_pct)
    limit = max_contractions if max_contractions is not None else cfg.max_contractions
    window_h, window_l = list(highs[: as_of_idx + 1]), list(lows[: as_of_idx + 1])
    window_atr = list(atr_pct[: as_of_idx + 1]) if atr_pct is not None else None
    pivots = [
        p
        for p in find_pivots(window_h, window_l, config=cfg, atr_pct=window_atr)
        if p.confirm_idx <= as_of_idx
    ]

    # Noise floor: an ATR-scaled floor adapts per stock; `min_leg_depth` is an absolute floor.
    floor = cfg.min_leg_depth
    if cfg.noise_floor_atr_k and window_atr is not None:
        floor = max(floor, cfg.noise_floor_atr_k * _mean(window_atr[-60:]))
    all_legs = legs_from_pivots(pivots, noise_floor=floor)

    state = VcpState()
    state.as_of_idx = as_of_idx
    state.leg_depths_all = [round(leg.depth, 6) for leg in all_legs]
    state.ignored_legs = sum(1 for leg in all_legs if leg.ignored)
    if not all_legs:
        return state

    highs_only = [p for p in pivots if p.kind == "high"]
    if highs_only:
        latest = highs_only[-1]
        state.pivot_line = latest.price
        state.pivot_line_idx = latest.idx
        state.pivot_confirm_idx = latest.confirm_idx
    if closes is not None and state.pivot_line:
        state.dist_to_pivot_pct = float(closes[as_of_idx]) / state.pivot_line - 1.0

    counted = [leg for leg in all_legs if not leg.ignored][-limit:]
    if not counted:
        return state

    state.depths = [round(leg.depth, 6) for leg in counted]
    state.leg_highs = [round(leg.high.price, 6) for leg in counted]
    state.contraction_count = len(counted)
    state.depths_descending = all(
        counted[i + 1].depth < counted[i].depth for i in range(len(counted) - 1)
    )
    state.highs_descending = all(
        counted[i + 1].high.price < counted[i].high.price for i in range(len(counted) - 1)
    )
    state.has_shakeout = any(
        counted[i + 1].depth > counted[i].depth * cfg.shakeout_factor
        for i in range(len(counted) - 1)
    )
    if len(counted) >= 2 and counted[-2].depth > 0:
        ratio = counted[-1].depth / counted[-2].depth
        state.halving = cfg.halving_lo <= ratio <= cfg.halving_hi

    first_high, newest_low = counted[0].high, counted[-1].low
    state.base_high = first_high.price
    state.last_pivot_low = newest_low.price
    state.base_depth = (first_high.price - newest_low.price) / first_high.price
    state.days_in_base = as_of_idx - first_high.idx
    state.base_qualified = (
        len(counted) >= 2
        and state.base_depth <= cfg.max_base_depth
        and state.days_in_base <= cfg.max_base_bars
    )

    # Volume: per-leg, relative to the 50-bar baseline at the leg's start, market-neutral when a
    # market series is supplied (finding V3: avg_vol_5d/avg_vol_90d conflates stock-specific dry-up
    # with a market-wide decline).
    if volumes is not None:
        ratios: list[float] = []
        for leg in counted:
            start = max(0, leg.high.idx - cfg.volume_baseline_bars)
            baseline = _mean(volumes[start : leg.high.idx + 1])
            leg_mean = _mean(volumes[leg.high.idx : leg.low.idx + 1])
            if not (baseline and np.isfinite(baseline)):
                continue
            ratio = leg_mean / baseline
            if market_volumes is not None:
                m_baseline = _mean(market_volumes[start : leg.high.idx + 1])
                m_leg = _mean(market_volumes[leg.high.idx : leg.low.idx + 1])
                if m_baseline and np.isfinite(m_baseline) and m_leg:
                    ratio = ratio / (m_leg / m_baseline)
            ratios.append(round(ratio, 6))
        state.leg_volume_ratios = ratios
        state.volume_dryup_ratio = ratios[-1] if ratios else None
        state.volume_dryup_compressing = (
            len(ratios) >= 2 and all(ratios[i + 1] < ratios[i] for i in range(len(ratios) - 1))
        )

    if avg_vol_50d is not None and volumes is not None:
        base_vol = avg_vol_50d[as_of_idx]
        if base_vol and np.isfinite(float(base_vol)) and float(base_vol) > 0:
            state.breakout_volume_ratio = round(float(volumes[as_of_idx]) / float(base_vol), 6)
    if closes is not None and state.pivot_line:
        state.breakout = float(closes[as_of_idx]) > state.pivot_line
        state.breakout_on_volume = bool(
            state.breakout
            and state.breakout_volume_ratio is not None
            and state.breakout_volume_ratio >= cfg.breakout_volume_mult
        )

    # ------------------------------------------------ relational facts and gates
    tol = cfg.level_tolerance
    state.leg_days = [leg.low.idx - leg.high.idx for leg in counted]
    state.first_leg_depth = counted[0].depth
    if state.pivot_line_idx is not None:
        state.days_since_pivot = as_of_idx - state.pivot_line_idx

    # Lo-Mamaysky-Wang compare levels *within a tolerance*, not strictly. That is the discriminant
    # the messy-base work needed: a split leg violates higher-lows by ~11%, a legitimate contraction
    # wobbles by <0.5%, so a strict comparison rejects both while a tolerance separates them.
    state.depths_descending_tol = all(
        counted[i + 1].depth <= counted[i].depth * (1 + tol) for i in range(len(counted) - 1)
    )
    state.highs_descending_tol = all(
        counted[i + 1].high.price <= counted[i].high.price * (1 + tol)
        for i in range(len(counted) - 1)
    )
    state.lows_ascending = all(
        counted[i + 1].low.price > counted[i].low.price for i in range(len(counted) - 1)
    )
    state.lows_ascending_tol = all(
        counted[i + 1].low.price >= counted[i].low.price * (1 - tol)
        for i in range(len(counted) - 1)
    )

    ratios = [
        counted[i + 1].depth / counted[i].depth
        for i in range(len(counted) - 1)
        if counted[i].depth > 0
    ]
    state.max_contraction_ratio_ok = bool(ratios) and max(ratios) <= cfg.max_contraction_ratio
    state.first_leg_deep_enough = counted[0].depth >= cfg.first_leg_min_depth
    state.legs_long_enough = bool(state.leg_days) and all(
        days >= cfg.min_contraction_days for days in state.leg_days
    )
    state.base_long_enough = state.days_in_base >= cfg.base_duration_min
    state.wide_and_loose = counted[-1].depth > cfg.wide_and_loose_depth

    # Per-leg ATR envelope (the Substack's volatility measure): a wiggle inflates percentage depth
    # but not the envelope, so this is an independent read on "contracting".
    if atr_14 is not None:
        leg_atr: list[float] = []
        for leg in counted:
            baseline = _mean(
                atr_14[max(0, leg.high.idx - cfg.volume_baseline_bars) : leg.high.idx + 1]
            )
            leg_mean = _mean(atr_14[leg.high.idx : leg.low.idx + 1])
            if baseline and np.isfinite(baseline):
                leg_atr.append(round(leg_mean / baseline, 6))
        state.leg_atr_ratios = leg_atr
        state.atr_contracting = len(leg_atr) >= 2 and all(
            leg_atr[i + 1] < leg_atr[i] for i in range(len(leg_atr) - 1)
        )

    # Pivot proximity bands (EMMA019) and breakout clearance / cross event (Substack).
    if state.dist_to_pivot_pct is not None:
        distance = abs(state.dist_to_pivot_pct)
        state.pivot_proximity_band = 2 if distance <= 0.04 else 1 if distance <= 0.08 else 0
    if closes is not None and state.pivot_line:
        price = float(closes[as_of_idx])
        previous = float(closes[as_of_idx - 1]) if as_of_idx > 0 else price
        state.breakout_clear = price > state.pivot_line * (1 + cfg.breakout_clearance)
        state.breakout_event = price > state.pivot_line and previous <= state.pivot_line

    state.execution_state = execution_state(state, cfg, closes, as_of_idx, sma200)
    return state


# ---------------------------------------------------------------- V1-V3 measures


def true_max_drawdown(closes: Sequence[float]) -> float:
    """Max drawdown from the running peak — V2's quantity, never above amplitude."""
    peak = float("-inf")
    worst = 0.0
    for value in closes:
        value = float(value)
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return abs(worst)


def atr_normalised_range(highs, lows, closes, window: int, atr: Sequence[float]) -> list[float]:
    """Range over ``window`` bars divided by ATR at each bar — V3's fix for high−low ratios."""
    out: list[float] = []
    for i in range(len(closes)):
        if i + 1 < window:
            out.append(float("nan"))
            continue
        hi = max(float(h) for h in highs[i + 1 - window : i + 1])
        lo = min(float(lo_) for lo_ in lows[i + 1 - window : i + 1])
        a = float(atr[i])
        out.append((hi - lo) / a if a and np.isfinite(a) and a > 0 else float("nan"))
    return out


def market_neutral_dryup(
    stock_volume: Sequence[float], market_volume: Sequence[float], window: int
) -> list[float]:
    """Leg-relative volume: stock's window mean ÷ market's window mean."""

    def rolling_mean(values: Sequence[float], end: int) -> float:
        lo = max(0, end + 1 - window)
        chunk = [float(v) for v in values[lo : end + 1] if np.isfinite(float(v))]
        return sum(chunk) / len(chunk) if chunk else float("nan")

    out: list[float] = []
    for i in range(len(stock_volume)):
        s, m = rolling_mean(stock_volume, i), rolling_mean(market_volume, i)
        out.append(s / m if m and np.isfinite(m) and m > 0 else float("nan"))
    return out


# ---------------------------------------------------------------- fixture + canary


def synth_base(
    contraction_depths: Sequence[float] = (0.20, 0.10, 0.05),
    *,
    start: float = 100.0,
    bars_per_leg: int = 10,
    lower_highs: Sequence[float] | None = None,
    rally_highs: Sequence[float] | None = None,
    breakout_bars: int = 6,
    breakout_target: float = 1.05,
    wick: float = 0.002,
    wiggle_at: int | None = None,
    wiggle_pct: float = 0.0,
) -> dict[str, list[float]]:
    """A synthetic base with the given contraction depths, then a breakout above the pivot line.

    Each leg is monotonic (linear, so it *reaches* its target — an asymptotic ramp lands ~35% short
    at 10 bars and quietly weakens the fixture). ``rally_highs`` replaces the default descending
    highs with explicit price levels, which is how the "higher high" and messy shapes are built.
    ``wiggle_at``/``wiggle_pct`` inject a counter-move inside leg ``wiggle_at`` to test noise.
    """
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []

    def emit(price: float) -> None:
        highs.append(price * (1 + wick))
        lows.append(price * (1 - wick))
        closes.append(price)

    def ramp(start_price: float, target: float, bars: int) -> None:
        for k in range(1, bars + 1):
            emit(start_price + (target - start_price) * k / bars)

    price = start
    emit(price)
    for n, depth in enumerate(contraction_depths):
        leg_start = price
        if wiggle_at == n and wiggle_pct:
            mid = leg_start * (1 - depth / 2)
            ramp(leg_start, mid, max(1, bars_per_leg // 2))
            ramp(mid, mid * (1 + wiggle_pct), max(1, bars_per_leg // 2))
            ramp(mid * (1 + wiggle_pct), leg_start * (1 - depth), bars_per_leg)
            price = leg_start * (1 - depth)
        else:
            ramp(leg_start, leg_start * (1 - depth), bars_per_leg)
            price = leg_start * (1 - depth)
        next_high = (
            rally_highs[n] * start
            if rally_highs and n < len(rally_highs)
            else lower_highs[n] * start
            if lower_highs and n < len(lower_highs)
            else start * (1 - 0.03 * (n + 1))
        )
        ramp(price, next_high, bars_per_leg)
        price = next_high
    ramp(price, max(highs) * breakout_target, breakout_bars)
    return {"high": highs, "low": lows, "close": closes}


def synth_volume(n: int, *, base: float = 1_000_000.0) -> list[float]:
    return [base] * n


def assert_point_in_time(
    highs: Sequence[float],
    lows: Sequence[float],
    dates: Sequence[object],
    *,
    threshold: float,
    config: VcpConfig | None = None,
) -> None:
    """Canary: the state published at bar t must equal the state computed on bars ≤ t.

    Recomputation, not inspection — the check the phase's gate calls "point-in-time clean".
    """
    for t in range(len(highs)):
        full = state_at(dates, highs, lows, t, threshold=threshold, config=config)
        truncated = state_at(
            dates[: t + 1], highs[: t + 1], lows[: t + 1], t, threshold=threshold, config=config
        )
        if (full.contraction_count, tuple(full.depths), full.pivot_line) != (
            truncated.contraction_count,
            tuple(truncated.depths),
            truncated.pivot_line,
        ):
            raise AssertionError(f"look-ahead at bar {t}: {full!r} != {truncated!r}")
