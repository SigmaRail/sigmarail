"""Pre-LEAN relative alpha performance evaluation (VeraProjects#70 / #72).

Scores a factor column against the active-universe equal-weighted benchmark
materialized in ``screener_forward_returns_daily`` (transform 132) — before any
LEAN compute is committed.

Metrics produced per evaluation:

- ``quantiles`` — cross-sectional buckets (per-date ``ntile`` over the scored
  universe) with mean forward return, mean active spread vs the EW universe,
  and hit rate (fraction of rows beating the universe mean).
- ``ic_stats`` — daily Spearman rank IC (Pearson corr of per-date ranks),
  std, and annualized ICIR = mean/std*sqrt(252). Ties use competition rank
  (``rank()``); continuous factor columns make this identical to average-rank
  Spearman in practice.
- ``regime_attribution`` — top-quantile active spread partitioned by
  ``market_regime_signals_daily.effective_allocation_fraction``
  (1.0 / 0.67 / 0.33 / 0.0; 'none' when no regime row exists; empty when the
  regime table is absent).
- ``monotonicity_score`` — Pearson corr between bucket index and bucket mean
  forward return (-1..+1; +1 = perfectly monotone).
- ``summary`` / ``verdict`` — headline numbers (top-bucket active spread,
  top-minus-bottom spread, EW universe mean) plus a coarse
  pass / fail / insufficient_data call. Diagnostic only — this is a
  screening aid, not a claim of true out-of-sample alpha.

PIT contract: factor values are read at signal date t; forward returns are
strictly after t (closeadj basis, transform 132). Nothing in this module reads
a same-day outcome.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

_FORWARD_TABLE = "screener_forward_returns_daily"
_REGIME_TABLE = "market_regime_signals_daily"
_HORIZONS: dict[str, tuple[str, str]] = {
    "5d": ("fwd_ret_5d", "ew_universe_ret_5d"),
    "21d": ("fwd_ret_21d", "ew_universe_ret_21d"),
}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ANN_FACTOR = 252.0

_POPULATIONS = ("all", "universe", "eligible")

# factor_expr whitelist contract (VeraProjects#77): a fixed character set — no
# quotes, semicolons, or comments — whitelisted scalar functions only, and every
# bare identifier must be a real column on the factor table.
_FACTOR_EXPR_CHARSET_RE = re.compile(r"^[A-Za-z0-9_+\-*/()., ]+$")
_FACTOR_EXPR_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FACTOR_EXPR_FNS = frozenset(
    {"abs", "sign", "greatest", "least", "max", "min", "log", "log1p", "round", "floor", "ceil"}
)

# ``{name:Type}`` placeholders emitted by compile_bool_expr_sql; folded into the
# client-side ``%(name)s`` binding used by this module's queries.
_EMITTED_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*):[^}]+\}")

_CMP_OPS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=", "neq": "<>"}
_SPEC_JOIN_TYPES = {"left_any": "LEFT ANY", "left": "LEFT", "inner": "INNER", "any": "ANY"}


def _table_to_prefix() -> dict[str, str]:
    from sigmarail.features.ir.vera_bool_expr import _PREFIX_TO_TABLE

    return {v: k for k, v in _PREFIX_TO_TABLE.items()}


def _validate_ident(name: str, value: str) -> str:
    if not _IDENT_RE.match(value or ""):
        raise ValueError(f"{name} must be a bare SQL identifier, got {value!r}")
    return value


def _validate_date(name: str, value: str) -> str:
    if not _DATE_RE.match(value or ""):
        raise ValueError(f"{name} must be ISO YYYY-MM-DD, got {value!r}")
    return value


def _table_exists(client: Any, table: str) -> bool:
    res = client.query(
        "SELECT count() FROM system.tables "
        "WHERE database = currentDatabase() AND name = %(t)s",
        parameters={"t": table},
    )
    return bool(res.result_rows and res.result_rows[0][0])


def _table_columns(client: Any, table: str) -> set[str]:
    res = client.query(
        "SELECT name FROM system.columns "
        "WHERE database = currentDatabase() AND table = %(t)s",
        parameters={"t": table},
    )
    return {str(r[0]) for r in res.result_rows}


def _factor_expr_tokens(expr: str) -> list[tuple[str, int, int, bool]]:
    """Phase-1 validation (no DB): charset + function whitelist.

    Returns ``(name, start, end, is_call)`` for every identifier so the caller
    can reject hostile or unsupported input before touching ``system.columns``.
    """
    if not _FACTOR_EXPR_CHARSET_RE.match(expr or ""):
        raise ValueError(
            "factor_expr may only contain [A-Za-z0-9_+-*/()., ] "
            f"(no quotes, semicolons, comments): {expr!r}"
        )
    for marker in ("--", "/*", "*/", "//"):
        if marker in expr:
            raise ValueError(f"factor_expr contains comment marker {marker!r}: {expr!r}")
    toks: list[tuple[str, int, int, bool]] = []
    for m in _FACTOR_EXPR_IDENT_RE.finditer(expr):
        name = m.group(0)
        is_call = expr[m.end() :].lstrip().startswith("(")
        if is_call and name.lower() not in _FACTOR_EXPR_FNS:
            raise ValueError(f"factor_expr function not whitelisted: {name!r}")
        toks.append((name, m.start(), m.end(), is_call))
    if not any(not t[3] for t in toks):
        raise ValueError("factor_expr must reference at least one factor-table column")
    return toks


def _compile_factor_expr(
    toks: list[tuple[str, int, int, bool]], expr: str, columns: set[str], alias: str
) -> str:
    """Qualify column identifiers in ``expr`` to ``{alias}.`name```.

    Every non-function identifier must be a real column on the factor table so
    the expression stays unambiguous under joins.
    """
    out: list[str] = []
    last = 0
    for name, start, end, is_call in toks:
        if is_call:
            continue
        if name not in columns:
            raise ValueError(
                f"factor_expr identifier {name!r} is not a column on the factor table"
            )
        out.append(expr[last:start])
        out.append(f"{alias}.`{name}`")
        last = end
    out.append(expr[last:])
    return "".join(out)


def _merge_emitted(sql: str, emitted: dict[str, object], params: dict[str, object]) -> str:
    """Fold a ``{name:Type}``-parameterized fragment into ``%(name)s`` bindings."""
    params.update(emitted)
    return _EMITTED_PARAM_RE.sub(lambda m: f"%({m.group(1)})s", sql)


def _compile_spec_where(node: dict, params: dict[str, object], pfx: str) -> str:
    from sigmarail_spec.expr import parse_bool_expr
    from sigmarail.features.ir.vera_bool_expr import compile_bool_expr_sql

    emitted: dict[str, object] = {}
    sql = compile_bool_expr_sql(parse_bool_expr(node), emitted, pfx)
    return _merge_emitted(sql, emitted, params)


def _refs_alias(node: object, aliases: dict[str, str]) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "col" and node.get("name") in aliases:
            return True
        return any(_refs_alias(v, aliases) for v in node.values())
    if isinstance(node, list):
        return any(_refs_alias(v, aliases) for v in node)
    return False


def _spec_operand(op: object, aliases: dict[str, str], params: dict[str, object], pfx: str) -> str:
    """Operand dict -> SQL; computed aliases inline to their emitted SQL."""
    if not isinstance(op, dict):
        raise ValueError(f"unsupported operand in universe_spec: {op!r}")
    t = op.get("type")
    if t == "col":
        name = str(op.get("name") or "")
        if name in aliases:
            return f"({aliases[name]})"
        from sigmarail.features.ir.vera_bool_expr import _col_sql

        return _col_sql(name)[0]
    if t == "lit":
        key = f"{pfx}lit"
        i = 0
        while f"{key}_{i}" in params:
            i += 1
        k = f"{key}_{i}"
        params[k] = op.get("value")
        return f"%({k})s"
    if t == "formula":
        args = op.get("args") or []
        if len(args) != 2:
            raise ValueError("formula operand requires exactly 2 args")
        left = _spec_operand(args[0], aliases, params, f"{pfx}fL_")
        right = _spec_operand(args[1], aliases, params, f"{pfx}fR_")
        return f"({left} {op['op']} {right})"
    raise ValueError(f"unsupported operand in universe_spec: {op!r}")


def _spec_bool(node: object, aliases: dict[str, str], params: dict[str, object], pfx: str) -> str:
    """Compile a spec-level bool tree, inlining computed aliases where they appear.

    Nodes that reference no computed alias delegate to the canonical emitter so
    the full dialect (col predicates, in_tickers, …) keeps working.
    """
    if not isinstance(node, dict):
        raise ValueError(f"unsupported node in universe_spec filter: {node!r}")
    t = node.get("type")
    if t == "all":
        items = node.get("items") or []
        if not items:
            return "1"
        return " AND ".join(
            f"({_spec_bool(x, aliases, params, f'{pfx}a{i}_')})" for i, x in enumerate(items)
        )
    if t == "any":
        items = node.get("items") or []
        if not items:
            return "0"
        return " OR ".join(
            f"({_spec_bool(x, aliases, params, f'{pfx}o{i}_')})" for i, x in enumerate(items)
        )
    if t == "not":
        return f"NOT ({_spec_bool(node.get('item'), aliases, params, pfx + 'n_')})"
    if t in _CMP_OPS and isinstance(node.get("left"), dict) and isinstance(node.get("right"), dict):
        left = _spec_operand(node["left"], aliases, params, f"{pfx}L_")
        right = _spec_operand(node["right"], aliases, params, f"{pfx}R_")
        return f"{left} {_CMP_OPS[t]} {right}"
    if not _refs_alias(node, aliases):
        return _compile_spec_where(node, params, f"{pfx}c_")
    raise ValueError(f"unsupported node in universe_spec filter: {node!r}")


def _spec_computed_aliases(spec: dict, params: dict[str, object]) -> dict[str, str]:
    """Emit ``computed[]`` items in order -> ``{alias: sql}`` for inlining."""
    out: dict[str, str] = {}
    for item in spec.get("computed") or []:
        if not isinstance(item, dict):
            raise ValueError(f"unsupported computed item: {item!r}")
        alias = str(item.get("alias") or "")
        if not _IDENT_RE.match(alias):
            raise ValueError(f"bad computed alias: {alias!r}")
        kind = item.get("kind")
        if kind == "bool" and isinstance(item.get("where"), dict):
            out[alias] = _spec_bool(item["where"], out, params, f"cp_{alias}_")
        elif kind == "number" and isinstance(item.get("expr"), dict):
            out[alias] = _spec_operand(item["expr"], out, params, f"cp_{alias}_")
        elif kind == "number" and item.get("sum_aliases"):
            missing = [a for a in item["sum_aliases"] if a not in out]
            if missing:
                raise ValueError(f"sum_aliases references unknown aliases: {missing}")
            out[alias] = " + ".join(f"({out[a]})" for a in item["sum_aliases"])
        else:
            raise ValueError(f"unsupported computed item: {item!r}")
    return out


def _spec_from_clause(spec: dict, factor_table: str) -> tuple[str, str, dict[str, str]]:
    """Build the FROM/JOIN clause; returns (from_sql, spine_alias, table->alias).

    The factor table is joined in automatically when it is not already the
    spine or one of the declared joins (all screener joins are 1:1 on
    ``(ticker, date)``).
    """
    t2p = _table_to_prefix()
    spine = spec.get("spine")
    if not isinstance(spine, str) or not _IDENT_RE.match(spine):
        raise ValueError(f"universe_spec.spine must be a bare table identifier, got {spine!r}")
    pa = t2p.get(spine, "sp")
    aliases = {spine: pa}
    joins = [dict(j) for j in spec.get("joins") or []]
    if factor_table != spine and all(j.get("table") != factor_table for j in joins):
        joins.append({"table": factor_table, "type": "left_any", "on": ["ticker", "date"]})
    parts = [f"{spine} AS {pa} FINAL"]
    for i, j in enumerate(joins):
        tbl = str(j.get("table") or "")
        _validate_ident("universe_spec.joins[].table", tbl)
        if tbl in aliases:
            continue
        alias = t2p.get(tbl, f"j{i}")
        jt = _SPEC_JOIN_TYPES.get(str(j.get("type", "left_any")), "LEFT ANY")
        on = j.get("on") or ["ticker", "date"]
        conds = " AND ".join(
            f"{alias}.{_validate_ident('join key', str(k))} = {pa}.{_validate_ident('join key', str(k))}"
            for k in on
        )
        parts.append(f"{jt} JOIN {tbl} AS {alias} ON {conds}")
        aliases[tbl] = alias
    return "\n            ".join(parts), pa, aliases


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def evaluate_factor_performance(
    client: Any,
    *,
    factor_column: str | None = None,
    factor_expr: str | None = None,
    factor_table: str = "screener_factor_daily",
    start_date: str,
    end_date: str,
    quantiles: int = 10,
    horizon: Literal["5d", "21d"] = "5d",
    population: str = "all",
    universe_spec: dict | None = None,
) -> dict[str, Any]:
    """Evaluate a factor's pre-LEAN relative performance.

    Args:
        client: clickhouse-connect client (query + parameters binding).
        factor_column / factor_expr: exactly one required. ``factor_column`` is
            a bare column on ``factor_table``; ``factor_expr`` is a whitelisted
            arithmetic expression over that table's columns (e.g.
            ``rs_rating - sma21d_rs_rating``) — see ``_compile_factor_expr``.
        factor_table: source table; must have (ticker, date) and the column(s).
        start_date / end_date: ISO dates bounding the evaluation window.
        quantiles: cross-sectional bucket count per date (2..20).
        horizon: "5d" or "21d" — selects the materialized forward columns.
        population: "all" (whole factor table), "universe" (spec base WHERE),
            or "eligible" (base WHERE + alpha post_where). The latter two
            require ``universe_spec``.
        universe_spec: compiled ``/VeraBase/Universe`` fragment
            (``spine``/``joins``/``where``/``computed``/``post_where``). The
            factor table is joined in automatically when it is not the spine
            or a declared join.

    Returns the dict documented in the module docstring.
    """
    if (factor_column is None) == (factor_expr is None):
        raise ValueError("exactly one of factor_column or factor_expr is required")
    if factor_column is not None:
        factor_column = _validate_ident("factor_column", factor_column)
    factor_table = _validate_ident("factor_table", factor_table)
    start_date = _validate_date("start_date", start_date)
    end_date = _validate_date("end_date", end_date)
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

    expr_toks = (
        _factor_expr_tokens(str(factor_expr)) if factor_expr is not None else None
    )

    ret_col, ew_col = _HORIZONS[horizon]

    if not _table_exists(client, factor_table):
        raise ValueError(f"missing factor table: {factor_table}")
    if not _table_exists(client, _FORWARD_TABLE):
        raise ValueError(
            f"missing forward-return mart {_FORWARD_TABLE}; "
            "run transform 132 (vera-populate --metrics screener-forward-returns) first"
        )
    has_regime = _table_exists(client, _REGIME_TABLE)

    regime_col = (
        "m.effective_allocation_fraction"
        if has_regime
        else "CAST(NULL AS Nullable(Float32))"
    )
    regime_join = (
        f"LEFT JOIN {_REGIME_TABLE} m FINAL ON m.date = f.date" if has_regime else ""
    )

    params: dict[str, object] = {
        "start": start_date,
        "end": end_date,
        "q": int(quantiles),
    }

    if universe_spec is None:
        if factor_column is not None:
            score_sql = f"f.`{factor_column}`"
            score_guard = f"isNotNull(f.`{factor_column}`)"
        else:
            assert expr_toks is not None
            cols = _table_columns(client, factor_table)
            expr = _compile_factor_expr(expr_toks, str(factor_expr), cols, "f")
            score_sql = f"({expr})"
            score_guard = f"isFinite(toFloat64(({expr})))"
        joined = f"""
            SELECT
                f.date AS date,
                f.ticker AS ticker,
                toFloat64({score_sql}) AS score,
                toFloat64(fr.{ret_col}) AS fwd_ret,
                toFloat64(fr.{ew_col}) AS ew_ret,
                {regime_col} AS regime_frac
            FROM {factor_table} AS f FINAL
            INNER JOIN {_FORWARD_TABLE} fr FINAL
                ON fr.ticker = f.ticker AND fr.date = f.date
            {regime_join}
            WHERE f.date BETWEEN toDate(%(start)s) AND toDate(%(end)s)
              AND {score_guard}
              AND isNotNull(fr.{ret_col})
              AND isNotNull(fr.{ew_col})
        """
    else:
        from_sql, pa, table_aliases = _spec_from_clause(universe_spec, factor_table)
        fa = table_aliases[factor_table]
        if factor_column is not None:
            cols = _table_columns(client, factor_table)
            if factor_column not in cols:
                raise ValueError(
                    f"factor_column {factor_column!r} is not a column on {factor_table}"
                )
            score_sql = f"{fa}.`{factor_column}`"
        else:
            assert expr_toks is not None
            cols = _table_columns(client, factor_table)
            score_sql = _compile_factor_expr(expr_toks, str(factor_expr), cols, fa)

        filters = [f"{pa}.date BETWEEN toDate(%(start)s) AND toDate(%(end)s)"]
        where = universe_spec.get("where")
        if isinstance(where, dict):
            filters.append(f"({_compile_spec_where(where, params, 'uw_')})")
        if population == "eligible" and isinstance(universe_spec.get("post_where"), dict):
            computed = _spec_computed_aliases(universe_spec, params)
            filters.append(
                f"({_spec_bool(universe_spec['post_where'], computed, params, 'pw_')})"
            )
        joined = f"""
            SELECT
                f.date AS date,
                f.ticker AS ticker,
                f.score AS score,
                toFloat64(fr.{ret_col}) AS fwd_ret,
                toFloat64(fr.{ew_col}) AS ew_ret,
                {regime_col} AS regime_frac
            FROM (
                SELECT {pa}.ticker AS ticker, {pa}.date AS date,
                       toFloat64(({score_sql})) AS score
                FROM {from_sql}
                WHERE {' AND '.join(f'({c})' for c in filters)}
            ) f
            INNER JOIN {_FORWARD_TABLE} fr FINAL
                ON fr.ticker = f.ticker AND fr.date = f.date
            {regime_join}
            WHERE isNotNull(fr.{ret_col})
              AND isNotNull(fr.{ew_col})
              AND isFinite(f.score)
        """

    # ---- Quantile table --------------------------------------------------
    quantile_sql = f"""
        SELECT
            bucket,
            count() AS n_obs,
            avg(fwd_ret) AS mean_fwd_ret,
            avg(ew_ret) AS mean_ew_ret,
            avg(fwd_ret - ew_ret) AS mean_active_spread,
            avg(fwd_ret > ew_ret) AS hit_rate,
            countDistinct(date) AS n_days
        FROM (
            SELECT
                date, ticker, fwd_ret, ew_ret,
                ntile(%(q)s) OVER (PARTITION BY date ORDER BY score, ticker) AS bucket
            FROM ({joined})
        )
        GROUP BY bucket
        ORDER BY bucket
    """
    qrows = client.query(quantile_sql, parameters=params).result_rows
    quantile_rows = [
        {
            "bucket": int(r[0]),
            "n_obs": int(r[1]),
            "mean_fwd_ret": float(r[2]),
            "mean_ew_ret": float(r[3]),
            "mean_active_spread": float(r[4]),
            "hit_rate": float(r[5]),
            "n_days": int(r[6]),
        }
        for r in qrows
    ]

    # ---- Daily Spearman IC ------------------------------------------------
    ic_sql = f"""
        SELECT
            date,
            corr(score_rank, ret_rank) AS ic
        FROM (
            SELECT
                date,
                rank() OVER (PARTITION BY date ORDER BY score, ticker) AS score_rank,
                rank() OVER (PARTITION BY date ORDER BY fwd_ret, ticker) AS ret_rank
            FROM ({joined})
        )
        GROUP BY date
        HAVING count() > 2
        ORDER BY date
    """
    ic_rows = client.query(ic_sql, parameters=params).result_rows
    ics = [float(r[1]) for r in ic_rows if r[1] is not None]
    mean_ic = sum(ics) / len(ics) if ics else None
    std_ic = (
        math.sqrt(sum((v - mean_ic) ** 2 for v in ics) / (len(ics) - 1))
        if mean_ic is not None and len(ics) > 1
        else None
    )
    icir = (
        mean_ic / std_ic * math.sqrt(_ANN_FACTOR)
        if mean_ic is not None and std_ic and std_ic > 0
        else None
    )

    # ---- Regime attribution (top-quantile active spread) -----------------
    regime_sql = f"""
        SELECT
            regime_frac,
            countDistinct(date) AS n_days,
            avg(fwd_ret - ew_ret) AS active_spread
        FROM (
            SELECT
                date, ticker, fwd_ret, ew_ret, regime_frac,
                ntile(%(q)s) OVER (PARTITION BY date ORDER BY score, ticker) AS bucket
            FROM ({joined})
        )
        WHERE bucket = %(q)s
        GROUP BY regime_frac
        ORDER BY regime_frac
    """
    regime_attribution: dict[str, dict[str, Any]] = {}
    if has_regime:
        regime_rows = client.query(regime_sql, parameters=params).result_rows
        regime_attribution = {
            ("none" if r[0] is None else str(round(float(r[0]), 2))): {
                "active_spread": float(r[2]),
                "n_days": int(r[1]),
            }
            for r in regime_rows
        }

    # Coverage ledger for the exact request. These stage counts distinguish
    # spine availability, factor-table availability, valid labels and the
    # evaluator's final eligible observations; they intentionally do not infer
    # why a source date is absent.
    spine_dates = client.query(
        "SELECT DISTINCT toString(date) FROM screener_price_tech_daily FINAL "
        "WHERE date BETWEEN toDate(%(start)s) AND toDate(%(end)s) ORDER BY date",
        parameters=params,
    ).result_rows
    factor_dates = client.query(
        f"SELECT DISTINCT toString(date) FROM {factor_table} FINAL "
        "WHERE date BETWEEN toDate(%(start)s) AND toDate(%(end)s) ORDER BY date",
        parameters=params,
    ).result_rows
    label_dates = client.query(
        f"SELECT DISTINCT toString(f.date) FROM {factor_table} f FINAL "
        f"INNER JOIN {_FORWARD_TABLE} fr FINAL ON fr.ticker = f.ticker AND fr.date = f.date "
        f"WHERE f.date BETWEEN toDate(%(start)s) AND toDate(%(end)s) "
        f"AND isNotNull(fr.{ret_col}) AND isNotNull(fr.{ew_col}) ORDER BY f.date",
        parameters=params,
    ).result_rows
    final_dates = client.query(
        f"SELECT DISTINCT toString(date) FROM ({joined}) ORDER BY date",
        parameters=params,
    ).result_rows
    spine_date_set = {str(r[0]) for r in spine_dates}
    factor_date_set = {str(r[0]) for r in factor_dates}
    label_date_set = {str(r[0]) for r in label_dates}
    final_date_set = {str(r[0]) for r in final_dates}
    exclusion_waterfall = {
        "requested_window": {"start_date": start_date, "end_date": end_date},
        "available_spine_dates": sorted(spine_date_set),
        "factor_table_dates": sorted(factor_date_set),
        "dates_with_valid_forward_labels": sorted(label_date_set),
        "dates_with_final_observations": sorted(final_date_set),
        "session_counts": {
            "available_spine": len(spine_date_set),
            "factor_table": len(factor_date_set),
            "valid_forward_labels": len(label_date_set),
            "final_observations": len(final_date_set),
        },
    }

    # ---- Monotonicity -----------------------------------------------------
    monotonicity = _pearson(
        [float(r["bucket"]) for r in quantile_rows],
        [r["mean_fwd_ret"] for r in quantile_rows],
    )

    # ---- Summary + verdict -----------------------------------------------
    n_days = max((r["n_days"] for r in quantile_rows), default=0)
    top = quantile_rows[-1] if quantile_rows else None
    bottom = quantile_rows[0] if quantile_rows else None
    summary = {
        "n_days": n_days,
        "top_bucket": top["bucket"] if top else None,
        "top_mean_fwd_ret": top["mean_fwd_ret"] if top else None,
        "top_mean_active_spread": top["mean_active_spread"] if top else None,
        "ew_mean_fwd_ret": top["mean_ew_ret"] if top else None,
        "top_minus_bottom_spread": (
            top["mean_fwd_ret"] - bottom["mean_fwd_ret"] if top and bottom else None
        ),
        "top_minus_bottom_active_spread": (
            top["mean_active_spread"] - bottom["mean_active_spread"]
            if top and bottom
            else None
        ),
    }

    reasons = []
    if not quantile_rows:
        verdict = "insufficient_data"
        reasons.append("no overlapping factor/forward-return rows in window")
    else:
        verdict = "pass"
        if summary["top_mean_active_spread"] is not None and summary["top_mean_active_spread"] <= 0:
            verdict = "fail"
            reasons.append("top quantile does not beat the EW universe")
        if summary["top_minus_bottom_active_spread"] is not None and summary["top_minus_bottom_active_spread"] <= 0:
            verdict = "fail"
            reasons.append("no top-minus-bottom active spread")
        if monotonicity is not None and monotonicity < 0.7:
            verdict = "fail"
            reasons.append(f"monotonicity {monotonicity:.2f} < 0.70")
        if mean_ic is not None and mean_ic <= 0:
            verdict = "fail"
            reasons.append(f"mean_ic {mean_ic:.3f} <= 0")

    factor_label = (
        factor_column
        if factor_column is not None
        else str(factor_expr)[:120] + ("…" if len(str(factor_expr)) > 120 else "")
    )
    return {
        "factor": factor_label,
        "factor_table": factor_table,
        "population": population,
        "horizon": horizon,
        "quantiles_requested": int(quantiles),
        "start_date": start_date,
        "end_date": end_date,
        "windows": [f"{start_date}..{end_date}"],
        "exclusion_waterfall": exclusion_waterfall,
        "quality_status": "pending_unverified",
        "data_quality_run_id": None,
        "quantiles": quantile_rows,
        "ic_stats": {
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "icir": icir,
            "n_days": len(ics),
        },
        "regime_attribution": regime_attribution,
        "monotonicity_score": monotonicity,
        "summary": summary,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
