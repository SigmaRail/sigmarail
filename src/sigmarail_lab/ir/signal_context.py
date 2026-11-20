"""SignalContext: per-ticker features and regime fields for graph policy evaluation."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .data_sources import DataSourceCatalog, DataSourceSpec


class DataProvider(Protocol):
    """Protocol for data providers that can fetch columns for a given source."""
    def get(self, source: str, column: str, as_of: str) -> Any: ...


class SignalContext:
    def __init__(self, providers: Mapping[str, DataProvider], *, as_of: str) -> None:
        self._providers = dict(providers)
        self._as_of = as_of
        self._cache: dict[tuple[str, str, str], Any] = {}

    @property
    def as_of(self) -> str:
        return self._as_of

    def get(self, ticker: str, column: str) -> Any:
        """Get signal/technical column for a ticker."""
        key = (ticker.strip().upper(), column, "signal")
        if key in self._cache:
            return self._cache[key]
        val = None
        for source in ("signal", "technical"):
            provider = self._providers.get(source)
            if provider is None:
                continue
            ticker_getter = getattr(provider, "get_for_ticker", None)
            val = (
                ticker_getter(key[0], column, self._as_of)
                if callable(ticker_getter)
                else provider.get(source, column, self._as_of)
            )
            if val is not None:
                break
        self._cache[key] = val
        return val

    def regime(self, field: str, source: str = "regime") -> Any:
        """Get field from a named data source."""
        key = (source, field, self._as_of)
        if key in self._cache:
            return self._cache[key]
        provider = self._providers.get(source)
        if provider is None:
            return None
        val = provider.get(source, field, self._as_of)
        self._cache[key] = val
        return val


def signal_context_from_store(
    store: Any,
    as_of: str,
    *,
    catalog: DataSourceCatalog | None = None
) -> SignalContext:
    """Build SignalContext with multiple providers from SigmaRailFrameworkStore."""
    if catalog is None:
        catalog = DataSourceCatalog()

    providers = {
        "signal": _SignalProvider(store),
        "regime": _RegimeProvider(store),
        "vix": _VixProvider(store),
        "macro": _MacroProvider(store),
        "technical": _TechnicalProvider(store),
    }
    # Allow catalog to add custom sources
    for name, spec in catalog.sources.items():
        if name not in providers:
            providers[name] = _ClickHouseProvider(store, spec)
    return SignalContext(providers, as_of=as_of)


class _SignalProvider:
    """Signal provider - uses screener/technical features for ticker-specific columns."""
    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, source: str, column: str, as_of: str) -> Any:
        # Ticker-less calls can't resolve - SignalContext.get routes via get_for_ticker
        return None

    def get_for_ticker(self, ticker: str, column: str, as_of: str) -> Any:
        features = getattr(self._store, "get_technical_features", None)
        if not callable(features):
            return None
        row = features(ticker, as_of) or {}
        return row.get(column)


class _RegimeProvider:
    """Regime provider - reads from market_regime_signals_daily / regime_composed_daily."""
    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, source: str, field: str, as_of: str) -> Any:
        f = field.strip().lower()
        if f in ("spy_above200d", "spy_bull", "spy_is_bull"):
            fn = getattr(self._store, "get_spy_is_bull", None)
            if not callable(fn):
                return None
            return 1 if fn(as_of) else 0
        if f in ("regime_weekly_fraction", "alloc_fraction", "weekly_allocation_fraction"):
            fn = getattr(self._store, "get_regime_weekly_fraction", None)
            return fn(as_of) if callable(fn) else None
        _daily_fields = (
            "clamp_risk_off",
            "daily_demote_streak",
            "distribution_count_25d",
            "breadth_200d",
            "breadth_50d",
            "power_trend_on",
            "power_trend_days",
            "power_trend_start",
        )
        if f in _daily_fields:
            fn = getattr(self._store, "get_regime_field", None)
            if not callable(fn):
                return None
            val = fn(as_of, f)
            if val is None:
                return None
            if f == "clamp_risk_off":
                return int(val)
            if f in ("daily_demote_streak", "distribution_count_25d"):
                return int(val)
            return val
        return None


class _VixProvider:
    """VIX provider - reads from market_context_daily."""
    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, source: str, field: str, as_of: str) -> Any:
        f = field.strip().lower()
        _vix_fields = ("vix_spike_flag", "vix_contango_proxy", "clamp_risk_off")
        if f in _vix_fields:
            fn = getattr(self._store, "get_regime_field", None)
            if not callable(fn):
                return None
            val = fn(as_of, f)
            if val is None:
                return None
            return int(val)
        return None


class _MacroProvider:
    """Macro provider - reads economic data."""
    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, source: str, field: str, as_of: str) -> Any:
        f = field.strip().lower()
        accessor = {
            "growth_delta": "growth_delta",
            "inflation_delta": "inflation_delta",
            "economic_quadrant": "economic_quadrant",
        }.get(f)
        if accessor is None:
            return None
        fn = getattr(self._store, accessor, None)
        return fn(as_of) if callable(fn) else None


class _TechnicalProvider:
    """Technical provider - reads from symbol_technical_features_daily."""
    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, source: str, field: str, as_of: str) -> Any:
        # Ticker-less calls can't resolve - SignalContext.get routes via get_for_ticker
        return None

    def get_for_ticker(self, ticker: str, field: str, as_of: str) -> Any:
        features = getattr(self._store, "get_technical_features", None)
        if not callable(features):
            return None
        row = features(ticker, as_of) or {}
        return row.get(field)


class _ClickHouseProvider:
    """Generic ClickHouse provider for catalog-registered sources."""
    def __init__(self, store: Any, spec: DataSourceSpec) -> None:
        self._store = store
        self._spec = spec

    def get(self, source: str, field: str, as_of: str) -> Any:
        # Fetch entire row for the date if not cached
        row = self._fetch_row(as_of)
        if not row:
            return None
        return row.get(field)

    def _fetch_row(self, as_of: str) -> dict[str, Any] | None:
        # Delegate to store's HTTP client
        if not hasattr(self._store, "_client") or self._store._client is None:
            return None
        sql = f"""
        SELECT {", ".join(self._spec.select)}
        FROM {self._spec.table}
        WHERE {self._spec.date_column} = toDate('{as_of}')
        LIMIT 1
        FORMAT JSONEachRow
        """
        rows = self._store._client.query_json_each_row(sql, max_rows=1)
        if rows:
            return rows[0]
        return None