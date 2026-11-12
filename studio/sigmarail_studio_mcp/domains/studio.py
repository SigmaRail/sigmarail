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


def run_context(run_id: str, trades_limit: int = 50) -> dict[str, Any]:
    """Context-pack for one backtest run (report + closed trades + equity summary + spec + warnings)."""
    from screens.backtest import get_run_context
    from sigmarail_studio_mcp.ch import get_client

    if not run_id or not run_id.strip():
        return {"error": "run_id is required", "code": "invalid_argument"}
    client = get_client()
    try:
        return get_run_context(client, run_id.strip(), trades_limit=trades_limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()
