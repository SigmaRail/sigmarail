"""Compile VeraLab universe specs to ClickHouse SQL (L7 screener joins).

``source: daily_screener`` is the logical IR id; generated SQL joins ``screener_*``.


Deprecation / policy: new universe authoring should target **VeraBase**
``universe_query_v1`` JSON (validated and executed via ``POST /v1/universe/run``).
This module remains the **legacy** compile path for:

- **Direct ClickHouse** HTTP from LEAN when the Vera query service URL is unset, and
- **``reload_today``** when the store holds a ``UniverseSpec`` (not an opaque v1 dict).

Do not extend this surface for new ChartMill-style features — add them in
``vera_query_core`` instead.
"""

from __future__ import annotations

import re
from .models import UniverseSpec
from sigmarail_spec import (
    AllExpr,
    AnyExpr,
    ColBetweenExpr,
    BoolExprItem,
    ColEqExpr,
    ColGteExpr,
    InTickersExpr,
    ColLteExpr,
    NotExpr,
    is_runtime_only_expr,
    validate_bool_expr_depth,
)
from .l7_from import l7_from_sql, qualify_column
from .screener_columns import (
    PROJECTION_COLUMNS,
    ScreenerColumn,
    SORTABLE_COLUMNS,
    sql_ident,
)

_TICKER_SAFE = re.compile(r"^[A-Za-z0-9.-]{1,16}$")


def _escape_ticker(t: str) -> str:
    t = t.strip().upper()
    if not _TICKER_SAFE.match(t):
        raise ValueError(f"invalid ticker for SQL: {t!r}")
    return t.replace("'", "''")


def effective_criteria(spec: UniverseSpec) -> BoolExprItem:
    """Explicit criteria or legacy flat fields synthesized to the same AST."""
    if spec.criteria is not None:
        return spec.criteria
    assert spec.min_close is not None
    assert spec.min_volume is not None
    assert spec.min_minervini_tt_score_full is not None
    inc = spec.always_include_tickers or ["SPY"]
    main = AllExpr(
        items=[
            ColGteExpr(column=ScreenerColumn.CLOSE, value=spec.min_close),
            ColGteExpr(column=ScreenerColumn.VOLUME, value=spec.min_volume),
            ColEqExpr(
                column=ScreenerColumn.HAS_VCP_SETUP,
                value=spec.require_has_vcp_setup,
            ),
            ColEqExpr(
                column=ScreenerColumn.IS_STAGE_2_ADVANCING,
                value=spec.require_is_stage_2_advancing,
            ),
            ColGteExpr(
                column=ScreenerColumn.MINERVINI_TT_SCORE_FULL,
                value=spec.min_minervini_tt_score_full,
            ),
        ]
    )
    return AnyExpr(
        items=[
            InTickersExpr(type="in_tickers", tickers=list(inc)),
            main,
        ]
    )


# Default SELECT: universe + sizing only. Predicates may still filter on close/volume etc.
# without projecting those columns. Add explicit ``UniverseSpec.projection`` / graph
# ``filter.projection`` when downstream code needs OHLC or other columns in row payloads.
DEFAULT_PROJECTION: tuple[ScreenerColumn, ...] = (
    ScreenerColumn.TICKER,
    ScreenerColumn.OVERALL_SCORE,
    ScreenerColumn.ATR_PCT_14D,
)


def effective_projection(spec: UniverseSpec) -> list[ScreenerColumn]:
    if spec.projection:
        for c in spec.projection:
            if c not in PROJECTION_COLUMNS:
                raise ValueError(f"projection column not allowed: {c!r}")
        return list(spec.projection)
    return list(DEFAULT_PROJECTION)


def _ident(column: ScreenerColumn | str) -> str:
    try:
        return qualify_column(str(column))
    except ValueError:
        return sql_ident(column) if isinstance(column, ScreenerColumn) else str(column)


def _predicate_columns(item: BoolExprItem) -> set[str]:
    if isinstance(item, (ColGteExpr, ColLteExpr, ColEqExpr)):
        return {str(item.column)}
    if isinstance(item, ColBetweenExpr):
        return {str(item.column)}
    if isinstance(item, InTickersExpr):
        return {"ticker"}
    if isinstance(item, (AllExpr, AnyExpr)):
        names: set[str] = set()
        for sub in item.items:
            names |= _predicate_columns(sub)
        return names
    if isinstance(item, NotExpr):
        return _predicate_columns(item.item)
    return set()


def _spec_from_sql(spec: UniverseSpec) -> str:
    names = {str(c) for c in effective_projection(spec)}
    names.add(str(spec.sort_field))
    names |= _predicate_columns(effective_criteria(spec))
    names.update({"ticker", "date"})
    return l7_from_sql(names)


def compile_predicate(item: BoolExprItem) -> str:
    if is_runtime_only_expr(item):
        raise ValueError(f"{item.type!r} cannot compile to SQL (runtime-only)")
    if isinstance(item, ColGteExpr):
        return f"{_ident(item.column)} >= {float(item.value)}"
    if isinstance(item, ColLteExpr):
        return f"{_ident(item.column)} <= {float(item.value)}"
    if isinstance(item, ColBetweenExpr):
        return (
            f"{_ident(item.column)} BETWEEN {float(item.min)} AND {float(item.max)}"
        )
    if isinstance(item, ColEqExpr):
        col = item.column
        if col in (ScreenerColumn.HAS_VCP_SETUP, ScreenerColumn.IS_STAGE_2_ADVANCING):
            if not isinstance(item.value, bool):
                raise ValueError(f"eq on {col} requires bool")
            bit = 1 if item.value else 0
            return f"{_ident(col)} = {bit}"
        if isinstance(item.value, bool):
            raise ValueError(f"eq on {col} expects numeric value")
        return f"{_ident(col)} = {float(item.value)}"
    if isinstance(item, InTickersExpr):
        inner = ", ".join(f"'{_escape_ticker(t)}'" for t in item.tickers)
        return f"px.ticker IN ({inner})"
    if isinstance(item, AllExpr):
        if not item.items:
            return "1"
        return " AND ".join(f"({compile_predicate(s)})" for s in item.items)
    if isinstance(item, AnyExpr):
        if not item.items:
            return "0"
        return " OR ".join(f"({compile_predicate(s)})" for s in item.items)
    if isinstance(item, NotExpr):
        return f"NOT ({compile_predicate(item.item)})"
    raise TypeError(type(item))


def _compile_select_clause(projection: list[ScreenerColumn]) -> str:
    parts: list[str] = ["toDate(px.date) AS date"]
    for c in projection:
        col = _ident(c)
        if c == ScreenerColumn.DM_OPEN:
            parts.append(f"ifNull({col}, px.close) AS open")
        elif c == ScreenerColumn.DM_HIGH:
            parts.append(f"ifNull({col}, px.close) AS high")
        elif c == ScreenerColumn.DM_LOW:
            parts.append(f"ifNull({col}, px.close) AS low")
        elif c == ScreenerColumn.CLOSE:
            parts.append("ifNull(px.close, 0) AS close")
        elif c == ScreenerColumn.VOLUME:
            parts.append("ifNull(px.volume, 0) AS volume")
        elif c == ScreenerColumn.SECTOR:
            parts.append("ifNull(px.sector, '') AS sector")
        elif c == ScreenerColumn.RS_RATING:
            parts.append("ifNull(px.rs_rating, 0) AS rs_rating")
        else:
            parts.append(f"{col} AS {c.value.replace('.', '_')}")
    return ",\n                ".join(parts)


def compile_screener_range_query(
    spec: UniverseSpec, start_date_iso: str, end_date_iso: str
) -> str:
    """Bulk backtest load: LIMIT n BY date."""
    crit = effective_criteria(spec)
    validate_bool_expr_depth(crit)
    where_inner = compile_predicate(crit)
    proj = _compile_select_clause(effective_projection(spec))
    if spec.sort_field not in SORTABLE_COLUMNS:
        raise ValueError("sort_field not in SORTABLE_COLUMNS")
    order_dir = "ASC" if spec.sort_direction == "asc" else "DESC"
    sort_col = _ident(spec.sort_field)
    lim = spec.limit_per_day
    assert lim is not None
    from_sql = _spec_from_sql(spec)
    return f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date BETWEEN toDate('{start_date_iso}') AND toDate('{end_date_iso}')
              AND ({where_inner})
            ORDER BY px.date ASC, {sort_col} {order_dir}, px.ticker ASC
            LIMIT {int(lim)} BY px.date
            FORMAT JSONEachRow
        """


def compile_screener_single_day_query(spec: UniverseSpec, today_iso: str) -> str:
    """Live: single calendar day."""
    crit = effective_criteria(spec)
    validate_bool_expr_depth(crit)
    where_inner = compile_predicate(crit)
    proj = _compile_select_clause(effective_projection(spec))
    if spec.sort_field not in SORTABLE_COLUMNS:
        raise ValueError("sort_field not in SORTABLE_COLUMNS")
    order_dir = "ASC" if spec.sort_direction == "asc" else "DESC"
    sort_col = _ident(spec.sort_field)
    lim = spec.limit_per_day
    assert lim is not None
    from_sql = _spec_from_sql(spec)
    return f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date = toDate('{today_iso}')
              AND ({where_inner})
            ORDER BY {sort_col} {order_dir}, px.ticker ASC
            LIMIT {int(lim)}
            FORMAT JSONEachRow
        """
