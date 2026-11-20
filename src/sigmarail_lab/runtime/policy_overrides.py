"""Apply PolicyOverride chains (when → set) last-wins per allowlisted param."""

from __future__ import annotations

from typing import Any

from sigmarail_lab.runtime.signal_evaluation import evaluate_slot_bool

# Keep in sync with vera_query_core.strategy.pipeline.POLICY_OVERRIDE_KEYS
POLICY_OVERRIDE_KEYS = frozenset(
    {
        "risk_per_trade_pct",
        "max_position_weight",
        "trailing_stop_pct",
        "atr_stop_multiplier",
        "breakeven_time_stop_days",
        "max_holding_days",
        "max_hold_days",
    }
)

_PCM_KEYS = frozenset({"risk_per_trade_pct", "max_position_weight"})
_RISK_KEYS = frozenset(
    {
        "trailing_stop_pct",
        "atr_stop_multiplier",
        "breakeven_time_stop_days",
        "max_holding_days",
        "max_hold_days",
    }
)


def resolve_policy_overrides(
    overrides: list[dict[str, Any]] | None,
    row: dict[str, Any] | None,
    *,
    consumer: str,
) -> dict[str, float | int | bool]:
    """Return effective override values for ``consumer`` (``pcm`` or ``risk``).

    Chain order: last matching ``when`` wins per key.
    """
    if not overrides:
        return {}
    allow = _PCM_KEYS if consumer == "pcm" else _RISK_KEYS
    bag = row or {}
    out: dict[str, float | int | bool] = {}
    for ov in overrides:
        if not isinstance(ov, dict):
            continue
        when = ov.get("when")
        set_map = ov.get("set")
        if not isinstance(when, dict) or not isinstance(set_map, dict):
            continue
        if not evaluate_slot_bool(bag, when):
            continue
        for key, val in set_map.items():
            k = str(key)
            if k not in allow or k not in POLICY_OVERRIDE_KEYS:
                continue
            # Normalize hold alias for Risk.
            if k == "max_hold_days":
                k = "max_holding_days"
            out[k] = val  # type: ignore[assignment]
    return out
