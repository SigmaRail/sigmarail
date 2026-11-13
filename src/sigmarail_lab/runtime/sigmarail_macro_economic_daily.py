"""
ClickHouse macro economic-environment rows for LEAN (Dalio 4-quadrant regime).

Caches ``macro_economic_daily`` (growth/inflation/quadrant) by date so the
All Weather regime overlay can tilt leg exposure from real macro data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._date_floor import floor_get

if TYPE_CHECKING:
    from .ch_http import ChHttpClient

_SELECT = """
    SELECT toDate32(date) AS date, real_gdp_qoq, cpi_yoy, regime_quadrant
    FROM macro_economic_daily
"""


class VeraMacroEconomicDaily:
    """In-memory cache of macro rows by date (YYYY-MM-DD)."""

    def __init__(self) -> None:
        self._http: ChHttpClient | None = None
        self._by_date: dict[str, dict[str, Any]] = {}

    def set_http_client(self, client: ChHttpClient) -> None:
        self._http = client

    def _query(self, sql: str, max_rows: int) -> list[dict[str, Any]]:
        if self._http is None:
            return []
        return self._http.query_json_each_row(sql, max_rows=max_rows)

    def load_range(self, start_date, end_date) -> None:
        pred = (
            f"date BETWEEN toDate32('{start_date.isoformat()}') "
            f"AND toDate32('{end_date.isoformat()}')"
        )
        rows = self._query(f"{_SELECT} WHERE {pred} FORMAT JSONEachRow", max_rows=100_000)
        self._by_date = {}
        for row in rows:
            d = str(row.get("date", ""))[:10]
            if d:
                self._by_date[d] = row

    def reload_today(self, today) -> None:
        rows = self._query(
            f"{_SELECT} WHERE date = toDate32('{today.isoformat()}') LIMIT 1 FORMAT JSONEachRow",
            max_rows=5,
        )
        if rows:
            d = str(rows[0].get("date", ""))[:10]
            if d:
                self._by_date[d] = rows[0]

    def _row(self, date_str: str) -> dict[str, Any] | None:
        # Floor across non-trading days — see _date_floor.py for the contract.
        return floor_get(self._by_date, date_str)

    def growth_delta(self, date_str: str) -> float:
        row = self._row(date_str)
        if not row:
            return 0.0
        return float(row.get("real_gdp_qoq") or 0.0)

    def inflation_delta(self, date_str: str) -> float:
        row = self._row(date_str)
        if not row:
            return 0.0
        return float(row.get("cpi_yoy") or 0.0)

    def quadrant(self, date_str: str) -> str:
        row = self._row(date_str)
        if not row:
            return ""
        return str(row.get("regime_quadrant") or "")
