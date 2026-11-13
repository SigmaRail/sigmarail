"""Generic single-table SELECT with JSON AST ``where`` (v1).

Used by MCP ``query_table_v1`` and REST ``POST /v1/query/table``.
Column names are validated against ``system.columns`` via :func:`query_describe_table`.
"""

from __future__ import annotations

import os
import re
from typing import Annotated, Any, Literal, Union

import clickhouse_connect
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sigmarail.features.clickhouse_schema import (
    query_describe_table,
    rows_to_dicts,
    session_database,
    validate_table_identifier,
)
from sigmarail.features.mcp_table_catalog import SQL_JOIN_EXAMPLE, catalog_schema_defs
from sigmarail.features.screener_join import compile_screener_sql

MAX_WHERE_DEPTH = 24


def _table_engine(client: clickhouse_connect.driver.Client, table: str) -> str:
    """Return ``system.tables.engine`` for ``table`` in the session database."""
    db = session_database(client)
    rows = client.query(
        """
        SELECT engine
        FROM system.tables
        WHERE database = {db:String} AND name = {tbl:String}
        LIMIT 1
        """,
        parameters={"db": db, "tbl": table},
    ).result_rows
    if not rows:
        return ""
    return str(rows[0][0] or "")


def _from_clause(table: str, engine: str) -> str:
    """Append FINAL only for MergeTree-family tables (not Views)."""
    eng = (engine or "").lower()
    if "view" in eng:
        return table
    return f"{table} FINAL"


class ColRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["col"] = "col"
    name: str


class LitVal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["lit"] = "lit"
    value: float | int | str | bool


Operand = ColRef | LitVal


class CmpEq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["eq"] = "eq"
    left: Operand
    right: Operand


class CmpNeq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["neq"] = "neq"
    left: Operand
    right: Operand


class CmpGt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["gt"] = "gt"
    left: Operand
    right: Operand


class CmpGte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["gte"] = "gte"
    left: Operand
    right: Operand


class CmpLt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["lt"] = "lt"
    left: Operand
    right: Operand


class CmpLte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["lte"] = "lte"
    left: Operand
    right: Operand


class CmpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["in"] = "in"
    left: Operand
    values: list[LitVal] = Field(min_length=1)


class CmpBetween(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["between"] = "between"
    value: Operand
    min: LitVal
    max: LitVal


class AllWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["all"] = "all"
    items: list["WhereExpr"]


class AnyWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["any"] = "any"
    items: list["WhereExpr"]


class NotWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["not"] = "not"
    item: "WhereExpr"


WhereExpr = Annotated[
    Union[
        AllWhere,
        AnyWhere,
        NotWhere,
        CmpEq,
        CmpNeq,
        CmpGt,
        CmpGte,
        CmpLt,
        CmpLte,
        CmpIn,
        CmpBetween,
    ],
    Field(discriminator="type"),
]

AllWhere.model_rebuild()
AnyWhere.model_rebuild()
NotWhere.model_rebuild()


class OrderByItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    direction: Literal["ASC", "DESC"] = "DESC"

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction_casing(cls, v: Any) -> Any:
        # universe_query_v1 uses lowercase asc/desc; accept any casing here so
        # agents moving between the two contracts need not remember which is which.
        if isinstance(v, str):
            return v.upper()
        return v


# Advisory hints only: common universe-level computed aliases (universe_query_v1
# ``computed``) that do not exist as physical columns on any single L7 table.
# Spec authors may define more; this list covers the preset/shipped ones.
_UNIVERSE_COMPUTED_ALIASES = frozenset(
    {
        "setup_pass",
        "hit_count",
        "screens_hit",
        "screens_hit_w",
        "conf_scale",
        "w_conviction",
        "mag_thrust",
        "insight_dir",
        "eps_beat",
        "ary_eps",
        "arq_eps",
        "ary_rev",
        "arq_rev",
        "code_33",
    }
)


def unknown_column_error(
    tbl: str, name: str, col_set: "set[str] | frozenset[str]"
) -> ValueError:
    """Build an actionable error for an unknown column reference."""
    import difflib

    n = str(name).strip().strip("`")
    hints: list[str] = []
    close = difflib.get_close_matches(n, sorted(col_set), n=3)
    if close:
        hints.append(f"did you mean: {', '.join(repr(c) for c in close)}?")
    if n in _UNIVERSE_COMPUTED_ALIASES:
        hints.append(
            f"{n!r} is a universe-level computed alias (universe_query_v1.computed), "
            f"not a physical column on {tbl}; query it via POST /v1/universe/run "
            f"(see docs/UNIVERSE_QUERY_V1_LLM.md)"
        )
    detail = f"unknown column for {tbl}: {name!r}"
    if hints:
        detail += " (" + "; ".join(hints) + ")"
    return ValueError(detail)


class TableQueryV1Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    sql: str | None = Field(
        default=None,
        description=(
            "ClickHouse SELECT over catalog tables. Each FROM/JOIN table requires "
            "AS <catalog prefix>. XOR with from/select/where."
        ),
        examples=[SQL_JOIN_EXAMPLE],
    )
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Catalog table or view name in the session database",
    )
    select: list[str] | None = Field(
        default=None,
        description='Column names, or ["*"] for all columns (JSON path only)',
    )
    where: WhereExpr | None = None
    order_by: list[OrderByItem] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _shape(self) -> TableQueryV1Spec:
        sql = (self.sql or "").strip() or None
        has_sql = sql is not None
        has_from = bool(self.from_)
        has_select = bool(self.select)
        has_where = self.where is not None
        if has_sql and (has_from or has_select or has_where):
            raise ValueError("spec.sql is XOR with from/select/where")
        if has_sql:
            object.__setattr__(self, "sql", sql)
            if self.order_by:
                raise ValueError("order_by is not allowed with spec.sql (put ORDER BY in the SQL)")
            if self.offset:
                raise ValueError("offset is not allowed with spec.sql")
            return self
        if not has_from or not has_select:
            raise ValueError("from and select are required when sql is omitted")
        if self.from_ and self.from_.strip().lower() in ("daily_screener", "screener"):
            raise ValueError(
                f"Table {self.from_!r} does not exist. The screener is an L7 star schema rooted at spine table "
                f"'screener_price_tech_daily' (joined with screener_ratings_daily, screener_fundamentals_daily, "
                f"screener_estimates_daily, etc. on ticker, date). Query 'screener_price_tech_daily' directly "
                f"or use universe_query_v1 / screen_stocks."
            )
        return self


def _max_rows() -> int:
    return int(os.environ.get("MCP_MAX_ROWS", "500").strip())


def _default_limit() -> int:
    return int(os.environ.get("MCP_DEFAULT_LIMIT", "50").strip())


def _clamp_limit(limit: int | None, max_rows: int | None = None) -> int:
    mx = max_rows if max_rows is not None else _max_rows()
    d = _default_limit()
    v = d if limit is None else int(limit)
    if v < 1:
        v = 1
    return min(v, mx)


def _clamp_offset(offset: int | None) -> int:
    o = 0 if offset is None else int(offset)
    if o < 0:
        return 0
    max_off = int(os.environ.get("MCP_MAX_OFFSET", "10000").strip())
    return min(o, max_off)


def _quote_ch_ident(name: str) -> str:
    if "`" in name:
        raise RuntimeError(f"invalid ClickHouse identifier (backtick): {name!r}")
    if not re.fullmatch(r"[A-Za-z0-9_.]+", name):
        raise RuntimeError(f"unexpected ClickHouse identifier characters: {name!r}")
    return f"`{name}`"


def _col_set_from_describe(out: dict[str, Any]) -> frozenset[str]:
    cols = out.get("columns") or []
    return frozenset(str(c["name"]) for c in cols if isinstance(c, dict) and "name" in c)


def _emit_literal(v: object, params: dict[str, object], prefix: str) -> str:
    i = 0
    while f"{prefix}{i}" in params:
        i += 1
    k = f"{prefix}{i}"
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
    raise ValueError(f"unsupported literal: {v!r}")


def table_query_v1_json_schema() -> dict[str, Any]:
    """JSON Schema for MCP ``query_table_v1_spec_schema`` (catalog prefixes + SQL example)."""
    schema = TableQueryV1Spec.model_json_schema()
    defs = schema.setdefault("$defs", {})
    defs.update(catalog_schema_defs())
    schema["description"] = (
        "XOR: spec.sql (catalog joins with required AS prefixes) or from+select JSON AST. "
        "list/describe/query_table_v1 only see mcp_table_catalog.yaml tables. "
        "screen_stocks and mcp-clickhouse are unrestricted."
    )
    schema["examples"] = [
        {"version": 1, "sql": SQL_JOIN_EXAMPLE},
        {
            "version": 1,
            "from": "screener_ownership_daily",
            "select": ["ticker", "date", "inst_shrholders_qoq_delta"],
            "limit": 25,
        },
    ]
    return schema


def compile_table_query_v1(
    client: clickhouse_connect.driver.Client,
    spec: dict[str, Any],
    *,
    max_rows: int | None = None,
) -> tuple[str, dict[str, object], dict[str, Any]]:
    """Compile a catalog-validated query for bounded buffered or streaming execution."""
    q = TableQueryV1Spec.model_validate(spec)
    if q.sql:
        compiled, _params, alias_tables = compile_screener_sql(
            q.sql, limit_override=q.limit, max_rows=max_rows
        )
        columns: dict[str, frozenset[str]] = {}
        database = session_database(client)
        for prefix, table in alias_tables.items():
            desc = query_describe_table(client, table)
            database = str(desc.get("database") or database)
            columns[prefix] = _col_set_from_describe(desc)
        compiled, params, alias_tables = compile_screener_sql(
            q.sql, columns=columns, limit_override=q.limit, max_rows=max_rows
        )
        return compiled, params, {
            "database": database, "table": ",".join(alias_tables.values()),
            "aliases": alias_tables, "limit": int(params.get("lim") or _clamp_limit(q.limit)),
            "offset": 0,
        }
    assert q.from_ is not None and q.select is not None
    tbl = validate_table_identifier(q.from_)
    desc = query_describe_table(client, tbl)
    col_set = _col_set_from_describe(desc)

    def col_sql(name: str) -> str:
        n = name.strip().strip("`")
        if n not in col_set:
            raise unknown_column_error(tbl, name, col_set)
        return _quote_ch_ident(n)

    params: dict[str, object] = {}

    def emit_operand(op: ColRef | LitVal, pfx: str) -> str:
        if isinstance(op, ColRef):
            return col_sql(op.name)
        return _emit_literal(op.value, params, pfx + "lit_")

    def compile_where(expr: WhereExpr, pfx: str, depth: int) -> str:
        if depth > MAX_WHERE_DEPTH:
            raise ValueError(f"where expression exceeds max depth {MAX_WHERE_DEPTH}")
        if isinstance(expr, AnyWhere):
            if not expr.items:
                return "0"
            parts = [compile_where(x, f"{pfx}o{i}_", depth + 1) for i, x in enumerate(expr.items)]
            return " OR ".join(f"({p})" for p in parts)
        if isinstance(expr, NotWhere):
            inner = compile_where(expr.item, f"{pfx}n_", depth + 1)
            return f"NOT ({inner})"
        if isinstance(expr, AllWhere):
            if not expr.items:
                return "1"
            parts = [compile_where(x, f"{pfx}a{i}_", depth + 1) for i, x in enumerate(expr.items)]
            return " AND ".join(f"({p})" for p in parts)

        opmap = {
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "eq": "=",
            "neq": "!=",
        }
        if isinstance(expr, (CmpGt, CmpGte, CmpLt, CmpLte, CmpEq, CmpNeq)):
            left_sql = emit_operand(expr.left, f"{pfx}L_")
            right_sql = emit_operand(expr.right, f"{pfx}R_")
            return f"{left_sql} {opmap[expr.type]} {right_sql}"
        if isinstance(expr, CmpIn):
            left_sql = emit_operand(expr.left, f"{pfx}L_")
            vals = [v.value for v in expr.values]
            if not all(isinstance(x, str) for x in vals):
                raise ValueError("in operator currently supports string literals only")
            key = f"{pfx}in"
            i = 0
            while f"{key}_{i}" in params:
                i += 1
            k = f"{key}_{i}"
            params[k] = [str(x) for x in vals]
            return f"{left_sql} IN {{{k}:Array(String)}}"
        if isinstance(expr, CmpBetween):
            v = emit_operand(expr.value, f"{pfx}V_")
            lo = _emit_literal(expr.min.value, params, f"{pfx}lo_")
            hi = _emit_literal(expr.max.value, params, f"{pfx}hi_")
            return f"{v} BETWEEN {lo} AND {hi}"
        raise ValueError(f"unsupported where node: {type(expr).__name__}")

    if q.select == ["*"]:
        select_cols = [col_sql(str(x["name"])) for x in desc["columns"]]  # type: ignore[index]
        select_sql = ", ".join(select_cols) if select_cols else "*"
    else:
        select_sql = ", ".join(col_sql(c) for c in q.select)

    where_sql = ""
    if q.where is not None:
        where_sql = "WHERE " + compile_where(q.where, "w_", 0)

    order_sql = ""
    if q.order_by:
        parts = []
        for ob in q.order_by:
            d = ob.direction.upper()
            if d not in ("ASC", "DESC"):
                raise ValueError("order_by.direction must be ASC or DESC")
            parts.append(f"{col_sql(ob.field)} {d}")
        order_sql = "ORDER BY " + ", ".join(parts)

    lim = _clamp_limit(q.limit, max_rows=max_rows)
    off = _clamp_offset(q.offset)
    params["lim"] = lim
    params["off"] = off

    from_sql = _from_clause(tbl, _table_engine(client, tbl))
    sql = f"""
    SELECT {select_sql}
    FROM {from_sql}
    {where_sql}
    {order_sql}
    LIMIT {{lim:UInt32}} OFFSET {{off:UInt32}}
    """.strip()
    return sql, params, {
        "database": desc["database"], "table": tbl, "limit": lim, "offset": off,
    }


def run_table_query_v1(
    client: clickhouse_connect.driver.Client,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Execute a validated ``table_query_v1`` against ClickHouse."""
    sql, params, metadata = compile_table_query_v1(client, spec)
    result = client.query(sql, parameters=params)
    rows = rows_to_dicts(result)
    return {
        **metadata,
        "row_count": len(rows),
        "sql": sql,
        "rows": rows,
    }
