"""portfolio domain: unified household status + RVAB / balance-at-risk sizing."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call


def status(
    scope: str = "household_yaml",
    account_id: str | None = None,
    book: str | None = None,
    include_cash_equivalents: bool = False,
    include_performance: bool = True,
    include_drift: bool = False,
) -> dict[str, Any]:
    from vera_query_core.portfolio_status import get_portfolio_status

    return call(
        get_portfolio_status,
        scope=scope,
        account_id=account_id,
        book=book,
        include_cash_equivalents=include_cash_equivalents,
        include_performance=include_performance,
        include_drift=include_drift,
    )


def household_summary() -> dict[str, Any]:
    from vera_query_core.broker_tools import get_household_broker_summary

    return call(get_household_broker_summary)


def rvab_position_size(
    ticker: str,
    as_of_date: str | None = None,
    slot_weight: float | None = None,
    reference_rvab: float | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    from vera_query_core.risk_sizing import compute_rvab_position_size

    kwargs: dict[str, Any] = {"ticker": ticker, "as_of_date": as_of_date, "account_id": account_id}
    if slot_weight is not None:
        kwargs["slot_weight"] = slot_weight
    if reference_rvab is not None:
        kwargs["reference_rvab"] = reference_rvab
    return call(compute_rvab_position_size, **kwargs)


def balance_at_risk(account_id: str | None = None, bar_budget_pct: float | None = None) -> dict[str, Any]:
    from vera_query_core.risk_sizing import compute_balance_at_risk

    kwargs: dict[str, Any] = {"account_id": account_id}
    if bar_budget_pct is not None:
        kwargs["bar_budget_pct"] = bar_budget_pct
    return call(compute_balance_at_risk, **kwargs)


def accounts(include_paper: bool = False, include_simulated: bool = False, execution_tier: str | None = None) -> dict[str, Any]:
    from vera_query_core.broker_tools import get_broker_accounts

    return call(get_broker_accounts, include_paper=include_paper, include_simulated=include_simulated, execution_tier=execution_tier)


def positions(
    account_id: str | None = None,
    include_paper: bool = False,
    include_simulated: bool = False,
    execution_tier: str | None = None,
    include_cash_equivalents: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    from vera_query_core.broker_tools import get_broker_positions

    return call(
        get_broker_positions,
        account_id=account_id,
        include_paper=include_paper,
        include_simulated=include_simulated,
        execution_tier=execution_tier,
        include_cash_equivalents=include_cash_equivalents,
        limit=limit,
    )


def trades(
    account_id: str | None = None,
    ticker: str | None = None,
    status: str = "closed",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from vera_query_core.broker_tools import get_broker_trades

    return call(
        get_broker_trades,
        account_id=account_id,
        ticker=ticker,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


def allocation_drift() -> dict[str, Any]:
    from vera_query_core.broker_tools import get_broker_allocation_drift

    return call(get_broker_allocation_drift)


def performance(account_id: str | None = None) -> dict[str, Any]:
    from vera_query_core.broker_tools import get_broker_performance

    return call(get_broker_performance, account_id=account_id)
