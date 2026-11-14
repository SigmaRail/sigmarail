"""
QuantConnect framework models that consume ``SigmaRailFrameworkStore`` (universe + metrics from CH).

Equity OHLCV for pricing comes from the **Lean data feed** only (composite / ``ClickHouseDataProvider``).

Used by ``wire_framework_bundle_v1(..., store=...)`` alongside standard LeanFrameworkV1 JSON Types.
Runtime: Lean / QC container (AlgorithmImports).
"""

from __future__ import annotations

from datetime import timedelta
import sys as _sys

# The quantconnect-stubs ``QuantConnect`` package strips site-packages from sys.path to force the C#
# namespace and only restores it on the SUCCESS path. In a non-Lean interpreter (clr absent) the
# ImportError skips the restore and leaves sys.path corrupted for every later import. Snapshot it.
_lean_path = _sys.path[:]

try:
    from AlgorithmImports import *  # noqa: F401,F403 — QC runtime (ScheduledUniverse, Symbol, …)
    from QuantConnect import Market, SecurityType, Symbol
    from QuantConnect.Data.Market import TradeBar

    from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection
    from QuantConnect.Algorithm.Framework.Execution import ExecutionModel
    from QuantConnect.Algorithm.Framework.Portfolio import PortfolioConstructionModel, PortfolioTarget
except ImportError:
    _sys.path[:] = _lean_path  # undo the QuantConnect stub's sys.path strip on a failed import
    class UniverseSelectionModel: pass
    class AlphaModel: pass
    class PortfolioConstructionModel: pass
    class ExecutionModel: pass
    class InsightDirection:
        Up = 1
        Down = 2
        Flat = 0
    class Insight:
        @classmethod
        def Price(cls, symbol, period, direction, confidence=None):
            class _I: pass
            i = _I()
            i.Symbol = symbol
            i.Period = period
            i.Direction = direction
            i.Confidence = confidence
            return i
    class PortfolioTarget:
        def __init__(self, symbol, quantity):
            self.Symbol = symbol
            self.Quantity = quantity
        @classmethod
        def Percent(cls, algorithm, symbol, percent):
            class _PT: pass
            pt = _PT()
            pt.Symbol = symbol
            pt.Quantity = percent
            return pt
    class Symbol:
        def __init__(self, val):
            self.Value = str(val)
        @classmethod
        def Create(cls, ticker, sec_type=None, market=None):
            return cls(ticker)
        def __hash__(self):
            return hash(self.Value)
        def __eq__(self, other):
            return hasattr(other, "Value") and self.Value == other.Value
        def __repr__(self):
            return f"Symbol({self.Value})"
    class SecurityType:
        Equity = 1
    class Market:
        USA = 1

from sigmarail_lab.runtime.sigmarail_screener_price_policy import mtm_price_for_holding
from sigmarail_lab.runtime.signal_evaluation import evaluate_entry_triggers


def _z_scores(values: dict[str, float | None]) -> dict[str, float]:
    """Compute z-scores across a dict of {key: value}. Returns 0.0 for missing/single item."""
    nums = {k: v for k, v in values.items() if v is not None}
    n = len(nums)
    if n < 2:
        return {k: 0.0 for k in values}
    mean = sum(nums.values()) / n
    variance = sum((v - mean) ** 2 for v in nums.values()) / (n - 1)
    std = variance ** 0.5
    if std < 1e-12:
        return {k: 0.0 for k in values}
    return {k: (nums.get(k, mean) - mean) / std for k in values}


class VeraScreenerUniverseSelectionModel(UniverseSelectionModel):
    """
    Universe from preloaded screener data — no coarse CSV subscriptions.
    """

    def __init__(self, store):
        super().__init__()
        self._store = store
        self._algorithm = None
        self._snapshot_date = None
        self._snapshot_symbols = []

    def CreateUniverses(self, algorithm):
        self._algorithm = algorithm
        return [
            ScheduledUniverse(
                algorithm.TimeZone,
                algorithm.DateRules.EveryDay(),
                algorithm.TimeRules.At(0, 0),
                self.SelectSymbols,
                algorithm.UniverseSettings,
            )
        ]

    def SelectSymbols(self, date_time):
        as_of = (date_time.date() - timedelta(days=1)).isoformat()
        if self._snapshot_date == as_of:
            return self._snapshot_symbols
        universe = self._store.get_universe(as_of)
        self._snapshot_date = as_of
        self._snapshot_symbols = [
            Symbol.Create(t, SecurityType.Equity, Market.USA) for t in universe
        ]
        if not universe:
            self._algorithm.Debug(f"No screener rows for {as_of}")
        else:
            self._algorithm.Debug(f"Universe {as_of}: {len(self._snapshot_symbols)} symbols")
        return self._snapshot_symbols


def _portfolio_items(algorithm) -> list[tuple[Any, Any]]:
    port = getattr(algorithm, "Portfolio", None)
    if port is None:
        return []
    if isinstance(port, dict):
        return [(k, v) for k, v in port.items()]
    if hasattr(port, "items") and callable(port.items):
        return port.items()
    if hasattr(port, "Values"):
        return [(getattr(v, "Symbol", None), v) for v in getattr(port, "Values", [])]
    items = []
    try:
        for kv in port:
            k = getattr(kv, "Key", kv)
            v = getattr(kv, "Value", None)
            items.append((k, v))
    except TypeError:
        return []
    return items


def _securities_has(algorithm, symbol) -> bool:
    sec = getattr(algorithm, "Securities", None)
    if sec is None:
        return False
    if hasattr(sec, "ContainsKey"):
        return bool(sec.ContainsKey(symbol))
    val = getattr(symbol, "Value", str(symbol))
    return symbol in sec or val in sec


def _security_price(algorithm, symbol) -> float:
    if not _securities_has(algorithm, symbol):
        return 0.0
    sec = getattr(algorithm, "Securities", None)
    if sec is None:
        return 0.0
    val = getattr(symbol, "Value", str(symbol))
    if symbol in sec:
        return float(getattr(sec[symbol], "Price", 0.0) or 0.0)
    if val in sec:
        return float(getattr(sec[val], "Price", 0.0) or 0.0)
    return 0.0


class VeraScreenerAlphaModel(AlphaModel):
    def __init__(
        self,
        store,
        max_positions=10,
        min_hold_days=5,
        stop_loss_pct=0.08,
        stop_cooldown_days=10,
        circuit_drawdown_threshold=0.10,
        circuit_pause_days=20,
        hold_buffer_rank=30,
        entry_triggers=None,
        stop_loss=None,
        **kwargs,
    ):
        self._store = store
        self._max_positions = max_positions
        self._min_hold_days = min_hold_days
        self._stop_loss_pct = stop_loss_pct
        if stop_loss and stop_loss.get("type") == "fixed_pct" and stop_loss.get("pct"):
            self._stop_loss_pct = float(stop_loss["pct"])
        # C3: opt-in pivot-derived stop. stop_loss={"type":"pivot","buffer_pct":0.0} stops on
        # current_px < entry pivot (entry's VCP pivot_line); defaults to the fixed pct otherwise.
        self._stop_mode = "pivot" if (stop_loss and stop_loss.get("type") == "pivot") else "fixed"
        self._stop_pivot_buffer = float((stop_loss or {}).get("buffer_pct") or 0.0)
        self._stop_pivot_field = str((stop_loss or {}).get("field") or "vcp_pivot_line")
        self._entry_pivots = {}
        self._stop_cooldown_days = stop_cooldown_days
        self._hold_buffer_rank = hold_buffer_rank
        self._entry_triggers = entry_triggers or []
        self._stop_loss = stop_loss
        self._entry_prices = {}
        self._entry_dates = {}
        self._stopped_out = {}
        self._portfolio_peak = None
        self._last_run_date = None
        self._last_status_month = None
        self._circuit_breaker_until = None
        self._circuit_drawdown_threshold = circuit_drawdown_threshold
        self._circuit_pause_days = circuit_pause_days
        self.Name = "VeraScreenerAlphaModel"

    def _is_bull_market(self, algorithm):
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        is_bull = self._store.get_spy_is_bull(as_of)
        if not is_bull:
            algorithm.Debug(
                f"BEAR MARKET {as_of}: market_regime_signals_daily.spy_above200d=0 — no new entries"
            )
        return is_bull

    def _get_settled_portfolio_value(self, algorithm):
        cash = float(getattr(algorithm.Portfolio, "Cash", 0.0))
        position_value = 0.0
        for symbol, holding in _portfolio_items(algorithm):
            if holding and getattr(holding, "Invested", False):
                px = mtm_price_for_holding(algorithm, symbol, holding)
                position_value += abs(float(getattr(holding, "Quantity", 0.0))) * px
        return cash + position_value

    def _check_circuit_breaker(self, algorithm):
        portfolio_value = self._get_settled_portfolio_value(algorithm)
        today = algorithm.Time.date()

        if self._circuit_breaker_until is not None and today > self._circuit_breaker_until:
            self._portfolio_peak = portfolio_value
            self._circuit_breaker_until = None

        if self._portfolio_peak is None or portfolio_value > self._portfolio_peak:
            self._portfolio_peak = portfolio_value

        if self._circuit_breaker_until is not None and today <= self._circuit_breaker_until:
            return True

        if self._portfolio_peak > 0:
            drawdown = (self._portfolio_peak - portfolio_value) / self._portfolio_peak
            month_key = (today.year, today.month)
            if self._last_status_month != month_key:
                self._last_status_month = month_key
                algorithm.Debug(
                    f"PORTFOLIO STATUS {today}: value=${portfolio_value:,.0f} "
                    f"peak=${self._portfolio_peak:,.0f} drawdown={drawdown:.1%}"
                )
            if drawdown >= self._circuit_drawdown_threshold:
                pre_reset_peak = self._portfolio_peak
                self._circuit_breaker_until = today + timedelta(days=self._circuit_pause_days)
                algorithm.Debug(
                    f"CIRCUIT BREAKER: portfolio dropped {drawdown:.1%} from peak "
                    f"(peak=${pre_reset_peak:,.0f} current=${portfolio_value:,.0f}) "
                    f"— pausing entries until {self._circuit_breaker_until}"
                )
                return True

        return False

    def Update(self, algorithm, data):
        today = algorithm.Time.date()
        if self._last_run_date == today:
            return []
        self._last_run_date = today

        as_of = (today - timedelta(days=1)).isoformat()
        scores = self._store.get_universe(as_of)
        if not scores:
            return []

        self._stopped_out = {t: d for t, d in self._stopped_out.items() if d > today}

        # Materialized regime table gate: allocation + clamp. Default / ``screener``: SPY 200d bull flag
        regime_src = (algorithm.GetParameter("regime-source") or "screener").strip().lower()
        if regime_src in ("regime_signals_canonical", "canonical", "regime_gate_v1", "market_regime_signals_daily", "mart"):
            bull_market = self._store.allows_new_longs_from_regime_signals(as_of)
            if not bull_market:
                algorithm.Debug(
                    f"RISK-OFF ({regime_src}) {as_of}: regime gate — no new entries"
                )
        else:
            bull_market = self._is_bull_market(algorithm)

        circuit_open = self._check_circuit_breaker(algorithm)
        exit_mode = (algorithm.GetParameter("exit-mode") or "topn").strip().lower()
        try:
            det_thr = float(algorithm.GetParameter("deterioration-loss-threshold") or "0.02")
        except Exception:
            det_thr = 0.02

        insights = []
        stop_exits = set()
        pivots = self._store.get_pivots(as_of, self._stop_pivot_field) if self._stop_mode == "pivot" else {}

        for symbol, holding in _portfolio_items(algorithm):
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if not holding or not getattr(holding, "Invested", False):
                self._entry_prices.pop(ticker, None)
                self._entry_dates.pop(ticker, None)
                self._entry_pivots.pop(ticker, None)
                continue
            if ticker not in self._entry_prices:
                self._entry_prices[ticker] = float(getattr(holding, "AveragePrice", 0.0))
            if ticker not in self._entry_dates:
                self._entry_dates[ticker] = today
            if self._stop_mode == "pivot" and ticker not in self._entry_pivots and pivots.get(ticker):
                self._entry_pivots[ticker] = pivots[ticker]
            entry_px = self._entry_prices[ticker]
            current_px = _security_price(algorithm, symbol)
            stop_hit = False
            if self._stop_mode == "pivot" and current_px > 0:
                pivot = self._entry_pivots.get(ticker)
                if pivot and current_px < pivot * (1.0 - self._stop_pivot_buffer):
                    stop_hit = True
            if not stop_hit and self._stop_loss_pct > 0 and current_px > 0 and entry_px > 0:
                if (entry_px - current_px) / entry_px >= self._stop_loss_pct:
                    stop_hit = True
            if stop_hit:
                stop_exits.add(ticker)
                cooldown_until = today + timedelta(days=self._stop_cooldown_days)
                self._stopped_out[ticker] = cooldown_until
                self._entry_prices.pop(ticker, None)
                self._entry_dates.pop(ticker, None)
                self._entry_pivots.pop(ticker, None)
                loss = (entry_px - current_px) / entry_px if entry_px > 0 else 0.0
                algorithm.Debug(
                    f"STOP-LOSS {ticker}: entry={entry_px:.2f} current={current_px:.2f} "
                    f"loss={loss:.1%} cooldown until {cooldown_until}"
                )
                insights.append(
                    Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                )

        if circuit_open:
            for symbol, holding in _portfolio_items(algorithm):
                ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
                if holding and getattr(holding, "Invested", False) and ticker not in stop_exits:
                    insights.append(
                        Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                    )
            return insights

        if not bull_market:
            # Regime gate blocks new longs; existing holdings stay on their stops/trailing exits
            return insights

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_n = [
            ticker
            for ticker, _ in ranked
            if ticker not in self._stopped_out and ticker not in stop_exits
        ][: self._max_positions]

        # Buffer set: symbols inside hold_buffer_rank are protected from rank-based churn
        buffer_limit = max(self._max_positions, self._hold_buffer_rank)
        hold_buffer_set = {ticker for ticker, _ in ranked[:buffer_limit]}

        universe_tickers = set(scores.keys())

        # Check existing holdings for buffer exits or deterioration
        for symbol, holding in _portfolio_items(algorithm):
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if not holding or not getattr(holding, "Invested", False) or ticker in stop_exits:
                continue

            entry_date = self._entry_dates.get(ticker, today)
            held_days = (today - entry_date).days

            if held_days >= self._min_hold_days:
                if exit_mode == "topn":
                    if ticker not in hold_buffer_set:
                        self._entry_prices.pop(ticker, None)
                        self._entry_dates.pop(ticker, None)
                        algorithm.Debug(
                            f"BUFFER RANK EXIT {ticker}: dropped out of top {buffer_limit} (held {held_days} days)"
                        )
                        insights.append(
                            Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                        )
                elif exit_mode == "deterioration":
                    if ticker not in universe_tickers:
                        entry_px = self._entry_prices.get(ticker, float(getattr(holding, "AveragePrice", 0.0)))
                        current_px = _security_price(algorithm, symbol)
                        if current_px > 0 and entry_px > 0:
                            loss = (entry_px - current_px) / entry_px
                            if loss >= det_thr:
                                self._entry_prices.pop(ticker, None)
                                self._entry_dates.pop(ticker, None)
                                algorithm.Debug(
                                    f"DETERIORATION EXIT {ticker}: out of universe + loss={loss:.1%} (entry={entry_px:.2f} current={current_px:.2f})"
                                )
                                insights.append(
                                    Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                                )

        max_score = ranked[0][1] if ranked else 1.0
        min_score = ranked[-1][1] if ranked else 0.0
        score_range = max(max_score - min_score, 1.0)

        period = timedelta(days=self._min_hold_days)

        for ticker in top_n:
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not _securities_has(algorithm, symbol):
                continue
            if self._entry_triggers:
                row = self._store.get_screener_row(ticker, as_of)
                current_px = _security_price(algorithm, symbol)
                if not evaluate_entry_triggers(row, self._entry_triggers, current_price=current_px):
                    continue
            raw_score = scores.get(ticker, min_score)
            confidence = (raw_score - min_score) / score_range
            insights.append(
                Insight.Price(symbol, period, InsightDirection.Up, confidence=confidence)
            )

        return insights


class VeraCompositeAlphaModel(AlphaModel):
    """Multi-factor composite alpha: blends z-scores from weighted field columns.

    The ``VeraBase.Universe`` ``select`` must include all columns named in
    ``field_weights``. At each daily Update, the model:
    1. Loads every row from the store.
    2. Computes z-scores for each numeric field across the universe.
    3. Blends scores via weighted average.
    4. Ranks by blended score and emits insights for the top ``max_positions``.
    """

    def __init__(
        self,
        store,
        max_positions=10,
        min_hold_days=5,
        stop_loss_pct=0.08,
        stop_cooldown_days=10,
        circuit_drawdown_threshold=0.10,
        circuit_pause_days=20,
        hold_buffer_rank=30,
        field_weights=None,
        entry_triggers=None,
        stop_loss=None,
        **kwargs,
    ):
        self._store = store
        self._max_positions = max_positions
        self._min_hold_days = min_hold_days
        self._stop_loss_pct = stop_loss_pct
        if stop_loss and stop_loss.get("type") == "fixed_pct" and stop_loss.get("pct"):
            self._stop_loss_pct = float(stop_loss["pct"])
        # C3: opt-in pivot-derived stop. stop_loss={"type":"pivot","buffer_pct":0.0} stops on
        # current_px < entry pivot (entry's VCP pivot_line); defaults to the fixed pct otherwise.
        self._stop_mode = "pivot" if (stop_loss and stop_loss.get("type") == "pivot") else "fixed"
        self._stop_pivot_buffer = float((stop_loss or {}).get("buffer_pct") or 0.0)
        self._stop_pivot_field = str((stop_loss or {}).get("field") or "vcp_pivot_line")
        self._entry_pivots = {}
        self._stop_cooldown_days = stop_cooldown_days
        self._hold_buffer_rank = hold_buffer_rank
        self._entry_triggers = entry_triggers or []
        self._stop_loss = stop_loss
        self._entry_prices = {}
        self._entry_dates = {}
        self._stopped_out = {}
        self._portfolio_peak = None
        self._last_run_date = None
        self._last_status_month = None
        self._circuit_breaker_until = None
        self._circuit_drawdown_threshold = circuit_drawdown_threshold
        self._circuit_pause_days = circuit_pause_days
        self._field_weights = field_weights or {
            "rs_rating": 0.40,
            "valuation_rating": 0.20,
            "mrt_roe": 0.20,
            "perf_1y": 0.20,
        }
        self.Name = "VeraCompositeAlphaModel"

    def _is_bull_market(self, algorithm):
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        is_bull = self._store.get_spy_is_bull(as_of)
        if not is_bull:
            algorithm.Debug(
                f"BEAR MARKET {as_of}: market_regime_signals_daily.spy_above200d=0"
            )
        return is_bull

    def _get_settled_portfolio_value(self, algorithm):
        cash = float(getattr(algorithm.Portfolio, "Cash", 0.0))
        position_value = 0.0
        for symbol, holding in _portfolio_items(algorithm):
            if holding and getattr(holding, "Invested", False):
                px = mtm_price_for_holding(algorithm, symbol, holding)
                position_value += abs(float(getattr(holding, "Quantity", 0.0))) * px
        return cash + position_value

    def _check_circuit_breaker(self, algorithm):
        portfolio_value = self._get_settled_portfolio_value(algorithm)
        today = algorithm.Time.date()
        if self._circuit_breaker_until is not None and today > self._circuit_breaker_until:
            self._portfolio_peak = portfolio_value
            self._circuit_breaker_until = None
        if self._portfolio_peak is None or portfolio_value > self._portfolio_peak:
            self._portfolio_peak = portfolio_value
        if self._circuit_breaker_until is not None and today <= self._circuit_breaker_until:
            return True
        if self._portfolio_peak > 0:
            drawdown = (self._portfolio_peak - portfolio_value) / self._portfolio_peak
            if drawdown >= self._circuit_drawdown_threshold:
                self._circuit_breaker_until = today + timedelta(days=self._circuit_pause_days)
                algorithm.Debug(
                    f"CIRCUIT BREAKER: drawdown {drawdown:.1%} — pause until "
                    f"{self._circuit_breaker_until}"
                )
                return True
        return False

    # COMPOSITE_ALPHA_MID_1

    def _compute_composite_score(self, rows):
        """Blend z-scores from weighted field columns into a single score per ticker."""
        tickers = list(rows.keys())
        if not tickers:
            return {}
        field_values = {f: {} for f in self._field_weights}
        for ticker in tickers:
            row = rows[ticker]
            for field in self._field_weights:
                field_values[field][ticker] = row.get(field)
        composite = {}
        for ticker in tickers:
            score = 0.0
            for field, weight in self._field_weights.items():
                zs = _z_scores(field_values[field])
                score += zs.get(ticker, 0.0) * weight
            composite[ticker] = score
        return composite

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
        regime_src = (algorithm.GetParameter("regime-source") or "screener").strip().lower()
        if regime_src in ("regime_signals_canonical", "canonical", "regime_gate_v1", "market_regime_signals_daily", "mart"):
            bull_market = self._store.allows_new_longs_from_regime_signals(as_of)
        else:
            bull_market = self._is_bull_market(algorithm)
        circuit_open = self._check_circuit_breaker(algorithm)
        exit_mode = (algorithm.GetParameter("exit-mode") or "topn").strip().lower()
        try:
            det_thr = float(algorithm.GetParameter("deterioration-loss-threshold") or "0.02")
        except Exception:
            det_thr = 0.02
        insights = []
        stop_exits = set()
        pivots = self._store.get_pivots(as_of, self._stop_pivot_field) if self._stop_mode == "pivot" else {}
        for symbol, holding in _portfolio_items(algorithm):
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if not holding or not getattr(holding, "Invested", False):
                self._entry_prices.pop(ticker, None)
                self._entry_dates.pop(ticker, None)
                self._entry_pivots.pop(ticker, None)
                continue
            if ticker not in self._entry_prices:
                self._entry_prices[ticker] = float(getattr(holding, "AveragePrice", 0.0))
            if ticker not in self._entry_dates:
                self._entry_dates[ticker] = today
            if self._stop_mode == "pivot" and ticker not in self._entry_pivots and pivots.get(ticker):
                self._entry_pivots[ticker] = pivots[ticker]
            entry_px = self._entry_prices[ticker]
            current_px = _security_price(algorithm, symbol)
            stop_hit = False
            if self._stop_mode == "pivot" and current_px > 0:
                pivot = self._entry_pivots.get(ticker)
                if pivot and current_px < pivot * (1.0 - self._stop_pivot_buffer):
                    stop_hit = True
            if not stop_hit and self._stop_loss_pct > 0 and current_px > 0 and entry_px > 0:
                if (entry_px - current_px) / entry_px >= self._stop_loss_pct:
                    stop_hit = True
            if stop_hit:
                stop_exits.add(ticker)
                cooldown = today + timedelta(days=self._stop_cooldown_days)
                self._stopped_out[ticker] = cooldown
                self._entry_prices.pop(ticker, None)
                self._entry_dates.pop(ticker, None)
                self._entry_pivots.pop(ticker, None)
                loss = (entry_px - current_px) / entry_px if entry_px > 0 else 0.0
                algorithm.Debug(
                    f"STOP-LOSS {ticker}: drawdown={loss:.1%} cooldown until {cooldown}"
                )
        scores = self._compute_composite_score(all_rows)
        if not scores:
            return []
        scores = {t: s for t, s in scores.items() if t not in self._stopped_out}
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_n = [t for t, _ in ranked[: self._max_positions]]
        if not bull_market or circuit_open:
            for ticker in stop_exits:
                s = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
                insights.append(Insight.Price(s, timedelta(days=1), InsightDirection.Flat))
            return insights
        buffer_limit = max(self._max_positions, self._hold_buffer_rank)
        hold_buffer_set = {t for t, _ in ranked[:buffer_limit]}
        universe_tickers = set(scores.keys())
        for symbol, holding in _portfolio_items(algorithm):
            ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
            if not holding or not getattr(holding, "Invested", False) or ticker in stop_exits:
                continue
            entry_date = self._entry_dates.get(ticker, today)
            held_days = (today - entry_date).days
            if held_days >= self._min_hold_days:
                if exit_mode == "topn" and ticker not in hold_buffer_set:
                    self._entry_prices.pop(ticker, None)
                    self._entry_dates.pop(ticker, None)
                    e = Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                    insights.append(e)
                elif exit_mode == "deterioration" and ticker not in universe_tickers:
                    ep = self._entry_prices.get(ticker, float(getattr(holding, "AveragePrice", 0.0)))
                    cp = _security_price(algorithm, symbol)
                    if cp > 0 and ep > 0 and (ep - cp) / ep >= det_thr:
                        self._entry_prices.pop(ticker, None)
                        self._entry_dates.pop(ticker, None)
                        e = Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat)
                        insights.append(e)
        max_score = ranked[0][1] if ranked else 1.0
        min_score = ranked[-1][1] if ranked else 0.0
        score_range = max(max_score - min_score, 1.0)
        period = timedelta(days=self._min_hold_days)
        for ticker in top_n:
            symbol = Symbol.Create(ticker, SecurityType.Equity, Market.USA)
            if not _securities_has(algorithm, symbol):
                continue
            if self._entry_triggers:
                row = all_rows.get(ticker) or {}
                current_px = _security_price(algorithm, symbol)
                if not evaluate_entry_triggers(row, self._entry_triggers, current_price=current_px):
                    continue
            raw_score = scores.get(ticker, min_score)
            confidence = (raw_score - min_score) / score_range
            e = Insight.Price(symbol, period, InsightDirection.Up, confidence=confidence)
            insights.append(e)
        return insights


class VeraScreenerPortfolioConstructionModel(PortfolioConstructionModel):
    def __init__(
        self,
        store,
        max_positions=10,
        max_weight=0.095,
        min_weight=0.03,
        target_atr_risk=0.003,
        uses=None,
        hold_policy="retain_if_invested",
        max_total_exposure=0.95,
        exit_when_no_bars=False,
        **kwargs,
    ):
        self._store = store
        self._max_positions = max_positions
        self._max_weight = max_weight
        self._min_weight = min_weight
        self._target_atr_risk = target_atr_risk
        self._uses = {str(u) for u in (uses or [])}
        self._hold_policy = hold_policy or "retain_if_invested"
        self._max_total_exposure = float(max_total_exposure)
        self._exit_when_no_bars = bool(exit_when_no_bars)

    def _scale_fraction(self, as_of: str) -> float:
        """Allocation scale from regime (thermostat). Never forces skip-all alone."""
        if "scale_exposure" not in self._uses:
            return 1.0
        if hasattr(self._store, "get_allocation_fraction"):
            frac = self._store.get_allocation_fraction(as_of)
            if frac is not None:
                return max(0.0, min(1.0, float(frac)))
        if hasattr(self._store, "allows_new_longs_from_regime_signals"):
            return 1.0 if self._store.allows_new_longs_from_regime_signals(as_of) else 0.0
        return 1.0

    def CreateTargets(self, algorithm, insights):
        up_insights = [i for i in insights if i.Direction == InsightDirection.Up]
        flat_insights = [i for i in insights if i.Direction == InsightDirection.Flat]

        targets = []
        as_of = (algorithm.Time.date() - timedelta(days=1)).isoformat()
        atrs = self._store.get_atrs(as_of) if self._store else {}
        scale = self._scale_fraction(as_of)
        max_total_exposure = self._max_total_exposure * scale if scale > 0 else self._max_total_exposure
        # Thermostat: scale slots/weights; fraction 0 still retains invested unless Flat
        scaled_max_positions = max(1, int(round(self._max_positions * max(scale, 0.01)))) if scale > 0 else self._max_positions
        if scale <= 0:
            # Scale to zero: do not open new slots; keep retain policy for invested
            scaled_max_positions = len(
                [
                    1
                    for _, h in _portfolio_items(algorithm)
                    if h and getattr(h, "Invested", False)
                ]
            )

        # 1. Process explicit exits (Flat insights)
        flat_symbols = set()
        for insight in flat_insights:
            flat_symbols.add(insight.Symbol)
            targets.append(PortfolioTarget(insight.Symbol, 0))

        # exit_when_no_bars: liquidate invested names missing from screener/bars
        if self._exit_when_no_bars and self._store is not None:
            universe = set()
            if hasattr(self._store, "get_universe"):
                universe = set(self._store.get_universe(as_of) or {})
            for symbol, holding in _portfolio_items(algorithm):
                if not holding or not getattr(holding, "Invested", False):
                    continue
                if symbol in flat_symbols:
                    continue
                ticker = symbol.Value if hasattr(symbol, "Value") else str(symbol)
                if ticker not in universe and ticker not in atrs:
                    flat_symbols.add(symbol)
                    targets.append(PortfolioTarget(symbol, 0))

        # 2. Retain existing invested holdings (do NOT sell just because not in new candidate list)
        invested_symbols = {
            symbol: holding
            for symbol, holding in _portfolio_items(algorithm)
            if holding and getattr(holding, "Invested", False) and symbol not in flat_symbols
        }

        # 3. Size new positions up to max_positions and max_total_exposure
        current_invested_count = len(invested_symbols)
        available_slots = max(0, scaled_max_positions - current_invested_count)

        new_up_insights = [
            i for i in up_insights if i.Symbol not in invested_symbols
        ]
        new_up_insights.sort(key=lambda i: i.Confidence or 0.0, reverse=True)
        to_enter = new_up_insights[:available_slots]

        total_portfolio_value = max(1.0, float(getattr(algorithm.Portfolio, "TotalPortfolioValue", 1.0)))
        total_weight = sum(
            float(getattr(h, "HoldingsValue", 0.0)) / total_portfolio_value
            for h in invested_symbols.values()
        )

        weight_scale = scale if scale > 0 else 0.0
        for insight in to_enter:
            if weight_scale <= 0:
                break
            ticker = insight.Symbol.Value if hasattr(insight.Symbol, "Value") else str(insight.Symbol)
            atr_pct = atrs.get(ticker)
            if atr_pct and atr_pct > 0:
                weight = self._target_atr_risk / atr_pct
            else:
                weight = (1.0 / self._max_positions) if self._max_positions > 0 else self._min_weight
            weight = max(self._min_weight, min(self._max_weight, weight)) * weight_scale
            if total_weight + weight > max_total_exposure:
                weight = max(0.0, max_total_exposure - total_weight)
            if weight < self._min_weight * max(weight_scale, 0.01):
                break
            total_weight += weight
            t = PortfolioTarget.Percent(algorithm, insight.Symbol, weight)
            if t is not None:
                targets.append(t)

        return targets

    def OnSecuritiesChanged(self, algorithm, changes):
        pass


def submit_session_order(
    algorithm,
    fill_session: str,
    symbol,
    delta: int,
    tag: str = "",
    limit_price: float | None = None,
) -> None:
    """Submit MOO/MOC using Python Lean snake_case, with PascalCase fallback.

    QCAlgorithm.Python exposes ``market_on_open_order`` / ``market_on_close_order``.
    ``MarketOnOpen`` is a C# name and is missing on the Python wrapper.
    Optional ``tag`` is passed when the Lean wrapper accepts a third argument.

    Pyramid adds (``tranche1_add``): use a **buy stop** at ``limit_price`` (prior close
    band). A buy *limit* would still fill on a gap-down (limit = max price willing to pay);
    a buy *stop* only fills if price trades back near the confirmation close.
    """
    tag = str(tag or "")
    if limit_price is not None and float(limit_price) > 0 and int(delta) > 0:
        # Buy-stop ~3% below prior close: skips crash gaps, allows normal open noise.
        stop_px = float(limit_price) * 0.97
        for name in ("stop_market_order", "StopMarketOrder"):
            fn = getattr(algorithm, name, None)
            if not callable(fn):
                continue
            if tag:
                try:
                    fn(symbol, int(delta), stop_px, tag)
                    return
                except TypeError:
                    pass
            fn(symbol, int(delta), stop_px)
            return
        # Fallback: skip the add rather than MOO into a potential gap.
        dbg = getattr(algorithm, "Debug", None)
        if callable(dbg):
            dbg(f"skip tranche add {getattr(symbol, 'Value', symbol)}: no stop_market_order")
        return

    session = str(fill_session or "moo").strip().lower()
    if session == "moc":
        names = ("market_on_close_order", "MarketOnClose")
    else:
        names = ("market_on_open_order", "MarketOnOpen")
    for name in names:
        fn = getattr(algorithm, name, None)
        if not callable(fn):
            continue
        if tag:
            try:
                fn(symbol, delta, tag)
                return
            except TypeError:
                pass
        fn(symbol, delta)
        return
    raise AttributeError(f"algorithm has none of {names}")


class VeraScreenerExecutionModel(ExecutionModel):
    def __init__(self, store, fill_session: str = "moo", **_extra):
        self._store = store
        self._fill_session = str(fill_session or "moo").strip().lower()
        if self._fill_session not in ("moo", "moc"):
            self._fill_session = "moo"
        # Per-symbol last-submitted target quantity — idempotence across the two
        # daily invocations (09:00 scheduled store-backed pass + the framework's
        # per-bar ManageRisk→Execute). A date-scoped gate would silently drop
        # same-day risk overrides that differ from the morning's targets
        # (e.g. a tranche trim fired on the close bar).
        self._submitted_targets: dict = {}

    def _resolve_tag(self, algorithm, sym, target) -> str:
        tag = str(getattr(target, "Tag", None) or "")
        if tag:
            return tag
        tags = getattr(algorithm, "_vera_order_tags", None) or {}
        return str(tags.get(str(getattr(sym, "Value", sym)), "") or "")

    def _submit(self, algorithm, sym, delta: int, tag: str = "") -> None:
        ticker = getattr(sym, "Value", sym)
        limit_price = None
        # Scale-ins: buy-stop near prior close so crash gaps do not fill.
        if tag == "tranche1_add" and delta > 0:
            try:
                sec = algorithm.Securities[sym]
                limit_price = float(getattr(sec, "Price", 0.0) or 0.0) or None
            except Exception:
                limit_price = None
            algorithm.Debug(
                f"EXEC ADD {ticker}: delta={delta} buy_stop_ref={limit_price}"
            )
        try:
            submit_session_order(
                algorithm,
                self._fill_session,
                sym,
                delta,
                tag=tag,
                limit_price=limit_price,
            )
        except Exception as exc:
            algorithm.Debug(
                f"VeraScreenerExecutionModel: submit failed {ticker} delta={delta}: {exc}"
            )

    def Execute(self, algorithm, targets):
        valid_targets = [t for t in targets if t is not None]

        exit_targets = [t for t in valid_targets if t.Quantity == 0]
        entry_targets = [t for t in valid_targets if t.Quantity != 0]

        for t in exit_targets:
            sym = t.Symbol
            if not algorithm.Securities.ContainsKey(sym):
                continue
            key = str(getattr(sym, "Value", sym))
            if self._submitted_targets.get(key) == 0:
                continue  # flatten already ordered; don't re-submit while pending
            holding = algorithm.Portfolio[sym]
            if holding and getattr(holding, "Invested", False):
                qty = int(getattr(holding, "Quantity", 0) or 0)
                if qty != 0:
                    self._submit(algorithm, sym, -qty, tag=self._resolve_tag(algorithm, sym, t))
                    self._submitted_targets[key] = 0

        for t in entry_targets:
            sym = t.Symbol
            if not algorithm.Securities.ContainsKey(sym):
                continue
            key = str(getattr(sym, "Value", sym))
            target_qty = int(t.Quantity)
            if self._submitted_targets.get(key) == target_qty:
                continue  # identical target already ordered — idempotent pass
            current_qty = int(algorithm.Portfolio[sym].Quantity)
            delta = target_qty - current_qty
            if abs(delta) >= 1:
                self._submit(algorithm, sym, delta, tag=self._resolve_tag(algorithm, sym, t))
                self._submitted_targets[key] = target_qty

        # Clear one-shot tags after the session submit pass.
        if hasattr(algorithm, "_vera_order_tags"):
            algorithm._vera_order_tags = {}
