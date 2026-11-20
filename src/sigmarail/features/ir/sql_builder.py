"""Build ClickHouse SQL for daily_screener universe loads.

Ported from VeraTradingLab `vera_lab.ir.sql_builder`.
"""

from __future__ import annotations

from .models import UniverseSpec


def build_screener_load_sql(spec: UniverseSpec, start_date_iso: str, end_date_iso: str) -> str:
    """Bulk load for backtest date range (LIMIT n BY date)."""
    return spec.to_screener_range_sql(start_date_iso, end_date_iso)


def build_screener_reload_today_sql(spec: UniverseSpec, today_iso: str) -> str:
    """Live: single calendar day."""
    return spec.to_screener_single_day_sql(today_iso)
