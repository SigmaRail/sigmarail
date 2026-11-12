"""Aggregated universe membership over a date range (A0 preview)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from screens.ir_preview import validate_universe_ir_spec

# No range-width cap: the summary is one aggregate query, and how much history to chart
# is the caller's choice.
_QUERY_SETTINGS = (
    " SETTINGS allow_experimental_analyzer = 0,"
    " join_algorithm = 'grace_hash',"
    " max_execution_time = 30,"
    " max_rows_to_read = 500000000,"
    " timeout_before_checking_execution_speed = 0"
)


def _parse_iso_date(value: str) -> date:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("date is required")
    return date.fromisoformat(raw[:10])


def _weekly_sample_dates(dates: list[str], *, max_weeks: int = 12) -> list[str]:
    if not dates:
        return []
    if len(dates) <= max_weeks:
        return dates
    step = max(1, len(dates) // max_weeks)
    sampled = [dates[i] for i in range(0, len(dates), step)]
    if dates[-1] not in sampled:
        sampled.append(dates[-1])
    return sampled[:max_weeks]


def _lean_membership_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop ranking/computed work — membership count is WHERE-only."""
    lean = dict(spec)
    lean["select"] = ["ticker", "date"]
    # Schema requires ≥1 order_by item; ticker is cheapest (unused when for_aggregate).
    lean["order_by"] = [{"field": "ticker", "direction": "asc"}]
    lean.pop("computed", None)
    lean["limit_per_day"] = 5000
    return lean


def summarize_universe_range(
    client: Any,
    *,
    spec: dict[str, Any],
    start_date: str,
    end_date: str,
    include_weekly_samples: bool = False,
) -> dict[str, Any]:
    """Return per-day member counts for a universe_query_v1 spec (aggregated CH query).

    Uses the aggregate compile path (no ORDER BY / LIMIT BY). Weekly ticker
    samples are opt-in — they re-scan the range and are unused by the probe chart.
    """
    validate_universe_ir_spec(spec)
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    from vera_query_core.ir.universe_query_v1 import (
        UniverseQueryV1,
        compile_universe_query_v1_range_param,
        strip_trailing_sql_settings,
    )

    count_spec = _lean_membership_spec(spec)
    uq = UniverseQueryV1.model_validate(count_spec)
    inner_sql, params = compile_universe_query_v1_range_param(uq, for_aggregate=True)
    inner_sql = strip_trailing_sql_settings(inner_sql)
    params = dict(params)
    params["start"] = start.isoformat()
    params["end"] = end.isoformat()

    summary_sql = f"""
        SELECT toString(u.date) AS day, count() AS member_count
        FROM (
            {inner_sql}
        ) AS u
        GROUP BY u.date
        ORDER BY u.date
        {_QUERY_SETTINGS}
    """
    rows = client.query(summary_sql, parameters=params)
    dates: list[str] = []
    counts: list[int] = []
    for row in rows.result_rows:
        day, cnt = row[0], int(row[1])
        dates.append(str(day))
        counts.append(cnt)

    weekly_samples: list[dict[str, Any]] = []
    if include_weekly_samples:
        sample_days = _weekly_sample_dates(dates)
        if sample_days:
            # Samples need tickers; reuse lean inner (still no ranking sort).
            top_sql = f"""
                SELECT toString(u.date) AS day, u.ticker
                FROM (
                    {inner_sql}
                ) AS u
                WHERE toString(u.date) IN {{sample_days:Array(String)}}
                ORDER BY u.date, u.ticker
                LIMIT 500
                {_QUERY_SETTINGS}
            """
            top_rows = client.query(
                top_sql,
                parameters={**params, "sample_days": sample_days},
            )
            by_day: dict[str, list[str]] = {d: [] for d in sample_days}
            for day, ticker in top_rows.result_rows:
                day_s = str(day)
                tickers = by_day.setdefault(day_s, [])
                if len(tickers) < 8:
                    tickers.append(str(ticker))
            for day in sample_days:
                weekly_samples.append({"date": day, "sample_tickers": by_day.get(day, [])})

    total_members = sum(counts)
    avg_count = (total_members / len(counts)) if counts else 0.0
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "dates": dates,
        "member_counts": counts,
        "summary": {
            "trading_days": len(dates),
            "avg_members_per_day": round(avg_count, 2),
            "min_members_per_day": min(counts) if counts else 0,
            "max_members_per_day": max(counts) if counts else 0,
        },
        "weekly_samples": weekly_samples,
    }


def membership_tenure_by_ticker(
    client: Any,
    *,
    spec: dict[str, Any],
    start_date: str,
    asof: str,
    tickers: list[str] | None = None,
) -> dict[str, int]:
    """NTH-2: days-in-window pass counts per ticker (uncapped hist, same WHERE as range).

    Optional ``tickers`` restricts the join to asof members (smaller result).
    """
    validate_universe_ir_spec(spec)
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(asof)
    if end < start:
        raise ValueError("asof must be on or after start_date")

    from vera_query_core.ir.universe_query_v1 import (
        UniverseQueryV1,
        compile_universe_query_v1_range_param,
        strip_trailing_sql_settings,
    )

    count_spec = _lean_membership_spec(spec)
    uq = UniverseQueryV1.model_validate(count_spec)
    inner_sql, params = compile_universe_query_v1_range_param(uq, for_aggregate=True)
    inner_sql = strip_trailing_sql_settings(inner_sql)
    params = dict(params)
    params["start"] = start.isoformat()
    params["end"] = end.isoformat()

    ticker_filter = ""
    if tickers:
        clean = [str(t).strip().upper() for t in tickers if str(t).strip()][:5000]
        if clean:
            params["tenure_tickers"] = clean
            ticker_filter = " WHERE u.ticker IN {tenure_tickers:Array(String)}"

    sql = f"""
        SELECT u.ticker AS ticker, count() AS days_in_universe
        FROM (
            {inner_sql}
        ) AS u
        {ticker_filter}
        GROUP BY u.ticker
        LIMIT 10000
        {_QUERY_SETTINGS}
    """
    rows = client.query(sql, parameters=params)
    out: dict[str, int] = {}
    for ticker, days in rows.result_rows:
        out[str(ticker).upper()] = int(days)
    return out


def default_range_end_start(*, end_date: str, trading_days: int = 252) -> tuple[str, str]:
    """Fallback when client omits start: approximate calendar span for ~1Y."""
    end = _parse_iso_date(end_date)
    start = end - timedelta(days=int(trading_days * 1.45))
    return start.isoformat(), end.isoformat()


__all__ = [
    "default_range_end_start",
    "membership_tenure_by_ticker",
    "summarize_universe_range",
]
