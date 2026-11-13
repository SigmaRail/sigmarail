"""
Store-backed Alpha: shortlist + setup/triggers → daily Up Insights.

Criteria and Confidence (signal quality) live here. Progressive scale-in
(phases / add_trigger / starter vs add) is owned by RiskBudgeted PCM — Alpha
does not walk Portfolio for adds or emit ``tranche1_add`` Tags.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sigmarail_lab.runtime.signal_evaluation import (
    evaluate_entry_triggers,
    evaluate_slot_bool,
    evaluate_slot_number,
    evaluate_where_ast,
)

try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect import Market, SecurityType, Symbol
    from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
except ImportError:
    class AlphaModel:
        pass

    class InsightDirection:
        Up = 1
        Down = -1
        Flat = 0

    class Insight:
        @classmethod
        def Price(cls, symbol, period, direction, confidence=None, magnitude=None, weight=None, **kwargs):
            class _I:
                pass

            i = _I()
            i.Symbol = symbol
            i.Period = period
            i.Direction = direction
            i.Confidence = confidence
            i.Magnitude = magnitude
            i.Weight = weight
            i.Tag = ""
            return i

    class Symbol:
        def __init__(self, val):
            self.Value = str(val)

        @classmethod
        def Create(cls, ticker, sec_type=None, market=None):
            return cls(ticker)

    class SecurityType:
        Equity = 1

    class Market:
        USA = 1


def atr_stop_price(
    entry_price: float,
    atr_14_pct: float | None,
    multiplier: float,
    max_stop_loss_pct: float = 0.05,
) -> float | None:
    """ATR stop from L7 ``atr_14_pct`` (percent of close, e.g. ``1.54`` = 1.54%).

    Distance = ``multiplier * atr_14_pct / 100``, capped at ``max_stop_loss_pct``.
    """
    if entry_price <= 0 or atr_14_pct is None:
        return None
    try:
        atr_frac = abs(float(atr_14_pct)) / 100.0
        dist = min(atr_frac * float(multiplier), float(max_stop_loss_pct))
        stop = float(entry_price) * (1.0 - dist)
    except (TypeError, ValueError):
        return None
    if stop <= 0:
        return None
    return stop


def _z_scores(values: dict[str, float | None]) -> dict[str, float]:
    """Cross-sectional z-scores for a dict of {key: value}."""
    nums = {k: v for k, v in values.items() if v is not None}
    n = len(nums)
    if n < 2:
        return {k: 0.0 for k in values}
    mean = sum(nums.values()) / n
    var = sum((v - mean) ** 2 for v in nums.values()) / (n - 1)
    std = var ** 0.5
    if std < 1e-12:
        return {k: 0.0 for k in values}
    return {k: (nums.get(k, mean) - mean) / std for k in values}


# Re-export for tests / callers that still import from this module.
from sigmarail_lab.runtime.pyramid_position_state import PyramidPositionState  # noqa: E402


class VeraPyramidAlphaModel(AlphaModel):
    """Store-backed shortlist Alpha: score → select → emit Up when criteria met."""

    def __init__(
        self,
        store,
        max_positions: int = 10,
        min_hold_days: int = 5,
        stop_loss_pct: float = 0.05,
        stop_cooldown_days: int = 10,
        field_weights: dict[str, float] | None = None,
        phases: list[dict[str, Any]] | None = None,
        selection: dict[str, Any] | None = None,
        entry_triggers: list[dict[str, Any]] | None = None,
        stop_loss: dict[str, Any] | None = None,
        uses: list[str] | None = None,
        membership: dict[str, Any] | None = None,
        named_groups: dict[str, Any] | None = None,
        stages: list[dict[str, Any]] | None = None,
        setup_where: dict[str, Any] | None = None,
        gates: list[dict[str, Any]] | None = None,
        gate_combine: str = "union",
        min_screens: int = 2,
        add_trigger_pct: float = 0.02,
        setup_col: str | None = None,
        row_rank: dict[str, Any] | None = None,
        row_scale_denom: float = 5.0,
        setup_expr: dict[str, Any] | None = None,
        confidence_expr: dict[str, Any] | None = None,
        direction_expr: dict[str, Any] | None = None,
        magnitude_expr: dict[str, Any] | None = None,
        weight_expr: dict[str, Any] | None = None,
        insight_period_days: int | None = None,
        eligibility_expr: dict[str, Any] | None = None,
        risk_allow_pyramid_add_expr: dict[str, Any] | None = None,
        # atr_14_pct is absolute percent of close in L7 (e.g. 5.0 = 5%). Cap entries;
        # 3.5 filters gap-prone names while keeping SEPA leaders.
        max_entry_atr_pct: float = 3.5,
        **kwargs: Any,
    ):
        self._store = store
        self._max_positions = int(max_positions)
        self._min_hold_days = int(min_hold_days)
        # Legacy kwargs accepted for old IR; scale-in owned by PCM.
        del phases
        del add_trigger_pct
        del risk_allow_pyramid_add_expr
        self._max_entry_atr_pct = float(max_entry_atr_pct)
        self._stop_loss_pct = float(stop_loss_pct)
        if stop_loss and stop_loss.get("type") == "fixed_pct" and stop_loss.get("pct") is not None:
            self._stop_loss_pct = float(stop_loss["pct"])
        self._stop_cooldown_days = int(stop_cooldown_days)
        self._field_weights = field_weights or {"rs_rating": 1.0}
        self._selection = selection or {"method": "top_n", "n": int(max_positions)}
        self._entry_triggers = entry_triggers or []
        # Legacy Vera Parameters — not Lean. Prefer bool measures / post_where for timing.
        # Empty list = emit for every shortlisted name that passes setup.
        self._stop_loss = stop_loss
        self._uses = {str(u) for u in (uses or [])}
        self._setup_where = setup_where
        self._setup_col = str(setup_col).strip() if setup_col else None
        self._setup_expr = dict(setup_expr) if setup_expr else None
        self._confidence_expr = dict(confidence_expr) if confidence_expr else None
        self._direction_expr = dict(direction_expr) if direction_expr else None
        self._magnitude_expr = dict(magnitude_expr) if magnitude_expr else None
        self._weight_expr = dict(weight_expr) if weight_expr else None
        try:
            self._insight_period_days = max(1, int(insight_period_days or 1))
        except (TypeError, ValueError):
            self._insight_period_days = 1
        self._eligibility_expr = dict(eligibility_expr) if eligibility_expr else None
        self._row_rank = dict(row_rank) if row_rank else None
        self._row_scale_denom = float(row_scale_denom) if row_scale_denom else 5.0
        self._gates = list(gates or [])
        self._gate_combine = str(gate_combine or "union").strip().lower()
        self._min_screens = int(min_screens)
        self._membership = membership
        self._named_groups = dict(named_groups or {})
        del stages
        del kwargs
        self._entry_prices: dict[str, float] = {}
        self._entry_dates: dict[str, Any] = {}
        self._stopped_out: dict[str, Any] = {}
        self._last_run_date = None
        self.Name = "VeraPyramidAlphaModel"

    def _regime_score_on(self, algorithm) -> bool:
        """True when regime score allows 'on' behavior (hysteresis evaluator / clamp)."""
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        if hasattr(self._store, "allows_new_longs_from_regime_signals"):
            return bool(self._store.allows_new_longs_from_regime_signals(as_of))
        return bool(self._store.get_spy_is_bull(as_of))

    def _is_bull_market(self, algorithm) -> bool:
        """Deprecated valve helper — prefer uses[] + _regime_score_on."""
        return self._regime_score_on(algorithm)

    def _compute_composite_score(self, rows: dict[str, dict[str, Any]]) -> dict[str, float]:
        """Blend weighted factor z-scores. Factor names map to row columns."""
        tickers = list(rows.keys())
        if not tickers:
            return {}
        field_values: dict[str, dict[str, float | None]] = {f: {} for f in self._field_weights}
        for ticker in tickers:
            row = rows[ticker]
            for field in self._field_weights:
                field_values[field][ticker] = row.get(field)
        composite: dict[str, float] = {}
        for ticker in tickers:
            score = 0.0
            for field, weight in self._field_weights.items():
                zs = _z_scores(field_values[field])
                score += zs.get(ticker, 0.0) * weight
            composite[ticker] = score
        return composite

    def _gate_require_passes(self, row: dict[str, Any], gate: dict[str, Any]) -> bool:
        """Membership / named-group require_flag used by union and count combine."""
        require = str(gate.get("require_flag") or "")
        if not require:
            require = "in_code_33" if gate.get("omit_tt") else "in_membership"
        if require == "in_membership" and self._membership:
            return evaluate_where_ast(row, self._membership)
        if require == "in_code_33":
            code_ast = self._named_groups.get("code_33")
            if code_ast:
                return evaluate_where_ast(row, code_ast)
            if not gate.get("omit_tt") and self._membership:
                return evaluate_where_ast(row, self._membership)
        return True

    def _primary_hit_col(self) -> str:
        if self._row_rank and isinstance(self._row_rank.get("by"), list) and self._row_rank["by"]:
            return str(self._row_rank["by"][0])
        return "screens_hit"

    def _floor_hit_col(self) -> str:
        """Eligibility floor column — unweighted screens_hit when present."""
        if self._row_rank and isinstance(self._row_rank.get("min"), dict):
            min_map = self._row_rank["min"]
            if "screens_hit" in min_map:
                return "screens_hit"
            if min_map:
                return str(next(iter(min_map.keys())))
        primary = self._primary_hit_col()
        if primary == "screens_hit_w":
            return "screens_hit"
        return primary

    def _score_from_col(
        self, rows: dict[str, dict[str, Any]], col: str
    ) -> dict[str, float] | None:
        if not any(col in (row or {}) for row in rows.values()):
            return None
        out: dict[str, float] = {}
        for ticker, row in rows.items():
            raw = (row or {}).get(col)
            if raw is None:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if val:
                out[ticker] = val
        return out

    def _count_gate_picks(self, rows: dict[str, dict[str, Any]]) -> dict[str, float]:
        """Ticker → hit score for ranking (weighted or unweighted).

        Prefers the SQL rank column (row_rank.by[0] or ``screens_hit``) when present.
        Fallback sums gate ``signal_weight`` (default 1) for matching gates.
        """
        hit_col = self._primary_hit_col()
        from_sql = self._score_from_col(rows, hit_col)
        if from_sql is not None:
            return from_sql
        counts: dict[str, float] = {}
        for ticker, row in rows.items():
            hits = 0.0
            for gate in self._gates:
                if gate.get("count_as_signal") is False:
                    continue
                where = gate.get("where")
                if where and not evaluate_where_ast(row, where):
                    continue
                if not self._gate_require_passes(row, gate):
                    continue
                try:
                    w = float(gate.get("signal_weight") or 1.0)
                except (TypeError, ValueError):
                    w = 1.0
                hits += w
            if hits:
                counts[ticker] = hits
        return counts

    def _unweighted_gate_picks(self, rows: dict[str, dict[str, Any]]) -> dict[str, float]:
        """Ticker → unweighted hit count for eligibility floor."""
        floor_col = self._floor_hit_col()
        from_sql = self._score_from_col(rows, floor_col)
        if from_sql is not None:
            return from_sql
        counts: dict[str, float] = {}
        for ticker, row in rows.items():
            hits = 0.0
            for gate in self._gates:
                if gate.get("count_as_signal") is False:
                    continue
                where = gate.get("where")
                if where and not evaluate_where_ast(row, where):
                    continue
                if not self._gate_require_passes(row, gate):
                    continue
                hits += 1.0
            if hits:
                counts[ticker] = hits
        return counts

    def _rank_by_screens_hit(self, rows: dict[str, dict[str, Any]]) -> list[str]:
        """Eligible tickers sorted by rank hit col desc, then blend / tie col desc.

        Eligibility floor uses unweighted ``screens_hit`` (or row_rank.min key);
        ranking may use ``screens_hit_w``.
        """
        rank_scores = self._count_gate_picks(rows)
        floor_scores = self._unweighted_gate_picks(rows)
        floor_col = self._floor_hit_col()
        min_hits = float(self._min_screens)
        if self._row_rank and isinstance(self._row_rank.get("min"), dict):
            min_map = self._row_rank["min"]
            if floor_col in min_map:
                min_hits = float(min_map[floor_col])
            elif self._primary_hit_col() in min_map:
                min_hits = float(min_map[self._primary_hit_col()])
        if self._eligibility_expr is not None:
            eligible_tickers = {
                t
                for t in set(rank_scores) | set(floor_scores)
                if evaluate_slot_bool(rows.get(t) or {}, self._eligibility_expr)
            }
        else:
            eligible_tickers = {
                t for t, n in floor_scores.items() if n >= min_hits
            }
        if not eligible_tickers:
            return []
        eligible_rows = {t: rows[t] for t in eligible_tickers if t in rows}
        scores = self._compute_composite_score(eligible_rows)
        tie_col = None
        if self._row_rank and isinstance(self._row_rank.get("by"), list):
            by = [str(x) for x in self._row_rank["by"]]
            if len(by) > 1:
                tie_col = by[1]

        def _tie(t: str) -> float:
            if tie_col and tie_col in (rows.get(t) or {}):
                try:
                    return float((rows[t] or {}).get(tie_col) or 0.0)
                except (TypeError, ValueError):
                    pass
            return scores.get(t, 0.0)

        return sorted(
            eligible_tickers,
            key=lambda t: (rank_scores.get(t, 0.0), _tie(t)),
            reverse=True,
        )

    def _setup_passes(self, row: dict[str, Any]) -> bool:
        """True when setup_expr matches, setup_col is 1, or setup_where matches."""
        if self._setup_expr is not None:
            return evaluate_slot_bool(row, self._setup_expr)
        if self._setup_col and self._setup_col in row:
            try:
                return int(row.get(self._setup_col) or 0) != 0
            except (TypeError, ValueError):
                return False
        if "setup_pass" in row:
            try:
                return int(row.get("setup_pass") or 0) != 0
            except (TypeError, ValueError):
                return False
        if self._setup_where:
            return evaluate_where_ast(row, self._setup_where)
        return True

    def _screens_hit_confidence(self, row: dict[str, Any], ticker: str, hits: dict[str, float]) -> float | None:
        """Confidence from confidence_expr; unbound → 1.0 (no screens_hit hardcode)."""
        if self._confidence_expr is not None:
            val = evaluate_slot_number(row, self._confidence_expr)
            if val is None:
                return None
            return max(0.1, min(1.0, float(val)))
        return 1.0

    def _direction_from_row(self, row: dict[str, Any]):
        """Map measure Int8 (1 / -1 / 0) → InsightDirection. Unbound → Up (legacy)."""
        """Map measure (>0 / <0 / ==0) → InsightDirection. Unbound → Up (legacy)."""
        if self._direction_expr is None:
            return InsightDirection.Up
        val = evaluate_slot_number(row, self._direction_expr)
        if val is None:
            return InsightDirection.Flat
        try:
            n = int(round(float(val)))
            f = float(val)
        except (TypeError, ValueError):
            return InsightDirection.Flat
        if f > 1e-6 or n > 0:
            return InsightDirection.Up
        if f < -1e-6 or n < 0:
            return InsightDirection.Down
        return InsightDirection.Flat

    def _magnitude_from_row(self, row: dict[str, Any]) -> float | None:
        if self._magnitude_expr is None:
            return None
        val = evaluate_slot_number(row, self._magnitude_expr)
        if val is None:
            return None
        try:
            return max(-0.25, min(0.25, float(val)))
        except (TypeError, ValueError):
            return None

    def _weight_from_row(self, row: dict[str, Any]) -> float | None:
        if self._weight_expr is None:
            return None
        val = evaluate_slot_number(row, self._weight_expr)
        if val is None:
            return None
        try:
            return max(0.0, min(1.0, float(val)))
        except (TypeError, ValueError):
            return None

    def _union_gate_picks(self, rows: dict[str, dict[str, Any]]) -> set[str] | None:
        """Per-gate score + top_k union. None means fall back to field_weights top-N."""
        if not self._gates:
            return None
        picked: set[str] = set()
        for gate in self._gates:
            fields = [
                str(f)
                for f in list(gate.get("score_fields") or [])
                + list(gate.get("optional_score_fields") or [])
            ]
            where = gate.get("where")
            optional_min = gate.get("optional_min") or {}
            scored: dict[str, float] = {}
            matching: list[str] = []
            for ticker, row in rows.items():
                if where and not evaluate_where_ast(row, where):
                    continue
                if not self._gate_require_passes(row, gate):
                    continue
                skip = False
                for field, min_v in optional_min.items():
                    raw = row.get(field)
                    n_col = {
                        "eps_ny_rev_pct_90d": "eps_ny_n",
                        "eps_nq_rev_pct_90d": "eps_nq_n",
                        "eps_cq_rev_pct_90d": "eps_cq_n",
                        "eps_cy_rev_pct_90d": "eps_cy_n",
                    }.get(str(field))
                    n_raw = row.get(n_col) if n_col else None
                    try:
                        n_val = float(n_raw) if n_raw is not None else None
                    except (TypeError, ValueError):
                        n_val = None
                    if raw is None or (n_val is not None and n_val <= 0):
                        continue
                    try:
                        if float(raw) < float(min_v):
                            skip = True
                            break
                    except (TypeError, ValueError):
                        continue
                if skip:
                    continue
                matching.append(ticker)
                vals: list[float] = []
                for field in fields:
                    raw = row.get(field)
                    if raw is None:
                        continue
                    try:
                        vals.append(float(raw))
                    except (TypeError, ValueError):
                        continue
                if vals:
                    scored[ticker] = sum(vals) / len(vals)
            top_k = int(gate.get("top_k") or 15)
            if scored:
                picked.update(
                    t
                    for t, _ in sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[
                        :top_k
                    ]
                )
            elif matching:
                picked.update(matching[:top_k])
        return picked

    def _security_price(self, algorithm, symbol) -> float:
        sec = getattr(algorithm, "Securities", None)
        if sec is None:
            return 0.0
        val = getattr(symbol, "Value", str(symbol))
        if symbol in sec:
            return float(getattr(sec[symbol], "Price", 0.0) or 0.0)
        if val in sec:
            return float(getattr(sec[val], "Price", 0.0) or 0.0)
        return 0.0

    def _securities_has(self, algorithm, symbol) -> bool:
        sec = getattr(algorithm, "Securities", None)
        if sec is None:
            return False
        if hasattr(sec, "ContainsKey"):
            return bool(sec.ContainsKey(symbol))
        val = getattr(symbol, "Value", str(symbol))
        return symbol in sec or val in sec

    def _portfolio_items(self, algorithm):
        port = getattr(algorithm, "Portfolio", None)
        if port is None:
            return []
        if isinstance(port, dict):
            return [(k, v) for k, v in port.items()]
        if hasattr(port, "items") and callable(port.items):
            return port.items()
        if hasattr(port, "Values"):
            return [(getattr(v, "Symbol", None), v) for v in getattr(port, "Values", [])]
        try:
            return [(getattr(kv, "Key", kv), getattr(kv, "Value", None)) for kv in port]
        except TypeError:
            return []

    def _is_invested(self, algorithm, ticker: str) -> bool:
        for symbol, holding in self._portfolio_items(algorithm):
            name = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if name == ticker and holding and getattr(holding, "Invested", False):
                return True
        return False

    def Update(self, algorithm, data):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []
        self._last_run_date = today
        as_of = (today - timedelta(days=1)).isoformat()

        all_rows = self._store.get_all_screener_rows(as_of)
        if not all_rows:
            return []

        self._stopped_out = {t: d for t, d in self._stopped_out.items() if d > today}

        def _cooled(ticker: str) -> bool:
            if ticker in self._stopped_out:
                return True
            getter = getattr(self._store, "is_stop_cooled", None)
            return bool(callable(getter) and getter(ticker, today))

        needs_score = bool(self._uses & {"block_new_longs"})
        score_on = self._regime_score_on(algorithm) if needs_score else True
        allow_new_longs = ("block_new_longs" not in self._uses) or score_on

        insights = []
        stop_exits: set[str] = set()

        # --- Stop-loss checks on existing holdings ---------------------------
        for symbol, holding in self._portfolio_items(algorithm):
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if not holding or not getattr(holding, "Invested", False):
                self._entry_prices.pop(ticker, None)
                self._entry_dates.pop(ticker, None)
                continue
            if ticker not in self._entry_prices:
                self._entry_prices[ticker] = float(getattr(holding, "AveragePrice", 0.0))
            if ticker not in self._entry_dates:
                self._entry_dates[ticker] = today
            entry_px = self._entry_prices[ticker]
            current_px = self._security_price(algorithm, symbol)
            if self._stop_loss_pct > 0 and current_px > 0 and entry_px > 0:
                drawdown = (entry_px - current_px) / entry_px
                if drawdown >= self._stop_loss_pct:
                    stop_exits.add(ticker)
                    until = today + timedelta(days=self._stop_cooldown_days)
                    self._stopped_out[ticker] = until
                    recorder = getattr(self._store, "record_stop_out", None)
                    if callable(recorder):
                        recorder(ticker, until)
                    self._entry_prices.pop(ticker, None)
                    self._entry_dates.pop(ticker, None)
                    algorithm.Debug(f"STOP-LOSS {ticker}: drawdown={drawdown:.1%}")

        top_n = self._selection.get("n", self._max_positions)
        if self._gate_combine == "count":
            # Prefer Universe SQL order (ORDER BY + post_where). Re-sort only when
            # the primary hit column is missing from rows (legacy specs).
            hit_col = self._primary_hit_col()
            sample = next(iter(all_rows.values()), {}) or {}
            if hit_col in sample or "screens_hit" in sample:
                selected = [t for t in all_rows.keys() if not _cooled(t)][:top_n]
            else:
                selected = [
                    t for t in self._rank_by_screens_hit(all_rows) if not _cooled(t)
                ][:top_n]
            eligible_rows = {t: all_rows[t] for t in selected if t in all_rows}
            scores = self._compute_composite_score(eligible_rows)
        else:
            scores = self._compute_composite_score(all_rows)
            if not scores:
                return []
            scores = {t: s for t, s in scores.items() if not _cooled(t)}
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            gate_picks = self._union_gate_picks(all_rows)
            if gate_picks is None:
                selected = [t for t, _ in ranked[:top_n]]
            else:
                selected = [t for t, _ in ranked if t in gate_picks]

        if not scores and not stop_exits:
            return []

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

        # --- Flats for stopped-out positions -------------------------------
        period = timedelta(days=self._insight_period_days)
        for ticker in stop_exits:
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            flat = Insight.Price(symbol, period, InsightDirection.Flat)
            try:
                flat.Tag = "alpha_flat"
            except Exception:
                pass
            insights.append(flat)

        # No implicit valve: only block_new_longs use suppresses Ups
        if not allow_new_longs:
            try:
                algorithm.Debug(
                    f"🚫 REGIME OFF {as_of}: block_new_longs — no new entries "
                    f"({len(stop_exits)} stop-exit insights still emitted)"
                )
            except Exception:
                pass
            return insights

        max_score = ranked[0][1] if ranked else 1.0
        min_score = ranked[-1][1] if ranked else 0.0
        score_range = max(max_score - min_score, 1.0)

        # Emit for every shortlisted name that passes setup/triggers/ATR —
        # including names already invested (PCM decides starter vs add).
        # Direction / Magnitude / Weight / Confidence come from row measures.
        for ticker in selected:
            if ticker in stop_exits:
                continue
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not self._securities_has(algorithm, symbol):
                continue
            row = all_rows.get(ticker) or {}
            if not self._setup_passes(row):
                continue
            try:
                atr_pct = float(row.get("atr_14_pct") or 0.0)
            except (TypeError, ValueError):
                atr_pct = 0.0
            if self._max_entry_atr_pct > 0 and atr_pct > self._max_entry_atr_pct:
                continue
            if self._entry_triggers:
                current_px = self._security_price(algorithm, symbol)
                if not evaluate_entry_triggers(
                    row, self._entry_triggers, current_price=current_px
                ):
                    continue
            hit_map = (
                self._count_gate_picks(all_rows)
                if self._gate_combine == "count"
                else {}
            )
            hit_conf = self._screens_hit_confidence(row, ticker, hit_map)
            if hit_conf is not None:
                conf = hit_conf
            else:
                conf = (scores.get(ticker, 0.0) - min_score) / score_range
            entry_px = self._security_price(algorithm, symbol) or float(
                row.get("close") or 0.0
            )
            if not self._is_invested(algorithm, ticker):
                self._entry_prices[ticker] = entry_px
                self._entry_dates[ticker] = today
            direction = self._direction_from_row(row)
            magnitude = self._magnitude_from_row(row)
            weight = self._weight_from_row(row)
            insight_kwargs: dict[str, Any] = {
                "confidence": max(0.1, min(1.0, conf)),
            }
            if magnitude is not None:
                insight_kwargs["magnitude"] = magnitude
            if weight is not None:
                insight_kwargs["weight"] = weight
            try:
                insight = Insight.Price(
                    symbol,
                    period,
                    direction,
                    **insight_kwargs,
                )
            except TypeError:
                # Stub / older Insight.Price without magnitude/weight kwargs
                insight = Insight.Price(
                    symbol,
                    period,
                    direction,
                    confidence=insight_kwargs["confidence"],
                )
                if magnitude is not None and hasattr(insight, "Magnitude"):
                    insight.Magnitude = magnitude
                if weight is not None and hasattr(insight, "Weight"):
                    insight.Weight = weight
            if self._stop_loss and self._stop_loss.get("type") == "atr":
                stop_px = atr_stop_price(
                    float(entry_px or 0.0),
                    row.get("atr_14_pct"),
                    float(self._stop_loss.get("multiplier") or 2.0),
                    max_stop_loss_pct=float(
                        self._stop_loss.get("max_stop_loss_pct")
                        or self._stop_loss_pct
                        or 0.05
                    ),
                )
                if stop_px is not None and hasattr(insight, "StopLossPrice"):
                    insight.StopLossPrice = stop_px
            insights.append(insight)

        return insights
