"""The two evaluators disagree on purpose: `where` fails *open*, slots fail *closed*.

This is the single easiest thing to get wrong in this codebase, and it has bitten before.
An unknown node inside a `where` filter returns **True** — "legacy filter fallback" — so an
unimplemented node *passed everything*. Inside a slot expression the same node returns
**False**, which refuses the entry instead. Neither is an accident; both are documented, and
`tests/test_coverage.py` keeps every declared node implemented so the fallback is never load
bearing.

    python3 examples/03_fail_open_vs_fail_closed.py
"""

from sigmarail_spec import evaluate_slot_bool, evaluate_slot_number, evaluate_where_ast

ROW = {"ticker": "SPY", "close": 100.0, "rs_rating": 91}

KNOWN = {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
         "right": {"type": "lit", "value": 85}}

# A context-requiring node: it needs a regime/signal context, not a plain row.
UNKNOWN_HERE = {"type": "regime", "field": "is_bear_market_active", "eq": 1}


def main() -> None:
    print("known filter node          :", evaluate_where_ast(ROW, KNOWN))
    print("known slot node            :", evaluate_slot_bool(ROW, KNOWN))
    print()
    print("context node in `where`    :", evaluate_where_ast(ROW, UNKNOWN_HERE),
          " <- fail-OPEN: the filter keeps the row")
    print("context node in a slot     :", evaluate_slot_bool(ROW, UNKNOWN_HERE),
          " <- fail-CLOSED: the entry is refused")
    print()
    print("empty `where` node         :", evaluate_where_ast(ROW, None), "(no filter = keep)")
    print("empty slot node            :", evaluate_slot_bool(ROW, None), "(no rule = refuse)")
    print()
    # Numbers come back as floats, or None when the expression cannot be evaluated.
    print("slot number (col)          :", evaluate_slot_number(ROW, {"type": "col", "name": "close"}))
    print("slot number (missing col)  :", evaluate_slot_number(ROW, {"type": "col", "name": "nope"}))
    print("slot number (divide by 0)  :",
          evaluate_slot_number(ROW, {"type": "formula", "op": "/",
                                     "args": [{"type": "col", "name": "close"},
                                              {"type": "lit", "value": 0}]}))


if __name__ == "__main__":
    main()
