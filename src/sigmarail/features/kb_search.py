"""Finance KB semantic + structured search via ClickHouse aiEmbed and kb_* tables."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any

_LM_STUDIO_COLLECTION = "lm_studio_kb"
_EMBED_DIM = 768


def _ch_embed_fn(client: Any) -> str | None:
    """Return SQL embed function name, or None if this ClickHouse build has no aiEmbed."""
    rows = client.query(
        "SELECT name FROM system.functions "
        "WHERE lower(name) IN ('aiembed', 'ai_embed') "
        "ORDER BY name LIMIT 1"
    )
    if rows.result_rows:
        return str(rows.result_rows[0][0])
    return None


def _set_ai_session(client: Any) -> None:
    client.command("SET allow_experimental_ai_functions = 1")


def _lm_studio_query_vector(query: str) -> list[float]:
    """Embed search query via LM Studio (same contract as kb-index)."""
    import httpx

    base = os.environ.get("LM_STUDIO_BASE", "http://127.0.0.1:1234/v1").rstrip("/")
    model = os.environ.get(
        "LM_STUDIO_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5"
    )
    text = (query or "").strip()
    if not text.startswith("search_query:"):
        text = f"search_query: {text}"
    with httpx.Client(timeout=60.0) as http:
        resp = http.post(
            f"{base}/embeddings",
            json={"model": model, "input": [text]},
        )
        resp.raise_for_status()
        data = resp.json()
    items = data.get("data") or []
    if not items:
        raise RuntimeError("LM Studio returned no embedding data")
    emb = items[0].get("embedding") or []
    if len(emb) != _EMBED_DIM:
        raise RuntimeError(f"expected {_EMBED_DIM}-dim query embedding, got {len(emb)}")
    return [float(x) for x in emb]


def _query_vector(client: Any, query: str) -> list[float]:
    embed_fn = _ch_embed_fn(client)
    if embed_fn:
        _set_ai_session(client)
        qtext = (query or "").strip()
        if not qtext.startswith("search_query:"):
            qtext = f"search_query: {qtext}"
        rows = client.query(
            f"SELECT {embed_fn}(%(collection)s, %(text)s) AS v",
            parameters={"collection": _LM_STUDIO_COLLECTION, "text": qtext},
        )
        return list(rows.result_rows[0][0])
    return _lm_studio_query_vector(query)


def _query_tokens(query: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]{2,}", query or "")][:32]


def kb_narrative_search(
    client: Any,
    *,
    query: str,
    ticker: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Full-text search over kb_documents.body_text with optional ticker/date filters."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 50))
    tokens = _query_tokens(q)

    params: dict[str, Any] = {"limit": limit, "tokens": tokens, "q": q}
    ticker_clause = ""
    if ticker and ticker.strip():
        params["ticker"] = ticker.strip().upper()
        ticker_clause = """
          AND d.doc_id IN (
            SELECT doc_id FROM kb_mentions FINAL
            WHERE entity_type = 'ticker' AND entity_value = %(ticker)s
          )
        """
    date_clause = ""
    if date_from and date_from.strip():
        params["date_from"] = date_from.strip()[:10]
        date_clause += " AND d.publish_date >= toDate(%(date_from)s)"
    if date_to and date_to.strip():
        params["date_to"] = date_to.strip()[:10]
        date_clause += " AND d.publish_date <= toDate(%(date_to)s)"

    text_clause = (
        "hasAnyTokens(d.body_text, %(tokens)s)"
        if tokens
        else "positionCaseInsensitive(d.body_text, %(q)s) > 0"
    )

    sql = f"""
        SELECT
            d.doc_id,
            0 AS chunk_index,
            substring(d.body_text, 1, 800) AS chunk_text,
            d.source_url,
            d.title,
            d.publish_date,
            d.sentiment,
            d.channel_slug,
            d.source_url AS doc_source_url,
            d.onedrive_url
        FROM kb_documents AS d FINAL
        WHERE d.body_text != ''
          AND {text_clause}
        {ticker_clause}
        {date_clause}
        ORDER BY d.publish_date DESC, d.doc_id
        LIMIT %(limit)s
    """
    try:
        rows = client.query(sql, parameters=params)
    except Exception:
        sql = f"""
            SELECT
                d.doc_id,
                0 AS chunk_index,
                substring(d.body_text, 1, 800) AS chunk_text,
                d.source_url,
                d.title,
                d.publish_date,
                d.sentiment,
                d.channel_slug,
                d.source_url AS doc_source_url,
                d.onedrive_url
            FROM kb_documents AS d FINAL
            WHERE d.body_text != ''
              AND positionCaseInsensitive(d.body_text, %(q)s) > 0
            {ticker_clause}
            {date_clause}
            ORDER BY d.publish_date DESC, d.doc_id
            LIMIT %(limit)s
        """
        rows = client.query(sql, parameters=params)

    hits = [dict(zip(rows.column_names, r)) for r in rows.result_rows]
    return {"query": q, "ticker": ticker, "limit": limit, "hits": hits, "count": len(hits)}


def kb_ticker_sentiment_timeline(
    client: Any,
    *,
    ticker: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Ticker mention timeline from kb_ticker_mentions_v1 (or kb_mentions fallback)."""
    sym = (ticker or "").strip().upper()
    if not sym:
        raise ValueError("ticker is required")
    limit = max(1, min(int(limit), 200))
    params: dict[str, Any] = {"ticker": sym, "limit": limit}
    date_clause = ""
    if date_from and date_from.strip():
        params["date_from"] = date_from.strip()[:10]
        date_clause += " AND observed_date >= toDate(%(date_from)s)"
    if date_to and date_to.strip():
        params["date_to"] = date_to.strip()[:10]
        date_clause += " AND observed_date <= toDate(%(date_to)s)"

    sql = f"""
        SELECT
            doc_id,
            ticker,
            ticker_sentiment,
            confidence,
            person,
            start_sec,
            chart_chosen_sec,
            chart_image_path,
            observed_at,
            observed_date,
            title,
            source_url,
            vault_relative_path,
            channel_slug,
            doc_sentiment
        FROM kb_ticker_mentions_v1
        WHERE ticker = %(ticker)s
        {date_clause}
        ORDER BY observed_at DESC
        LIMIT %(limit)s
    """
    try:
        rows = client.query(sql, parameters=params)
    except Exception:
        sql = f"""
            SELECT
                m.doc_id,
                m.entity_value AS ticker,
                m.ticker_sentiment,
                m.observed_at,
                d.title,
                d.source_url,
                d.channel_slug,
                d.sentiment AS doc_sentiment
            FROM kb_mentions AS m FINAL
            INNER JOIN kb_documents AS d FINAL ON d.doc_id = m.doc_id
            WHERE m.entity_type = 'ticker' AND m.entity_value = %(ticker)s
            {date_clause}
            ORDER BY m.observed_at DESC
            LIMIT %(limit)s
        """
        rows = client.query(sql, parameters=params)

    timeline = [dict(zip(rows.column_names, r)) for r in rows.result_rows]
    return {"ticker": sym, "timeline": timeline, "count": len(timeline)}


def research_context(
    client: Any,
    *,
    ticker: str,
    as_of_date: str | None = None,
    narrative_query: str | None = None,
    narrative_limit: int = 5,
) -> dict[str, Any]:
    """Composite: screener row + mention timeline + optional narrative search."""
    sym = (ticker or "").strip().upper()
    if not sym:
        raise ValueError("ticker is required")

    out: dict[str, Any] = {"ticker": sym}

    if as_of_date and as_of_date.strip():
        d = as_of_date.strip()[:10]
        screener = client.query(
            """
            SELECT
                px.ticker AS ticker,
                px.date AS date,
                rt.overall_score AS overall_score,
                px.rs_rating AS rs_rating,
                rt.classification AS classification,
                px.industry_group_rank AS industry_group_rank
            FROM screener_price_tech_daily AS px FINAL
            LEFT ANY JOIN screener_ratings_daily AS rt FINAL
                ON px.ticker = rt.ticker AND px.date = rt.date
            WHERE px.ticker = %(ticker)s AND px.date = toDate(%(d)s)
            LIMIT 1
            """,
            parameters={"ticker": sym, "d": d},
        )
        out["as_of_date"] = d
        out["screener"] = (
            dict(zip(screener.column_names, screener.result_rows[0]))
            if screener.result_rows
            else None
        )
        timeline = kb_ticker_sentiment_timeline(
            client, ticker=sym, date_from=None, date_to=d, limit=30
        )
    else:
        out["screener"] = None
        timeline = kb_ticker_sentiment_timeline(client, ticker=sym, limit=30)

    out["mention_timeline"] = timeline.get("timeline", [])

    nq = (narrative_query or "").strip() or f"{sym} outlook sentiment"
    try:
        out["narrative"] = kb_narrative_search(
            client,
            query=nq,
            ticker=sym,
            date_from=None,
            date_to=as_of_date,
            limit=narrative_limit,
        )
    except Exception as exc:
        out["narrative"] = {"error": str(exc), "query": nq}

    return out


def timeseries_anchored_research(
    client: Any,
    *,
    ticker: str,
    as_of_date: str,
    narrative_query: str | None = None,
    narrative_lookback_days: int = 90,
    narrative_limit: int = 5,
    include_regime: bool = True,
) -> dict[str, Any]:
    """Mandatory as_of_date: screener + KB timeline + windowed narrative + optional regime."""
    sym = (ticker or "").strip().upper()
    if not sym:
        raise ValueError("ticker is required")
    d = (as_of_date or "").strip()[:10]
    if not d:
        raise ValueError("as_of_date is required (YYYY-MM-DD)")

    lookback = max(1, min(int(narrative_lookback_days), 365))
    dt = datetime.strptime(d, "%Y-%m-%d")
    date_from = (dt - timedelta(days=lookback)).strftime("%Y-%m-%d")

    screener = client.query(
        """
        SELECT
            px.ticker AS ticker,
            px.date AS date,
            rt.overall_score AS overall_score,
            px.rs_rating AS rs_rating,
            rt.classification AS classification,
            px.industry_group_rank AS industry_group_rank
        FROM screener_price_tech_daily AS px FINAL
        LEFT ANY JOIN screener_ratings_daily AS rt FINAL
            ON px.ticker = rt.ticker AND px.date = rt.date
        WHERE px.ticker = %(ticker)s AND px.date = toDate(%(d)s)
        LIMIT 1
        """,
        parameters={"ticker": sym, "d": d},
    )
    timeline = kb_ticker_sentiment_timeline(
        client, ticker=sym, date_from=None, date_to=d, limit=30
    )
    out: dict[str, Any] = {
        "ticker": sym,
        "as_of_date": d,
        "screener": (
            dict(zip(screener.column_names, screener.result_rows[0]))
            if screener.result_rows
            else None
        ),
        "mention_timeline": timeline.get("timeline", []),
    }

    nq = (narrative_query or "").strip() or f"{sym} outlook sentiment"
    try:
        out["narrative"] = kb_narrative_search(
            client,
            query=nq,
            ticker=sym,
            date_from=date_from,
            date_to=d,
            limit=narrative_limit,
        )
    except Exception as exc:
        out["narrative"] = {"error": str(exc), "query": nq}

    out["narrative_window"] = {"date_from": date_from, "date_to": d, "lookback_days": lookback}

    if include_regime:
        try:
            from sigmarail.features.platform_tools import get_market_regime

            out["market_regime"] = get_market_regime(client, date=d)
        except Exception as exc:
            out["market_regime"] = {"error": str(exc)}

    return out


_INDEX_WATCH = frozenset({"SPY", "QQQ", "IWM", "DIA", "ES", "NQ", "RTY"})
_MAG7_WATCH = frozenset({"NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO"})
_WATCH_TICKERS = sorted(_INDEX_WATCH | _MAG7_WATCH)
_HARD_CONTEXT = re.compile(
    r"\b(short|trim|hedge|put|reduce|de-?risk|exit|sell|below|break|distribution|overextended)\b",
    re.I,
)
_MIN_ALERT_CONTEXT = 20


def _mention_context_quality(context: str) -> str:
    ctx = (context or "").strip()
    if not ctx:
        return "empty"
    if len(ctx) >= 40:
        return "high"
    if len(ctx) >= _MIN_ALERT_CONTEXT:
        return "medium"
    return "low"


def _is_hard_derisk(context: str, sentiment: str) -> bool:
    ctx = (context or "").strip()
    if _HARD_CONTEXT.search(ctx):
        return True
    # Bare bearish without actionable context is not hard de-risk.
    if str(sentiment or "").lower() == "bearish" and len(ctx) >= _MIN_ALERT_CONTEXT:
        return True
    return False


def _alert_eligible(context: str) -> bool:
    return _mention_context_quality(context) in ("high", "medium")

_CHANNEL_TIER: dict[str, str] = {
    "ibdlive": "A",
    "prime_trading": "A",
    "mark_ritchie": "A",
    "mark_ritchie_ii": "A",
    "mark_ritchie_x": "A",
    "alpha_trends": "B",
    "alpha_trends_x": "B",
    "alphatrends": "B",
    "brian_shannon": "B",
    "prime_report": "B",
}


def _channel_tier(channel_slug: str) -> str:
    slug = str(channel_slug or "").strip().lower()
    if not slug:
        return "C"
    if slug in _CHANNEL_TIER:
        return _CHANNEL_TIER[slug]
    if "ritchie" in slug or slug.startswith("prime_"):
        return "A"
    if slug.endswith("_x") or "shannon" in slug or "alphatrends" in slug:
        return "B"
    return "C"


def _symbol_class(symbol: str) -> str:
    sym = str(symbol or "").upper()
    if sym in _INDEX_WATCH:
        return "index"
    if sym in _MAG7_WATCH:
        return "mag7"
    return "other"


def get_influencer_index_posture(
    client: Any,
    *,
    as_of_date: str,
    lookback_days: int = 2,
) -> dict[str, Any]:
    """De-risking on indexes and Mag7 from kb_mentions + kb_sentiment_items (no extra tables)."""
    d = (as_of_date or "").strip()[:10]
    if not d:
        raise ValueError("as_of_date is required (YYYY-MM-DD)")
    lookback = max(1, min(int(lookback_days), 14))
    start = (datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=lookback - 1)).isoformat()

    mention_sql = """
        SELECT
            m.observed_date AS observed_date,
            d.channel_slug AS channel_slug,
            m.entity_value AS symbol,
            m.ticker_sentiment AS ticker_sentiment,
            m.confidence AS confidence,
            m.person AS person,
            m.mention_context AS mention_context,
            d.title AS title,
            d.source_url AS source_url,
            d.sentiment AS doc_sentiment,
            d.summary AS doc_summary,
            m.doc_id AS doc_id,
            'mention' AS source_kind
        FROM kb_mentions AS m FINAL
        INNER JOIN kb_documents AS d FINAL ON d.doc_id = m.doc_id
        WHERE m.entity_type = 'ticker'
          AND m.observed_date >= toDate(%(start)s)
          AND m.observed_date <= toDate(%(end)s)
          AND m.entity_value IN %(watch)s
          AND (
            m.ticker_sentiment IN ('bearish', 'mixed')
            OR positionCaseInsensitive(m.mention_context, 'short') > 0
            OR positionCaseInsensitive(m.mention_context, 'trim') > 0
            OR positionCaseInsensitive(m.mention_context, 'hedge') > 0
            OR positionCaseInsensitive(m.mention_context, 'put') > 0
            OR positionCaseInsensitive(m.mention_context, 'reduce') > 0
          )
        ORDER BY m.observed_at DESC
    """
    params: dict[str, Any] = {"start": start, "end": d, "watch": list(_WATCH_TICKERS)}
    rows = client.query(mention_sql, parameters=params)
    hits = [dict(zip(rows.column_names, r)) for r in rows.result_rows]

    sentiment_sql = """
        SELECT
            si.observed_date AS observed_date,
            d.channel_slug AS channel_slug,
            si.entity_value AS symbol,
            si.sentiment AS ticker_sentiment,
            si.confidence AS confidence,
            '' AS person,
            si.evidence_summary AS mention_context,
            d.title AS title,
            d.source_url AS source_url,
            d.sentiment AS doc_sentiment,
            d.summary AS doc_summary,
            si.doc_id AS doc_id,
            'sentiment_item' AS source_kind
        FROM kb_sentiment_items AS si FINAL
        INNER JOIN kb_documents AS d FINAL ON d.doc_id = si.doc_id
        WHERE si.observed_date >= toDate(%(start)s)
          AND si.observed_date <= toDate(%(end)s)
          AND si.sentiment IN ('cautious', 'negative', 'extended', 'mixed')
          AND (
            (si.scope = 'ticker' AND si.entity_value IN %(watch)s)
            OR (si.scope = 'market' AND si.time_context IN ('current', 'portfolio_update'))
          )
        ORDER BY si.observed_at DESC
    """
    try:
        si_rows = client.query(sentiment_sql, parameters=params)
        for r in si_rows.result_rows:
            hits.append(dict(zip(si_rows.column_names, r)))
    except Exception:
        pass

    actions: list[dict[str, Any]] = []
    for h in hits:
        sym = str(h.get("symbol") or "").upper()
        sym_class = _symbol_class(sym) if sym in _WATCH_TICKERS else (
            "market" if str(h.get("source_kind")) == "sentiment_item" and not sym else "other"
        )
        if sym_class not in {"index", "mag7", "market"}:
            continue
        ctx = str(h.get("mention_context") or "")
        sentiment = str(h.get("ticker_sentiment") or "")
        channel = str(h.get("channel_slug") or "")
        hard = _is_hard_derisk(ctx, sentiment)
        quality = _mention_context_quality(ctx)
        actions.append(
            {
                **h,
                "symbol_class": sym_class,
                "channel_tier": _channel_tier(channel),
                "hard_derisk": hard,
                "mention_quality": quality,
                "alert_eligible": _alert_eligible(ctx),
                "doc_summary": str(h.get("doc_summary") or "")[:400],
            }
        )

    alert_actions = [a for a in actions if a.get("alert_eligible")]
    channels = {str(a.get("channel_slug") or "") for a in alert_actions if a.get("channel_slug")}
    tier_a = {
        str(a.get("channel_slug") or "")
        for a in alert_actions
        if str(a.get("channel_tier") or "").upper() == "A" and a.get("channel_slug")
    }
    hard = [a for a in alert_actions if a.get("hard_derisk")]

    alert = False
    reasons: list[str] = []
    if len(channels) >= 3:
        alert = True
        reasons.append(f"{len(channels)} channels de-risking index/Mag7 in {lookback}d")
    elif len(channels) >= 2 and hard:
        alert = True
        reasons.append(f"{len(channels)} channels with explicit short/trim/hedge language")
    elif len(tier_a) >= 1 and len(channels) >= 2:
        alert = True
        reasons.append("Tier-A desk + second independent source")

    by_class: dict[str, dict[str, Any]] = {}
    for cls in ("index", "mag7", "market"):
        cls_rows = [a for a in alert_actions if str(a.get("symbol_class") or "") == cls]
        cls_channels = {str(a.get("channel_slug") or "") for a in cls_rows if a.get("channel_slug")}
        by_class[cls] = {
            "hits": len(cls_rows),
            "channels": sorted(c for c in cls_channels if c),
            "hard_derisk": sum(1 for a in cls_rows if a.get("hard_derisk")),
        }

    return {
        "as_of_date": d,
        "lookback_days": lookback,
        "window_start": start,
        "watch_tickers": list(_WATCH_TICKERS),
        "alert": alert,
        "alert_reasons": reasons,
        "summary": {
            "total_hits": len(actions),
            "alert_eligible_hits": len(alert_actions),
            "distinct_channels": len(channels),
            "tier_a_channels": len(tier_a),
            "hard_derisk_hits": len(hard),
            "index_hits": by_class.get("index", {}).get("hits", 0),
            "mag7_hits": by_class.get("mag7", {}).get("hits", 0),
        },
        "by_symbol_class": by_class,
        "hits": actions[:100],
    }


_TIER_AB_CHANNELS: frozenset[str] = frozenset(
    {
        "ibdlive",
        "Steve_Jacobs",
        "prime_trading_x",
        "prime_trading_24",
        "richard_moglen_x",
        "alpha_trends_x",
        "revere_asset",
        "revere_asset_x",
        "ted_hzhang_x",
        "connor_jbates_x",
        "dvandenbord_revere_x",
        "mark_minervini_x",
        "mark_ritchie_ii_x",
        "jfsrev_x",
    }
)


def get_influencer_action_rollups(
    client: Any,
    *,
    as_of_date: str,
    lookback_days: int = 2,
    action_types: list[str] | None = None,
    channel_slugs: list[str] | None = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> dict[str, Any]:
    """Merge ``kb_ticker_actions`` by (symbol, action_type) with influencer citations."""
    d = (as_of_date or "").strip()[:10]
    if not d:
        raise ValueError("as_of_date is required (YYYY-MM-DD)")
    lookback = max(1, min(int(lookback_days), 30))
    start = (datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=lookback - 1)).isoformat()
    channels = [c.strip() for c in (channel_slugs or []) if c.strip()]
    if not channels:
        channels = sorted(_TIER_AB_CHANNELS)
    actions = [a.strip().lower() for a in (action_types or []) if a.strip()]
    min_conf = max(0.0, min(float(min_confidence), 1.0))
    lim = max(1, min(int(limit), 500))

    sql = """
        SELECT
            a.entity_value AS symbol,
            a.action_type AS action_type,
            a.channel_slug AS channel_slug,
            a.list_class AS list_class,
            a.stance AS stance,
            a.evidence_summary AS evidence_summary,
            a.source_excerpt AS source_excerpt,
            a.person AS person,
            a.confidence AS confidence,
            a.mention_source AS mention_source,
            a.doc_id AS doc_id,
            a.observed_at AS observed_at,
            d.title AS title,
            d.source_url AS source_url,
            d.publish_date AS publish_date
        FROM kb_ticker_actions AS a FINAL
        LEFT JOIN kb_documents AS d FINAL ON d.doc_id = a.doc_id
        WHERE a.observed_date >= toDate(%(start)s)
          AND a.observed_date <= toDate(%(end)s)
          AND a.channel_slug IN %(channels)s
          AND a.confidence >= %(min_conf)s
    """
    params: dict[str, Any] = {
        "start": start,
        "end": d,
        "channels": channels,
        "min_conf": min_conf,
    }
    if actions:
        sql += " AND a.action_type IN %(actions)s"
        params["actions"] = actions
    sql += " ORDER BY a.observed_at DESC LIMIT 5000"

    try:
        rows = client.query(sql, parameters=params)
    except Exception as exc:
        return {
            "as_of_date": d,
            "lookback_days": lookback,
            "error": str(exc),
            "items": [],
        }

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows.result_rows:
        rec = dict(zip(rows.column_names, row))
        sym = str(rec.get("symbol") or "").upper()
        action = str(rec.get("action_type") or "watch").lower()
        if not sym:
            continue
        key = (sym, action)
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {
                "symbol": sym,
                "action_type": action,
                "source_count": 0,
                "channels": [],
                "why_parts": [],
                "max_confidence": 0.0,
                "latest_observed_at": "",
                "citations": [],
            }
            grouped[key] = bucket
        ch = str(rec.get("channel_slug") or "")
        if ch and ch not in bucket["channels"]:
            bucket["channels"].append(ch)
        excerpt = str(rec.get("source_excerpt") or rec.get("evidence_summary") or "").strip()
        if excerpt and excerpt not in bucket["why_parts"]:
            bucket["why_parts"].append(excerpt[:200])
        conf = float(rec.get("confidence") or 0.0)
        bucket["max_confidence"] = max(bucket["max_confidence"], conf)
        obs = str(rec.get("observed_at") or "")
        if obs > bucket["latest_observed_at"]:
            bucket["latest_observed_at"] = obs
        bucket["citations"].append(
            {
                "doc_id": str(rec.get("doc_id") or ""),
                "channel_slug": ch,
                "source_url": str(rec.get("source_url") or ""),
                "title": str(rec.get("title") or "")[:200],
                "excerpt": excerpt[:300],
                "mention_source": str(rec.get("mention_source") or ""),
                "confidence": conf,
            }
        )

    items: list[dict[str, Any]] = []
    for bucket in grouped.values():
        bucket["source_count"] = len(bucket["channels"])
        bucket["why"] = "; ".join(bucket.pop("why_parts")[:4])
        # dedupe citations by doc_id
        seen_docs: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for c in bucket["citations"]:
            did = str(c.get("doc_id") or "")
            if did and did in seen_docs:
                continue
            if did:
                seen_docs.add(did)
            deduped.append(c)
        bucket["citations"] = deduped[:8]
        items.append(bucket)

    items.sort(
        key=lambda x: (
            -int(x.get("source_count") or 0),
            -float(x.get("max_confidence") or 0.0),
        )
    )

    return {
        "as_of_date": d,
        "lookback_days": lookback,
        "window_start": start,
        "action_types": actions or ["all"],
        "channel_slugs": channels,
        "min_confidence": min_conf,
        "items": items[:lim],
    }
