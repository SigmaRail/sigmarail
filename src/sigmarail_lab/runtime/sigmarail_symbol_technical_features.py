"""
ClickHouse table ``symbol_technical_features_daily`` — bulk load for TQQQ tactical runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._date_floor import floor_key

if TYPE_CHECKING:
    from .ch_http import ChHttpClient


class VeraSymbolTechnicalFeaturesDaily:
    """Cache rows from symbol_technical_features_daily keyed by (ticker, date)."""

    _COLS = """
        ticker,
        toString(date) AS trade_date,
        pct_from_sma10d,
        pct_from_sma20d,
        drawdown_from_20d_high,
        drawdown_from_50d_high,
        drawdown_from_63d_high,
        consecutive_up_days,
        up_days_last_3,
        up_days_last_5,
        close_location_pct,
        downside_reversal_flag,
        extended_above_sma20_flag,
        near_sma20_flag,
        closes_below_sma20_streak,
        two_closes_below_sma20,
        first_up_day_low,
        toString(first_up_day_date) AS first_up_day_date,
        pullback_ready,
        three_up_days,
        entry_gate
    """

    def __init__(self, tickers: list[str] | None = None) -> None:
        self._tickers = tickers or ["QQQ", "TQQQ"]
        self._http: ChHttpClient | None = None
        self._by_key: dict[tuple[str, str], dict[str, Any]] = {}
        self._dates_by_ticker: dict[str, list[str]] = {}

    def set_http_client(self, client: ChHttpClient) -> None:
        self._http = client

    def set_tickers(self, tickers: list[str]) -> None:
        """Re-target the loader at a different ticker set (e.g. the screener universe)."""
        self._tickers = list(tickers)

    def bind_algorithm(self, algorithm) -> None:
        return

    def reload_today(self, today) -> None:
        if not self._http:
            return
        from datetime import timedelta

        start = today - timedelta(days=5)
        self.load_range(start, today)

    def load_range(self, start_date, end_date) -> None:
        if not self._http:
            return
        escaped = ", ".join(f"'{t}'" for t in self._tickers)
        sql = f"""
            SELECT {self._COLS}
            FROM symbol_technical_features_daily FINAL
            WHERE ticker IN ({escaped})
              AND symbol_technical_features_daily.date BETWEEN toDate('{start_date.isoformat()}')
                           AND toDate('{end_date.isoformat()}')
            FORMAT JSONEachRow
        """
        rows = self._http.query_json_each_row(sql, max_rows=500_000)
        self._by_key = {}
        for row in rows:
            ticker = str(row.get("ticker", ""))
            d = str(row.get("trade_date", row.get("date", "")))[:10]
            if ticker and d:
                self._by_key[(ticker, d)] = row
        self._dates_by_ticker = {}
        for ticker, d in self._by_key:
            self._dates_by_ticker.setdefault(ticker, []).append(d)
        for dates in self._dates_by_ticker.values():
            dates.sort()

    def get_features(self, ticker: str, date_str: str) -> dict[str, Any]:
        # Per-ticker floor across non-trading days — see _date_floor.py.
        d = floor_key(self._dates_by_ticker.get(ticker, ()), date_str)
        return dict(self._by_key.get((ticker, d), {})) if d else {}

    def get_with_close(self, ticker: str, date_str: str, close: float | None = None) -> dict[str, Any]:
        row = self.get_features(ticker, date_str)
        if close is not None:
            row = {**row, "close": close}
        return row
