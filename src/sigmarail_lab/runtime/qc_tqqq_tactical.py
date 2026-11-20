"""
TQQQ tactical alpha + portfolio construction (IBD/Vibha SMA-proxy rules).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from AlgorithmImports import *  # noqa: F401,F403
from QuantConnect import Market, SecurityType, Symbol

from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget

from sigmarail_lab.tqqq_tactical_rules import TqqqTacticalParams, evaluate_target_weight


class VeraTqqqTacticalAlphaModel(AlphaModel):
    """Daily signal for single-name TQQQ tactical sleeve."""

    def __init__(self, store: Any, **params: Any):
        self._store = store
        self._params = TqqqTacticalParams.from_dict(params)
        self._last_run_date = None
        self._target_weight = 0.0
        self.Name = "VeraTqqqTacticalAlphaModel"

    def Update(self, algorithm, data):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []
        self._last_run_date = today

        as_of = (today - timedelta(days=1)).isoformat()
        spy_bull = self._store.get_spy_is_bull(as_of)
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)

        qqq = self._store.get_technical_features(self._params.signal_ticker, as_of)
        tqqq_row = self._store.get_technical_features(self._params.trade_ticker, as_of)
        tqqq_close = self._store.get_ticker_close(self._params.trade_ticker, as_of)
        if tqqq_close is not None:
            tqqq_row = {**tqqq_row, "close": tqqq_close}

        prev_weight = self._target_weight
        self._target_weight = evaluate_target_weight(
            current_weight=prev_weight,
            qqq=qqq,
            tqqq=tqqq_row,
            spy_bull=spy_bull,
            params=self._params,
            alloc_fraction=alloc_fraction,
        )

        symbol = Symbol.Create(self._params.trade_ticker, SecurityType.Equity, Market.USA)
        if not algorithm.Securities.ContainsKey(symbol):
            algorithm.Debug(f"TQQQ ALPHA {as_of}: {self._params.trade_ticker} not in universe")
            return []

        algorithm.Debug(
            f"TQQQ ALPHA {as_of}: target={self._target_weight:.1%} "
            f"(prev={prev_weight:.1%} spy_bull={spy_bull})"
        )

        if self._target_weight <= 0:
            if algorithm.Portfolio[symbol].Invested or prev_weight > 0:
                return [Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)]
            return []

        return [Insight.Price(symbol, timedelta(days=2), InsightDirection.Up)]


class VeraTqqqTacticalPortfolioConstructionModel(PortfolioConstructionModel):
    """Apply evaluate_target_weight result as percent target."""

    def __init__(self, store: Any, **params: Any):
        self._store = store
        self._params = TqqqTacticalParams.from_dict(params)

    def CreateTargets(self, algorithm, insights):
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        spy_bull = self._store.get_spy_is_bull(as_of)
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)

        qqq = self._store.get_technical_features(self._params.signal_ticker, as_of)
        tqqq_row = self._store.get_technical_features(self._params.trade_ticker, as_of)
        tqqq_close = self._store.get_ticker_close(self._params.trade_ticker, as_of)
        if tqqq_close is not None:
            tqqq_row = {**tqqq_row, "close": tqqq_close}

        symbol = Symbol.Create(self._params.trade_ticker, SecurityType.Equity, Market.USA)
        current = 0.0
        if algorithm.Portfolio.ContainsKey(symbol) and algorithm.Portfolio.TotalPortfolioValue > 0:
            current = float(algorithm.Portfolio[symbol].HoldingsValue) / float(
                algorithm.Portfolio.TotalPortfolioValue
            )

        target = evaluate_target_weight(
            current_weight=current,
            qqq=qqq,
            tqqq=tqqq_row,
            spy_bull=spy_bull,
            params=self._params,
            alloc_fraction=alloc_fraction,
        )

        flat = [i for i in insights if i.Direction == InsightDirection.Flat]
        targets: list = [PortfolioTarget(i.Symbol, 0) for i in flat]

        if target <= 0:
            if algorithm.Portfolio.ContainsKey(symbol) and algorithm.Portfolio[symbol].Invested:
                targets.append(PortfolioTarget(symbol, 0))
            return targets

        pct_target = PortfolioTarget.Percent(algorithm, symbol, target)
        if pct_target is not None:
            targets.append(pct_target)
        return targets

    def OnSecuritiesChanged(self, algorithm, changes):
        pass
