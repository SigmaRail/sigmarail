"""Python → C# bar-provider bridge.

Bulk-loads Lean zip envelopes via ``ClickHouseDataProvider.PreHydrate`` using the
**full** configured backtest range (large ``IN (...)`` on ``daily_metrics``).
Window dates are ignored. ``Fetch`` is a cache hit / single-ticker fallback.
``Evict`` is a no-op so a still-invested name cannot lose bars.
"""

from __future__ import annotations

from typing import Any, Iterable

# C# PreHydrate also chunks internally; Python sends the full unique set in one call.
PREHYDRATE_CHUNK_SIZE = 2000


def _provider() -> Any | None:
    try:
        import clr  # noqa: F401
        clr.AddReference("QuantConnect.Lean.Engine")  # type: ignore[attr-defined]
        from QuantConnect.Lean.Engine.DataFeeds import ClickHouseDataProvider  # noqa: F401

        return ClickHouseDataProvider.Current
    except Exception:
        return None


def unique_tickers(tickers: Iterable[str | None]) -> list[str]:
    """Uppercased unique names, first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        if not raw:
            continue
        ticker = str(raw).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def chunk_tickers(tickers: list[str], size: int = PREHYDRATE_CHUNK_SIZE) -> list[list[str]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [tickers[i : i + size] for i in range(0, len(tickers), size)]


def tickers_from_schedule(schedule) -> list[str]:
    """Tickers from a windowed schedule; dates are discarded."""
    if not schedule:
        return []
    names: list[str | None] = []
    for window in schedule:
        names.append(getattr(window, "ticker", None))
    return unique_tickers(names)


def prehydrate_tickers(tickers: Iterable[str | None]) -> int:
    """Bulk PreHydrate unique tickers in one C# call. Returns unique count sent (0 if no CLR)."""
    names = unique_tickers(tickers)
    provider = _provider()
    if provider is None or not names:
        return 0 if provider is None else len(names)
    try:
        provider.PreHydrate(names)
    except Exception:
        pass
    return len(names)


def prehydrate_windows(schedule) -> None:
    """Compatibility wrapper: hydrate unique schedule tickers at full range."""
    prehydrate_tickers(tickers_from_schedule(schedule))


def evict(ticker: str) -> None:
    """No-op. Do not drop bars for a name that may still be invested."""
    return
