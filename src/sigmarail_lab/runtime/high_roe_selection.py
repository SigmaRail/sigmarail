"""High-ROE large-cap rolling cohort selection (L7 + Sharadar daily/tickers, no Lean import)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable


DebugLog = Callable[[str], None] | None


def fetch_high_roe_candidates(
    client: Any,
    as_of: date,
    *,
    min_market_cap_millions: float = 500.0,
    timeout: float = 90.0,
) -> list[dict[str, Any]]:
    """
    Point-in-time candidates from L7 price/fundamentals plus Sharadar ``daily`` / ``tickers``.

    Sharadar ``marketcap`` is in millions; QC used absolute USD (5e8 → 500).
    Dollar volume is ``close * volume`` (no zipper 20d average).
    """
    sql = f"""
    SELECT
        px.ticker AS ticker,
        fd.mrt_roe AS mrt_roe,
        d.marketcap AS marketcap,
        px.close AS close,
        (px.close * px.volume) AS dollar_volume,
        t.firstadded AS firstadded
    FROM screener_price_tech_daily AS px FINAL
    LEFT ANY JOIN screener_fundamentals_daily AS fd FINAL
      ON px.ticker = fd.ticker AND px.date = fd.date
    LEFT ANY JOIN daily AS d FINAL
      ON px.ticker = d.ticker AND px.date = d.date
    LEFT ANY JOIN tickers AS t FINAL
      ON px.ticker = t.ticker
    WHERE px.date = (
        SELECT max(date) FROM screener_price_tech_daily WHERE date <= '{as_of.isoformat()}'
    )
      AND t.isdelisted != 'Y'
      AND t.category LIKE '%Common Stock%'
      AND d.marketcap > {float(min_market_cap_millions)}
      AND px.close > 0
      AND isFinite(fd.mrt_roe)
      AND t.firstadded != ''
      AND (px.close * px.volume) > 0
    SETTINGS max_execution_time = 60
    """
    return list(client.query_json_each_row(sql, timeout=timeout) or [])


def select_new_high_roe_names(
    rows: list[dict[str, Any]],
    as_of: date,
    previous_tickers: set[str],
    *,
    n_new: int = 2,
    min_ipo_days: int = 180,
) -> list[dict[str, Any]]:
    """
    QC Strategies #312-style pick: liquid 90th pct by dollar volume, then top ``n_new`` by ROE,
    excluding names already in the rolling cohort.
    """
    filtered: list[dict[str, Any]] = []
    for r in rows:
        ticker = str(r.get("ticker") or "").upper()
        if not ticker or ticker in previous_tickers:
            continue
        try:
            first_added = datetime.strptime(str(r["firstadded"])[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if (as_of - first_added).days <= min_ipo_days:
            continue
        try:
            filtered.append(
                {
                    "ticker": ticker,
                    "roe": float(r["mrt_roe"]),
                    "dollar_volume": float(r["dollar_volume"]),
                }
            )
        except (TypeError, ValueError):
            continue

    if len(filtered) < n_new:
        return []

    sorted_by_volume = sorted(filtered, key=lambda x: x["dollar_volume"])
    keep_n = max(n_new, int(0.9 * len(sorted_by_volume)))
    top_volume = sorted_by_volume[-keep_n:]
    sorted_by_roe = sorted(top_volume, key=lambda x: x["roe"])
    return sorted_by_roe[-n_new:]


class HighRoeRollingCohort:
    """Stateful 12-month rolling cohort (up to ``n_new * 12`` names)."""

    def __init__(
        self,
        *,
        n_new: int = 2,
        min_market_cap_millions: float = 500.0,
        min_ipo_days: int = 180,
        debug: DebugLog = None,
    ) -> None:
        self.n_new = int(n_new)
        self.min_market_cap_millions = float(min_market_cap_millions)
        self.min_ipo_days = int(min_ipo_days)
        self._debug = debug
        self._cohorts: list[list[str]] = []
        self._last_select_month: tuple[int, int] | None = None

    @property
    def active_tickers(self) -> list[str]:
        out: list[str] = []
        for c in self._cohorts:
            out.extend(c)
        return out

    def maybe_select(self, client: Any, as_of: date) -> list[str]:
        """On first call each calendar month, add ``n_new`` names; return full active list."""
        month_key = (as_of.year, as_of.month)
        if self._last_select_month == month_key:
            return self.active_tickers

        previous = set(self.active_tickers)
        rows = fetch_high_roe_candidates(
            client,
            as_of,
            min_market_cap_millions=self.min_market_cap_millions,
        )
        picks = select_new_high_roe_names(
            rows,
            as_of,
            previous,
            n_new=self.n_new,
            min_ipo_days=self.min_ipo_days,
        )
        self._last_select_month = month_key
        if not picks:
            if self._debug:
                self._debug(f"HighRoe {as_of}: no new picks (candidates={len(rows)})")
            return self.active_tickers

        tickers = [p["ticker"] for p in picks]
        self._cohorts.append(tickers)
        self._cohorts = self._cohorts[-12:]
        active = self.active_tickers
        if self._debug:
            detail = ", ".join(f"{p['ticker']}(roe={p['roe']:.3f})" for p in picks)
            self._debug(f"HighRoe {as_of}: +[{detail}] cohort_n={len(active)}")
        return active
