"""
Universe bulk load via Vera query service only (``POST /v1/universe/run``).

``VeraBase.Universe`` must be an opaque ``universe_query_v1`` dict; validation and SQL
compilation live in VeraBase (``vera_query_core``). This module is a row cache + REST client.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from ._date_floor import floor_key
from .ch_http import ChHttpClient
from .sigmarail_api_client import (
    SigmaRailApiClient,
    SigmaRailApiError,
    resolve_sigmarail_api_service_api_key,
    resolve_sigmarail_api_service_url,
)


def _is_universe_query_v1(spec: dict[str, Any]) -> bool:
    return spec.get("version") in (1, 2) and isinstance(spec.get("select"), list)


def _extract_fixed_tickers(spec: dict[str, Any]) -> list[str] | None:
    """Extract fixed tickers from a universe_query_v1 with an 'any' of 'eq' on ticker."""
    where = spec.get("where")
    if not isinstance(where, dict):
        return None
    if where.get("type") != "any":
        return None
    items = where.get("items")
    if not isinstance(items, list):
        return None
    tickers = []
    for item in items:
        if not isinstance(item, dict):
            return None
        if item.get("type") != "eq":
            return None
        left = item.get("left")
        right = item.get("right")
        if not isinstance(left, dict) or left.get("type") != "col" or left.get("name") != "ticker":
            return None
        if not isinstance(right, dict) or right.get("type") != "lit":
            return None
        tickers.append(str(right.get("value", "")).strip().upper())
    if tickers:
        return tickers
    return None


def _rank_field(spec: dict[str, Any]) -> str:
    order_by = spec.get("order_by")
    if isinstance(order_by, list) and order_by:
        first = order_by[0]
        if isinstance(first, dict):
            field = str(first.get("field") or "").strip()
            if field:
                return field
    return "overall_score"


def _add_months(d: date, months: int) -> date:
    month_index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def date_range_chunks(start_date: str, end_date: str, *, months: int = 6) -> list[tuple[str, str]]:
    """Inclusive ISO date windows of ``months`` (last chunk may be shorter).

    A single 10y ``universe_run`` hash-joins L7 tables past the local CH
    memory cap (~8 GiB). ~8 months succeeded; 6-month chunks stay under that.
    """
    if months < 1:
        raise ValueError("months must be >= 1")
    start = date.fromisoformat(start_date[:10])
    end = date.fromisoformat(end_date[:10])
    if end < start:
        raise ValueError("end_date before start_date")
    out: list[tuple[str, str]] = []
    cur = start
    while cur <= end:
        chunk_end = min(_add_months(cur, months) - timedelta(days=1), end)
        out.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return out


class SigmaRailDailyScreener:
    """In-memory cache: date_str -> ticker -> row dict (screener columns from REST or CH)."""

    def __init__(self, universe_spec: dict[str, Any]) -> None:
        if not isinstance(universe_spec, dict):
            raise TypeError(
                "SigmaRailDailyScreener requires universe_query_v1 dict; "
                f"got {type(universe_spec)!r}"
            )
        if not _is_universe_query_v1(universe_spec):
            raise ValueError(
                "VeraBase.Universe must be universe_query_v1 or v2 (version in (1, 2), select[])"
            )
        self._universe_spec = universe_spec
        self._api: SigmaRailApiClient | None = None
        self._algorithm = None
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        # Fixed universe support (for manual/backtest universes without REST API)
        self._fixed_tickers = _extract_fixed_tickers(universe_spec)
        # C-API-SURFACE-V1: what this run compiled/validated against.
        self.registry_digest: str = ""
        self._fabricated_rows_warned = False

    def set_http_client(self, client: ChHttpClient) -> None:
        """Wire REST client when ``sigmarail-api-url`` / ``SIGMARAIL_API_URL`` is set."""
        del client  # universe loads are REST-only; regime/technical use other loaders
        self._wire_api_client()

    def bind_algorithm(self, algorithm) -> None:
        self._algorithm = algorithm
        self._wire_api_client()

    def _wire_api_client(self) -> None:
        url = resolve_sigmarail_api_service_url(self._algorithm)
        if not url:
            self._api = None
            return
        key = resolve_sigmarail_api_service_api_key(self._algorithm)

        def _log(msg: str) -> None:
            if self._algorithm:
                self._algorithm.Debug(msg)

        self._api = SigmaRailApiClient(url, api_key=key, debug_log=_log)

    def _spec_payload(self) -> dict[str, Any]:
        return dict(self._universe_spec)

    def _expected_frame_fields(self) -> set[str]:
        """Columns this spec says the frame must carry (select ∪ computed aliases)."""
        expected = {str(c) for c in (self._universe_spec.get("select") or [])}
        for item in self._universe_spec.get("computed") or []:
            if isinstance(item, dict) and item.get("alias"):
                expected.add(str(item["alias"]))
            elif isinstance(item, str):
                expected.add(item)
        return expected

    def _require_api(self) -> SigmaRailApiClient:
        if self._api is None:
            msg = (
                "SigmaRailDailyScreener: SIGMARAIL_API_URL (or sigmarail-api-url parameter) is required "
                "to load universe_query_v1 via POST /v1/universe/run"
            )
            if self._algorithm:
                self._algorithm.Debug(msg)
            raise RuntimeError(msg)
        return self._api

    def load(self, start_date, end_date) -> None:
        """Bulk-load universe metrics for the full date range."""
        self._verify_service_compatibility()
        # If we have a fixed universe (manual tickers), synthesize rows without REST API
        if self._fixed_tickers:
            self._load_fixed_universe(start_date, end_date)
            return

        rows = self._query_range(start_date.isoformat(), end_date.isoformat(), max_rows=500_000)
        self._data = {}
        for row in rows:
            d = str(row.get("date", ""))[:10]
            ticker = row.get("ticker")
            if d and ticker:
                self._data.setdefault(d, {})[ticker] = row
        if self._algorithm:
            total = sum(len(v) for v in self._data.values())
            self._algorithm.Debug(
                f"daily_screener loaded: {total} rows across {len(self._data)} dates "
                f"({start_date} to {end_date})"
            )

    def _verify_service_compatibility(self) -> None:
        """Check dialect identity and record the registry digest before loading.

        ``C-API-SURFACE-V1``: the spec is only meaningful against a dialect + a field
        registry. A mismatch means this tree would validate one dialect while VeraBase
        compiles another — the failure mode that used to surface as an HTTP 422 (or,
        worse, a silently empty universe) mid-backtest.
        """
        if self._api is None:
            return
        try:
            meta = self._api.require_dialect()
        except SigmaRailApiError as exc:
            raise RuntimeError(
                f"SigmaRailDailyScreener: VeraBase compatibility check failed ({exc}); "
                "refusing to run against a mismatched service"
            ) from exc
        self.registry_digest = str(meta.get("registry_digest") or "")
        if self._algorithm:
            self._algorithm.Debug(
                "SigmaRailDailyScreener: dialect="
                f"{(meta.get('dialect') or {}).get('id')} "
                f"registry_digest={self.registry_digest}"
            )

    def _fabricated_rows_warning(self, count: int, *, dates: int) -> None:
        """Say once, loudly, that fixed-universe rows carry placeholder metrics."""
        if self._fabricated_rows_warned:
            return
        self._fabricated_rows_warned = True
        if self._algorithm:
            self._algorithm.Debug(
                "SigmaRailDailyScreener: FIXED UNIVERSE — "
                f"{count} rows across {dates} dates synthesized locally with placeholder "
                "metrics (overall_score=1.0, atr_14_pct=2.0); these are NOT warehouse "
                "values and no /v1/universe/run call was made. "
                f"tickers={self._fixed_tickers}"
            )

    def _load_fixed_universe(self, start_date, end_date) -> None:
        """Synthesize minimal rows for fixed tickers using ClickHouse for price data."""
        if not self._fixed_tickers:
            return
        # For fixed universe, we don't need screener scores - just return the tickers
        # with minimal data so get_universe() returns them
        self._data = {}
        # We'll populate minimal rows; the actual price/ATR data comes from other loaders
        # This is just so get_universe() returns the fixed tickers
        from datetime import timedelta
        current = start_date
        while current <= end_date:
            d = current.isoformat()
            day_data = {}
            for ticker in self._fixed_tickers:
                day_data[ticker] = {
                    "ticker": ticker,
                    "date": d,
                    "overall_score": 1.0,  # Default score for fixed universe
                    "atr_14_pct": 2.0,   # Default ATR
                }
            self._data[d] = day_data
            current += timedelta(days=1)
        total = sum(len(v) for v in self._data.values())
        if self._algorithm:
            self._algorithm.Debug(
                f"daily_screener fixed universe: {total} rows across {len(self._data)} dates "
                f"({start_date} to {end_date}) tickers={self._fixed_tickers}"
            )
        self._fabricated_rows_warning(total, dates=len(self._data))

    def reload_today(self, today) -> None:
        """Live: refresh today's slice only (overwrites that date key)."""
        iso = today.isoformat() if hasattr(today, "isoformat") else str(today)
        if self._fixed_tickers:
            day_data = {}
            for ticker in self._fixed_tickers:
                day_data[ticker] = {
                    "ticker": ticker,
                    "date": iso,
                    "overall_score": 1.0,
                    "atr_14_pct": 2.0,
                }
            self._data[iso] = day_data
            self._fabricated_rows_warning(len(day_data), dates=1)
            return

        rows = self._query_range(iso, iso, max_rows=50_000)
        day: dict[str, dict[str, Any]] = {}
        for row in rows:
            ticker = row.get("ticker")
            if ticker:
                day[ticker] = row
        self._data[iso] = day

    def _floor_date(self, date_str: str) -> str | None:
        """Latest loaded date at or before ``date_str`` (floor across weekends/holidays).

        ``as_of`` is ``today - 1`` — non-trading days have no screener slice, so
        exact-match reads made every Monday/post-holiday session see an empty
        universe. The floor returns the last published slice a live session
        would actually have; dates before the first loaded slice still miss.
        """
        return floor_key(self._data, date_str)

    def get_row(self, ticker: str, date_str: str) -> dict[str, Any]:
        return dict(self._data.get(self._floor_date(date_str) or "", {}).get(ticker, {}))

    def dates_by_ticker(self) -> dict[str, list[str]]:
        """``{ticker: sorted date strings}`` — for presence-interval extraction."""
        out: dict[str, list[str]] = {}
        for d, tickers in self._data.items():
            for t in tickers:
                out.setdefault(t, []).append(d)
        for dates in out.values():
            dates.sort()
        return out

    def tickers(self) -> list[str]:
        """All distinct tickers across loaded dates (sorted)."""
        out: set[str] = set()
        for tickers in self._data.values():
            out.update(tickers)
        return sorted(out)

    def get_universe(self, date_str: str) -> dict[str, float]:
        """{ticker: rank_score} for tradeable symbols (excludes SPY)."""
        rank_field = _rank_field(self._universe_spec)
        out: dict[str, float] = {}
        for t, r in self._data.get(self._floor_date(date_str) or "", {}).items():
            if t == "SPY":
                continue
            score = r.get(rank_field)
            if score is None and rank_field != "overall_score":
                score = r.get("overall_score")
            if score is None:
                continue
            try:
                out[t] = float(score)
            except (TypeError, ValueError):
                continue
        return out

    def get_atrs(self, date_str: str) -> dict[str, float]:
        return {
            t: float(r.get("atr_14_pct") or 0)
            for t, r in self._data.get(self._floor_date(date_str) or "", {}).items()
            if t != "SPY" and r.get("atr_14_pct") is not None
        }

    def get_pivots(self, date_str: str, field: str = "vcp_pivot_line") -> dict[str, float]:
        """{ticker: pivot_line} when the universe spec selects the VCP satellite's pivot.

        Empty when the spec does not select ``field`` — callers must fall back to a fixed stop.
        """
        return {
            t: float(r[field])
            for t, r in self._data.get(self._floor_date(date_str) or "", {}).items()
            if t != "SPY" and r.get(field) is not None
        }

    def get_all_rows(self, date_str: str) -> dict[str, dict[str, Any]]:
        """All rows for a date keyed by ticker (excludes SPY).

        Includes every column from the select clause. Key insertion order matches
        the SQL ``ORDER BY`` order from ``universe_run`` (Python 3.7+ dict order).
        Pyramid Alpha walks this order when hit columns are present.
        """
        rows = self._data.get(self._floor_date(date_str) or "", {})
        return {t: dict(r) for t, r in rows.items() if t != "SPY"}

    def get_sector_rows(self, date_str: str) -> dict[str, dict[str, dict]]:
        """{sector: {ticker: row}} for the given date, excluding SPY and empty sectors."""
        out: dict[str, dict[str, dict]] = {}
        for ticker, row in self._data.get(self._floor_date(date_str) or "", {}).items():
            if ticker == "SPY":
                continue
            sector = str(row.get("sector") or "").strip()
            if not sector:
                continue
            out.setdefault(sector, {})[ticker] = row
        return out

    def get_sector_rs_scores(self, date_str: str) -> dict[str, float]:
        """{sector: avg_rs_rating} from screener rows for the given date."""
        buckets: dict[str, list[float]] = {}
        for ticker, row in self._data.get(self._floor_date(date_str) or "", {}).items():
            if ticker == "SPY":
                continue
            sector = str(row.get("sector") or "").strip()
            rs = row.get("rs_rating")
            if not sector or rs is None:
                continue
            try:
                buckets.setdefault(sector, []).append(float(rs))
            except (TypeError, ValueError):
                pass
        return {s: sum(v) / len(v) for s, v in buckets.items() if v}

    def _query_range(self, start_date: str, end_date: str, max_rows: int) -> list:
        api = self._require_api()
        # Monthly chunks keep each /v1/universe/run payload small enough that a
        # 30s ClickHouse HTTP timeout cannot truncate mid-stream (6-month chunks
        # starved weekday as-of dates down to 1–9 names).
        chunks = date_range_chunks(start_date, end_date, months=1)
        all_rows: list = []
        for chunk_start, chunk_end in chunks:
            payload = {
                "start_date": chunk_start,
                "end_date": chunk_end,
                "spec": self._spec_payload(),
                "mode": "detail",
                "export_format": "objects",
                "limit": max_rows,
            }
            try:
                r = api.universe_run(payload)
            except SigmaRailApiError as exc:
                raise RuntimeError(
                    f"SigmaRailDailyScreener: universe_run failed for {chunk_start}..{chunk_end} "
                    f"({exc}); refusing to continue with a partial universe"
                ) from exc
            rows = r.get("rows")
            if not isinstance(rows, list):
                raise RuntimeError(
                    f"SigmaRailDailyScreener: universe_run returned no rows for "
                    f"{chunk_start}..{chunk_end}; refusing to continue with a partial universe"
                )
            # C-API-SURFACE-V1: the service echoes the frame it carried. If it does
            # not cover everything this spec selected/computed, the runtime would
            # evaluate its expressions against a frame that is missing columns —
            # silently (setup_col falls back, pivots come back empty).
            reported = r.get("required_fields")
            if isinstance(reported, list):
                expected = self._expected_frame_fields()
                missing = sorted(expected - set(str(x) for x in reported))
                if missing:
                    raise RuntimeError(
                        f"SigmaRailDailyScreener: frame from {chunk_start}..{chunk_end} is missing "
                        f"{missing} (spec expects {sorted(expected)}); refusing to evaluate "
                        "expressions against an incomplete frame"
                    )
            # C-API-SURFACE-V1: record what the frame actually carried.
            if not self.registry_digest:
                self.registry_digest = str(r.get("registry_digest") or "")
            frame_fields = r.get("required_fields")
            if self._algorithm:
                self._algorithm.Debug(
                    f"SigmaRailDailyScreener: universe_run {chunk_start}..{chunk_end}: "
                    f"{len(rows)} rows, registry_digest={r.get('registry_digest') or '-'}, "
                    f"frame_fields={frame_fields if isinstance(frame_fields, list) else '-'}"
                )
            all_rows.extend(rows)
        return all_rows
