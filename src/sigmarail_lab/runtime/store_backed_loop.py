"""Store-backed daily loop: Alpha → PCM → Risk.ManageRisk → Execution.

Champion (and other VeraScreenerExecutionModel books) do not use Lean's default
insight pipeline. This helper is the single place that must call ManageRisk so
tranches, time-stop, ATR stops, and hedge actually run.
"""

from __future__ import annotations

from typing import Any


def fill_session_time_rule_kind(fill_session: str | None) -> str:
    """Schedule kind for store-backed rebalance. ``moo`` must not be AfterMarketOpen."""
    session = str(fill_session or "moo").strip().lower()
    if session == "moc":
        return "before_market_close"
    return "before_market_open"


def fill_session_minutes_before(fill_session: str | None) -> int:
    """Minutes before the open/close bell.

    ``TimeRules.BeforeMarketOpen(symbol, 0)`` is 09:30 — the open — which rejects
    Python ``market_on_open_order``. Same for ``BeforeMarketClose(0)`` and
    ``market_on_close_order``.
    """
    session = str(fill_session or "moo").strip().lower()
    if session == "moc":
        return 10
    return 30


def _symbol_key(symbol: Any) -> str:
    return str(getattr(symbol, "Value", symbol))


def merge_pcm_and_risk_targets(pcm_targets: list[Any] | None, risk_targets: list[Any] | None) -> list[Any]:
    """Union by ticker; risk overrides PCM for the same symbol."""
    by_sym: dict[str, Any] = {}
    for t in pcm_targets or []:
        if t is None:
            continue
        by_sym[_symbol_key(getattr(t, "Symbol", None))] = t
    for t in risk_targets or []:
        if t is None:
            continue
        by_sym[_symbol_key(getattr(t, "Symbol", None))] = t
    return list(by_sym.values())


def run_store_backed_rebalance(
    algorithm: Any,
    alpha: Any,
    pcm: Any,
    risk: Any,
    execution: Any,
) -> list[Any] | None:
    """One Alpha/PCM/Risk/Execute pass per calendar date.

    Runs ManageRisk even when Alpha emits no insights so open-position defense
    still fires. Returns merged targets (may be empty).
    """
    as_of_date = algorithm.Time.date()
    last = getattr(algorithm, "_vera_store_loop_date", None)
    if last == as_of_date:
        return None
    algorithm._vera_store_loop_date = as_of_date

    insights = []
    if alpha is not None:
        insights = alpha.Update(algorithm, None) or []
    targets = []
    if pcm is not None:
        targets = pcm.CreateTargets(algorithm, insights) or []
    risk_targets = []
    if risk is not None and hasattr(risk, "ManageRisk"):
        risk_targets = risk.ManageRisk(algorithm, targets) or []
    merged = merge_pcm_and_risk_targets(targets, risk_targets)
    if execution is not None and hasattr(execution, "Execute"):
        execution.Execute(algorithm, merged)
    return merged
