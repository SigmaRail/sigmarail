"""
Market hedge model: deploys inverse ETFs when the regime goes risk-off.

Reads the regime allocation fraction from the store and holds SH (or other
inverse instruments) proportionally to the un-deployed equity fraction. When
the regime normalizes (allocation back to 1.0), the hedge unwinds.

This is additive to the entry gate: the gate already blocks new longs, while
this model *deploys* a short/inverse position instead of sitting in cash.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect import Market, SecurityType, Symbol
    from QuantConnect.Algorithm.Framework.Risk import RiskManagementModel
    from QuantConnect.Algorithm.Framework.Portfolio import PortfolioTarget
except ImportError:
    class RiskManagementModel:
        pass

    class PortfolioTarget:
        @classmethod
        def Percent(cls, algorithm, symbol, percent):
            class _PT:
                pass

            pt = _PT()
            pt.Symbol = symbol
            pt.Quantity = percent
            return pt

    class Symbol:
        def __init__(self, val):
            self.Value = str(val)

        @classmethod
        def Create(cls, ticker, sec_type=None, market=None):
            return cls(ticker)

    class SecurityType:
        Equity = 1

    class Market:
        USA = 1


class VeraHedgeModel(RiskManagementModel):
    """Deploy SH/SPXS inverse to the regime allocation_fraction."""

    def __init__(
        self,
        store,
        instruments: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        self._store = store
        self._instruments = instruments or [{"ticker": "SH", "max_allocation": 0.25}]
        self._last_run_date = None
        self.Name = "VeraHedgeModel"

    def _hedge_ratio(self, algorithm) -> float:
        """1.0 - effective_allocation_fraction, clamped to [0, 1]."""
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        frac = self._store.get_regime_field(as_of, "allocation_fraction")
        if frac is None:
            return 0.0
        try:
            allocation = float(frac)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, 1.0 - allocation))

    def _security_price(self, algorithm, symbol) -> float:
        sec = getattr(algorithm, "Securities", None)
        if sec is None or symbol not in sec:
            return 0.0
        return float(getattr(sec[symbol], "Price", 0.0) or 0.0)

    def ManageRisk(self, algorithm, targets):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return list(targets or [])
        self._last_run_date = today

        ratio = self._hedge_ratio(algorithm)
        risk_targets = list(targets or [])

        for inst in self._instruments:
            ticker = str(inst.get("ticker", ""))
            if not ticker:
                continue
            max_alloc = float(inst.get("max_allocation", 0.25))
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            securities = getattr(algorithm, "Securities", {}) or {}
            if symbol not in securities:
                # Ensure the hedge instrument is subscribed; wait for bars before targeting.
                try:
                    algorithm.AddEquity(ticker)
                except Exception:
                    continue
                continue
            price = self._security_price(algorithm, symbol)
            if price <= 0:
                continue
            target_weight = ratio * max_alloc
            if target_weight <= 0.0001:
                target_weight = 0.0
                # Avoid PortfolioTarget.Percent on flat hedge with no bar / no position.
                try:
                    holding = bool(algorithm.Portfolio[symbol].Invested)
                except Exception:
                    holding = False
                if not holding:
                    continue
            pt = PortfolioTarget.Percent(algorithm, symbol, target_weight)
            if pt is None:
                continue
            risk_targets.append(pt)
            algorithm.Debug(
                f"HEDGE {ticker}: regime ratio={ratio:.2f} -> target={target_weight:.1%}"
            )

        return risk_targets
