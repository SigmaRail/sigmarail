"""Canonical SwingProgressive risk-ladder generator (C-FW-RULES).

Single source of truth for the default rule table: every post-entry decision —
protective stops, chandelier trail, time stops, tranches, weight cap, breakeven
ratchet — is emitted as a rule AST so a stored/generated spec fully describes
runtime behavior. There is no procedural decision code underneath this.

Consumed by:
  - ``vera_lab.runtime.qc_swing_risk`` (generated mode: ``rules=None``), and
  - ``vera_query_core.strategy`` (compile-time materialization into
    ``Parameters.rules`` so the saved spec is self-describing) — bridged via
    ``vera_query_core.strategy.risk_ladder`` because the LEAN container only
    carries ``vera_lab`` + vendored ``vera_spec``, never ``vera_query_core``.

Pure dict-building: no runtime imports, no store/algorithm access — safe for
both the IR layer and the container.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "generate_default_init_stop",
    "generate_swing_risk_ladder",
    "time_stop_skip_ast",
]

# Rule-literal keys that policy_overrides may re-materialize in generated mode.
# Authored rules are authoritative and never re-materialized; and once a spec
# carries materialized ``Parameters.rules`` the knobs are inert at runtime, so
# override rematerialization only matters for direct-Python ``rules=None``
# construction.
OVERRIDABLE_LADDER_KEYS = frozenset(
    {"trailing_stop_pct", "breakeven_time_stop_days", "max_holding_days"}
)


def time_stop_skip_ast(
    *,
    risk_skip_time_stop_expr: dict | None = None,
    time_stop_skip_if: dict | None = None,
) -> dict | None:
    """Convert the time-stop skip bindings into a BoolExprItem.

    The result is embedded *inside* the generated time-stop rules' ``when``
    clauses — the skip narrows those rules only, never short-circuits the
    whole rule set the way the removed procedural path did.

    Sources, in precedence order:
      - ``risk_skip_time_stop_expr``: a raw SlotExpr AST, embedded as-is.
      - ``time_stop_skip_if`` (legacy binding): ``above_entry`` maps to
        ``pos.price > pos.entry``; ``all_of`` cols map to
        ``col != 0`` checks. ``above_entry`` was required historically, so
        a binding without it produces no skip rule material.
    """
    if risk_skip_time_stop_expr is not None:
        return dict(risk_skip_time_stop_expr)
    skip = time_stop_skip_if or {}
    if not skip.get("above_entry"):
        return None
    items: list[dict] = [
        {
            "type": "gt",
            "left": {"type": "pos", "field": "price"},
            "right": {"type": "pos", "field": "entry"},
        }
    ]
    for col_name in skip.get("all_of") or []:
        items.append(
            {
                "type": "neq",
                "left": {"type": "col", "name": str(col_name)},
                "right": {"type": "lit", "value": 0},
            }
        )
    return items[0] if len(items) == 1 else {"type": "all", "items": items}


def generate_default_init_stop(
    *,
    use_atr_stops: bool = True,
    atr_stop_multiplier: float = 2.0,
    max_stop_loss_pct: float = 0.05,
) -> dict:
    """Materialize the position-init stop as an Operand AST (C-VERA-EXPR-V2).

    Encodes the same computation ``qc_swing_risk._compute_initial_stop``
    performs — evaluated once at fill against the init context
    (``pos.entry``, ``pos.atr``, ``pos.leverage``)::

        floor_frac = 1 - min(0.35, max_stop_loss_pct * pos.leverage)
        atr_stop   = pos.entry - atr_stop_multiplier * pos.atr
        pct_stop   = pos.entry * floor_frac
        init_stop  = max(atr_stop, pct_stop)   when atr > 0 (and use_atr_stops)
                   = pct_stop                  otherwise

    ``use_atr_stops`` is baked at generation: ``False`` emits just the
    ``pct_stop`` operand — there is no dead conditional in the stored AST.
    The knobs remain *generation* inputs; the emitted AST is what the runtime
    executes, so a stored spec carries the actual initial-stop computation.
    """
    entry = {"type": "pos", "field": "entry"}
    atr = {"type": "pos", "field": "atr"}
    lev = {"type": "pos", "field": "leverage"}
    floor_frac = {
        "type": "formula",
        "op": "-",
        "args": [
            {"type": "lit", "value": 1.0},
            {
                "type": "min",
                "args": [
                    {"type": "lit", "value": 0.35},
                    {
                        "type": "formula",
                        "op": "*",
                        "args": [{"type": "lit", "value": float(max_stop_loss_pct)}, lev],
                    },
                ],
            },
        ],
    }
    pct_stop = {"type": "formula", "op": "*", "args": [entry, floor_frac]}
    if not use_atr_stops:
        return pct_stop
    atr_stop = {
        "type": "formula",
        "op": "-",
        "args": [
            entry,
            {
                "type": "formula",
                "op": "*",
                "args": [{"type": "lit", "value": float(atr_stop_multiplier)}, atr],
            },
        ],
    }
    return {
        "type": "cond",
        "when": {
            "type": "gt",
            "left": atr,
            "right": {"type": "lit", "value": 0},
        },
        "then": {"type": "max", "args": [atr_stop, pct_stop]},
        "otherwise": pct_stop,
    }


def generate_swing_risk_ladder(
    *,
    take_profit_r: float = 2.5,
    tranche1_sell_pct: float = 0.20,
    tranche2_r: float = 4.5,
    tranche2_sell_pct: float = 0.33,
    tranche3_r: float = 8.0,
    tranche3_sell_pct: float = 0.33,
    # Legacy knob — absorbed but unused: concentration capping moved to the PCM
    # (max_position_weight governs entry sizing AND post-fill drift trims). Old
    # specs keep their stored max_weight_cap/cap_weight rule and it still runs.
    max_single_weight: float = 0.20,
    trailing_stop_pct: float = 0.15,
    trailing_arm_r: float = 3.0,
    breakeven_r_trigger: float = 1.5,
    max_holding_days: int = 25,
    breakeven_time_stop_days: int = 10,
    stop_cooldown_days: int = 10,
    tranches: list | None = None,
    time_stop_skip_if: dict | None = None,
    risk_skip_time_stop_expr: dict | None = None,
    overrides: dict | None = None,
    max_hold_days: int | None = None,
    **_ignored: Any,
) -> list[dict]:
    """Materialize the complete risk ladder as ordered rule ASTs.

    Parameters mirror the ``SwingProgressiveRiskManagementModel`` ctor knobs
    (and the spec ``Parameters`` names) so the compiler can call this directly
    on resolved ``risk_params``. ``tranches`` documents normalize onto the flat
    ``tranche*`` knobs exactly as the ctor does; ``max_hold_days`` is the legacy
    alias for ``max_holding_days``.

    ``overrides`` carries resolved ``policy_overrides`` values — only
    ``OVERRIDABLE_LADDER_KEYS`` apply (generated mode only).

    Ordering mirrors the reverted procedural ladder: the chandelier ratchets
    BEFORE the breach check (raise the floor, then test it), protective stops
    precede discretionary exits, tranches precede the breakeven trigger.
    Terminality derives from the actions — rules whose ``then`` contains only
    non-terminal actions (ratchet_stop/arm_cooldown/set_flag; cap_weight remains
    readable for old specs) apply and pass control to the next rule; the first
    rule with a terminal action (exit/trim) wins the bar.

    Scope: the ladder is position-lifecycle only — stops, trails, tranche
    profit-taking, time stops, cooldowns. Portfolio-shape controls (position
    weight caps, regime exposure scaling) live in the PCM, not here.
    """
    if max_hold_days is not None:
        try:
            max_holding_days = int(max_hold_days)
        except (TypeError, ValueError):
            pass
    if tranches:
        try:
            t0 = tranches[0] if len(tranches) > 0 else None
            t1 = tranches[1] if len(tranches) > 1 else None
            t2 = tranches[2] if len(tranches) > 2 else None
            if isinstance(t0, dict):
                if t0.get("trigger_r") is not None:
                    take_profit_r = float(t0["trigger_r"])
                if t0.get("sell_pct") is not None:
                    tranche1_sell_pct = float(t0["sell_pct"])
            if isinstance(t1, dict):
                if t1.get("trigger_r") is not None:
                    tranche2_r = float(t1["trigger_r"])
                if t1.get("sell_pct") is not None:
                    tranche2_sell_pct = float(t1["sell_pct"])
            if isinstance(t2, dict):
                if t2.get("trigger_r") is not None:
                    tranche3_r = float(t2["trigger_r"])
                if t2.get("sell_pct") is not None:
                    tranche3_sell_pct = float(t2["sell_pct"])
        except (TypeError, ValueError, KeyError):
            pass

    ov = overrides or {}
    trail_pct = float(ov.get("trailing_stop_pct", trailing_stop_pct))
    arm_r = float(trailing_arm_r)
    be_days = int(ov.get("breakeven_time_stop_days", breakeven_time_stop_days))
    hold_days = int(ov.get("max_holding_days", max_holding_days))
    tp_r = float(take_profit_r)
    t1_sell = float(tranche1_sell_pct)
    t2_r = float(tranche2_r)
    t2_sell = float(tranche2_sell_pct)
    t3_r = float(tranche3_r)
    t3_sell = float(tranche3_sell_pct)
    cooldown = int(stop_cooldown_days)
    be_trigger_r = float(breakeven_r_trigger)

    def pc(name: str) -> dict:  # position binding ref
        return {"type": "pos", "field": name}

    def lit(v) -> dict:
        return {"type": "lit", "value": v}

    def fml(op: str, a: dict, b: dict) -> dict:
        return {"type": "formula", "op": op, "args": [a, b]}

    def cmp_(t: str, l: dict, r: dict) -> dict:
        return {"type": t, "left": l, "right": r}

    # "Trailing" vs "hard" tag fidelity: a breach counts as trailing only when
    # the stop has been ratcheted above the initial stop AND the trail regime
    # is live (r >= arm_r, or a tranche1 winner via runner_active).
    trail_armed = {
        "type": "all",
        "items": [
            cmp_("gt", pc("current_stop"), fml("+", pc("initial_stop"), lit(1e-9))),
            {
                "type": "any",
                "items": [
                    cmp_("gte", pc("r"), lit(arm_r)),
                    cmp_("neq", pc("runner_active"), lit(0)),
                ],
            },
        ],
    }
    breached = cmp_("lte", pc("check_price"), pc("current_stop"))

    rules: list[dict] = [
        {
            "name": "chandelier_trail",
            "priority": -5,
            "when": cmp_("gte", pc("r"), lit(arm_r)),
            "then": [
                {
                    "type": "ratchet_stop",
                    "to": fml("*", pc("highest_price"), lit(1.0 - trail_pct)),
                    "mode": "max",
                }
            ],
            "tag": "trailing_stop",
            "description": (
                f"Once the trade is ≥{arm_r:g}R in profit, trail the protective stop "
                f"{trail_pct * 100:g}% under the highest price since entry — the "
                "runner's giveback ceiling. Non-terminal: only raises the stop."
            ),
        },
        {
            "name": "trailing_stop",
            "priority": 0,
            "when": {"type": "all", "items": [breached, trail_armed]},
            "then": [
                {"type": "exit", "fraction": 1.0},
                {"type": "arm_cooldown", "days": cooldown},
            ],
            "tag": "trailing_stop",
            "description": (
                "Exit the whole position when price breaches a ratcheted stop and the "
                "trail regime is armed (stop above initial AND r≥arm or runner). Tags "
                "the exit as 'trailing' and suppresses re-entry for the cooldown window."
            ),
        },
        {
            "name": "hard_stop",
            "priority": 1,
            "when": {"type": "all", "items": [breached, {"type": "not", "item": trail_armed}]},
            "then": [
                {"type": "exit", "fraction": 1.0},
                {"type": "arm_cooldown", "days": cooldown},
            ],
            "tag": "hard_stop",
            "description": (
                "Exit the whole position on any breach of the protective stop before the "
                "trail regime has armed — this is the initial-stop loss line. Arms the "
                "re-entry cooldown."
            ),
        },
    ]

    time_stop_guard = [
        cmp_("gte", pc("days_held"), lit(be_days)),
        cmp_("lt", pc("r"), lit(1.0)),
        cmp_("eq", pc("time_stop_partial_taken"), lit(False)),
        cmp_("eq", pc("tranche1_taken"), lit(False)),
    ]
    skip_ast = time_stop_skip_ast(
        risk_skip_time_stop_expr=risk_skip_time_stop_expr,
        time_stop_skip_if=time_stop_skip_if,
    )
    if skip_ast is not None:
        # entry > 0 guard preserves the old fail-closed contract: a broken
        # entry falls through to the partial cut instead of skipping into
        # the breakeven ratchet.
        skip_guarded = {"type": "all", "items": [cmp_("gt", pc("entry"), lit(0)), skip_ast]}
        rules.append(
            {
                "name": "time_stop_breakeven_ratchet",
                "priority": 9,
                "when": {"type": "all", "items": [*time_stop_guard, skip_guarded]},
                "then": [
                    {"type": "ratchet_stop", "to": pc("entry"), "mode": "max"},
                    {"type": "set_flag", "flag": "time_stop_partial_taken"},
                ],
                "tag": "time_stop",
                "description": (
                    f"If the trade is still under 1R after {be_days} days but the "
                    "skip predicate holds (setup still valid), pull the stop up to "
                    "breakeven instead of selling — keeps the trade at ~zero downside "
                    "and marks the time-stop as consumed."
                ),
            }
        )
        time_stop_guard = [*time_stop_guard, {"type": "not", "item": skip_guarded}]
    rules.append(
        {
            "name": "time_stop_partial",
            "priority": 10,
            "when": {"type": "all", "items": time_stop_guard},
            "then": [
                {"type": "trim", "fraction": 0.5},
                {"type": "set_flag", "flag": "time_stop_partial_taken"},
            ],
            "tag": "time_stop",
            "description": (
                f"If the trade is still under 1R after {be_days} days and no tranche "
                "has fired, cut half — recycle capital out of dead trades while "
                "leaving a reduced position in case it recovers."
            ),
        }
    )
    rules.append(
        {
            "name": "time_stop_full",
            "priority": 11,
            "when": {
                "type": "all",
                "items": [
                    cmp_("gte", pc("days_held"), lit(hold_days)),
                    cmp_("lt", pc("r"), lit(1.0)),
                ],
            },
            "then": [
                {"type": "exit", "fraction": 1.0},
                {"type": "arm_cooldown", "days": cooldown},
            ],
            "tag": "time_stop",
            "description": (
                f"Hard age-out: exit the entire position after {hold_days} days if it "
                "never reached 1R — capital rotation rule. Arms the re-entry cooldown."
            ),
        }
    )

    rules += [
        {
            "name": "tranche1",
            "priority": 20,
            "when": {
                "type": "all",
                "items": [
                    cmp_("gte", pc("r"), lit(tp_r)),
                    cmp_("eq", pc("tranche1_taken"), lit(False)),
                ],
            },
            "then": [
                {"type": "trim", "fraction": t1_sell},
                {
                    "type": "ratchet_stop",
                    "to": fml("+", pc("entry"), fml("*", pc("r_unit"), lit(0.5))),
                    "mode": "max",
                },
                {"type": "set_flag", "flag": "tranche1_taken"},
                {"type": "set_flag", "flag": "runner_active"},
            ],
            "tag": "tranche1",
            "description": (
                f"First profit milestone: at +{tp_r:g}R sell {t1_sell * 100:g}% of the "
                "position, pull the stop to entry+0.5R, and flag runner mode (which "
                "arms the trailing regime for the remainder)."
            ),
        },
        {
            "name": "tranche2",
            "priority": 21,
            "when": {
                "type": "all",
                "items": [
                    cmp_("eq", pc("tranche1_taken"), lit(True)),
                    cmp_("eq", pc("tranche2_taken"), lit(False)),
                    cmp_("gte", pc("r"), lit(t2_r)),
                ],
            },
            "then": [
                {"type": "trim", "fraction": t2_sell},
                {
                    "type": "ratchet_stop",
                    "to": fml("+", pc("entry"), fml("*", pc("r_unit"), lit(2.0))),
                    "mode": "max",
                },
                {"type": "set_flag", "flag": "tranche2_taken"},
            ],
            "tag": "tranche2",
            "description": (
                f"Second profit milestone: at +{t2_r:g}R (requires tranche1 already "
                f"taken) sell another {t2_sell * 100:g}% and pull the stop to entry+2R."
            ),
        },
        {
            "name": "tranche3",
            "priority": 22,
            "when": {
                "type": "all",
                "items": [
                    cmp_("eq", pc("tranche2_taken"), lit(True)),
                    cmp_("eq", pc("tranche3_taken"), lit(False)),
                    cmp_("gte", pc("r"), lit(t3_r)),
                ],
            },
            "then": [
                {"type": "trim", "fraction": t3_sell},
                {
                    "type": "ratchet_stop",
                    "to": fml("+", pc("entry"), fml("*", pc("r_unit"), lit(4.0))),
                    "mode": "max",
                },
                {"type": "set_flag", "flag": "tranche3_taken"},
            ],
            "tag": "tranche3",
            "description": (
                f"Final programmed de-risking: at +{t3_r:g}R sell another "
                f"{t3_sell * 100:g}% and pull the stop to entry+4R — what remains is "
                "the runner, managed by the chandelier trail."
            ),
        },
        {
            "name": "breakeven_trigger",
            "priority": 70,
            "when": {
                "type": "all",
                "items": [
                    cmp_("eq", pc("tranche1_taken"), lit(False)),
                    cmp_("gte", pc("r"), lit(be_trigger_r)),
                ],
            },
            "then": [
                {
                    "type": "ratchet_stop",
                    "to": fml("+", pc("entry"), fml("*", pc("r_unit"), lit(0.2))),
                    "mode": "max",
                }
            ],
            "tag": "breakeven_trigger",
            "description": (
                f"Before any tranche fires, once the trade reaches +{be_trigger_r:g}R "
                "pull the stop to entry+0.2R — worst case becomes roughly a scratch "
                "from that point on."
            ),
        },
    ]
    return rules
