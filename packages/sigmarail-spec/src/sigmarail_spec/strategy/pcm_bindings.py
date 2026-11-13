"""Canonical registry of PCM runtime bindings — the ``ref`` Operand's namespaces.

**Why this lives here.** ``{"type": "ref", "ns": …, "field": …}`` nodes inside PCM
``rules`` and ``size_expr`` resolve against the decision-unit context the runtime
supplies in ``RiskBudgetedPortfolioConstructionModel.CreateTargets``. That context
is defined by this tree, so the catalog of namespaces, fields, and docs lives here.
Studio serves it read-only; it must not be re-authored in the frontend.

**The decision-unit model.** PCM evaluates one unified rules pass per rebalance.
Each *decision unit* is either:

- a **candidate** — an Up/Down insight from Alpha (``cand.*`` populated;
  ``hold.*`` populated too when the symbol is already held — an "add" unit), or
- a **holding** — an invested symbol with no insight today (``cand.*`` empty;
  the unit exists so rules like the drift cap can act on quiet days).

``acct.*`` is shared mutable state for the whole pass: ``slots_remaining``
decrements as ``enter`` actions consume slots, so ordering by insight rank is
the allocation order — the same sequential-greedy semantics the procedural
code used. ``pyr.*`` is the per-symbol pyramid-phase state. ``regime.*`` is the
regime inputs resolved once per pass.

**Book-level expressions** (C-FW-RULES Phase 3). Three Operand ASTs run once
per pass before the unit loop, so even book policy is data:

- ``scale_expr`` → ``regime.scale`` (contexts: ``regime`` raw + ``acct``).
- ``slots_expr`` → ``acct.scaled_max_positions`` (same contexts, with
  ``regime.scale`` already resolved).
- ``order_expr`` → unit sort key (light contexts: ``cand.{rank,has_insight,
  is_new,is_add,confidence,weight,rs}``, ``hold.invested``, ``acct``,
  ``regime``; evaluated before the full unit build, so deep ``hold.*``/
  ``pyr.*`` are absent there).

A binding that is empty for the unit (e.g. ``cand.*`` on a holding unit, or
``hold.*`` on a fresh candidate) resolves to ``None`` — comparisons fail
closed, so a rule can never fire on context it doesn't have.
"""

from __future__ import annotations

from typing import TypedDict


class PcmBinding(TypedDict):
    """One runtime PCM binding, as served to Studio's field catalog."""

    field: str
    label: str
    description: str
    type: str  # "number" | "bool" — bools compare as 0/1


PCM_BINDING_NAMESPACES: dict[str, list[PcmBinding]] = {
    "cand": [
        {
            "field": "has_insight",
            "label": "Has insight today",
            "description": (
                "True when the unit is driven by an Alpha insight. False on "
                "quiet-day holding units — gate holding-only rules (drift cap) "
                "on `cand.has_insight == 0` so insight-driven targets win."
            ),
            "type": "bool",
        },
        {
            "field": "is_new",
            "label": "New entry candidate",
            "description": "Up insight on a symbol not currently held.",
            "type": "bool",
        },
        {
            "field": "is_add",
            "label": "Pyramid add candidate",
            "description": (
                "Up insight on a symbol already held. Whether it can actually "
                "add still depends on phase state and add conditions."
            ),
            "type": "bool",
        },
        {
            "field": "is_down",
            "label": "Down insight",
            "description": (
                "Down direction — the candidate wants the holding closed "
                "(flatten target). A Flat insight is 'no opinion' and does not "
                "set this."
            ),
            "type": "bool",
        },
        {
            "field": "price",
            "label": "Candidate price",
            "description": "Current trade price for the insight's symbol.",
            "type": "number",
        },
        {
            "field": "confidence",
            "label": "Insight confidence",
            "description": (
                "Alpha-stamped Insight.Confidence (0–1). In the generated "
                "size_expr it multiplies the risk budget when "
                "honor_insight_confidence is on."
            ),
            "type": "number",
        },
        {
            "field": "weight",
            "label": "Insight weight",
            "description": (
                "Alpha-stamped numeric Insight.Weight (0 when absent). The "
                "generated size_expr caps the computed weight at this when set."
            ),
            "type": "number",
        },
        {
            "field": "stop_price",
            "label": "Insight stop price",
            "description": (
                "Insight.StopLossPrice when Alpha stamps one; the engine falls "
                "back to price × (1 − default_stop_loss_pct) before evaluation."
            ),
            "type": "number",
        },
        {
            "field": "stop_distance_frac",
            "label": "Stop distance (frac)",
            "description": (
                "Resolved stop distance as a fraction of price — "
                "(price − stop) / price on the underlying stock, leverage-"
                "adjusted for surrogate trades. The sizing denominator."
            ),
            "type": "number",
        },
        {
            "field": "leader_exempt",
            "label": "Leader exemption",
            "description": (
                "Insight.IsLeaderExemption — elite-RS names may enter during "
                "risk-off when the ladder's regime rule allows it."
            ),
            "type": "bool",
        },
        {
            "field": "leverage",
            "label": "Trade leverage",
            "description": (
                "Effective leverage of the instrument the PCM will trade "
                "(surrogate router output; 1.0 for the plain stock)."
            ),
            "type": "number",
        },
        {
            "field": "eff_leverage",
            "label": "Sizing leverage",
            "description": (
                "Leverage divisor applied in dollar-risk-parity surrogate "
                "sizing mode; 1.0 otherwise. Keeps surrogate mode a visible "
                "operand in size_expr."
            ),
            "type": "number",
        },
        {
            "field": "rs",
            "label": "Candidate RS",
            "description": (
                "Resolved RS rating for the candidate — today's screener row "
                "with the engine's last-known fallback. Displacement rules "
                "qualify challengers on it."
            ),
            "type": "number",
        },
        {
            "field": "confirm_price",
            "label": "Confirmed price",
            "description": (
                "Store-confirmed close when available, else the LEAN mark — "
                "the add-trigger anchor price."
            ),
            "type": "number",
        },
        {
            "field": "cooldown_active",
            "label": "Re-entry cooldown",
            "description": (
                "True while the symbol sits inside a displacement cooldown "
                "armed by an earlier `displace` action."
            ),
            "type": "bool",
        },
        {
            "field": "rank",
            "label": "Allocation rank",
            "description": (
                "The unit's position in the allocation order — insights take "
                "Alpha order 0..n-1, quiet holdings follow. The generated "
                "order_expr is `ref cand.rank` (reproduces Alpha rank order); "
                "author a different key to re-prioritize the pass."
            ),
            "type": "number",
        },
    ],
    "hold": [
        {
            "field": "invested",
            "label": "Holding invested",
            "description": "True when the unit's symbol is currently held.",
            "type": "bool",
        },
        {
            "field": "weight",
            "label": "Current weight",
            "description": (
                "Holding's market value as a fraction of portfolio value. The "
                "drift-cap rule compares this to the configured cap."
            ),
            "type": "number",
        },
        {
            "field": "entry",
            "label": "Average entry",
            "description": "Volume-weighted average cost of the aggregate holding.",
            "type": "number",
        },
        {
            "field": "price",
            "label": "Holding price",
            "description": "Current mark of the held symbol.",
            "type": "number",
        },
        {
            "field": "days_held",
            "label": "Days held",
            "description": (
                "Calendar age of the position from the pyramid state. Fresh "
                "states recorded on re-hydration start near zero."
            ),
            "type": "number",
        },
        {
            "field": "open_r",
            "label": "Open profit (R)",
            "description": (
                "(price − avg_cost) / (avg_cost × default_stop_loss_pct) — the "
                "incumbent-quality yardstick displacement rules use."
            ),
            "type": "number",
        },
        {
            "field": "rs",
            "label": "Last-known RS",
            "description": (
                "RS rating with the engine's fallback chain (today's row → "
                "last-known → recorded at entry)."
            ),
            "type": "number",
        },
    ],
    "acct": [
        {
            "field": "slots_remaining",
            "label": "Slots remaining",
            "description": (
                "Live counter — scaled_max_positions minus invested count, "
                "decremented by `enter`, incremented by `displace`. Entry "
                "rules gate on `acct.slots_remaining > 0`."
            ),
            "type": "number",
        },
        {
            "field": "scaled_max_positions",
            "label": "Scaled max positions",
            "description": (
                "max_positions × regime scale, floored at "
                "scaled_max_positions_floor — the pass's position ceiling."
            ),
            "type": "number",
        },
        {
            "field": "invested_count",
            "label": "Invested count",
            "description": "Number of currently invested symbols.",
            "type": "number",
        },
        {
            "field": "portfolio_value",
            "label": "Portfolio value",
            "description": "Total portfolio value at this pass.",
            "type": "number",
        },
        {
            "field": "cash_pct",
            "label": "Cash fraction",
            "description": "Portfolio cash as a fraction of total value.",
            "type": "number",
        },
        {
            "field": "invested_weight",
            "label": "Invested weight",
            "description": "Sum of current holding weights — the deployed fraction.",
            "type": "number",
        },
        {
            "field": "max_positions",
            "label": "Max positions",
            "description": (
                "The configured position ceiling before regime scaling — "
                "book-level input to the generated slots_expr "
                "(`acct.max_positions * regime.scale`)."
            ),
            "type": "number",
        },
        {
            "field": "slots_floor",
            "label": "Scaled slots floor",
            "description": (
                "scaled_max_positions_floor — the regime-scaled slot count "
                "never drops below this (0 lets risk-off go fully flat). "
                "Book-level input to slots_expr."
            ),
            "type": "number",
        },
        {
            "field": "risk_budget_pct",
            "label": "Risk budget per name",
            "description": (
                "risk_per_trade_pct — the configured 1R budget fraction. "
                "Live input to the generated size_expr (risk_budget ÷ "
                "stop distance)."
            ),
            "type": "number",
        },
        {
            "field": "max_weight",
            "label": "Max name weight",
            "description": (
                "max_position_weight — the per-name weight cap. Live input "
                "to size_expr's min() cap and the drift_cap resize."
            ),
            "type": "number",
        },
    ],
    "pyr": [
        {
            "field": "phase_index",
            "label": "Phase index",
            "description": "0-based index of the current pyramid phase; -1 when unphased.",
            "type": "number",
        },
        {
            "field": "phases_remaining",
            "label": "Phases remaining",
            "description": "Adds still available before the final phase.",
            "type": "number",
        },
        {
            "field": "entry_frac",
            "label": "Entry phase fraction",
            "description": (
                "Fraction of the full target weight a new entry deploys "
                "(phases[0].size_pct). The generated `enter` action uses it as "
                "size_scale."
            ),
            "type": "number",
        },
        {
            "field": "add_frac",
            "label": "Add target fraction",
            "description": (
                "Cumulative fraction of the full target after the next phase "
                "advance — the `add` action's size_scale. 0 when phases are "
                "exhausted."
            ),
            "type": "number",
        },
        {
            "field": "entry_price",
            "label": "Phase entry price",
            "description": (
                "Price recorded when the pyramid state opened — the add "
                "trigger's anchor (distinct from hold.entry, the blended "
                "average cost)."
            ),
            "type": "number",
        },
        {
            "field": "add_trigger_pct",
            "label": "Add trigger",
            "description": "Confirm-price move over phase entry price required to add.",
            "type": "number",
        },
    ],
    "regime": [
        {
            "field": "scale",
            "label": "Regime scale",
            "description": (
                "Effective deployment fraction — raw regime fraction floored "
                "at min_regime_fraction when scaling is enabled; 1.0 when the "
                "scale_exposure use is off."
            ),
            "type": "number",
        },
        {
            "field": "fraction",
            "label": "Raw regime fraction",
            "description": "The store's weekly allocation fraction before the floor.",
            "type": "number",
        },
        {
            "field": "on",
            "label": "Regime score on",
            "description": (
                "allows_new_longs_from_regime_signals — the score-side bull "
                "flag. Gates `block_new_longs`/`skip_pyramid_adds` rules."
            ),
            "type": "bool",
        },
        {
            "field": "scaling_on",
            "label": "Scaling enabled",
            "description": "True when the scale_exposure use is active on this PCM.",
            "type": "bool",
        },
        {
            "field": "min_fraction",
            "label": "Min regime fraction",
            "description": (
                "min_regime_fraction — the configured floor inside the "
                "generated scale_expr (`max(regime.min_fraction, "
                "regime.fraction)`)."
            ),
            "type": "number",
        },
    ],
}


def namespaces() -> list[str]:
    return list(PCM_BINDING_NAMESPACES)


def bindings_for(ns: str) -> list[PcmBinding]:
    return list(PCM_BINDING_NAMESPACES.get(ns, []))


def binding_fields(ns: str) -> set[str]:
    return {b["field"] for b in PCM_BINDING_NAMESPACES.get(ns, [])}


def all_fields() -> set[tuple[str, str]]:
    return {
        (ns, b["field"]) for ns, items in PCM_BINDING_NAMESPACES.items() for b in items
    }
