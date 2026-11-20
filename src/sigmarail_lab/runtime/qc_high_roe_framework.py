"""
QC framework: High-ROE large-cap rolling universe (CH fundamentals + Lean bars).

Universe membership from ClickHouse ``daily_screener``; OHLCV from Lean feed only.
"""

from __future__ import annotations

from datetime import timedelta

from AlgorithmImports import *  # noqa: F401,F403
from QuantConnect import Market, SecurityType, Symbol

from sigmarail_lab.runtime.high_roe_selection import HighRoeRollingCohort


class HighRoeQualityUniverseSelectionModel(UniverseSelectionModel):
    """
    Monthly: add ``new_assets_per_month`` highest-ROE liquid large-caps not held in the
    last 12 monthly cohorts; return the full rolling cohort for Lean subscriptions.
    """

    def __init__(
        self,
        store,
        new_assets_per_month: int = 2,
        min_market_cap_millions: float = 500.0,
        min_ipo_days: int = 180,
    ):
        super().__init__()
        self._store = store
        self._algorithm = None
        self._snapshot_key = None
        self._snapshot_symbols: list = []
        self._cohort = HighRoeRollingCohort(
            n_new=int(new_assets_per_month),
            min_market_cap_millions=float(min_market_cap_millions),
            min_ipo_days=int(min_ipo_days),
        )

    def CreateUniverses(self, algorithm):
        self._algorithm = algorithm

        def _debug(msg: str) -> None:
            algorithm.Debug(msg)

        self._cohort._debug = _debug
        return [
            ScheduledUniverse(
                algorithm.TimeZone,
                algorithm.DateRules.MonthStart(),
                algorithm.TimeRules.At(0, 0),
                self.SelectSymbols,
                algorithm.UniverseSettings,
            )
        ]

    def SelectSymbols(self, date_time):
        as_of = (date_time.date() - timedelta(days=1))
        key = (as_of.year, as_of.month, as_of.isoformat())
        if self._snapshot_key == key:
            return self._snapshot_symbols

        client = getattr(self._store, "_client", None)
        if client is None:
            self._algorithm.Debug("HighRoe: store has no ClickHouse client")
            return self._snapshot_symbols

        # Seed 12 prior months so the first live month already has a full cohort.
        if not self._cohort._cohorts:
            y, m = as_of.year, as_of.month
            seed_dates = []
            for _ in range(12):
                if m == 1:
                    y, m = y - 1, 12
                else:
                    m -= 1
                seed_dates.append(as_of.replace(year=y, month=m, day=1))
            for d in reversed(seed_dates):
                self._cohort.maybe_select(client, d)

        tickers = self._cohort.maybe_select(client, as_of)
        self._snapshot_key = key
        self._snapshot_symbols = [
            Symbol.Create(t, SecurityType.Equity, Market.USA) for t in tickers
        ]
        return self._snapshot_symbols
