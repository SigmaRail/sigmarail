"""JSON universe query v1: portable contract for daily historical screener queries.

``from: screener`` is the canonical logical source id (alias ``daily_screener`` is
deprecated); compiled SQL joins ``screener_*``.
The SigmaRail service validates this contract against its generated field and join
catalogs and compiles it to its internal data-query representation. SQL compilation
does not belong in this portable specification package.
"""

from __future__ import annotations

import re
import json
from functools import lru_cache
from importlib.resources import files
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
        description="Logical query spine (default: screener_price_tech_daily).",
    )
    joins: list[UniverseJoin] = Field(
        default_factory=list,
        description="Legacy caller join declarations. SigmaRail resolves joins from registered fields.",
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
        for name in self.select:
            _validate_field_name(name)
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
                    _validate_field_name(name)
            if item.expr is not None:
                for name in _operand_column_names(item.expr):
                    if name in prior_aliases or name in seen:
                        continue
                    _validate_field_name(name)
            if item.where is not None:
                for name in _where_column_names(item.where):
                    if name in prior_aliases:
                        continue
                    _validate_field_name(name)
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
                    _validate_field_name(name)
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
            _validate_field_name(name)
        return self


UniverseQueryV2 = UniverseQueryV1


# --- Schema-driven field surface ------------------------------------------

@lru_cache(maxsize=1)
def universe_v1_allowed_columns() -> frozenset[str]:
    """Universe fields in the packaged SigmaRail catalog, generated from core SQL."""
    doc = json.loads(files("sigmarail_spec").joinpath("data/fields.json").read_text(encoding="utf-8"))
    universe_tables = {
        "screener_price_tech_daily",
        "screener_fundamentals_daily",
        "screener_ratings_daily",
        "screener_stage_weekly_daily",
        "screener_ownership_daily",
    }
    return frozenset(
        str(row["name"])
        for row in doc.get("fields", [])
        if row.get("name") and row.get("table") in universe_tables
    )


def _validate_field_name(name: str) -> None:
    key = str(name).strip().strip("`")
    bare = key.split(".", 1)[-1]
    if bare not in universe_v1_allowed_columns():
        raise ValueError(f"unknown or disallowed field: {name!r}")


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
