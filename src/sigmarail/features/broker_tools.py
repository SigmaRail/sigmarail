"""MCP helpers for broker analytics (Layer 2)."""

from __future__ import annotations

from typing import Any

from vera.broker_trades.rules import load_household_config

_YAML_EXCLUDED_BOOKS = frozenset({"paper", "unused"})

_PRODUCTION_TIER = "execution_tier = 'production' AND account_source = 'snaptrade'"

_SUMMARY_TOTAL_KEYS = (
    "account_count",
    "total_equity",
    "total_cash",
    "cash_equivalent_value",
    "cash_and_equivalents",
    "invested_value",
    "open_pnl",
)


def _rows_to_dicts(result) -> list[dict[str, Any]]:
    cols = result.column_names
    return [dict(zip(cols, row)) for row in result.result_rows]


def _account_scope_clause(
    *,
    include_paper: bool = False,
    include_simulated: bool = False,
    execution_tier: str | None = None,
) -> str:
    if execution_tier:
        return f"execution_tier = '{execution_tier}'"
    if include_simulated and include_paper:
        return "execution_tier IN ('production', 'broker_paper', 'simulated')"
    if include_simulated:
        return "execution_tier IN ('production', 'simulated') AND account_source IN ('snaptrade', 'vera_internal')"
    if include_paper:
        return "execution_tier IN ('production', 'broker_paper') AND account_source = 'snaptrade'"
    return _PRODUCTION_TIER


def _book_maps(cfg) -> tuple[dict[str, str], set[str]]:
    """Return (account_id -> book, yaml production book ids)."""
    book_by_id = {a.snaptrade_id: a.book for a in cfg.accounts}
    yaml_prod_ids = {
        a.snaptrade_id
        for a in cfg.accounts
        if a.book not in _YAML_EXCLUDED_BOOKS
    }
    return book_by_id, yaml_prod_ids


def _rollup_accounts(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    if not accounts:
        return {key: 0 for key in _SUMMARY_TOTAL_KEYS}
    return {
        "account_count": len(accounts),
        "total_equity": round(sum(float(a.get("total_equity") or 0) for a in accounts), 2),
        "total_cash": round(sum(float(a.get("cash") or 0) for a in accounts), 2),
        "cash_equivalent_value": round(
            sum(float(a.get("cash_equivalent_market_value") or 0) for a in accounts), 2
        ),
        "cash_and_equivalents": round(
            sum(float(a.get("cash_and_equivalents") or 0) for a in accounts), 2
        ),
        "invested_value": round(
            sum(float(a.get("invested_market_value") or 0) for a in accounts), 2
        ),
        "open_pnl": round(sum(float(a.get("total_open_pnl") or 0) for a in accounts), 2),
    }


def _view_summary_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_count": int(row.get("production_account_count") or 0),
        "total_equity": float(row.get("production_total_equity") or 0),
        "total_cash": float(row.get("production_total_cash") or 0),
        "cash_equivalent_value": float(row.get("production_cash_equivalent_value") or 0),
        "cash_and_equivalents": float(row.get("production_cash_and_equivalents") or 0),
        "invested_value": float(row.get("production_invested_value") or 0),
        "open_pnl": float(row.get("production_open_pnl") or 0),
        "as_of_snapshot": row.get("as_of_snapshot"),
        "paper_account_count": int(row.get("paper_account_count") or 0),
    }


def get_household_broker_summary(client: Any) -> dict[str, Any]:
    cfg = load_household_config()
    book_by_id, yaml_prod_ids = _book_maps(cfg)

    view_row = client.query("SELECT * FROM broker_household_summary LIMIT 1").first_item or {}
    all_snaptrade = _view_summary_to_payload(view_row)

    account_rows = client.query(
        """
        SELECT
            account_id,
            institution_name,
            account_name,
            is_paper,
            total_equity,
            cash,
            cash_reported,
            cash_equivalent_market_value,
            cash_and_equivalents,
            invested_market_value,
            total_open_pnl
        FROM broker_accounts_current
        ORDER BY total_equity DESC
        """
    )
    prod_accounts: list[dict[str, Any]] = []
    yaml_accounts: list[dict[str, Any]] = []
    snaptrade_only_accounts: list[dict[str, Any]] = []

    for r in account_rows.result_rows:
        row = dict(zip(account_rows.column_names, r))
        if row.get("is_paper") != 0:
            continue
        if row.get("execution_tier") not in (None, "", "production"):
            continue
        if row.get("account_source") not in (None, "", "snaptrade"):
            continue
        row["book"] = book_by_id.get(row["account_id"], "unmapped")
        prod_accounts.append(row)
        if row["account_id"] in yaml_prod_ids:
            yaml_accounts.append(row)
        else:
            snaptrade_only_accounts.append(row)

    yaml_book = _rollup_accounts(yaml_accounts)
    yaml_book["as_of_snapshot"] = all_snaptrade.get("as_of_snapshot")

    missing = [name for name in cfg.expected_not_linked if name]
    not_in_yaml = [row["account_id"] for row in snaptrade_only_accounts]

    return {
        "all_snaptrade": all_snaptrade,
        "yaml_book": yaml_book,
        "summary": view_row,
        "accounts": prod_accounts,
        "yaml_accounts": yaml_accounts,
        "snaptrade_only_accounts": snaptrade_only_accounts,
        "expected_not_linked": missing,
        "accounts_missing_from_yaml": not_in_yaml,
    }


def get_broker_accounts(
    client: Any,
    *,
    include_paper: bool = False,
    include_simulated: bool = False,
    execution_tier: str | None = None,
) -> dict[str, Any]:
    scope = _account_scope_clause(
        include_paper=include_paper,
        include_simulated=include_simulated,
        execution_tier=execution_tier,
    )
    result = client.query(
        f"SELECT * FROM broker_accounts_current WHERE {scope} ORDER BY total_equity DESC"
    )
    return {"accounts": _rows_to_dicts(result), "count": len(result.result_rows)}


def get_broker_positions(
    client: Any,
    *,
    account_id: str | None = None,
    include_paper: bool = False,
    include_simulated: bool = False,
    execution_tier: str | None = None,
    include_cash_equivalents: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Latest positions per account from ``broker_positions_flat``."""
    if account_id and str(account_id).startswith("sim:"):
        include_simulated = True
    clauses = ["1"]
    params: dict[str, Any] = {"limit": max(1, min(int(limit), 5000))}
    clauses.append(_account_scope_clause(
        include_paper=include_paper,
        include_simulated=include_simulated,
        execution_tier=execution_tier,
    ))
    if account_id:
        clauses.append("account_id = {account_id:String}")
        params["account_id"] = account_id
    if not include_cash_equivalents:
        clauses.append("cash_equivalent = 0")
        clauses.append("ticker NOT IN ('', 'UNKNOWN', '__SIGMARAIL_EMPTY_SNAPSHOT__')")
    where = " AND ".join(clauses)
    q = f"""
        SELECT
            account_id,
            institution_name,
            account_name,
            is_paper,
            snapshot_at,
            ticker,
            description,
            units,
            price,
            average_purchase_price,
            open_pnl,
            market_value,
            cash_equivalent,
            updated_at
        FROM broker_positions_flat
        WHERE {where}
        ORDER BY market_value DESC
        LIMIT {{limit:UInt32}}
    """
    result = client.query(q, parameters=params)
    positions = _rows_to_dicts(result)
    as_of_snapshot = positions[0].get("snapshot_at") if positions else None
    return {
        "positions": positions,
        "count": len(positions),
        "as_of_snapshot": as_of_snapshot,
    }


def get_broker_trades(
    client: Any,
    *,
    account_id: str | None = None,
    ticker: str | None = None,
    status: str = "closed",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    view = "broker_trades_closed" if status.lower() == "closed" else "broker_trades_open"
    clauses = ["1"]
    params: dict[str, Any] = {"limit": limit}
    if account_id:
        clauses.append("account_id = {account_id:String}")
        params["account_id"] = account_id
    if ticker:
        clauses.append("ticker = {ticker:String}")
        params["ticker"] = ticker.upper()
    if date_from and status.lower() == "closed":
        clauses.append("toDate(close_time) >= {date_from:Date}")
        params["date_from"] = date_from
    if date_to and status.lower() == "closed":
        clauses.append("toDate(close_time) <= {date_to:Date}")
        params["date_to"] = date_to
    where = " AND ".join(clauses)
    q = f"SELECT * FROM {view} WHERE {where} ORDER BY open_time DESC LIMIT {{limit:UInt32}}"
    result = client.query(q, parameters=params)
    return {"trades": _rows_to_dicts(result), "count": len(result.result_rows), "view": view}


def get_broker_allocation_drift(client: Any) -> dict[str, Any]:
    sector = client.query("SELECT * FROM broker_vs_sector_targets ORDER BY abs(weight_drift) DESC")
    stock = client.query("SELECT * FROM broker_vs_stock_targets ORDER BY abs(weight_drift) DESC LIMIT 25")
    deploy = client.query("SELECT * FROM broker_household_deployment LIMIT 1")
    swing_bar = client.query("SELECT * FROM broker_swing_bar LIMIT 1")
    sso_interim = client.query("SELECT * FROM broker_swing_sso_interim LIMIT 1")
    return {
        "sector_drift": _rows_to_dicts(sector),
        "stock_drift": _rows_to_dicts(stock),
        "household_deployment": deploy.first_item,
        "swing_bar": swing_bar.first_item,
        "sso_interim": sso_interim.first_item,
    }


def get_broker_performance(client: Any, *, account_id: str | None = None) -> dict[str, Any]:
    where = "1"
    params: dict[str, Any] = {}
    if account_id:
        where = "account_id = {account_id:String}"
        params["account_id"] = account_id
    perf = client.query(f"SELECT * FROM broker_performance_summary WHERE {where}")
    returns = client.query(f"SELECT * FROM broker_returns_summary WHERE {where}")
    return {
        "performance": _rows_to_dicts(perf),
        "returns": _rows_to_dicts(returns),
    }
