"""Compile universe specs to ClickHouse SQL (L7 screener joins).

``source: daily_screener`` is the logical id; SQL joins ``screener_*``.
Ported from VeraTradingLab `vera_lab.ir.query_compile` with minimal changes.
"""

from __future__ import annotations

import re

from .models import UniverseSpec
from sigmarail_spec import (
    AllExpr,
    AnyExpr,
    BoolExprItem,
    ColBetweenExpr,
    ColEqExpr,
    ColGteExpr,
    ColLteExpr,
    InTickersExpr,
    NotExpr,
    validate_bool_expr_depth,
)
from .l7_from import l7_from_sql, qualify_column
from .screener_columns import ScreenerColumn, sql_ident

# Legacy screener SQL supports sorting by any available daily_screener column.
# The schema-driven universe_v1 column registry is the canonical source.
from .screener_columns import available_columns as _available_columns

_TICKER_SAFE = re.compile(r"^[A-Za-z0-9.-]{1,16}$")

SORTABLE_COLUMNS: frozenset[str] = _available_columns()


def _escape_ticker(t: str) -> str:
    t = t.strip().upper()
    if not _TICKER_SAFE.match(t):
        raise ValueError(f"invalid ticker for SQL: {t!r}")
    return t.replace("'", "''")


class CompiledQuery(dict):
    """Simple typed alias: {'sql': str, 'params': dict}."""

_DM_OPEN: ScreenerColumn = "open"
_DM_HIGH: ScreenerColumn = "high"
_DM_LOW: ScreenerColumn = "low"
_CLOSE: ScreenerColumn = "close"
_VOLUME: ScreenerColumn = "volume"
_HAS_VCP_SETUP: ScreenerColumn = "has_vcp_setup"
_IS_STAGE_2_ADVANCING: ScreenerColumn = "is_stage_2_advancing"
_MINERVINI_TT_SCORE_FULL: ScreenerColumn = "minervini_tt_score_full"



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
            ColGteExpr(column=_CLOSE, value=spec.min_close),
            ColGteExpr(column=_VOLUME, value=spec.min_volume),
            ColEqExpr(
                column=_HAS_VCP_SETUP,
                value=spec.require_has_vcp_setup,
            ),
            ColEqExpr(
                column=_IS_STAGE_2_ADVANCING,
                value=spec.require_is_stage_2_advancing,
            ),
            ColGteExpr(
                column=_MINERVINI_TT_SCORE_FULL,
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


DEFAULT_PROJECTION: tuple[ScreenerColumn, ...] = (
    "ticker",
    "overall_score",
    "atr_14_pct",
)


def effective_projection(spec: UniverseSpec) -> list[ScreenerColumn]:
    if spec.projection:
        return list(spec.projection)
    return list(DEFAULT_PROJECTION)


def universe_spec_result_column_names(spec: UniverseSpec) -> frozenset[str]:
    """Result column aliases for legacy single-day screener SQL (matches ``_compile_select_clause``)."""
    names: set[str] = {"date"}
    for c in effective_projection(spec):
        if c == _DM_OPEN:
            names.add("open")
        elif c == _DM_HIGH:
            names.add("high")
        elif c == _DM_LOW:
            names.add("low")
        elif c == _CLOSE:
            names.add("close")
        elif c == _VOLUME:
            names.add("volume")
        else:
            names.add(str(c).replace(".", "_"))
    return frozenset(names)


def _ident(column: ScreenerColumn) -> str:
    try:
        return qualify_column(str(column))
    except ValueError:
        return sql_ident(column)


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
    names = set(str(c) for c in effective_projection(spec))
    names.add(str(spec.sort_field))
    names |= _predicate_columns(effective_criteria(spec))
    names.update({"ticker", "date"})
    return l7_from_sql(names)


def compile_predicate(item: BoolExprItem) -> str:
    if isinstance(item, ColGteExpr):
        return f"{_ident(item.column)} >= {float(item.value)}"
    if isinstance(item, ColLteExpr):
        return f"{_ident(item.column)} <= {float(item.value)}"
    if isinstance(item, ColBetweenExpr):
        return f"{_ident(item.column)} BETWEEN {float(item.min)} AND {float(item.max)}"
    if isinstance(item, ColEqExpr):
        col = item.column
        if col in (_HAS_VCP_SETUP, _IS_STAGE_2_ADVANCING):
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

def compile_predicate_param(item: BoolExprItem, params: dict[str, object], *, prefix: str = "p") -> str:
    """
    Compile predicate to parameterized ClickHouse SQL using {name:Type} placeholders.
    """
    def add(name: str, typ: str, value: object) -> str:
        key = f"{prefix}{name}"
        params[key] = value
        return f"{{{key}:{typ}}}"

    if isinstance(item, ColGteExpr):
        ph = add("gte", "Float64", float(item.value))
        return f"{_ident(item.column)} >= {ph}"
    if isinstance(item, ColLteExpr):
        ph = add("lte", "Float64", float(item.value))
        return f"{_ident(item.column)} <= {ph}"
    if isinstance(item, ColBetweenExpr):
        lo = add("lo", "Float64", float(item.min))
        hi = add("hi", "Float64", float(item.max))
        return f"{_ident(item.column)} BETWEEN {lo} AND {hi}"
    if isinstance(item, ColEqExpr):
        col = item.column
        if col in (_HAS_VCP_SETUP, _IS_STAGE_2_ADVANCING):
            if not isinstance(item.value, bool):
                raise ValueError(f"eq on {col} requires bool")
            ph = add("eqb", "UInt8", 1 if item.value else 0)
            return f"{_ident(col)} = {ph}"
        if isinstance(item.value, bool):
            raise ValueError(f"eq on {col} expects numeric value")
        ph = add("eq", "Float64", float(item.value))
        return f"{_ident(col)} = {ph}"
    if isinstance(item, InTickersExpr):
        # Ticker validation is intentionally conservative: uppercasing + safe length.
        tickers = [t.strip().upper() for t in item.tickers if t and t.strip()]
        if not tickers:
            raise ValueError("in_tickers requires at least one ticker")
        ph = add("tickers", "Array(String)", tickers)
        return f"px.ticker IN {ph}"
    if isinstance(item, AllExpr):
        if not item.items:
            return "1"
        inner = [compile_predicate_param(s, params, prefix=f"{prefix}a{idx}_") for idx, s in enumerate(item.items)]
        return " AND ".join(f"({x})" for x in inner)
    if isinstance(item, AnyExpr):
        if not item.items:
            return "0"
        inner = [compile_predicate_param(s, params, prefix=f"{prefix}o{idx}_") for idx, s in enumerate(item.items)]
        return " OR ".join(f"({x})" for x in inner)
    if isinstance(item, NotExpr):
        return f"NOT ({compile_predicate_param(item.item, params, prefix=f'{prefix}n_')})"
    raise TypeError(type(item))


def _compile_select_clause(projection: list[ScreenerColumn]) -> str:
    parts: list[str] = ["toDate(px.date) AS date"]
    for c in projection:
        col = _ident(c)
        if c == _DM_OPEN:
            parts.append(f"ifNull({col}, px.close) AS open")
        elif c == _DM_HIGH:
            parts.append(f"ifNull({col}, px.close) AS high")
        elif c == _DM_LOW:
            parts.append(f"ifNull({col}, px.close) AS low")
        elif c == _CLOSE:
            parts.append("ifNull(px.close, 0) AS close")
        elif c == _VOLUME:
            parts.append("ifNull(px.volume, 0) AS volume")
        else:
            parts.append(f"{col} AS {str(c).replace('.', '_')}")
    return ",\n                ".join(parts)


def compile_screener_range_query(spec: UniverseSpec, start_date_iso: str, end_date_iso: str) -> str:
    """Bulk backtest load: LIMIT n BY date."""
    crit = effective_criteria(spec)
    validate_bool_expr_depth(crit)
    where_inner = compile_predicate(crit)
    proj = _compile_select_clause(effective_projection(spec))
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

def compile_screener_range_query_param(spec: UniverseSpec) -> tuple[str, dict[str, object]]:
    """
    Parameterized range query (no inlined dates, no FORMAT).
    Caller provides params: start/end as ISO strings.
    """
    crit = effective_criteria(spec)
    validate_bool_expr_depth(crit)
    params: dict[str, object] = {}
    where_inner = compile_predicate_param(crit, params, prefix="c_")
    proj = _compile_select_clause(effective_projection(spec))
    order_dir = "ASC" if spec.sort_direction == "asc" else "DESC"
    sort_col = _ident(spec.sort_field)
    lim = spec.limit_per_day
    assert lim is not None
    from_sql = _spec_from_sql(spec)
    sql = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date BETWEEN toDate({{start:String}}) AND toDate({{end:String}})
              AND ({where_inner})
            ORDER BY px.date ASC, {sort_col} {order_dir}, px.ticker ASC
            LIMIT {{lim:UInt32}} BY px.date
        """
    params["start"] = ""
    params["end"] = ""
    params["lim"] = int(lim)
    return sql, params


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


def compile_screener_single_day_query_param(spec: UniverseSpec) -> tuple[str, dict[str, object]]:
    """
    Parameterized single-day query (no inlined date, no FORMAT).
    Caller provides param: day as ISO string.
    """
    crit = effective_criteria(spec)
    validate_bool_expr_depth(crit)
    params: dict[str, object] = {}
    where_inner = compile_predicate_param(crit, params, prefix="c_")
    proj = _compile_select_clause(effective_projection(spec))
    if spec.sort_field not in SORTABLE_COLUMNS:
        raise ValueError("sort_field not in SORTABLE_COLUMNS")
    order_dir = "ASC" if spec.sort_direction == "asc" else "DESC"
    sort_col = _ident(spec.sort_field)
    lim = spec.limit_per_day
    assert lim is not None
    from_sql = _spec_from_sql(spec)
    sql = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date = toDate({{day:String}})
              AND ({where_inner})
            ORDER BY {sort_col} {order_dir}, px.ticker ASC
            LIMIT {{lim:UInt32}}
        """
    params["day"] = ""
    params["lim"] = int(lim)
    return sql, params
