"""Attach Sharadar/CH exchange codes to preview rows for TradingView symbol resolution."""

from __future__ import annotations

from typing import Any


def enrich_rows_with_exchange(client: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set ``exchange`` on each row from ``tickers`` when missing."""
    if not rows:
        return rows
    need = [
        str(r.get("ticker") or "").upper()
        for r in rows
        if r.get("ticker") and not r.get("exchange")
    ]
    if not need:
        return rows
    # Dedupe preserve order
    seen: set[str] = set()
    tickers: list[str] = []
    for t in need:
        if t in seen:
            continue
        seen.add(t)
        tickers.append(t)
    try:
        result = client.query(
            """
            SELECT ticker, exchange
            FROM tickers FINAL
            WHERE ticker IN {tickers:Array(String)}
            """,
            parameters={"tickers": tickers},
        )
    except Exception:
        return rows
    by_ticker: dict[str, str] = {}
    for row in result.result_rows:
        t = str(row[0] or "").upper()
        ex = str(row[1] or "").strip()
        if t and ex:
            by_ticker[t] = ex
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if t and not r.get("exchange") and t in by_ticker:
            r["exchange"] = by_ticker[t]
    return rows
