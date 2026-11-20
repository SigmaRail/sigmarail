"""RegimeGateV1 specification and evaluator (C-REGIME-GATE-V1).

Encodes market-condition gating with continuous normalized signal inputs,
asymmetric hysteresis (fast off, slow on confirmation), and fail-closed
semantics on missing data.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


RegimeUse = Literal[
    "scale_exposure",
    "skip_pyramid_adds",
    "block_new_longs",
    "hedge",
]


class RegimeGateV1(BaseModel):
    """Declarative regime score + optional slot uses (C-REGIME-POLICY-V1).

    Score/hysteresis remain the continuous market condition. ``uses`` lists which
    Lean slots subscribe — presence of a regime source alone is not an Alpha valve.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = "regime_signals_canonical"
    threshold: float = 0.50
    signal_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "s_ma200_macro": 0.40,
            "s_breadth200": 0.35,
            "s_breadth50": 0.25,
        }
    )
    confirm_on_days: int = Field(default=3, ge=1)
    confirm_off_days: int = Field(default=1, ge=1)
    missing_action: Literal["block", "allow"] = "block"
    expression: str | None = None
    min_allocation_fraction: float = 0.0
    uses: list[RegimeUse] = Field(
        default_factory=list,
        description="Slot subscriptions: scale_exposure, skip_pyramid_adds, block_new_longs, hedge",
    )


class RegimeGateEvaluator:
    """Evaluates continuous market regime signals with confirmation hysteresis."""

    def __init__(self, gate: RegimeGateV1 | dict[str, Any] | None = None) -> None:
        if gate is None:
            self.gate = RegimeGateV1()
        elif isinstance(gate, RegimeGateV1):
            self.gate = gate
        elif isinstance(gate, dict):
            # Allow dicts that might contain legacy keys or partial shapes
            filtered = {k: v for k, v in gate.items() if k in RegimeGateV1.model_fields}
            self.gate = RegimeGateV1.model_validate(filtered)
        else:
            self.gate = RegimeGateV1()

        self._state: bool = False
        self._consecutive_on: int = 0
        self._consecutive_off: int = 0

    @property
    def current_state(self) -> bool:
        return self._state

    def evaluate_score(self, row: dict[str, Any] | None) -> float:
        """Compute the continuous normalized market condition score for a day."""
        if not row:
            return 0.0

        weights = self.gate.signal_weights
        if not weights:
            # Fallback to single column if present
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
        """Online daily update: advances hysteresis counters and returns allows_new_longs."""
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

    def evaluate_series(self, rows_by_date: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Evaluate a historical range of dates sorted chronologically."""
        results: dict[str, dict[str, Any]] = {}
        for d in sorted(rows_by_date.keys()):
            row = rows_by_date[d]
            score = self.evaluate_score(row)
            is_on = self.update_day(d, row)
            results[d] = {
                "score": score,
                "on": is_on,
                "allows_new_longs": is_on,
            }
        return results
