"""
Pure rule evaluation for TQQQ tactical sizing (testable without Lean).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _f(row: Mapping[str, Any] | None, key: str, default: float = 0.0) -> float:
    if not row:
        return default
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _b(row: Mapping[str, Any] | None, key: str) -> bool:
    if not row:
        return False
    val = row.get(key)
    if val is None:
        return False
    return bool(int(val)) if isinstance(val, (int, float)) else bool(val)


@dataclass(frozen=True)
class TqqqTacticalParams:
    signal_ticker: str = "QQQ"
    trade_ticker: str = "TQQQ"
    base_weight: float = 0.10
    max_weight: float = 0.20
    qqq_pullback_min: float = 0.05
    max_pct_from_sma20_entry: float = 0.08
    trim_pct_from_sma20: float = 0.10
    trim_fraction_on_reversal: float = 0.15
    exit_on_two_closes_below_sma20: bool = True
    exit_on_close_below_first_up_day_low: bool = True
    require_spy_bull: bool = True
    buyhold_mode: bool = False

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> TqqqTacticalParams:
        raw = raw or {}
        return cls(
            signal_ticker=str(raw.get("signal_ticker", "QQQ")),
            trade_ticker=str(raw.get("trade_ticker", "TQQQ")),
            base_weight=float(raw.get("base_weight", 0.10)),
            max_weight=float(raw.get("max_weight", 0.20)),
            qqq_pullback_min=float(raw.get("qqq_pullback_min", 0.05)),
            max_pct_from_sma20_entry=float(raw.get("max_pct_from_sma20_entry", 0.08)),
            trim_pct_from_sma20=float(raw.get("trim_pct_from_sma20", 0.10)),
            trim_fraction_on_reversal=float(raw.get("trim_fraction_on_reversal", 0.15)),
            exit_on_two_closes_below_sma20=bool(
                raw.get("exit_on_two_closes_below_sma20", True)
            ),
            exit_on_close_below_first_up_day_low=bool(
                raw.get("exit_on_close_below_first_up_day_low", True)
            ),
            require_spy_bull=bool(raw.get("require_spy_bull", True)),
            buyhold_mode=bool(raw.get("buyhold_mode", False)),
        )


def entry_signal(qqq: Mapping[str, Any] | None, tqqq: Mapping[str, Any] | None, params: TqqqTacticalParams) -> bool:
    if not qqq or not tqqq:
        return False
    pullback = _f(qqq, "drawdown_from_50d_high") <= -params.qqq_pullback_min
    thrust = int(_f(qqq, "up_days_last_3", 0)) >= 3
    near = _b(tqqq, "near_sma20_flag")
    not_extended = _f(tqqq, "pct_from_sma20d") <= params.max_pct_from_sma20_entry
    return pullback and thrust and near and not_extended


def exit_signal(
    tqqq: Mapping[str, Any] | None,
    params: TqqqTacticalParams,
) -> bool:
    if not tqqq:
        return False
    if params.exit_on_two_closes_below_sma20 and _b(tqqq, "two_closes_below_sma20"):
        return True
    if params.exit_on_close_below_first_up_day_low:
        stop = _f(tqqq, "first_up_day_low", 0.0)
        close = _f(tqqq, "close") or _f(tqqq, "tqqq_close")
        if stop > 0 and close > 0 and close < stop:
            return True
    return False


def trim_signal(tqqq: Mapping[str, Any] | None, params: TqqqTacticalParams) -> bool:
    if not tqqq:
        return False
    extended = _f(tqqq, "pct_from_sma20d") >= params.trim_pct_from_sma20
    reversal = _b(tqqq, "downside_reversal_flag")
    return extended and reversal


def evaluate_target_weight(
    *,
    current_weight: float,
    qqq: Mapping[str, Any] | None,
    tqqq: Mapping[str, Any] | None,
    spy_bull: bool,
    params: TqqqTacticalParams | None = None,
    alloc_fraction: float = 1.0,
) -> float:
    """Return target portfolio weight for trade_ticker (0..max_weight)."""
    p = params or TqqqTacticalParams()
    if p.buyhold_mode:
        return min(p.max_weight, max(p.base_weight, 0.0))
    if p.require_spy_bull and not spy_bull:
        return 0.0
    if exit_signal(tqqq, p):
        return 0.0
    target = current_weight
    if target <= 0 and entry_signal(qqq, tqqq, p):
        target = p.base_weight * max(0.0, min(1.0, alloc_fraction))
    elif target > 0 and trim_signal(tqqq, p):
        target = max(0.0, target * (1.0 - p.trim_fraction_on_reversal))
    if _b(tqqq, "extended_above_sma20_flag") and target < current_weight:
        pass  # allow trim down
    elif _b(tqqq, "extended_above_sma20_flag") and target > current_weight:
        target = current_weight  # no adds when extended
    return min(p.max_weight, max(0.0, target))
