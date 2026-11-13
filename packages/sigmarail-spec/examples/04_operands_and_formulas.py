"""Operands: `col`, `lit`, `formula` — and when the root itself is an operand.

* `col` may carry `offset`, but be careful: the **row evaluators ignore it** — they look
  the column up in the row as-is, so `offset=5` and `offset=0` give the same value. It is
  honoured by the SQL compiler in VeraBase. Do not rely on it in a row-evaluated slot.
* `lit` holds a number or a string; a bare Python number/string also works in an operand slot.
* `formula` is strictly binary (`+ - * /`) and nests through `args`. Division by zero yields
  `None` rather than infinity, so the comparison fails closed.
* `SpecExpr` — not `BoolExprItem` — is the union for fields that may root at a bare operand.
  `weight_expr: {"type": "col", "name": "w_conviction"}` is real: 75 stored specs do exactly
  that.

    python3 examples/04_operands_and_formulas.py
"""

from pydantic import TypeAdapter, ValidationError

from sigmarail_spec import ColRef, LitVal, SpecExpr, evaluate_where_ast, parse_bool_expr

# Risk-adjusted momentum: rs_rating / atr_14 >= 10
RATIO = {
    "type": "gte",
    "left": {"type": "formula", "op": "/",
             "args": [{"type": "col", "name": "rs_rating"},
                      {"type": "col", "name": "atr_14"}]},
    "right": {"type": "lit", "value": 10},
}

# An operand-rooted field: a bare column reference, not a boolean.
BARE = {"type": "col", "name": "w_conviction"}


def main() -> None:
    print("rs_rating / atr_14 >= 10:")
    for row in (
        {"rs_rating": 91, "atr_14": 3},      # 30.3 -> True
        {"rs_rating": 91, "atr_14": 20},     # 4.55 -> False
        {"rs_rating": 91, "atr_14": 0},      # divide by zero -> None -> False
        {"rs_rating": 91},                   # missing column -> None -> False
    ):
        print(f"  {row} -> {evaluate_where_ast(row, RATIO)}")
    print("  ^ divide-by-zero and a missing column both fail closed")

    print()
    adapter = TypeAdapter(SpecExpr)
    print("operand root, SpecExpr      :", adapter.validate_python(BARE).name)
    try:
        parse_bool_expr(BARE)
        print("operand root, BoolExprItem  : NOT REFUSED (unexpected)")
    except ValidationError:
        print("operand root, BoolExprItem  : refused — use SpecExpr for operand-rooted fields")

    print()
    print("ColRef can reference a prior bar:", ColRef(name="close", offset=1).model_dump())
    print("LitVal accepts strings as well  :", LitVal(value="breakout").model_dump())


if __name__ == "__main__":
    main()
