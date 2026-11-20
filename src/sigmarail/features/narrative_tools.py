"""Soft narrative wrappers — only two legal consumption points for convergence.

``evaluate_narrative_convergence`` is INTERNAL (not MCP-registered).
MCP tools that may call it:
  - rank_candidates_for_selection — re-verifies entry gate first
  - regime_transition_weight — direction-split; identity outside zone
"""

from __future__ import annotations

from typing import Any

from .gate_tools import evaluate_entry_gate

# Fixed tag set for deterministic convergence counting (Tier A/B mentions).
_CONVERGENCE_TAGS = frozenset(
    {
        "chop",
        "do-less",
        "sit-out",
        "leadership-breakdown",
        "distribution",
        "extended",
        "wait",
        "waiting",
        "cautious",
        "constructive",
        "ftd",
        "follow-through",
        "thrust",
    }
)

_TIER_AB_CHANNELS = frozenset(
    {
        "ibdlive",
        "steve_jacobs",
        "Steve_Jacobs",
        "prime_trading_x",
        "prime_trading_24",
        "richard_moglen_x",
        "richard_moglen",
        "alpha_trends_x",
        "alpha_trends",
        "revere_asset_x",
        "revere_asset",
        "ariel_hernandez",
    }
)


def in_regime_transition_zone(client: Any, *, as_of_date: str) -> dict[str, Any]:
    """Ascending vs descending transition zone (Locked defaults #4).

    Gate closed → never in zone. Descending: weekly + 0 < streak < 3.
    Ascending: daily_promote / early_promote (± thrust suffixes).
    """
    gate = evaluate_entry_gate(client, as_of_date=as_of_date)
    if gate.get("gate") == "closed":
        return {
            "in_zone": False,
            "direction": None,
            "reason": "entry gate closed — transition zone inactive",
            "gate": gate,
        }
    fields = gate.get("fields") or {}
    source = str(fields.get("effective_source") or "")
    streak = int(fields.get("daily_demote_streak") or 0)

    ascending_prefixes = ("daily_promote", "early_promote")
    if any(source.startswith(p) for p in ascending_prefixes):
        return {
            "in_zone": True,
            "direction": "ascending",
            "reason": f"source={source} — narrative may weight entries",
            "gate": gate,
        }
    if source == "weekly" and 0 < streak < 3:
        return {
            "in_zone": True,
            "direction": "descending",
            "reason": f"weekly with demote streak {streak} — narrative may only de-risk",
            "gate": gate,
        }
    return {
        "in_zone": False,
        "direction": None,
        "reason": f"source={source} streak={streak} — outside named transition states",
        "gate": gate,
    }


def evaluate_narrative_convergence(
    client: Any,
    *,
    as_of_date: str,
    vera_signal: str = "ftd",
    lookback_days: int = 7,
) -> dict[str, Any]:
    """INTERNAL only — deterministic count over Tier A/B kb_mentions.

    Sparse KB → insufficient_coverage. Never mutates gate output.
    """
    d = (as_of_date or "").strip()[:10]
    if not d:
        raise ValueError("as_of_date is required")

    # Prefer kb_mentions with channel + evidence text when available.
    try:
        result = client.query(
            """
            SELECT channel, entity_value, evidence, sentiment_label
            FROM kb_mentions
            WHERE observed_date >= toDate(%(d)s) - %(lookback)s
              AND observed_date <= toDate(%(d)s)
            LIMIT 500
            """,
            parameters={"d": d, "lookback": int(lookback_days)},
        )
        rows = [dict(zip(result.column_names, r)) for r in result.result_rows]
    except Exception as e:  # noqa: BLE001 — soft layer must not break hard path
        return {
            "verdict": "insufficient_coverage",
            "vera_signal": vera_signal,
            "matching_mentions": [],
            "error": str(e),
            "note": "KB query failed — treat as insufficient_coverage",
        }

    matching: list[dict[str, Any]] = []
    for row in rows:
        channel = str(row.get("channel") or "")
        if channel and channel not in _TIER_AB_CHANNELS:
            continue
        blob = " ".join(
            str(row.get(k) or "").lower()
            for k in ("entity_value", "evidence", "sentiment_label")
        )
        tags = [t for t in _CONVERGENCE_TAGS if t in blob]
        if tags:
            matching.append(
                {
                    "channel": channel,
                    "tags": tags,
                    "entity_value": row.get("entity_value"),
                    "evidence": (str(row.get("evidence") or ""))[:240],
                }
            )

    if len(matching) < 2:
        verdict = "insufficient_coverage"
    else:
        # Heuristic: de-risk tags vs constructive tags.
        derisk = {"chop", "do-less", "sit-out", "leadership-breakdown", "distribution", "extended", "wait", "waiting", "cautious"}
        construct = {"constructive", "ftd", "follow-through", "thrust"}
        n_derisk = sum(1 for m in matching if set(m["tags"]) & derisk)
        n_construct = sum(1 for m in matching if set(m["tags"]) & construct)
        if abs(n_derisk - n_construct) < 1:
            verdict = "divergent"
        elif n_derisk > n_construct:
            verdict = "convergent" if vera_signal in ("demote", "closed", "cautious") else "divergent"
        else:
            verdict = "convergent" if vera_signal in ("ftd", "open", "constructive") else "divergent"

    return {
        "verdict": verdict,
        "vera_signal": vera_signal,
        "matching_mentions": matching[:20],
        "lookback_days": lookback_days,
        "as_of_date": d,
    }


def rank_candidates_for_selection(
    client: Any,
    *,
    passing_tickers: list[str],
    as_of_date: str,
) -> dict[str, Any]:
    """MCP: rank Vera-passed tickers. Refuses when entry gate is closed."""
    gate = evaluate_entry_gate(client, as_of_date=as_of_date)
    if gate.get("gate") == "closed":
        return {
            "error": "entry gate closed — refuse to rank",
            "code": "gate_closed",
            "gate": gate,
            "ranked": [],
        }

    tickers = [t.strip().upper() for t in (passing_tickers or []) if t and str(t).strip()]
    if not tickers:
        return {"gate": gate, "ranked": [], "note": "empty passing_tickers"}

    # Vera scores first (screener), convergence secondary.
    scores: dict[str, float] = {}
    try:
        result = client.query(
            """
            SELECT
                px.ticker AS ticker,
                rt.overall_score AS overall_score,
                rt.minervini_score AS minervini_score,
                px.rs_rating AS rs_rating
            FROM screener_price_tech_daily AS px FINAL
            LEFT ANY JOIN screener_ratings_daily AS rt FINAL
                ON px.ticker = rt.ticker AND px.date = rt.date
            WHERE px.date = (
                SELECT max(date) FROM screener_price_tech_daily WHERE date <= toDate(%(d)s)
            )
              AND px.ticker IN %(tickers)s
            """,
            parameters={"d": as_of_date[:10], "tickers": tickers},
        )
        for row in result.result_rows:
            rec = dict(zip(result.column_names, row))
            scores[str(rec["ticker"]).upper()] = float(rec.get("overall_score") or 0)
    except Exception:  # noqa: BLE001
        scores = {t: 0.0 for t in tickers}

    # Map gate state to soft signal for convergence pairing.
    vera_signal = "open" if gate.get("gate") == "open" else "cautious"
    conv = evaluate_narrative_convergence(
        client, as_of_date=as_of_date, vera_signal=vera_signal
    )
    conv_boost = 1.0 if conv.get("verdict") == "convergent" else 0.0

    ranked = sorted(
        (
            {
                "ticker": t,
                "vera_score": scores.get(t, 0.0),
                "convergence_boost": conv_boost,
                "rank_score": scores.get(t, 0.0) + conv_boost,
            }
            for t in tickers
        ),
        key=lambda r: (-r["rank_score"], r["ticker"]),
    )
    return {
        "gate": {"gate": gate.get("gate"), "hit_rules": gate.get("hit_rules"), "reason": gate.get("reason")},
        "convergence": {
            "verdict": conv.get("verdict"),
            "matching_count": len(conv.get("matching_mentions") or []),
        },
        "ranked": ranked,
        "note": "Vera screener scores primary; convergence is secondary tiebreak only",
    }


def regime_transition_weight(
    client: Any,
    *,
    as_of_date: str,
    base_weight: float = 1.0,
) -> dict[str, Any]:
    """MCP: direction-split weighting. Descending multipliers clamped ≤ 1.0."""
    zone = in_regime_transition_zone(client, as_of_date=as_of_date)
    if not zone.get("in_zone"):
        return {
            "weight": float(base_weight),
            "adjusted": False,
            "direction": None,
            "zone": zone,
            "note": "identity — outside transition zone",
        }

    direction = zone.get("direction")
    conv = evaluate_narrative_convergence(
        client,
        as_of_date=as_of_date,
        vera_signal="cautious" if direction == "descending" else "open",
    )
    w = float(base_weight)
    if direction == "ascending" and conv.get("verdict") == "convergent":
        w = min(w * 1.1, 1.25)
        adjusted = True
        note = "ascending + convergent — modest size/timing boost"
    elif direction == "descending":
        # Never increase aggression — multipliers clamped ≤ 1.0
        if conv.get("verdict") == "convergent":
            w = min(w * 0.75, 1.0)
            note = "descending + convergent derisk narrative — reduce size"
        else:
            w = min(w * 0.9, 1.0)
            note = "descending zone — de-risk only (no aggression increase)"
        adjusted = True
        assert w <= 1.0
    else:
        adjusted = False
        note = "ascending without convergent coverage — identity"

    return {
        "weight": round(w, 4),
        "adjusted": adjusted,
        "direction": direction,
        "zone": {"in_zone": True, "direction": direction, "reason": zone.get("reason")},
        "convergence_verdict": conv.get("verdict"),
        "note": note,
    }
