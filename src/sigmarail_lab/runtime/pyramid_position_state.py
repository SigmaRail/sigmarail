"""Progressive entry phase state — owned by RiskBudgeted PCM."""

from __future__ import annotations

from typing import Any

from sigmarail_lab.ir.rules import validate_phases
from sigmarail_lab.runtime.signal_evaluation import evaluate_slot_bool


class PyramidPositionState:
    """Tracks one position's progressive entry phase and sizing."""

    def __init__(self, ticker: str, phases: list[dict[str, Any]]) -> None:
        self.ticker = ticker
        self.phases = validate_phases(phases) or [
            {"name": "test", "size_pct": 0.50},
            {"name": "add", "size_pct": 0.25},
            {"name": "full", "size_pct": 0.25},
        ]
        self.phase_index = 0  # 0 = test, 1 = add, 2 = full
        self.entry_price: float | None = None
        self.highest_price: float = 0.0
        self.entry_date = None
        self.entry_rs: float = 0.0

    @property
    def phase_name(self) -> str:
        if self.phase_index >= len(self.phases):
            return "complete"
        return str(self.phases[self.phase_index].get("name", "phase"))

    @property
    def next_size_pct(self) -> float:
        if self.phase_index >= len(self.phases):
            return 0.0
        return float(self.phases[self.phase_index].get("size_pct", 0.0))

    def cumulative_size_pct(self) -> float:
        """Sum of phase size_pct from test through the current phase (inclusive)."""
        end = min(self.phase_index + 1, len(self.phases))
        total = 0.0
        for phase in self.phases[:end]:
            try:
                total += float(phase.get("size_pct", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
        return min(1.0, max(0.0, total))

    def next_phase_allows(
        self,
        row: dict[str, Any],
        contexts: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        """``phases[phase_index + 1].trigger`` gate — the typed per-phase
        predicate (bool AST over the unit context, same evaluator as rule
        ``when``). No trigger authored → allowed; phases exhausted → allowed
        (``add`` sizing already fails closed upstream).
        """
        nxt = self.phase_index + 1
        if nxt >= len(self.phases):
            return True
        trig = self.phases[nxt].get("trigger")
        if not trig:
            return True
        try:
            return evaluate_slot_bool(row, trig, contexts=contexts)
        except Exception:
            return False

    def advance(self) -> None:
        self.phase_index += 1
