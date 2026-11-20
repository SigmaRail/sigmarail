"""RVAB sizing and balance-at-risk helpers (thin wrappers over CH views)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from vera.broker_trades.rules import DEFAULT_CONFIG, load_household_config, swing_account_id

DEFAULT_SLOT_WEIGHT = 0.165
DEFAULT_REFERENCE_RVAB = 1.0
DEFAULT_BAR_BUDGET_PCT = 0.08
CASH_TICKERS = frozenset({"SGOV", "SPAXX"})
SWING_STOPS_PATH = Path(__file__).resolve().parents[2] / "config" / "swing_stops.yaml"
FLAT_FIRST_POSITION_BASELINE = 25_000.0


def _rows_to_dicts(result: Any) -> list[dict[str, Any]]:
    cols = result.column_names
    return [dict(zip(cols, row)) for row in result.result_rows]


def load_swing_stops(path: Path | None = None) -> dict[str, float]:
    stops_path = path or SWING_STOPS_PATH
    if not stops_path.is_file():
        return {}
    raw = yaml.safe_load(stops_path.read_text(encoding="utf-8")) or {}
    out: dict[str, float] = {}
    for row in raw.get("stops") or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("ticker") or "").strip().upper()
        stop = row.get("stop_price")
        if sym and stop is not None:
            out[sym] = float(stop)
    return out


def get_swing_account_equity(client: Any, *, account_id: str | None = None) -> dict[str, Any]:
    aid = account_id or swing_account_id()
    if not aid:
        return {"error": "swing account not configured in household_accounts.yaml", "code": "config_missing"}
    row = client.query(
        """
        SELECT account_id, account_name, total_equity
        FROM broker_accounts_current
        WHERE account_id = {account_id:String}
        LIMIT 1
        """,
        parameters={"account_id": aid},
    ).first_item
    if not row:
        return {"error": f"swing account {aid} not found in broker_accounts_current", "code": "account_missing"}
    return {
        "account_id": row["account_id"],
        "account_name": row.get("account_name"),
        "swing_account_equity": float(row.get("total_equity") or 0),
    }


def compute_rvab_position_size(
    client: Any,
    *,
    ticker: str,
    as_of_date: str | None = None,
    slot_weight: float = DEFAULT_SLOT_WEIGHT,
    reference_rvab: float = DEFAULT_REFERENCE_RVAB,
    account_id: str | None = None,
) -> dict[str, Any]:
    sym = ticker.strip().upper()
    equity_info = get_swing_account_equity(client, account_id=account_id)
    if "error" in equity_info:
        return equity_info

    date_clause = "date = {as_of_date:Date}" if as_of_date else "date = (SELECT max(date) FROM screener_price_tech_daily)"
    params: dict[str, Any] = {"ticker": sym}
    if as_of_date:
        params["as_of_date"] = as_of_date

    row = client.query(
        f"""
        SELECT
            ticker,
            date,
            rvab_score,
            spy_atr_missing,
            closeadj,
            atr_14,
            factor_beta_mkt_252d
        FROM ticker_rvab_daily FINAL
        WHERE ticker = {{ticker:String}} AND {date_clause}
        LIMIT 1
        """,
        parameters=params,
    ).first_item

    if not row:
        return {"error": f"no ticker_rvab_daily row for {sym}", "code": "rvab_row_missing"}

    if row.get("spy_atr_missing"):
        return {
            "error": "SPY atr_14 missing or invalid for session — cannot size",
            "code": "spy_atr_missing",
            "ticker": sym,
            "date": row.get("date"),
        }

    rvab_score = row.get("rvab_score")
    if rvab_score is None or float(rvab_score) <= 0:
        return {
            "error": "rvab_score null or non-positive",
            "code": "rvab_invalid",
            "ticker": sym,
            "date": row.get("date"),
        }

    equity = float(equity_info["swing_account_equity"])
    score = float(rvab_score)
    ref = float(reference_rvab) if reference_rvab > 0 else DEFAULT_REFERENCE_RVAB
    base_dollars = equity * slot_weight
    suggested_dollars = base_dollars / (score / ref)
    closeadj = float(row.get("closeadj") or 0)
    suggested_shares = int(math.floor(suggested_dollars / closeadj)) if closeadj > 0 else 0

    return {
        "ticker": sym,
        "date": str(row.get("date")),
        "account_id": equity_info["account_id"],
        "swing_account_equity": round(equity, 2),
        "slot_weight": slot_weight,
        "reference_rvab": ref,
        "rvab_score": round(score, 4),
        "spy_atr_missing": bool(row.get("spy_atr_missing")),
        "base_dollars": round(base_dollars, 2),
        "suggested_dollars": round(suggested_dollars, 2),
        "suggested_shares": suggested_shares,
        "closeadj": closeadj,
        "flat_25k_baseline_dollars": FLAT_FIRST_POSITION_BASELINE,
        "vs_flat_25k_ratio": round(suggested_dollars / FLAT_FIRST_POSITION_BASELINE, 3)
        if FLAT_FIRST_POSITION_BASELINE
        else None,
    }


def compute_balance_at_risk(
    client: Any,
    *,
    account_id: str | None = None,
    bar_budget_pct: float = DEFAULT_BAR_BUDGET_PCT,
) -> dict[str, Any]:
    equity_info = get_swing_account_equity(client, account_id=account_id)
    if "error" in equity_info:
        return equity_info

    aid = equity_info["account_id"]
    equity = float(equity_info["swing_account_equity"])
    stops = load_swing_stops()

    positions = _rows_to_dicts(
        client.query(
            """
            SELECT trade_id, ticker, entry_qty, avg_entry, atr_stop_baseline, inferred_risk_dollars, stop_inferred
            FROM swing_bar_baseline
            WHERE account_id = {account_id:String}
            ORDER BY ticker
            """,
            parameters={"account_id": aid},
        )
    )

    lines: list[dict[str, Any]] = []
    total_bar = 0.0
    for pos in positions:
        sym = str(pos.get("ticker") or "").upper()
        if sym in CASH_TICKERS:
            continue
        qty = float(pos.get("entry_qty") or 0)
        entry = float(pos.get("avg_entry") or 0)
        stop = stops.get(sym)
        stop_inferred = stop is None
        if stop is None:
            baseline = pos.get("atr_stop_baseline")
            stop = float(baseline) if baseline is not None else None
        risk = 0.0
        if stop is not None and entry > 0 and qty > 0:
            risk = qty * max(entry - stop, 0)
        total_bar += risk
        lines.append(
            {
                "trade_id": pos.get("trade_id"),
                "ticker": sym,
                "entry_qty": qty,
                "avg_entry": entry,
                "stop_price": stop,
                "risk_dollars": round(risk, 2),
                "stop_inferred": stop_inferred,
            }
        )

    total_bar_pct = (total_bar / equity) if equity > 0 else 0.0
    return {
        "account_id": aid,
        "swing_account_equity": round(equity, 2),
        "positions": lines,
        "total_bar_dollars": round(total_bar, 2),
        "total_bar_pct": round(total_bar_pct, 4),
        "bar_budget_pct": bar_budget_pct,
        "over_budget": total_bar_pct > bar_budget_pct,
        "all_stops_inferred": bool(lines) and all(line["stop_inferred"] for line in lines),
        "approximate": bool(lines) and all(line["stop_inferred"] for line in lines),
    }
