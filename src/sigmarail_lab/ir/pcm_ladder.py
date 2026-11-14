"""Canonical RiskBudgeted PCM allocation-table generator (C-FW-RULES Phase 2).

Single source of truth for the default PCM rule table: every allocation
decision — direction routing, regime gates, entry/add gates, displacement,
pyramid phasing, drift cap — is emitted as a rule AST so a stored/generated
spec fully describes runtime behavior. There is no procedural decision code
underneath this.

The decision-unit model: one pass per rebalance over units — Alpha insights
(``cand.*``) plus insight-quiet holdings (``hold.*``) — evaluated in rank
order with shared ``acct.*`` counters. ``enter`` consumes a slot; ``displace``
frees one; ``resize`` targets existing holdings. ``size_expr`` is the sizing
Operand AST the ``enter``/``add`` actions scale.

Consumed by:
  - ``sigmarail_lab.runtime.qc_risk_budgeted_pcm`` (generated mode: ``rules=None``),
  - ``vera_query_core.strategy`` (compile-time materialization into
    ``Parameters.rules``/``size_expr``) via Studio's bridge — the LEAN
    container only carries ``sigmarail_lab`` + vendored ``sigmarail_spec``.

Pure dict-building: no runtime imports, no store/algorithm access.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "generate_default_size_expr",
    "generate_pcm_ladder",
    "generate_scale_expr",
    "generate_slots_expr",
    "generate_order_expr",
]


def _ref(ns: str, field: str) -> dict:
    return {"type": "ref", "ns": ns, "field": field}


def _lit(v) -> dict:
    return {"type": "lit", "value": v}


def _fml(op: str, a: dict, b: dict) -> dict:
    return {"type": "formula", "op": op, "args": [a, b]}


def _cmp(t: str, l: dict, r: dict) -> dict:
    return {"type": t, "left": l, "right": r}


def _all(*items: dict) -> dict:
    return {"type": "all", "items": list(items)}


def _any(*items: dict) -> dict:
    return {"type": "any", "items": list(items)}


def _not(item: dict) -> dict:
    return {"type": "not", "item": item}


def generate_default_size_expr(
    *,
    risk_per_trade_pct: float = 0.005,
    max_position_weight: float = 0.25,
    honor_insight_confidence: bool = True,
    pcm_scale_expr: dict | None = None,
    **_ignored: Any,
) -> dict:
    """Materialize the base position-sizing formula as an Operand AST.

    Encodes the same math ``CreateTargets._size_insight`` performs — the
    *full-position* target weight (phase fractions are applied by the
    ``enter``/``add`` actions' ``size_scale``, not here)::

        local_max_w = max_position_weight * regime.scale
        ideal_w     = risk_per_trade_pct * regime.scale * conf_scale
                      / cand.stop_distance_frac
        w           = min(local_max_w,
                          cand.weight > 0 ? cand.weight : ideal_w)
                      — a stamped Insight.Weight REPLACES risk sizing
        size        = w / cand.eff_leverage   (dollar-risk-parity surrogate mode;
                                               eff_leverage is 1.0 otherwise)

    ``conf_scale`` is the author's ``pcm_scale`` expression when bound, else
    ``cand.confidence`` under honor_insight_confidence, else ``lit 1`` — the
    branch is chosen at generation so the stored AST has no dead conditional.
    """
    if pcm_scale_expr is not None:
        conf = dict(pcm_scale_expr)
    elif honor_insight_confidence:
        conf = _ref("cand", "confidence")
    else:
        conf = _lit(1.0)

    return _fml(
        "/",
        {
            "type": "min",
            "args": [
                _fml("*", _lit(float(max_position_weight)), _ref("regime", "scale")),
                {
                    "type": "cond",
                    "when": _cmp("gt", _ref("cand", "weight"), _lit(0)),
                    "then": _ref("cand", "weight"),
                    "otherwise": _fml(
                        "/",
                        _fml(
                            "*",
                            _fml("*", _lit(float(risk_per_trade_pct)), _ref("regime", "scale")),
                            conf,
                        ),
                        _ref("cand", "stop_distance_frac"),
                    ),
                },
            ],
        },
        _ref("cand", "eff_leverage"),
    )


def generate_scale_expr(
    *,
    use_regime_scaling: bool = False,
    min_regime_fraction: float = 0.15,  # noqa: ARG001 — feeds regime.min_fraction binding
    **_ignored: Any,
) -> dict:
    """Materialize the book-scale formula — evaluated once per pass → ``regime.scale``.

    Same math the procedural pass ran: scaling off → 1.0; on → the weekly
    fraction floored at ``min_regime_fraction`` (baked literal — the materialized
    AST is the whole policy; ``regime.min_fraction`` stays bound for authored
    exprs).
    """
    if not use_regime_scaling:
        return _lit(1.0)
    return {
        "type": "max",
        "args": [_lit(float(min_regime_fraction)), _ref("regime", "fraction")],
    }


def generate_slots_expr(
    *,
    use_regime_scaling: bool = False,
    scaled_max_positions_floor: int = 2,
    max_positions: int = 8,
    **_ignored: Any,
) -> dict:
    """Materialize the slot-count formula — once per pass → ``acct.scaled_max_positions``.

    ``max(scaled_max_positions_floor, max_positions × regime.scale)`` — magnitudes
    bake as literals so the materialized AST is the whole policy (the
    ``acct.slots_floor``/``acct.max_positions`` bindings remain for authored
    exprs). With scaling off ``regime.scale`` is 1.0, reproducing
    ``max(floor, max_positions)``. The engine casts to int.
    """
    return {
        "type": "max",
        "args": [
            _lit(float(scaled_max_positions_floor)),
            _fml("*", _lit(float(max_positions)), _ref("regime", "scale")),
        ],
    }


def generate_order_expr(**_ignored: Any) -> dict:
    """Materialize the unit-ordering key — once per unit before the rule pass.

    Default is the Alpha-supplied rank (insight list order, quiet holdings
    appended) — the sequential-greedy allocation order the procedural code
    used. Author a different key to reprioritize, e.g. ``-cand.rs`` to fill
    the book highest-RS-first.
    """
    return _ref("cand", "rank")


def generate_pcm_ladder(
    *,
    max_position_weight: float = 0.25,
    allow_adds_on_invested: bool = True,
    use_regime_scaling: bool = False,
    uses: list | tuple | set | None = None,
    phases: list | None = None,
    add_trigger_pct: float = 0.08,
    max_entry_atr_pct: float = 0.0,
    enable_displacement: bool = True,
    displacement_min_hold_days: int = 5,
    displacement_max_incumbent_r: float = 1.0,
    displacement_min_challenger_rs: float = 90.0,
    displacement_min_challenger_screens: int = 3,
    displacement_immune_rs: float = 95.0,
    displacement_cooldown_days: int = 14,
    drift_restore_frac: float = 0.8,
    pcm_allow_entry_expr: dict | None = None,
    risk_allow_pyramid_add_expr: dict | None = None,
    **_ignored: Any,
) -> list[dict]:
    """Materialize the complete PCM allocation table as ordered rule ASTs.

    Parameters mirror the ``RiskBudgetedPortfolioConstructionModel`` ctor knobs
    (and the spec ``Parameters`` names) so the compiler can call this directly
    on resolved ``pcm_params``. Every row documents a decision the runtime used
    to make procedurally — nothing else gates allocation.

    Ordering: exit directions first, then gate rules (skip is terminal — the
    unit is decided), then displacement (non-terminal — frees a slot the
    ``new_entry`` rule can consume), the quiet-day drift cap, the pyramid add,
    and finally the entry. ``when`` clauses gate on unit shape
    (``cand.is_new``/``cand.is_add``/``cand.has_insight``) so one table serves
    candidates and holdings alike.
    """
    uses_set = {str(u) for u in (uses or [])}
    rules: list[dict] = []

    rules.append(
        {
            "name": "down_flatten",
            "priority": -40,
            "when": _cmp("neq", _ref("cand", "is_down"), _lit(0)),
            "then": [{"type": "resize", "to": _lit(0)}],
            "tag": "flatten",
            "description": (
                "A Down insight means close the holding — emit a zero-weight "
                "target for the symbol."
            ),
        }
    )

    rules.append(
        {
            "name": "displacement_cooldown_skip",
            "priority": -30,
            "when": _all(
                _cmp("neq", _ref("cand", "has_insight"), _lit(0)),
                _cmp("neq", _ref("cand", "cooldown_active"), _lit(0)),
            ),
            "then": [{"type": "skip"}],
            "tag": "cooldown",
            "description": (
                f"A symbol displaced within the last {displacement_cooldown_days} "
                "days cannot re-enter — prevents churn on freshly rotated names."
            ),
        }
    )

    if use_regime_scaling:
        rules.append(
            {
                "name": "regime_risk_off_block",
                "priority": -20,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_new"), _lit(0)),
                    _cmp("neq", _ref("regime", "scaling_on"), _lit(0)),
                    _cmp("lte", _ref("regime", "fraction"), _lit(0)),
                    _cmp("eq", _ref("cand", "leader_exempt"), _lit(0)),
                ),
                "then": [{"type": "skip"}],
                "tag": "regime_block",
                "description": (
                    "scale_exposure use: when the regime fraction reads 0, no "
                    "new entries — except candidates Alpha marked RS-90+ "
                    "leader-exempt. Existing holdings keep their targets."
                ),
            }
        )

    if "skip_pyramid_adds" in uses_set:
        rules.append(
            {
                "name": "regime_skip_pyramid_adds",
                "priority": -15,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_add"), _lit(0)),
                    _cmp("eq", _ref("regime", "on"), _lit(0)),
                ),
                "then": [{"type": "skip"}],
                "tag": "regime_block",
                "description": (
                    "skip_pyramid_adds use: adds to existing positions only "
                    "while the regime score is on — no averaging-up in "
                    "risk-off."
                ),
            }
        )

    if pcm_allow_entry_expr is not None:
        rules.append(
            {
                "name": "entry_gate",
                "priority": -10,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_new"), _lit(0)),
                    _not(dict(pcm_allow_entry_expr)),
                ),
                "then": [{"type": "skip"}],
                "tag": "entry_gate",
                "description": (
                    "The pcm_allow_entry binding as a visible gate — new "
                    "entries skip when the expression does not hold."
                ),
            }
        )

    if risk_allow_pyramid_add_expr is not None:
        rules.append(
            {
                "name": "add_gate",
                "priority": -10,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_add"), _lit(0)),
                    _not(dict(risk_allow_pyramid_add_expr)),
                ),
                "then": [{"type": "skip"}],
                "tag": "add_gate",
                "description": (
                    "The risk_allow_pyramid_add binding as a visible gate — "
                    "adds skip when the expression does not hold."
                ),
            }
        )

    if max_entry_atr_pct and float(max_entry_atr_pct) > 0:
        rules.append(
            {
                "name": "add_atr_gate",
                "priority": -9,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_add"), _lit(0)),
                    _cmp(
                        "gt",
                        {"type": "col", "name": "atr_14_pct"},
                        _lit(float(max_entry_atr_pct)),
                    ),
                ),
                "then": [{"type": "skip"}],
                "tag": "atr_gate",
                "description": (
                    f"No adds when the name's volatility ({float(max_entry_atr_pct)*100:g}%+ "
                    "daily ATR) is past the add ceiling — late-stage adds on "
                    "hot names are where pyramids go wrong."
                ),
            }
        )

    if enable_displacement:
        challenger_ok = _any(
            _all(
                _cmp("gte", _ref("cand", "rs"), _lit(float(displacement_min_challenger_rs))),
                _cmp(
                    "gte",
                    {"type": "col", "name": "screens_hit"},
                    _lit(int(displacement_min_challenger_screens)),
                ),
            ),
            _cmp("gte", _ref("cand", "rs"), _lit(95.0)),
        )
        rules.append(
            {
                "name": "displace_weakest",
                "priority": 0,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_new"), _lit(0)),
                    _cmp("lte", _ref("acct", "slots_remaining"), _lit(0)),
                    challenger_ok,
                ),
                "then": [
                    {
                        "type": "displace",
                        "min_incumbent_days": int(displacement_min_hold_days),
                        "max_incumbent_r": float(displacement_max_incumbent_r),
                        "immune_rs": float(displacement_immune_rs),
                        "cooldown_days": int(displacement_cooldown_days),
                        "max_per_day": 2,
                    }
                ],
                "tag": "displacement",
                "description": (
                    "Book full? An elite challenger (RS "
                    f"{displacement_min_challenger_rs:g}+ with "
                    f"{displacement_min_challenger_screens} screens, or RS 95+) "
                    "flattens the weakest incumbent — one held "
                    f"{displacement_min_hold_days}+ days, under "
                    f"{displacement_max_incumbent_r:g}R open profit, below "
                    f"{displacement_immune_rs:g} RS — freeing a slot for the "
                    "new_entry rule below."
                ),
            }
        )

    rules.append(
        {
            "name": "drift_cap",
            "priority": 5,
            "when": _all(
                _cmp("eq", _ref("cand", "has_insight"), _lit(0)),
                _cmp("neq", _ref("hold", "invested"), _lit(0)),
                _cmp("gt", _ref("hold", "weight"), _lit(float(max_position_weight))),
            ),
            "then": [
                {
                    "type": "resize",
                    "to": _lit(float(max_position_weight) * float(drift_restore_frac)),
                }
            ],
            "tag": "drift_cap",
            "description": (
                f"Concentration cap: a holding that drifts above "
                f"{float(max_position_weight)*100:g}% of the book on a quiet "
                f"day resizes back to {drift_restore_frac*100:g}% of the cap. "
                "Units with an insight today are exempt — insight flow wins."
            ),
        }
    )

    if allow_adds_on_invested:
        rules.append(
            {
                "name": "pyramid_add",
                "priority": 10,
                "when": _all(
                    _cmp("neq", _ref("cand", "is_add"), _lit(0)),
                    _cmp("gt", _ref("pyr", "add_frac"), _lit(0)),
                    _cmp("gte", _ref("hold", "days_held"), _lit(1)),
                    _cmp(
                        "gte",
                        _ref("cand", "confirm_price"),
                        _fml(
                            "*",
                            _ref("pyr", "entry_price"),
                            _lit(1.0 + float(add_trigger_pct)),
                        ),
                    ),
                    _cmp("gte", _ref("cand", "price"), _ref("hold", "entry")),
                ),
                "then": [
                    {"type": "add", "size_scale": _ref("pyr", "add_frac")}
                ],
                "tag": "tranche1_add",
                "description": (
                    f"Scale into a winner: phases remaining, held a full day, "
                    f"confirmed price ≥ phase entry +{float(add_trigger_pct)*100:g}%, "
                    "and price not below average cost — then buy up to the next "
                    "phase's cumulative fraction of the full target."
                ),
            }
        )

    rules.append(
        {
            "name": "new_entry",
            "priority": 20,
            "when": _all(
                _cmp("neq", _ref("cand", "is_new"), _lit(0)),
                _cmp("gt", _ref("acct", "slots_remaining"), _lit(0)),
            ),
            "then": [
                {"type": "enter", "size_scale": _ref("pyr", "entry_frac")}
            ],
            "tag": "entry",
            "description": (
                "The entry itself: a free slot and no gate above blocked it — "
                "buy the first pyramid phase (entry_frac × size_expr)."
            ),
        }
    )

    return rules
