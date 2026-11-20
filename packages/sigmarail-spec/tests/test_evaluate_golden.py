"""Golden outputs for the row evaluator.

These pin the *arithmetic*, which the dialect tests do not: `test_expr.py` checks the shape of
a parsed tree, while this file records what the evaluator actually returns for a fixed set of
expressions and rows. It exists because the evaluator moved out of VeraTradingLab on
2026-10-03 — the move was proven byte-identical and by a 103,200-comparison differential test,
and this file keeps that guarantee once the old implementation is gone from the tree.

If a change makes one of these fail, the change altered strategy behaviour. That is not
automatically wrong, but it must be a deliberate decision, not a silent one.
"""

from __future__ import annotations

import pytest

from sigmarail_spec import evaluate_slot_bool, evaluate_slot_number, evaluate_where_ast

ROWS = [
    {
        "a": 1,
        "b": 2,
        "rs_rating": 85,
        "ticker": "SPY"
    },
    {
        "a": 2,
        "b": 1,
        "rs_rating": 84,
        "ticker": "AAPL"
    },
    {
        "a": 5,
        "b": 5,
        "rs_rating": 100,
        "ticker": "QQQ"
    },
    {
        "a": 0,
        "b": 0,
        "rs_rating": 0,
        "ticker": "SGOV"
    },
    {
        "a": -3,
        "b": 3,
        "rs_rating": -1,
        "ticker": "TQQQ"
    },
    {
        "a": None,
        "b": 1,
        "rs_rating": 50,
        "ticker": "SPY"
    },
    {
        "b": 1
    }
]

EXPRS = {
    "gte_col_lit": {
        "type": "gte",
        "left": {
            "type": "col",
            "name": "rs_rating"
        },
        "right": {
            "type": "lit",
            "value": 85
        }
    },
    "gt_col_lit": {
        "type": "gt",
        "left": {
            "type": "col",
            "name": "rs_rating"
        },
        "right": {
            "type": "lit",
            "value": 85
        }
    },
    "lt_col_lit": {
        "type": "lt",
        "left": {
            "type": "col",
            "name": "rs_rating"
        },
        "right": {
            "type": "lit",
            "value": 85
        }
    },
    "lte_col_lit": {
        "type": "lte",
        "left": {
            "type": "col",
            "name": "rs_rating"
        },
        "right": {
            "type": "lit",
            "value": 85
        }
    },
    "eq_col_col": {
        "type": "eq",
        "left": {
            "type": "col",
            "name": "a"
        },
        "right": {
            "type": "col",
            "name": "b"
        }
    },
    "gte_col_col": {
        "type": "gte",
        "left": {
            "type": "col",
            "name": "a"
        },
        "right": {
            "type": "col",
            "name": "b"
        }
    },
    "formula_add": {
        "type": "gte",
        "left": {
            "type": "formula",
            "op": "+",
            "args": [
                {
                    "type": "col",
                    "name": "a"
                },
                {
                    "type": "col",
                    "name": "b"
                }
            ]
        },
        "right": {
            "type": "lit",
            "value": 3
        }
    },
    "formula_div": {
        "type": "lte",
        "left": {
            "type": "formula",
            "op": "/",
            "args": [
                {
                    "type": "col",
                    "name": "a"
                },
                {
                    "type": "col",
                    "name": "b"
                }
            ]
        },
        "right": {
            "type": "lit",
            "value": 1
        }
    },
    "all_nested": {
        "type": "all",
        "items": [
            {
                "type": "gte",
                "left": {
                    "type": "col",
                    "name": "rs_rating"
                },
                "right": {
                    "type": "lit",
                    "value": 50
                }
            },
            {
                "type": "gte",
                "left": {
                    "type": "col",
                    "name": "a"
                },
                "right": {
                    "type": "lit",
                    "value": 0
                }
            }
        ]
    },
    "any_nested": {
        "type": "any",
        "items": [
            {
                "type": "gte",
                "left": {
                    "type": "col",
                    "name": "rs_rating"
                },
                "right": {
                    "type": "lit",
                    "value": 90
                }
            },
            {
                "type": "lte",
                "left": {
                    "type": "col",
                    "name": "a"
                },
                "right": {
                    "type": "lit",
                    "value": 0
                }
            }
        ]
    },
    "not_nested": {
        "type": "not",
        "item": {
            "type": "gte",
            "left": {
                "type": "col",
                "name": "rs_rating"
            },
            "right": {
                "type": "lit",
                "value": 50
            }
        }
    },
    "col_gte": {
        "type": "col_gte",
        "column": "rs_rating",
        "value": 85
    },
    "col_lte": {
        "type": "col_lte",
        "column": "rs_rating",
        "value": 50
    },
    "col_eq": {
        "type": "col_eq",
        "column": "a",
        "value": 1
    },
    "between": {
        "type": "between",
        "column": "rs_rating",
        "min": 50,
        "max": 90
    },
    "in_tickers": {
        "type": "in_tickers",
        "tickers": [
            "SPY",
            "QQQ"
        ]
    }
}

GOLDEN = {
    "gte_col_lit": {
        "where": [
            True,
            False,
            True,
            False,
            False,
            False,
            False
        ],
        "slot": [
            True,
            False,
            True,
            False,
            False,
            False,
            False
        ]
    },
    "gt_col_lit": {
        "where": [
            False,
            False,
            True,
            False,
            False,
            False,
            False
        ],
        "slot": [
            False,
            False,
            True,
            False,
            False,
            False,
            False
        ]
    },
    "lt_col_lit": {
        "where": [
            False,
            True,
            False,
            True,
            True,
            True,
            False
        ],
        "slot": [
            False,
            True,
            False,
            True,
            True,
            True,
            False
        ]
    },
    "lte_col_lit": {
        "where": [
            True,
            True,
            False,
            True,
            True,
            True,
            False
        ],
        "slot": [
            True,
            True,
            False,
            True,
            True,
            True,
            False
        ]
    },
    "eq_col_col": {
        "where": [
            False,
            False,
            True,
            True,
            False,
            False,
            False
        ],
        "slot": [
            False,
            False,
            True,
            True,
            False,
            False,
            False
        ]
    },
    "gte_col_col": {
        "where": [
            False,
            True,
            True,
            True,
            False,
            False,
            False
        ],
        "slot": [
            False,
            True,
            True,
            True,
            False,
            False,
            False
        ]
    },
    "formula_add": {
        "where": [
            True,
            True,
            True,
            False,
            False,
            False,
            False
        ],
        "slot": [
            True,
            True,
            True,
            False,
            False,
            False,
            False
        ]
    },
    "formula_div": {
        "where": [
            True,
            False,
            True,
            False,
            True,
            False,
            False
        ],
        "slot": [
            True,
            False,
            True,
            False,
            True,
            False,
            False
        ]
    },
    "all_nested": {
        "where": [
            True,
            True,
            True,
            False,
            False,
            False,
            False
        ],
        "slot": [
            True,
            True,
            True,
            False,
            False,
            False,
            False
        ]
    },
    "any_nested": {
        "where": [
            False,
            False,
            True,
            True,
            True,
            False,
            False
        ],
        "slot": [
            False,
            False,
            True,
            True,
            True,
            False,
            False
        ]
    },
    "not_nested": {
        "where": [
            False,
            False,
            False,
            True,
            True,
            False,
            True
        ],
        "slot": [
            False,
            False,
            False,
            True,
            True,
            False,
            True
        ]
    },
    "col_gte": {
        "where": [
            True,
            False,
            True,
            False,
            False,
            False,
            False
        ],
        "slot": [
            True,
            False,
            True,
            False,
            False,
            False,
            False
        ]
    },
    "col_lte": {
        "where": [
            False,
            False,
            False,
            True,
            True,
            True,
            False
        ],
        "slot": [
            False,
            False,
            False,
            True,
            True,
            True,
            False
        ]
    },
    "col_eq": {
        "where": [
            True,
            False,
            False,
            False,
            False,
            False,
            False
        ],
        "slot": [
            True,
            False,
            False,
            False,
            False,
            False,
            False
        ]
    },
    "between": {
        "where": [
            True,
            True,
            False,
            False,
            False,
            True,
            False
        ],
        "slot": [
            True,
            True,
            False,
            False,
            False,
            True,
            False
        ]
    },
    "in_tickers": {
        "where": [
            True,
            False,
            True,
            False,
            False,
            True,
            False
        ],
        "slot": [
            True,
            False,
            True,
            False,
            False,
            True,
            False
        ]
    }
}


@pytest.mark.parametrize("name", sorted(EXPRS))
def test_where_ast_matches_golden(name: str) -> None:
    assert [evaluate_where_ast(r, EXPRS[name]) for r in ROWS] == GOLDEN[name]["where"]


@pytest.mark.parametrize("name", sorted(EXPRS))
def test_slot_bool_matches_golden(name: str) -> None:
    assert [evaluate_slot_bool(r, EXPRS[name]) for r in ROWS] == GOLDEN[name]["slot"]


# --- C-VERA-EXPR-V2 operand pins (min / max / clamp / abs / cond) -------------
# These pin the *value* path (`evaluate_slot_number`), including the fail-closed
# convention: any operand resolving to None propagates None; `cond` treats an
# unevaluatable `when` as false and takes `otherwise`.

OPERAND_EXPRS = {
    "min_ab": {
        "type": "min",
        "args": [{"type": "col", "name": "a"}, {"type": "col", "name": "b"}],
    },
    "max_ab": {
        "type": "max",
        "args": [{"type": "col", "name": "a"}, {"type": "col", "name": "b"}],
    },
    "clamp_a": {
        "type": "clamp",
        "value": {"type": "col", "name": "a"},
        "min": {"type": "lit", "value": 0.5},
        "max": {"type": "lit", "value": 3.5},
    },
    "abs_a": {"type": "abs", "arg": {"type": "col", "name": "a"}},
    "cond_a_pos": {
        "type": "cond",
        "when": {
            "type": "gt",
            "left": {"type": "col", "name": "a"},
            "right": {"type": "lit", "value": 0},
        },
        "then": {"type": "col", "name": "a"},
        "otherwise": {"type": "lit", "value": 99},
    },
    "cond_nested_min": {
        # max(a - b, a*0.95) when a resolves, else a*0.95 — the init-stop shape.
        "type": "cond",
        "when": {
            "type": "gt",
            "left": {"type": "col", "name": "b"},
            "right": {"type": "lit", "value": 0},
        },
        "then": {
            "type": "max",
            "args": [
                {
                    "type": "formula",
                    "op": "-",
                    "args": [{"type": "col", "name": "a"}, {"type": "col", "name": "b"}],
                },
                {
                    "type": "formula",
                    "op": "*",
                    "args": [{"type": "col", "name": "a"}, {"type": "lit", "value": 0.95}],
                },
            ],
        },
        "otherwise": {
            "type": "formula",
            "op": "*",
            "args": [{"type": "col", "name": "a"}, {"type": "lit", "value": 0.95}],
        },
    },
}

OPERAND_GOLDEN = {
    # ROWS: a,b = (1,2) (2,1) (5,5) (0,0) (-3,3) (None,1) (missing,1)
    "min_ab": [1.0, 1.0, 5.0, 0.0, -3.0, None, None],
    "max_ab": [2.0, 2.0, 5.0, 0.0, 3.0, None, None],
    "clamp_a": [1.0, 2.0, 3.5, 0.5, 0.5, None, None],
    "abs_a": [1.0, 2.0, 5.0, 0.0, 3.0, None, None],
    "cond_a_pos": [1.0, 2.0, 5.0, 99.0, 99.0, 99.0, 99.0],
    "cond_nested_min": [0.95, 1.9, 4.75, 0.0, -2.85, None, None],
}


@pytest.mark.parametrize("name", sorted(OPERAND_EXPRS))
def test_operands_match_golden(name: str) -> None:
    got = [evaluate_slot_number(r, OPERAND_EXPRS[name]) for r in ROWS]
    want = OPERAND_GOLDEN[name]
    for g, w in zip(got, want):
        if w is None:
            assert g is None
        else:
            assert g == pytest.approx(w)
