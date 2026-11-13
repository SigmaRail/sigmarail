"""Parse and validate an expression — what `parse_bool_expr` accepts and rejects.

The dialect is a discriminated union: the `type` field picks the node class, and every field
is validated by pydantic. There is no bespoke validation layer.

    python3 examples/01_parse_and_validate.py
"""

from pydantic import ValidationError

from sigmarail_spec import bool_expr_depth, is_runtime_only_expr, parse_bool_expr, validate_bool_expr_depth

# A Minervini-style trend template, written as the conditions it actually is:
#   price above the 50/150/200-day, the 150 above the 200, and RS >= 85.
#
# Composed rather than collapsed into a `..._all_conditions_full` flag column: the flag reads
# as one opaque field, hides which condition failed, and cannot be relaxed for a variant.
FILTER = {
    "type": "all",
    "items": [
        {"type": "gte", "left": {"type": "col", "name": "close"},
         "right": {"type": "col", "name": "sma50d"}},
        {"type": "gte", "left": {"type": "col", "name": "close"},
         "right": {"type": "col", "name": "sma150d"}},
        {"type": "gte", "left": {"type": "col", "name": "close"},
         "right": {"type": "col", "name": "sma200d"}},
        {"type": "gte", "left": {"type": "col", "name": "sma150d"},
         "right": {"type": "col", "name": "sma200d"}},
        {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
         "right": {"type": "lit", "value": 85}},
    ],
}


def main() -> None:
    node = parse_bool_expr(FILTER)
    print("parsed      :", type(node).__name__, "with", len(node.items), "conditions")
    print("depth       :", bool_expr_depth(node))
    validate_bool_expr_depth(node)          # raises past MAX_BOOL_DEPTH (24)
    print("depth ok    : <= MAX_BOOL_DEPTH")
    print("runtime-only:", is_runtime_only_expr(node), "(a regime/signal node would be True)")
    print("as dict     :", node.model_dump()["type"], node.model_dump()["items"][1])

    # Rejections — each of these was a real defect in the stored corpus.
    bad = {
        "redundant operator on a comparison": {
            "type": "eq", "op": "eq",
            "left": {"type": "col", "name": "a"}, "right": {"type": "lit", "value": 1}},
        "unknown field (extra='forbid')": {
            "type": "gte", "left": {"type": "col", "name": "a"},
            "right": {"type": "lit", "value": 1}, "typo": 1},
        "formula with three args": {
            "type": "gte", "left": {"type": "col", "name": "a"},
            "right": {"type": "formula", "op": "*",
                      "args": [{"type": "lit", "value": 1},
                               {"type": "lit", "value": 2},
                               {"type": "lit", "value": 3}]}},
        "unknown discriminator": {"type": "nope"},
    }
    print()
    for label, payload in bad.items():
        try:
            parse_bool_expr(payload)
            print(f"  NOT REJECTED (unexpected): {label}")
        except ValidationError as exc:
            first = exc.errors()[0]
            print(f"  rejected: {label} -> {first['msg']}")


if __name__ == "__main__":
    main()
