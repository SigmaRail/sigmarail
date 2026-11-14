"""Dialect behaviour — the properties the consolidation must preserve."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sigmarail_spec import (
    MAX_BOOL_DEPTH,
    SpecExpr,
    bool_expr_depth,
    is_runtime_only_expr,
    parse_bool_expr,
    validate_bool_expr_depth,
)
from sigmarail_spec import evaluate_slot_bool, evaluate_where_ast


def test_parses_a_nested_expression() -> None:
    node = parse_bool_expr({
        "type": "any",
        "items": [
            {"type": "gte", "left": {"type": "col", "name": "screens_hit"},
             "right": {"type": "lit", "value": 1}},
            {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
             "right": {"type": "lit", "value": 85}},
        ],
    })
    assert node.type == "any"
    assert bool_expr_depth(node) == 2


def test_rejects_a_redundant_op_on_a_comparison() -> None:
    """20 stored specs carried this; the runtime ignores `op`, but schema-wise it is invalid."""
    with pytest.raises(ValidationError):
        parse_bool_expr({"type": "eq", "op": "eq",
                         "left": {"type": "col", "name": "a"},
                         "right": {"type": "lit", "value": 1}})


def test_rejects_a_non_binary_formula() -> None:
    with pytest.raises(ValidationError):
        parse_bool_expr({"type": "gte",
                         "left": {"type": "col", "name": "a"},
                         "right": {"type": "formula", "op": "*",
                                   "args": [{"type": "lit", "value": 1},
                                            {"type": "lit", "value": 2},
                                            {"type": "lit", "value": 3}]}})


def test_regime_node_with_source_is_accepted() -> None:
    node = parse_bool_expr({"type": "regime", "field": "is_bear_market_active",
                            "eq": 1, "source": "market_context"})
    assert node.source == "market_context"
    assert is_runtime_only_expr(node)


def test_regime_allows_entries_is_accepted() -> None:
    """VeraTradingLab-only node until consolidation."""
    assert parse_bool_expr({"type": "regime_allows_entries", "eq": 1}).type == \
        "regime_allows_entries"


def test_operand_root_is_valid_for_spec_expr_only() -> None:
    from pydantic import TypeAdapter
    adapter = TypeAdapter(SpecExpr)
    assert adapter.validate_python({"type": "col", "name": "w_conviction"}).name == "w_conviction"
    with pytest.raises(ValidationError):
        parse_bool_expr({"type": "col", "name": "w_conviction"})


def test_depth_limit_enforced() -> None:
    node: dict = {"type": "gte", "left": {"type": "col", "name": "a"},
                  "right": {"type": "lit", "value": 1}}
    for _ in range(MAX_BOOL_DEPTH + 2):
        node = {"type": "all", "items": [node]}
    with pytest.raises(ValueError):
        validate_bool_expr_depth(parse_bool_expr(node))


def test_evaluator_agrees_with_the_dialect_on_a_row() -> None:
    row = {"screens_hit": 2, "rs_rating": 91}
    node = {"type": "any", "items": [
        {"type": "gte", "left": {"type": "col", "name": "screens_hit"},
         "right": {"type": "lit", "value": 5}},
        {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
         "right": {"type": "lit", "value": 85}},
    ]}
    assert evaluate_where_ast(row, node) is True
    assert evaluate_where_ast({"screens_hit": 0, "rs_rating": 10}, node) is False


def test_pos_ref_parses_in_operand_and_spec_expr() -> None:
    from pydantic import TypeAdapter
    from sigmarail_spec.expr import Operand
    assert TypeAdapter(Operand).validate_python({"type": "pos", "field": "entry"}).field == "entry"
    adapter = TypeAdapter(SpecExpr)
    assert adapter.validate_python({"type": "pos", "field": "r"}).type == "pos"
    # extra keys still forbidden
    with pytest.raises(ValidationError):
        TypeAdapter(Operand).validate_python({"type": "pos", "field": "r", "x": 1})


def test_pos_ref_evaluates_from_position_context_only() -> None:
    from sigmarail_spec.evaluate import evaluate_slot_number, evaluate_slot_bool, evaluate_where_ast
    pos_node = {"type": "pos", "field": "entry"}
    # slot eval: position dict supplies the binding
    assert evaluate_slot_number({}, pos_node, position={"entry": 52.25}) == 52.25
    # inside a comparison it behaves like a col
    assert evaluate_slot_bool(
        {},
        {"type": "gte", "left": {"type": "pos", "field": "r"},
         "right": {"type": "lit", "value": 3}},
        position={"r": 3.4},
    ) is True
    # row-only eval (universe where/computed): no position → None → fail closed
    assert evaluate_slot_number({"entry": 99.0}, pos_node) is None
    assert evaluate_where_ast(
        {"__position.r": None},
        {"type": "gte", "left": pos_node, "right": {"type": "lit", "value": 0}},
    ) is False


def test_ref_parses_in_operand_and_spec_expr() -> None:
    from pydantic import TypeAdapter
    from sigmarail_spec.expr import Operand
    node = TypeAdapter(Operand).validate_python({"type": "ref", "ns": "hold", "field": "weight"})
    assert node.ns == "hold" and node.field == "weight"
    assert TypeAdapter(SpecExpr).validate_python({"type": "ref", "ns": "acct", "field": "cash"}).type == "ref"
    with pytest.raises(ValidationError):
        TypeAdapter(Operand).validate_python({"type": "ref", "ns": "hold"})  # field required
    with pytest.raises(ValidationError):
        TypeAdapter(Operand).validate_python({"type": "ref", "ns": "hold", "field": "w", "x": 1})


def test_ref_evaluates_from_named_contexts() -> None:
    from sigmarail_spec.evaluate import evaluate_slot_number, evaluate_slot_bool
    node = {"type": "ref", "ns": "hold", "field": "weight"}
    assert evaluate_slot_number({}, node, contexts={"hold": {"weight": 0.12}}) == 0.12
    # ref{ns:"pos"} resolves the same __position namespace as the pos node
    ref_pos = {"type": "ref", "ns": "pos", "field": "r"}
    assert evaluate_slot_number({}, ref_pos, position={"r": 2.0}) == 2.0
    assert evaluate_slot_number({}, ref_pos, contexts={"pos": {"r": 2.5}}) == 2.5
    # missing ns / missing field → None → comparisons fail closed
    assert evaluate_slot_number({}, node, contexts={"acct": {"cash": 1}}) is None
    assert evaluate_slot_bool(
        {},
        {"type": "gt", "left": node, "right": {"type": "lit", "value": 0}},
        contexts={"hold": {}},
    ) is False
    # row-only: no contexts → None
    assert evaluate_slot_number({"hold.weight": 9.0}, node) is None
