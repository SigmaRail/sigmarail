"""Evaluate an expression against one screener row.

`evaluate_where_ast` is the *filter* entry point — it answers "keep this row?".

    python3 examples/02_evaluate_a_row.py
"""

from sigmarail_spec import evaluate_where_ast

# A 21-EMA pullback with a volume dry-up:
#   close >= ema21d  AND  volume <= 0.7 * avg_vol_20d
SETUP = {
    "type": "all",
    "items": [
        {"type": "gte", "left": {"type": "col", "name": "close"},
         "right": {"type": "col", "name": "ema21d"}},
        {"type": "lte", "left": {"type": "col", "name": "volume"},
         "right": {"type": "formula", "op": "*",
                   "args": [{"type": "lit", "value": 0.7},
                            {"type": "col", "name": "avg_vol_20d"}]}},
    ],
}

ROWS = [
    {"ticker": "AAA", "close": 105.0, "ema21d": 100.0,
     "volume": 600_000, "avg_vol_20d": 1_000_000},   # passes both clauses
    {"ticker": "BBB", "close": 98.0, "ema21d": 100.0,
     "volume": 600_000, "avg_vol_20d": 1_000_000},   # below the 21 EMA
    {"ticker": "CCC", "close": 105.0, "ema21d": 100.0,
     "volume": 900_000, "avg_vol_20d": 1_000_000},   # volume not dry enough
    {"ticker": "DDD", "close": 105.0},               # missing columns
]


def main() -> None:
    print("filter: close >= ema21d AND volume <= 0.7 * avg_vol_20d")
    for row in ROWS:
        print(f"  {row['ticker']}: {evaluate_where_ast(row, SETUP)}")

    # A missing column resolves to None, and any comparison against None is False — the row
    # is dropped rather than passing by accident. This is the "fail-closed on data" rule.
    print()
    print("  missing data ->", evaluate_where_ast({"ticker": "X"}, SETUP), "(row dropped)")


if __name__ == "__main__":
    main()
