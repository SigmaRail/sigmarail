"""Registry of Vera ClickHouse sources that compile from VeraLab (extensible).

Universe compilation here is **legacy** for ``daily_screener``; new work should
use **VeraBase** ``universe_query_v1`` over REST. This registry remains for
callers that still invoke ``compile_universe_*_sql`` directly.
"""

from __future__ import annotations

from enum import StrEnum

from .models import UniverseSpec


class VeraSourceId(StrEnum):
    DAILY_SCREENER = "daily_screener"
    MARKET_REGIME_SIGNALS_DAILY = "market_regime_signals_daily"


# Reference SQL shape for market_regime_signals_daily (loader: sigmarail_market_regime_signals_daily.py).
REFERENCE_MARKET_REGIME_SQL = """
SELECT
    toDate(date) AS date,
    clamp_risk_off,
    weekly_allocation_fraction,
    spy_close,
    spy_above200d,
    allocation_fraction,
    allocation_reason
FROM market_regime_signals_daily FINAL
WHERE date BETWEEN toDate('{start}') AND toDate('{end}')
FORMAT JSONEachRow
""".strip()


def compile_universe_range_sql(source: VeraSourceId, spec: UniverseSpec, start: str, end: str) -> str:
    if source == VeraSourceId.DAILY_SCREENER:
        raise NotImplementedError(
            "daily_screener universe SQL compile was removed; use VeraBase "
            "universe_query_v1 via POST /v1/universe/run"
        )
    if source == VeraSourceId.MARKET_REGIME_SIGNALS_DAILY:
        raise NotImplementedError(
            "market_regime_signals_daily is loaded via sigmarail_lab.runtime.sigmarail_market_regime_signals_daily; "
            "see REFERENCE_MARKET_REGIME_SQL for column shape"
        )
    raise ValueError(f"unknown Vera source: {source!r}")


def compile_universe_single_day_sql(source: VeraSourceId, spec: UniverseSpec, day: str) -> str:
    if source == VeraSourceId.DAILY_SCREENER:
        raise NotImplementedError(
            "daily_screener universe SQL compile was removed; use VeraBase "
            "universe_query_v1 via POST /v1/universe/run"
        )
    if source == VeraSourceId.MARKET_REGIME_SIGNALS_DAILY:
        raise NotImplementedError(
            "use SigmaRailMarketRegimeSignalsDaily / SigmaRailFrameworkStore for regime rows"
        )
    raise ValueError(f"unknown Vera source: {source!r}")
