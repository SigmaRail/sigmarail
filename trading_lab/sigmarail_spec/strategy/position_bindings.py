"""Canonical registry of runtime position bindings — the ``pos`` Operand's vocabulary.

**Why this lives here.** A ``{"type": "pos", "field": …}`` node resolves against the
position context the runtime supplies to the slot evaluators — see
``SwingProgressiveRiskManagementModel._evaluate_rules`` (live context) and the
``init_stop`` evaluation at position open (init context) in
``vera_lab/runtime/qc_swing_risk.py``. That context is defined by this tree, so the
catalog of names, labels, docs, and valid contexts lives here too. Studio serves it
read-only; it must not be re-authored in the frontend.

Two contexts, and they are **not** interchangeable:

- ``init`` — what exists at the moment of first fill, when ``init_stop`` is
  evaluated: ``entry``, ``atr``, ``leverage`` (plus the T-1 screener row).
- ``live`` — what exists on every subsequent risk check while the position is
  open: everything below marked ``live`` (plus the screener row and any flags
  planted by ``set_flag`` actions).

A ``live``-only binding inside ``init_stop`` evaluates to ``None`` and the
``cond``/fallback machinery handles it — but lint should flag it, because it is
almost always an authoring error, not a deliberate fallback.
"""

from __future__ import annotations

from typing import TypedDict


class PositionBinding(TypedDict):
    """One runtime position binding, as served to Studio's field catalog."""

    field: str
    label: str
    description: str
    type: str  # "number" | "bool" — bools compare as 0/1
    contexts: list[str]  # subset of ("init", "live")


_INIT = ["init"]
_LIVE = ["live"]
_BOTH = ["init", "live"]

POSITION_BINDINGS: list[PositionBinding] = [
    {
        "field": "entry",
        "label": "Entry price",
        "description": (
            "Average fill price of the aggregate holding (all tranches of the "
            "position share one entry), fixed at the first fill."
        ),
        "type": "number",
        "contexts": _BOTH,
    },
    {
        "field": "atr",
        "label": "ATR at entry",
        "description": (
            "Average true range measured at entry. Available only when the "
            "initial stop is computed — it does not update afterwards."
        ),
        "type": "number",
        "contexts": _INIT,
    },
    {
        "field": "leverage",
        "label": "Surrogate leverage",
        "description": (
            "Leverage multiplier in effect at entry (from the surrogate router). "
            "Scales the maximum stop-loss floor in the generated init_stop."
        ),
        "type": "number",
        "contexts": _INIT,
    },
    {
        "field": "price",
        "label": "Current price",
        "description": "Latest price of the held symbol at the risk check.",
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "low",
        "label": "Session low",
        "description": "Intraday low of the current session, when available.",
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "check_price",
        "label": "Stop-check price",
        "description": (
            "The price protective-stop conditions compare against: the session "
            "low when known, otherwise the close. Use this (not price) so a "
            "wick through the stop still triggers."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "r",
        "label": "Profit (R)",
        "description": (
            "Current profit measured in R — (price − entry) / r_unit. 1R is "
            "the risk taken at entry; +3R means three times the initial risk."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "r_unit",
        "label": "R unit",
        "description": (
            "One R in price terms: entry − initial_stop. The yardstick every "
            "R-multiple comparison uses."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "initial_stop",
        "label": "Initial stop",
        "description": (
            "Protective stop computed at entry by the init_stop expression. "
            "Never moves; the reference for 'has the stop been ratcheted'."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "current_stop",
        "label": "Current stop",
        "description": (
            "Live protective stop — starts at initial_stop; ratchet_stop "
            "actions move it (mode 'max' can only tighten)."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "highest_price",
        "label": "Highest since entry",
        "description": (
            "Highest price recorded while the position has been open. The "
            "chandelier trail anchors to this."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "days_held",
        "label": "Days held",
        "description": "Calendar age of the position in trading days.",
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "current_weight",
        "label": "Current weight",
        "description": (
            "The holding's market value as a fraction of total portfolio "
            "value, refreshed at every risk check."
        ),
        "type": "number",
        "contexts": _LIVE,
    },
    {
        "field": "stop_cooled",
        "label": "Stop cooldown elapsed",
        "description": (
            "True once the post-stop-out cooldown window has elapsed for this "
            "symbol — gates re-entry after a stop."
        ),
        "type": "bool",
        "contexts": _LIVE,
    },
    {
        "field": "runner_active",
        "label": "Runner active",
        "description": (
            "Set when the position has scaled into runner mode (first profit "
            "tranche taken). Distinct from the trail being armed — runner "
            "mode survives below the arm threshold."
        ),
        "type": "bool",
        "contexts": _LIVE,
    },
    {
        "field": "tranche1_taken",
        "label": "Tranche 1 taken",
        "description": "First profit-taking tranche has sold.",
        "type": "bool",
        "contexts": _LIVE,
    },
    {
        "field": "tranche2_taken",
        "label": "Tranche 2 taken",
        "description": "Second profit-taking tranche has sold.",
        "type": "bool",
        "contexts": _LIVE,
    },
    {
        "field": "tranche3_taken",
        "label": "Tranche 3 taken",
        "description": "Third profit-taking tranche has sold.",
        "type": "bool",
        "contexts": _LIVE,
    },
    {
        "field": "time_stop_partial_taken",
        "label": "Time-stop partial taken",
        "description": "The partial time-stop exit has already fired for this position.",
        "type": "bool",
        "contexts": _LIVE,
    },
]


def bindings_for_context(context: str) -> list[PositionBinding]:
    """Bindings valid in ``context`` — ``"init"`` or ``"live"``."""
    return [b for b in POSITION_BINDINGS if context in b["contexts"]]


def binding_fields() -> set[str]:
    return {b["field"] for b in POSITION_BINDINGS}
