"""Unified portfolio status payload for MCP / REST."""

from __future__ import annotations

from typing import Any

from vera.broker_trades.rules import load_household_config
from sigmarail.features.broker_tools import (
    _YAML_EXCLUDED_BOOKS,
    _book_maps,
    _rollup_accounts,
    _view_summary_to_payload,
    get_broker_allocation_drift,
    get_broker_performance,
)
from sigmarail.features.risk_sizing import (
    CASH_TICKERS,
    DEFAULT_BAR_BUDGET_PCT,
    load_swing_stops,
)

SCHEMA_VERSION = 1
REVERE_TARGETS = {
    "stock_bar_pct_typical": "1.5–2.5%",
    "total_bar_pct_target": "5–8%",
    "portfolio_rvab_target": "~1.0",
    "total_bar_pct_max": DEFAULT_BAR_BUDGET_PCT,
}
RVAB_METHOD = "dollar_weighted_per_ticker_rvab_score"

_VALID_SCOPES = frozenset({"household_yaml", "all_production", "account_id", "book"})


def _rows_to_dicts(result: Any) -> list[dict[str, Any]]:
    cols = result.column_names
    return [dict(zip(cols, row)) for row in result.result_rows]


def _bar_semantics(book: str) -> str:
    return "swing_single" if book == "swing" else "etf_sector"


def _apply_stop_overrides(
    positions: list[dict[str, Any]],
    stops: dict[str, float],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pos in positions:
        row = dict(pos)
        sym = str(row.get("ticker") or "").upper()
        if sym in CASH_TICKERS:
            continue
        entry = row.get("entry_price")
        equity = float(row.get("account_equity") or 0)
        units = float(row.get("units") or 0)
        yaml_stop = stops.get(sym)
        if yaml_stop is not None:
            row["stop_price"] = float(yaml_stop)
            row["stop_inferred"] = False
            row["stop_source"] = "swing_stops_yaml"
        else:
            row["stop_source"] = "atr_inferred" if row.get("stop_inferred") else "unknown"
        stop = row.get("stop_price")
        risk = 0.0
        if entry is not None and stop is not None and units > 0:
            risk = units * max(float(entry) - float(stop), 0)
        row["risk_dollars"] = round(risk, 2)
        row["stock_bar_pct"] = round(risk / equity, 6) if equity > 0 else 0.0
        out.append(row)
    return out


def _aggregate_book_bar(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, dict[str, Any]] = {}
    for pos in positions:
        aid = str(pos.get("account_id") or "")
        if not aid:
            continue
        bucket = by_account.setdefault(
            aid,
            {
                "account_id": aid,
                "book": pos.get("book"),
                "institution_name": pos.get("institution_name"),
                "account_name": pos.get("account_name"),
                "account_equity": float(pos.get("account_equity") or 0),
                "total_bar_dollars": 0.0,
                "open_position_count": 0,
                "stop_inferred_count": 0,
            },
        )
        bucket["total_bar_dollars"] += float(pos.get("risk_dollars") or 0)
        bucket["open_position_count"] += 1
        if pos.get("stop_inferred"):
            bucket["stop_inferred_count"] += 1

    rows: list[dict[str, Any]] = []
    for bucket in by_account.values():
        equity = bucket["account_equity"]
        total_bar = bucket["total_bar_dollars"]
        total_bar_pct = (total_bar / equity) if equity > 0 else 0.0
        book = str(bucket.get("book") or "")
        rows.append(
            {
                **bucket,
                "total_bar_dollars": round(total_bar, 2),
                "total_bar_pct": round(total_bar_pct, 6),
                "bar_budget_pct": DEFAULT_BAR_BUDGET_PCT,
                "over_budget": total_bar_pct > DEFAULT_BAR_BUDGET_PCT,
                "bar_semantics": _bar_semantics(book),
            }
        )
    return sorted(rows, key=lambda r: (-float(r.get("account_equity") or 0), r.get("book") or ""))


def _rollup_by_book(
    bar_rows: list[dict[str, Any]],
    account_rows: list[dict[str, Any]],
    rvab_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for row in account_rows:
        book = str(row.get("book") or "unmapped")
        bucket = books.setdefault(
            book,
            {
                "book": book,
                "account_count": 0,
                "total_equity": 0.0,
                "invested_market_value": 0.0,
                "total_bar_dollars": 0.0,
                "open_position_count": 0,
                "stop_inferred_count": 0,
                "bar_semantics": _bar_semantics(book),
            },
        )
        bucket["account_count"] += 1
        bucket["total_equity"] += float(row.get("total_equity") or 0)
        bucket["invested_market_value"] += float(row.get("invested_market_value") or 0)

    for row in bar_rows:
        book = str(row.get("book") or "unmapped")
        bucket = books.setdefault(
            book,
            {
                "book": book,
                "account_count": 0,
                "total_equity": 0.0,
                "invested_market_value": 0.0,
                "total_bar_dollars": 0.0,
                "open_position_count": 0,
                "stop_inferred_count": 0,
                "bar_semantics": _bar_semantics(book),
            },
        )
        bucket["total_bar_dollars"] += float(row.get("total_bar_dollars") or 0)
        bucket["open_position_count"] += int(row.get("open_position_count") or 0)
        bucket["stop_inferred_count"] += int(row.get("stop_inferred_count") or 0)

    rvab_by_book: dict[str, list[tuple[float, float]]] = {}
    for row in rvab_rows:
        book = str(row.get("book") or "unmapped")
        rv = row.get("portfolio_rvab")
        mv = float(row.get("rvab_eligible_market_value") or 0)
        if rv is not None and mv > 0:
            rvab_by_book.setdefault(book, []).append((float(rv), mv))

    out: list[dict[str, Any]] = []
    for book, bucket in sorted(books.items()):
        equity = bucket["total_equity"]
        bar = bucket["total_bar_dollars"]
        pairs = rvab_by_book.get(book, [])
        if pairs:
            num = sum(rv * mv for rv, mv in pairs)
            den = sum(mv for _, mv in pairs)
            portfolio_rvab = num / den if den > 0 else None
        else:
            portfolio_rvab = None
        out.append(
            {
                "book": book,
                "account_count": bucket["account_count"],
                "total_equity": round(equity, 2),
                "invested_market_value": round(bucket["invested_market_value"], 2),
                "total_bar_dollars": round(bar, 2),
                "total_bar_pct": round(bar / equity, 6) if equity > 0 else 0.0,
                "bar_budget_pct": DEFAULT_BAR_BUDGET_PCT,
                "over_budget": (bar / equity > DEFAULT_BAR_BUDGET_PCT) if equity > 0 else False,
                "open_position_count": bucket["open_position_count"],
                "stop_inferred_count": bucket["stop_inferred_count"],
                "portfolio_rvab": round(portfolio_rvab, 4) if portfolio_rvab is not None else None,
                "bar_semantics": bucket["bar_semantics"],
            }
        )
    return out


def _household_exposure(
    book_bar_accounts: list[dict[str, Any]],
    account_rows: list[dict[str, Any]],
    household_equity: float,
    rvab_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total_bar = sum(float(r.get("total_bar_dollars") or 0) for r in book_bar_accounts)
    pairs = [
        (float(r["portfolio_rvab"]), float(r["rvab_eligible_market_value"]))
        for r in rvab_rows
        if r.get("portfolio_rvab") is not None and float(r.get("rvab_eligible_market_value") or 0) > 0
    ]
    if pairs:
        num = sum(rv * mv for rv, mv in pairs)
        den = sum(mv for _, mv in pairs)
        portfolio_rvab = num / den if den > 0 else None
    else:
        portfolio_rvab = None
    invested = sum(float(r.get("invested_market_value") or 0) for r in account_rows)
    return {
        "total_equity": round(household_equity, 2),
        "invested_market_value": round(invested, 2),
        "invested_pct": round(invested / household_equity, 6) if household_equity > 0 else 0.0,
        "total_bar_dollars": round(total_bar, 2),
        "total_bar_pct": round(total_bar / household_equity, 6) if household_equity > 0 else 0.0,
        "portfolio_rvab": round(portfolio_rvab, 4) if portfolio_rvab is not None else None,
    }


def _scope_account_ids(
    scope: str,
    *,
    account_id: str | None,
    book: str | None,
    yaml_prod_ids: set[str],
    book_by_id: dict[str, str],
) -> set[str] | None:
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}; expected one of {sorted(_VALID_SCOPES)}")
    if scope == "account_id":
        if not account_id:
            raise ValueError("account_id required when scope=account_id")
        return {account_id}
    if scope == "book":
        if not book:
            raise ValueError("book required when scope=book")
        return {aid for aid, b in book_by_id.items() if b == book and aid in yaml_prod_ids}
    if scope == "household_yaml":
        return yaml_prod_ids
    return None  # all_production


def _fetch_positions(
    client: Any,
    *,
    include_cash_equivalents: bool,
    account_ids: set[str] | None,
) -> list[dict[str, Any]]:
    clauses = [
        "execution_tier = 'production'",
        "account_source = 'snaptrade'",
    ]
    params: dict[str, Any] = {}
    if not include_cash_equivalents:
        clauses.append("cash_equivalent = 0")
        clauses.append("upper(ticker) NOT IN ('SGOV', 'SPAXX', 'FCASH')")
    if account_ids is not None:
        clauses.append("account_id IN {account_ids:Array(String)}")
        params["account_ids"] = sorted(account_ids)
    where = " AND ".join(clauses)
    result = client.query(
        f"SELECT * FROM broker_position_risk_enriched WHERE {where} ORDER BY market_value DESC",
        parameters=params,
    )
    return _rows_to_dicts(result)


def _fetch_sp_exposure(client: Any, account_ids: set[str] | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where = "1"
    if account_ids is not None:
        where = "account_id IN {account_ids:Array(String)}"
        params["account_ids"] = sorted(account_ids)
    result = client.query(
        f"SELECT * FROM broker_sp_exposure WHERE {where} ORDER BY book, sp_bucket",
        parameters=params,
    )
    return _rows_to_dicts(result)


def _fetch_portfolio_rvab(client: Any, account_ids: set[str] | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where = "1"
    if account_ids is not None:
        where = "account_id IN {account_ids:Array(String)}"
        params["account_ids"] = sorted(account_ids)
    result = client.query(
        f"SELECT * FROM broker_portfolio_rvab WHERE {where} ORDER BY book, account_id",
        parameters=params,
    )
    return _rows_to_dicts(result)


def get_portfolio_status(
    client: Any,
    *,
    scope: str = "household_yaml",
    account_id: str | None = None,
    book: str | None = None,
    include_cash_equivalents: bool = False,
    include_performance: bool = True,
    include_drift: bool = False,
) -> dict[str, Any]:
    """Return a single-shot household portfolio status payload."""
    cfg = load_household_config()
    book_by_id, yaml_prod_ids = _book_maps(cfg)
    scope_ids = _scope_account_ids(
        scope,
        account_id=account_id,
        book=book,
        yaml_prod_ids=yaml_prod_ids,
        book_by_id=book_by_id,
    )

    view_row = client.query("SELECT * FROM broker_household_summary LIMIT 1").first_item or {}
    all_snaptrade = _view_summary_to_payload(view_row)

    account_result = client.query(
        """
        SELECT
            acc.account_id,
            acc.institution_name,
            acc.account_name,
            acc.total_equity,
            acc.cash,
            acc.cash_equivalent_market_value,
            acc.cash_and_equivalents,
            acc.invested_market_value,
            acc.total_open_pnl,
            acc.position_count,
            acc.balance_snapshot_at,
            hab.book AS book,
            hab.group_trades AS group_trades
        FROM broker_accounts_current AS acc
        LEFT JOIN household_account_books AS hab FINAL ON hab.account_id = acc.account_id
        WHERE acc.execution_tier = 'production' AND acc.account_source = 'snaptrade'
        ORDER BY acc.total_equity DESC
        """
    )
    all_accounts = _rows_to_dicts(account_result)
    for row in all_accounts:
        row["book"] = row.get("book") or book_by_id.get(row["account_id"], "unmapped")

    if scope_ids is not None:
        accounts = [a for a in all_accounts if a["account_id"] in scope_ids]
    else:
        accounts = [a for a in all_accounts if a.get("book") not in _YAML_EXCLUDED_BOOKS]

    yaml_accounts = [a for a in all_accounts if a["account_id"] in yaml_prod_ids]
    yaml_book = _rollup_accounts(yaml_accounts)
    yaml_book["as_of_snapshot"] = all_snaptrade.get("as_of_snapshot")

    raw_positions = _fetch_positions(
        client,
        include_cash_equivalents=include_cash_equivalents,
        account_ids=scope_ids,
    )
    stops = load_swing_stops()
    positions = _apply_stop_overrides(raw_positions, stops)

    book_bar_accounts = _aggregate_book_bar(positions)
    # attach book to bar rows from accounts
    acct_book = {a["account_id"]: a.get("book") for a in accounts}
    acct_invested = {a["account_id"]: float(a.get("invested_market_value") or 0) for a in accounts}
    for row in book_bar_accounts:
        row["book"] = acct_book.get(row["account_id"], row.get("book"))
        row["invested_market_value"] = acct_invested.get(row["account_id"], 0.0)

    rvab_rows = _fetch_portfolio_rvab(client, scope_ids)
    sp_rows = _fetch_sp_exposure(client, scope_ids)

    # merge rvab onto account bar rows
    rvab_by_account = {r["account_id"]: r for r in rvab_rows}
    for row in book_bar_accounts:
        rv = rvab_by_account.get(row["account_id"])
        if rv:
            row["portfolio_rvab"] = rv.get("portfolio_rvab")
            row["rvab_eligible_market_value"] = rv.get("rvab_eligible_market_value")

    household_equity = float(yaml_book.get("total_equity") or 0) if scope == "household_yaml" else sum(
        float(a.get("total_equity") or 0) for a in accounts
    )

    spy_missing = any(bool(p.get("spy_atr_missing")) for p in positions)
    session_date = positions[0].get("session_date") if positions else None
    if session_date is None:
        sess = client.query(
            "SELECT max(date) AS session_date FROM screener_price_tech_daily"
        ).first_item
        session_date = sess.get("session_date") if sess else None

    missing_entry = [
        {"account_id": p["account_id"], "ticker": p["ticker"]}
        for p in positions
        if p.get("entry_source") == "missing"
    ]
    stop_inferred_count = sum(1 for p in positions if p.get("stop_inferred"))

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "as_of_snapshot": all_snaptrade.get("as_of_snapshot"),
            "session_date": str(session_date) if session_date is not None else None,
            "scope": scope,
            "rvab_method": RVAB_METHOD,
            "spy_atr_missing": spy_missing,
        },
        "household": {
            "all_snaptrade": all_snaptrade,
            "yaml_book": yaml_book,
        },
        "accounts": accounts,
        "positions": positions,
        "exposure": {
            "by_account": book_bar_accounts,
            "by_book": _rollup_by_book(book_bar_accounts, accounts, rvab_rows),
            "household": _household_exposure(book_bar_accounts, accounts, household_equity, rvab_rows),
            "sp_stack": sp_rows,
        },
        "revere_targets": REVERE_TARGETS,
        "gaps": {
            "expected_not_linked": [name for name in cfg.expected_not_linked if name],
            "stop_inferred_count": stop_inferred_count,
            "missing_avg_entry": missing_entry,
        },
    }

    if include_performance:
        payload["performance"] = get_broker_performance(client)
    if include_drift:
        payload["drift"] = get_broker_allocation_drift(client)

    return payload
