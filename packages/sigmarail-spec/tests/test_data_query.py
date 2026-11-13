from datetime import date

import math

import pytest
from pydantic import ValidationError

from sigmarail_spec import (
    DataQueryV1,
    QueryFieldExpression,
    QueryLiteralExpression,
    QueryPredicate,
)


def _query(**updates):
    payload = {
        "version": 1,
        "module_id": "sigmarail.core",
        "dataset_id": "daily_prices",
        "select": [{"field_id": "price.close"}],
        "as_of_date": "2025-01-02",
        "where": {"op": "gte", "field_id": "price.close", "value": 10},
    }
    payload.update(updates)
    return payload


def test_legacy_query_and_predicate_wire_shape_remains_valid():
    query = DataQueryV1.model_validate(_query())

    assert query.as_of_date == date(2025, 1, 2)
    assert query.where.field_id == "price.close"
    assert query.where.value == 10
    assert query.computed == []
    assert query.post_where is None


def test_computed_boolean_supports_field_to_field_comparison_and_offset():
    query = DataQueryV1.model_validate(
        _query(
            computed=[
                {
                    "alias": "near_high",
                    "kind": "bool",
                    "where": {
                        "op": "gte",
                        "left": {"type": "field", "field_id": "price.close", "offset": 0},
                        "right": {"type": "arithmetic", "op": "*", "args": [
                            {"type": "field", "field_id": "price.high_52w"},
                            {"type": "literal", "value": 0.9},
                        ]},
                    },
                }
            ],
            post_where={"op": "eq", "left": {"type": "alias", "alias": "near_high"}, "right": {"type": "literal", "value": True}},
            order_by=[{"expr": {"type": "alias", "alias": "near_high"}, "direction": "desc"}],
        )
    )

    assert query.computed[0].where.left.field_id == "price.close"
    assert query.computed[0].where.right.op == "*"
    assert query.post_where.left.alias == "near_high"


def test_computed_number_composition_and_mean_available_are_valid():
    query = DataQueryV1.model_validate(
        _query(
            computed=[
                {"alias": "trend", "kind": "number", "expr": {"type": "field", "field_id": "technical.rs_rating"}},
                {"alias": "quality", "kind": "number", "mean_available": ["fundamentals.roe", "fundamentals.roic"]},
                {"alias": "score", "kind": "number", "sum_aliases": ["trend", "quality"]},
                {"alias": "scaled_score", "kind": "number", "expr": {"type": "arithmetic", "op": "/", "args": [
                    {"type": "alias", "alias": "score"}, {"type": "literal", "value": 2},
                ]}},
            ]
        )
    )

    assert [item.alias for item in query.computed] == ["trend", "quality", "score", "scaled_score"]


@pytest.mark.parametrize(
    "computed",
    [
        [{"alias": "x", "kind": "number", "expr": {"type": "alias", "alias": "later"}}],
        [{"alias": "x", "kind": "number", "sum_aliases": ["later"]}],
        [{"alias": "x", "kind": "bool", "where": {"op": "eq", "left": {"type": "field", "field_id": "a"}, "right": {"type": "alias", "alias": "later"}}}],
    ],
)
def test_computed_fields_cannot_reference_future_aliases(computed):
    with pytest.raises(ValidationError, match="not declared earlier"):
        DataQueryV1.model_validate(_query(computed=computed))


def test_pre_filter_cannot_reference_computed_alias():
    with pytest.raises(ValidationError, match="where cannot reference computed aliases"):
        DataQueryV1.model_validate(
            _query(
                computed=[{"alias": "flag", "kind": "bool", "where": {"op": "gt", "field_id": "price.close", "value": 10}}],
                where={"op": "eq", "left": {"type": "alias", "alias": "flag"}, "right": {"type": "literal", "value": True}},
            )
        )


def test_post_filter_and_order_reject_unknown_aliases():
    with pytest.raises(ValidationError, match="post_where references unknown"):
        DataQueryV1.model_validate(_query(post_where={"op": "eq", "left": {"type": "alias", "alias": "missing"}, "right": {"type": "literal", "value": 1}}))
    with pytest.raises(ValidationError, match="order_by references unknown"):
        DataQueryV1.model_validate(_query(order_by=[{"expr": {"type": "alias", "alias": "missing"}}]))


def test_expression_limits_and_alias_collisions_are_enforced():
    deep = {"type": "field", "field_id": "a"}
    for _ in range(9):
        deep = {"type": "arithmetic", "op": "+", "args": [deep, {"type": "literal", "value": 1}]}
    with pytest.raises(ValidationError, match="less than or equal to 3650"):
        QueryFieldExpression.model_validate({"field_id": "x", "offset": 3651})
    with pytest.raises(ValidationError, match="maximum depth"):
        DataQueryV1.model_validate(_query(computed=[{"alias": "deep", "kind": "number", "expr": deep}]))
    with pytest.raises(ValidationError, match="collides"):
        DataQueryV1.model_validate(
            _query(
                select=[{"field_id": "price.close", "alias": "signal"}],
                computed=[{"alias": "signal", "kind": "number", "expr": {"type": "literal", "value": 1}}],
            )
        )


def test_predicates_require_valid_legacy_or_expression_shape():
    with pytest.raises(ValidationError):
        QueryPredicate.model_validate({"op": "gt", "field_id": "price.close"})
    with pytest.raises(ValidationError):
        QueryPredicate.model_validate({"op": "gt", "left": {"type": "field", "field_id": "a"}})


def test_recursive_query_schema_is_generatable():
    schema = DataQueryV1.model_json_schema()

    assert "QueryArithmeticExpression" in schema["$defs"]
    assert "computed" in schema["properties"]
    assert "post_where" in schema["properties"]


def test_literals_reject_non_finite_numbers_and_oversized_strings():
    with pytest.raises(ValidationError, match="finite"):
        QueryLiteralExpression.model_validate({"value": math.inf})
    with pytest.raises(ValidationError, match="1024 characters"):
        QueryLiteralExpression.model_validate({"value": "x" * 1025})
