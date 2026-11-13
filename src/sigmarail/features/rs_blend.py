"""Query-time RS blend scoring (VeraProjects#161).

A blend profile is a weighted sum of already-stored component percentiles in
``relative_strength_ranks`` — arbitrary profiles are a query-time operation,
no recompute, no schema break. Profiles register in ``rs_blend_profile``; ad
hoc weight maps are accepted as an alternative to registered profiles.

Component names in weight maps map to ranks columns:
    perf_1y -> yearly_pct, perf_6m -> performance_6m_pct,
    perf_3m -> performance_3m_pct, perf_1m -> performance_1m_pct

Missing policies:
    fallback_yearly — missing component value falls back to yearly_pct and its
        weight counts when either value exists (current transform-49 semantics;
        the ``legacy_40_20_20_20`` profile reproduces blended_pct byte-for-byte).
    renorm          — component contributes only when its pct is non-NULL.
    require_all     — blend is NULL unless every weighted component is non-NULL.

Score modes:
    blend_pct  — raw blended percentile in [0, 1]
    rerank_100 — percentile rerank of blends across the date cohort, scaled
        0-100 (rs_rating semantics; NULL blends excluded and rank last).
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence, Tuple

_COMPONENT_COLUMNS = {
    "perf_1y": "yearly_pct",
    "perf_6m": "performance_6m_pct",
    "perf_3m": "performance_3m_pct",
    "perf_1m": "performance_1m_pct",
    # #163 sub-period components — blend ingredients for recency-weighted
    # profiles (ibd_style ≈ {perf_q1:.2, perf_q2:.2, perf_q3:.2, perf_q4:.4}).
    "perf_9m": "performance_9m_pct",
    "perf_q1": "performance_q1_pct",
    "perf_q2": "performance_q2_pct",
    "perf_q3": "performance_q3_pct",
    "perf_q4": "performance_q4_pct",
}

_MISSING_POLICIES = {"fallback_yearly", "renorm", "require_all"}
_SCORE_MODES = {"blend_pct", "rerank_100"}


def _client(client=None):
    if client is not None:
        return client
    from vera.database import get_client

    return get_client()


def _fetch_profile(client, profile_id: str, version: Optional[int]) -> dict:
    """Latest registered definition for a profile_id (or a pinned version)."""
    where = "profile_id = %(p)s"
    params: dict[str, Any] = {"p": profile_id}
    if version is not None:
        where += " AND version = %(v)s"
        params["v"] = version
    res = client.query(
        f"""
        SELECT universe_id, component_weights, score_mode, missing_policy, version
        FROM rs_blend_profile FINAL
        WHERE {where}
        ORDER BY version DESC
        LIMIT 1
        """,
        parameters=params,
    )
    if not res.result_rows:
        raise KeyError(f"rs_blend_profile has no profile_id={profile_id!r}")
    universe_id, weights_json, score_mode, missing_policy, ver = res.result_rows[0]
    return {
        "profile_id": profile_id,
        "version": ver,
        "universe_id": universe_id,
        "component_weights": json.loads(weights_json),
        "score_mode": score_mode,
        "missing_policy": missing_policy,
    }


def _validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    out = {}
    for name, w in weights.items():
        if name not in _COMPONENT_COLUMNS:
            raise ValueError(
                f"unknown RS component {name!r}; valid: {sorted(_COMPONENT_COLUMNS)}"
            )
        w = float(w)
        if w < 0:
            raise ValueError(f"negative weight for {name!r}: {w}")
        if w > 0:
            out[name] = w
    if not out:
        raise ValueError("component_weights has no positive entries")
    return out


def _blend_expr(weights: Mapping[str, float], missing_policy: str) -> str:
    """SQL expression for the blended percentile given the policy."""
    yearly = _COMPONENT_COLUMNS["perf_1y"]
    terms, counts = [], []
    for name, w in weights.items():
        col = _COMPONENT_COLUMNS[name]
        if missing_policy == "require_all":
            terms.append(f"{w!r} * {col}")
            counts.append(None)
        elif missing_policy == "fallback_yearly" and name != "perf_1y":
            terms.append(f"{w!r} * coalesce({col}, {yearly}, 0.0)")
            counts.append(f"{w!r} * ({col} IS NOT NULL OR {yearly} IS NOT NULL)")
        else:  # renorm (and yearly under fallback_yearly)
            terms.append(f"{w!r} * coalesce({col}, 0.0)")
            counts.append(f"{w!r} * ({col} IS NOT NULL)")

    if missing_policy == "require_all":
        non_null = " AND ".join(
            f"{_COMPONENT_COLUMNS[n]} IS NOT NULL" for n in weights
        )
        total = " + ".join(f"{w!r}" for w in weights.values())
        return (
            f"if({non_null}, ({' + '.join(terms)}) / ({total}), NULL)"
        )
    return (
        f"({' + '.join(terms)}) / nullIf({' + '.join(counts)}, 0.0)"
    )


def rs_blend_scores(
    date,
    *,
    profile_id: Optional[str] = None,
    version: Optional[int] = None,
    weights: Optional[Mapping[str, float]] = None,
    missing_policy: Optional[str] = None,
    score_mode: Optional[str] = None,
    tickers: Optional[Sequence[str]] = None,
    client=None,
) -> list[Tuple[str, Optional[float], Optional[float]]]:
    """Score tickers for a date under a blend profile or ad-hoc weights.

    Returns [(ticker, blend, rating)] for every ranks row on the date (optionally
    restricted to ``tickers``): ``blend`` is the blended percentile [0,1] and
    ``rating`` depends on score_mode — the same value *100 for ``blend_pct``,
    or the cohort rerank for ``rerank_100`` (the rs_rating semantics).
    """
    client = _client(client)
    if profile_id is not None:
        prof = _fetch_profile(client, profile_id, version)
        weights = weights or prof["component_weights"]
        missing_policy = missing_policy or prof["missing_policy"]
        score_mode = score_mode or prof["score_mode"]
    if weights is None:
        raise ValueError("pass profile_id or weights")
    weights = _validate_weights(weights)
    missing_policy = missing_policy or "renorm"
    score_mode = score_mode or "blend_pct"
    if missing_policy not in _MISSING_POLICIES:
        raise ValueError(f"missing_policy must be one of {sorted(_MISSING_POLICIES)}")
    if score_mode not in _SCORE_MODES:
        raise ValueError(f"score_mode must be one of {sorted(_SCORE_MODES)}")

    blend = _blend_expr(weights, missing_policy)
    if score_mode == "rerank_100":
        rating = (
            "if(blend IS NULL, NULL, (row_number() OVER (ORDER BY blend ASC) - 1)"
            " / greatest(countIf(blend IS NOT NULL) OVER () - 1, 1) * 100)"
        )
    else:
        rating = "blend * 100"

    params: dict[str, Any] = {"d": date}
    ticker_filter = ""
    if tickers is not None:
        ticker_filter = " AND ticker IN %(t)s"
        params["t"] = tuple(tickers)
    res = client.query(
        f"""
        WITH scored AS (
            SELECT ticker, {blend} AS blend
            FROM relative_strength_ranks FINAL
            WHERE date = %(d)s{ticker_filter}
        )
        SELECT ticker, blend, {rating} AS rating
        FROM scored
        ORDER BY rating DESC NULLS LAST, ticker
        """,
        parameters=params,
    )
    return [(r[0], r[1], r[2]) for r in res.result_rows]
