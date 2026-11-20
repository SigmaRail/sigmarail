"""SQL emission for the canonical expression dialect (C-VERA-EXPR-V1).

The dialect itself — node classes, unions, parsing and depth validation — lives in the
**`sigmarail_spec`** package since the 2026-10-02 consolidation. It moved because
VeraTradingLab needs the same dialect *and its row evaluator*, and cannot import VeraBase:
that tree ships into the LEAN container, where pandas/clickhouse/fastapi are absent.

What remains **here** is the part that genuinely needs the database: resolving column names
against the L7 registry (`_col_sql`) and compiling the tree to ClickHouse SQL
(`compile_bool_expr_sql`). The dialect is re-exported below so existing imports keep
working; new code should import from `sigmarail_spec` directly.
"""

from __future__ import annotations

from typing import Any

from sigmarail_spec.expr import (  # noqa: F401  (re-export for compatibility)
    AllExpr, AnyExpr, BoolExprItem, CmpEq,
    CmpGt, CmpGte, CmpLt, CmpLte,
    ColBetweenExpr, ColEqExpr, ColGteExpr, ColLteExpr,
    ColRef, FormulaExpr, InTickersExpr, LitVal,
    MAX_BOOL_DEPTH, MAX_FORMULA_DEPTH, NotExpr, Operand,
    RegimeAllowsEntriesExpr, RegimeExpr, RegimeMartAllowsEntriesExpr, SignalCompareExpr,
    SignalExpr, SpecExpr, WhereExpr, _BOOL_ADAPTER,
    bool_expr_depth, is_runtime_only_expr, parse_bool_expr, validate_bool_expr_depth,
)


def _col_sql(name: str) -> tuple[str, str]:
    from sigmarail.features.ir.universe_v1_column_registry import get_universe_v1_col_sql_map

    key = name.strip().strip("`")
    m = get_universe_v1_col_sql_map()
    if key in m:
        return m[key]
    if "." in key:
        bare = key.split(".", 1)[1]
        if bare in m:
            return m[bare]
    raise ValueError(f"unknown or disallowed column: {name!r}")


def _emit_operand(
    op: Operand, params: dict[str, object], key_pfx: str, *, depth: int = 0
) -> str:
    if isinstance(op, ColRef):
        sql_expr, _alias = _col_sql(op.name)
        if op.offset == 0:
            return sql_expr
        return _emit_offset_column(sql_expr, op.offset, params, key_pfx)
    if isinstance(op, LitVal):
        v = op.value
        key = f"{key_pfx}lit"
        i = 0
        while f"{key}_{i}" in params:
            i += 1
        k = f"{key}_{i}"
        if isinstance(v, bool):
            params[k] = 1 if v else 0
            return f"{{{k}:UInt8}}"
        if isinstance(v, int) and not isinstance(v, bool):
            params[k] = int(v)
            return f"{{{k}:Int64}}"
        if isinstance(v, float):
            params[k] = float(v)
            return f"{{{k}:Float64}}"
        if isinstance(v, str):
            params[k] = str(v)
            return f"{{{k}:String}}"
        raise TypeError(f"unsupported literal type: {type(v)}")
    if isinstance(op, FormulaExpr):
        if depth >= MAX_FORMULA_DEPTH:
            raise ValueError(f"formula expression exceeds max depth {MAX_FORMULA_DEPTH}")
        if len(op.args) != 2:
            raise ValueError("formula requires exactly 2 args")
        left_sql = _emit_operand(op.args[0], params, f"{key_pfx}fL", depth=depth + 1)
        right_sql = _emit_operand(op.args[1], params, f"{key_pfx}fR", depth=depth + 1)
        return f"({left_sql} {op.op} {right_sql})"
    raise TypeError(type(op))


_PREFIX_TO_TABLE: dict[str, str] = {
    "px": "screener_price_tech_daily",
    "rt": "screener_ratings_daily",
    "ow": "screener_ownership_daily",
    "fd": "screener_fundamentals_daily",
    "st": "screener_stage_weekly_daily",
    "fa": "screener_factor_daily",
    "fc": "screener_forecast_models_daily",
    "es": "screener_estimates_daily",
    "kb": "screener_kb_daily",
    "mx": "market_context_daily",
    "tf": "symbol_technical_features_daily",
    "rv": "ticker_rvab_daily",
}


def _emit_offset_column(
    sql_expr: str, offset: int, params: dict[str, object], key_pfx: str
) -> str:
    """Compile a column reference with a non-zero bar offset to a correlated subquery.

    For offset -1 (previous bar), generates:
        (SELECT col FROM <table> AS <prefix>2
         WHERE <prefix>2.ticker = <prefix>.ticker
           AND <prefix>2.date = toDate({day:String}) - INTERVAL 1 DAY)
    """
    if "." in sql_expr:
        prefix, col_name = sql_expr.split(".", 1)
    else:
        prefix, col_name = "px", sql_expr
    tbl = _PREFIX_TO_TABLE.get(prefix, "screener_price_tech_daily")
    sign = "-" if offset < 0 else "+"
    abs_off = abs(offset)
    k = f"{key_pfx}off"
    params[k] = abs_off
    return (
        f"(SELECT {col_name} FROM {tbl} AS {prefix}2 "
        f"WHERE {prefix}2.ticker = {prefix}.ticker "
        f"AND {prefix}2.date = toDate({{day:String}}) {sign} INTERVAL {k}:Int64 DAY)"
    )


def _compile_cmp_col_lit(
    expr: CmpGt | CmpGte | CmpLt | CmpLte | CmpEq, params: dict[str, object], pfx: str
) -> str:
    opmap = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
    left_sql = _emit_operand(expr.left, params, f"{pfx}L")
    right_sql = _emit_operand(expr.right, params, f"{pfx}R")
    return f"{left_sql} {opmap[expr.type]} {right_sql}"


def _compile_col_predicate(expr: BoolExprItem, params: dict[str, object], pfx: str) -> str:
    if isinstance(expr, ColGteExpr):
        sql_expr, _ = _col_sql(expr.column)
        key = f"{pfx}cg"
        params[key] = float(expr.value)
        return f"{sql_expr} >= {{{key}:Float64}}"
    if isinstance(expr, ColLteExpr):
        sql_expr, _ = _col_sql(expr.column)
        key = f"{pfx}cl"
        params[key] = float(expr.value)
        return f"{sql_expr} <= {{{key}:Float64}}"
    if isinstance(expr, ColEqExpr):
        sql_expr, _ = _col_sql(expr.column)
        if isinstance(expr.value, bool):
            key = f"{pfx}ce"
            params[key] = 1 if expr.value else 0
            return f"{sql_expr} = {{{key}:UInt8}}"
        key = f"{pfx}ce"
        params[key] = float(expr.value)
        return f"{sql_expr} = {{{key}:Float64}}"
    if isinstance(expr, ColBetweenExpr):
        sql_expr, _ = _col_sql(expr.column)
        k0, k1 = f"{pfx}b0", f"{pfx}b1"
        params[k0] = float(expr.min)
        params[k1] = float(expr.max)
        return f"{sql_expr} BETWEEN {{{k0}:Float64}} AND {{{k1}:Float64}}"
    if isinstance(expr, InTickersExpr):
        parts = []
        for i, t in enumerate(expr.tickers):
            k = f"{pfx}t{i}"
            params[k] = str(t).strip().upper()
            parts.append(f"{{{k}:String}}")
        return f"px.ticker IN ({', '.join(parts)})"
    raise TypeError(type(expr))


def compile_bool_expr_sql(item: BoolExprItem, params: dict[str, object], pfx: str = "w_") -> str:
    if is_runtime_only_expr(item):
        raise ValueError(f"{item.type!r} is runtime-only and cannot compile to SQL")
    if isinstance(item, (CmpGt, CmpGte, CmpLt, CmpLte, CmpEq)):
        return _compile_cmp_col_lit(item, params, pfx)
    if isinstance(item, (ColGteExpr, ColLteExpr, ColEqExpr, ColBetweenExpr, InTickersExpr)):
        return _compile_col_predicate(item, params, pfx)
    if isinstance(item, AllExpr):
        if not item.items:
            return "1"
        parts = [compile_bool_expr_sql(x, params, f"{pfx}a{i}_") for i, x in enumerate(item.items)]
        return " AND ".join(f"({p})" for p in parts)
    if isinstance(item, AnyExpr):
        if not item.items:
            return "0"
        parts = [compile_bool_expr_sql(x, params, f"{pfx}o{i}_") for i, x in enumerate(item.items)]
        return " OR ".join(f"({p})" for p in parts)
    if isinstance(item, NotExpr):
        inner = compile_bool_expr_sql(item.item, params, f"{pfx}n_")
        return f"NOT ({inner})"
    raise TypeError(type(item))
