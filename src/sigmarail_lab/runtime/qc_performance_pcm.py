"""Performance-weighted (strategy-momentum) portfolio construction.

Allocates more capital to legs with positive trailing performance and less to
laggards — the "allocate to winners" overlay (plan §5.1). The pure core is
``performance_weights``; the LEAN PCM delegates to it.
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


def performance_weights(
    returns: dict[str, float],
    *,
    floor: float = 0.0,
    ceiling: float = 1.0,
) -> dict[str, float]:
    """Strategy-momentum allocation from per-leg trailing returns.

    Positive returns earn proportionally more weight; non-positive returns earn
    ``floor``. Weights are clamped to ``[floor, ceiling]`` and normalized to sum
    to 1.0. Falls back to equal weight when there is no positive signal.
    """
    if not returns:
        return {}
    scores = {k: max(0.0, float(v)) for k, v in returns.items()}
    total = sum(scores.values())
    if total <= 0:
        w = 1.0 / len(returns)
        return {k: w for k in returns}
    weights = {k: scores[k] / total for k in returns}
    weights = {k: min(max(w, floor), ceiling) for k, w in weights.items()}
    total = sum(weights.values())
    if total <= 0:
        w = 1.0 / len(weights)
        return {k: w for k in weights}
    return {k: w / total for k, w in weights.items()}


class PerformanceWeightedPortfolioConstructionModel(PortfolioConstructionModel):
    """LEAN PCM: reweights insights by their source leg's trailing performance."""

    def __init__(
        self,
        metric: str = "trailing_return",
        lookback_days: int = 60,
        floor: float = 0.0,
        ceiling: float = 1.0,
        rebalance_days: int = 1,
        store: Any = None,
    ):
        self._metric = metric
        self._lookback_days = int(lookback_days)
        self._floor = float(floor)
        self._ceiling = float(ceiling)
        self._rebalance_period = timedelta(days=int(rebalance_days))
        self._store = store
        self._last_rebalance = None
        self.Name = "PerformanceWeightedPortfolioConstructionModel"

    def bind_store(self, store: Any) -> None:
        self._store = store

    def _leg_returns(self, algorithm: Any) -> dict[str, float]:
        if self._store is not None and hasattr(self._store, "leg_returns"):
            return self._store.leg_returns(algorithm, self._lookback_days, self._metric)
        return {}

    def CreateTargets(self, algorithm: Any, insights: list) -> list:  # noqa: ANN001
        targets = []
        if not insights:
            return targets
        if self._last_rebalance is not None and algorithm.Time - self._last_rebalance < self._rebalance_period:
            return targets
        self._last_rebalance = algorithm.Time

        weights = performance_weights(
            self._leg_returns(algorithm), floor=self._floor, ceiling=self._ceiling
        )
        default = 1.0 / max(1, len(insights))
        for insight in insights:
            source = getattr(insight, "SourceModel", None)
            leg = getattr(source, "Name", None) or "default"
            w = weights.get(leg, default)
            targets.append(PortfolioTarget.Percent(algorithm, insight.Symbol, w))
        return targets
