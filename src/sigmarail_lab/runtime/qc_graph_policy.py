"""
Generic graph policy Alpha + PCM (Policy B if/weight tree).
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta
from typing import Any

from AlgorithmImports import *  # noqa: F401,F403
from QuantConnect import Market, SecurityType, Symbol

from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget

from sigmarail_lab.etf_rotation_state import (
    ALLOCATIONS,
    comparison_summary,
    prior_session_as_of,
)
from sigmarail_lab.ir.data_sources import DataSourceCatalog
from sigmarail_lab.ir.graph_policy_runtime import PolicyState, evaluate_graph
from sigmarail_lab.ir.models import GraphStep
from sigmarail_lab.ir.signal_context import signal_context_from_store


def _weekly_rebalance_enabled() -> bool:
    return (os.environ.get("SIGMARAIL_GRAPH_WEEKLY") or "").strip() in ("1", "true", "yes")


def _compare_enabled() -> bool:
    return (os.environ.get("SIGMARAIL_ETF_COMPARE") or "").strip() in ("1", "true", "yes")


def _regime_date_map(store: Any) -> dict[str, Any]:
    regime = getattr(store, "_regime", None)
    by_date = getattr(regime, "_by_date", None) if regime is not None else None
    return by_date if isinstance(by_date, dict) else {}


def _resolve_as_of(store: Any, today) -> str:
    by_date = _regime_date_map(store)
    if by_date:
        key = prior_session_as_of(by_date, today)
        if key:
            return key
    # Walk back via store.get_regime_row when map not exposed
    d = today - timedelta(days=1)
    for _ in range(10):
        key = d.isoformat()
        if store.get_regime_row(key) is not None:
            return key
        d -= timedelta(days=1)
    return (today - timedelta(days=1)).isoformat()


def _state_from_targets(targets: dict[str, float]) -> str | None:
    """Best-effort reverse map of weight vector → rotation state name."""
    rounded = {k: round(float(v), 4) for k, v in targets.items()}
    for name, weights in ALLOCATIONS.items():
        w = {k: round(float(v), 4) for k, v in weights.items()}
        if all(abs(rounded.get(t, 0.0) - w.get(t, 0.0)) < 1e-3 for t in set(w) | set(rounded)):
            return name
    return None


def _build_catalog_from_store(store: Any) -> DataSourceCatalog:
    """Build DataSourceCatalog from store's VeraBase data_sources if available."""
    catalog = DataSourceCatalog()
    # Check if store has attached data sources from VeraBase facet
    vera_base = getattr(store, "_vera_base", None)
    if vera_base is not None:
        data_sources = getattr(vera_base, "data_sources", None)
        if data_sources:
            for spec in data_sources:
                catalog.register(spec)
    return catalog


class VeraGraphPolicyAlphaModel(AlphaModel):
    def __init__(self, store: Any, **_: Any):
        self._store = store
        root = getattr(store, "_policy_graph_root", None)
        if root is None:
            raise ValueError("SigmaRailFrameworkStore.attach_policy_graph(root) required")
        self._root: GraphStep = root
        self._last_run_date = None
        self._last_iso_week = None
        self._targets: dict[str, float] = {}
        self._current_state: str | None = None
        self._transitions: list[tuple[str, str]] = []
        self._state_days: Counter = Counter()
        self._peak_equity = None
        self._max_dd = 0.0
        self.Name = "VeraGraphPolicyAlphaModel"

    def Update(self, algorithm, data):
        if getattr(algorithm, "IsWarmingUp", False):
            return []
        # Compare mode is driven only by main._daily_rebalance (Update(..., data=None)).
        # Ignore framework slice-driven Update to avoid double orders / buying-power errors.
        if _compare_enabled() and data is not None:
            return []
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []

        if _weekly_rebalance_enabled():
            iso = today.isocalendar()[:2]
            if self._last_iso_week == iso:
                return []
            self._last_iso_week = iso

        self._last_run_date = today
        as_of = _resolve_as_of(self._store, today)
        # Do not evaluate when regime row is missing (store defaults weekly frac→1.0).
        if self._store.get_regime_row(as_of) is None:
            algorithm.Debug(f"GRAPH POLICY {as_of}: no regime row, skip")
            return []
        catalog = _build_catalog_from_store(self._store)
        ctx = signal_context_from_store(self._store, as_of, catalog=catalog)
        # Debug: log regime values
        clamp = ctx.regime("clamp_risk_off")
        vix_spike = ctx.regime("vix_spike_flag", source="vix")
        vix_contango = ctx.regime("vix_contango_proxy", source="vix")
        breadth = ctx.regime("breadth_200d")
        dist = ctx.regime("distribution_count_25d")
        algorithm.Debug(f"GRAPH POLICY {as_of}: clamp={clamp} vix_spike={vix_spike} vix_contango={vix_contango} breadth={breadth} dist={dist}")
        state = PolicyState(current_weights=dict(self._targets))
        decision = evaluate_graph(self._root, ctx, state=state, algorithm=algorithm)
        algorithm.Debug(f"GRAPH POLICY {as_of}: decision targets={decision.targets} action={decision.action}")
        new_targets = dict(decision.targets)

        if _compare_enabled():
            self._track_compare(algorithm, as_of, new_targets)

        # State-change only: skip insights when weights unchanged
        if self._targets and all(
            abs(float(new_targets.get(t, 0.0)) - float(self._targets.get(t, 0.0))) < 1e-6
            for t in set(new_targets) | set(self._targets)
        ):
            algorithm.Debug(f"GRAPH POLICY {as_of}: unchanged targets={self._targets}")
            return []

        self._targets = new_targets

        # Compare mode: same SetHoldings batch semantics as Path1/2.
        if _compare_enabled():
            targets = []
            for ticker, weight in self._targets.items():
                sym = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
                if algorithm.Securities.ContainsKey(sym):
                    targets.append(PortfolioTarget(sym, float(weight)))
            if targets:
                algorithm.SetHoldings(targets, True)
            algorithm.Debug(f"GRAPH POLICY {as_of}: compare-allocated targets={self._targets}")
            return []

        insights = []
        for ticker, weight in self._targets.items():
            sym = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not algorithm.Securities.ContainsKey(sym):
                continue
            if weight <= 0:
                if algorithm.Portfolio[sym].Invested:
                    insights.append(
                        Insight.Price(sym, timedelta(days=1), InsightDirection.Flat)
                    )
            else:
                insights.append(Insight.Price(sym, timedelta(days=2), InsightDirection.Up))
        algorithm.Debug(f"GRAPH POLICY {as_of}: targets={self._targets}")
        return insights

    def _track_compare(self, algorithm, as_of: str, targets: dict[str, float]) -> None:
        eq = float(algorithm.Portfolio.TotalPortfolioValue)
        if self._peak_equity is None:
            self._peak_equity = eq
        if eq > self._peak_equity:
            self._peak_equity = eq
        if self._peak_equity > 0:
            dd = (self._peak_equity - eq) / self._peak_equity
            if dd > self._max_dd:
                self._max_dd = dd

        state_name = _state_from_targets(targets)
        if state_name is None:
            return
        self._state_days[state_name] += 1
        if state_name != self._current_state:
            self._transitions.append((as_of, state_name))
            self._current_state = state_name

        cash0 = float(algorithm.GetParameter("initial-cash") or 100_000)
        summary = comparison_summary(
            path="graph",
            final_equity=eq,
            initial_cash=cash0,
            n_state_transitions=len(self._transitions),
            state_day_histogram=dict(self._state_days),
            transitions=list(self._transitions),
            max_drawdown=self._max_dd,
        )
        algorithm._etf_compare_summary = summary


class VeraGraphPolicyPortfolioConstructionModel(PortfolioConstructionModel):
    def __init__(self, store: Any, **_: Any):
        self._store = store
        root = getattr(store, "_policy_graph_root", None)
        if root is None:
            raise ValueError("SigmaRailFrameworkStore.attach_policy_graph(root) required")
        self._root: GraphStep = root
        self._last_iso_week = None

    def CreateTargets(self, algorithm, insights):
        # Compare mode: Alpha.Update performs SetHoldings; do not emit PCM targets.
        if _compare_enabled():
            return []
        today = algorithm.Time.date()
        if _weekly_rebalance_enabled():
            iso = today.isocalendar()[:2]
            if self._last_iso_week == iso and not insights:
                return []
            self._last_iso_week = iso

        as_of = _resolve_as_of(self._store, today)
        catalog = _build_catalog_from_store(self._store)
        ctx = signal_context_from_store(self._store, as_of, catalog=catalog)
        current: dict[str, float] = {}
        for kv in algorithm.Portfolio:
            if kv.Value.Invested and algorithm.Portfolio.TotalPortfolioValue > 0:
                current[kv.Key.Value] = float(kv.Value.HoldingsValue) / float(
                    algorithm.Portfolio.TotalPortfolioValue
                )
        state = PolicyState(current_weights=current)
        decision = evaluate_graph(self._root, ctx, state=state, algorithm=algorithm)
        out = []
        for ticker, weight in decision.targets.items():
            sym = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if algorithm.Securities.ContainsKey(sym):
                out.append(PortfolioTarget.Percent(algorithm, sym, weight))
        return out
