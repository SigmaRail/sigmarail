"""studio domain: canonical navigation URLs (LLM-shareable)."""
from __future__ import annotations

from typing import Any

_SECTIONS = {"screens", "charts", "watchlists", "strategies", "backtests", "optimize", "deploy", "monitor"}
_VIEWS = {"overview", "trades", "attribution", "scrubber"}


def navigate(
    section: str,
    run_id: str | None = None,
    section_view: str | None = None,
    ticker: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Return the canonical React-Router URL for a Studio section/subview."""
    s = (section or "").strip().lower().lstrip("/")
    if s == "backtests" and run_id:
        view = (section_view or "overview").strip().lower()
        if view not in _VIEWS:
            raise ValueError(f"unknown backtest view {view!r}; known: {sorted(_VIEWS)}")
        url = f"/backtests/{run_id.strip()}/{view}"
    else:
        if s not in _SECTIONS:
            raise ValueError(f"unknown section {section!r}; known: {sorted(_SECTIONS)}")
        url = f"/{s}"

    query = [f"{k}={v}" for k, v in (("ticker", ticker), ("as_of", as_of)) if v]
    if query:
        url += "?" + "&".join(query)
    return {"url": url}
