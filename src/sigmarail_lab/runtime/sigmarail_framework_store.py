"""
LEAN-facing facade: delegates to sigmarail_daily_screener + sigmarail_market_regime_signals_daily.

No table SQL here — only composition and one-line delegates for wire_framework_bundle_v1(store=...).
"""

from __future__ import annotations

from typing import Any

from sigmarail_lab.ir.data_sources import DataSourceSpec
from sigmarail_lab.ir.models import GraphStep

from .ch_connection import resolve_clickhouse_settings
from .ch_http import ChHttpClient
from .sigmarail_daily_screener import SigmaRailDailyScreener
from .sigmarail_market_regime_signals_daily import SigmaRailMarketRegimeSignalsDaily
from .sigmarail_macro_economic_daily import VeraMacroEconomicDaily
from .sigmarail_symbol_technical_features import VeraSymbolTechnicalFeaturesDaily


class SigmaRailFrameworkStore:
    """Facade: universe metrics from ``daily_screener``; SPY/regime from ``market_regime_signals_daily``."""

    def __init__(self, universe_spec: dict[str, Any]) -> None:
        self._screener = SigmaRailDailyScreener(universe_spec)
        self._regime = SigmaRailMarketRegimeSignalsDaily()
        self._macro = VeraMacroEconomicDaily()
        self._technical = VeraSymbolTechnicalFeaturesDaily()
        self._algorithm = None
        self._client: ChHttpClient | None = None
        self._policy_graph_root: GraphStep | None = None
        self._vera_base: Any = None
        self._regime_gate_evaluator = None
        self._regime_gate_as_of: str | None = None
        self._regime_gate_last: bool = True

    def attach_regime_gate(self, gate: Any) -> None:
        """Attach RegimeGateV1 (or dict) evaluator for store-backed regime condition filtering."""
        # Lean Docker PYTHONPATH is /project only — do not import VeraBase here.
        from sigmarail_lab.runtime.regime_gate import RegimeGateEvaluator

        self._regime_gate_evaluator = RegimeGateEvaluator(gate)
        self._regime_gate_as_of = None
        self._regime_gate_last = True

    def _regime_gate_allows(self, date_str: str) -> bool:
        """Advance hysteresis at most once per session date (Alpha + PCM share this)."""
        if self._regime_gate_evaluator is None:
            return self._regime.allows_new_longs(date_str)
        if self._regime_gate_as_of != date_str:
            row = self._regime.get_row(date_str)
            self._regime_gate_last = bool(
                self._regime_gate_evaluator.update_day(date_str, row)
            )
            self._regime_gate_as_of = date_str
        return self._regime_gate_last

    def attach_policy_graph(self, root: GraphStep) -> None:
        """Attach Policy B graph root for VeraGraphPolicy* models."""
        self._policy_graph_root = root

    def attach_vera_base(self, vera_base: Any) -> None:
        """Attach VeraBase facet (includes data_sources) for graph policy data sources."""
        self._vera_base = vera_base

    def bind(self, algorithm, *, regime_source: str | None = None) -> None:
        self._algorithm = algorithm
        self._screener.bind_algorithm(algorithm)
        self._regime.bind_algorithm(algorithm)
        if regime_source:
            self._regime.set_regime_source(regime_source)
        self._technical.bind_algorithm(algorithm)
        settings = resolve_clickhouse_settings(algorithm)

        def _log(msg: str) -> None:
            if algorithm:
                algorithm.Debug(msg)

        self._client = ChHttpClient(settings, debug_log=_log)
        self._screener.set_http_client(self._client)
        self._regime.set_http_client(self._client)
        self._macro.set_http_client(self._client)
        self._technical.set_http_client(self._client)

    def load(self, start_date, end_date) -> None:
        self._screener.load(start_date, end_date)
        self._technical.set_tickers(self._screener.tickers())
        self._regime.load_range(start_date, end_date)
        self._macro.load_range(start_date, end_date)
        self._technical.load_range(start_date, end_date)

    def set_benchmark_ticker(self, ticker: str) -> None:
        self._regime.set_benchmark_ticker(ticker)

    def reload_today(self) -> None:
        from datetime import date as _date

        today = _date.today()
        self._screener.reload_today(today)
        self._regime.reload_today(today)
        self._macro.reload_today(today)
        self._technical.reload_today(today)

    def allows_new_longs_from_regime_signals(self, date_str: str) -> bool:
        if self._regime_gate_evaluator is not None:
            return self._regime_gate_allows(date_str)
        return self._regime.allows_new_longs(date_str)

    def get_allocation_fraction(self, date_str: str) -> float | None:
        """Session allocation fraction for PCM scale_exposure (thermostat).

        When a RegimeGate evaluator is attached, fraction follows the gate
        (including hysteresis), not binary weekly_allocation_fraction columns.
        """
        if self._regime_gate_evaluator is not None:
            return 1.0 if self._regime_gate_allows(date_str) else 0.0
        row = None
        if hasattr(self._regime, "get_row"):
            row = self._regime.get_row(date_str)
        if not row:
            return None
        for key in (
            "effective_allocation_fraction",
            "weekly_allocation_fraction",
            "allocation_fraction",
        ):
            if key in row and row[key] is not None:
                try:
                    return float(row[key])
                except (TypeError, ValueError):
                    continue
        return None

    def get_universe(self, date_str: str) -> dict[str, float]:
        return self._screener.get_universe(date_str)

    def get_atrs(self, date_str: str) -> dict[str, float]:
        return self._screener.get_atrs(date_str)

    def get_pivots(self, date_str: str, field: str = "vcp_pivot_line") -> dict[str, float]:
        """{ticker: VCP pivot line} — for pivot-derived stops (C3). Empty if the spec omits it."""
        return self._screener.get_pivots(date_str, field)

    def get_spy_price(self, date_str: str) -> float:
        return self._regime.get_spy_close(date_str)

    def get_benchmark_price(self, date_str: str) -> float:
        return self._regime.get_benchmark_price(date_str)

    def benchmark_series(self) -> dict[str, Any]:
        return self._regime.benchmark_series()

    def record_benchmark_session(self, date_str: str) -> None:
        self._regime.record_benchmark_session(date_str)

    def get_spy_is_bull(self, date_str: str) -> bool:
        if self._regime_gate_evaluator is not None:
            return self._regime_gate_allows(date_str)
        return self._regime.get_spy_is_bull(date_str)

    def get_regime_weekly_fraction(self, date_str: str) -> float:
        """weekly_allocation_fraction (0..1) — use to scale total equity exposure."""
        return self._regime.get_weekly_allocation_fraction(date_str)

    def get_regime_weekly_tier(self, date_str: str) -> int:
        """weekly_allocation_tier (0/33/67/100)."""
        return self._regime.get_weekly_allocation_tier(date_str)

    def get_regime_row(self, date_str: str):
        return self._regime.get_row(date_str)

    def get_regime_field(self, date_str: str, field: str):
        return self._regime.get_regime_field(date_str, field)

    def growth_delta(self, date_str: str) -> float:
        """Real GDP QoQ % (annualized) for the economic-environment regime."""
        return self._macro.growth_delta(date_str)

    def inflation_delta(self, date_str: str) -> float:
        """CPI-U YoY % for the economic-environment regime."""
        return self._macro.inflation_delta(date_str)

    def economic_quadrant(self, date_str: str) -> str:
        """Dalio 4-quadrant regime (reflation | goldilocks | stagflation | deflation)."""
        return self._macro.quadrant(date_str)

    def get_all_screener_rows(self, date_str: str) -> dict[str, dict[str, Any]]:
        """All rows for a date keyed by ticker (excludes SPY). Includes every column from the select clause."""
        return self._screener.get_all_rows(date_str)

    def get_sector_rows(self, date_str: str) -> dict[str, dict[str, dict]]:
        """{sector: {ticker: row}} — rows must include sector + rs_rating columns."""
        return self._screener.get_sector_rows(date_str)

    def get_sector_rs_scores(self, date_str: str) -> dict[str, float]:
        """{sector: avg_rs_rating} computed from screener rows."""
        return self._screener.get_sector_rs_scores(date_str)

    def get_technical_features(self, ticker: str, date_str: str) -> dict[str, Any]:
        return self._technical.get_features(ticker, date_str)

    def get_ticker_close(self, ticker: str, date_str: str) -> float | None:
        row = self._screener.get_row(ticker, date_str)
        close = row.get("close")
        if close is None:
            return None
        return float(close)

    def get_screener_row(self, ticker: str, date_str: str) -> dict[str, Any]:
        return self._screener.get_row(ticker, date_str)

    def dates_by_ticker(self) -> dict[str, list[str]]:
        """``{ticker: sorted date strings}`` — for presence-interval extraction."""
        return self._screener.dates_by_ticker()

    def get_ticker_metric(self, date_str: str, ticker: str, metric: str, default: Any = None) -> Any:
        row = self._screener.get_row(ticker, date_str)
        if not row:
            return default
        return row.get(metric, default)

    # --- Cross-model stop cooldown (Risk → Alpha) ----------------------------

    def record_stop_out(self, ticker: str, until_date) -> None:
        """Arm a stop cooldown until ``until_date`` (date or datetime.date)."""
        from datetime import date as _date

        if not hasattr(self, "_stop_cooled_until"):
            self._stop_cooled_until: dict[str, _date] = {}
        if hasattr(until_date, "date") and not isinstance(until_date, _date):
            until_date = until_date.date()
        self._stop_cooled_until[str(ticker)] = until_date

    def is_stop_cooled(self, ticker: str, as_of) -> bool:
        """True while ticker is still inside a Risk/Alpha stop cooldown window."""
        from datetime import date as _date

        cooled = getattr(self, "_stop_cooled_until", None) or {}
        until = cooled.get(str(ticker))
        if until is None:
            return False
        if hasattr(as_of, "date") and not isinstance(as_of, _date):
            as_of = as_of.date()
        if until <= as_of:
            cooled.pop(str(ticker), None)
            return False
        return True
