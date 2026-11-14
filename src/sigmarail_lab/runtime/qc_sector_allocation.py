"""
Sector-aware, regime-scaled QC framework models.

``VeraSectorAlphaModel``
  Groups ``daily_screener`` rows by sector, computes per-sector avg RS rating,
  selects the top ``sector_top_n`` sectors, and emits Up insights for the top
  ``stocks_per_sector`` stocks within each qualifying sector.  Regime gate:
  ``weekly_allocation_fraction == 0`` → flat all equity; otherwise proceeds.

``VeraSectorPortfolioConstructionModel``
  Allocates total equity budget = ``weekly_allocation_fraction × max_total_exposure``.
  Within the budget, sectors are weighted proportionally to their RS rank score.
  Positions within each sector are ATR-sized (same logic as VeraScreenerPortfolioConstructionModel).

Both models tag each Insight with the sector name (``Insight.Tag``) so the PCM can
reconstruct per-sector budgets without a second lookup.

Runtime: Lean / QC container (AlgorithmImports).
"""

from __future__ import annotations

from datetime import timedelta

from AlgorithmImports import *  # noqa: F401,F403
from QuantConnect import Market, SecurityType, Symbol

from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget

from sigmarail_lab.runtime.sigmarail_screener_price_policy import mtm_price_for_holding


class VeraSectorAlphaModel(AlphaModel):
    """Top-N sector selection with regime gate and per-sector stock selection."""

    def __init__(
        self,
        store,
        sector_top_n: int = 4,
        stocks_per_sector: int = 5,
        min_hold_days: int = 5,
        stop_loss_pct: float = 0.08,
        stop_cooldown_days: int = 10,
        circuit_drawdown_threshold: float = 0.10,
        circuit_pause_days: int = 20,
    ):
        self._store = store
        self._sector_top_n = int(sector_top_n)
        self._stocks_per_sector = int(stocks_per_sector)
        self._min_hold_days = int(min_hold_days)
        self._stop_loss_pct = float(stop_loss_pct)
        self._stop_cooldown_days = int(stop_cooldown_days)
        self._circuit_drawdown_threshold = float(circuit_drawdown_threshold)
        self._circuit_pause_days = int(circuit_pause_days)
        self._entry_prices: dict[str, float] = {}
        self._stopped_out: dict[str, object] = {}
        self._portfolio_peak: float | None = None
        self._circuit_breaker_until = None
        self._last_run_date = None
        self._last_status_month = None
        self.Name = "VeraSectorAlphaModel"

    def _settled_portfolio_value(self, algorithm) -> float:
        cash = float(algorithm.Portfolio.Cash)
        pos_value = 0.0
        for kv in algorithm.Portfolio:
            if kv.Value.Invested:
                px = mtm_price_for_holding(algorithm, kv.Key, kv.Value)
                pos_value += abs(float(kv.Value.Quantity)) * px
        return cash + pos_value

    def _check_circuit_breaker(self, algorithm) -> bool:
        portfolio_value = self._settled_portfolio_value(algorithm)
        today = algorithm.Time.date()

        if self._circuit_breaker_until is not None and today > self._circuit_breaker_until:
            self._portfolio_peak = portfolio_value
            self._circuit_breaker_until = None

        if self._portfolio_peak is None or portfolio_value > self._portfolio_peak:
            self._portfolio_peak = portfolio_value

        if self._circuit_breaker_until is not None and today <= self._circuit_breaker_until:
            return True

        if self._portfolio_peak and self._portfolio_peak > 0:
            drawdown = (self._portfolio_peak - portfolio_value) / self._portfolio_peak
            month_key = (today.year, today.month)
            if self._last_status_month != month_key:
                self._last_status_month = month_key
                algorithm.Debug(
                    f"SECTOR-PORTFOLIO {today}: value=${portfolio_value:,.0f} "
                    f"peak=${self._portfolio_peak:,.0f} dd={drawdown:.1%}"
                )
            if drawdown >= self._circuit_drawdown_threshold:
                self._circuit_breaker_until = today + timedelta(days=self._circuit_pause_days)
                algorithm.Debug(
                    f"CIRCUIT BREAKER: {drawdown:.1%} drawdown → pause until {self._circuit_breaker_until}"
                )
                return True

        return False

    def Update(self, algorithm, data):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []
        self._last_run_date = today

        as_of = (today - timedelta(days=1)).isoformat()

        # Regime gate — zero allocation → exit all
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)
        if alloc_fraction < 1e-6:
            algorithm.Debug(f"SECTOR REGIME-OFF {as_of}: weekly_allocation_fraction=0 → flat all")
            return self._flat_all(algorithm)

        circuit_open = self._check_circuit_breaker(algorithm)

        # Stop-loss maintenance (runs regardless of circuit breaker)
        self._stopped_out = {t: d for t, d in self._stopped_out.items() if d > today}
        insights = []
        stop_exits: set[str] = set()

        for kv in algorithm.Portfolio:
            symbol = kv.Key
            ticker = symbol.Value
            if not kv.Value.Invested:
                self._entry_prices.pop(ticker, None)
                continue
            if ticker not in self._entry_prices:
                self._entry_prices[ticker] = float(kv.Value.AveragePrice)
            entry_px = self._entry_prices[ticker]
            current_px = (
                float(algorithm.Securities[symbol].Price)
                if algorithm.Securities.ContainsKey(symbol) else 0
            )
            if self._stop_loss_pct > 0 and current_px > 0 and entry_px > 0:
                dd = (entry_px - current_px) / entry_px
                if dd >= self._stop_loss_pct:
                    stop_exits.add(ticker)
                    cooldown_until = today + timedelta(days=self._stop_cooldown_days)
                    self._stopped_out[ticker] = cooldown_until
                    self._entry_prices.pop(ticker, None)
                    algorithm.Debug(
                        f"STOP-LOSS {ticker}: entry={entry_px:.2f} current={current_px:.2f} "
                        f"loss={dd:.1%} → cooldown until {cooldown_until}"
                    )
                    insights.append(Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat))

        if circuit_open:
            for kv in algorithm.Portfolio:
                sym = kv.Key
                if kv.Value.Invested and sym.Value not in stop_exits:
                    insights.append(Insight.Price(sym, timedelta(days=1), InsightDirection.Flat))
            return insights

        # Sector ranking
        sector_rs = self._store.get_sector_rs_scores(as_of)
        if not sector_rs:
            algorithm.Debug(f"SECTOR ALPHA {as_of}: no sector RS data (missing sector/rs_rating projection?)")
            return insights

        ranked_sectors = sorted(sector_rs.items(), key=lambda x: x[1], reverse=True)
        top_sectors = [s for s, _ in ranked_sectors[: self._sector_top_n]]
        top_sectors_set = set(top_sectors)
        algorithm.Debug(
            f"SECTOR RANKING {as_of}: top={top_sectors} | alloc={alloc_fraction:.0%}"
        )

        # Select stocks within top sectors
        sector_rows = self._store.get_sector_rows(as_of)
        selected: dict[str, tuple[str, float]] = {}  # ticker -> (sector, score)

        for sector in top_sectors:
            rows = sector_rows.get(sector, {})
            sorted_stocks = sorted(
                ((t, float(r.get("overall_score") or 0)) for t, r in rows.items()
                 if t not in self._stopped_out and t not in stop_exits),
                key=lambda x: x[1],
                reverse=True,
            )
            for ticker, score in sorted_stocks[: self._stocks_per_sector]:
                selected[ticker] = (sector, score)

        selected_set = set(selected)
        period = timedelta(days=self._min_hold_days)

        # Up insights for selected
        for ticker, (sector, score) in selected.items():
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not algorithm.Securities.ContainsKey(symbol):
                continue
            insights.append(
                Insight.Price(symbol, period, InsightDirection.Up, confidence=score / 100.0, tag=sector)
            )

        # Flat insights for positions that fell out of the top
        for kv in algorithm.Portfolio:
            sym = kv.Key
            ticker = sym.Value
            if kv.Value.Invested and ticker not in selected_set and ticker not in stop_exits:
                insights.append(Insight.Price(sym, timedelta(days=1), InsightDirection.Flat))

        return insights

    def _flat_all(self, algorithm) -> list:
        insights = []
        for kv in algorithm.Portfolio:
            if kv.Value.Invested:
                insights.append(
                    Insight.Price(kv.Key, timedelta(days=1), InsightDirection.Flat)
                )
        return insights


class VeraSectorPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Sector-bucketed, regime-scaled position sizing.

    Total equity budget = weekly_allocation_fraction × max_total_exposure.
    Sectors receive budget proportional to their RS rank (relative score within the top-N).
    Within each sector bucket, positions are ATR-sized up to their sector budget.
    """

    def __init__(
        self,
        store,
        sector_top_n: int = 4,
        stocks_per_sector: int = 5,
        max_total_exposure: float = 0.90,
        max_weight_per_stock: float = 0.12,
        min_weight: float = 0.02,
        target_atr_risk: float = 0.003,
    ):
        self._store = store
        self._sector_top_n = int(sector_top_n)
        self._stocks_per_sector = int(stocks_per_sector)
        self._max_total_exposure = float(max_total_exposure)
        self._max_weight_per_stock = float(max_weight_per_stock)
        self._min_weight = float(min_weight)
        self._target_atr_risk = float(target_atr_risk)

    def CreateTargets(self, algorithm, insights):
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()

        up_insights = [i for i in insights if i.Direction == InsightDirection.Up]
        flat_insights = [i for i in insights if i.Direction == InsightDirection.Flat]

        targets = []

        # Exit targets first
        flat_symbols = {i.Symbol for i in flat_insights}
        for insight in flat_insights:
            targets.append(PortfolioTarget(insight.Symbol, 0))

        if not up_insights:
            for kv in algorithm.Portfolio:
                if kv.Value.Invested and kv.Key not in flat_symbols:
                    targets.append(PortfolioTarget(kv.Key, 0))
            return targets

        # Regime scaling
        alloc_fraction = self._store.get_regime_weekly_fraction(as_of)
        total_budget = self._max_total_exposure * alloc_fraction

        # Group Up insights by sector (tag carries sector name)
        sector_insights: dict[str, list] = {}
        untagged: list = []
        for ins in up_insights:
            sector = getattr(ins, "Tag", None) or ""
            sector = str(sector).strip()
            if sector:
                sector_insights.setdefault(sector, []).append(ins)
            else:
                untagged.append(ins)

        # Compute sector RS scores to weight budgets proportionally
        sector_rs = self._store.get_sector_rs_scores(as_of)
        atrs = self._store.get_atrs(as_of)

        # Sort sectors by RS score, keep only those with insights
        active_sectors = sorted(
            [(s, sector_rs.get(s, 0.0)) for s in sector_insights],
            key=lambda x: x[1],
            reverse=True,
        )

        total_rs = sum(rs for _, rs in active_sectors) or 1.0
        sector_budgets = {s: (rs / total_rs) * total_budget for s, rs in active_sectors}

        # ATR-size within each sector budget
        for sector, ins_list in sector_insights.items():
            sector_budget = sector_budgets.get(sector, 0.0)
            if sector_budget < self._min_weight:
                continue
            ins_list.sort(key=lambda i: i.Confidence or 0.0, reverse=True)
            used = 0.0
            for ins in ins_list[: self._stocks_per_sector]:
                ticker = ins.Symbol.Value
                atr_pct = atrs.get(ticker)
                if atr_pct and atr_pct > 0:
                    weight = self._target_atr_risk / atr_pct
                else:
                    weight = sector_budget / len(ins_list)
                weight = max(self._min_weight, min(self._max_weight_per_stock, weight))
                weight = min(weight, sector_budget - used)
                if weight < self._min_weight:
                    break
                used += weight
                t = PortfolioTarget.Percent(algorithm, ins.Symbol, weight)
                if t is not None:
                    targets.append(t)

        # Fallback: untagged insights share remaining budget equally
        if untagged:
            per_pos = total_budget / (len(untagged) + 1)
            for ins in untagged:
                w = max(self._min_weight, min(self._max_weight_per_stock, per_pos))
                t = PortfolioTarget.Percent(algorithm, ins.Symbol, w)
                if t is not None:
                    targets.append(t)

        # Exit any invested positions not in the target set
        target_symbols = {t.Symbol for t in targets if getattr(t, "Quantity", 0) != 0}
        for kv in algorithm.Portfolio:
            if kv.Value.Invested and kv.Key not in target_symbols and kv.Key not in flat_symbols:
                targets.append(PortfolioTarget(kv.Key, 0))

        return targets

    def OnSecuritiesChanged(self, algorithm, changes):
        pass
