"""Versioned, module-aware read-query contracts.

The contract names logical datasets and stable field IDs. A module owns the mapping
from those IDs to physical columns and declared join relationships; callers do not
provide SQL identifiers or join expressions. Optional computed fields are bounded,
typed expressions compiled by the owning query service.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_QUERY_EXPR_DEPTH = 8
MAX_QUERY_EXPR_NODES = 63
MAX_QUERY_PREDICATE_DEPTH = 24
MAX_QUERY_PREDICATE_NODES = 255
MAX_QUERY_COMPUTED_FIELDS = 50
MAX_QUERY_COMPUTED_INPUTS = 50
_ALIAS_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
QueryAliasName = Annotated[str, Field(min_length=1, max_length=64, pattern=_ALIAS_PATTERN)]


class QueryFieldExpression(BaseModel):
    """Read one field in the selected dataset/join scope."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["field"] = "field"
    field_id: str = Field(min_length=1)
    offset: int = Field(default=0, ge=-3650, le=3650)


class QueryLiteralExpression(BaseModel):
    """A scalar constant; query values are still bound as SQL parameters."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["literal"] = "literal"
    value: int | float | str | bool

    @model_validator(mode="after")
    def validate_literal(self) -> "QueryLiteralExpression":
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("literal numbers must be finite")
        if isinstance(self.value, str) and len(self.value) > 1024:
            raise ValueError("literal strings cannot exceed 1024 characters")
        return self


class QueryAliasExpression(BaseModel):
    """Reference an earlier computed result in the same query."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["alias"] = "alias"
    alias: QueryAliasName


class QueryArithmeticExpression(BaseModel):
    """Binary arithmetic over field, literal, or prior-alias expressions."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["arithmetic"] = "arithmetic"
    op: Literal["+", "-", "*", "/"]
    args: list["QueryExpression"] = Field(min_length=2, max_length=2)


QueryExpression = Annotated[
    Union[
        QueryFieldExpression,
        QueryLiteralExpression,
        QueryAliasExpression,
        QueryArithmeticExpression,
    ],
    Field(discriminator="type"),
]
QueryArithmeticExpression.model_rebuild()


class QueryPredicate(BaseModel):
    """Boolean filter tree with a backward-compatible field/literal shorthand.

    Older requests may continue to use ``{"op":"gte", "field_id":..., "value":...}``.
    New requests can compare two typed expressions with ``left`` and ``right``; this
    enables schema-bound comparisons such as ``close > high_52w`` without SQL text.
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal[
        "all", "any", "not", "eq", "neq", "gt", "gte", "lt", "lte",
        "is_null", "is_not_null",
    ]
    field_id: str | None = None
    value: int | float | str | bool | None = None
    left: QueryExpression | None = None
    right: QueryExpression | None = None
    items: list["QueryPredicate"] = Field(default_factory=list, max_length=50)
    item: "QueryPredicate | None" = None

    @model_validator(mode="after")
    def validate_shape(self) -> "QueryPredicate":
        if self.op in {"all", "any"}:
            if (
                not self.items
                or self.field_id is not None
                or "value" in self.model_fields_set
                or self.left is not None
                or self.right is not None
                or self.item is not None
            ):
                raise ValueError("all/any require items and cannot include a field, value, operands, or item")
        elif self.op == "not":
            if (
                self.item is None
                or self.items
                or self.field_id is not None
                or "value" in self.model_fields_set
                or self.left is not None
                or self.right is not None
            ):
                raise ValueError("not requires exactly one item")
        elif self.op in {"is_null", "is_not_null"}:
            legacy = self.field_id is not None and "value" not in self.model_fields_set and self.left is None and self.right is None
            expression = self.field_id is None and "value" not in self.model_fields_set and self.left is not None and self.right is None
            if not (legacy or expression) or self.items or self.item is not None:
                raise ValueError("null checks require only a field_id or left expression")
        else:
            legacy = (
                bool(self.field_id)
                and "value" in self.model_fields_set
                and self.left is None
                and self.right is None
            )
            expression = (
                self.field_id is None
                and "value" not in self.model_fields_set
                and self.left is not None
                and self.right is not None
            )
            if not (legacy or expression) or self.items or self.item is not None:
                raise ValueError("comparisons require either field_id/value or left/right expressions")
        return self


QueryPredicate.model_rebuild()


class QueryComputedField(BaseModel):
    """A query-local bool or number emitted under a stable alias.

    Boolean fields use ``where``. Numeric fields use one of ``expr``,
    ``sum_aliases``, or ``mean_available``. Arithmetic and boolean calculations
    are evaluated by the query service in ClickHouse; they are not persisted.
    ``mean_available`` lists stable field IDs and averages the non-null values.
    """

    model_config = ConfigDict(extra="forbid")

    alias: QueryAliasName
    kind: Literal["bool", "number"]
    where: QueryPredicate | None = None
    expr: QueryExpression | None = None
    sum_aliases: list[QueryAliasName] | None = Field(default=None, min_length=1, max_length=MAX_QUERY_COMPUTED_INPUTS)
    mean_available: list[str] | None = Field(default=None, min_length=1, max_length=MAX_QUERY_COMPUTED_INPUTS)

    @model_validator(mode="after")
    def validate_shape(self) -> "QueryComputedField":
        payloads = [self.where is not None, self.expr is not None, self.sum_aliases is not None, self.mean_available is not None]
        if sum(payloads) != 1:
            raise ValueError("computed field requires exactly one of where, expr, sum_aliases, or mean_available")
        if self.kind == "bool" and self.where is None:
            raise ValueError("computed kind='bool' requires where")
        if self.kind == "number" and self.where is not None:
            raise ValueError("computed kind='number' requires expr, sum_aliases, or mean_available")
        if self.mean_available is not None and any(not field_id.strip() for field_id in self.mean_available):
            raise ValueError("mean_available entries must be non-empty stable field IDs")
        return self


class QueryField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1)
    alias: QueryAliasName | None = None


class QueryJoin(BaseModel):
    """Reference one join declared by a module manifest."""

    model_config = ConfigDict(extra="forbid")

    relationship_id: str = Field(min_length=1)


class QueryOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str | None = Field(default=None, min_length=1)
    expr: QueryExpression | None = None
    direction: Literal["asc", "desc"] = "asc"

    @model_validator(mode="after")
    def validate_shape(self) -> "QueryOrder":
        if (self.field_id is None) == (self.expr is None):
            raise ValueError("order item requires exactly one of field_id or expr")
        return self


def _expression_stats(expr: QueryExpression, depth: int = 1) -> tuple[int, set[str]]:
    if depth > MAX_QUERY_EXPR_DEPTH:
        raise ValueError(f"query expression exceeds maximum depth {MAX_QUERY_EXPR_DEPTH}")
    if isinstance(expr, QueryAliasExpression):
        return 1, {expr.alias}
    if isinstance(expr, QueryArithmeticExpression):
        nodes = 1
        aliases: set[str] = set()
        for arg in expr.args:
            count, refs = _expression_stats(arg, depth + 1)
            nodes += count
            aliases.update(refs)
        if nodes > MAX_QUERY_EXPR_NODES:
            raise ValueError(f"query expression exceeds maximum size {MAX_QUERY_EXPR_NODES} nodes")
        return nodes, aliases
    return 1, set()


def _predicate_alias_refs(predicate: QueryPredicate, depth: int = 1) -> set[str]:
    if depth > MAX_QUERY_PREDICATE_DEPTH:
        raise ValueError(f"query predicate exceeds maximum depth {MAX_QUERY_PREDICATE_DEPTH}")
    aliases: set[str] = set()
    for expr in (predicate.left, predicate.right):
        if expr is not None:
            _, refs = _expression_stats(expr)
            aliases.update(refs)
    if predicate.item is not None:
        aliases.update(_predicate_alias_refs(predicate.item, depth + 1))
    for item in predicate.items:
        aliases.update(_predicate_alias_refs(item, depth + 1))
    return aliases


def _validate_predicate_size(predicate: QueryPredicate, depth: int = 1) -> int:
    if depth > MAX_QUERY_PREDICATE_DEPTH:
        raise ValueError(f"query predicate exceeds maximum depth {MAX_QUERY_PREDICATE_DEPTH}")
    nodes = 1
    for expr in (predicate.left, predicate.right):
        if expr is not None:
            nodes += _expression_stats(expr)[0]
    if predicate.item is not None:
        nodes += _validate_predicate_size(predicate.item, depth + 1)
    for item in predicate.items:
        nodes += _validate_predicate_size(item, depth + 1)
    if nodes > MAX_QUERY_PREDICATE_NODES:
        raise ValueError(f"query predicate exceeds maximum size {MAX_QUERY_PREDICATE_NODES} nodes")
    return nodes


class DataQueryV1(BaseModel):
    """Bounded read query over registered datasets, joins, and computed measures."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    module_id: str = Field(pattern=r"^sigmarail\.[a-z][a-z0-9_]{0,61}$")
    dataset_id: str = Field(min_length=1)
    joins: list[QueryJoin] = Field(default_factory=list, max_length=12)
    select: list[QueryField] = Field(min_length=1, max_length=100)
    computed: list[QueryComputedField] = Field(default_factory=list, max_length=MAX_QUERY_COMPUTED_FIELDS)
    where: QueryPredicate | None = None
    post_where: QueryPredicate | None = None
    as_of_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    order_by: list[QueryOrder] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_query(self) -> "DataQueryV1":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be supplied together")
        if self.as_of_date is not None and self.start_date is not None:
            raise ValueError("choose as_of_date or a date range, not both")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")

        selected_aliases = [field.alias for field in self.select if field.alias is not None]
        if len(selected_aliases) != len(set(selected_aliases)):
            raise ValueError("selected field aliases must be unique")
        prior_aliases: set[str] = set()
        for computed in self.computed:
            if computed.alias in prior_aliases or computed.alias in selected_aliases:
                raise ValueError(f"computed alias {computed.alias!r} collides with a selected or prior alias")
            refs: set[str] = set()
            if computed.expr is not None:
                _, refs = _expression_stats(computed.expr)
            if computed.where is not None:
                _validate_predicate_size(computed.where)
                refs = _predicate_alias_refs(computed.where)
            if computed.sum_aliases is not None:
                refs = set(computed.sum_aliases)
            unknown = refs - prior_aliases
            if unknown:
                raise ValueError(
                    f"computed alias {computed.alias!r} references aliases that are not declared earlier: "
                    f"{sorted(unknown)}"
                )
            prior_aliases.add(computed.alias)

        if self.where is not None:
            _validate_predicate_size(self.where)
            aliases = _predicate_alias_refs(self.where)
            if aliases:
                raise ValueError("where cannot reference computed aliases; use post_where")
        if self.post_where is not None:
            _validate_predicate_size(self.post_where)
            unknown = _predicate_alias_refs(self.post_where) - prior_aliases
            if unknown:
                raise ValueError(f"post_where references unknown computed aliases: {sorted(unknown)}")
        for item in self.order_by:
            if item.expr is not None:
                unknown = _expression_stats(item.expr)[1] - prior_aliases
                if unknown:
                    raise ValueError(f"order_by references unknown computed aliases: {sorted(unknown)}")
        return self


__all__ = [
    "DataQueryV1",
    "QueryAliasExpression",
    "QueryArithmeticExpression",
    "QueryComputedField",
    "QueryExpression",
    "QueryField",
    "QueryFieldExpression",
    "QueryJoin",
    "QueryLiteralExpression",
    "QueryOrder",
    "QueryPredicate",
]
