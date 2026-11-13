"""
Mark-to-market helpers for screener-backed strategies (no QuantConnect imports).

Equity OHLCV and ``Securities[].Price`` come from the Lean feed only. Python loads
universe metrics from ``daily_screener``, not duplicate bar series for pricing.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable


def _has_sec(algorithm: Any, symbol: Any) -> bool:
    if algorithm is None or getattr(algorithm, "Securities", None) is None:
        return False
    sec = algorithm.Securities
    if hasattr(sec, "ContainsKey"):
        return bool(sec.ContainsKey(symbol))
    return symbol in sec


def warn_missing_lean_prices(
    algorithm: Any,
    tickers: Iterable[str],
    *,
    resolve_symbol: Callable[[str], Any],
) -> None:
    """
    ``Debug`` once per ticker whose Lean ``Price`` is non-positive.

    ``resolve_symbol`` maps ticker string to the key used with ``algorithm.Securities``.
    """
    if algorithm is None:
        return
    for ticker in sorted(tickers):
        symbol = resolve_symbol(ticker)
        if not _has_sec(algorithm, symbol):
            continue
        sec = algorithm.Securities[symbol]
        if float(sec.Price) <= 0:
            algorithm.Debug(
                f"VeraScreenerExecutionModel: {ticker} Price=0 "
                f"(expect Lean feed / composite equity data)"
            )


def mtm_price_for_holding(algorithm: Any, symbol: Any, holding: Any) -> float:
    """Mark-to-market: ``Securities[symbol].Price``, then ``AveragePrice``."""
    if _has_sec(algorithm, symbol):
        p = float(getattr(algorithm.Securities[symbol], "Price", 0.0) or 0.0)
        if p > 0:
            return p
    ap = float(getattr(holding, "AveragePrice", 0.0) or 0.0)
    if ap > 0:
        return ap
    return 0.0
