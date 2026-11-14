"""Build ClickHouse SQL strings for ``daily_screener`` universe loads (legacy).

Prefer **VeraBase** ``/v1/universe/run`` with ``universe_query_v1`` JSON when
``sigmarail-api-url`` is configured (see ``sigmarail_lab.runtime.sigmarail_daily_screener``).
These helpers are retained for **offline / fallback** execution and for
``reload_today`` with ``UniverseSpec`` without the query service.
"""

from __future__ import annotations

from .models import UniverseSpec


def build_screener_load_sql(
    spec: UniverseSpec,
    start_date_iso: str,
    end_date_iso: str,
) -> str:
    """Bulk load for backtest date range (LIMIT n BY date)."""
    return spec.to_screener_range_sql(start_date_iso, end_date_iso)


def build_screener_reload_today_sql(spec: UniverseSpec, today_iso: str) -> str:
    """Live: single calendar day."""
    return spec.to_screener_single_day_sql(today_iso)
