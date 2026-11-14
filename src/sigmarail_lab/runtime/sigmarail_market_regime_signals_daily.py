"""
ClickHouse regime rows for LEAN — bulk load from regime_composed or market_regime_signals_daily.

LEAN runtime: uses ChHttpClient from sigmarail_lab.runtime.ch_http.
"""

from __future__ import annotations

import os
import re
import math
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from ._date_floor import floor_get, floor_key

if TYPE_CHECKING:
    from .ch_http import ChHttpClient


class SigmaRailMarketRegimeSignalsDaily:
    """In-memory cache of regime rows by date (YYYY-MM-DD) from composed or daily monolith."""

    def __init__(self) -> None:
        self._http: ChHttpClient | None = None
        self._algorithm = None
        self._by_date: dict[str, dict[str, Any]] = {}
        self._benchmark_ticker = "SPY"
        self._benchmark_by_date: dict[str, float] = {}
        self._benchmark_range_start: str | None = None
        self._benchmark_range_end: str | None = None
        self._benchmark_session_dates: set[str] = set()
        self._pt_by_date: dict[str, dict[str, Any]] = {}
        self._regime_source_override: str | None = None

    _PT_FIELDS = ("power_trend_on", "power_trend_days", "power_trend_start")
    _PT_INDEX_TICKER = "^IXIC"  # Nasdaq Composite — IBD's canonical Power Trend index

    def set_regime_source(self, source: str | None) -> None:
        if source is not None and str(source).strip():
            self._regime_source_override = str(source).strip().lower()

    def set_benchmark_ticker(self, ticker: str) -> None:
        """Set the explicit benchmark whose fully adjusted closes LEAN will chart."""
        value = str(ticker or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^_-]{1,24}", value):
            raise ValueError(f"Invalid benchmark ticker: {ticker!r}")
        self._benchmark_ticker = value

    def record_benchmark_session(self, date_str: str) -> None:
        """Record a benchmark date for which LEAN received an actual market bar."""
        if self._benchmark_ticker != "CASH":
            day = str(date_str)[:10]
            try:
                date.fromisoformat(day)
            except ValueError:
                return
            self._benchmark_session_dates.add(day)

    def set_http_client(self, client: ChHttpClient) -> None:
        self._http = client

    def bind_algorithm(self, algorithm) -> None:
        self._algorithm = algorithm

    def _regime_source(self) -> str:
        if self._regime_source_override:
            return self._regime_source_override
        if self._algorithm is not None:
            p = self._algorithm.GetParameter("regime-source")
            if p is not None and str(p).strip():
                return str(p).strip().lower()
        return (os.environ.get("SIGMARAIL_REGIME_SOURCE") or "composed").strip().lower()

    def _regime_policy_name(self) -> str:
        return (os.environ.get("SIGMARAIL_REGIME_POLICY_NAME") or "baseline_v4").strip()

    _SELECT_COLS_DAILY = """
                toDate(date) AS date,
                clamp_risk_off,
                weekly_allocation_fraction,
                weekly_allocation_tier,
                spy_close,
                spy_above200d,
                breadth_200d,
                distribution_count_25d,
                effective_allocation_fraction AS allocation_fraction,
                effective_allocation_tier AS allocation_tier,
                effective_source AS allocation_reason
    """

    _SELECT_COLS_TSMOM = """
                toDate(date) AS date,
                toUInt8(perf_1y <= 0) AS clamp_risk_off,
                toUInt8(0) AS daily_demote_streak,
                toFloat64(0) AS distribution_count_25d,
                toFloat64(0) AS breadth_200d,
                toFloat32(if(perf_1y > 0, 1.0, 0.0)) AS weekly_allocation_fraction,
                toUInt8(if(perf_1y > 0, 100, 0)) AS weekly_allocation_tier,
                toFloat64(close) AS spy_close,
                toUInt8(perf_1y > 0) AS spy_above200d,
                toFloat32(if(perf_1y > 0, 1.0, 0.0)) AS allocation_fraction,
                toUInt8(if(perf_1y > 0, 100, 0)) AS allocation_tier,
                'tsmom' AS allocation_reason
    """

    _SELECT_COLS_CANONICAL = """
                toDate(date) AS date,
                s_ma200_macro,
                s_breadth200,
                s_breadth50,
                s_vix,
                s_thrust,
                s_risk_off,
                toFloat64(0) AS spy_close,
                toUInt8(s_ma200_macro >= 0.5) AS spy_above200d,
                toFloat32(if(s_ma200_macro >= 0.5, 1.0, 0.0)) AS weekly_allocation_fraction,
                toUInt8(if(s_ma200_macro >= 0.5, 100, 0)) AS weekly_allocation_tier,
                toUInt8(if(s_ma200_macro < 0.5, 1, 0)) AS clamp_risk_off,
                'canonical' AS allocation_reason
    """

    _SELECT_COLS_COMPOSED = """
                toDate(date) AS date,
                toUInt8(frac <= 0.001) AS clamp_risk_off,
                toFloat32(frac) AS weekly_allocation_fraction,
                toUInt8(round(frac * 100)) AS weekly_allocation_tier,
                toFloat64(0) AS spy_close,
                toUInt8(frac >= 0.5) AS spy_above200d,
                toFloat64(0) AS breadth_200d,
                toFloat64(0) AS distribution_count_25d,
                toFloat32(frac) AS allocation_fraction,
                toUInt8(round(frac * 100)) AS allocation_tier,
                concat('composed:', policy_name, ' top=', top_contributor) AS allocation_reason
    """

    def _build_query(self, date_predicate: str, *, limit: str = "") -> str:
        """Single valid SELECT with one WHERE clause (avoids duplicate WHERE on composed path)."""
        if self._regime_source() == "composed":
            policy = self._regime_policy_name().replace("'", "")
            if not policy:
                raise RuntimeError(
                    "SIGMARAIL_REGIME_SOURCE=composed requires SIGMARAIL_REGIME_POLICY_NAME"
                )
            return f"""
            SELECT
            {self._SELECT_COLS_COMPOSED}
            FROM regime_composed_daily
            WHERE ticker = 'SPY' AND policy_name = '{policy}'
              AND {date_predicate}
            {limit}
            FORMAT JSONEachRow
            """
        src = self._regime_source()
        if src in ("regime_signals_canonical", "canonical"):
            return f"""
            SELECT
            {self._SELECT_COLS_CANONICAL}
            FROM regime_signals_canonical FINAL
            WHERE ticker = 'SPY' AND {date_predicate}
            {limit}
            FORMAT JSONEachRow
            """
        if src in ("daily", "v3", "market_regime_signals_daily", "mart"):
            return f"""
            SELECT
            {self._SELECT_COLS_DAILY}
            FROM market_regime_signals_daily FINAL
            WHERE {date_predicate}
            {limit}
            FORMAT JSONEachRow
            """
        if src in ("tsmom", "screener"):
            return f"""
            SELECT
            {self._SELECT_COLS_TSMOM}
            FROM screener_price_tech_daily FINAL
            WHERE ticker = 'SPY' AND {date_predicate}
            {limit}
            FORMAT JSONEachRow
            """
        raise RuntimeError(
            f"SIGMARAIL_REGIME_SOURCE must be 'canonical', 'composed', 'daily' (v3 alias), or 'tsmom', got {src!r}"
        )

    def load_range(self, start_date, end_date) -> None:
        """Bulk-load FINAL rows for [start_date, end_date] (date objects)."""
        pred = (
            f"date BETWEEN toDate('{start_date.isoformat()}') "
            f"AND toDate('{end_date.isoformat()}')"
        )
        sql = self._build_query(pred)
        rows = self._query(sql, max_rows=100_000)
        self._by_date = {}
        for row in rows:
            d = str(row.get("date", ""))[:10]
            if d:
                self._by_date[d] = row
        self._load_benchmark_prices(start_date, end_date)
        self._load_power_trend(start_date, end_date)

    def _load_benchmark_prices(self, start_date, end_date) -> None:
        """Load dividend/split-adjusted benchmark closes independently of regime marts."""
        self._benchmark_range_start = start_date.isoformat()
        self._benchmark_range_end = end_date.isoformat()
        ticker = self._benchmark_ticker
        if ticker == "CASH":
            self._benchmark_by_date = {}
            return
        sql = f"""
            SELECT toString(toDate(date)) AS benchmark_date, closeadj
            FROM daily_metrics FINAL
            WHERE ticker = '{ticker}'
              AND date BETWEEN toDate('{start_date.isoformat()}')
                           AND toDate('{end_date.isoformat()}')
              AND closeadj IS NOT NULL AND closeadj > 0
            ORDER BY date
            FORMAT JSONEachRow
            """
        rows = self._query(sql, max_rows=100_000)
        self._benchmark_by_date = {}
        for row in rows:
            day = str(row.get("benchmark_date", ""))[:10]
            try:
                close = float(row["closeadj"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if day and math.isfinite(close) and close > 0:
                self._benchmark_by_date[day] = close

    def _load_power_trend(self, start_date, end_date) -> None:
        """Compute the IBD Power Trend series on ^IXIC and cache per trading date.

        Runs at load time rather than in CH so no schema/populate change is
        needed: ema21d is unpopulated on index rows, so EMA21 is computed here
        (SMA-21 seed, k=2/22). Streak + latch follow the published definition:
        on when low>ema21 for 10d AND ema21>sma50 for 5d AND sma50 rising AND
        up close; off on the ema21<sma50 cross or the circuit breaker (close
        under sma50 while >10% below the episode high). Missing data → {} →
        field reads return None (fail-closed).
        """
        self._pt_by_date = {}
        pad = start_date - timedelta(days=130) if hasattr(start_date, "__sub__") else start_date
        sql = f"""
            SELECT toDate(date) AS date, close, low, high, sma50d
            FROM daily_metrics
            WHERE ticker = '{self._PT_INDEX_TICKER}'
              AND date BETWEEN toDate('{pad}') AND toDate('{end_date}')
            ORDER BY date
            FORMAT JSONEachRow
            """
        rows = self._query(sql, max_rows=50_000)
        bars = [
            (
                str(r["date"])[:10],
                float(r.get("close") or 0.0),
                float(r.get("low") or 0.0),
                float(r.get("high") or 0.0),
                float(r["sma50d"]) if r.get("sma50d") is not None else None,
            )
            for r in rows
        ]
        if len(bars) < 22:
            return
        k = 2.0 / 22.0
        ema = sum(b[1] for b in bars[:21]) / 21.0
        low_ok = ema_ok = 0
        pt_on = False
        pt_days = 0
        ep_high = 0.0
        for i, (d, close, low, high, sma50) in enumerate(bars):
            if i >= 21:
                ema = ema + k * (close - ema)
            if sma50 is None or i < 21:
                continue
            prev_close = bars[i - 1][1]
            prev_sma50 = bars[i - 1][4]
            low_ok = low_ok + 1 if low > ema else 0
            ema_ok = ema_ok + 1 if ema > sma50 else 0
            start = (
                low_ok >= 10
                and ema_ok >= 5
                and prev_sma50 is not None
                and sma50 > prev_sma50
                and close > prev_close
            )
            if start:
                pt_on, pt_days, ep_high = True, 0, high
            elif pt_on:
                ep_high = max(ep_high, high)
                circuit = close < sma50 and close < 0.9 * ep_high
                if ema < sma50 or circuit:
                    pt_on, pt_days, ep_high = False, 0, 0.0
            if pt_on:
                pt_days += 1
            self._pt_by_date[d] = {
                "power_trend_on": 1 if pt_on else 0,
                "power_trend_days": pt_days if pt_on else 0,
                "power_trend_start": 1 if start else 0,
            }

    def reload_today(self, today) -> None:
        """Refresh single calendar day (live). Merges into _by_date."""
        sql = self._build_query(
            f"date = toDate('{today.isoformat()}')", limit="LIMIT 1"
        )
        rows = self._query(sql, max_rows=5)
        if rows:
            d = str(rows[0].get("date", ""))[:10]
            if d:
                self._by_date[d] = rows[0]

    def get_row(self, date_str: str):
        """Regime row as of ``date_str`` — the last published row at or before it.

        Floor-resolved: a Sunday/holiday ``as_of`` returns the prior trading
        day's row (the data a live session would have). Only dates before the
        first loaded row return None (genuinely no data → fail-closed).
        """
        return floor_get(self._by_date, date_str)

    def get_weekly_allocation_fraction(self, date_str: str) -> float:
        """Return weekly_allocation_fraction (0..1); defaults to 1.0 when no row present."""
        row = floor_get(self._by_date, date_str)
        if not row:
            return 1.0
        return float(row.get("weekly_allocation_fraction") or 0.0)

    def get_weekly_allocation_tier(self, date_str: str) -> int:
        """Return weekly_allocation_tier (0/33/67/100); defaults to 100 when no row."""
        row = floor_get(self._by_date, date_str)
        if not row:
            return 100
        return int(row.get("weekly_allocation_tier") or 0)

    def allows_new_longs(self, date_str: str) -> bool:
        """True if row allows new longs: no clamp and positive weekly allocation; missing row blocks."""
        row = floor_get(self._by_date, date_str)
        if not row:
            return False
        clamp = int(row.get("clamp_risk_off") or 0)
        wfrac = float(row.get("weekly_allocation_fraction") or 0.0)
        return clamp == 0 and wfrac > 1e-6

    def get_spy_close(self, date_str: str) -> float:
        """Benchmark / reference close from regime row (composed or daily; not ``daily_screener``)."""
        row = floor_get(self._by_date, date_str)
        if not row:
            return 0.0
        return float(row.get("spy_close") or 0.0)

    def get_benchmark_price(self, date_str: str) -> float:
        """Return the last fully adjusted benchmark close at or before ``date_str``."""
        if self._benchmark_ticker == "CASH":
            return 1.0
        value = floor_get(self._benchmark_by_date, date_str)
        return float(value) if value is not None else 0.0

    def benchmark_series(self) -> dict[str, Any]:
        """Evidence payload aligned to the date-floored prices supplied to LEAN."""
        if self._benchmark_ticker == "CASH":
            return {
                "ticker": "CASH",
                "price_basis": "cash_zero_return",
                "source": "constant_cash",
                "observations": [],
                "market_session_dates": [],
            }
        observations = [
            {"date": day, "close": close}
            for day, close in sorted(self._benchmark_by_date.items())
        ]
        if self._benchmark_range_start and self._benchmark_range_end:
            start = date.fromisoformat(self._benchmark_range_start)
            end = date.fromisoformat(self._benchmark_range_end)
            observations = []
            current = start
            while current <= end:
                day = current.isoformat()
                close = floor_get(self._benchmark_by_date, day)
                if close is not None:
                    observations.append({"date": day, "close": close})
                current += timedelta(days=1)
        return {
            "ticker": self._benchmark_ticker,
            "price_basis": "adjusted_total_return",
            "source": "daily_metrics.closeadj",
            "observations": observations,
            "market_session_dates": sorted(self._benchmark_session_dates),
        }

    def get_spy_is_bull(self, date_str: str) -> bool:
        """True if ``spy_above200d`` is set; missing row blocks entries (fail-closed)."""
        row = floor_get(self._by_date, date_str)
        if not row:
            return False
        v = row.get("spy_above200d")
        if v is None:
            return False
        return int(v) != 0

    def _query(self, sql: str, max_rows: int) -> list:
        if self._http is None:
            if self._algorithm:
                self._algorithm.Debug("SigmaRailMarketRegimeSignalsDaily: HTTP client not set")
            return []
        return self._http.query_json_each_row(sql, max_rows=max_rows)

    def get_regime_field(self, date_str: str, field: str):
        """Return a single field from the cached regime row, or fetch VIX from market_context_daily."""
        if field in self._PT_FIELDS:
            row = floor_get(self._pt_by_date, date_str)
            return row.get(field) if row else None
        row = floor_get(self._by_date, date_str)
        if row and field in row:
            return row[field]
        # Fallback: fetch VIX columns from market_context_daily (floored date —
        # non-trading days have no market_context row either)
        vix_fields = {"vix_spike_flag", "vix_contango_proxy", "clamp_risk_off"}
        if field in vix_fields:
            floor_d = floor_key(self._by_date, date_str) or date_str
            sql = f"""
            SELECT {field}
            FROM market_context_daily FINAL
            WHERE date = toDate('{floor_d}')
            LIMIT 1
            FORMAT JSONEachRow
            """
            rows = self._query(sql, max_rows=1)
            if rows:
                return rows[0].get(field)
        return None
