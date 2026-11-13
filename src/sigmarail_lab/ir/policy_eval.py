"""Evaluate BoolExpr policy conditions (runtime-only nodes) against SignalContext."""

from __future__ import annotations

from typing import Any

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
    RegimeExpr,
    RegimeAllowsEntriesExpr,
    RegimeMartAllowsEntriesExpr,
    SignalCompareExpr,
    SignalExpr,
)
from .signal_context import SignalContext


def _num(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _bool_val(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(int(val))
    return bool(val)


def evaluate_bool_expr(item: BoolExprItem, ctx: SignalContext, algorithm=None) -> bool:
    if isinstance(item, SignalExpr):
        v = _num(ctx.get(item.ticker, item.column))
        if item.gt is not None:
            return v > float(item.gt)
        if item.gte is not None:
            return v >= float(item.gte)
        if item.lt is not None:
            return v < float(item.lt)
        if item.lte is not None:
            return v <= float(item.lte)
        if item.eq is not None:
            if isinstance(item.eq, bool):
                return _bool_val(ctx.get(item.ticker, item.column)) == item.eq
            return v == float(item.eq)
        return False
    if isinstance(item, RegimeExpr):
        rv = ctx.regime(item.field, item.source)
        if algorithm:
            algorithm.Debug(f"POLICY EVAL: RegimeExpr field={item.field} source={item.source} eq={item.eq} gte={item.gte} -> value={rv}")
        if item.eq is not None:
            if isinstance(item.eq, bool):
                return _bool_val(rv) == item.eq
            return _num(rv) == float(item.eq)
        if item.gte is not None:
            return _num(rv) >= float(item.gte)
        return False
    if isinstance(item, (RegimeAllowsEntriesExpr, RegimeMartAllowsEntriesExpr)):
        return evaluate_bool_expr(
            RegimeExpr(type="regime", field="spy_above200d", eq=bool(item.eq)),
            ctx,
            algorithm,
        )
    if isinstance(item, SignalCompareExpr):
        left = _num(ctx.get(item.ticker, item.left))
        right = _num(ctx.get(item.ticker, item.right))
        if item.op == "lt":
            return left < right
        if item.op == "lte":
            return left <= right
        if item.op == "gt":
            return left > right
        if item.op == "gte":
            return left >= right
        return left == right
    if isinstance(item, AllExpr):
        result = all(evaluate_bool_expr(x, ctx, algorithm) for x in item.items) if item.items else True
        if algorithm:
            algorithm.Debug(f"POLICY EVAL: AllExpr -> {result}")
        return result
    if isinstance(item, AnyExpr):
        result = any(evaluate_bool_expr(x, ctx, algorithm) for x in item.items) if item.items else False
        if algorithm:
            algorithm.Debug(f"POLICY EVAL: AnyExpr -> {result}")
        return result
    if isinstance(item, NotExpr):
        result = not evaluate_bool_expr(item.item, ctx, algorithm)
        if algorithm:
            algorithm.Debug(f"POLICY EVAL: NotExpr -> {result}")
        return result
    if isinstance(item, (ColGteExpr, ColLteExpr, ColEqExpr, ColBetweenExpr, InTickersExpr)):
        raise ValueError(
            f"{item.type!r} is for SQL filters; use signal/regime nodes in graph if conditions"
        )
    raise TypeError(type(item))


def evaluate_condition_dict(raw: dict[str, Any], ctx: SignalContext) -> bool:
    from pydantic import TypeAdapter

    from sigmarail_spec import BoolExprItem as _Item

    item = TypeAdapter(_Item).validate_python(raw)
    return evaluate_bool_expr(item, ctx)
