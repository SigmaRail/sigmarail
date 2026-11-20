"""Tests for screens/rule_eval.py — the Studio preview evaluator.

The endpoint fetches the real T-1 universe row server-side; these tests cover
the pure evaluation contract (terminality, displace slot mutation, error
capture) with synthetic rows/contexts — no ClickHouse needed.
"""

from __future__ import annotations

from screens.rule_eval import evaluate_rule_table


def _ctx(**kw):
    base = {ns: {} for ns in ("cand", "hold", "acct", "pyr", "regime", "pos")}
    for k, v in kw.items():
        base[k].update(v)
    return base


RULES = [
    {
        "name": "down_flatten",
        "priority": -40,
        "when": {"type": "neq", "left": {"type": "ref", "ns": "cand", "field": "is_down"}, "right": {"type": "lit", "value": 0}},
        "then": [{"type": "resize", "to": {"type": "lit", "value": 0}}],
    },
    {
        "name": "displace_weakest",
        "priority": 0,
        "when": {
            "type": "all",
            "items": [
                {"type": "neq", "left": {"type": "ref", "ns": "cand", "field": "is_new"}, "right": {"type": "lit", "value": 0}},
                {"type": "lte", "left": {"type": "ref", "ns": "acct", "field": "slots_remaining"}, "right": {"type": "lit", "value": 0}},
                {"type": "gte", "left": {"type": "ref", "ns": "cand", "field": "rs"}, "right": {"type": "lit", "value": 95}},
            ],
        },
        "then": [{"type": "displace", "max_per_day": 2}],
    },
    {
        "name": "new_entry",
        "priority": 20,
        "when": {
            "type": "all",
            "items": [
                {"type": "neq", "left": {"type": "ref", "ns": "cand", "field": "is_new"}, "right": {"type": "lit", "value": 0}},
                {"type": "gt", "left": {"type": "ref", "ns": "acct", "field": "slots_remaining"}, "right": {"type": "lit", "value": 0}},
            ],
        },
        "then": [{"type": "enter"}],
    },
]


def test_terminal_rule_ends_the_pass():
    out = evaluate_rule_table({}, RULES, _ctx(cand={"is_down": 1}))
    assert out["decision"]["rule"] == "down_flatten"
    assert len(out["per_rule"]) == 1  # later rules never evaluated


def test_displace_frees_slot_then_entry_fires():
    out = evaluate_rule_table(
        {}, RULES,
        _ctx(cand={"is_new": 1, "rs": 96}, acct={"slots_remaining": 0}),
    )
    names = [r["name"] for r in out["per_rule"] if r["matched"]]
    assert names == ["displace_weakest", "new_entry"]
    assert out["decision"]["rule"] == "new_entry"


def test_no_match_no_decision():
    out = evaluate_rule_table(
        {}, RULES,
        _ctx(cand={"is_new": 1, "rs": 10}, acct={"slots_remaining": 0}),
    )
    assert out["decision"]["rule"] is None
    assert all(not r["matched"] for r in out["per_rule"])


def test_col_reads_the_universe_row():
    rules = [
        {
            "name": "rs_gate",
            "when": {"type": "gte", "left": {"type": "col", "name": "rs_rating"}, "right": {"type": "lit", "value": 80}},
            "then": [{"type": "enter"}],
        }
    ]
    ctx = _ctx()
    assert evaluate_rule_table({"rs_rating": 91}, rules, ctx)["decision"]["rule"] == "rs_gate"
    assert evaluate_rule_table({"rs_rating": 50}, rules, ctx)["decision"]["rule"] is None
    assert evaluate_rule_table({}, rules, ctx)["decision"]["rule"] is None  # fail-closed


def test_eval_error_is_captured_not_raised():
    rules = [
        {
            "name": "bad_when",
            "when": {"type": "definitely_not_a_node"},
            "then": [{"type": "enter"}],
        }
    ]
    out = evaluate_rule_table({}, rules, _ctx(cand={"is_new": 1}))
    assert out["decision"]["rule"] is None
    assert out["per_rule"][0]["matched"] is False


def test_row_none_means_not_in_universe():
    out = evaluate_rule_table(None, RULES, _ctx(cand={"is_new": 1}, acct={"slots_remaining": 3}))
    # empty row: col reads fail closed, ref-driven rules still evaluate
    assert out["decision"]["rule"] == "new_entry"
