"""Enum ``entry_triggers`` ≡ compiled-AST differential (EXPRESSION_SURFACE §11).

``compile_entry_trigger`` lowers the enum dialect to bool AST; these tests
pin semantic equivalence: for every trigger type, over a matrix of row
shapes (fields present/absent, live price given/withheld), the legacy
procedural branch and the compiled AST must reach the same verdict.

A divergence here means the searchable surface changed behavior — the AST
form is what stored specs will carry, so it must be *identical*, not similar.
"""

from __future__ import annotations

import pytest

from sigmarail_spec.entry_trigger_ast import (
    ENUM_TRIGGER_TYPES,
    compile_entry_trigger,
    trigger_eval_row,
)
from sigmarail_spec.evaluate import evaluate_single_trigger, evaluate_slot_bool


# A row with every field populated, plus targeted sparse variants.
FULL_ROW = {
    "close": 100.0,
    "high": 102.0,
    "volume": 2_000_000.0,
    "avg_vol_50d": 1_000_000.0,
    "high_5d": 101.0,
    "high_90d": 99.0,
    "breakout_signal": 0,
    "vcp_atr_compression_5d_90d": 0.30,
    "vcp_volume_dryup_5d_90d": 0.50,
    "vcp_proximity_90d": 0.95,
    "pullback_ready": 1,
    "pocket_pivot_score": 40.0,
    "sma50d": 98.0,
    "sma10d": 99.0,
    "ema_21d": 100.0,
}

ROWS = {
    "full": FULL_ROW,
    "sparse": {"close": 100.0},
    "empty": {},
    "no_pivot": {**FULL_ROW, "high_90d": None, "breakout_signal": 0},
    "no_breakout": {**FULL_ROW, "breakout_signal": 0, "high": 90.0},
    "breakout_only": {**FULL_ROW, "high_90d": None, "high": 90.0, "breakout_signal": 1},
    "no_proximity": {k: v for k, v in FULL_ROW.items() if k != "vcp_proximity_90d"},
    "no_sma": {k: v for k, v in FULL_ROW.items() if not k.startswith("sma")},
    "no_volume": {**FULL_ROW, "avg_vol_50d": None},
    "thin_volume": {**FULL_ROW, "volume": 500.0},
    "weak_vcp": {**FULL_ROW, "vcp_atr_compression_5d_90d": 0.9},
    "no_ema": {k: v for k, v in FULL_ROW.items() if k != "ema_21d"},
    "no_pb": {**FULL_ROW, "pullback_ready": 0, "pocket_pivot_score": 0.0},
}

PRICES = [None, 100.0, 96.0, 106.0, 0.0]


def _triggers() -> list[dict]:
    return [
        {"type": "pivot_breakout"},
        {"type": "pivot_breakout", "lookback_days": 5},
        {"type": "pivot_breakout", "volume_multiplier": 1.5},
        {"type": "breakout", "lookback_days": 90, "volume_multiplier": 1.2},
        {"type": "vcp_complete"},
        {"type": "vcp_complete", "max_compression": 0.2, "max_dryup": 0.4, "min_proximity": 0.98},
        {"type": "pullback_to_sma"},
        {"type": "pullback_to_sma", "sma_period": 10, "max_deviation_pct": 0.02},
        {"type": "ema_cross"},
    ]


@pytest.mark.parametrize("trigger", _triggers(), ids=lambda t: str(sorted(t.items())))
@pytest.mark.parametrize("row_name", sorted(ROWS))
@pytest.mark.parametrize("px", PRICES)
def test_enum_equals_compiled_ast(trigger: dict, row_name: str, px) -> None:
    row = ROWS[row_name]
    legacy = evaluate_single_trigger(row, trigger, current_price=px)
    ast = compile_entry_trigger(trigger)
    assert ast is not None
    compiled = evaluate_slot_bool(trigger_eval_row(row, px), ast)
    assert compiled == legacy, (
        f"{trigger} on {row_name} px={px}: enum={legacy} ast={compiled}"
    )


# ---------------------------------------------------------------------------
# The expr form and mixed lists
# ---------------------------------------------------------------------------


def test_expr_form_evaluates_via_slot_eval() -> None:
    trig = {"expr": {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
                     "right": {"type": "lit", "value": 90}}}
    assert evaluate_single_trigger({"rs_rating": 95}, trig) is True
    assert evaluate_single_trigger({"rs_rating": 80}, trig) is False


def test_expr_form_sees_injected_price_cols() -> None:
    trig = {"expr": {"type": "gte", "left": {"type": "col", "name": "__px"},
                     "right": {"type": "lit", "value": 50}}}
    assert evaluate_single_trigger({}, trig, current_price=55.0) is True
    assert evaluate_single_trigger({}, trig, current_price=45.0) is False
    # __px not injected when no live price → fails closed
    assert evaluate_single_trigger({"close": 100.0}, trig) is False


def test_close_px_falls_back_to_row_close() -> None:
    trig = {"expr": {"type": "gte", "left": {"type": "col", "name": "__close_px"},
                     "right": {"type": "lit", "value": 90}}}
    assert evaluate_single_trigger({"close": 100.0}, trig) is True
    assert evaluate_single_trigger({"close": 80.0}, trig, current_price=95.0) is True


def test_expr_form_mixed_with_enum_in_list() -> None:
    from sigmarail_spec.evaluate import evaluate_entry_triggers

    triggers = [
        {"type": "ema_cross"},
        {"expr": {"type": "gte", "left": {"type": "col", "name": "x"},
                  "right": {"type": "lit", "value": 1}}},
    ]
    # ema_cross fails on this row; the expr saves the OR
    assert evaluate_entry_triggers({"ema_21d": 1, "sma50d": 2, "x": 5}, triggers) is True
    # both fail → False
    assert evaluate_entry_triggers({"ema_21d": 1, "sma50d": 2, "x": 0}, triggers) is False


def test_compile_returns_none_for_expr_and_unknown() -> None:
    assert compile_entry_trigger({"expr": {"type": "lit", "value": 1}}) is None
    assert compile_entry_trigger({"type": "not_a_trigger"}) is None
    assert compile_entry_trigger({"type": "unknown_x"}) is None


def test_every_enum_type_compiles() -> None:
    for ttype in ENUM_TRIGGER_TYPES:
        assert compile_entry_trigger({"type": ttype}) is not None
