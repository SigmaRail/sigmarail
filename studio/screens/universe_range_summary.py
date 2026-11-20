"""SigmaRail-native universe membership aggregation over a date range."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from screens.ir_preview import validate_universe_ir_spec


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


def summarize_universe_range(
    client: Any,
    *,
    spec: dict[str, Any],
    start_date: str,
    end_date: str,
    include_weekly_samples: bool = False,
) -> dict[str, Any]:
    """Return per-day member counts using Core's schema-validated aggregate query."""
    validate_universe_ir_spec(spec)
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    from sigmarail.universe import universe_membership_counts, universe_membership_samples

    rows = universe_membership_counts(
        spec,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        client=client,
    )
    dates = [row["date"] for row in rows]
    counts = [int(row["count"]) for row in rows]

    weekly_samples: list[dict[str, Any]] = []
    if include_weekly_samples:
        sample_days = _weekly_sample_dates(dates)
        if sample_days:
            samples = universe_membership_samples(
                spec,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                sample_dates=sample_days,
                client=client,
            )
            by_day: dict[str, list[str]] = {d: [] for d in sample_days}
            for sample in samples:
                day_s = sample["date"]
                tickers = by_day.setdefault(day_s, [])
                if len(tickers) < 8:
                    tickers.append(sample["ticker"])
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
    """Count in-range membership days by ticker with optional ticker restriction."""
    validate_universe_ir_spec(spec)
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(asof)
    if end < start:
        raise ValueError("asof must be on or after start_date")

    from sigmarail.universe import universe_membership_by_ticker

    return universe_membership_by_ticker(
        spec,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        tickers=tickers,
        client=client,
    )


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
