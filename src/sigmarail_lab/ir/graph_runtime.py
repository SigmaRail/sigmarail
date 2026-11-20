"""Lower supported graph shapes to ``universe_query_v1`` for runner execution."""

from __future__ import annotations

from typing import Any

from .models import (
    FilterStep,
    GraphStep,
    GroupStep,
    IfStep,
    SelectStep,
    WeightStep,
)
from .presets import get_preset_criteria
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
)

_DEFAULT_SELECT = [
    "ticker",
    "close",
    "closeadj",
    "rs_rating",
    "overall_score",
    "atr_14_pct",
]


def _col_name(column: object) -> str:
    return str(getattr(column, "value", column))


def _legacy_criteria_to_v1_where(item: BoolExprItem) -> dict[str, Any]:
    if isinstance(item, ColGteExpr):
        return {
            "type": "gte",
            "left": {"type": "col", "name": _col_name(item.column)},
            "right": {"type": "lit", "value": item.value},
        }
    if isinstance(item, ColLteExpr):
        return {
            "type": "lte",
            "left": {"type": "col", "name": _col_name(item.column)},
            "right": {"type": "lit", "value": item.value},
        }
    if isinstance(item, ColEqExpr):
        val: bool | float | int = item.value
        if isinstance(val, bool):
            val = 1 if val else 0
        return {
            "type": "eq",
            "left": {"type": "col", "name": _col_name(item.column)},
            "right": {"type": "lit", "value": val},
        }
    if isinstance(item, ColBetweenExpr):
        return {
            "type": "all",
            "items": [
                {
                    "type": "gte",
                    "left": {"type": "col", "name": _col_name(item.column)},
                    "right": {"type": "lit", "value": item.min},
                },
                {
                    "type": "lte",
                    "left": {"type": "col", "name": _col_name(item.column)},
                    "right": {"type": "lit", "value": item.max},
                },
            ],
        }
    if isinstance(item, InTickersExpr):
        return {
            "type": "any",
            "items": [
                {
                    "type": "eq",
                    "left": {"type": "col", "name": "ticker"},
                    "right": {"type": "lit", "value": t.strip().upper()},
                }
                for t in item.tickers
            ],
        }
    if isinstance(item, AllExpr):
        return {"type": "all", "items": [_legacy_criteria_to_v1_where(x) for x in item.items]}
    if isinstance(item, AnyExpr):
        return {"type": "any", "items": [_legacy_criteria_to_v1_where(x) for x in item.items]}
    if isinstance(item, NotExpr):
        return {"type": "not", "item": _legacy_criteria_to_v1_where(item.item)}
    raise TypeError(f"unsupported graph criteria node: {type(item)!r}")


def _collect_in_tickers(item: BoolExprItem) -> list[str]:
    if isinstance(item, InTickersExpr):
        return [t.strip().upper() for t in item.tickers]
    if isinstance(item, AllExpr):
        out: list[str] = []
        for x in item.items:
            out.extend(_collect_in_tickers(x))
        return out
    if isinstance(item, AnyExpr):
        out: list[str] = []
        for x in item.items:
            out.extend(_collect_in_tickers(x))
        return out
    return []


def _collect_weight_tickers(node: GraphStep, out: set[str]) -> None:
    if isinstance(node, WeightStep) and node.weights:
        for key in node.weights:
            k = (key or "").strip().upper()
            if k and not k.startswith("$"):
                out.add(k)
    if isinstance(node, GroupStep):
        for c in node.children:
            _collect_weight_tickers(c, out)
    if isinstance(node, IfStep):
        _collect_weight_tickers(node.then, out)
        _collect_weight_tickers(node.else_, out)
    if isinstance(node, WeightStep):
        for c in node.children:
            _collect_weight_tickers(c, out)


def graph_subscription_tickers(root: GraphStep) -> set[str]:
    """Tickers that must be Lean-subscribed for graph policy + universe filter."""
    tickers: set[str] = {"SPY"}
    sel = _find_first_select(root)
    if sel is not None and isinstance(sel.from_, FilterStep):
        fl = sel.from_
        if fl.criteria is not None:
            tickers.update(_collect_in_tickers(fl.criteria))
    _collect_weight_tickers(root, tickers)
    return tickers


def _find_first_select(node: GraphStep) -> SelectStep | None:
    if isinstance(node, SelectStep):
        return node
    if isinstance(node, GroupStep):
        for c in node.children:
            found = _find_first_select(c)
            if found is not None:
                return found
    if isinstance(node, IfStep):
        return _find_first_select(node.then) or _find_first_select(node.else_)
    if isinstance(node, WeightStep):
        for c in node.children:
            found = _find_first_select(c)
            if found is not None:
                return found
    return None


def lower_graph_to_universe(root: GraphStep) -> dict[str, Any] | None:
    """
    MVP: first SelectStep in DFS order whose ``from`` is a FilterStep (daily_screener).
    Preset or inline criteria on the filter; limit from filter.limit_per_day or select.top_k.
    """
    sel = _find_first_select(root)
    if sel is None:
        return None
    fl = sel.from_
    if not isinstance(fl, FilterStep):
        return None
    if fl.source != "daily_screener":
        return None
    if fl.preset and fl.preset.strip():
        crit = get_preset_criteria(fl.preset)
    elif fl.criteria is not None:
        crit = fl.criteria
    else:
        return None
    lim = fl.limit_per_day if fl.limit_per_day is not None else sel.top_k
    select = [_col_name(c) for c in (fl.projection or [])] or list(_DEFAULT_SELECT)
    sort_field = _col_name(fl.sort.field)
    if sort_field not in select:
        select = list(select) + [sort_field]
    return {
        "version": 1,
        "from": "daily_screener",
        "select": select,
        "where": _legacy_criteria_to_v1_where(crit),
        "order_by": [{"field": sort_field, "direction": fl.sort.direction}],
        "limit_per_day": int(lim),
    }
