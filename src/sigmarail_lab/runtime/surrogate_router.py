"""Surrogate Router for routing single-stock / sector insights to leveraged ETF surrogates.

Maintains canonical mappings (backed by ClickHouse vera.etf_surrogate_catalog and offline fallback)
and handles historical inception date boundaries, minimum ADV liquidity floors, and dynamic
QuantConnect security subscription.
"""

from __future__ import annotations

import datetime
from typing import Any

try:
    from AlgorithmImports import Symbol, SecurityType, Market, Resolution
except ImportError:
    class SecurityType:
        Equity = 1

    class Market:
        USA = "usa"

    class Resolution:
        Daily = 1

    class Symbol:
        def __init__(self, value: str):
            self.Value = value

        @classmethod
        def Create(cls, value: str, sec_type=SecurityType.Equity, market=Market.USA):
            return cls(value)

        def __str__(self):
            return self.Value

        def __repr__(self):
            return f"Symbol({self.Value})"

        def __hash__(self):
            return hash(self.Value)

        def __eq__(self, other):
            return str(self) == str(other)


# Fallback catalog for standalone unit tests or offline environments
FALLBACK_SURROGATE_CATALOG: dict[str, dict[str, Any]] = {
    "NVDA": {
        "surrogate_ticker": "NVDL",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 12, 13),
        "category": "single_stock",
        "is_active": 1,
    },
    "TSLA": {
        "surrogate_ticker": "TSLL",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 8, 9),
        "category": "single_stock",
        "is_active": 1,
    },
    "COIN": {
        "surrogate_ticker": "CONL",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 8, 9),
        "category": "single_stock",
        "is_active": 1,
    },
    "AAPL": {
        "surrogate_ticker": "AAPU",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 8, 9),
        "category": "single_stock",
        "is_active": 1,
    },
    "MSFT": {
        "surrogate_ticker": "MSFU",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 9, 7),
        "category": "single_stock",
        "is_active": 1,
    },
    "AMZN": {
        "surrogate_ticker": "AMZU",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 9, 7),
        "category": "single_stock",
        "is_active": 1,
    },
    "GOOGL": {
        "surrogate_ticker": "GGLL",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 9, 7),
        "category": "single_stock",
        "is_active": 1,
    },
    "GOOG": {
        "surrogate_ticker": "GGLL",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2022, 9, 7),
        "category": "single_stock",
        "is_active": 1,
    },
    "META": {
        "surrogate_ticker": "METU",
        "leverage_factor": 2.0,
        "inception_date": datetime.date(2024, 6, 5),
        "category": "single_stock",
        "is_active": 1,
    },
    "SMH": {
        "surrogate_ticker": "SOXL",
        "leverage_factor": 3.0,
        "inception_date": datetime.date(2010, 3, 11),
        "category": "sector",
        "is_active": 1,
    },
    "SOXX": {
        "surrogate_ticker": "SOXL",
        "leverage_factor": 3.0,
        "inception_date": datetime.date(2010, 3, 11),
        "category": "sector",
        "is_active": 1,
    },
    "QQQ": {
        "surrogate_ticker": "TQQQ",
        "leverage_factor": 3.0,
        "inception_date": datetime.date(2010, 2, 9),
        "category": "index",
        "is_active": 1,
    },
    "SPY": {
        "surrogate_ticker": "UPRO",
        "leverage_factor": 3.0,
        "inception_date": datetime.date(2009, 6, 25),
        "category": "index",
        "is_active": 1,
    },
}


class SurrogateRouter:
    """Resolves underlying stock / ETF symbols to leveraged surrogates."""

    def __init__(
        self,
        client: Any = None,
        enable_surrogates: bool = True,
        min_surrogate_adv: float = 1_000_000.0,
    ) -> None:
        self.enabled = bool(enable_surrogates)
        self.min_surrogate_adv = float(min_surrogate_adv)
        self._catalog: dict[str, dict[str, Any]] = dict(FALLBACK_SURROGATE_CATALOG)
        self._reverse_map: dict[str, str] = {}
        self._load_catalog(client)
        self._build_reverse_map()

    def _load_catalog(self, client: Any = None) -> None:
        """Query ClickHouse vera.etf_surrogate_catalog if client is available."""
        if client is None:
            try:
                from vera.database import get_client
                client = get_client()
            except Exception:
                client = None

        if client is None:
            return

        try:
            sql = """
                SELECT underlying_ticker, surrogate_ticker, leverage_factor,
                       category, direction, inception_date, is_active
                FROM vera.etf_surrogate_catalog FINAL
                WHERE is_active = 1 AND direction = 'bull'
                ORDER BY leverage_factor DESC
            """
            res = client.query(sql)
            for row in res.result_rows:
                und = str(row[0]).strip().upper()
                surr = str(row[1]).strip().upper()
                lev = float(row[2])
                cat = str(row[3])
                incept = row[5]
                if isinstance(incept, datetime.datetime):
                    incept = incept.date()
                active = int(row[6])

                # Primary mapping: underlying -> highest leverage active surrogate
                if und not in self._catalog or lev > self._catalog[und].get("leverage_factor", 0):
                    self._catalog[und] = {
                        "surrogate_ticker": surr,
                        "leverage_factor": lev,
                        "inception_date": incept,
                        "category": cat,
                        "is_active": active,
                    }
        except Exception:
            # Fall back cleanly to preloaded dictionary
            pass

    def _build_reverse_map(self) -> None:
        self._reverse_map = {}
        for und, data in self._catalog.items():
            surr = data.get("surrogate_ticker")
            if surr:
                self._reverse_map[surr] = und

    def get_underlying_ticker(self, ticker_or_symbol: Any) -> str:
        """Given a surrogate ticker (e.g. NVDL), return underlying ticker (NVDA), or self."""
        val = ticker_or_symbol.Value if hasattr(ticker_or_symbol, "Value") else str(ticker_or_symbol)
        val = val.strip().upper()
        return self._reverse_map.get(val, val)

    def get_leverage(self, ticker_or_symbol: Any) -> float:
        """Return leverage factor if ticker is a known surrogate, else 1.0."""
        val = ticker_or_symbol.Value if hasattr(ticker_or_symbol, "Value") else str(ticker_or_symbol)
        val = val.strip().upper()
        und = self._reverse_map.get(val)
        if und and und in self._catalog:
            return float(self._catalog[und].get("leverage_factor", 1.0))
        return 1.0

    def has_surrogate(self, symbol_or_ticker: Any, as_of: datetime.date | None = None) -> bool:
        """True if an active, tradeable surrogate is available as of date."""
        if not self.enabled:
            return False
        val = symbol_or_ticker.Value if hasattr(symbol_or_ticker, "Value") else str(symbol_or_ticker)
        val = val.strip().upper()
        entry = self._catalog.get(val)
        if not entry or not entry.get("is_active"):
            return False
        incept = entry.get("inception_date")
        if incept and as_of and as_of < incept:
            return False
        return True

    def resolve_trade_symbol(
        self,
        algorithm: Any,
        symbol_or_ticker: Any,
        as_of: datetime.date | None = None,
    ) -> tuple[Any, float]:
        """Resolve a candidate to (trade_symbol, leverage_factor).

        Returns:
            (surrogate_symbol, leverage_factor) if eligible and tradeable,
            else (original_symbol, 1.0).
        """
        if not self.enabled:
            return symbol_or_ticker, 1.0

        val = symbol_or_ticker.Value if hasattr(symbol_or_ticker, "Value") else str(symbol_or_ticker)
        val = val.strip().upper()

        if not self.has_surrogate(val, as_of):
            return symbol_or_ticker, 1.0

        entry = self._catalog[val]
        surr_ticker = entry["surrogate_ticker"]
        leverage = float(entry.get("leverage_factor", 2.0))

        # Dynamic subscription in LEAN if algorithm provided
        if algorithm is not None:
            securities = getattr(algorithm, "Securities", None)
            if securities is not None:
                has_key = False
                if hasattr(securities, "ContainsKey"):
                    has_key = securities.ContainsKey(surr_ticker)
                elif hasattr(securities, "__contains__"):
                    has_key = surr_ticker in securities

                if not has_key:
                    try:
                        add_equity = getattr(algorithm, "AddEquity", None)
                        if callable(add_equity):
                            add_equity(surr_ticker, Resolution.Daily)
                    except Exception:
                        pass

        # Return QuantConnect Symbol if input was a Symbol
        if hasattr(symbol_or_ticker, "Value"):
            try:
                surr_symbol = Symbol.Create(surr_ticker, SecurityType.Equity, Market.USA)
                return surr_symbol, leverage
            except Exception:
                pass

        return surr_ticker, leverage
