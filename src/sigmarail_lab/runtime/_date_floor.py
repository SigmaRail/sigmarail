"""Floor-resolution for date-keyed runtime caches.

``as_of`` is conventionally ``today - 1``. Non-trading days (weekends,
holidays) have no published row, so exact-match lookups read every Monday
and post-holiday session as "no data": Alpha saw an empty universe and the
regime context read fail-closed ``off`` — positions exited on stale regime
and entries silently died on Mondays.

The floor resolves ``as_of`` to the last loaded date at or before it — the
data a live session would actually have. Fail-closed semantics are
preserved before the first loaded date AND beyond ``MAX_GAP_DAYS`` of
staleness: a bound longer than any trading-calendar gap means a real data
outage still reads as missing (``missing_action="block"`` stays live in
the regime-gate evaluator).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

# Longest plausible gap between published trading-day rows. Thanksgiving
# (Wed→Mon) is ~5 calendar days; 7 covers every holiday cluster while a
# >1-week outage still resolves missing.
MAX_GAP_DAYS = 7


def _iso(d: str) -> date:
    return date.fromisoformat(d[:10])


def floor_key(
    dates: Iterable[str], as_of: str, *, max_gap_days: int = MAX_GAP_DAYS
) -> str | None:
    """Latest date in ``dates`` at or before ``as_of``, or None.

    ISO ``YYYY-MM-DD`` strings sort chronologically; callers pass either
    materialized iterables (dict keys — O(n)) or pre-sorted lists. A floor
    older than ``max_gap_days`` is treated as absent — that is an outage,
    not a weekend.
    """
    best: str | None = None
    for d in dates:
        if d <= as_of and (best is None or d > best):
            best = d
    if best is not None and (_iso(as_of) - _iso(best)).days > max_gap_days:
        return None
    return best


def floor_get(
    by_date: dict[str, Any], as_of: str, *, max_gap_days: int = MAX_GAP_DAYS
) -> Any:
    """``by_date[floor_key]`` — value at the last date <= ``as_of``."""
    d = floor_key(by_date, as_of, max_gap_days=max_gap_days)
    return by_date.get(d) if d is not None else None
