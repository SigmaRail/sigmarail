"""regime domain: market regime + allocation + period comparison."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call


def market_regime(date: str) -> dict[str, Any]:
    from sigmarail.features.platform_tools import get_market_regime

    return call(get_market_regime, date=date)


def explain_allocation(date: str, policy_name: str | None = None, ticker: str = "SPY") -> dict[str, Any]:
    from sigmarail.features.platform_tools import explain_regime_allocation

    return call(explain_regime_allocation, date=date, policy_name=policy_name, ticker=ticker)


def compare_periods(
    focus_start: str,
    focus_end: str,
    reference_start: str,
    reference_end: str,
) -> dict[str, Any]:
    from sigmarail.features.platform_tools import compare_regime_periods

    return call(
        compare_regime_periods,
        focus_start=focus_start,
        focus_end=focus_end,
        reference_start=reference_start,
        reference_end=reference_end,
    )


def entry_gate(as_of_date: str) -> dict[str, Any]:
    from sigmarail.features.gate_tools import evaluate_entry_gate

    return call(evaluate_entry_gate, as_of_date=as_of_date)


def position_management(
    ticker: str,
    entry: float,
    stop: float,
    targets: list[float],
    as_of_date: str | None = None,
    action: str = "new",
    earnings_date: str | None = None,
) -> dict[str, Any]:
    from sigmarail.features.gate_tools import evaluate_position_management

    return call(
        evaluate_position_management,
        ticker=ticker,
        entry=entry,
        stop=stop,
        targets=targets,
        as_of_date=as_of_date,
        action=action,
        earnings_date=earnings_date,
    )


def rank_candidates(passing_tickers: list[str], as_of_date: str) -> dict[str, Any]:
    from sigmarail.features.narrative_tools import rank_candidates_for_selection

    return call(rank_candidates_for_selection, passing_tickers=passing_tickers, as_of_date=as_of_date)


def transition_weight(as_of_date: str, base_weight: float = 1.0) -> dict[str, Any]:
    from sigmarail.features.narrative_tools import regime_transition_weight

    return call(regime_transition_weight, as_of_date=as_of_date, base_weight=base_weight)
