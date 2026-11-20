"""The canonical Vera expression dialect (C-VERA-EXPR-V1) — one dialect, one home.

VeraBase and VeraTradingLab previously declared **two** dialects with colliding
discriminators: VeraBase's `gte` carried `left`/`right` *operands*, VeraTradingLab's
carried a flat `column`/`value`. That divergence produced false validation failures
whenever one side could not import the other, and it is what this package removes.

Structural facts established before the move (2026-10-02):

* VeraBase's dialect is a superset of what the stored corpus uses — 20 nodes, nested
  operands (`col`/`lit`/`formula`), including `gt`/`lt` which VeraTradingLab's lacked.
* The flat `column`/`value` form has **no producer, no consumer and zero corpus specs**;
  its only references were the validators inside VeraTradingLab's own module. It is
  therefore dropped rather than normalised, so one class exists per discriminator.
* `regime_allows_entries` existed only in VeraTradingLab and is added here.
* `regime.source` existed only in VeraTradingLab and was added upstream during the
  spec-lint slice.

This module must stay **pydantic-only** — no pandas, clickhouse, fastapi, or Lean. It is
shipped into the LEAN container, where those are absent. `tests/test_purity.py` enforces it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

MAX_BOOL_DEPTH = 24
MAX_FORMULA_DEPTH = 8


class ColRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["col"] = "col"
    name: str
    offset: int = 0


class PosRef(BaseModel):
    """Runtime position binding (C-VERA-EXPR-V2).

    Resolves a field of the *open position context* — ``entry``, ``r``,
    ``current_stop``, ``days_held``, tranche flags, … — supplied by the slot
    evaluator's ``position`` argument. It is **not a row column**: a row-only
    evaluation (universe ``where`` / ``computed``) resolves it to ``None``,
    and consumers compiling to SQL must reject it.

    Deprecated spelling: ``{"type":"pos","field":f}`` is the same binding as
    ``{"type":"ref","ns":"pos","field":f}``. New specs should author ``ref``;
    ``pos`` remains valid and evaluates identically.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["pos"] = "pos"
    field: str


class BindingRef(BaseModel):
    """Namespaced runtime binding (C-VERA-EXPR-V2).

    Resolves ``ns.field`` against runtime-supplied context dicts — ``pos``
    (open position), ``hold`` (held-holding state), ``cand`` (candidate
    insight), ``acct`` (portfolio/account), ``pyr`` (pyramid phase),
    ``regime`` (regime inputs), and any namespace a consumer registers. The
    slot evaluator merges each context dict under ``__<ns>.``; a missing
    namespace or field resolves to ``None`` (fails closed in comparisons).

    Not a row column: row-only evaluation sees ``None``, and consumers
    compiling to SQL must reject it.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["ref"] = "ref"
    ns: str = Field(min_length=1)
    field: str = Field(min_length=1)


class LitVal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["lit"] = "lit"
    value: float | int | str | bool


class FormulaExpr(BaseModel):
    """Binary arithmetic formula operand (C-VERA-EXPR); nests via ``args``."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["formula"] = "formula"
    op: Literal["+", "-", "*", "/"]
    args: list["Operand"]

    @model_validator(mode="after")
    def _arity(self) -> FormulaExpr:
        if len(self.args) != 2:
            raise ValueError("formula requires exactly 2 args")
        return self


class MinExpr(BaseModel):
    """N-ary minimum operand (C-VERA-EXPR); ``args`` may nest."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["min"] = "min"
    args: list["Operand"] = Field(min_length=1)


class MaxExpr(BaseModel):
    """N-ary maximum operand (C-VERA-EXPR); ``args`` may nest."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["max"] = "max"
    args: list["Operand"] = Field(min_length=1)


class ClampExpr(BaseModel):
    """``clamp(value, min, max)`` — the quant's bound; ``min(max(value, lo), hi)``."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["clamp"] = "clamp"
    value: "Operand"
    min: "Operand"
    max: "Operand"


class AbsExpr(BaseModel):
    """Absolute value operand."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["abs"] = "abs"
    arg: "Operand"


class CmpGt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["gt"] = "gt"
    left: "Operand"
    right: "Operand"


class CmpGte(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["gte"] = "gte"
    left: "Operand"
    right: "Operand"


class CmpLt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["lt"] = "lt"
    left: "Operand"
    right: "Operand"


class CmpLte(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["lte"] = "lte"
    left: "Operand"
    right: "Operand"


class CmpEq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["eq"] = "eq"
    left: "Operand"
    right: "Operand"


class CmpNeq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["neq"] = "neq"
    left: "Operand"
    right: "Operand"


class ColGteExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["col_gte"] = "col_gte"
    column: str
    value: float | int


class ColLteExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["col_lte"] = "col_lte"
    column: str
    value: float | int


class ColEqExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["col_eq"] = "col_eq"
    column: str
    value: bool | float | int


class ColBetweenExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["between"] = "between"
    column: str
    min: float | int
    max: float | int

    @model_validator(mode="after")
    def _order(self) -> ColBetweenExpr:
        if float(self.min) > float(self.max):
            raise ValueError("between min must be <= max")
        return self


class InTickersExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["in_tickers"] = "in_tickers"
    tickers: list[str] = Field(min_length=1)


class AllExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["all"] = "all"
    items: list["BoolExprItem"]
    name: str | None = None


class AnyExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["any"] = "any"
    items: list["BoolExprItem"]
    name: str | None = None


class NotExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["not"] = "not"
    item: "BoolExprItem"


class SignalExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["signal"] = "signal"
    ticker: str
    column: str
    gt: float | int | None = None
    gte: float | int | None = None
    lt: float | int | None = None
    lte: float | int | None = None
    eq: bool | float | int | None = None

    @model_validator(mode="after")
    def _one_op(self) -> SignalExpr:
        ops = [self.gt, self.gte, self.lt, self.lte, self.eq]
        if sum(x is not None for x in ops) != 1:
            raise ValueError("signal requires exactly one of gt, gte, lt, lte, eq")
        return self


class RegimeExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["regime"] = "regime"
    field: str
    # Data source for the field ("regime", "vix", "macro", "technical", ...). The
    # VeraTradingLab dialect has always accepted this; this module did not, so a spec
    # carrying it failed validation whenever that dialect was unavailable — which is
    # exactly the case in the Studio process, where `vera_lab` is not importable. Nine
    # `regime` nodes in the stored corpus use it.
    source: str = "regime"
    eq: bool | float | int | None = None
    gte: float | int | None = None

    @model_validator(mode="after")
    def _one_op(self) -> RegimeExpr:
        if (self.eq is None) == (self.gte is None):
            raise ValueError("regime requires exactly one of eq or gte")
        return self


class SignalCompareExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["signal_compare"] = "signal_compare"
    ticker: str
    left: str
    op: Literal["lt", "lte", "gt", "gte", "eq"]
    right: str


class RegimeMartAllowsEntriesExpr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["regime_mart_allows_entries"] = "regime_mart_allows_entries"
    eq: bool | int = 1



class RegimeAllowsEntriesExpr(BaseModel):
    """Regime-gate admission. VeraTradingLab-only until now; folded in on consolidation."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["regime_allows_entries"] = "regime_allows_entries"
    eq: bool | int = 1


class CondExpr(BaseModel):
    """Piecewise operand (C-VERA-EXPR-V2): ``when`` selects ``then`` or ``otherwise``.

    ``when`` is evaluated with **fail-closed slot semantics** — missing columns or an
    unevaluatable predicate resolve to false, so ``otherwise`` is the graceful-fallback
    branch (e.g. percent stop when ``atr`` is absent). ``otherwise`` is named, not
    ``else``, because ``else`` is a Python keyword and aliases would leak into
    serialization everywhere.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["cond"] = "cond"
    when: "BoolExprItem"
    then: "Operand"
    otherwise: "Operand"


BoolExprItem = Annotated[
    Union[
        AllExpr,
        AnyExpr,
        NotExpr,
        CmpGt,
        CmpGte,
        CmpLt,
        CmpLte,
        CmpEq,
        CmpNeq,
        ColGteExpr,
        ColLteExpr,
        ColEqExpr,
        ColBetweenExpr,
        InTickersExpr,
        SignalExpr,
        RegimeExpr,
        SignalCompareExpr,
        RegimeMartAllowsEntriesExpr,
        RegimeAllowsEntriesExpr,
    ],
    Field(discriminator="type"),
]

# Value-level union (C-VERA-EXPR-V2): arithmetic, aggregate, and piecewise operands.
# Defined after BoolExprItem so `cond` can carry a boolean `when` and still nest inside
# operands (all field annotations above use the "Operand" forward ref, resolved by the
# model_rebuild calls below).
Operand = Annotated[
    Union[ColRef, PosRef, BindingRef, LitVal, FormulaExpr, MinExpr, MaxExpr, ClampExpr, AbsExpr, CondExpr],
    Field(discriminator="type"),
]

# Spec-facing union: a Framework expression field may root at a boolean expression **or** a
# bare operand — `weight_expr` is `{"type": "col", ...}` in 75 stored specs, and
# `confidence_expr` roots at `col`/`formula`. Typing those fields as `dict` (which is what
# they were) meant the AST schema was never enforced by the models at all. Typing them with
# this union makes Pydantic validate the entire tree recursively — node types, operators,
# `extra="forbid"` at every level, and `FormulaExpr`'s arity rule — with no bespoke linter.
SpecExpr = Annotated[
    Union[
        AllExpr,
        AnyExpr,
        NotExpr,
        CmpGt,
        CmpGte,
        CmpLt,
        CmpLte,
        CmpEq,
        CmpNeq,
        ColGteExpr,
        ColLteExpr,
        ColEqExpr,
        ColBetweenExpr,
        InTickersExpr,
        SignalExpr,
        RegimeExpr,
        SignalCompareExpr,
        RegimeMartAllowsEntriesExpr,
        RegimeAllowsEntriesExpr,
        ColRef,
        PosRef,
        BindingRef,
        LitVal,
        FormulaExpr,
        MinExpr,
        MaxExpr,
        ClampExpr,
        AbsExpr,
        CondExpr,
    ],
    Field(discriminator="type"),
]

WhereExpr = Annotated[
    Union[AllExpr, AnyExpr, NotExpr, CmpGt, CmpGte, CmpLt, CmpLte, CmpEq, CmpNeq],
    Field(discriminator="type"),
]

FormulaExpr.model_rebuild()
MinExpr.model_rebuild()
MaxExpr.model_rebuild()
ClampExpr.model_rebuild()
AbsExpr.model_rebuild()
CmpGt.model_rebuild()
CmpGte.model_rebuild()
CmpLt.model_rebuild()
CmpLte.model_rebuild()
CmpEq.model_rebuild()
CmpNeq.model_rebuild()
AllExpr.model_rebuild()
AnyExpr.model_rebuild()
NotExpr.model_rebuild()
CondExpr.model_rebuild()

_BOOL_ADAPTER = TypeAdapter(BoolExprItem)


def parse_bool_expr(data: Any) -> BoolExprItem:
    return _BOOL_ADAPTER.validate_python(data)


def is_runtime_only_expr(item: BoolExprItem) -> bool:
    return isinstance(
        item,
        (SignalExpr, RegimeExpr, SignalCompareExpr, RegimeMartAllowsEntriesExpr,
         RegimeAllowsEntriesExpr),
    )


def bool_expr_depth(item: BoolExprItem) -> int:
    if isinstance(
        item,
        (
            CmpGt,
            CmpGte,
            CmpLt,
            CmpLte,
            CmpEq,
            CmpNeq,
            ColGteExpr,
            ColLteExpr,
            ColEqExpr,
            ColBetweenExpr,
            InTickersExpr,
            SignalExpr,
            RegimeExpr,
            SignalCompareExpr,
            RegimeMartAllowsEntriesExpr,
            RegimeAllowsEntriesExpr,
        ),
    ):
        return 1
    if isinstance(item, NotExpr):
        return 1 + bool_expr_depth(item.item)
    if isinstance(item, (AllExpr, AnyExpr)):
        if not item.items:
            return 1
        return 1 + max(bool_expr_depth(x) for x in item.items)
    raise TypeError(type(item))


def validate_bool_expr_depth(item: BoolExprItem) -> None:
    d = bool_expr_depth(item)
    if d > MAX_BOOL_DEPTH:
        raise ValueError(f"bool expression exceeds max depth {MAX_BOOL_DEPTH} (got {d})")
