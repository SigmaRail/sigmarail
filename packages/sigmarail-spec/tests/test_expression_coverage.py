"""Every dialect node must be handled, or context-requiring. There is no third bucket.

The evaluator and the dialect lived in different repositories and drifted: the row evaluator
implemented 12 node types while the dialect declared 21. `signal`/`signal_compare`/`regime*`
are *context*-requiring by design — they need a regime or signal context, not a plain row.

The other five (`between`, `in_tickers`, `col_gte`, `col_lte`, `col_eq`) were row-evaluable and
simply **unimplemented**, so each silently took its caller's fallback. That is not a neutral
failure: `evaluate_where_ast` falls back to **True** ("legacy filter fallback"), so an
unimplemented node inside a `where` passed *everything*. `in_tickers` is how an ETF universe
restricts itself to a ticker list, so that fallback disabled universe restriction outright.
They are implemented now, and this test keeps the set closed: a newly declared node must
either be implemented or explicitly declared context-requiring, or this fails.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest

from sigmarail_spec import evaluate, expr

# Needs a regime/signal context rather than a plain row — cannot be row-evaluated.
CONTEXT_REQUIRING = {
    "signal", "signal_compare", "regime", "regime_allows_entries",
    "regime_mart_allows_entries",
}


def _dialect_nodes() -> set[str]:
    found = set()
    for obj in vars(expr).values():
        fields = getattr(obj, "model_fields", None)
        if fields and "type" in fields and isinstance(fields["type"].default, str):
            found.add(fields["type"].default)
    return found


def _evaluator_handled() -> set[str]:
    """Discriminators the evaluator's source mentions, intersected with the dialect."""
    src = pathlib.Path(evaluate.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'"([a-z_]+)"', src)) & _dialect_nodes()


def test_every_node_is_handled_or_context_requiring() -> None:
    unclassified = _dialect_nodes() - _evaluator_handled() - CONTEXT_REQUIRING
    assert not unclassified, (
        "dialect node(s) that are neither handled nor declared context-requiring: "
        f"{sorted(unclassified)}. Implement them in `evaluate` — do not let them fall through "
        "to the caller's fallback, which is fail-OPEN inside a `where`."
    )


def test_context_requiring_nodes_are_real() -> None:
    for name in CONTEXT_REQUIRING:
        assert name in _dialect_nodes(), f"{name} is no longer a dialect node"


@pytest.mark.parametrize("name", sorted(CONTEXT_REQUIRING))
def test_context_requiring_nodes_are_not_row_predicates(name: str) -> None:
    """They must not be silently claimed by the row evaluators either."""
    node: dict[str, Any] = {
        "type": name, "field": "f", "eq": 1, "ticker": "SPY",
        "left": "a", "op": "gt", "right": "b",
    }
    # `where` keeps its documented fail-open, slots their fail-closed. Asserted so a future
    # edit cannot quietly promote a context node into a row predicate.
    assert evaluate.evaluate_where_ast({"ticker": "SPY"}, node) is True
    assert evaluate.evaluate_slot_bool({"ticker": "SPY"}, node) is False


def test_the_five_former_gaps_are_implemented() -> None:
    """Regression pin for the specific nodes that used to fall through."""
    handled = _evaluator_handled()
    for name in ("between", "in_tickers", "col_gte", "col_lte", "col_eq"):
        assert name in handled, f"{name} regressed to unhandled"


def test_dialect_unions_are_consistent() -> None:
    """SpecExpr = BoolExprItem + Operand — always, by construction."""
    from typing import get_args

    def discs(union):
        inner = get_args(union)[0]
        return {c.model_fields["type"].default for c in get_args(inner)}

    bool_names = discs(expr.BoolExprItem)
    spec_names = discs(expr.SpecExpr)
    operand_names = discs(expr.Operand)
    assert bool_names <= spec_names
    assert spec_names - bool_names == operand_names


def test_no_duplicate_discriminators() -> None:
    """A discriminator is unique across the canonical dialect — that was the whole split."""
    seen: dict[str, int] = {}
    for obj in vars(expr).values():
        fields = getattr(obj, "model_fields", None)
        if fields and "type" in fields and isinstance(fields["type"].default, str):
            seen[fields["type"].default] = seen.get(fields["type"].default, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    assert not dupes, f"duplicate discriminator(s): {dupes}"
