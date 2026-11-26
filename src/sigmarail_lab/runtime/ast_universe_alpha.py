"""Enforce SigmaRail query membership at the LEAN Alpha boundary."""

from __future__ import annotations

try:
    from AlgorithmImports import AlphaModel, InsightDirection  # type: ignore[import-not-found]
except ImportError:
    class AlphaModel:  # pragma: no cover - LEAN host supplies the implementation
        pass

    class InsightDirection:  # pragma: no cover - only used by the standalone test stub
        Up = 1


def _ticker(value) -> str:
    symbol = getattr(value, "Symbol", value)
    return str(getattr(symbol, "Value", symbol))


def _held_tickers(algorithm) -> set[str]:
    held: set[str] = set()
    try:
        for item in algorithm.Portfolio:
            if item.Value.Invested:
                held.add(_ticker(item.Key))
    except Exception:
        pass
    return held


class SigmaRailQueryUniverseAlphaModel(AlphaModel):
    """Filter LEAN Alpha output to AST members, retaining non-entry signals for holdings."""

    def __init__(self, model):
        super().__init__()
        self._model = model
        self._up = getattr(InsightDirection, "Up", None)
        if self._up is None:
            self._up = getattr(InsightDirection, "UP", None)

    def OnSecuritiesChanged(self, algorithm, changes) -> None:
        callback = getattr(self._model, "OnSecuritiesChanged", None)
        if callable(callback):
            callback(algorithm, changes)

    def Update(self, algorithm, data):
        insights = self._model.Update(algorithm, data) or []
        selected = set(getattr(algorithm, "_decision_universe_rows", {}) or {})
        held = _held_tickers(algorithm)
        admitted = []
        for insight in insights:
            ticker = _ticker(getattr(insight, "Symbol", ""))
            if ticker in selected:
                admitted.append(insight)
                continue
            if ticker in held and getattr(insight, "Direction", None) != self._up:
                admitted.append(insight)
        return admitted
