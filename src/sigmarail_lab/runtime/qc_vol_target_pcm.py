"""Volatility-targeting portfolio construction (plan §5.2).

Scales the whole book to a target volatility. The pure core is
``vol_target_scale``; the LEAN PCM delegates to it.
"""

from __future__ import annotations

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


def vol_target_scale(current_vol: float, target_vol: float, band: float = 0.0) -> float:
    """Scale factor to bring ``current_vol`` toward ``target_vol``.

    - Returns 1.0 when either side is non-positive or the ratio is already
      within ``band`` (avoids churn).
    - Clamps leverage to ``[0, 2]`` (no shorting, max 2x leverage).
    """
    if current_vol <= 0 or target_vol <= 0:
        return 1.0
    ratio = target_vol / current_vol
    if band > 0 and abs(1.0 - ratio) <= band:
        return 1.0
    return min(max(ratio, 0.0), 2.0)


class VolatilityTargetingPortfolioConstructionModel(PortfolioConstructionModel):
    """LEAN PCM: scales all targets by the realized-vs-target vol ratio."""

    def __init__(self, target_vol: float = 0.15, band: float = 0.02, store: Any = None):
        self._target_vol = float(target_vol)
        self._band = float(band)
        self._store = store
        self.Name = "VolatilityTargetingPortfolioConstructionModel"

    def bind_store(self, store: Any) -> None:
        self._store = store

    def _current_vol(self, algorithm: Any) -> float:
        if self._store is not None and hasattr(self._store, "portfolio_vol"):
            return float(self._store.portfolio_vol(algorithm) or 0.0)
        # Fallback: realized vol from the algorithm's daily returns.
        try:
            return float(algorithm.Portfolio.TotalPortfolioValue * 0) + 0.0  # placeholder
        except Exception:  # noqa: BLE001
            return 0.0

    def CreateTargets(self, algorithm: Any, insights: list) -> list:  # noqa: ANN001
        targets = []
        if not insights:
            return targets
        scale = vol_target_scale(self._current_vol(algorithm), self._target_vol, self._band)
        for insight in insights:
            base = 1.0 / max(1, len(insights))
            targets.append(PortfolioTarget.Percent(algorithm, insight.Symbol, base * scale))
        return targets
