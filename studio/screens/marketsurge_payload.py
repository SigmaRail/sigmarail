"""Pure helpers for MarketSurge-style chart dossier shaping.

No ClickHouse I/O — unit-testable without a live warehouse.
"""

from __future__ import annotations

from typing import Any


REVISION_CLAMP_ABS = 40.0


def clamp_revision_pct(value: float | None, *, limit: float = REVISION_CLAMP_ABS) -> float | None:
    """Hide extreme revision % (slot-roll artifacts); return display units (0–100)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # L7 stores fractions (e.g. -0.74); accept either fraction or already-percent.
    pct = v * 100.0 if abs(v) <= 1.5 else v
    if abs(pct) > limit:
        return None
    return round(pct, 1)


def attach_surprises_to_events(
    events: list[dict[str, Any]],
    actuals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join analyst_actuals surprise_pct onto earnings_events by nearest period_end."""
    if not events:
        return events
    if not actuals:
        return [{**e, "surprise_pct": e.get("surprise_pct")} for e in events]

    sorted_actuals = sorted(
        (a for a in actuals if a.get("period_end_date") and a.get("metric", "eps") == "eps"),
        key=lambda a: str(a["period_end_date"]),
    )

    out: list[dict[str, Any]] = []
    for e in events:
        date_str = str(e.get("date") or "")
        best = None
        best_delta = None
        for a in sorted_actuals:
            ped = str(a["period_end_date"])
            # Prefer period_end on or before print date within 120 days.
            if ped > date_str:
                continue
            delta = abs(
                (datetime_days(date_str) or 0) - (datetime_days(ped) or 0)
            )
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best = a
        surprise = None
        if best is not None and best_delta is not None and best_delta <= 120:
            sp = best.get("surprise_pct")
            if sp is not None:
                try:
                    fv = float(sp)
                    surprise = round(fv * 100.0 if abs(fv) <= 1.5 else fv, 1)
                except (TypeError, ValueError):
                    surprise = None
        out.append({**e, "surprise_pct": surprise})
    return out


def datetime_days(iso: str) -> int | None:
    try:
        y, m, d = iso[:10].split("-")
        import datetime as _dt

        return _dt.date(int(y), int(m), int(d)).toordinal()
    except Exception:
        return None


def _ymd(iso: str) -> tuple[int, int, int] | None:
    try:
        y, m, d = str(iso)[:10].split("-")
        return int(y), int(m), int(d)
    except (TypeError, ValueError):
        return None


def infer_fye_month(period_ends: list[str], hint: int | None = None) -> int:
    """Fiscal-year-end month. Prefer an annual-consensus hint; else Jan/Feb/Dec."""
    if hint is not None and 1 <= int(hint) <= 12:
        return int(hint)
    months = []
    for ped in period_ends:
        parsed = _ymd(ped)
        if parsed is not None:
            months.append(parsed[1])
    if 1 in months:
        return 1
    if 2 in months:
        return 2
    if 12 in months:
        return 12
    return months[-1] if months else 12


def ibd_fiscal_year_label(period_end: str, fye_month: int) -> int | None:
    """IBD Year (FYE month) label for a fiscal period-end date.

    For Jan/Feb year-ends, IBD names the year that contains 11 months of the
    fiscal year (FY ending 2026-01-31 → 2025). Other FYE months use the
    period-end calendar year.
    """
    parsed = _ymd(period_end)
    if parsed is None:
        return None
    year, _month, _day = parsed
    if fye_month <= 2:
        return year - 1
    return year


def ibd_year_from_print_date(first_date: str, fye_month: int) -> int | None:
    """Map the first print date of an annual figure onto the IBD year label.

    Jan FYE: a January print is the year just ended (2024-01-02 → 2023);
    a December print is the year about to end in January (2024-12-31 → 2024).
    """
    parsed = _ymd(first_date)
    if parsed is None:
        return None
    year, month, _day = parsed
    if fye_month <= 2:
        return year - 1 if month <= 2 else year
    if month >= fye_month:
        return year
    return year - 1


def build_annual_growth(
    *,
    street_actuals_eps: list[dict[str, Any]],
    annual_sales_rows: list[dict[str, Any]],
    cy_eps: float | None,
    ny_eps: float | None,
    cy_sales: float | None,
    ny_sales: float | None,
    cy_label: str | None = None,
    ny_label: str | None = None,
    annual_estimates_by_fy: dict[int, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Annual Year table: street EPS from actuals + Sharadar sales; CY/NY tagged e.

    ``street_actuals_eps`` items: {fiscal_year: int, eps: float}
    ``annual_sales_rows`` items: {fiscal_year: int, sales: float, sales_yoy: float|None}
    """
    by_year: dict[int, dict[str, Any]] = {}

    for row in annual_sales_rows:
        fy = int(row["fiscal_year"])
        sales = row.get("sales")
        sales_m = None
        if sales is not None:
            try:
                sv = float(sales)
                sales_m = round(sv / 1e6, 1) if sv > 1e6 else round(sv, 1)
            except (TypeError, ValueError):
                sales_m = None
        yoy = row.get("sales_yoy")
        yoy_pct = None
        if yoy is not None:
            try:
                yv = float(yoy)
                yoy_pct = round(yv * 100.0 if abs(yv) < 5 else yv, 1)
            except (TypeError, ValueError):
                yoy_pct = None
        eps_sec = row.get("eps")
        eps_val = None
        if eps_sec is not None:
            try:
                eps_val = round(float(eps_sec), 2)
            except (TypeError, ValueError):
                eps_val = None

        by_year[fy] = {
            "year": str(fy),
            "eps": None,
            "eps_actual": None,
            "eps": eps_val,
            "eps_actual": eps_val,
            "eps_estimate": None,
            "eps_beat_miss": None,
            "eps_chg_pct": None,
            "sales_m": sales_m,
            "sales_actual": sales_m,
            "sales_estimate": None,
            "sales_beat_miss": None,
            "sales_chg_pct": yoy_pct,
            "is_estimate": False,
        }

    for row in street_actuals_eps:
        fy = int(row["fiscal_year"])
        eps = row.get("eps")
        entry = by_year.setdefault(
            fy,
            {
                "year": str(fy),
                "eps": None,
                "eps_actual": None,
                "eps_estimate": None,
                "eps_beat_miss": None,
                "eps_chg_pct": None,
                "sales_m": None,
                "sales_actual": None,
                "sales_estimate": None,
                "sales_beat_miss": None,
                "sales_chg_pct": None,
                "is_estimate": False,
            },
        )
        if eps is not None:
            try:
                val = round(float(eps), 2)
                entry["eps"] = val
                entry["eps_actual"] = val
                # Keep street actuals if available; if SEC EPS is present and radically divergent (e.g. unadjusted mid-year stock split), prioritize SEC
                sec_val = entry.get("eps_actual")
                if sec_val is None or abs(sec_val) < 0.05 or abs(val - sec_val) / max(1.0, abs(sec_val)) < 3.0:
                    entry["eps"] = val
                    entry["eps_actual"] = val
            except (TypeError, ValueError):
                pass

    years_sorted = sorted(by_year.keys())
    prev_eps = None
    for fy in years_sorted:
        entry = by_year[fy]
        if entry["eps"] is not None and prev_eps not in (None, 0):
            entry["eps_chg_pct"] = round((entry["eps"] - prev_eps) / abs(prev_eps) * 100.0, 1)
        if entry["eps"] is not None:
            prev_eps = entry["eps"]

    result = [by_year[fy] for fy in years_sorted]

    if annual_estimates_by_fy:
        for entry in result:
            try:
                fy = int(str(entry.get("year") or "").rstrip("eE"))
            except (ValueError, TypeError):
                continue
            est_data = annual_estimates_by_fy.get(fy)
            if not est_data:
                continue
            if entry.get("eps_estimate") is None and est_data.get("eps_est") is not None:
                entry["eps_estimate"] = round(float(est_data["eps_est"]), 2)
            if entry.get("sales_estimate") is None and est_data.get("sales_est") is not None:
                entry["sales_estimate"] = round(float(est_data["sales_est"]), 1)
            if entry.get("eps_actual") is not None and entry.get("eps_estimate") is not None:
                if entry["eps_actual"] > entry["eps_estimate"]:
                    entry["eps_beat_miss"] = "beat"
                elif entry["eps_actual"] < entry["eps_estimate"]:
                    entry["eps_beat_miss"] = "miss"
                else:
                    entry["eps_beat_miss"] = "in_line"
            if entry.get("sales_actual") is not None and entry.get("sales_estimate") is not None:
                if entry["sales_actual"] > entry["sales_estimate"]:
                    entry["sales_beat_miss"] = "beat"
                elif entry["sales_actual"] < entry["sales_estimate"]:
                    entry["sales_beat_miss"] = "miss"
                else:
                    entry["sales_beat_miss"] = "in_line"

    def _sales_m(v: float | None) -> float | None:
        if v is None:
            return None
        try:
            sv = float(v)
            return round(sv / 1e6, 1) if sv > 1e6 else round(sv, 1)
        except (TypeError, ValueError):
            return None

    existing_years = {str(r["year"]) for r in result}

    def _append_estimate(label: str | None, fallback: str, eps: float | None, sales: float | None) -> None:
        if eps is None and sales is None:
            return
        year = str(label or fallback).rstrip("eE")
        if year in existing_years:
            return
        existing_years.add(year)
        eps_est = round(float(eps), 2) if eps is not None else None
        sales_est = _sales_m(sales)
        result.append(
            {
                "year": year,
                "eps": eps_est,
                "eps_actual": None,
                "eps_estimate": eps_est,
                "eps_beat_miss": None,
                "eps_chg_pct": None,
                "sales_m": sales_est,
                "sales_actual": None,
                "sales_estimate": sales_est,
                "sales_beat_miss": None,
                "sales_chg_pct": None,
                "is_estimate": True,
            }
        )

    _append_estimate(cy_label, "CY", cy_eps, cy_sales)
    _append_estimate(ny_label, "NY", ny_eps, ny_sales)

    prev_eps = None
    prev_sales = None
    for entry in result:
        if entry["eps"] is not None and prev_eps not in (None, 0) and entry["eps_chg_pct"] is None:
            entry["eps_chg_pct"] = round((entry["eps"] - prev_eps) / abs(prev_eps) * 100.0, 1)
        if entry["eps"] is not None:
            prev_eps = entry["eps"]
        if entry["sales_m"] is not None and prev_sales not in (None, 0) and entry["sales_chg_pct"] is None:
            entry["sales_chg_pct"] = round((entry["sales_m"] - prev_sales) / abs(prev_sales) * 100.0, 1)
        if entry["sales_m"] is not None:
            prev_sales = entry["sales_m"]

    # Keep last ~10 rows for rail density
    return result[-10:]


def merge_forward_estimates(
    quarterly: list[dict[str, Any]],
    *,
    cq_eps: float | None,
    nq_eps: float | None,
    cq_sales: float | None,
    nq_sales: float | None,
    cq_period_end: str | None,
    nq_period_end: str | None,
    max_reported: int = 8,
) -> list[dict[str, Any]]:
    """Keep last 8 reported quarters + append CQ/NQ estimate columns."""
    """Keep last N reported quarters + append CQ/NQ estimate columns."""
    reported = [q for q in quarterly if not q.get("is_estimate")]
    # quarterly_growth is newest-first from introspection; normalize to oldest-first for bar.
    # Callers may pass either order — sort by report_date ascending for the strip.
    reported_sorted = sorted(reported, key=lambda q: str(q.get("report_date") or ""))
    last8 = reported_sorted[-8:]
    last_reported = reported_sorted[-max_reported:] if max_reported > 0 else reported_sorted

    def _est_col(period_end: str | None, eps: float | None, sales: float | None) -> dict[str, Any] | None:
        if period_end is None and eps is None and sales is None:
            return None
        sales_m = None
        if sales is not None:
            try:
                sv = float(sales)
                sales_m = round(sv / 1e6, 1) if sv > 1e6 else round(sv, 1)
            except (TypeError, ValueError):
                sales_m = None
        eps_val = round(float(eps), 2) if eps is not None else None
        return {
            "report_date": period_end or "",
            "eps": eps_val,
            "eps_actual": None,
            "eps_estimate": eps_val,
            "eps_surprise_dollar": None,
            "eps_surprise_pct": None,
            "eps_beat_miss": None,
            "eps_growth_yoy": None,
            "revenue_m": sales_m,
            "revenue_actual": None,
            "revenue_estimate": sales_m,
            "revenue_surprise_m": None,
            "revenue_surprise_pct": None,
            "revenue_beat_miss": None,
            "revenue_growth_yoy": None,
            "gross_margin_pct": None,
            "net_margin_pct": None,
            "is_estimate": True,
            "surprise_pct": None,
        }

    out = [{**q, "is_estimate": False} for q in last8]
    out = [{**q, "is_estimate": False} for q in last_reported]
    cq = _est_col(cq_period_end, cq_eps, cq_sales)
    nq = _est_col(nq_period_end, nq_eps, nq_sales)
    if cq:
        out.append(cq)
    if nq:
        out.append(nq)
    return out


def overlay_street_eps(
    quarterly: list[dict[str, Any]],
    actuals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace GAAP mrq EPS & sales with nearest street analyst_actuals.reported."""
    if not quarterly:
        return quarterly

    def _init_row(q: dict[str, Any]) -> dict[str, Any]:
        row = dict(q)
        row.setdefault("eps_actual", row.get("eps"))
        row.setdefault("eps_estimate", None)
        row.setdefault("eps_surprise_dollar", None)
        row.setdefault("eps_surprise_pct", row.get("surprise_pct"))
        row.setdefault("eps_beat_miss", None)
        row.setdefault("revenue_actual", row.get("revenue_m"))
        row.setdefault("revenue_estimate", None)
        row.setdefault("revenue_surprise_m", None)
        row.setdefault("revenue_surprise_pct", None)
        row.setdefault("revenue_beat_miss", None)
        return row

    if not actuals:
        return [_init_row(q) for q in quarterly]

    out: list[dict[str, Any]] = []
    for q in quarterly:
        row = _init_row(q)
        date_str = str(row.get("report_date") or "")
        best_eps = None
        best_eps_delta = None
        best_sales = None
        best_sales_delta = None

        for a in actuals:
            ped = str(a.get("period_end_date") or "")
            if not ped:
                continue
            delta = abs((datetime_days(date_str) or 0) - (datetime_days(ped) or 0))
            if delta > 75:
                continue
            metric = a.get("metric", "eps")
            if metric == "eps":
                if best_eps_delta is None or delta < best_eps_delta:
                    best_eps_delta = delta
                    best_eps = a
            elif metric == "sales":
                if best_sales_delta is None or delta < best_sales_delta:
                    best_sales_delta = delta
                    best_sales = a

        if best_eps is not None and best_eps_delta is not None and best_eps_delta <= 120:
            if best_eps.get("reported") is not None:
                try:
                    act_v = round(float(best_eps["reported"]), 2)
                    row["eps"] = act_v
                    row["eps_actual"] = act_v
                except (TypeError, ValueError):
                    pass
            if best_eps.get("estimate_at_print") is not None:
                try:
                    est_v = round(float(best_eps["estimate_at_print"]), 2)
                    row["eps_estimate"] = est_v
                except (TypeError, ValueError):
                    pass
            if row.get("eps_actual") is not None and row.get("eps_estimate") is not None:
                row["eps_surprise_dollar"] = round(row["eps_actual"] - row["eps_estimate"], 2)
                if row["eps_actual"] > row["eps_estimate"]:
                    row["eps_beat_miss"] = "beat"
                elif row["eps_actual"] < row["eps_estimate"]:
                    row["eps_beat_miss"] = "miss"
                else:
                    row["eps_beat_miss"] = "in_line"
            sp = best_eps.get("surprise_pct")
            if sp is not None:
                try:
                    fv = float(sp)
                    surp_val = round(fv * 100.0 if abs(fv) <= 1.5 else fv, 1)
                    row["surprise_pct"] = surp_val
                    row["eps_surprise_pct"] = surp_val
                except (TypeError, ValueError):
                    pass

        if best_sales is not None and best_sales_delta is not None and best_sales_delta <= 120:
            if best_sales.get("reported") is not None:
                try:
                    sv = float(best_sales["reported"])
                    act_m = round(sv / 1e6, 1) if sv > 1e6 else round(sv, 1)
                    row["revenue_m"] = act_m
                    row["revenue_actual"] = act_m
                except (TypeError, ValueError):
                    pass
            if best_sales.get("estimate_at_print") is not None:
                try:
                    ev = float(best_sales["estimate_at_print"])
                    est_m = round(ev / 1e6, 1) if ev > 1e6 else round(ev, 1)
                    row["revenue_estimate"] = est_m
                except (TypeError, ValueError):
                    pass
            if row.get("revenue_actual") is not None and row.get("revenue_estimate") is not None:
                row["revenue_surprise_m"] = round(row["revenue_actual"] - row["revenue_estimate"], 1)
                if row["revenue_actual"] > row["revenue_estimate"]:
                    row["revenue_beat_miss"] = "beat"
                elif row["revenue_actual"] < row["revenue_estimate"]:
                    row["revenue_beat_miss"] = "miss"
                else:
                    row["revenue_beat_miss"] = "in_line"
            ssp = best_sales.get("surprise_pct")
            if ssp is not None:
                try:
                    fv = float(ssp)
                    row["revenue_surprise_pct"] = round(fv * 100.0 if abs(fv) <= 1.5 else fv, 1)
                except (TypeError, ValueError):
                    pass

        out.append(row)
    return out


def overlay_street_eps_on_events(
    events: list[dict[str, Any]],
    actuals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Set event eps + surprise from street actuals (same nearest-period join)."""
    enriched = attach_surprises_to_events(events, actuals)
    if not actuals:
        return enriched
    out: list[dict[str, Any]] = []
    for e in enriched:
        date_str = str(e.get("date") or "")
        best = None
        best_delta = None
        for a in actuals:
            ped = str(a.get("period_end_date") or "")
            if not ped or ped > date_str:
                continue
            delta = abs((datetime_days(date_str) or 0) - (datetime_days(ped) or 0))
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best = a
        row = dict(e)
        if best is not None and best_delta is not None and best_delta <= 120:
            try:
                row["eps"] = round(float(best["reported"]), 2)
            except (TypeError, ValueError, KeyError):
                pass
        out.append(row)
    return out


def rollup_street_annual_eps(
    actuals: list[dict[str, Any]],
    fye_month: int | None = None,
) -> list[dict[str, Any]]:
    """Sum four street EPS quarters that end on the company's fiscal year-end.

    Incomplete current-year quarters are omitted (not a trailing-twelve-month
    lump). Year labels follow IBD Year (FYE month). Skips a fiscal year if any
    quarter-to-quarter ratio shock exceeds 3× (split discontinuity guard).
    """
    rows = sorted(
        (
            a
            for a in actuals
            if a.get("period_end_date") is not None and a.get("reported") is not None
        ),
        key=lambda a: str(a["period_end_date"]),
    )
    if not rows:
        return []
    fye = infer_fye_month([str(r["period_end_date"]) for r in rows], fye_month)
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        parsed = _ymd(str(row["period_end_date"]))
        if parsed is None or parsed[1] != fye or i < 3:
            continue
        window = rows[i - 3 : i + 1]
        try:
            vals = [float(w["reported"]) for w in window]
            shocked = False
            for a, b in zip(vals, vals[1:]):
                if a == 0 or b == 0:
                    continue
                ratio = abs(b / a)
                if (abs(a) >= 1.0 or abs(b) >= 1.0) and (ratio > 3.0 or ratio < (1.0 / 3.0)):
                    shocked = True
                    break
            if shocked:
                continue
            total = sum(vals)
        except (TypeError, ValueError):
            continue
        ped = str(window[-1]["period_end_date"])[:10]
        fy = ibd_fiscal_year_label(ped, fye)
        if fy is None:
            continue
        out.append({"fiscal_year": fy, "eps": round(total, 2), "period_end_date": ped})
    return out


def enrich_as_of_kpis_street(
    as_of: dict[str, Any],
    es: dict[str, Any] | None,
    tickers_meta: dict[str, Any] | None = None,
    valuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge street consensus + ticker/valuation fields into as_of_kpis."""
    out = dict(as_of)
    if es:
        for key in (
            "eps_cq_mean",
            "eps_nq_mean",
            "eps_cy_mean",
            "eps_ny_mean",
            "sales_cq_mean",
            "sales_nq_mean",
            "sales_cy_mean",
            "sales_ny_mean",
            "eps_last_surprise_pct",
            "eps_cq_rev_pct_90d",
            "eps_nq_rev_pct_90d",
            "eps_cy_rev_pct_90d",
            "eps_ny_rev_pct_90d",
            "sales_nq_rev_pct_90d",
            "sales_ny_rev_pct_90d",
            "eps_last_reported",
            "eps_last_estimate",
            "eps_beat_flag",
            "sales_last_reported",
            "sales_last_estimate",
            "sales_last_surprise_pct",
            "sales_beat_flag",
        ):
            if key in es and es[key] is not None:
                out[key] = es[key]
        # Display-ready clamped revisions (percent)
        out["eps_cy_rev_pct_90d_display"] = clamp_revision_pct(es.get("eps_cy_rev_pct_90d"))
        out["eps_ny_rev_pct_90d_display"] = clamp_revision_pct(es.get("eps_ny_rev_pct_90d"))
        out["sales_ny_rev_pct_90d_display"] = clamp_revision_pct(es.get("sales_ny_rev_pct_90d"))
        last_surp = es.get("eps_last_surprise_pct")
        if last_surp is not None:
            try:
                fv = float(last_surp)
                out["eps_last_surprise_pct_display"] = round(
                    fv * 100.0 if abs(fv) <= 1.5 else fv, 1
                )
            except (TypeError, ValueError):
                pass
        last_sales_surp = es.get("sales_last_surprise_pct")
        if last_sales_surp is not None:
            try:
                fv = float(last_sales_surp)
                out["sales_last_surprise_pct_display"] = round(
                    fv * 100.0 if abs(fv) <= 1.5 else fv, 1
                )
            except (TypeError, ValueError):
                pass
    if tickers_meta:
        if tickers_meta.get("firstpricedate"):
            out["ipo_date"] = tickers_meta["firstpricedate"]
        if tickers_meta.get("location"):
            out["hq_location"] = tickers_meta["location"]
    if valuation:
        if valuation.get("marketcap") is not None:
            out["marketcap"] = valuation["marketcap"]
        if valuation.get("pe") is not None:
            out["pe"] = valuation["pe"]
        if valuation.get("ps") is not None:
            out["ps"] = valuation["ps"]
    return out
