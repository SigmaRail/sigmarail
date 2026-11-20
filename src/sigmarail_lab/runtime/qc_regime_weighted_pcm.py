"""Regime-weighted portfolio construction (Dalio tactical tilt).

Reads the current economic-environment quadrant from the store and sets each
leg's target weight from a per-quadrant ``regime_map`` (symbol -> weight).
Falls back to equal weight when the quadrant is unknown. This is the
``conditional`` entourage mode: regime-conditional leg exposure.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget
except ImportError:  # unit-test fallback (no LEAN)
    class PortfolioConstructionModel:
        pass

    class PortfolioTarget:
        def __init__(self, symbol, quantity):  # noqa: ANN001
            self.Symbol = symbol
            self.Quantity = quantity

        @classmethod
        def Percent(cls, algorithm, symbol, percent):  # noqa: ANN001,ANN003
            pt = PortfolioTarget(symbol, percent)
            return pt


def regime_weights(
    quadrant: str,
    regime_map: dict[str, dict[str, float]],
    symbols: list[str],
) -> dict[str, float]:
    """Per-symbol target weights for a quadrant; equal weight when unknown.

    ``regime_map`` is ``{quadrant: {symbol: weight}}``. Weights are normalized
    over the *available* symbols (a symbol absent from the quadrant gets 0).
    """
    symbols = [s for s in symbols if s]
    if not symbols:
        return {}
    if quadrant and quadrant in regime_map:
        mapped = regime_map[quadrant]
        out = {s: float(mapped.get(s, 0.0)) for s in symbols}
        total = sum(out.values())
        if total > 0:
            return {s: w / total for s, w in out.items()}
    w = 1.0 / len(symbols)
    return {s: w for s in symbols}


class RegimeWeightedPortfolioConstructionModel(PortfolioConstructionModel):
    """LEAN PCM: reweights legs by the current economic-environment quadrant."""

    def __init__(
        self,
        regime_map: dict[str, dict[str, float]] | None = None,
        signal: str = "economic_environment",
        rebalance_days: int = 7,
        store: Any = None,
    ):
        self._regime_map = dict(regime_map or {})
        self._signal = signal
        self._rebalance_period = timedelta(days=int(rebalance_days))
        self._store = store
        self._last_rebalance = None
        self.Name = "RegimeWeightedPortfolioConstructionModel"

    def bind_store(self, store: Any) -> None:
        self._store = store

    def _quadrant(self, algorithm: Any) -> str:
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        if self._store is not None:
            return str(getattr(self._store, "economic_quadrant", lambda d: "")(as_of) or "")
        return ""

    def CreateTargets(self, algorithm: Any, insights: list) -> list:  # noqa: ANN001
        targets = []
        if not insights:
            return targets
        if self._last_rebalance is not None and algorithm.Time - self._last_rebalance < self._rebalance_period:
            return targets
        self._last_rebalance = algorithm.Time

        quadrant = self._quadrant(algorithm)
        symbols = [str(getattr(i.Symbol, "Value", "")) for i in insights]
        weights = regime_weights(quadrant, self._regime_map, symbols)

        for insight in insights:
            sym = str(getattr(insight.Symbol, "Value", ""))
            w = weights.get(sym, 1.0 / max(1, len(symbols)))
            targets.append(PortfolioTarget.Percent(algorithm, insight.Symbol, w))
        return targets
