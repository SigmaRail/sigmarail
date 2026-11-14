"""Bar-fetch schedule built from deterministic screen presence + bar requirements.

**NOT WIRED (2026-10-03).** Nothing in the runtime calls this module: `main.py` drives
`provider_bridge.prehydrate_tickers`, and the C# provider deliberately ignores the window
arguments it receives, hydrating the configured full range
(`Lean/Engine/DataFeeds/ClickHouseDataProvider.cs`, `PreHydrate` / `GetEffectiveRange`).
A bounded hydrate therefore needs a C#-side change *and* a data check before this can be
switched on. Until then this module is the specification of that change, not a live path.

The screener's universe rows are deterministic (precomputed), so each ticker's
screen-presence intervals are known at init. Combined with the strategy's
``BarRequirements`` (warm-up + worst-case hold), this yields the bounded
``[start, end]`` window the bar provider should fetch per ticker — instead of the
full backtest range.

Window formula (per presence span ``[entry, exit]``)::

    [entry - warmup_days, exit + max_hold_days]

- ``warmup_days`` pads *before* the earliest possible entry (indicator warm-up).
- ``max_hold_days`` pads *after* the latest possible entry (``exit``) so a
  position opened on the last screen day can still be trailed to its time stop.

Fixed universes pass one interval per ticker covering the whole range; rotating
universes pass one interval per presence span.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .bar_requirements import BarRequirements

TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365.25
# Calendar-day gap above which two presence dates are treated as separate spans.
_PRESENCE_GAP_TOLERANCE_DAYS = 5


@dataclass(frozen=True)
class FetchWindow:
    """A bounded bar-fetch window for one ticker (inclusive dates)."""

    ticker: str
    start: date
    end: date


def bars_to_calendar_days(bars: int) -> int:
    """Convert trading bars to a calendar-day pad (same convention as the provider)."""
    if bars <= 0:
        return 0
    return math.ceil(bars * CALENDAR_DAYS_PER_YEAR / TRADING_DAYS_PER_YEAR)


def fetch_windows_for_ticker(
    ticker: str,
    presence: list[tuple[date, date]],
    req: BarRequirements,
) -> list[FetchWindow]:
    """Windows for one ticker: each presence span + warm-up + worst-case hold."""
    warmup_days = bars_to_calendar_days(req.warmup_bars)
    windows: list[FetchWindow] = []
    for entry, exit_ in presence:
        windows.append(
            FetchWindow(
                ticker=ticker,
                start=entry - timedelta(days=warmup_days),
                end=exit_ + timedelta(days=req.max_hold_days),
            )
        )
    return _merge(windows)


def _merge(windows: list[FetchWindow]) -> list[FetchWindow]:
    """Merge overlapping/adjacent windows (sorted by start)."""
    if not windows:
        return []
    merged: list[FetchWindow] = []
    for w in sorted(windows, key=lambda w: (w.ticker, w.start, w.end)):
        if merged and merged[-1].ticker == w.ticker and w.start <= merged[-1].end:
            prev = merged[-1]
            merged[-1] = FetchWindow(w.ticker, prev.start, max(prev.end, w.end))
        else:
            merged.append(w)
    return merged


def build_fetch_schedule(
    presence: dict[str, list[tuple[date, date]]],
    req: BarRequirements,
) -> list[FetchWindow]:
    """All tickers' fetch windows (merged within each ticker), sorted by start."""
    out: list[FetchWindow] = []
    for ticker, intervals in presence.items():
        out.extend(fetch_windows_for_ticker(ticker, intervals, req))
    return sorted(out, key=lambda w: (w.start, w.ticker))


def group_by_start(windows: list[FetchWindow]) -> dict[date, list[FetchWindow]]:
    """Group windows by start date so the provider batches one ``PreHydrate`` per day."""
    grouped: dict[date, list[FetchWindow]] = {}
    for w in windows:
        grouped.setdefault(w.start, []).append(w)
    return grouped


def presence_intervals_from_dates(
    dates_by_ticker: dict[str, list[date]],
    *,
    gap_days: int = _PRESENCE_GAP_TOLERANCE_DAYS,
) -> dict[str, list[tuple[date, date]]]:
    """Group a ticker's presence dates into contiguous spans.

    Consecutive dates within ``gap_days`` calendar days are treated as one span
    (tolerates weekends/holidays); a larger gap splits into a new span.
    """
    out: dict[str, list[tuple[date, date]]] = {}
    for ticker, dates in dates_by_ticker.items():
        ds = sorted({d for d in dates})
        if not ds:
            continue
        intervals: list[tuple[date, date]] = []
        start = ds[0]
        prev = ds[0]
        for d in ds[1:]:
            if (d - prev).days > gap_days:
                intervals.append((start, prev))
                start = d
            prev = d
        intervals.append((start, prev))
        out[ticker] = intervals
    return out


def build_schedule_from_store(
    store,
    req: BarRequirements,
    *,
    always_include: Iterable[str] | None = None,
) -> list[FetchWindow]:
    """Build the fetch schedule from a ``SigmaRailDailyScreener``-backed store.

    The store exposes ``dates_by_ticker()`` (presence dates); this groups them
    into spans and applies the window formula.
    """
    dates_by_ticker = store.dates_by_ticker()
    parsed = {
        t: [datetime.strptime(d[:10], "%Y-%m-%d").date() for d in ds]
        for t, ds in dates_by_ticker.items()
    }
    if always_include:
        all_dates = [d for ds in parsed.values() for d in ds]
        if all_dates:
            min_d, max_d = min(all_dates), max(all_dates)
            for ticker in always_include:
                if ticker not in parsed:
                    parsed[ticker] = [min_d, max_d]
    return build_fetch_schedule(presence_intervals_from_dates(parsed), req)


def serialize_schedule(windows: list[FetchWindow]) -> list[dict]:
    """JSON-serializable form of a fetch schedule for the C# provider."""
    return [
        {"ticker": w.ticker, "start": w.start.isoformat(), "end": w.end.isoformat()}
        for w in windows
    ]
