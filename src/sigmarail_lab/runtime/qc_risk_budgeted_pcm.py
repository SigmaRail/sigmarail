"""
Risk-Budgeted Portfolio Construction Model for Systematic Swing Trading.

Implements Standard Fixed Fractional Risk Sizing:
- Calculates dollar risk per trade = Total Portfolio Value * risk_per_trade_pct (e.g. 1.0%).
- Sizes shares strictly based on the distance between Entry and Tactical Stop Loss (R).
- Enforces an absolute maximum position size cap (e.g. 15% of portfolio).
- Respects maximum concurrent position count and cash buffer constraints.
- Owns progressive scale-in (phases / add_trigger_pct): starter vs add from Invested.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sigmarail_lab.ir.pcm_ladder import (
    generate_default_size_expr,
    generate_order_expr,
    generate_pcm_ladder,
    generate_scale_expr,
    generate_slots_expr,
)
from sigmarail_lab.ir.rules import ACTION_TERMINAL, validate_phases, validate_rules
from sigmarail_lab.runtime.pyramid_position_state import PyramidPositionState
from sigmarail_lab.runtime.signal_evaluation import evaluate_slot_bool, evaluate_slot_number
from sigmarail_lab.runtime._acct_stats import trailing_loss_streak
from sigmarail_lab.runtime.action_args import action_arg_number
from sigmarail_lab.runtime.policy_overrides import resolve_policy_overrides

try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget
except ImportError:
    class PortfolioConstructionModel:
        pass

    class InsightDirection:
        Up = 1
        Down = -1
        Flat = 0

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


class RiskBudgetedPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Sizes positions based on risk budget per trade and stop-loss distance,
    with dynamic Graduated Market Regime Exposure scaling and Leader Exemption support.

    Progressive scale-in (phases / add_trigger) lives here — Alpha only emits Ups.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_position_weight: float = 0.15,
        max_positions: int = 8,
        default_stop_loss_pct: float = 0.05,
        # Accepted for stored-spec compatibility; unread at runtime — the
        # rebalance cadence is driven by the caller's insight flow, and the
        # regime fractions come straight from the store's allocation ladder.
        rebalance_period_days: int = 1,
        use_regime_scaling: bool = True,
        min_regime_fraction: float = 0.15,
        regime_neutral_fraction: float = 0.5,
        regime_bull_fraction: float = 1.0,
        honor_insight_confidence: bool = False,
        allow_adds_on_invested: bool = False,
        scaled_max_positions_floor: int = 2,
        pcm_scale_expr: dict | None = None,
        pcm_allow_entry_expr: dict | None = None,
        risk_allow_pyramid_add_expr: dict | None = None,
        policy_overrides: list | None = None,
        phases: list[dict[str, Any]] | None = None,
        add_trigger_pct: float = 0.02,
        uses: list[str] | None = None,
        max_entry_atr_pct: float = 3.5,
        enable_displacement: bool = False,
        displacement_min_hold_days: int = 18,
        displacement_max_incumbent_r: float = 0.1,
        displacement_min_challenger_rs: float = 92.0,
        displacement_min_challenger_screens: int = 1,
        displacement_immune_rs: float = 85.0,
        displacement_cooldown_days: int = 14,
        enable_surrogates: bool = False,
        surrogate_router: Any = None,
        surrogate_sizing_mode: str = "dollar_risk_parity",
        prefer_capital_efficient_surrogates: bool = True,  # dead: legacy Debug log only
        min_surrogate_adv: float = 1_000_000,
        # Cash-gate cushion: each emitted target reserves weight*(1+buffer) of
        # book fraction so orders filled at drifted prices (daily bars fill at
        # the close after the 09:00 decision pass) still clear LEAN's margin
        # check. The momentum cohort drifts correlated within a batch, so the
        # buffer applies per-reservation, not once.
        cash_reserve_buffer: float = 0.05,
        # Ordered rule-driven allocation (C-FW-RULES Phase 2): when provided,
        # the rules ARE the decision table — every gate, the displacement
        # challenger criteria, the pyramid add, the drift cap, the entry.
        # None → the ladder is generated from the ctor knobs; [] → fail-closed.
        rules: list | None = None,
        # Sizing Operand AST (C-VERA-EXPR-V2) — the full-position target weight
        # the `enter`/`add` actions scale. None → generated from the knobs.
        size_expr: dict | None = None,
        # Book-level Operand ASTs (C-FW-RULES Phase 3) — evaluated once per
        # pass so book policy is data too:
        #   scale_expr → regime.scale   (contexts: regime raw + acct)
        #   slots_expr → acct.scaled_max_positions (same + regime.scale)
        #   order_expr → unit sort key   (light cand/hold + acct + regime)
        # None → generated defaults reproducing the legacy math; authored ASTs
        # are authoritative.
        scale_expr: dict | None = None,
        slots_expr: dict | None = None,
        order_expr: dict | None = None,
        store: Any = None,
        **_extra: Any,
    ):
        self._risk_per_trade_pct = float(risk_per_trade_pct)
        self._max_position_weight = float(max_position_weight)
        self._max_positions = max(1, int(max_positions))
        self._default_stop_loss_pct = float(default_stop_loss_pct)
        self._use_regime_scaling = bool(use_regime_scaling)
        self._min_regime_fraction = float(min_regime_fraction)
        self._pcm_scale_expr = dict(pcm_scale_expr) if pcm_scale_expr else None
        # XOR: pcm_scale_expr present → ignore insight confidence scaling.
        self._honor_insight_confidence = (
            False if self._pcm_scale_expr else bool(honor_insight_confidence)
        )
        self._pcm_allow_entry_expr = dict(pcm_allow_entry_expr) if pcm_allow_entry_expr else None
        self._risk_allow_pyramid_add_expr = (
            dict(risk_allow_pyramid_add_expr) if risk_allow_pyramid_add_expr else None
        )
        self._policy_overrides = list(policy_overrides) if policy_overrides else []
        self._allow_adds_on_invested = bool(allow_adds_on_invested)
        self._scaled_max_positions_floor = int(scaled_max_positions_floor)
        self._phases = validate_phases(phases) or [
            {"name": "test", "size_pct": 0.50},
            {"name": "add", "size_pct": 0.25},
            {"name": "full", "size_pct": 0.25},
        ]
        self._add_trigger_pct = float(add_trigger_pct)
        self._uses = {str(u) for u in (uses or [])}
        self._cash_reserve_buffer = float(cash_reserve_buffer)
        self._max_entry_atr_pct = float(max_entry_atr_pct)
        self._enable_displacement = bool(enable_displacement)
        self._displacement_min_hold_days = int(displacement_min_hold_days)
        self._displacement_max_incumbent_r = float(displacement_max_incumbent_r)
        self._displacement_min_challenger_rs = float(displacement_min_challenger_rs)
        self._displacement_min_challenger_screens = int(displacement_min_challenger_screens)
        self._displacement_immune_rs = float(displacement_immune_rs)
        self._displacement_cooldown_days = int(displacement_cooldown_days)
        self._enable_surrogates = bool(enable_surrogates)
        self._surrogate_sizing_mode = str(surrogate_sizing_mode)
        self._min_surrogate_adv = float(min_surrogate_adv)
        if self._enable_surrogates and surrogate_router is None:
            try:
                from sigmarail_lab.runtime.surrogate_router import SurrogateRouter
                self._surrogate_router = SurrogateRouter(
                    enable_surrogates=True, min_surrogate_adv=self._min_surrogate_adv
                )
            except Exception:
                self._surrogate_router = None
        else:
            self._surrogate_router = surrogate_router
        self._store = store
        self._last_effective_scale = 1.0
        self._pyramid_states: dict[str, PyramidPositionState] = {}
        self._last_known_rs: dict[str, float] = {}
        self._displacement_cooldown: dict[str, Any] = {}
        self._pcm_rule_fired: dict[str, set[str]] = {}
        self._pcm_flags: dict[str, set[str]] = {}
        # Rules contract (mirrors qc_swing_risk): None → generated ladder;
        # non-empty list → authored & authoritative; [] → fail-closed.
        if rules is None:
            self._rules_from_defaults = True
            self._rules = [
                _r.model_dump()
                for _r in validate_rules(
                    self._generated_ladder(),
                    slot="PortfolioConstruction(generated)",
                )
            ]
        elif not rules:
            raise ValueError(
                "RiskBudgetedPortfolioConstructionModel: 'rules' must be a "
                "non-empty list when provided — an empty table allocates "
                "nothing. Omit 'rules' to use the generated ladder."
            )
        else:
            self._rules_from_defaults = False
            self._rules = [
                _r.model_dump()
                for _r in validate_rules(rules, slot="PortfolioConstruction")
            ]
        self._size_expr_authored = size_expr is not None
        self._size_expr = dict(size_expr) if size_expr is not None else self._generated_size_expr()
        # Book-level ASTs — same contract: authored wins, absent → generated.
        self._scale_expr = (
            dict(scale_expr)
            if scale_expr is not None
            else generate_scale_expr(
                use_regime_scaling=self._use_regime_scaling,
                min_regime_fraction=self._min_regime_fraction,
            )
        )
        self._slots_expr = (
            dict(slots_expr)
            if slots_expr is not None
            else generate_slots_expr(
                use_regime_scaling=self._use_regime_scaling,
                scaled_max_positions_floor=self._scaled_max_positions_floor,
                max_positions=self._max_positions,
            )
        )
        self._order_expr = dict(order_expr) if order_expr is not None else generate_order_expr()
        self.Name = "RiskBudgetedPortfolioConstructionModel"

    def _generated_ladder(self, overrides: dict | None = None) -> list[dict]:
        ov = overrides or {}
        return generate_pcm_ladder(
            max_position_weight=float(
                ov.get("max_position_weight", self._max_position_weight)
            ),
            allow_adds_on_invested=self._allow_adds_on_invested,
            use_regime_scaling=self._use_regime_scaling,
            uses=sorted(self._uses),
            phases=self._phases,
            add_trigger_pct=self._add_trigger_pct,
            max_entry_atr_pct=self._max_entry_atr_pct,
            enable_displacement=self._enable_displacement,
            displacement_min_hold_days=self._displacement_min_hold_days,
            displacement_max_incumbent_r=self._displacement_max_incumbent_r,
            displacement_min_challenger_rs=self._displacement_min_challenger_rs,
            displacement_min_challenger_screens=self._displacement_min_challenger_screens,
            displacement_immune_rs=self._displacement_immune_rs,
            displacement_cooldown_days=self._displacement_cooldown_days,
            pcm_allow_entry_expr=self._pcm_allow_entry_expr,
            risk_allow_pyramid_add_expr=self._risk_allow_pyramid_add_expr,
        )

    def _generated_size_expr(self, overrides: dict | None = None) -> dict:
        ov = overrides or {}
        return generate_default_size_expr(
            risk_per_trade_pct=float(
                ov.get("risk_per_trade_pct", self._risk_per_trade_pct)
            ),
            max_position_weight=float(
                ov.get("max_position_weight", self._max_position_weight)
            ),
            honor_insight_confidence=self._honor_insight_confidence,
            pcm_scale_expr=self._pcm_scale_expr,
        )

    # ------------------------------------------------------------------
    # Rule-driven allocation engine (C-FW-RULES Phase 2)
    #
    # One unified pass per rebalance: Alpha insights (rank order preserved)
    # followed by insight-quiet holdings form the decision units. Each unit's
    # rules evaluate with contexts {cand, hold, acct, pyr, regime} + the T-1
    # screener row; `acct.slots_remaining` is shared mutable state — `enter`
    # decrements it, `displace` increments it — so evaluation order IS the
    # allocation order, exactly the sequential-greedy semantics the procedural
    # version used.
    # ------------------------------------------------------------------

    def _store_row(self, ticker: str, as_of: str) -> dict:
        if self._store is None:
            return {}
        getter = getattr(self._store, "get_all_screener_rows", None)
        row = getter(as_of).get(ticker) if callable(getter) else None
        if row and row.get("rs_rating") is not None:
            try:
                self._last_known_rs[ticker] = float(row["rs_rating"])
            except (TypeError, ValueError):
                pass
        return row or {}

    def _confirm_price(self, ticker: str, lean_px: float, as_of: str) -> float:
        if self._store is not None:
            getter = getattr(self._store, "get_ticker_close", None)
            if callable(getter):
                store_px = getter(ticker, as_of)
                if store_px:
                    try:
                        return float(store_px)
                    except (TypeError, ValueError):
                        pass
        return lean_px

    @staticmethod
    def _sec(algorithm, sym):
        securities = getattr(algorithm, "Securities", None)
        if securities is None:
            return None
        val = str(getattr(sym, "Value", sym))
        getter = getattr(securities, "get", None)
        if callable(getter):
            res = getter(sym) or getter(val)
            if res is not None:
                return res
        for k in (sym, val):
            try:
                if hasattr(securities, "ContainsKey") and securities.ContainsKey(k):
                    return securities[k]
                if k in securities:
                    return securities[k]
            except TypeError:
                pass
        return None

    def _build_cand(self, algorithm, insight, row, today, as_of):
        """Resolve an insight into the ``cand`` binding dict + trade routing.

        Returns ``(cand, trade_symbol, leverage)`` — the surrogate resolution
        and stop-distance math are plumbing the rules read, not decide.
        """
        direction = getattr(insight, "Direction", None)
        symbol = insight.Symbol
        ticker = str(getattr(symbol, "Value", symbol))
        # Bindings are total — every field exists zero-filled so ``eq(x, 0)``
        # works (a missing ref evaluates to None, which fails every comparison).
        cand: dict[str, Any] = {
            "has_insight": 1.0,
            "is_down": 1.0 if direction == InsightDirection.Down else 0.0,
            "is_new": 0.0,
            "is_add": 0.0,
            "cooldown_active": 0.0,
            "leader_exempt": 0.0,
            "confidence": 0.0,
            "weight": 0.0,
            "rs": 0.0,
            "leverage": 1.0,
            "eff_leverage": 1.0,
            "price": 0.0,
            "confirm_price": 0.0,
            "stop_price": 0.0,
            "stop_distance_frac": float(self._default_stop_loss_pct),
        }
        trade_symbol = symbol
        leverage = 1.0
        if direction != InsightDirection.Up:
            return cand, trade_symbol, leverage

        invested = ticker in self._invested_tickers
        if not invested:
            # Fallback: the invested set comes from Portfolio.Values — some
            # holders only resolve through the keyed lookup.
            try:
                invested = bool(
                    symbol in algorithm.Portfolio
                    and getattr(algorithm.Portfolio[symbol], "Invested", False)
                )
            except Exception:
                invested = False
        cand["is_new" if not invested else "is_add"] = 1.0
        cand["cooldown_active"] = 1.0 if (
            (cd := self._displacement_cooldown.get(ticker)) is not None and today < cd
        ) else 0.0
        cand["leader_exempt"] = 1.0 if getattr(insight, "IsLeaderExemption", False) else 0.0
        cand["confidence"] = float(getattr(insight, "Confidence", None) or 1.0)
        raw_w = getattr(insight, "Weight", None)
        cand["weight"] = float(raw_w) if isinstance(raw_w, (int, float)) and not isinstance(raw_w, bool) else 0.0
        cand["rs"] = float(
            row.get("rs_rating") or self._last_known_rs.get(ticker, 0.0) or 0.0
        )

        if self._enable_surrogates and self._surrogate_router:
            trade_symbol, leverage = self._surrogate_router.resolve_trade_symbol(
                algorithm, symbol, as_of=today
            )
        cand["leverage"] = float(leverage)
        cand["eff_leverage"] = (
            float(leverage)
            if self._surrogate_sizing_mode == "dollar_risk_parity" and leverage > 1.0
            else 1.0
        )

        sec = self._sec(algorithm, trade_symbol)
        lean_px = float(getattr(sec, "Price", 0.0) or 0.0) if sec else 0.0
        stock_sec = self._sec(algorithm, symbol)
        stock_px = float(getattr(stock_sec, "Price", 0.0) or 0.0) if stock_sec else lean_px
        current_px = lean_px or float(row.get("close") or 0.0)
        cand["price"] = float(current_px)
        cand["confirm_price"] = self._confirm_price(ticker, current_px, as_of)

        raw_stop = getattr(insight, "StopLossPrice", None)
        try:
            stop_price = float(raw_stop) if raw_stop is not None else 0.0
        except (TypeError, ValueError):
            stop_price = 0.0
        if stop_price <= 0 or stop_price >= current_px:
            stop_price = current_px * (1.0 - self._default_stop_loss_pct)
        cand["stop_price"] = float(stop_price)
        if stock_px > 0 and 0 < stop_price < stock_px:
            cand["stop_distance_frac"] = (stock_px - stop_price) / stock_px
        else:
            cand["stop_distance_frac"] = self._default_stop_loss_pct
        return cand, trade_symbol, leverage

    def _build_hold(self, algorithm, symbol, ticker, row, portfolio_value, today):
        """The ``hold`` binding dict — populated only when the unit's symbol is held."""
        holding = None
        for h in getattr(algorithm.Portfolio, "Values", []):
            if h and getattr(h, "Invested", False):
                sym = getattr(h, "Symbol", None)
                if str(getattr(sym, "Value", sym)) == ticker:
                    holding = h
                    break
        if holding is None:
            try:
                h = algorithm.Portfolio[symbol]
                if getattr(h, "Invested", False):
                    holding = h
            except Exception:
                holding = None
        if not holding or not getattr(holding, "Invested", False):
            return {"invested": 0.0}
        avg_cost = float(getattr(holding, "AveragePrice", 0.0) or 0.0)
        h_px = float(getattr(holding, "Price", 0.0) or 0.0)
        h_state = self._pyramid_states.get(ticker)
        h_days = (today - h_state.entry_date).days if (h_state and h_state.entry_date) else 0
        risk_per_share = avg_cost * self._default_stop_loss_pct
        open_r = (h_px - avg_cost) / risk_per_share if (risk_per_share > 0 and avg_cost > 0) else 0.0
        h_rs = 0.0
        if row and row.get("rs_rating") is not None:
            try:
                h_rs = float(row["rs_rating"])
            except (TypeError, ValueError):
                pass
        if h_rs <= 0.0:
            h_rs = self._last_known_rs.get(ticker, 0.0)
        if h_rs <= 0.0 and h_state and getattr(h_state, "entry_rs", 0.0):
            h_rs = float(h_state.entry_rs or 0.0)
        hold = {
            "invested": 1.0,
            "weight": float(getattr(holding, "HoldingsValue", 0.0) or 0.0) / portfolio_value
            if portfolio_value > 0 else 0.0,
            "entry": avg_cost,
            "price": h_px,
            "days_held": float(h_days),
            "open_r": float(open_r),
            "rs": h_rs,
        }
        for flag in self._pcm_flags.get(ticker, ()):
            hold[flag] = 1.0
        return hold

    def _build_pyr(self, ticker) -> dict:
        """The ``pyr`` binding dict — phase geometry for the unit's symbol."""
        n = len(self._phases)
        state = self._pyramid_states.get(ticker)
        phase_index = state.phase_index if state is not None else 0
        entry_frac = float(self._phases[0].get("size_pct", 0.0)) if n else 0.0
        # add_frac = cumulative fraction AFTER the next advance (0 when exhausted)
        if state is None or phase_index >= n - 1:
            add_frac = 0.0
        else:
            end = phase_index + 2
            add_frac = min(
                1.0,
                sum(
                    float(self._phases[i].get("size_pct", 0.0) or 0.0)
                    for i in range(min(end, n))
                ),
            )
        return {
            "phase_index": float(phase_index if state is not None else -1),
            "phases_remaining": float(max(0, n - 1 - phase_index)),
            "entry_frac": entry_frac,
            "add_frac": add_frac,
            "entry_price": float(state.entry_price or 0.0) if state else 0.0,
            "add_trigger_pct": float(self._add_trigger_pct),
        }

    def _emit_weight(self, algorithm, symbol, weight: float, tag: str, ticker: str, targets):
        """Emit a weight target (Percent when priced; qty fallback)."""
        if weight <= 1e-9:
            weight = 0.0
        sec = self._sec(algorithm, symbol)
        px = float(getattr(sec, "Price", 0.0) or 0.0) if sec else 0.0
        if px > 0:
            pt = PortfolioTarget.Percent(algorithm, symbol, weight)
        else:
            pv = float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 0.0) or 0.0)
            qty = int(weight * pv / 1.0) if weight > 0 else 0
            pt = PortfolioTarget(symbol, qty)
        try:
            pt.Tag = tag
        except Exception:
            pass
        tags = getattr(algorithm, "_vera_order_tags", None)
        if not isinstance(tags, dict):
            tags = {}
            algorithm._vera_order_tags = tags
        tags[ticker] = tag
        targets.append(pt)

    def CreateTargets(self, algorithm, insights):
        targets = []
        portfolio_value = float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 0.0) or 100000.0)
        if portfolio_value <= 0:
            return targets

        today = algorithm.Time.date()
        as_of = (today - timedelta(days=1)).isoformat()

        # Regime inputs — raw fraction + score flag (data fetch, not policy).
        regime_fraction = 1.0
        if self._use_regime_scaling and self._store:
            rf = None
            getter = getattr(self._store, "get_allocation_fraction", None)
            if callable(getter):
                rf = getter(as_of)
            if rf is None:
                rf = self._store.get_regime_weekly_fraction(as_of)
            if rf is not None:
                regime_fraction = float(rf)
        regime_on = True
        if self._store is not None:
            getter = getattr(self._store, "allows_new_longs_from_regime_signals", None)
            if callable(getter):
                regime_on = bool(getter(as_of))
            else:
                spy = getattr(self._store, "get_spy_is_bull", None)
                if callable(spy):
                    regime_on = bool(spy(as_of))

        # Book state — invested set includes surrogate underlyings so adds and
        # incumbency checks see through the router.
        current_invested = 0
        invested_weight = 0.0
        self._invested_tickers: set[str] = set()
        self._invested_symbols: dict[str, Any] = {}
        for holding in getattr(algorithm.Portfolio, "Values", []):
            if not holding or not getattr(holding, "Invested", False):
                continue
            current_invested += 1
            sym = getattr(holding, "Symbol", None)
            if sym is None:
                continue
            h_ticker = str(getattr(sym, "Value", sym))
            self._invested_tickers.add(h_ticker)
            self._invested_symbols[h_ticker] = sym
            invested_weight += float(getattr(holding, "HoldingsValue", 0.0) or 0.0) / portfolio_value
            if self._surrogate_router:
                und = self._surrogate_router.get_underlying_ticker(h_ticker)
                if und:
                    self._invested_tickers.add(und)
                    self._invested_symbols.setdefault(und, sym)

        _raw_cash = getattr(algorithm.Portfolio, "Cash", None)
        port_cash = (
            float(_raw_cash)
            if isinstance(_raw_cash, (int, float))
            else portfolio_value
        )

        # Book-level policy — three ASTs evaluated once per pass (C-FW-RULES
        # Phase 3). scale_expr resolves the deployment fraction; slots_expr
        # resolves the position ceiling; both see regime/acct contexts.
        pt_on = pt_days = 0.0
        if self._store is not None:
            _g = getattr(self._store, "get_regime_field", None)
            if callable(_g):
                _v = _g(as_of, "power_trend_on")
                _w = _g(as_of, "power_trend_days")
                pt_on = float(_v) if _v is not None else 0.0
                pt_days = float(_w) if _w is not None else 0.0
        regime_ctx = {
            "fraction": float(regime_fraction) if self._use_regime_scaling else 1.0,
            "on": 1.0 if regime_on else 0.0,
            "scaling_on": 1.0 if self._use_regime_scaling else 0.0,
            "min_fraction": float(self._min_regime_fraction),
            # IBD Power Trend on ^IXIC, computed per-run by the regime loader
            # (fail-closed: 0 when index data is absent).
            "power_trend_on": pt_on,
            "power_trend_days": pt_days,
        }
        acct = {
            "portfolio_value": portfolio_value,
            "cash_pct": port_cash / portfolio_value if portfolio_value > 0 else 1.0,
            "invested_count": float(current_invested),
            "invested_weight": invested_weight,
            "max_positions": float(self._max_positions),
            "slots_floor": float(self._scaled_max_positions_floor),
            "risk_budget_pct": float(self._risk_per_trade_pct),
            "max_weight": float(self._max_position_weight),
            "loss_streak": float(trailing_loss_streak(algorithm)),
            # Book-fraction of cash still deployable this pass — entries and
            # add deltas decrement it so emitted targets can't exceed free cash.
            "cash_remaining_pct": port_cash / portfolio_value if portfolio_value > 0 else 1.0,
        }
        book_ctx = {"regime": regime_ctx, "acct": acct}

        try:
            eff = evaluate_slot_number({}, self._scale_expr, contexts=book_ctx)
        except Exception as exc:
            eff = None
            try:
                algorithm.Debug(f"⚠️ PCM scale_expr eval error: {exc} — fallback 1.0")
            except Exception:
                pass
        effective_scale = max(0.0, float(eff)) if isinstance(eff, (int, float)) else 1.0
        self._last_effective_scale = float(effective_scale)
        regime_ctx["scale"] = float(effective_scale)

        try:
            slots_v = evaluate_slot_number({}, self._slots_expr, contexts=book_ctx)
        except Exception as exc:
            slots_v = None
            try:
                algorithm.Debug(
                    f"⚠️ PCM slots_expr eval error: {exc} — fallback max_positions"
                )
            except Exception:
                pass
        scaled_max_positions = (
            max(0, int(round(float(slots_v))))
            if isinstance(slots_v, (int, float))
            else self._max_positions
        )
        acct["scaled_max_positions"] = float(scaled_max_positions)
        acct["slots_remaining"] = float(max(0, scaled_max_positions - current_invested))

        # Drop pyramid state / flags / fired markers for names no longer held.
        for ticker in list(self._pyramid_states.keys()):
            if ticker not in self._invested_tickers:
                self._pyramid_states.pop(ticker, None)
                self._pcm_flags.pop(ticker, None)
                self._pcm_rule_fired.pop(ticker, None)

        # Decision units: insights first (Alpha rank order = allocation order),
        # then insight-quiet holdings so book rules (drift cap) see quiet days.
        # order_expr re-sorts on light contexts — the generated default is
        # `ref cand.rank`, i.e. exactly this assembly order.
        units: list[tuple[Any, Any, str, int]] = []  # (insight|None, symbol, ticker, rank)
        covered: set[str] = set()
        for i in insights or []:
            sym = getattr(i, "Symbol", None)
            if sym is None:
                continue
            ticker = str(getattr(sym, "Value", sym))
            if getattr(i, "Direction", None) == InsightDirection.Flat:
                continue  # "no opinion" — the holding still forms its own unit
            covered.add(ticker)
            units.append((i, sym, ticker, len(units)))
        for h_ticker, sym in self._invested_symbols.items():
            if h_ticker not in covered:
                units.append((None, sym, h_ticker, len(units)))
        units.sort(
            key=lambda u: self._order_key(
                algorithm, u[0], u[2], u[3], acct, regime_ctx, as_of
            )
        )

        self._displaced_today = 0
        self._displaced_symbols: set[str] = set()
        for insight, sym, ticker, rank in units:
            if ticker in self._displaced_symbols:
                continue  # this holding was flattened by a displace action
            self._apply_unit_rules(
                algorithm, insight, sym, ticker, rank, acct, regime_ctx,
                targets, today, as_of, portfolio_value,
            )
        return targets

    def _order_key(self, algorithm, insight, ticker, rank, acct, regime_ctx, as_of):
        """order_expr sort key on a light context (full cand build happens later).

        Light bindings only: ``cand.{rank,has_insight,is_new,is_add,is_down,
        confidence,weight,rs}``, ``hold.invested``, ``acct``, ``regime`` —
        deep ``hold.*``/``pyr.*`` don't exist yet at ordering time.
        """
        invested = ticker in self._invested_tickers
        cand = {
            "rank": float(rank),
            "has_insight": 1.0 if insight is not None else 0.0,
            "is_new": 0.0 if (insight is None or invested) else 1.0,
            "is_add": 1.0 if (insight is not None and invested) else 0.0,
            "is_down": 0.0,
        }
        row = {}
        if insight is not None:
            if getattr(insight, "Direction", None) == InsightDirection.Down:
                cand["is_down"] = 1.0
            for attr, key in (("Confidence", "confidence"), ("Weight", "weight")):
                raw = getattr(insight, attr, None)
                try:
                    cand[key] = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0.0
                except (TypeError, ValueError):
                    cand[key] = 0.0
            row = self._store_row(ticker, as_of)
        cand["rs"] = float(row.get("rs_rating") or self._last_known_rs.get(ticker, 0.0) or 0.0)
        ctx = {
            "cand": cand,
            "hold": {"invested": 1.0 if invested else 0.0},
            "acct": acct,
            "regime": regime_ctx,
        }
        try:
            key = evaluate_slot_number(row, self._order_expr, contexts=ctx)
        except Exception as exc:
            key = None
            try:
                algorithm.Debug(f"⚠️ PCM order_expr eval error [{ticker}]: {exc}")
            except Exception:
                pass
        return float(key) if isinstance(key, (int, float)) else float(rank)

    def _apply_unit_rules(
        self, algorithm, insight, symbol, ticker, rank, acct, regime_ctx,
        targets, today, as_of, portfolio_value,
    ):
        row = dict(self._store_row(ticker, as_of))
        fired = self._pcm_rule_fired.get(ticker, set())
        for name in fired:
            row[f"__rule.{name}.fired"] = True

        if insight is not None:
            cand, trade_symbol, leverage = self._build_cand(algorithm, insight, row, today, as_of)
        else:
            cand, trade_symbol, leverage = {
                "has_insight": 0.0,
                "is_down": 0.0,
                "is_new": 0.0,
                "is_add": 0.0,
            }, symbol, 1.0
        cand["rank"] = float(rank)
        hold = self._build_hold(algorithm, symbol, ticker, row, portfolio_value, today)
        if cand.get("is_add") and ticker not in self._pyramid_states:
            # Recover mid-flight (state lost to redeploy/prune): assume the
            # position is at its first phase, anchored at average cost, held
            # at least one day — the bindings must see the recovered values.
            state = PyramidPositionState(ticker, self._phases)
            state.entry_price = float(hold.get("entry") or cand.get("price") or 0.0)
            state.highest_price = float(cand.get("confirm_price") or hold.get("price") or 0.0)
            state.entry_date = today - timedelta(days=1)
            self._pyramid_states[ticker] = state
            hold["days_held"] = 1.0
        pyr = self._build_pyr(ticker)
        contexts = {
            "cand": cand,
            "hold": hold,
            "acct": acct,
            "pyr": pyr,
            "regime": regime_ctx,
        }

        rules = self._rules
        size_expr = self._size_expr
        if self._policy_overrides:
            try:
                ov = resolve_policy_overrides(self._policy_overrides, row, consumer="pcm")
            except Exception:
                ov = {}
            if ov:
                # Generated artifacts re-materialize per row (authored ASTs are
                # authoritative — same contract as the risk slot).
                if not self._size_expr_authored:
                    size_expr = self._generated_size_expr(ov)
                if self._rules_from_defaults:
                    rules = [
                        _r.model_dump()
                        for _r in validate_rules(
                            self._generated_ladder(ov),
                            slot="PortfolioConstruction(generated)",
                        )
                    ]
                # Generated ASTs read magnitude knobs via bindings — overlay the
                # resolved override onto this unit's acct binding so the override
                # still lands (per-unit contexts; the shared acct dict is untouched).
                acct_ov = {}
                if "max_position_weight" in ov:
                    acct_ov["max_weight"] = float(ov["max_position_weight"])
                if "risk_per_trade_pct" in ov:
                    acct_ov["risk_budget_pct"] = float(ov["risk_per_trade_pct"])
                if acct_ov:
                    contexts = {**contexts, "acct": {**acct, **acct_ov}}

        sorted_rules = sorted(
            enumerate(rules or []),
            key=lambda x: (x[1].get("priority", 0) if isinstance(x[1], dict) else 0, x[0]),
        )
        for _idx, rule in sorted_rules:
            name = rule.get("name", f"rule_{_idx}")
            when = rule.get("when", {})
            if rule.get("once", False) and name in fired:
                continue
            try:
                matched = evaluate_slot_bool(row, when, contexts=contexts)
            except Exception as exc:
                matched = False
                try:
                    algorithm.Debug(f"⚠️ PCM RULE EVAL ERROR [{ticker}] {name}: {exc}")
                except Exception:
                    pass
            if not matched:
                continue
            terminal = False
            for action in rule.get("then", []):
                if not isinstance(action, dict):
                    continue
                atype = action.get("type")
                if ACTION_TERMINAL.get(atype, False):
                    terminal = True
                if atype == "skip":
                    pass  # decided: nothing emitted
                elif atype == "resize":
                    to_val = evaluate_slot_number(row, action.get("to"), contexts=contexts)
                    if to_val is not None:
                        tgt_sym = (
                            self._invested_symbols.get(ticker) or symbol
                        )
                        self._emit_weight(
                            algorithm, tgt_sym, float(to_val),
                            str(rule.get("tag") or name), ticker, targets,
                        )
                elif atype == "enter" or atype == "add":
                    base = evaluate_slot_number(row, size_expr, contexts=contexts)
                    scale = evaluate_slot_number(
                        row, action.get("size_scale") or {"type": "lit", "value": 1.0},
                        contexts=contexts,
                    )
                    if base is None or scale is None or base <= 0 or scale <= 0:
                        continue
                    unit_tag = str(rule.get("tag") or name)
                    if leverage > 1.0:
                        surr = f"surrogate_{leverage:.1f}x:underlying={ticker}"
                        unit_tag = f"{unit_tag}_{surr}" if unit_tag else surr
                    if atype == "enter":
                        self._do_enter(
                            algorithm, unit_sym=trade_symbol, ticker=ticker,
                            weight=base * scale, tag=unit_tag,
                            row=row, targets=targets, acct=acct, today=today,
                        )
                    else:
                        self._do_add(
                            algorithm, symbol, trade_symbol, ticker,
                            weight=base * scale, tag=unit_tag,
                            hold=hold, targets=targets,
                            row=row, contexts=contexts,
                        )
                elif atype == "displace":
                    self._do_displace(
                        algorithm, action, acct, regime_ctx, targets, today,
                        as_of, portfolio_value,
                        tag=str(rule.get("tag") or name),
                        row=row, contexts=contexts,
                    )
                elif atype == "arm_cooldown":
                    days = int(action_arg_number(row, action, "days", contexts=contexts, default=0.0) or 0)
                    if days > 0:
                        self._displacement_cooldown[ticker] = today + timedelta(days=days)
                elif atype == "set_flag":
                    flag = str(action.get("flag") or "")
                    if flag:
                        self._pcm_flags.setdefault(ticker, set()).add(flag)
                        contexts["hold"][flag] = 1.0
            if terminal:
                self._pcm_rule_fired.setdefault(ticker, set()).add(name)
                return

    def _do_enter(self, algorithm, unit_sym, ticker, weight, tag, row, targets, acct, today):
        """`enter`: emit the buy target, consume a slot, open pyramid state."""
        cash_rem = float(acct.get("cash_remaining_pct", 1.0))
        reserve = weight * (1.0 + self._cash_reserve_buffer)
        if reserve > cash_rem + 1e-6:
            try:
                algorithm.Debug(
                    f"💸 CASH-GATE [{ticker}]: entry target={weight:.1%} reserve={reserve:.1%} > cash_remaining={cash_rem:.1%}"
                )
            except Exception:
                pass
            return
        acct["cash_remaining_pct"] = cash_rem - reserve
        acct["slots_remaining"] = float(acct.get("slots_remaining", 0.0)) - 1.0
        acct["invested_count"] = float(acct.get("invested_count", 0.0)) + 1.0
        state = PyramidPositionState(ticker, self._phases)
        sec = self._sec(algorithm, unit_sym)
        px = float(getattr(sec, "Price", 0.0) or 0.0) if sec else 0.0
        state.entry_price = px or float(row.get("close") or 0.0)
        state.highest_price = state.entry_price
        state.entry_date = today
        if row and row.get("rs_rating") is not None:
            try:
                state.entry_rs = float(row["rs_rating"])
                self._last_known_rs[ticker] = state.entry_rs
            except (TypeError, ValueError):
                pass
        self._pyramid_states[ticker] = state
        try:
            algorithm.Debug(
                f"📈 ENTER [{ticker}]: target={weight:.1%} scale={self._last_effective_scale:.0%} tag={tag}"
            )
        except Exception:
            pass
        self._emit_weight(algorithm, unit_sym, weight, tag, ticker, targets)

    def _do_add(self, algorithm, symbol, trade_symbol, ticker, weight, tag, hold, targets, *, row=None, contexts=None):
        """`add`: advance the phase (gated by phases[next].trigger), then emit
        the add-to weight target."""
        state = self._pyramid_states.get(ticker)
        if state is None:
            # Recover mid-flight: assume already at test phase.
            state = PyramidPositionState(ticker, self._phases)
            state.entry_price = float(hold.get("entry") or hold.get("price") or 0.0)
            state.highest_price = float(hold.get("price") or 0.0)
            self._pyramid_states[ticker] = state
        # Per-phase gate: phases[next].trigger is a typed bool AST on the unit
        # context — a failed trigger means the position holds its current phase.
        if not state.next_phase_allows(row or {}, contexts):
            try:
                algorithm.Debug(f"📊 PHASE GATE [{ticker}]: trigger for next phase not met")
            except Exception:
                pass
            return
        state.advance()
        state.highest_price = max(
            float(state.highest_price or 0.0), float(hold.get("price") or 0.0)
        )
        held_w = float(hold.get("weight") or 0.0)
        if weight <= held_w + 1e-4:
            try:
                algorithm.Debug(
                    f"📊 SKIP ADD [{ticker}]: held={held_w:.1%} already >= target={weight:.1%}"
                )
            except Exception:
                pass
            return
        delta_w = weight - held_w
        acct_ctx = (contexts or {}).get("acct") or {}
        cash_rem = float(acct_ctx.get("cash_remaining_pct", 1.0))
        reserve = delta_w * (1.0 + self._cash_reserve_buffer)
        if reserve > cash_rem + 1e-6:
            try:
                algorithm.Debug(
                    f"💸 CASH-GATE [{ticker}]: add Δ={delta_w:.1%} reserve={reserve:.1%} > cash_remaining={cash_rem:.1%}"
                )
            except Exception:
                pass
            return
        acct_ctx["cash_remaining_pct"] = cash_rem - reserve
        try:
            algorithm.Debug(
                f"📊 PYRAMID ADD [{ticker}]: held={held_w:.1%} → target={weight:.1%} tag={tag}"
            )
        except Exception:
            pass
        self._emit_weight(algorithm, trade_symbol, weight, tag, ticker, targets)

    def _do_displace(self, algorithm, action, acct, regime_ctx, targets, today, as_of, portfolio_value, tag, *, row=None, contexts=None):
        """`displace`: flatten the weakest qualifying incumbent; free a slot.

        Threshold args are operands evaluated on the challenger unit's context
        (``row``/``contexts``) — literals pass straight through.
        """
        u_row = row or {}
        if self._displaced_today >= int(
            action_arg_number(u_row, action, "max_per_day", contexts=contexts, default=2.0) or 2
        ):
            return
        min_days = int(action_arg_number(u_row, action, "min_incumbent_days", contexts=contexts, default=5.0) or 0)
        max_r = float(action_arg_number(u_row, action, "max_incumbent_r", contexts=contexts, default=1.0) or 1.0)
        immune_rs = float(action_arg_number(u_row, action, "immune_rs", contexts=contexts, default=95.0) or 95.0)
        cooldown_days = int(action_arg_number(u_row, action, "cooldown_days", contexts=contexts, default=14.0) or 0)
        score_expr = action.get("incumbent_score")
        best = None  # (sort_key, open_r, rs, sym, ticker)
        for holding in getattr(algorithm.Portfolio, "Values", []):
            if not holding or not getattr(holding, "Invested", False):
                continue
            sym = getattr(holding, "Symbol", None)
            if sym is None:
                continue
            h_ticker = str(getattr(sym, "Value", sym))
            if h_ticker in self._displaced_symbols:
                continue
            h_state = self._pyramid_states.get(h_ticker)
            h_days = (today - h_state.entry_date).days if (h_state and h_state.entry_date) else 0
            if h_days < min_days:
                continue
            avg_cost = float(getattr(holding, "AveragePrice", 0.0) or 0.0)
            h_px = float(getattr(holding, "Price", 0.0) or 0.0)
            risk_per_share = avg_cost * self._default_stop_loss_pct
            open_r = (
                (h_px - avg_cost) / risk_per_share
                if (risk_per_share > 0 and avg_cost > 0)
                else 0.0
            )
            if open_r >= max_r:
                continue
            h_row = self._store_row(h_ticker, as_of)
            h_rs = float(h_row.get("rs_rating") or self._last_known_rs.get(h_ticker, 0.0) or 0.0)
            if h_rs <= 0.0 and h_state and getattr(h_state, "entry_rs", 0.0):
                h_rs = float(h_state.entry_rs or 0.0)
            if h_rs >= immune_rs:
                continue
            if score_expr is not None:
                # Authored incumbent ranking — hold.* binds to the incumbent.
                inc_ctx = {
                    "hold": {
                        "invested": 1.0,
                        "weight": float(getattr(holding, "HoldingsValue", 0.0) or 0.0) / portfolio_value
                        if portfolio_value > 0 else 0.0,
                        "entry": avg_cost,
                        "price": h_px,
                        "days_held": float(h_days),
                        "open_r": float(open_r),
                        "rs": h_rs,
                    },
                    "acct": acct,
                    "regime": regime_ctx,
                }
                try:
                    s = evaluate_slot_number(h_row, score_expr, contexts=inc_ctx)
                except Exception:
                    s = None
                sort_key = float(s) if isinstance(s, (int, float)) else float("inf")
            else:
                # Default pairing: lowest open_r, then lowest RS.
                sort_key = (open_r, h_rs)
            if best is None or sort_key < best[0]:
                best = (sort_key, open_r, h_rs, sym, h_ticker)
        if best is None:
            return
        _key, open_r, h_rs, inc_sym, inc_ticker = best
        self._emit_weight(algorithm, inc_sym, 0.0, tag, inc_ticker, targets)
        self._displacement_cooldown[inc_ticker] = today + timedelta(days=cooldown_days)
        self._displaced_today += 1
        self._displaced_symbols.add(inc_ticker)
        self._pyramid_states.pop(inc_ticker, None)
        self._pcm_flags.pop(inc_ticker, None)
        self._pcm_rule_fired.pop(inc_ticker, None)
        acct["slots_remaining"] = float(acct.get("slots_remaining", 0.0)) + 1.0
        acct["invested_count"] = float(acct.get("invested_count", 0.0)) - 1.0
        try:
            algorithm.Debug(
                f"🔄 DISPLACE [{inc_ticker}] (R={open_r:+.2f}, RS={h_rs:.0f}) → frees slot tag={tag}"
            )
        except Exception:
            pass
