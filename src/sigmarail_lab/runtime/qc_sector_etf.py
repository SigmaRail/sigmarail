"""
ETF-based sector allocation with regime-scaled leverage and inverse hedging.

Regime tier → leverage tier:
  100 → 3x leveraged ETFs in top N sectors
   67 → 2x leveraged ETFs in top N sectors
   33 → base sector ETFs in top N sectors (reduced allocation)
    0 → inverse ETFs in bottom N sectors (hedge mode)

When tier > 0 and a leveraged tier is unavailable for a sector, falls back to
the next available tier (e.g. 3x → 2x → base).

When tier = 0 and a sector has no liquid inverse ETF, falls back to
``broad_inverse_etf`` (default SPXS) or skips that sector if ``None``.

Runtime: Lean / QC container (AlgorithmImports).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from AlgorithmImports import *  # noqa: F401,F403
from QuantConnect import Market, SecurityType, Symbol

from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget

from sigmarail_lab.ir.sector_etf_constants import DEFAULT_ETF_MAP, DEFAULT_ETF_UNIVERSE


def _pick_long_etf(tier: int, entry: dict[str, str | None]) -> str | None:
    """Select ETF ticker for the given regime tier (best available, with fallback)."""
    if tier >= 100:
        return entry.get("3x") or entry.get("2x") or entry.get("base")
    elif tier >= 67:
        return entry.get("2x") or entry.get("base")
    else:  # tier 33
        return entry.get("base")


def _pick_inverse_etf(entry: dict[str, str | None]) -> str | None:
    """Select inverse ETF ticker for the sector, or None if unavailable."""
    return entry.get("inverse")


# ---------------------------------------------------------------------------
# Alpha model
# ---------------------------------------------------------------------------

class VeraSectorEtfAlphaModel(AlphaModel):
    """
    Selects sector ETFs based on regime tier × sector RS ranking.

    Long book (tier > 0):
      Top ``sector_long_n`` sectors by avg RS → appropriate leverage tier.

    Short book (tier == 0):
      Bottom ``sector_short_n`` sectors by avg RS → inverse ETFs.
      Falls back to ``broad_inverse_etf`` (SPXS) when sector has no inverse.

    Position exits: emits Flat for any currently-held ETF not in the new selection.
    """

    def __init__(
        self,
        store: Any,
        sector_long_n: int = 4,
        sector_short_n: int = 3,
        broad_inverse_etf: str = "SPXS",
        etf_map: dict | None = None,
    ):
        self._store = store
        self._sector_long_n = int(sector_long_n)
        self._sector_short_n = int(sector_short_n)
        self._broad_inverse = broad_inverse_etf or "SPXS"
        self._etf_map: dict[str, dict[str, str | None]] = etf_map or DEFAULT_ETF_MAP
        self._all_etf_tickers: frozenset[str] = frozenset(
            sym
            for entry in self._etf_map.values()
            for sym in entry.values()
            if sym is not None
        ) | frozenset([self._broad_inverse])
        self._current_selections: set[str] = set()  # currently targeted long/inverse ETFs
        self._last_run_date = None
        self.Name = "VeraSectorEtfAlphaModel"

    def Update(self, algorithm, data):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []
        self._last_run_date = today

        as_of = (today - timedelta(days=1)).isoformat()

        # Regime tier drives leverage selection
        tier = self._store.get_regime_weekly_tier(as_of)
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)

        # Sector RS scores (computed from non-ETF stocks in screener)
        sector_rs = self._store.get_sector_rs_scores(as_of)
        if not sector_rs:
            algorithm.Debug(f"ETF ALPHA {as_of}: no sector RS data — holding current positions")
            return []

        ranked = sorted(sector_rs.items(), key=lambda x: x[1], reverse=True)

        new_selections: set[str] = set()
        insights: list = []

        if tier == 0:
            # Bear mode: inverse ETFs in weakest sectors
            bottom_sectors = [s for s, _ in ranked[-self._sector_short_n:]]
            algorithm.Debug(
                f"ETF ALPHA {as_of}: BEAR tier=0 | short sectors={bottom_sectors}"
            )
            for sector in bottom_sectors:
                entry = self._etf_map.get(sector, {})
                inv = _pick_inverse_etf(entry) or self._broad_inverse
                if inv:
                    new_selections.add(inv)

        else:
            # Bull mode: leveraged long ETFs in strongest sectors
            top_sectors = [s for s, _ in ranked[: self._sector_long_n]]
            algorithm.Debug(
                f"ETF ALPHA {as_of}: BULL tier={tier} alloc={alloc_fraction:.0%} "
                f"| long sectors={top_sectors}"
            )
            for sector in top_sectors:
                entry = self._etf_map.get(sector, {})
                sym = _pick_long_etf(tier, entry)
                if sym:
                    new_selections.add(sym)

        # Up = long leveraged ETF; Down = inverse ETF (still a long position, but tagged as hedge).
        period = timedelta(days=2)
        direction = InsightDirection.Down if tier == 0 else InsightDirection.Up
        for ticker in new_selections:
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not algorithm.Securities.ContainsKey(symbol):
                algorithm.Debug(f"ETF ALPHA {as_of}: {ticker} not in universe — skipping")
                continue
            insights.append(Insight.Price(symbol, period, direction))

        # Flat for ETFs that dropped out of the selection
        for ticker in self._current_selections - new_selections:
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if algorithm.Securities.ContainsKey(symbol) and algorithm.Portfolio[symbol].Invested:
                insights.append(Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat))

        self._current_selections = new_selections
        return insights


# ---------------------------------------------------------------------------
# Portfolio construction model
# ---------------------------------------------------------------------------

class VeraSectorEtfPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Regime-scaled equal-weight allocation across selected ETFs.

    Long budget  = weekly_allocation_fraction × max_long_exposure
    Inverse budget = max_inverse_exposure  (only active when tier == 0)
    Per-ETF weight = budget / num_selected (capped at max_weight_per_etf)
    """

    def __init__(
        self,
        store: Any,
        max_long_exposure: float = 0.90,
        max_inverse_exposure: float = 0.40,
        max_weight_per_etf: float = 0.30,
        min_weight: float = 0.05,
    ):
        self._store = store
        self._max_long = float(max_long_exposure)
        self._max_inverse = float(max_inverse_exposure)
        self._max_per_etf = float(max_weight_per_etf)
        self._min_weight = float(min_weight)

    def CreateTargets(self, algorithm, insights):
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        tier = self._store.get_regime_weekly_tier(as_of)
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)

        long_insights = [i for i in insights if i.Direction == InsightDirection.Up]
        inv_insights  = [i for i in insights if i.Direction == InsightDirection.Down]
        flat_insights = [i for i in insights if i.Direction == InsightDirection.Flat]

        targets = []
        flat_symbols = {i.Symbol for i in flat_insights}

        # Exit targets
        for ins in flat_insights:
            targets.append(PortfolioTarget(ins.Symbol, 0))

        if not long_insights and not inv_insights:
            for kv in algorithm.Portfolio:
                if kv.Value.Invested and kv.Key not in flat_symbols:
                    targets.append(PortfolioTarget(kv.Key, 0))
            return targets

        target_symbols: set = set()

        if long_insights:
            budget = self._max_long * alloc_fraction
            per_etf = min(self._max_per_etf, budget / len(long_insights))
            if per_etf >= self._min_weight:
                for ins in long_insights:
                    t = PortfolioTarget.Percent(algorithm, ins.Symbol, per_etf)
                    if t is not None:
                        targets.append(t)
                        target_symbols.add(ins.Symbol)
                algorithm.Debug(
                    f"ETF PCM: {len(long_insights)} long ETFs @ {per_etf:.1%} each "
                    f"(budget={budget:.0%} tier={tier})"
                )

        if inv_insights:
            budget = self._max_inverse
            per_etf = min(self._max_per_etf, budget / len(inv_insights))
            if per_etf >= self._min_weight:
                for ins in inv_insights:
                    t = PortfolioTarget.Percent(algorithm, ins.Symbol, per_etf)
                    if t is not None:
                        targets.append(t)
                        target_symbols.add(ins.Symbol)
                algorithm.Debug(
                    f"ETF PCM: {len(inv_insights)} inverse ETFs @ {per_etf:.1%} each "
                    f"(budget={budget:.0%})"
                )

        # Liquidate anything currently held that's not in the new target set
        for kv in algorithm.Portfolio:
            if kv.Value.Invested and kv.Key not in target_symbols and kv.Key not in flat_symbols:
                targets.append(PortfolioTarget(kv.Key, 0))

        return targets

    def OnSecuritiesChanged(self, algorithm, changes):
        pass
