"""Lean-safe RegimeGate evaluator (C-REGIME-GATE-V1).

VeraBase ``vera_query_core.strategy.regime_gate`` remains the authoring SSOT.
LEAN Docker only mounts this project (``PYTHONPATH=/project``), so the store
imports the evaluator from here instead of VeraBase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class _GateConfig:
    threshold: float = 0.50
    signal_weights: dict[str, float] = field(
        default_factory=lambda: {
            "s_ma200_macro": 0.40,
            "s_breadth200": 0.35,
            "s_breadth50": 0.25,
        }
    )
    confirm_on_days: int = 3
    confirm_off_days: int = 1
    missing_action: Literal["block", "allow"] = "block"


def _coerce_gate(gate: Any) -> _GateConfig:
    if gate is None:
        return _GateConfig()
    if isinstance(gate, _GateConfig):
        return gate
    if isinstance(gate, dict):
        cfg = _GateConfig()
        if "threshold" in gate and gate["threshold"] is not None:
            cfg.threshold = float(gate["threshold"])
        if isinstance(gate.get("signal_weights"), dict) and gate["signal_weights"]:
            cfg.signal_weights = {str(k): float(v) for k, v in gate["signal_weights"].items()}
        if "confirm_on_days" in gate and gate["confirm_on_days"] is not None:
            cfg.confirm_on_days = max(1, int(gate["confirm_on_days"]))
        if "confirm_off_days" in gate and gate["confirm_off_days"] is not None:
            cfg.confirm_off_days = max(1, int(gate["confirm_off_days"]))
        missing = gate.get("missing_action")
        if missing in ("block", "allow"):
            cfg.missing_action = missing
        return cfg
    # Pydantic RegimeGateV1 or duck-typed object
    cfg = _GateConfig()
    for attr in ("threshold", "confirm_on_days", "confirm_off_days", "missing_action", "signal_weights"):
        if hasattr(gate, attr):
            setattr(cfg, attr, getattr(gate, attr))
    if cfg.confirm_on_days < 1:
        cfg.confirm_on_days = 1
    if cfg.confirm_off_days < 1:
        cfg.confirm_off_days = 1
    if cfg.missing_action not in ("block", "allow"):
        cfg.missing_action = "block"
    if not isinstance(cfg.signal_weights, dict):
        cfg.signal_weights = _GateConfig().signal_weights
    return cfg


class RegimeGateEvaluator:
    """Evaluates continuous market regime signals with confirmation hysteresis."""

    def __init__(self, gate: Any = None) -> None:
        self.gate = _coerce_gate(gate)
        self._state: bool = False
        self._consecutive_on: int = 0
        self._consecutive_off: int = 0

    @property
    def current_state(self) -> bool:
        return self._state

    def evaluate_score(self, row: dict[str, Any] | None) -> float:
        if not row:
            return 0.0

        weights = self.gate.signal_weights
        if not weights:
            return 1.0 if float(row.get("spy_above200d") or 0.0) > 0 else 0.0

        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0

        score = 0.0
        for col, weight in weights.items():
            val = row.get(col)
            if val is not None:
                score += float(val) * weight
            elif col == "s_ma200_macro" and "spy_above200d" in row:
                score += float(row["spy_above200d"]) * weight

        return score / total_weight

    def update_day(self, date_str: str, row: dict[str, Any] | None) -> bool:
        del date_str  # reserved for future per-date diagnostics
        if not row:
            if self.gate.missing_action == "block":
                self._consecutive_on = 0
                self._consecutive_off += 1
                if self._consecutive_off >= self.gate.confirm_off_days:
                    self._state = False
                return False
            return True

        score = self.evaluate_score(row)
        condition_met = score >= self.gate.threshold

        if condition_met:
            self._consecutive_on += 1
            self._consecutive_off = 0
            if self._consecutive_on >= self.gate.confirm_on_days:
                self._state = True
        else:
            self._consecutive_off += 1
            self._consecutive_on = 0
            if self._consecutive_off >= self.gate.confirm_off_days:
                self._state = False

        return self._state
