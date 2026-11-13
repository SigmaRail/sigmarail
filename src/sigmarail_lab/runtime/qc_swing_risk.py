"""
Progressive Swing Risk Management Model for QuantConnect Framework.

Implements Standard Institutional Swing Trade Lifecycle:
1. Dynamic ATR-Based Stop-Loss: Sizes stop to ATR*multiplier below entry, capped at max_stop_pct.
2. Breakeven Time-Stop: If position not at +1R within breakeven_time_stop_days, exits 50%.
3. Tranche 1 Profit Scaling (+2.5R default): Sells 20% into strength to lock in gains.
4. Breakeven Ratchet: Moves protective stop to Entry + 0.5R once Tranche 1 profit is achieved.
5. Tranche 2 (+4.5R) and Tranche 3 (+8R): Progressive additional scale-outs with stop ratchets.
6. Chandelier Trailing Stop: Trails the remaining runner at highest_price * (1 - trailing_stop_pct).

Post-fill concentration capping is PCM-owned (RiskBudgetedPortfolioConstructionModel
drift-cap on max_position_weight). The cap_weight action is still evaluated so
stored specs carrying a max_weight_cap rule keep working.

Performance Improvements (v2):
- ATR-based stops replace fixed 6% → tighter, adaptive stop sizing per volatility
- T1 trigger widened from 2.0R → 2.5R, trim reduced from 33% → 20% (let more ride)
- Breakeven time-stop: 50% exit if not at +1R by breakeven_time_stop_days
- Tighter max_holding_days (25 vs 30)
- Regime-scaled stop initialization (tight ATR in bull, wider in neutral)
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sigmarail_lab.runtime.policy_overrides import resolve_policy_overrides
from sigmarail_lab.runtime.signal_evaluation import evaluate_slot_bool, evaluate_slot_number
from sigmarail_lab.runtime.action_args import action_arg_number
from sigmarail_lab.runtime._acct_stats import trailing_loss_streak
from sigmarail_lab.ir.risk_ladder import generate_default_init_stop, generate_swing_risk_ladder
from sigmarail_lab.ir.rules import ACTION_TERMINAL, validate_rules

# Node types the row evaluator actually implements (see sigmarail_spec/expr.py and
# sigmarail_spec/evaluate.py). Note "ne" is NOT among them: `evaluate_slot_bool` treats
# an unknown node type as False, so a rule written with `ne` would silently never
# fire. Validation below rejects it at construction time rather than letting an
# exit rule become a silent no-op.
_OPERAND_TYPES = frozenset({"col", "pos", "lit", "formula", "min", "max", "clamp", "abs", "cond"})
_CMP_OPS = frozenset({"gt", "gte", "lt", "lte", "eq", "neq"})
_BOOL_OPS = frozenset({"all", "any", "not"})
_SHORTHAND_OPS = frozenset({"col_gte", "col_lte", "col_eq", "between", "in_tickers"})
_DOMAIN_OPS = frozenset(
    {
        "signal",
        "regime",
        "signal_compare",
        "regime_mart_allows_entries",
        "regime_allows_entries",
    }
)
_KNOWN_OPS = _CMP_OPS | _BOOL_OPS | _SHORTHAND_OPS | _DOMAIN_OPS | _OPERAND_TYPES
_FORMULA_OPERATORS = frozenset({"+", "-", "*", "/"})

# Populated after the class definition; used to print the known set when rejecting
# an unknown risk parameter.
_RISK_MODEL_PARAM_NAMES: frozenset[str] = frozenset()

# Position flags with dedicated PositionRiskState attributes (kept for backwards
# compatibility with rule sets authored before the ``set_flag`` action existed).
# The generic store is ``state.flags``; these names additionally mirror onto the
# named attribute so older code paths keep working.
_KNOWN_POSITION_FLAGS = frozenset(
    {
        "tranche1_taken",
        "tranche2_taken",
        "tranche3_taken",
        "time_stop_partial_taken",
        "runner_active",
    }
)

# Compatibility shim for legacy rule sets that rely on rule-name → flag wiring:
# a fired rule with one of these names raises the same flags it always did.
# New rules should declare ``{"type": "set_flag", "flag": ...}`` explicitly.
_LEGACY_RULE_FLAGS: dict[str, tuple[str, ...]] = {
    "tranche1": ("tranche1_taken", "runner_active"),
    "tranche2": ("tranche2_taken",),
    "tranche3": ("tranche3_taken",),
    "time_stop_partial": ("time_stop_partial_taken",),
}


def _validate_exit_rules(rules: list | None) -> list[dict]:
    """Validate declarative exit rules; raise on anything that could silently no-op.

    Called at construction so a bad rule fails the backtest immediately instead of
    producing a strategy whose exits never trigger.
    """
    if not rules:
        return []
    if not isinstance(rules, list):
        raise ValueError(f"exit_rules must be a list, got {type(rules).__name__}")
    out: list[dict] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"exit_rules[{idx}] must be a dict, got {type(rule).__name__}")
        name = str(rule.get("name") or f"rule_{idx}")
        when = rule.get("when")
        if not isinstance(when, dict):
            raise ValueError(f"exit_rules[{idx}] ({name}): 'when' must be an AST dict")
        _validate_expr_ops(when, where=f"exit_rules[{idx}] ({name}).when")
        size = float(rule.get("size_pct", 1.0))
        if not 0.0 < size <= 1.0:
            raise ValueError(
                f"exit_rules[{idx}] ({name}): size_pct must be in (0, 1], got {size}"
            )
        out.append(
            {
                "name": name,
                "when": when,
                "size_pct": size,
                "tag": str(rule.get("tag") or name),
            }
        )
    return out


def _validate_expr_ops(node: Any, *, where: str) -> None:
    """Reject unknown node types / formula operators anywhere in an expression tree."""
    if isinstance(node, list):
        for i, sub in enumerate(node):
            _validate_expr_ops(sub, where=f"{where}[{i}]")
        return
    if not isinstance(node, dict):
        return
    ntype = node.get("type")
    if ntype is not None and ntype not in _KNOWN_OPS:
        hint = ""
        if ntype == "ne":
            hint = " — did you mean 'neq'? ('ne' is not implemented and always evaluates False)"
        raise ValueError(f"{where}: unsupported node type {ntype!r}{hint}")
    if ntype == "formula":
        op = node.get("op")
        if op is not None and op not in _FORMULA_OPERATORS:
            raise ValueError(
                f"{where}: unsupported formula operator {op!r}; "
                f"expected one of {sorted(_FORMULA_OPERATORS)}"
            )
    for key in (
        "items",
        "item",
        "left",
        "right",
        "args",
        # C-VERA-EXPR-V2 operand fields: cond(when/then/otherwise),
        # clamp(value/min/max), abs(arg). lit.value is a scalar — the
        # dict guard above makes recursing into it a no-op.
        "when",
        "then",
        "otherwise",
        "arg",
        "value",
        "min",
        "max",
    ):
        if key in node:
            _validate_expr_ops(node[key], where=f"{where}.{key}")



try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect.Algorithm.Framework.Risk import RiskManagementModel
    from QuantConnect.Algorithm.Framework.Portfolio import PortfolioTarget
except ImportError:
    class RiskManagementModel:
        pass

    class PortfolioTarget:
        def __init__(self, symbol, quantity):
            self.Symbol = symbol
            self.Quantity = quantity

        @classmethod
        def Percent(cls, algorithm, symbol, percent):
            class _PT:
                pass
            pt = _PT()
            pt.Symbol = symbol
            pt.Quantity = percent
            pt.Tag = ""
            return pt


class PositionRiskState:
    """Tracks state and profit stages for an individual open position."""

    def __init__(self, symbol, entry_price: float, initial_stop: float, entry_date, atr: float = 0.0):
        self.symbol = symbol
        self.entry_price = entry_price
        self.initial_stop = initial_stop
        self.entry_date = entry_date
        self.r_unit = max(0.01, entry_price - initial_stop)
        self.atr = atr
        self.current_stop = initial_stop
        self.tranche1_taken = False
        self.tranche2_taken = False
        self.tranche3_taken = False
        self.highest_price = entry_price
        self.runner_active = False
        self.time_stop_partial_taken = False
        self.fired_rules: set[str] = set()
        # Generic rule-set flags (the ``set_flag`` action) — each is exposed to
        # rule ``when`` clauses as ``__position.<flag>``.
        self.flags: set[str] = set()


class SwingProgressiveRiskManagementModel(RiskManagementModel):
    """
    Manages progressive multi-tranche exits, R-multiple take-profit scaling,
    Chandelier trailing stops, and portfolio single-position weight caps.
    """

    def __init__(
        self,
        take_profit_r: float = 2.5,
        tranche1_sell_pct: float = 0.20,
        tranche2_r: float = 4.5,
        tranche2_sell_pct: float = 0.33,
        tranche3_r: float = 8.0,
        tranche3_sell_pct: float = 0.33,
        max_single_weight: float = 0.20,
        trailing_stop_pct: float = 0.15,
        trailing_arm_r: float = 3.0,
        breakeven_r_trigger: float = 1.5,
        trailing_ema_period: int = 20,
        max_holding_days: int = 25,
        # v2: ATR-based dynamic stop parameters
        atr_stop_multiplier: float = 2.0,
        max_stop_loss_pct: float = 0.05,
        breakeven_time_stop_days: int = 10,
        use_atr_stops: bool = True,
        store: Any = None,
        # Compiler honesty: exit stage tranches (mapped onto flat tranche_* knobs)
        tranches: list | None = None,
        time_stop_skip_if: dict | None = None,
        risk_skip_time_stop_expr: dict | None = None,
        stop_cooldown_days: int = 10,
        # Legacy compat: new compiles emit policy_overrides on PCM only — the
        # risk-side path below stays live for specs already stored with it.
        policy_overrides: list | None = None,
        surrogate_router: Any = None,
        # Declarative exit rules: [{"name","when":<bool AST>,"size_pct","tag"}]
        exit_rules: list | None = None,
        # Ordered rule-driven control flow (Phase 1 AST). When provided, exit_rules
        # is normalised into this form so new specs carry `rules` directly.
        rules: list | None = None,
        # Position-init stop as an Operand AST (C-VERA-EXPR-V2). Evaluated once at
        # fill against __position.{entry,atr,leverage}; when omitted the default
        # is materialized from the ATR/max-stop knobs so the runtime still executes
        # an expression — the knobs are generation inputs, not live config.
        init_stop: dict | None = None,
        # Which price triggers a stop: "close" (Minervini — avoids intraday
        # shakeouts) or "low" (legacy — catches a same-day breach for next MOO).
        stop_trigger_on: str = "close",
        **_extra: Any,
    ):
        # Normalize legacy hold-days alias so it is not silently swallowed by **_extra.
        if "max_hold_days" in _extra:
            try:
                max_holding_days = int(_extra.pop("max_hold_days"))
            except (TypeError, ValueError):
                _extra.pop("max_hold_days", None)
        # Fail-closed on unknown parameters. Risk-slot Parameters is a free-form
        # dict[str, Any] at the spec layer (no Pydantic model is registered for this
        # Type, so validate_slot_parameters_for_type is a no-op), which means a typo
        # used to be swallowed silently: `exit_rule` instead of `exit_rules`, or
        # `max_stop_loss` instead of `max_stop_loss_pct`, would quietly leave the
        # position UNPROTECTED with no error. For a risk defence that is the worst
        # possible failure mode, so unknown names are rejected here instead.
        if _extra:
            known = sorted(
                p
                for p in _RISK_MODEL_PARAM_NAMES
                if p not in ("self", "_extra")
            )
            raise ValueError(
                "SwingProgressiveRiskManagementModel: unknown parameter(s) "
                f"{sorted(_extra)}. Risk parameters are fail-closed because a typo "
                f"would silently disable the defence. Known parameters: {known}"
            )
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

        self._store = store
        self._take_profit_r = float(take_profit_r)
        self._tranche1_sell_pct = float(tranche1_sell_pct)
        self._tranche2_r = float(tranche2_r)
        self._tranche2_sell_pct = float(tranche2_sell_pct)
        self._tranche3_r = float(tranche3_r)
        self._tranche3_sell_pct = float(tranche3_sell_pct)
        self._max_single_weight = float(max_single_weight)
        self._trailing_stop_pct = float(trailing_stop_pct)
        self._trailing_arm_r = float(trailing_arm_r)
        self._breakeven_r_trigger = float(breakeven_r_trigger)
        self._trailing_ema_period = int(trailing_ema_period)
        self._max_holding_days = int(max_holding_days)
        # v2 ATR stop params
        self._atr_stop_multiplier = float(atr_stop_multiplier)
        self._max_stop_loss_pct = float(max_stop_loss_pct)
        self._breakeven_time_stop_days = int(breakeven_time_stop_days)
        self._use_atr_stops = bool(use_atr_stops)
        self._tranches = list(tranches) if tranches else []
        self._time_stop_skip_if = dict(time_stop_skip_if) if time_stop_skip_if else {}
        self._risk_skip_time_stop_expr = (
            dict(risk_skip_time_stop_expr) if risk_skip_time_stop_expr else None
        )
        self._stop_cooldown_days = int(stop_cooldown_days)
        self._policy_overrides = list(policy_overrides) if policy_overrides else []
        # Declarative exits — validated eagerly so a malformed rule cannot become a
        # silent no-op (see _validate_exit_rules).
        self._exit_rules = _validate_exit_rules(exit_rules)
        if self._exit_rules:
            # Legacy ``exit_rules`` normalize onto the rules path, appended after
            # the generated ladder at priority 100+ so built-ins keep precedence.
            # Full exits keep the old auto-cooldown contract (a thesis-broken name
            # must not re-enter the next session); partial trims never cooled.
            self._normalized_exit_rules = [
                {
                    "name": r["name"],
                    "priority": 100 + i,
                    "once": False,
                    "when": r["when"],
                    "then": (
                        [
                            {"type": "exit", "fraction": r["size_pct"]},
                            {"type": "arm_cooldown", "days": self._stop_cooldown_days},
                        ]
                        if r["size_pct"] >= 0.999
                        else [{"type": "trim", "fraction": r["size_pct"]}]
                    ),
                    "tag": r.get("tag") or r["name"],
                }
                for i, r in enumerate(self._exit_rules)
            ]
        else:
            self._normalized_exit_rules = []
        if rules is None:
            # Generated mode: the complete ladder (protective stops, chandelier,
            # time stops, tranches, cap, breakeven) is materialized as rule ASTs
            # from the ctor knobs — and validated, so a malformed generated rule
            # fails loudly at construction rather than silently no-oping at runtime.
            # There is no procedural fallback in ManageRisk: this list IS the
            # decision table.
            self._rules_from_defaults = True
            self._rules = [
                _r.model_dump()
                for _r in validate_rules(
                    self._normalized_exit_rules + self._default_exit_rules(),
                    slot="RiskManagement(generated)",
                )
            ]
        elif not rules:
            # Explicit empty rule set is fail-closed: a risk model with no rules
            # leaves positions unprotected. Omit 'rules' for the generated ladder,
            # or author at least one rule.
            raise ValueError(
                "SwingProgressiveRiskManagementModel: 'rules' must be a non-empty "
                "list when provided — an empty rule set leaves positions "
                "unprotected. Omit 'rules' to use the generated ladder."
            )
        else:
            # Authored mode: the spec's rules are the whole decision table.
            # Generated-mode params (tranche_*, *_time_stop_days, skip bindings)
            # are inert here — the authored AST is authoritative.
            self._rules_from_defaults = False
            self._rules = [_r.model_dump() for _r in validate_rules(rules, slot="RiskManagement")]
        # Initial stop: authored AST wins; absent → materialize the default from
        # the ATR/max-stop knobs so the computation is an expression either way.
        # The knob path (_compute_initial_stop) survives only as the runtime
        # safety net when expr eval yields no value at fill.
        self._init_stop_authored = init_stop is not None
        self._init_stop_expr = (
            self._validate_init_stop(init_stop)
            if init_stop is not None
            else self._default_init_stop()
        )
        basis = str(stop_trigger_on or "close").strip().lower()
        if basis not in ("close", "low"):
            raise ValueError(
                f"stop_trigger_on must be 'close' or 'low', got {stop_trigger_on!r}"
            )
        self._stop_trigger_on = basis
        if surrogate_router is None:
            try:
                from sigmarail_lab.runtime.surrogate_router import SurrogateRouter
                self._surrogate_router = SurrogateRouter()
            except Exception:
                self._surrogate_router = None
        else:
            self._surrogate_router = surrogate_router

        self._states: dict = {}
        # Last rule evaluation trace (observability): [{rule, matched, ...}] —
        # populated by _evaluate_rules on every call, success or no-match.
        self._last_rule_trace: list[dict] = []
        # ATR indicator cache: symbol -> ATR indicator
        self._atr_indicators: dict = {}
        # One-shot boot log of the materialized rule table (first ManageRisk call).
        self._rules_logged = False
        self.Name = "SwingProgressiveRiskManagementModel"

    def bind_store(self, store: Any) -> None:
        self._store = store

    def _default_exit_rules(self, overrides: dict | None = None) -> list[dict]:
        """Materialize the complete risk ladder via the canonical generator.

        Every post-entry decision is a visible rule — protective stops,
        chandelier trail, time stops, tranches, weight cap, breakeven ratchet —
        so a stored/generated spec fully describes runtime behavior. There is no
        procedural decision code in ``ManageRisk`` underneath this.

        The generator lives in ``sigmarail_lab.ir.risk_ladder`` (single source of
        truth) so ``vera_query_core`` can materialize the identical table into
        ``Parameters.rules`` at compile time — the LEAN container carries
        ``sigmarail_lab`` but never ``vera_query_core``.

        ``overrides`` carries resolved ``policy_overrides`` values (generated
        mode only); authored ``rules`` specs are authoritative and never
        re-materialized.
        """
        return generate_swing_risk_ladder(
            take_profit_r=self._take_profit_r,
            tranche1_sell_pct=self._tranche1_sell_pct,
            tranche2_r=self._tranche2_r,
            tranche2_sell_pct=self._tranche2_sell_pct,
            tranche3_r=self._tranche3_r,
            tranche3_sell_pct=self._tranche3_sell_pct,
            max_single_weight=self._max_single_weight,
            trailing_stop_pct=self._trailing_stop_pct,
            trailing_arm_r=self._trailing_arm_r,
            breakeven_r_trigger=self._breakeven_r_trigger,
            max_holding_days=self._max_holding_days,
            breakeven_time_stop_days=self._breakeven_time_stop_days,
            stop_cooldown_days=self._stop_cooldown_days,
            time_stop_skip_if=self._time_stop_skip_if,
            risk_skip_time_stop_expr=self._risk_skip_time_stop_expr,
            overrides=overrides,
        )

    def _default_init_stop(self, *, atr_stop_multiplier: float | None = None) -> dict:
        """Materialize the initial-stop Operand AST from the resolved knobs."""
        return generate_default_init_stop(
            use_atr_stops=self._use_atr_stops,
            atr_stop_multiplier=(
                self._atr_stop_multiplier
                if atr_stop_multiplier is None
                else float(atr_stop_multiplier)
            ),
            max_stop_loss_pct=self._max_stop_loss_pct,
        )

    @staticmethod
    def _validate_init_stop(expr: dict) -> dict:
        """Eagerly validate an authored init_stop Operand AST (fail closed)."""
        from pydantic import TypeAdapter
        from sigmarail_spec.expr import Operand

        if not isinstance(expr, dict):
            raise ValueError(
                f"init_stop must be an Operand AST dict, got {type(expr).__name__}"
            )
        try:
            node = TypeAdapter(Operand).validate_python(expr)
        except Exception as exc:
            raise ValueError(f"init_stop: invalid Operand AST — {exc}") from exc
        return node.model_dump()

    @staticmethod
    def _set_position_flag(state, pos: dict, flag: str) -> None:
        """Raise a per-position flag: visible to subsequent rules this same bar
        (``pos`` is live) and to later bars (``state.flags`` / legacy attrs)."""
        if state is not None:
            state.flags.add(flag)
            if flag in _KNOWN_POSITION_FLAGS:
                setattr(state, flag, True)
        pos[flag] = True

    def _evaluate_rules(self, algorithm, symbol, position=None, *, row=None, rules=None):
        """Evaluate the ordered rule list and apply each match's actions.

        Terminality derives from the actions themselves
        (``sigmarail_lab.ir.rules.ACTION_TERMINAL``): a matched rule whose ``then``
        contains ``exit``/``trim`` ends the evaluation; rules whose actions are
        all non-terminal (``ratchet_stop``/``cap_weight``/``arm_cooldown``/
        ``set_flag``) apply their effects and evaluation continues to lower
        priorities. That is what lets the chandelier trail co-exist with tranche
        exits in one visible rule set.

        Returns ``(rule, target_weight, tag)`` — for a terminal hit ``rule`` is
        the matched rule; for a bar where only non-terminal rules changed the
        target (e.g. ``cap_weight``), the last matched rule is returned with the
        adjusted weight. ``target_weight`` is ``None`` when nothing changed
        (pure state mutation / no match).
        """
        if row is None:
            try:
                row = self._get_screener_row(algorithm, symbol) or {}
            except Exception:
                row = {}
        # Copy before stamping ``__rule.*.fired`` markers: the store's row objects
        # are shared per-ticker and outlive a position, so markers must not leak
        # back into the store (a stale marker would wrongly suppress once-rules
        # on a re-entered symbol).
        row = dict(row)
        pos = dict(position) if position else {}
        if not row and not pos:
            return None
        rules = self._rules if rules is None else rules
        ticker = getattr(symbol, "Value", symbol)
        try:
            current_weight = 0.0
            holding = None
            try:
                holding = algorithm.Portfolio[symbol]
            except Exception:
                holding = None
            if holding is not None:
                total = float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 0.0) or 0.0)
                hv = float(getattr(holding, "HoldingsValue", 0.0) or 0.0)
                current_weight = (hv / total) if total > 0 else 0.0
            pos["current_weight"] = current_weight
            state = self._states.get(symbol)
            if state is not None:
                for flag in _KNOWN_POSITION_FLAGS:
                    pos.setdefault(flag, getattr(state, flag, False))
                for flag in getattr(state, "flags", ()):
                    pos.setdefault(flag, True)
                pos.setdefault("r_unit", getattr(state, "r_unit", 1.0))
                for fired in getattr(state, "fired_rules", set()):
                    row[f"__rule.{fired}.fired"] = True
            # Wider contexts (read-only): rules may qualify on book state and
            # regime — e.g. "exit early when regime off AND weak". ``acct`` is
            # the computable subset (PCM's slots_remaining/scaled_* are PCM
            # state); ``regime`` mirrors the PCM store getters and is present
            # only when the store supplies it — absent means fail-closed, not
            # silently true.
            contexts: dict[str, dict] = {}
            try:
                total = float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 0.0) or 0.0)
                if total > 0:
                    cash = float(getattr(algorithm.Portfolio, "Cash", 0.0) or 0.0)
                    invested_w = 0.0
                    invested_n = 0
                    for h in getattr(algorithm.Portfolio, "Values", []):
                        if h and getattr(h, "Invested", False):
                            invested_n += 1
                            invested_w += float(getattr(h, "HoldingsValue", 0.0) or 0.0) / total
                    contexts["acct"] = {
                        "portfolio_value": total,
                        "cash_pct": cash / total,
                        "invested_count": float(invested_n),
                        "invested_weight": invested_w,
                        "loss_streak": float(trailing_loss_streak(algorithm)),
                    }
            except Exception:
                pass
            try:
                if self._store is not None:
                    as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
                    regime_bag: dict[str, float] = {}
                    rf = None
                    getter = getattr(self._store, "get_allocation_fraction", None)
                    if callable(getter):
                        rf = getter(as_of)
                    if rf is None:
                        getter = getattr(self._store, "get_regime_weekly_fraction", None)
                        if callable(getter):
                            rf = getter(as_of)
                    if rf is not None:
                        regime_bag["fraction"] = float(rf)
                    on = None
                    getter = getattr(self._store, "allows_new_longs_from_regime_signals", None)
                    if callable(getter):
                        on = getter(as_of)
                    else:
                        spy = getattr(self._store, "get_spy_is_bull", None)
                        if callable(spy):
                            on = spy(as_of)
                    if on is not None:
                        regime_bag["on"] = 1.0 if on else 0.0
                    if regime_bag:
                        contexts["regime"] = regime_bag
            except Exception:
                pass
            trace: list[dict] = []
            target = float(current_weight)
            target_changed = False
            last_hit: tuple[dict, str] | None = None
            sorted_rules = sorted(
                enumerate(rules or []),
                key=lambda x: (x[1].get("priority", 0) if isinstance(x[1], dict) else 0, x[0]),
            )
            for idx, rule in sorted_rules:
                name = rule.get("name", f"rule_{idx}")
                when = rule.get("when", {})
                if rule.get("once", False) and row.get(f"__rule.{name}.fired"):
                    trace.append({"rule": name, "skipped": "once"})
                    continue
                try:
                    matched = evaluate_slot_bool(row, when, position=pos, contexts=contexts)
                except Exception as exc:
                    # Rule eval failures are visible — never a silent skip.
                    matched = False
                    trace.append({"rule": name, "error": str(exc)[:200]})
                    try:
                        algorithm.Debug(f"⚠️ RULE EVAL ERROR [{ticker}] {name}: {exc}")
                    except Exception:
                        pass
                if not matched:
                    trace.append({"rule": name, "matched": False})
                    continue
                terminal = any(
                    ACTION_TERMINAL.get(a.get("type"), False)
                    for a in rule.get("then", [])
                    if isinstance(a, dict)
                )
                for action in rule.get("then", []):
                    atype = action.get("type", "") if isinstance(action, dict) else ""
                    if atype == "exit":
                        frac = action_arg_number(row, action, "fraction", position=pos, contexts=contexts, default=1.0)
                        target = 0.0 if frac is None or frac >= 1.0 else max(0.0, target * (1.0 - frac))
                        target_changed = True
                    elif atype == "trim":
                        frac = action_arg_number(row, action, "fraction", position=pos, contexts=contexts, default=0.0)
                        target = max(0.0, target * (1.0 - (frac or 0.0)))
                        target_changed = True
                    elif atype == "cap_weight":
                        # DEPRECATED action — kept evaluating so stored specs
                        # whose rules still carry max_weight_cap behave the
                        # same. New specs cap concentration in the PCM drift
                        # scan (max_position_weight) instead.
                        to_val = action.get("to")
                        if to_val is not None:
                            cap = evaluate_slot_number(row, to_val, position=pos, contexts=contexts)
                            if cap is not None:
                                capped = min(target, float(cap))
                                target_changed = target_changed or capped != target
                                target = capped
                    elif atype == "ratchet_stop":
                        to_val = action.get("to")
                        mode = str(action.get("mode", "max") or "max")
                        if to_val is not None and state is not None:
                            new_stop = evaluate_slot_number(row, to_val, position=pos, contexts=contexts)
                            if new_stop is not None:
                                if mode == "set":
                                    state.current_stop = float(new_stop)
                                else:
                                    state.current_stop = max(state.current_stop, float(new_stop))
                                # Keep the live position view coherent for the
                                # rest of this bar's rules.
                                pos["current_stop"] = state.current_stop
                    elif atype == "arm_cooldown":
                        days = int(action_arg_number(row, action, "days", position=pos, contexts=contexts, default=0.0) or 0)
                        if days > 0:
                            self._arm_stop_cooldown(algorithm, symbol, days)
                    elif atype == "set_flag":
                        flag = str(action.get("flag") or "")
                        if flag:
                            self._set_position_flag(state, pos, flag)
                # A matched rule is "fired" whether terminal or not — once=true
                # and ``__rule.<name>.fired`` read this marker on later bars.
                if state is not None:
                    state.fired_rules.add(name)
                row[f"__rule.{name}.fired"] = True
                # Legacy name-keyed flags for rule sets authored before set_flag.
                for legacy_flag in _LEGACY_RULE_FLAGS.get(name, ()):
                    self._set_position_flag(state, pos, legacy_flag)
                tag = rule.get("tag") or name
                trace.append(
                    {
                        "rule": name,
                        "matched": True,
                        "terminal": terminal,
                        "priority": rule.get("priority", 0),
                        "target": target,
                        "tag": tag,
                        # What the rule saw — pos + the read-only acct/regime
                        # bags — so a context-qualified firing is auditable.
                        "ctx": {**({"pos": dict(pos)} if pos else {}), **contexts},
                    }
                )
                last_hit = (rule, tag)
                if terminal:
                    self._last_rule_trace = trace
                    return rule, target, tag
            self._last_rule_trace = trace  # publish the why-not trace either way
            if target_changed and last_hit is not None:
                rule, tag = last_hit
                return rule, target, tag
        except Exception as exc:
            self._last_rule_trace = []
            try:
                algorithm.Debug(f"⚠️ RULE ENGINE ERROR [{ticker}]: {exc}")
            except Exception:
                pass
            return None
        return None

    def _arm_stop_cooldown(self, algorithm, symbol, days: int | None = None) -> None:
        """Tell Alpha (via store) not to re-enter until stop_cooldown expires."""
        if self._store is None or not hasattr(self._store, "record_stop_out"):
            return
        try:
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            cooldown_days = int(days or getattr(self, "_stop_cooldown_days", 10) or 10)
            # Prefer Alpha's cooldown if store exposes it; default 10 calendar days.
            until = algorithm.Time.date() + timedelta(days=cooldown_days)
            self._store.record_stop_out(ticker, until)
            if self._surrogate_router is not None:
                underlying = self._surrogate_router.get_underlying_ticker(ticker)
                if underlying and underlying != ticker:
                    self._store.record_stop_out(underlying, until)
        except Exception:
            pass

    def _is_stop_cooled(self, algorithm, symbol) -> bool:
        if self._store is None or not hasattr(self._store, "is_stop_cooled"):
            return False
        try:
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            cooled = bool(self._store.is_stop_cooled(ticker, algorithm.Time.date()))
            if not cooled and self._surrogate_router is not None:
                underlying = self._surrogate_router.get_underlying_ticker(ticker)
                if underlying and underlying != ticker:
                    return bool(self._store.is_stop_cooled(underlying, algorithm.Time.date()))
            return cooled
        except Exception:
            return False

    def _get_screener_row(self, algorithm, symbol) -> dict:
        """Fetch T-1 screener row for symbol, falling back to underlying if symbol is a surrogate."""
        if self._store is None:
            return {}
        try:
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
            getter = getattr(self._store, "get_all_screener_rows", None)
            if not callable(getter):
                return {}
            rows = getter(as_of) or {}
            row = rows.get(ticker)
            if row:
                return row
            if self._surrogate_router is not None:
                underlying = self._surrogate_router.get_underlying_ticker(ticker)
                if underlying:
                    return rows.get(underlying) or {}
        except Exception:
            pass
        return {}



    def _get_atr(self, algorithm, symbol) -> float:
        """Get current ATR for a symbol (precomputed from the store when available)."""
        if not self._use_atr_stops:
            return 0.0
        if self._store is not None:
            atr = self._store_atr(algorithm, symbol)
            if atr and atr > 0:
                return atr
        # Surrogate fallback: scale underlying ATR if available
        if self._surrogate_router is not None and self._store is not None:
            try:
                ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
                underlying = self._surrogate_router.get_underlying_ticker(ticker)
                if underlying and underlying != ticker:
                    as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
                    atr_pct = self._store.get_atrs(as_of).get(underlying)
                    if atr_pct:
                        leverage = float(self._surrogate_router.get_leverage(ticker))
                        holding = algorithm.Portfolio[symbol] if symbol in algorithm.Portfolio else None
                        px = float(getattr(holding, "Price", 0.0) or getattr(holding, "AveragePrice", 0.0) or 0.0)
                        if px > 0:
                            return px * (float(atr_pct) * leverage / 100.0)
            except Exception:
                pass
        # Fallback: live ATR indicator (no store, e.g. pure-Lean wiring).
        try:
            if symbol not in self._atr_indicators:
                atr_ind = algorithm.ATR(symbol, 14, MovingAverageType.Simple)
                self._atr_indicators[symbol] = atr_ind
            atr_ind = self._atr_indicators[symbol]
            if atr_ind.IsReady:
                return float(atr_ind.Current.Value)
        except Exception:
            pass
        return 0.0

    def _store_atr(self, algorithm, symbol) -> float:
        """Absolute ATR(14) from L7 ``atr_14_pct`` (percent of close).

        ``abs_atr = close * atr_14_pct / 100``. Reads T-1 screener slice.
        """
        try:
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
            atr_pct = self._store.get_atrs(as_of).get(ticker)
            close = self._store.get_ticker_close(ticker, as_of)
            if atr_pct and close:
                return float(close) * (float(atr_pct) / 100.0)
        except Exception:
            pass
        return 0.0

    def _compute_initial_stop(
        self,
        entry_price: float,
        atr: float,
        *,
        atr_mult: float | None = None,
        leverage_factor: float = 1.0,
    ) -> float:
        """Compute ATR-based or fixed stop loss, scaled by leverage_factor."""
        mult = float(self._atr_stop_multiplier if atr_mult is None else atr_mult)
        lev = max(1.0, float(leverage_factor or 1.0))
        effective_max_stop = min(0.35, self._max_stop_loss_pct * lev)
        if self._use_atr_stops and atr > 0:
            atr_stop = entry_price - (mult * atr)
            floor_stop = entry_price * (1.0 - effective_max_stop)
            return max(atr_stop, floor_stop)
        # Fallback: fixed percentage stop
        return entry_price * (1.0 - effective_max_stop)

    @staticmethod
    def _tagged_percent(algorithm, symbol, percent: float, tag: str):
        """PortfolioTarget.Percent with Studio-visible order tag."""
        target = PortfolioTarget.Percent(algorithm, symbol, percent)
        try:
            target.Tag = str(tag)
        except Exception:
            pass
        tags = getattr(algorithm, "_vera_order_tags", None)
        if not isinstance(tags, dict):
            tags = {}
            algorithm._vera_order_tags = tags
        ticker = str(getattr(symbol, "Value", symbol))
        tags[ticker] = str(tag)
        return target

    def ManageRisk(self, algorithm, targets):
        # Boot log: emit the exact rule table once so every run's log proves which
        # decision set was active (generated ladder vs authored rules).
        if not self._rules_logged:
            self._rules_logged = True
            try:
                names = ", ".join(
                    f"{r.get('name')}@{r.get('priority', 0)}" for r in (self._rules or [])
                )
                mode = "generated" if self._rules_from_defaults else "authored"
                init_mode = "authored" if self._init_stop_authored else "generated"
                algorithm.Debug(f"🧾 RISK RULES ({mode}, init_stop={init_mode}): {names}")
            except Exception:
                pass
        risk_targets = []
        today = algorithm.Time.date()
        total_portfolio_val = float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 100000.0) or 100000.0)

        for symbol, holding in getattr(algorithm.Portfolio, "items", lambda: [])():
            if not holding or not getattr(holding, "Invested", False):
                self._states.pop(symbol, None)
                continue

            current_px = float(getattr(holding, "Price", 0.0) or 0.0)
            avg_px = float(getattr(holding, "AveragePrice", 0.0) or current_px)
            holdings_val = float(getattr(holding, "HoldingsValue", 0.0) or 0.0)
            if current_px <= 0 or avg_px <= 0:
                continue

            # Initialize state for every invested symbol. Stop-cooldown must NOT
            # skip protective exits — if cooled while still invested, keep forcing flat
            # until the MOO/MOC liquidation fills (avoids ghost re-init loops).
            if symbol not in self._states:
                if self._is_stop_cooled(algorithm, symbol):
                    algorithm.Debug(
                        f"🛑 PENDING FLATTEN [{symbol.Value}]: still invested while stop-cooled "
                        f"→ forcing flat (tag=hard_stop)"
                    )
                    risk_targets.append(self._tagged_percent(algorithm, symbol, 0.0, "hard_stop"))
                    continue
                atr = self._get_atr(algorithm, symbol)
                atr_mult = self._atr_stop_multiplier
                ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
                leverage = 1.0
                if self._surrogate_router is not None:
                    leverage = float(self._surrogate_router.get_leverage(ticker))
                row: dict = {}
                if self._init_stop_authored and not self._policy_overrides:
                    # Authored exprs may reference screener columns — give them
                    # the same T-1 row context rules get.
                    row = self._get_screener_row(algorithm, symbol) or {}
                if self._policy_overrides and self._store is not None:
                    try:
                        ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
                        as_of = (today - timedelta(days=1)).isoformat()
                        getter = getattr(self._store, "get_all_screener_rows", None)
                        row = getter(as_of).get(ticker) if callable(getter) else {}
                        if not row and self._surrogate_router is not None:
                            und = self._surrogate_router.get_underlying_ticker(ticker)
                            if und:
                                row = getter(as_of).get(und) if callable(getter) else {}
                        ov = resolve_policy_overrides(
                            self._policy_overrides, row or {}, consumer="risk"
                        )
                        if "atr_stop_multiplier" in ov:
                            atr_mult = float(ov["atr_stop_multiplier"])
                    except Exception:
                        pass
                # Initial stop is an AST eval (C-VERA-EXPR-V2): authored
                # Parameters.init_stop wins; absent → the ctor materialized the
                # default from knobs. In generated mode, a policy_overrides
                # atr_stop_multiplier re-materializes the expr so the override
                # still reaches the computation (authored exprs are authoritative
                # and never re-materialized).
                init_expr = self._init_stop_expr
                if not self._init_stop_authored and atr_mult != self._atr_stop_multiplier:
                    init_expr = self._default_init_stop(atr_stop_multiplier=atr_mult)
                initial_stop = None
                if init_expr:
                    try:
                        initial_stop = evaluate_slot_number(
                            row,
                            init_expr,
                            position={
                                "entry": avg_px,
                                "atr": atr,
                                "leverage": leverage,
                            },
                        )
                    except Exception as exc:
                        algorithm.Debug(
                            f"⚠️ INIT STOP EVAL ERROR [{ticker}]: {exc} → knob fallback"
                        )
                        initial_stop = None
                if initial_stop is None or not (0.0 < float(initial_stop) < avg_px):
                    # Fail-SAFE (not closed): a spec bug must never leave a
                    # position unprotected — fall back to the knob computation.
                    if init_expr:
                        algorithm.Debug(
                            f"⚠️ INIT STOP [{ticker}]: expr → {initial_stop!r} "
                            f"(entry={avg_px:.2f}) → knob fallback"
                        )
                    initial_stop = self._compute_initial_stop(
                        avg_px, atr, atr_mult=atr_mult, leverage_factor=leverage
                    )
                self._states[symbol] = PositionRiskState(
                    symbol=symbol,
                    entry_price=avg_px,
                    initial_stop=initial_stop,
                    entry_date=today,
                    atr=atr,
                )
                algorithm.Debug(
                    f"📍 NEW POSITION [{symbol.Value}]: Entry=${avg_px:.2f} "
                    f"ATR={atr:.2f} Stop=${initial_stop:.2f} "
                    f"({(avg_px - initial_stop) / avg_px:.1%} away, lev={leverage}x) "
                    f"R=${avg_px - initial_stop:.2f}"
                )

            state = self._states[symbol]
            state.highest_price = max(state.highest_price, current_px)

            # NOTE (2026-10-05): a "pyramid-add stop floor" lived here. It raised
            # current_stop to max_stop_loss_pct below each add price so an added lot
            # could not run past the configured stop distance. It was measured on the
            # 2019-01-01..2026-10-02 window and REVERTED: on the gated universe it cost
            # ~20pp (26.64% -> 6.30%) because it tightened onto adds and shook out
            # winners (IPHI: floored to $58.85, stopped at +11.3%, then ran to +6.2R
            # on 2019-10-30). Neither Minervini nor Weinstein moves a stop because you
            # added; they bound the add by SIZING against the existing stop.
            # If revisited: size the add (shares = risk / (add_px - current_stop))
            # rather than moving the stop.

            gain = current_px - state.entry_price
            r_multiple = gain / state.r_unit if state.r_unit > 0 else 0.0
            held_days = (today - state.entry_date).days

            current_weight = holdings_val / total_portfolio_val if total_portfolio_val > 0 else 0.0

            # Stop trigger basis.
            #   "close" (default) — Minervini judges stops on the CLOSE precisely to
            #     avoid being shaken out by intraday noise. IPHI 2019-08-28 is the
            #     worked example: intraday low $58.78 tagged every level, but it closed
            #     $60.17, and the position went on to +6.2R. The intraday low is still
            #     read, but only to log an early warning.
            #   "low" (legacy) — catch a same-day breach for the next MOO fill.
            check_px = current_px
            session_low = 0.0
            try:
                securities = getattr(algorithm, "Securities", None)
                sec = securities[symbol] if securities is not None and symbol in securities else None
                session_low = float(getattr(sec, "Low", 0.0) or 0.0) if sec is not None else 0.0
            except Exception:
                session_low = 0.0
            if self._stop_trigger_on == "low":
                if session_low > 0:
                    check_px = min(current_px, session_low)
            elif session_low > 0 and session_low <= state.current_stop < current_px:
                algorithm.Debug(
                    f"⚠️ INTRADAY BREACH [{symbol.Value}]: low=${session_low:.2f} < "
                    f"Stop=${state.current_stop:.2f} but close=${current_px:.2f} held "
                    f"(close-based trigger, Minervini)"
                )

            # ---- Decision layer -------------------------------------------------
            # The rule AST is the sole post-init decision source. Generated specs
            # carry the full ladder (protective stops, chandelier, time stops,
            # tranches, cap, breakeven); authored rules replace it wholesale.
            # There is no procedural fallback: a position that matches no rule
            # simply holds.
            row = self._get_screener_row(algorithm, symbol)

            # policy_overrides may re-materialize the *generated* ladder per
            # holding so row-scoped thresholds (e.g. per-regime trail %) stay
            # live. Authored rules are authoritative and never re-materialized.
            rules = self._rules
            if self._rules_from_defaults and self._policy_overrides:
                try:
                    ov = resolve_policy_overrides(
                        self._policy_overrides, row or {}, consumer="risk"
                    )
                    if ov:
                        rules = list(self._normalized_exit_rules) + self._default_exit_rules(ov)
                except Exception:
                    rules = self._rules

            hit = self._evaluate_rules(
                algorithm,
                symbol,
                position={
                    "price": current_px,
                    "entry": state.entry_price,
                    "r": r_multiple,
                    "days_held": held_days,
                    "low": session_low,
                    "check_price": check_px,
                    "current_stop": state.current_stop,
                    "initial_stop": state.initial_stop,
                    "highest_price": state.highest_price,
                    "r_unit": state.r_unit,
                    "stop_cooled": self._is_stop_cooled(algorithm, symbol),
                },
                row=row,
                rules=rules,
            )
            if hit is not None:
                rule, exit_weight, tag = hit
                if exit_weight is not None and exit_weight <= 1e-9:
                    algorithm.Debug(
                        f"🚪 EXIT RULE [{symbol.Value}]: {rule.get('name')} "
                        f"(tag={tag}) → full exit "
                        f"(R={r_multiple:+.1f}R, Held={held_days}d)"
                    )
                    risk_targets.append(
                        self._tagged_percent(algorithm, symbol, 0.0, tag)
                    )
                    self._states.pop(symbol, None)
                elif exit_weight is not None:
                    algorithm.Debug(
                        f"🚪 RULE [{symbol.Value}]: {rule.get('name')} "
                        f"(tag={tag}) → target {exit_weight:.1%} "
                        f"(R={r_multiple:+.1f}R, Held={held_days}d)"
                    )
                    risk_targets.append(
                        self._tagged_percent(algorithm, symbol, exit_weight, tag)
                    )

        return risk_targets


# Resolve the accepted parameter names once, from the live signature, so the
# fail-closed error message cannot drift from the actual constructor.
import inspect as _inspect  # noqa: E402

_RISK_MODEL_PARAM_NAMES = frozenset(
    p for p in _inspect.signature(SwingProgressiveRiskManagementModel.__init__).parameters
)
