# region imports
from AlgorithmImports import *
# endregion
import os
from datetime import date as date_cls
from datetime import timedelta
import json

from clr import AddReference

AddReference("QuantConnect.Common")
AddReference("QuantConnect.Algorithm")

from QuantConnect import Market, Resolution, DataNormalizationMode, SecurityType, Symbol
from QuantConnect.Algorithm import QCAlgorithm

from sigmarail_lab.ir.clickhouse_runner_bundle import (
    framework_bundle_for_clickhouse_pipeline,
    framework_bundle_for_graph_policy,
)
from sigmarail_lab.ir.graph_policy_runtime import is_policy_graph, parse_graph
from sigmarail_lab.ir.graph_runtime import graph_subscription_tickers
from sigmarail_lab.ir.evaluation_coalesce import coalesce_research_evaluation
from sigmarail_lab.ir.resolver import resolve_sigmarail_lab
from sigmarail_lab.ir.sigmarail_lab_v1_bind import VeraLabV1BindingProxy
from sigmarail_lab.ir.sigmarail_screener_framework_types import STORE_BACKED_EXECUTION_TYPES
from sigmarail_lab.runtime.lean_framework_interpreter import wire_framework_bundle_v1
from sigmarail_lab.runtime.bar_requirements import (
    collect_bar_requirements,
    ensure_select_columns,
    required_columns_for,
)
from sigmarail_lab.runtime.provider_bridge import prehydrate_tickers
from sigmarail_lab.runtime.live_snapshot_writer import insert_live_snapshot_from_algorithm
from sigmarail_lab.runtime.sigmarail_framework_store import SigmaRailFrameworkStore
from sigmarail_lab.runtime.sigmarail_screener_price_policy import warn_missing_lean_prices
from sigmarail_lab.runtime.store_backed_loop import (
    fill_session_minutes_before,
    fill_session_time_rule_kind,
    run_store_backed_rebalance,
)


def _backtest_security_initializer(sec):
    """Module-level initializer (LEAN ToAction requires exactly one parameter)."""
    sec.SetLeverage(1.0)
    sec.SetDataNormalizationMode(DataNormalizationMode.Raw)


class ClickHouseUniverseAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Allow SIGMARAIL_STRATEGY_ID to be passed as Lean parameter (sigmarail-strategy-id)
        # Fallback to environment variable for docker-based runs
        sigmarail_lab_id = self.GetParameter("sigmarail-strategy-id")
        if sigmarail_lab_id:
            os.environ["SIGMARAIL_STRATEGY_ID"] = sigmarail_lab_id

        try:
            _resolved = resolve_sigmarail_lab(self)
        except Exception as exc:
            self.Quit(f"SigmaRail strategy resolution failed: {exc}")
            return

        _spec = _resolved.spec
        uspec = _spec.effective_universe()
        if uspec is None:
            self.Quit(
                "VeraLab graph mode: unsupported graph shape "
                "(need select→filter on daily_screener with preset or criteria)."
            )
            return
        if not isinstance(uspec, dict):
            self.Quit(
                "Strategy Universe must be universe_query_v1 JSON (version == 1, select[])."
            )
            return
        lf = _spec.effective_lean_framework()
        param_map = {}
        if hasattr(lf, "lean_set_parameter_map"):
            param_map = lf.lean_set_parameter_map() or {}
        vb = getattr(_spec, "vera_base", None)
        evaluation = getattr(vb, "evaluation", None) if vb is not None else None
        start_date, end_date, initial_cash, benchmark = coalesce_research_evaluation(
            get_parameter=self.GetParameter,
            parameter_map=param_map,
            evaluation=evaluation,
        )
        self._accounting_period = {"start": start_date, "end": end_date}
        self._benchmark_ticker = benchmark

        s = [int(x) for x in start_date.split("-")]
        e = [int(x) for x in end_date.split("-")]
        self.SetStartDate(s[0], s[1], s[2])
        self.SetEndDate(e[0], e[1], e[2])
        self.SetCash(initial_cash)
        self._initial_cash = initial_cash
        self._accounting_fills = []
        self._accounting_corporate_actions = []
        self._accounting_snapshots = []
        self._accounting_slices_seen = 0
        self._accounting_start = self._accounting_state()
        if (os.environ.get("SIGMARAIL_ETF_COMPARE") or "").strip() in ("1", "true", "yes"):
            self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Cash)

        for param_key, param_value in lf.lean_set_parameter_map().items():
            # Some LEAN builds don't expose SetParameter on QCAlgorithm at runtime.
            if hasattr(self, "SetParameter"):
                self.SetParameter(param_key, param_value)

        # Brokerage model: not set here — use QC project / live brokerage link / LEAN job / lean.json.

        if not self.LiveMode:
            self.SetSecurityInitializer(_backtest_security_initializer)

        # Tickers that must be subscribed regardless of screener score (e.g. ETFs for sector models).
        if isinstance(uspec, dict):
            self._always_include_tickers = set(uspec.get("always_include_tickers") or [])
        else:
            self._always_include_tickers = set()

        # Resolve the framework bundle first so its declared bar requirements can
        # inform the universe select (e.g. atr_14_pct for the swing risk model).
        _attach_policy_graph = False
        is_graph = getattr(_spec, "is_graph_mode", None)
        root = getattr(_spec, "root", None)
        fb_method = getattr(_spec, "framework_bundle", None)
        if callable(is_graph) and is_graph() and root is not None:
            fb = framework_bundle_for_graph_policy(_spec.effective_lean_framework())
            _attach_policy_graph = True
            # Parse the graph dict into GraphStep model
            from sigmarail_lab.ir.graph_policy_runtime import parse_graph
            root = parse_graph(root)
        elif fb_method is not None:
            fb = fb_method()
        else:
            fb = framework_bundle_for_clickhouse_pipeline(_spec.effective_lean_framework())

        if isinstance(uspec, dict):
            uspec = ensure_select_columns(uspec, required_columns_for(fb))

        self._store = SigmaRailFrameworkStore(uspec)
        self._store.set_benchmark_ticker(benchmark)
        if _attach_policy_graph:
            self._store.attach_policy_graph(root)
        # Attach VeraBase facet for data_sources (graph policy + store-backed catalog)
        if hasattr(_spec, "vera_base") and getattr(_spec, "vera_base", None):
            self._store.attach_vera_base(_spec.vera_base)
            # C-REGIME-POLICY-V1: attach score evaluator from DataSources.regime.score
            vb = _spec.vera_base
            for ds in getattr(vb, "data_sources", None) or []:
                name = getattr(ds, "name", None) or (ds.get("name") if isinstance(ds, dict) else None)
                if name != "regime":
                    continue
                score = getattr(ds, "score", None) or (ds.get("score") if isinstance(ds, dict) else None)
                if score:
                    self._store.attach_regime_gate(score)
                break
        elif hasattr(_spec, "_bound") and getattr(_spec._bound, "_vera_base", None):
            self._store.attach_vera_base(_spec._bound._vera_base)
        self._store.bind(self, regime_source=getattr(lf.regime, "source", None))
        self._deployment_id = (
            (self.GetParameter("deployment-id") or os.environ.get("DEPLOYMENT_ID") or "")
            .strip()
        )
        self._sigmarail_lab_id = (
            (self.GetParameter("sigmarail-strategy-id") or os.environ.get("SIGMARAIL_STRATEGY_ID") or "")
            .strip()
        )

        if self.LiveMode:
            today = date_cls.today()
            self._store.load(today, today)
        else:
            start = date_cls(self.StartDate.year, self.StartDate.month, self.StartDate.day)
            end = date_cls(self.EndDate.year, self.EndDate.month, self.EndDate.day)
            # Pad so calendar D-1 / prior-session as-of on week 1 has regime rows.
            self._store.load(start - timedelta(days=14), end)

        _bar_req = collect_bar_requirements(fb)
        self._bar_req = _bar_req

        # Bulk ClickHouse bar load for the full backtest range (chunked IN lists).
        # Must run before AddEquity so Fetch is a cache hit of the full-range zip.
        hydrate_names = set(self._always_include_tickers) | {"SPY", benchmark}
        if self._store is not None:
            hydrate_names |= set(self._store.dates_by_ticker().keys())
        if fb.portfolio_construction and (fb.portfolio_construction.parameters or {}).get("enable_surrogates"):
            try:
                from sigmarail_lab.runtime.surrogate_router import SurrogateRouter
                _router = SurrogateRouter()
                for _t in list(hydrate_names):
                    _trade_sym, _ = _router.resolve_trade_symbol(None, _t)
                    _s = str(getattr(_trade_sym, "Value", _trade_sym))
                    if _s != _t:
                        hydrate_names.add(_s)
            except Exception as _ex:
                self.Debug(f"Warning: could not resolve surrogate tickers for prehydrate: {_ex}")
        n_hydrate = prehydrate_tickers(hydrate_names)
        self.Debug(f"INIT: bulk bar hydrate tickers={n_hydrate}")

        self.Debug(
            f"INIT: spec={type(_spec).__name__} alpha_type={fb.alpha.type}"
        )

        wired = wire_framework_bundle_v1(self, fb, store=self._store)
        self.Debug(f"INIT: wired alpha={type(wired.alpha).__name__}")
        self._universe_model = wired.universe_selection
        self._alpha_model = wired.alpha
        self._pcm = wired.portfolio_construction
        self._exec_model = wired.execution
        self._risk_model = wired.risk_management

        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw

        # Keep SPY as the schedule anchor. Other benchmark equity subscriptions
        # may support framework references, but the benchmark callback below is
        # sourced from Vera's fully adjusted series (or explicit constant cash).
        self._anchor = self.AddEquity("SPY", Resolution.Daily).Symbol
        bench_sym = self._anchor
        if benchmark not in ("SPY", "CASH"):
            bench_eq = self.AddEquity(benchmark, Resolution.Daily)
            bench_eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
            bench_sym = bench_eq.Symbol

        exec_type = (fb.execution.type or "").strip()
        self._use_store_manual_rebalance = exec_type in STORE_BACKED_EXECUTION_TYPES
        exec_params = dict(fb.execution.parameters or {})
        self._fill_session = str(exec_params.get("fill_session") or "moo").strip().lower()

        if self._use_store_manual_rebalance:
            self._symbols_added = {"SPY", benchmark} - {"CASH"}
            self.SetBenchmark(lambda dt: self._store.get_benchmark_price(dt.date().isoformat()))
            self._preload_equity_subscriptions(_spec)
            rule_kind = fill_session_time_rule_kind(self._fill_session)
            minutes = fill_session_minutes_before(self._fill_session)
            if rule_kind == "before_market_close":
                time_rule = self.TimeRules.BeforeMarketClose(self._anchor, minutes)
            else:
                time_rule = self.TimeRules.BeforeMarketOpen(self._anchor, minutes)
            self.Schedule.On(
                self.DateRules.EveryDay(self._anchor),
                time_rule,
                self._daily_rebalance,
            )
            if not self.LiveMode:
                self._day_snapshots = []
                self.Schedule.On(
                    self.DateRules.EveryDay(self._anchor),
                    self.TimeRules.AfterMarketClose(self._anchor, 5),
                    self._record_backtest_day_snapshot,
                )
        else:
            self.SetBenchmark(lambda dt: self._store.get_benchmark_price(dt.date().isoformat()))

        if self.LiveMode:
            self.Schedule.On(
                self.DateRules.EveryDay(self._anchor),
                self.TimeRules.BeforeMarketClose(self._anchor, 15),
                self._live_reload_today,
            )
            self.Schedule.On(
                self.DateRules.EveryDay(self._anchor),
                self.TimeRules.AfterMarketClose(self._anchor, 30),
                self._live_eod_snapshot,
            )

    def _live_reload_today(self):
        today = self.Time.date()
        self._store.reload_today()
        self.Debug(f"live: reload_today as_of={today.isoformat()}")

    def _live_eod_snapshot(self):
        if not self._deployment_id:
            return
        ir_id = self._sigmarail_lab_id
        try:
            insert_live_snapshot_from_algorithm(
                self,
                deployment_id=self._deployment_id,
                as_of=self.Time.date(),
                source="eod_hook",
                ir_id=ir_id,
            )
        except Exception as exc:
            self.Debug(f"live_snapshot failed: {exc}")

    def _preload_equity_subscriptions(self, spec) -> None:
        """Subscribe policy/universe tickers at init so Lean has bars before first rebalance."""
        tickers = set(self._always_include_tickers) | {"SPY", getattr(self, "_benchmark_ticker", "SPY")}
        is_graph = getattr(spec, "is_graph_mode", None)
        root = getattr(spec, "root", None)
        if callable(is_graph) and is_graph() and root is not None:
            tickers |= graph_subscription_tickers(root)
        if self._store is not None:
            tickers |= set(self._store.dates_by_ticker().keys())
        enable_surr = False
        pcm = getattr(self, "_pcm", None)
        if pcm is not None:
            enable_surr = getattr(pcm, "_enable_surrogates", False)
        if not enable_surr and spec is not None:
            try:
                lf = spec.effective_lean_framework()
                enable_surr = bool((lf.portfolio_construction.parameters or {}).get("enable_surrogates"))
            except Exception:
                pass
        if enable_surr:
            try:
                from sigmarail_lab.runtime.surrogate_router import SurrogateRouter
                _router = SurrogateRouter()
                for _t in list(tickers):
                    _trade_sym, _ = _router.resolve_trade_symbol(None, _t)
                    _s = str(getattr(_trade_sym, "Value", _trade_sym))
                    if _s != _t:
                        tickers.add(_s)
            except Exception as _ex:
                self.Debug(f"Warning: could not resolve surrogate tickers for pre-subscription: {_ex}")

        # Only warm up when the framework bundle declares a real bar-warmup need
        # (e.g. alpha models that build rolling windows from live Lean bars).
        # Store-backed strategies (all screener models) compute their lookbacks
        # from ClickHouse, so Lean warmup adds nothing — and the engine's
        # warmup→normal enumerator handoff does not deliver post-warmup daily
        # bars for ClickHouse-provider-fed securities (bars stop after warmup,
        # so the scheduled rebalance never fires and Total Orders stays 0).
        # When no bar warmup is required we subscribe at t0 and the data feed
        # serves the full range directly.
        bar_req = getattr(self, "_bar_req", None)
        needs_bar_warmup = bar_req is not None and (
            bar_req.warmup_bars > 0 or bar_req.needs_live_bars
        )
        if needs_bar_warmup and not self.LiveMode:
            warmup_days = max(bar_req.warmup_bars, 5)
            self.SetWarmup(timedelta(days=warmup_days), Resolution.Daily)
            self.Debug(
                f"INIT: bar warmup enabled ({warmup_days}d) for models needing live bars"
            )
        for ticker in sorted(tickers):
            if ticker in self._symbols_added:
                continue
            equity = self.AddEquity(ticker, Resolution.Daily)
            equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
            self._symbols_added.add(ticker)
            self.Debug(f"INIT: pre-subscribed {ticker}")

    def _daily_rebalance(self):
        as_of_date = self.Time.date()
        as_of = (as_of_date - timedelta(days=1)).isoformat()

        universe = self._store.get_universe(as_of)
        for ticker in list(universe) + [t for t in self._always_include_tickers if t not in universe]:
            if ticker not in self._symbols_added:
                equity = self.AddEquity(ticker, Resolution.Daily)
                equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
                self._symbols_added.add(ticker)

        all_tickers = set(universe.keys()) | {kv.Key.Value for kv in self.Portfolio if kv.Value.Invested}
        warn_missing_lean_prices(
            self,
            all_tickers,
            resolve_symbol=lambda t: Symbol.Create(t, SecurityType.Equity, Market.USA),
        )

        run_store_backed_rebalance(
            self,
            self._alpha_model,
            self._pcm,
            getattr(self, "_risk_model", None),
            self._exec_model,
        )

    def _record_backtest_day_snapshot(self):
        as_of = (self.Time.date() - timedelta(days=1)).isoformat()
        universe = self._store.get_universe(as_of)
        candidates = []
        for ticker, row in list(universe.items())[:100]:
            item = {"ticker": ticker}
            if isinstance(row, dict):
                for key in ("overall_score", "minervini_score", "technical_rating", "close"):
                    if key in row:
                        item[key] = row[key]
            candidates.append(item)
        holdings = []
        for kv in self.Portfolio:
            if not kv.Value.Invested:
                continue
            holdings.append(
                {
                    "ticker": kv.Key.Value,
                    "quantity": float(kv.Value.Quantity),
                    "price": float(kv.Value.Price),
                    "value": float(kv.Value.HoldingsValue),
                }
            )
        self._day_snapshots.append(
            {
                "date": self.Time.date().isoformat(),
                "observed_at": str(self.Time),
                "as_of": as_of,
                "cash": float(self.Portfolio.Cash),
                "equity": float(self.Portfolio.TotalPortfolioValue),
                "holdings": holdings,
                "candidates": candidates,
            }
        )
        accounting_snapshot = self._accounting_state()
        accounting_snapshot["date"] = self.Time.date().isoformat()
        accounting_snapshot["as_of"] = as_of
        self._accounting_snapshots.append(accounting_snapshot)

    def _accounting_state(self):
        """Capture account-level balances and marks without writing to ClickHouse."""
        holdings = []
        for kv in self.Portfolio:
            holding = kv.Value
            if not holding.Invested:
                continue
            holdings.append(
                {
                    "ticker": kv.Key.Value,
                    "quantity": str(holding.Quantity),
                    "price": str(holding.Price),
                    "value": str(holding.HoldingsValue),
                }
            )
        return {
            "observed_at": str(self.Time),
            "cash": str(self.Portfolio.Cash),
            "equity": str(self.Portfolio.TotalPortfolioValue),
            "holdings": holdings,
        }

    def OnOrderEvent(self, order_event):
        """Record each fill with its fee and the account state immediately after it."""
        if self.LiveMode:
            return
        try:
            fill_quantity = float(order_event.FillQuantity)
            if not fill_quantity:
                return
            fee_value = getattr(getattr(order_event, "OrderFee", None), "Value", None)
            try:
                order = self.Transactions.GetOrderById(int(order_event.OrderId))
            except Exception:
                order = None
            self._accounting_fills.append(
                {
                    "order_id": int(order_event.OrderId),
                    "order_event_id": int(getattr(order_event, "OrderEventId", 0)),
                    "symbol": str(order_event.Symbol.Value),
                    "order_quantity": str(order.Quantity) if order is not None else None,
                    "fill_quantity": str(order_event.FillQuantity),
                    "fill_price": str(order_event.FillPrice),
                    "fee_amount": str(fee_value.Amount) if fee_value is not None else None,
                    "fee_currency": str(fee_value.Currency) if fee_value is not None else None,
                    "status": str(order_event.Status),
                    "event_time": str(getattr(order_event, "UtcTime", self.Time)),
                    "account_after_fill": self._accounting_state(),
                }
            )
        except Exception as exc:
            self.Debug(f"accounting fill capture failed ({type(exc).__name__})")

    def OnData(self, data):
        """Capture dividend and split evidence delivered by LEAN's data feed."""
        if self.LiveMode:
            return
        try:
            self._accounting_slices_seen += 1
            benchmark_ticker = getattr(self, "_benchmark_ticker", "SPY")
            benchmark_bars = getattr(data, "Bars", None)
            if benchmark_bars is not None:
                for bar in benchmark_bars.Values:
                    if str(bar.Symbol.Value).upper() == benchmark_ticker:
                        self._store.record_benchmark_session(self.Time.date().isoformat())
                        break
            for dividend in data.Dividends.Values:
                self._accounting_corporate_actions.append(
                    {
                        "kind": "dividend",
                        "observed_at": str(self.Time),
                        "symbol": str(dividend.Symbol.Value),
                        "distribution_per_share": str(dividend.Distribution),
                        "reference_price": str(dividend.ReferencePrice),
                        "held_quantity": str(self.Portfolio[dividend.Symbol].Quantity),
                    }
                )
            for split in data.Splits.Values:
                self._accounting_corporate_actions.append(
                    {
                        "kind": "split",
                        "observed_at": str(self.Time),
                        "symbol": str(split.Symbol.Value),
                        "split_factor": str(split.SplitFactor),
                        "reference_price": str(split.ReferencePrice),
                        "held_quantity": str(self.Portfolio[split.Symbol].Quantity),
                    }
                )
        except Exception as exc:
            self.Debug(f"accounting corporate-action capture failed ({type(exc).__name__})")

    def _write_backtest_accounting(self):
        if self.LiveMode:
            return
        try:
            from pathlib import Path

            ledger = {
                "schema_version": 1,
                "source": "LEAN algorithm callbacks",
                "account_currency": str(getattr(self, "AccountCurrency", "USD")),
                "period": {
                    "start": self._accounting_period["start"],
                    "end": self._accounting_period["end"],
                    "ir_id": os.environ.get("SIGMARAIL_STRATEGY_ID") or self.GetParameter("sigmarail-strategy-id") or None,
                },
                "initial": self._accounting_start,
                "orders": [
                    {
                        "order_id": int(order.Id),
                        "symbol": str(order.Symbol.Value),
                        "quantity": str(order.Quantity),
                    }
                    for order in self.Transactions.GetOrders()
                ],
                "fills": self._accounting_fills,
                "corporate_actions": self._accounting_corporate_actions,
                "corporate_action_slices_seen": self._accounting_slices_seen,
                "daily_snapshots": self._accounting_snapshots,
                "final": self._accounting_state(),
            }
            output = Path("/Results")
            output.mkdir(parents=True, exist_ok=True)
            (output / "backtest_accounting.json").write_text(
                json.dumps(ledger, separators=(",", ":"))
            )
        except Exception as exc:
            self.Debug(f"accounting ledger write failed ({type(exc).__name__})")

    def OnEndOfAlgorithm(self):
        self._write_backtest_accounting()
        if not self.LiveMode and getattr(self, "_store", None) is not None:
            try:
                from pathlib import Path

                output = Path("/Results")
                output.mkdir(parents=True, exist_ok=True)
                (output / "benchmark_series.json").write_text(
                    json.dumps(self._store.benchmark_series(), separators=(",", ":"))
                )
            except Exception as exc:
                self.Debug(f"benchmark series write failed ({type(exc).__name__})")
        if not self.LiveMode and getattr(self, "_day_snapshots", None):
            try:
                from pathlib import Path

                d = Path("/Results")
                d.mkdir(parents=True, exist_ok=True)
                (d / "backtest_day_snapshots.json").write_text(
                    json.dumps(self._day_snapshots, separators=(",", ":"))
                )
            except Exception as exc:
                self.Debug(f"Could not write backtest_day_snapshots: {exc}")

        summary = getattr(self, "_etf_compare_summary", None)
        if not summary:
            return
        # Refresh equity / drawdown at true end
        try:
            from sigmarail_lab.etf_rotation_state import comparison_summary

            summary = comparison_summary(
                path=summary.get("path", "graph"),
                final_equity=float(self.Portfolio.TotalPortfolioValue),
                initial_cash=float(getattr(self, "_initial_cash", None) or self.GetParameter("initial-cash") or 100_000),
                n_state_transitions=int(summary.get("n_state_transitions") or 0),
                state_day_histogram=summary.get("state_day_histogram") or {},
                transitions=[
                    (t["date"], t["state"]) if isinstance(t, dict) else t
                    for t in (summary.get("transitions") or [])
                ],
                max_drawdown=float(summary.get("max_drawdown") or 0.0),
            )
        except Exception as exc:
            self.Debug(f"etf compare summary refresh failed: {exc}")
        self.Debug(f"SUMMARY {json.dumps(summary)}")
        try:
            from pathlib import Path

            d = Path("/Results")
            d.mkdir(parents=True, exist_ok=True)
            (d / "etf_rotation_summary_graph.json").write_text(json.dumps(summary, indent=2))
        except Exception as exc:
            self.Debug(f"Could not write graph summary: {exc}")
