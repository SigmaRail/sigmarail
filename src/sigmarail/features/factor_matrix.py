"""Multi-factor evaluation matrix (VeraProjects#78).

Evaluates a *set* of factor candidates in one pass — each rule is emitted as a
``(name, expression)`` pair and pivoted long inside the query via
``arrayJoin(map(...))``, so quantile stats, daily IC, coverage, and pairwise
score correlations come back already paired ``(rule, stat)`` — the shape the
ctx_gate v3 blend/gate derivations consume.

Differences from the single-factor evaluator (``alpha_evaluation``):

- **Population-mean baseline.** ``mean_active_spread`` is computed against the
  evaluated population's own daily mean forward return — filtered subsets
  benchmarked against the whole-tape EW universe read systematically negative.
  The EW-universe spread is kept as a second reported column.
- **Coverage per rule** — ``n_obs / pop_rows`` so sparse columns are visible.
- **Discrete factors bypass quantiles** — rules marked ``discrete`` evaluate
  by ``GROUP BY score`` value instead of ``ntile`` (ties make bucket ordering
  arbitrary).
- **Pairwise score-correlation matrix** via ``corrIf`` — redundancy verdicts
  (e.g. ``insight_dir`` vs ``mag_thrust``) fall out alongside the stats.

PIT contract identical to ``alpha_evaluation``: factor values at t, forward
returns strictly after t.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from sigmarail.features.alpha_evaluation import (
    _FORWARD_TABLE,
    _HORIZONS,
    _IDENT_RE,
    _POPULATIONS,
    _compile_factor_expr,
    _compile_spec_where,
    _factor_expr_tokens,
    _spec_bool,
    _spec_computed_aliases,
    _spec_from_clause,
    _table_columns,
    _table_exists,
    _table_to_prefix,
    _validate_date,
    _validate_ident,
)

_MAX_RULES = 50


def _normalize_factors(
    factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate the factor list; returns normalized dicts."""
    if not isinstance(factors, list) or not factors:
        raise ValueError("factors must be a non-empty list")
    if len(factors) > _MAX_RULES:
        raise ValueError(f"factors capped at {_MAX_RULES} per call, got {len(factors)}")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in factors:
        if not isinstance(f, dict):
            raise ValueError(f"factor must be a dict, got {f!r}")
        name = str(f.get("name") or "")
        if not _IDENT_RE.match(name):
            raise ValueError(f"factor name must be a bare identifier, got {name!r}")
        if name in seen:
            raise ValueError(f"duplicate factor name: {name!r}")
        seen.add(name)
        table = _validate_ident("factor table", str(f.get("table") or ""))
        col = f.get("column")
        expr = f.get("expr")
        if (col is None) == (expr is None):
            raise ValueError(
                f"factor {name!r}: exactly one of column or expr is required"
            )
        if col is not None:
            col = _validate_ident(f"factor {name!r} column", str(col))
        toks = _factor_expr_tokens(str(expr)) if expr is not None else None
        out.append(
            {
                "name": name,
                "table": table,
                "column": col,
                "expr": str(expr) if expr is not None else None,
                "toks": toks,
                "discrete": bool(f.get("discrete")),
            }
        )
    return out


def _all_mode_from_clause(
    factor_tables: list[str], base_table: str | None
) -> tuple[str, str, dict[str, str]]:
    """FROM clause for population='all': base table + LEFT ANY joins per table."""
    t2p = _table_to_prefix()
    base = base_table or factor_tables[0]
    _validate_ident("base_table", base)
    pa = t2p.get(base, "sp")
    aliases = {base: pa}
    parts = [f"{base} AS {pa} FINAL"]
    for i, tbl in enumerate(t for t in factor_tables if t != base):
        alias = t2p.get(tbl, f"j{i}")
        parts.append(
            f"LEFT ANY JOIN {tbl} AS {alias} "
            f"ON {alias}.ticker = {pa}.ticker AND {alias}.date = {pa}.date"
        )
        aliases[tbl] = alias
    return "\n            ".join(parts), pa, aliases


def _resolve_score_sql(
    client: Any,
    factor: dict[str, Any],
    table_aliases: dict[str, str],
    col_cache: dict[str, set[str]],
) -> str:
    """Qualified score SQL for one factor (column or validated expr)."""
    tbl = factor["table"]
    if tbl not in table_aliases:
        raise ValueError(f"factor {factor['name']!r}: table {tbl!r} not in FROM clause")
    alias = table_aliases[tbl]
    if tbl not in col_cache:
        col_cache[tbl] = _table_columns(client, tbl)
    cols = col_cache[tbl]
    if factor["column"] is not None:
        if factor["column"] not in cols:
            raise ValueError(
                f"factor {factor['name']!r}: column {factor['column']!r} not on {tbl}"
            )
        return f"{alias}.`{factor['column']}`"
    return _compile_factor_expr(factor["toks"], factor["expr"], cols, alias)


def evaluate_factor_matrix(
    client: Any,
    *,
    factors: list[dict[str, Any]],
    base_table: str | None = None,
    windows: list[dict[str, str]] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    quantiles: int = 10,
    horizon: Literal["5d", "21d"] = "5d",
    population: str = "all",
    universe_spec: dict | None = None,
) -> dict[str, Any]:
    """Evaluate a set of factor candidates against forward returns in one pass.

    Args:
        client: clickhouse-connect client.
        factors: list of ``{"name", "table", "column"|"expr", "discrete"?}``
            (max 50). ``expr`` follows the ``_compile_factor_expr`` whitelist.
        base_table: driving table for ``population='all'`` (defaults to the
            first factor's table); ignored when ``universe_spec`` is given.
        windows: list of ``{"label","start","end"}`` for split-window
            evaluation. Alternatively pass ``start_date``/``end_date`` for a
            single unnamed window.
        quantiles / horizon: as in ``evaluate_factor_performance``.
        population / universe_spec: as in ``evaluate_factor_performance``.

    Returns ``{"population", "horizon", "windows": {label: {...}}, ...}`` with
    per-window ``pop_rows``, ``quantiles``, ``by_value``, ``ic_stats``,
    ``correlations``, ``scales``.
    """
    norm = _normalize_factors(factors)
    if horizon not in _HORIZONS:
        raise ValueError(f"horizon must be one of {sorted(_HORIZONS)}, got {horizon!r}")
    if not (2 <= int(quantiles) <= 20):
        raise ValueError(f"quantiles must be in [2, 20], got {quantiles}")
    if population not in _POPULATIONS:
        raise ValueError(f"population must be one of {_POPULATIONS}, got {population!r}")
    if population == "all" and universe_spec is not None:
        raise ValueError("universe_spec requires population 'universe' or 'eligible'")
    if population != "all" and not isinstance(universe_spec, dict):
        raise ValueError(f"population {population!r} requires universe_spec")

    if windows is None:
        if not (start_date and end_date):
            raise ValueError("windows or start_date/end_date required")
        windows = [{"label": f"{start_date}..{end_date}", "start": start_date, "end": end_date}]
    windows = [
        {
            "label": w.get("label") or f"{w.get('start')}..{w.get('end')}",
            "start": _validate_date("window.start", str(w.get("start") or "")),
            "end": _validate_date("window.end", str(w.get("end") or "")),
        }
        for w in windows
    ]

    tables = sorted({f["table"] for f in norm})
    for t in tables:
        if not _table_exists(client, t):
            raise ValueError(f"missing factor table: {t}")
    if not _table_exists(client, _FORWARD_TABLE):
        raise ValueError(
            f"missing forward-return mart {_FORWARD_TABLE}; "
            "run transform 132 (vera-populate --metrics screener-forward-returns) first"
        )
    if universe_spec is None:
        from_sql, pa, table_aliases = _all_mode_from_clause(tables, base_table)
    else:
        # join every factor table that isn't already spine/declared
        spec_joins = {str(j.get("table")) for j in universe_spec.get("joins") or []}
        extra = [t for t in tables if t != universe_spec.get("spine") and t not in spec_joins]
        joined_spec = dict(universe_spec)
        joined_spec["joins"] = list(universe_spec.get("joins") or []) + [
            {"table": t, "type": "left_any", "on": ["ticker", "date"]} for t in extra
        ]
        from_sql, pa, table_aliases = _spec_from_clause(joined_spec, norm[0]["table"])

    scores: dict[str, str] = {}
    col_cache: dict[str, set[str]] = {}
    for f in norm:
        scores[f["name"]] = _resolve_score_sql(client, f, table_aliases, col_cache)
    discrete = {f["name"] for f in norm if f["discrete"]}
    continuous = [n for n in scores if n not in discrete]

    map_items = ", ".join(f"'{n}', toFloat64({sql})" for n, sql in scores.items())
    ret_col, ew_col = _HORIZONS[horizon]

    results: dict[str, Any] = {}
    for w in windows:
        params: dict[str, object] = {
            "start": w["start"],
            "end": w["end"],
            "q": int(quantiles),
        }
        filters = [f"{pa}.date BETWEEN toDate(%(start)s) AND toDate(%(end)s)"]
        if universe_spec is not None:
            where = universe_spec.get("where")
            if isinstance(where, dict):
                filters.append(f"({_compile_spec_where(where, params, 'uw_')})")
            if population == "eligible" and isinstance(universe_spec.get("post_where"), dict):
                computed = _spec_computed_aliases(universe_spec, params)
                filters.append(
                    f"({_spec_bool(universe_spec['post_where'], computed, params, 'pw_')})"
                )
        filters.append(f"isNotNull(fr.{ret_col})")
        filters.append(f"isNotNull(fr.{ew_col})")
        filter_sql = " AND ".join(f"({c})" for c in filters)

        # One joined+pivoted population per window; every metric reads it.
        pivoted = f"""
            SELECT f.date AS date, f.ticker AS ticker,
                   kv.1 AS rule, kv.2 AS score,
                   f.fwd_ret AS fwd_ret, f.ew_ret AS ew_ret, f.pop_ret AS pop_ret
            FROM (
                SELECT {pa}.ticker AS ticker, {pa}.date AS date,
                       toFloat64(fr.{ret_col}) AS fwd_ret,
                       toFloat64(fr.{ew_col}) AS ew_ret,
                       avg(toFloat64(fr.{ret_col})) OVER (PARTITION BY {pa}.date) AS pop_ret,
                       map({map_items}) AS pairs
                FROM {from_sql}
                INNER JOIN {_FORWARD_TABLE} fr FINAL
                    ON fr.ticker = {pa}.ticker AND fr.date = {pa}.date
                WHERE {filter_sql}
            ) f
            ARRAY JOIN f.pairs AS kv
            WHERE isFinite(kv.2)
        """

        pop_sql = f"""
            SELECT count()
            FROM {from_sql}
            INNER JOIN {_FORWARD_TABLE} fr FINAL
                ON fr.ticker = {pa}.ticker AND fr.date = {pa}.date
            WHERE {filter_sql}
        """
        pop_rows = int(
            client.query(pop_sql, parameters=params).result_rows[0][0]
        )

        # ---- quantile stats (continuous rules) --------------------------
        quantile_rows: list[dict[str, Any]] = []
        if continuous:
            rule_list = ", ".join(f"'{n}'" for n in continuous)
            qsql = f"""
                SELECT rule, bucket,
                       count() AS n_obs,
                       min(score) AS lo, max(score) AS hi,
                       avg(fwd_ret) AS mean_fwd_ret,
                       avg(pop_ret) AS mean_pop_ret,
                       avg(fwd_ret - pop_ret) AS mean_active_pop,
                       avg(fwd_ret - ew_ret) AS mean_active_ew,
                       avg(fwd_ret > pop_ret) AS hit_pop,
                       avg(fwd_ret > ew_ret) AS hit_ew,
                       countDistinct(date) AS n_days
                FROM (
                    SELECT date, ticker, rule, score, fwd_ret, ew_ret, pop_ret,
                           ntile(%(q)s) OVER (PARTITION BY date, rule ORDER BY score, ticker) AS bucket
                    FROM ({pivoted})
                    WHERE rule IN ({rule_list})
                )
                GROUP BY rule, bucket
                ORDER BY rule, bucket
            """
            for r in client.query(qsql, parameters=params).result_rows:
                quantile_rows.append(
                    {
                        "rule": r[0],
                        "bucket": int(r[1]),
                        "n_obs": int(r[2]),
                        "score_min": float(r[3]) if r[3] is not None else None,
                        "score_max": float(r[4]) if r[4] is not None else None,
                        "mean_fwd_ret": float(r[5]),
                        "mean_pop_ret": float(r[6]),
                        "mean_active_pop": float(r[7]),
                        "mean_active_ew": float(r[8]),
                        "hit_pop": float(r[9]),
                        "hit_ew": float(r[10]),
                        "n_days": int(r[11]),
                    }
                )

        if discrete:
            rule_list = ", ".join(f"'{n}'" for n in discrete)
            dsql = f"""
                SELECT rule, score AS value,
                       count() AS n_obs,
                       avg(fwd_ret) AS mean_fwd_ret,
                       avg(fwd_ret - pop_ret) AS mean_active_pop,
                       avg(fwd_ret - ew_ret) AS mean_active_ew,
                       avg(fwd_ret > pop_ret) AS hit_pop,
                       countDistinct(date) AS n_days
                FROM ({pivoted})
                WHERE rule IN ({rule_list})
                GROUP BY rule, value
                ORDER BY rule, value
            """
            by_value = [
                {
                    "rule": r[0],
                    "value": float(r[1]) if r[1] is not None else None,
                    "n_obs": int(r[2]),
                    "mean_fwd_ret": float(r[3]),
                    "mean_active_pop": float(r[4]),
                    "mean_active_ew": float(r[5]),
                    "hit_pop": float(r[6]),
                    "n_days": int(r[7]),
                }
                for r in client.query(dsql, parameters=params).result_rows
            ]
        else:
            by_value = []

        # ---- daily IC per rule ------------------------------------------
        icsql = f"""
            SELECT rule, date, corr(score_rank, ret_rank) AS ic
            FROM (
                SELECT date, ticker, rule, fwd_ret,
                       rank() OVER (PARTITION BY date, rule ORDER BY score, ticker) AS score_rank,
                       rank() OVER (PARTITION BY date, rule ORDER BY fwd_ret, ticker) AS ret_rank
                FROM ({pivoted})
            )
            GROUP BY rule, date
            HAVING count() > 2
            ORDER BY rule, date
        """
        ic_by_rule: dict[str, list[float]] = {}
        for r in client.query(icsql, parameters=params).result_rows:
            ic_by_rule.setdefault(str(r[0]), []).append(float(r[2]))
        ic_stats = {}
        for rule, vals in ic_by_rule.items():
            mean = sum(vals) / len(vals)
            std = (
                math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
                if len(vals) > 1
                else None
            )
            ic_stats[rule] = {
                "mean_ic": mean,
                "std_ic": std,
                "icir": (mean / std * math.sqrt(252.0)) if std and std > 0 else None,
                "n_days": len(vals),
            }

        # ---- pairwise score correlations (wide form, corrIf) -------------
        correlations: list[dict[str, Any]] = []
        if len(scores) > 1:
            names = list(scores)
            pair_cols = []
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    pair_cols.append(
                        f"corrIf({scores[names[i]]}, {scores[names[j]]}, "
                        f"isFinite({scores[names[i]]}) AND isFinite({scores[names[j]]})) AS c{i}_{j}"
                    )
            csql = f"""
                SELECT {pa}.date AS date, {', '.join(pair_cols)}
                FROM {from_sql}
                INNER JOIN {_FORWARD_TABLE} fr FINAL
                    ON fr.ticker = {pa}.ticker AND fr.date = {pa}.date
                WHERE {filter_sql}
                GROUP BY {pa}.date
            """
            sums: dict[tuple[str, str], list[float]] = {}
            for row in client.query(csql, parameters=params).result_rows:
                k = 1
                for i in range(len(names)):
                    for j in range(i + 1, len(names)):
                        v = row[k]
                        if v is not None:
                            sums.setdefault((names[i], names[j]), []).append(float(v))
                        k += 1
            correlations = [
                {"a": a, "b": b, "mean_corr": sum(v) / len(v), "n_days": len(v)}
                for (a, b), v in sorted(sums.items())
            ]

        # ---- scales (p95) -------------------------------------------------
        ssql = f"""
            SELECT rule, quantile(0.95)(score) AS p95
            FROM ({pivoted})
            GROUP BY rule
        """
        scales = {
            str(r[0]): (float(r[1]) if r[1] is not None else None)
            for r in client.query(ssql, parameters=params).result_rows
        }

        coverage: dict[str, float | None] = {}
        for name in scores:
            n = sum(
                q["n_obs"] for q in quantile_rows if q["rule"] == name
            ) or sum(v["n_obs"] for v in by_value if v["rule"] == name)
            coverage[name] = (n / pop_rows) if pop_rows else None

        results[str(w["label"])] = {
            "start_date": w["start"],
            "end_date": w["end"],
            "pop_rows": pop_rows,
            "coverage": coverage,
            "quantiles": quantile_rows,
            "by_value": by_value,
            "ic_stats": ic_stats,
            "correlations": correlations,
            "scales": scales,
        }

    # ---- derivations ------------------------------------------------------
    labels = list(results)
    keep: dict[str, dict[str, Any]] = {}
    for name in scores:
        stats = [results[l]["ic_stats"].get(name) for l in labels]
        stats = [s for s in stats if s and s.get("mean_ic") is not None]
        if len(stats) != len(labels) or not stats:
            keep[name] = {"kept": False, "reason": "missing IC in one or more windows"}
            continue
        same_sign = all(s["mean_ic"] * stats[0]["mean_ic"] > 0 for s in stats[1:])
        pos_icir = all((s["icir"] or 0) > 0 for s in stats)
        mono = None
        qs = [q for q in results[labels[0]]["quantiles"] if q["rule"] == name]
        if len(qs) >= 3:
            xs = [q["bucket"] for q in qs]
            ys = [q["mean_active_pop"] for q in qs]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = sum((x - mx) ** 2 for x in xs)
            vy = sum((y - my) ** 2 for y in ys)
            mono = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else None
        kept = same_sign and pos_icir and mono is not None and mono > 0
        keep[name] = {
            "kept": kept,
            "same_sign_ic": same_sign,
            "pos_icir": pos_icir,
            "monotonicity": mono,
            "icirs": {l: results[l]["ic_stats"].get(name, {}).get("icir") for l in labels},
        }
    total_icir = sum(
        (v["icirs"].get(labels[0]) or 0) for v in keep.values() if v["kept"]
    )
    for name, v in keep.items():
        if v["kept"]:
            v["weight"] = (
                (v["icirs"].get(labels[0]) or 0) / total_icir if total_icir > 0 else None
            )
            v["scale_p95"] = results[labels[0]]["scales"].get(name)

    # Mechanical gate-threshold evidence: the lowest bucket where the
    # population-demeaned spread is non-negative and stays non-negative for
    # every higher bucket. Reported as candidate cut points, not commitments.
    gate_thresholds: dict[str, dict[str, Any]] = {}
    for name in continuous:
        qs = sorted(
            (q for q in results[labels[0]]["quantiles"] if q["rule"] == name),
            key=lambda q: q["bucket"],
        )
        for i, q in enumerate(qs):
            if all(h["mean_active_pop"] >= 0 for h in qs[i:]):
                gate_thresholds[name] = {
                    "threshold_score": q["score_min"],
                    "from_bucket": q["bucket"],
                }
                break

    return {
        "population": population,
        "horizon": horizon,
        "quantiles_requested": int(quantiles),
        "factors": [
            {k: f[k] for k in ("name", "table", "column", "expr", "discrete")}
            for f in norm
        ],
        "windows": results,
        "derivations": {"blend": keep, "gate_thresholds": gate_thresholds},
    }
