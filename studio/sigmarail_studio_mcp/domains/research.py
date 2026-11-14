"""research domain: KB narrative / timeline / anchored research (read side)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call


def narrative_search(
    query: str,
    ticker: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    from sigmarail.features.kb_search import kb_narrative_search

    return call(kb_narrative_search, query=query, ticker=ticker, date_from=date_from, date_to=date_to, limit=limit)


def sentiment_timeline(ticker: str, date_from: str | None = None, date_to: str | None = None, limit: int = 50) -> dict[str, Any]:
    from sigmarail.features.kb_search import kb_ticker_sentiment_timeline

    return call(kb_ticker_sentiment_timeline, ticker=ticker, date_from=date_from, date_to=date_to, limit=limit)


def context(ticker: str, as_of_date: str | None = None, narrative_query: str | None = None, narrative_limit: int = 5) -> dict[str, Any]:
    from sigmarail.features.kb_search import research_context

    return call(research_context, ticker=ticker, as_of_date=as_of_date, narrative_query=narrative_query, narrative_limit=narrative_limit)


def anchored_research(
    ticker: str,
    as_of_date: str,
    narrative_query: str | None = None,
    narrative_lookback_days: int = 90,
    narrative_limit: int = 5,
    include_regime: bool = True,
) -> dict[str, Any]:
    from sigmarail.features.kb_search import timeseries_anchored_research

    return call(
        timeseries_anchored_research,
        ticker=ticker,
        as_of_date=as_of_date,
        narrative_query=narrative_query,
        narrative_lookback_days=narrative_lookback_days,
        narrative_limit=narrative_limit,
        include_regime=include_regime,
    )


def influencer_index_posture(as_of_date: str, lookback_days: int = 2) -> dict[str, Any]:
    from sigmarail.features.kb_search import get_influencer_index_posture

    return call(get_influencer_index_posture, as_of_date=as_of_date, lookback_days=lookback_days)


def influencer_action_rollups(
    as_of_date: str,
    lookback_days: int = 2,
    action_types: list[str] | None = None,
    channel_slugs: list[str] | None = None,
    min_confidence: float = 0,
    limit: int = 100,
) -> dict[str, Any]:
    from sigmarail.features.kb_search import get_influencer_action_rollups

    return call(
        get_influencer_action_rollups,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
        action_types=action_types,
        channel_slugs=channel_slugs,
        min_confidence=min_confidence,
        limit=limit,
    )
