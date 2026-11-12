"""chart domain: TradingView + Vera price chart embeds."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call


def tv_embed(symbol: str, interval: str = "D", theme: str = "dark", height: int = 480, studies: list[str] | None = None) -> dict[str, Any]:
    from vera_query_core.tv_chart import tv_chart_embed_payload

    try:
        return tv_chart_embed_payload(symbol, interval=interval, theme=theme, height=height, studies=studies)
    except ValueError as exc:
        return {"error": str(exc), "code": "invalid_argument"}


def price_embed(ticker: str, lookback_days: int = 252, theme: str = "dark", height: int = 520, show_rsi: bool = True) -> dict[str, Any]:
    from vera_query_core.vera_price_chart import vera_price_chart_embed_payload

    return call(vera_price_chart_embed_payload, ticker=ticker, lookback_days=lookback_days, theme=theme, height=height, show_rsi=show_rsi)
