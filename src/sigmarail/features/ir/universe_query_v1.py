"""JSON universe query v1: SELECT / WHERE / ORDER BY / limit_per_day over L7 screener joins.

``from: screener`` is the canonical logical source id (alias ``daily_screener`` is
deprecated); compiled SQL joins ``screener_*``.
Validated and compiled only in VeraBase (opaque dict on VeraTradingLab REST path).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- AST -----------------------------------------------------------------

_MAX_WHERE_DEPTH = 24
_MAX_FORMULA_DEPTH = 8


class ColRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["col"] = "col"
    name: str
    offset: int = 0


class LitVal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["lit"] = "lit"
    value: float | int | str | bool


class FormulaExpr(BaseModel):
    """Binary arithmetic formula operand; nests via ``args`` (C-VERA-EXPR)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["formula"] = "formula"
    op: Literal["+", "-", "*", "/"]
    args: list["Operand"]

    @model_validator(mode="after")
    def _arity(self) -> FormulaExpr:
        if len(self.args) != 2:
            raise ValueError("formula requires exactly 2 args")
        return self


Operand = ColRef | LitVal | FormulaExpr


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


class CmpEq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["eq"] = "eq"
    left: Operand
    right: Operand


class AllWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["all"] = "all"
    items: list["WhereExpr"]
    name: str | None = None


class AnyWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["any"] = "any"
    items: list["WhereExpr"]
    name: str | None = None


class NotWhere(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["not"] = "not"
    item: "WhereExpr"


WhereExpr = Annotated[
    Union[AllWhere, AnyWhere, NotWhere, CmpGt, CmpGte, CmpLt, CmpLte, CmpEq],
    Field(discriminator="type"),
]

FormulaExpr.model_rebuild()
CmpGt.model_rebuild()
CmpGte.model_rebuild()
CmpLt.model_rebuild()
CmpLte.model_rebuild()
CmpEq.model_rebuild()
AllWhere.model_rebuild()
AnyWhere.model_rebuild()
NotWhere.model_rebuild()

_COMPUTED_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ComputedSelect(BaseModel):
    """Named measure compiled into the SELECT list (C-UNIVERSE-QUERY-V1).

    Bool measures become ``toUInt8(<predicate>) AS alias``. Number measures use
    ``expr``, ``mean_available``, or ``sum_aliases`` (count combinator over prior
    bool aliases). Later computed items may ``col``-ref earlier aliases (same
    SELECT left-to-right reuse in ClickHouse).
    """

    model_config = ConfigDict(extra="forbid")

    alias: str
    kind: Literal["bool", "number"]
    where: WhereExpr | None = None
    expr: Operand | None = None
    mean_available: list[str] | None = None
    sum_aliases: list[str] | None = None

    @model_validator(mode="after")
    def _validate_alias_and_payload(self) -> ComputedSelect:
        if not _COMPUTED_ALIAS_RE.match(self.alias):
            raise ValueError(
                f"computed alias {self.alias!r} must match {_COMPUTED_ALIAS_RE.pattern}"
            )
        n_sources = sum(
            1
            for x in (self.where, self.expr, self.mean_available, self.sum_aliases)
            if x is not None
        )
        if n_sources != 1:
            raise ValueError(
                "computed requires exactly one of where / expr / mean_available / sum_aliases"
            )
        if self.kind == "bool" and self.where is None:
            raise ValueError("computed kind=bool requires where")
        if self.kind == "number" and self.where is not None:
            raise ValueError("computed kind=number cannot use where (use expr/sum_aliases)")
        if self.mean_available is not None and len(self.mean_available) == 0:
            raise ValueError("mean_available must be non-empty when set")
        if self.sum_aliases is not None and len(self.sum_aliases) == 0:
            raise ValueError("sum_aliases must be non-empty when set")
        if self.where is not None:
            _validate_where_depth(self.where)
        if self.expr is not None:
            depth = _operand_depth(self.expr)
            if depth > _MAX_FORMULA_DEPTH:
                raise ValueError(f"computed expr exceeds max depth {_MAX_FORMULA_DEPTH}")
        return self


class OrderByItem(BaseModel):
    """Single ORDER BY term: either an allowlisted ``field`` (must be in select)
    or a computed ``expr`` operand (ColRef / LitVal / FormulaExpr over allowlisted
    columns). Exactly one of ``field`` / ``expr`` must be present.
    """

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    expr: Operand | None = None
    direction: Literal["asc", "desc"] = "desc"

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction_casing(cls, v: Any) -> Any:
        # query_table_v1 uses uppercase ASC/DESC; accept any casing here so
        # agents moving between the two contracts need not remember which is which.
        if isinstance(v, str):
            return v.lower()
        return v

    @model_validator(mode="after")
    def _xor_field_expr(self) -> "OrderByItem":
        if (self.field is None) == (self.expr is None):
            raise ValueError("order_by item requires exactly one of 'field' or 'expr'")
        return self

    @model_validator(mode="after")
    def _expr_depth(self) -> "OrderByItem":
        if self.expr is not None:
            depth = _operand_depth(self.expr)
            if depth > _MAX_FORMULA_DEPTH:
                raise ValueError(f"order_by expr exceeds max depth {_MAX_FORMULA_DEPTH}")
        return self


class UniverseJoin(BaseModel):
    """Specification of a joined satellite table in a universe query."""

    model_config = ConfigDict(extra="forbid")

    table: str
    type: Literal["left_any", "inner", "left", "right", "full"] = "left_any"
    on: list[str]


class UniverseQueryV1(BaseModel):
    """Canonical JSON universe clause (version 1 or 2)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: Literal[1, 2] = 2
    spine: str = Field(
        default="screener_price_tech_daily",
        description="Physical spine table for universe queries (default: screener_price_tech_daily).",
    )
    joins: list[UniverseJoin] = Field(
        default_factory=list,
        description="Auto-resolved or explicit satellite table joins onto the spine.",
    )
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Legacy logical source alias (optional; 'screener' or 'daily_screener'). Ignored in favor of spine/joins.",
    )
    select: list[str] = Field(min_length=1)
    computed: list[ComputedSelect] = Field(default_factory=list)
    where: WhereExpr | None = Field(
        default=None,
        description="JSON boolean expression tree (preferred). Mutually exclusive with where_sql.",
    )
    where_sql: str | None = Field(
        default=None,
        max_length=2048,
        description=(
            "Optional ClickHouse-style predicate string (parsed with sqlglot, a core dependency). "
            "Mutually exclusive with where. Same allowlisted columns as JSON `col` refs."
        ),
    )
    order_by: list[OrderByItem] = Field(default_factory=list)
    limit_per_day: int = Field(ge=1, le=5000)
    post_where: WhereExpr | None = Field(
        default=None,
        description=(
            "Optional filter on SELECT/computed output aliases (e.g. screens_hit >= 2). "
            "Compiled as an outer WHERE around the inner projection so aliases are visible."
        ),
    )

    @model_validator(mode="after")
    def _validate_where_xor(self) -> "UniverseQueryV1":
        has_ast = self.where is not None
        has_sql = self.where_sql is not None and self.where_sql.strip() != ""
        if has_ast == has_sql:
            raise ValueError("Set exactly one of 'where' (JSON AST) or 'where_sql' (string predicate).")
        if has_ast:
            assert self.where is not None
            _validate_where_depth(self.where)
        if not self.joins:
            from sigmarail.features.ir.l7_from import resolve_joins_for_columns
            cols = _spec_column_names(self)
            resolved = resolve_joins_for_columns(cols)
            self.joins = [UniverseJoin(**j) for j in resolved]
        return self

    @model_validator(mode="after")
    def _validate_computed(self) -> "UniverseQueryV1":
        seen: set[str] = set(self.select)
        prior_aliases: list[str] = []
        for item in self.computed:
            if item.alias in seen:
                raise ValueError(f"computed alias {item.alias!r} collides with select or prior alias")
            if item.sum_aliases:
                for a in item.sum_aliases:
                    if a not in prior_aliases:
                        raise ValueError(
                            f"computed {item.alias!r} sum_aliases references unknown prior alias {a!r}"
                        )
            if item.mean_available:
                for name in item.mean_available:
                    _col_sql(name)
            if item.expr is not None:
                for name in _operand_column_names(item.expr):
                    if name in prior_aliases or name in seen:
                        continue
                    _col_sql(name)
            if item.where is not None:
                for name in _where_column_names(item.where):
                    if name in prior_aliases:
                        continue
                    _col_sql(name)
            seen.add(item.alias)
            prior_aliases.append(item.alias)
        return self

    @model_validator(mode="after")
    def _validate_order_by(self) -> "UniverseQueryV1":
        if not self.order_by:
            raise ValueError(
                "order_by must contain at least one item (deterministic order is required "
                "for backtest chunking). Minimal example: "
                '"order_by": [{"field": "overall_score", "direction": "desc"}] — the field '
                "must appear in select or computed. Full contract: docs/UNIVERSE_QUERY_V1_LLM.md "
                "or GET /openapi.json on the query service."
            )
        sel = set(self.select) | {c.alias for c in self.computed}
        prior = {c.alias for c in self.computed}
        for ob in self.order_by:
            if ob.field is not None:
                if ob.field not in sel:
                    raise ValueError(
                        f"order_by field {ob.field!r} must appear in select or computed "
                        f"(got select={sorted(self.select)!r}). Fix: add {ob.field!r} to "
                        "select (or a computed alias). Full contract: "
                        "docs/UNIVERSE_QUERY_V1_LLM.md or GET /openapi.json on the query service."
                    )
            elif ob.expr is not None:
                for name in _operand_column_names(ob.expr):
                    if name in prior:
                        continue
                    _col_sql(name)
        return self

    @model_validator(mode="after")
    def _validate_post_where(self) -> "UniverseQueryV1":
        if self.post_where is None:
            return self
        _validate_where_depth(self.post_where)
        sel = set(self.select) | {c.alias for c in self.computed}
        prior = set(sel)
        for name in _where_column_names(self.post_where):
            if name in prior:
                continue
            # Allow physical L7 cols too (rare in outer filter).
            _col_sql(name)
        return self


UniverseQueryV2 = UniverseQueryV1


# --- Column surface: schema-driven (see universe_v1_column_registry) --------

def universe_v1_allowed_columns() -> frozenset[str]:
    from sigmarail.features.ir.universe_v1_column_registry import get_universe_v1_col_sql_map

    return frozenset(get_universe_v1_col_sql_map().keys())


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


def universe_v1_column_sql_expression(name: str) -> str:
    """SQL expression (L7-qualified) for an allowlisted logical or qualified column name."""
    return _col_sql(name)[0]


def _operand_column_names(op: Operand) -> set[str]:
    if isinstance(op, ColRef):
        return {op.name}
    if isinstance(op, LitVal):
        return set()
    if isinstance(op, FormulaExpr):
        names: set[str] = set()
        for a in op.args:
            names |= _operand_column_names(a)
        return names
    return set()


def _operand_depth(op: Operand) -> int:
    """Nested depth of a formula operand tree (ColRef/LitVal = 0, Formula = 1 + max child)."""
    if isinstance(op, FormulaExpr):
        return 1 + max((_operand_depth(a) for a in op.args), default=0)
    return 0


def _where_column_names(expr: WhereExpr) -> set[str]:
    names: set[str] = set()
    if isinstance(expr, (CmpGt, CmpGte, CmpLt, CmpLte, CmpEq)):
        names |= _operand_column_names(expr.left)
        names |= _operand_column_names(expr.right)
        return names
    if isinstance(expr, NotWhere):
        return _where_column_names(expr.item)
    if isinstance(expr, (AllWhere, AnyWhere)):
        for item in expr.items:
            names |= _where_column_names(item)
        return names
    return names


def _order_by_column_names(spec: UniverseQueryV1) -> set[str]:
    """Every column referenced by ORDER BY (field names or expression operands)."""
    names: set[str] = set()
    for ob in spec.order_by:
        if ob.field is not None:
            names.add(ob.field)
        elif ob.expr is not None:
            names |= _operand_column_names(ob.expr)
    return names


def _spec_column_names(spec: UniverseQueryV1) -> set[str]:
    """Physical L7 columns needed for joins (excludes computed output aliases)."""
    names = set(spec.select)
    names |= _order_by_column_names(spec)
    if spec.where is not None:
        names |= _where_column_names(spec.where)
    if spec.where_sql:
        names |= {c.strip() for c in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", spec.where_sql)}
    computed_aliases = {c.alias for c in spec.computed}
    for item in spec.computed:
        if item.where is not None:
            names |= {n for n in _where_column_names(item.where) if n not in computed_aliases}
        if item.expr is not None:
            names |= {n for n in _operand_column_names(item.expr) if n not in computed_aliases}
        if item.mean_available:
            names |= set(item.mean_available)
    names -= computed_aliases
    names.update({"ticker", "date"})
    return names


def where_expr_depth(expr: WhereExpr) -> int:
    if isinstance(expr, (CmpGt, CmpGte, CmpLt, CmpLte, CmpEq)):
        return 1
    if isinstance(expr, NotWhere):
        return 1 + where_expr_depth(expr.item)
    if isinstance(expr, (AllWhere, AnyWhere)):
        if not expr.items:
            return 1
        return 1 + max(where_expr_depth(x) for x in expr.items)
    raise TypeError(type(expr))


def _validate_where_depth(expr: WhereExpr) -> None:
    if where_expr_depth(expr) > _MAX_WHERE_DEPTH:
        raise ValueError(f"where expression exceeds max depth {_MAX_WHERE_DEPTH}")


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
        if depth >= _MAX_FORMULA_DEPTH:
            raise ValueError(f"formula expression exceeds max depth {_MAX_FORMULA_DEPTH}")
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


def _compile_where(expr: WhereExpr, params: dict[str, object], pfx: str) -> str:
    from sigmarail.features.ir.vera_bool_expr import compile_bool_expr_sql, parse_bool_expr

    return compile_bool_expr_sql(parse_bool_expr(expr.model_dump()), params, pfx)


def universe_v1_result_column_names(select: list[str], computed: list[ComputedSelect] | None = None) -> frozenset[str]:
    """Output column names (`AS` aliases) for a v1 `select` (+ optional computed), including auto-injected `date`."""
    _, aliases = _compile_select_list(select, computed or [], {})
    return frozenset(aliases)


def _compile_mean_available(cols: list[str], params: dict[str, object], pfx: str) -> str:
    """Average of non-null allowlisted columns; NULL when all missing."""
    del params, pfx  # reserved for future parameterized companions
    parts: list[str] = []
    for name in cols:
        sql_expr, _ = _col_sql(name)
        parts.append(sql_expr)
    joined = ", ".join(parts)
    return f"arrayAvg([{joined}])"


def _compile_select_list(
    select: list[str],
    computed: list[ComputedSelect] | None = None,
    params: dict[str, object] | None = None,
) -> tuple[str, list[str]]:
    """Returns SELECT clause text and ordered output aliases (for ORDER BY)."""
    params = params if params is not None else {}
    computed = computed or []
    parts: list[str] = []
    seen_alias: set[str] = set()
    aliases: list[str] = []
    for raw in select:
        sql_expr, alias = _col_sql(raw)
        if alias in seen_alias:
            raise ValueError(f"duplicate select output alias: {alias!r}")
        seen_alias.add(alias)
        aliases.append(alias)
        parts.append(f"{sql_expr} AS {alias}")
    if "date" not in seen_alias:
        parts.insert(0, "toDate(px.date) AS date")
        aliases.insert(0, "date")
        seen_alias.add("date")

    prior_aliases: set[str] = set()
    for i, item in enumerate(computed):
        if item.alias in seen_alias:
            raise ValueError(f"duplicate select output alias: {item.alias!r}")
        if item.where is not None:
            pred = _compile_where_with_aliases(item.where, params, f"c{i}_", prior_aliases)
            frag = f"toUInt8(({pred})) AS {item.alias}"
        elif item.sum_aliases is not None:
            frag = f"({' + '.join(item.sum_aliases)}) AS {item.alias}"
        elif item.mean_available is not None:
            frag = f"{_compile_mean_available(item.mean_available, params, f'c{i}_')} AS {item.alias}"
        elif item.expr is not None:
            frag = f"({_emit_operand_with_aliases(item.expr, params, f'c{i}_', prior_aliases)}) AS {item.alias}"
        else:
            raise ValueError(f"computed {item.alias!r} has no payload")
        parts.append(frag)
        seen_alias.add(item.alias)
        aliases.append(item.alias)
        prior_aliases.add(item.alias)

    return ",\n                ".join(parts), aliases


def _emit_operand_with_aliases(
    op: Operand,
    params: dict[str, object],
    key_pfx: str,
    prior_aliases: set[str],
    *,
    depth: int = 0,
) -> str:
    """Emit operand SQL; prior computed aliases stay bare identifiers (incl. nested formulas)."""
    if isinstance(op, ColRef) and op.name in prior_aliases and op.offset == 0:
        return op.name
    if isinstance(op, FormulaExpr):
        if depth >= _MAX_FORMULA_DEPTH:
            raise ValueError(f"formula expression exceeds max depth {_MAX_FORMULA_DEPTH}")
        if len(op.args) != 2:
            raise ValueError("formula requires exactly 2 args")
        left_sql = _emit_operand_with_aliases(
            op.args[0], params, f"{key_pfx}fL", prior_aliases, depth=depth + 1
        )
        right_sql = _emit_operand_with_aliases(
            op.args[1], params, f"{key_pfx}fR", prior_aliases, depth=depth + 1
        )
        return f"({left_sql} {op.op} {right_sql})"
    return _emit_operand(op, params, key_pfx, depth=depth)


def _compile_where_with_aliases(
    expr: WhereExpr,
    params: dict[str, object],
    pfx: str,
    prior_aliases: set[str],
) -> str:
    """Compile WHERE; ColRefs that name prior computed aliases emit bare identifiers."""
    from sigmarail.features.ir.vera_bool_expr import compile_bool_expr_sql, parse_bool_expr

    physical_only = True
    for name in _where_column_names(expr):
        if name in prior_aliases:
            physical_only = False
            break
    if physical_only:
        return compile_bool_expr_sql(parse_bool_expr(expr.model_dump()), params, pfx)

    return _compile_where_expr_aliases(expr, params, pfx, prior_aliases)


def _compile_where_expr_aliases(
    expr: WhereExpr,
    params: dict[str, object],
    pfx: str,
    prior_aliases: set[str],
) -> str:
    op_map = {
        CmpGt: ">",
        CmpGte: ">=",
        CmpLt: "<",
        CmpLte: "<=",
        CmpEq: "=",
    }
    if isinstance(expr, (CmpGt, CmpGte, CmpLt, CmpLte, CmpEq)):
        left = _emit_operand_with_aliases(expr.left, params, f"{pfx}L", prior_aliases)
        right = _emit_operand_with_aliases(expr.right, params, f"{pfx}R", prior_aliases)
        return f"{left} {op_map[type(expr)]} {right}"
    if isinstance(expr, NotWhere):
        return f"NOT ({_compile_where_expr_aliases(expr.item, params, f'{pfx}n', prior_aliases)})"
    if isinstance(expr, AllWhere):
        if not expr.items:
            return "1"
        parts = [
            _compile_where_expr_aliases(x, params, f"{pfx}a{i}_", prior_aliases)
            for i, x in enumerate(expr.items)
        ]
        return " AND ".join(f"({p})" for p in parts)
    if isinstance(expr, AnyWhere):
        if not expr.items:
            return "0"
        parts = [
            _compile_where_expr_aliases(x, params, f"{pfx}o{i}_", prior_aliases)
            for i, x in enumerate(expr.items)
        ]
        return " OR ".join(f"({p})" for p in parts)
    raise TypeError(type(expr))


def _compile_where_clause(spec: UniverseQueryV1, params: dict[str, object]) -> str:
    if spec.where_sql is not None and spec.where_sql.strip():
        from sigmarail.features.ir.universe_where_sqlglot import compile_where_sql_fragment

        return compile_where_sql_fragment(spec.where_sql.strip(), params, prefix="ws_")
    assert spec.where is not None
    return _compile_where(spec.where, params, "w_")


def _compile_order_by_sql(
    spec: UniverseQueryV1, params: dict[str, object], *, pfx: str = "ob_"
) -> str:
    """Build the ORDER BY key list. ``field`` items resolve to output aliases
    (they must be selected); ``expr`` items compile to a parameterized
    ClickHouse expression over allowlisted columns."""
    order_parts: list[str] = []
    computed_aliases = {c.alias for c in spec.computed}
    for ob in spec.order_by:
        order_dir = "ASC" if ob.direction == "asc" else "DESC"
        if ob.field is not None:
            if ob.field in computed_aliases:
                order_parts.append(f"{ob.field} {order_dir}")
            else:
                _, sort_alias = _col_sql(ob.field)
                order_parts.append(f"{sort_alias} {order_dir}")
        elif ob.expr is not None:
            expr_sql = _emit_operand(ob.expr, params, pfx)
            order_parts.append(f"{expr_sql} {order_dir}")
    order_by_sql = ", ".join(order_parts) if order_parts else "px.ticker ASC"
    return order_by_sql


def strip_trailing_sql_settings(sql: str) -> str:
    """Remove a trailing ``SETTINGS …`` clause so the SQL can be nested as a subquery.

    ClickHouse rejects changing ``allow_experimental_analyzer`` (and similar)
    inside a subquery when the outer query also has SETTINGS (code 80).
    Callers that wrap range/single-day compiles must strip settings from the
    inner SQL and apply them only on the outermost statement (or via client
    query settings).
    """
    return re.sub(r"\s+SETTINGS\s+[\s\S]*\Z", "", (sql or "").rstrip(), flags=re.IGNORECASE).rstrip()


def _compile_post_where_clause(
    spec: UniverseQueryV1, params: dict[str, object]
) -> str | None:
    """Compile post_where against select+computed aliases (outer query)."""
    if spec.post_where is None:
        return None
    prior = set(spec.select) | {c.alias for c in spec.computed}
    return _compile_where_with_aliases(spec.post_where, params, "pw_", prior)


def compile_universe_query_v1_range_param(
    spec: UniverseQueryV1,
    *,
    for_aggregate: bool = False,
) -> tuple[str, dict[str, object]]:
    """Parameterized range query: caller sets start/end ISO strings and lim.

    ``for_aggregate=True`` omits ORDER BY / LIMIT BY — use when the caller only
    wraps the result in GROUP BY (membership counts / measure series). Ranking
    sort is wasted work for those paths and dominates probe latency.
    """
    params: dict[str, object] = {}
    where_sql = _compile_where_clause(spec, params)
    proj, _aliases = _compile_select_list(spec.select, spec.computed, params)
    from sigmarail.features.ir.l7_from import l7_from_sql

    from_sql = l7_from_sql(
        _spec_column_names(spec),
        date_between_sql="toDate({start:String}) AND toDate({end:String})",
    )
    if for_aggregate:
        sql = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date BETWEEN toDate({{start:String}}) AND toDate({{end:String}})
              AND ({where_sql})
            SETTINGS allow_experimental_analyzer = 0,
                     join_algorithm = 'grace_hash'
        """
        params["start"] = ""
        params["end"] = ""
        return sql, params

    order_by_sql = _compile_order_by_sql(spec, params)
    lim = int(spec.limit_per_day)
    post_sql = _compile_post_where_clause(spec, params)
    if post_sql:
        inner = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date BETWEEN toDate({{start:String}}) AND toDate({{end:String}})
              AND ({where_sql})
        """
        sql = f"""
            SELECT *
            FROM (
{strip_trailing_sql_settings(inner)}
            ) AS _ranked
            WHERE ({post_sql})
            ORDER BY date ASC, {order_by_sql}, ticker ASC
            LIMIT {{lim:UInt32}} BY date
            SETTINGS allow_experimental_analyzer = 0,
                     join_algorithm = 'grace_hash'
        """
    else:
        sql = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date BETWEEN toDate({{start:String}}) AND toDate({{end:String}})
              AND ({where_sql})
            ORDER BY px.date ASC, {order_by_sql}, px.ticker ASC
            LIMIT {{lim:UInt32}} BY px.date
            SETTINGS allow_experimental_analyzer = 0,
                     join_algorithm = 'grace_hash'
        """
    params["start"] = ""
    params["end"] = ""
    params["lim"] = lim
    return sql, params


def compile_universe_query_v1_single_day_param(spec: UniverseQueryV1) -> tuple[str, dict[str, object]]:
    """Parameterized single-day query: caller sets day ISO string and lim."""
    params: dict[str, object] = {}
    where_sql = _compile_where_clause(spec, params)
    proj, _aliases = _compile_select_list(spec.select, spec.computed, params)
    order_by_sql = _compile_order_by_sql(spec, params)
    lim = int(spec.limit_per_day)
    from sigmarail.features.ir.l7_from import l7_from_sql

    from_sql = l7_from_sql(_spec_column_names(spec))
    post_sql = _compile_post_where_clause(spec, params)
    if post_sql:
        inner = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date = toDate({{day:String}})
              AND ({where_sql})
        """
        sql = f"""
            SELECT *
            FROM (
{strip_trailing_sql_settings(inner)}
            ) AS _ranked
            WHERE ({post_sql})
            ORDER BY {order_by_sql}, ticker ASC
            LIMIT {{lim:UInt32}}
            SETTINGS allow_experimental_analyzer = 0
        """
    else:
        sql = f"""
            SELECT
                {proj}
            FROM {from_sql}
            WHERE px.date = toDate({{day:String}})
              AND ({where_sql})
            ORDER BY {order_by_sql}, px.ticker ASC
            LIMIT {{lim:UInt32}}
            SETTINGS allow_experimental_analyzer = 0
        """
    params["day"] = ""
    params["lim"] = lim
    return sql, params
