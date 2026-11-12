"""Unit tests for MarketSurge payload helpers (no ClickHouse)."""

from __future__ import annotations

from screens.marketsurge_payload import (
    attach_surprises_to_events,
    build_annual_growth,
    clamp_revision_pct,
    enrich_as_of_kpis_street,
    ibd_fiscal_year_label,
    ibd_year_from_print_date,
    merge_forward_estimates,
    overlay_street_eps,
    rollup_street_annual_eps,
)


def test_clamp_revision_hides_extreme_fractions():
    assert clamp_revision_pct(-0.74) is None  # -74% > 40
    assert clamp_revision_pct(-0.20) == -20.0
    assert clamp_revision_pct(0.35) == 35.0
    assert clamp_revision_pct(None) is None


def test_clamp_revision_accepts_already_percent():
    assert clamp_revision_pct(-15.0) == -15.0
    assert clamp_revision_pct(50.0) is None


def test_build_annual_growth_street_not_gaap_and_estimates():
    sales = [
        {"fiscal_year": 2023, "sales": 2_000_000_000, "sales_yoy": 0.25},
        {"fiscal_year": 2024, "sales": 2_500_000_000, "sales_yoy": 0.25},
    ]
    street = [
        {"fiscal_year": 2023, "eps": 0.90},
        {"fiscal_year": 2024, "eps": 1.10},
    ]
    rows = build_annual_growth(
        street_actuals_eps=street,
        annual_sales_rows=sales,
        cy_eps=1.25,
        ny_eps=1.80,
        cy_sales=3_000_000_000,
        ny_sales=3_600_000_000,
        cy_label="2025",
        ny_label="2026",
    )
    assert rows[-2]["year"] == "2025"
    assert rows[-2]["is_estimate"] is True
    assert rows[-2]["eps"] == 1.25
    assert rows[-2]["eps_chg_pct"] == 13.6  # (1.25-1.10)/1.10
    assert rows[-1]["eps"] == 1.80
    assert rows[-1]["year"] == "2026"
    fy24 = next(r for r in rows if r["year"] == "2024")
    assert fy24["eps"] == 1.10
    assert fy24["eps_chg_pct"] == 22.2  # (1.10-0.90)/0.90


def test_attach_surprises_nearest_period_end():
    events = [
        {"date": "2024-08-28", "eps": 0.99, "is_future": False},
        {"date": "2024-11-26", "eps": 1.03, "is_future": False},
    ]
    actuals = [
        {"period_end_date": "2024-07-31", "surprise_pct": 0.12},
        {"period_end_date": "2024-10-31", "surprise_pct": -0.05},
    ]
    out = attach_surprises_to_events(events, actuals)
    assert out[0]["surprise_pct"] == 12.0
    assert out[1]["surprise_pct"] == -5.0


def test_merge_forward_estimates_keeps_last_8_plus_2():
    quarterly = [
        {
            "report_date": f"202{i // 4}-{(i % 4) * 3 + 1:02d}-15",
            "eps": float(i),
            "revenue_m": 100.0 + i,
            "eps_growth_yoy": 10.0,
            "revenue_growth_yoy": 5.0,
            "gross_margin_pct": None,
            "net_margin_pct": None,
        }
        for i in range(12)
    ]
    merged = merge_forward_estimates(
        quarterly,
        cq_eps=1.5,
        nq_eps=1.7,
        cq_sales=500_000_000,
        nq_sales=520_000_000,
        cq_period_end="2025-04-30",
        nq_period_end="2025-07-31",
    )
    assert len(merged) == 10
    assert sum(1 for q in merged if q.get("is_estimate")) == 2
    assert merged[-2]["eps"] == 1.5
    assert merged[-1]["is_estimate"] is True


def test_overlay_street_eps_replaces_gaap():
    quarterly = [{"report_date": "2025-02-26", "eps": 1.76, "revenue_m": 100.0}]
    actuals = [{"period_end_date": "2025-01-31", "reported": 1.62, "surprise_pct": 0.05}]
    out = overlay_street_eps(quarterly, actuals)
    assert out[0]["eps"] == 1.62
    assert out[0]["surprise_pct"] == 5.0


def test_rollup_street_annual_eps_sums_four_quarters():
    actuals = [
        {"period_end_date": "2024-04-30", "reported": 0.93},
        {"period_end_date": "2024-07-31", "reported": 1.04},
        {"period_end_date": "2024-10-31", "reported": 0.93},
        {"period_end_date": "2025-01-31", "reported": 1.03},
        {"period_end_date": "2025-04-30", "reported": 0.73},
        {"period_end_date": "2025-07-31", "reported": 0.93},
        {"period_end_date": "2025-10-31", "reported": 0.96},
        {"period_end_date": "2026-01-31", "reported": 1.12},
    ]
    rows = rollup_street_annual_eps(actuals, fye_month=1)
    assert rows[0]["fiscal_year"] == 2024  # IBD Year (Jan): FY ending 2025-01-31
    assert rows[0]["eps"] == 3.93  # 0.93+1.04+0.93+1.03
    assert rows[-1]["fiscal_year"] == 2025
    assert rows[-1]["eps"] == 3.74


def test_rollup_skips_split_shock_window():
    actuals = [
        {"period_end_date": "2024-01-31", "reported": 6.12},
        {"period_end_date": "2024-04-30", "reported": 0.68},
        {"period_end_date": "2024-07-31", "reported": 0.70},
        {"period_end_date": "2024-10-31", "reported": 0.75},
    ]
    rows = rollup_street_annual_eps(actuals)
    assert rows == []


def test_enrich_as_of_kpis_street_clamps_and_ipo():
    as_of = {"close": 100.0, "rs_rating": 90}
    es = {
        "eps_cy_mean": 1.25,
        "eps_cy_rev_pct_90d": -0.05,
        "eps_cq_rev_pct_90d": -0.74,
        "eps_last_surprise_pct": 0.08,
    }
    tickers = {"firstpricedate": "2019-06-12", "location": "Austin, TX"}
    out = enrich_as_of_kpis_street(as_of, es, tickers, {"marketcap": 1e11, "pe": 40.0})
    assert out["eps_cy_mean"] == 1.25
    assert out["eps_cy_rev_pct_90d_display"] == -5.0
    assert out["ipo_date"] == "2019-06-12"
    assert out["marketcap"] == 1e11
    assert out["eps_last_surprise_pct_display"] == 8.0


def test_ibd_year_jan_fye_uses_prior_calendar_year():
    assert ibd_fiscal_year_label("2026-01-31", 1) == 2025
    assert ibd_fiscal_year_label("2025-01-31", 1) == 2024
    assert ibd_fiscal_year_label("2025-12-31", 12) == 2025


def test_ibd_print_date_jan_fye_does_not_collide_on_calendar_year():
    assert ibd_year_from_print_date("2024-01-02", 1) == 2023
    assert ibd_year_from_print_date("2024-12-31", 1) == 2024
    assert ibd_year_from_print_date("2023-01-03", 1) == 2022
    assert ibd_year_from_print_date("2025-12-31", 1) == 2025


def test_rollup_aligns_to_fye_not_trailing_ttm():
    """DELL-like Jan FYE with two extra quarters into the next FY.

    Trailing-4 from the latest print would be 18.38 labeled 2026. Complete
    FYs only: 2024 = 7.99, 2025 = 10.35.
    """
    actuals = [
        {"period_end_date": "2024-04-30", "reported": 1.27},
        {"period_end_date": "2024-07-31", "reported": 1.89},
        {"period_end_date": "2024-10-31", "reported": 2.15},
        {"period_end_date": "2025-01-31", "reported": 2.68},
        {"period_end_date": "2025-04-30", "reported": 1.55},
        {"period_end_date": "2025-07-31", "reported": 2.32},
        {"period_end_date": "2025-10-31", "reported": 2.59},
        {"period_end_date": "2026-01-31", "reported": 3.89},
        {"period_end_date": "2026-04-30", "reported": 4.86},
        {"period_end_date": "2026-07-31", "reported": 7.04},
    ]
    rows = rollup_street_annual_eps(actuals, fye_month=1)
    by_year = {r["fiscal_year"]: r["eps"] for r in rows}
    assert by_year[2024] == 7.99
    assert by_year[2025] == 10.35
    assert 2026 not in by_year


def test_build_annual_growth_skips_estimate_when_year_already_actual():
    rows = build_annual_growth(
        street_actuals_eps=[{"fiscal_year": 2025, "eps": 10.35}],
        annual_sales_rows=[{"fiscal_year": 2025, "sales": 113_538_000_000, "sales_yoy": 0.19}],
        cy_eps=25.34,
        ny_eps=29.46,
        cy_sales=196_030_000_000,
        ny_sales=226_830_000_000,
        cy_label="2025",
        ny_label="2026",
    )
    years = [r["year"] for r in rows]
    assert years.count("2025") == 1
    actual = next(r for r in rows if r["year"] == "2025")
    assert actual["is_estimate"] is False
    assert actual["eps"] == 10.35
    est = next(r for r in rows if r["year"] == "2026")
    assert est["is_estimate"] is True
    assert est["eps"] == 29.46


def test_overlay_street_eps_and_sales_with_beat_miss():
    quarterly = [
        {"report_date": "2025-02-26", "eps": 1.76, "revenue_m": 120.0},
        {"report_date": "2025-05-28", "eps": 0.80, "revenue_m": 95.0},
    ]
    actuals = [
        # Quarter 1: EPS beat, Sales miss
        {"period_end_date": "2025-01-31", "metric": "eps", "reported": 1.62, "estimate_at_print": 1.50, "surprise_pct": 0.08},
        {"period_end_date": "2025-01-31", "metric": "sales", "reported": 115_000_000, "estimate_at_print": 120_000_000, "surprise_pct": -0.0417},
        # Quarter 2: EPS miss, Sales beat
        {"period_end_date": "2025-04-30", "metric": "eps", "reported": 0.75, "estimate_at_print": 0.82, "surprise_pct": -0.0854},
        {"period_end_date": "2025-04-30", "metric": "sales", "reported": 102_000_000, "estimate_at_print": 98_000_000, "surprise_pct": 0.0408},
    ]
    out = overlay_street_eps(quarterly, actuals)
    q1 = out[0]
    assert q1["eps_actual"] == 1.62
    assert q1["eps_estimate"] == 1.50
    assert q1["eps_surprise_dollar"] == 0.12
    assert q1["eps_surprise_pct"] == 8.0
    assert q1["eps_beat_miss"] == "beat"
    assert q1["revenue_actual"] == 115.0
    assert q1["revenue_estimate"] == 120.0
    assert q1["revenue_surprise_m"] == -5.0
    assert q1["revenue_surprise_pct"] == -4.2
    assert q1["revenue_beat_miss"] == "miss"

    q2 = out[1]
    assert q2["eps_actual"] == 0.75
    assert q2["eps_estimate"] == 0.82
    assert q2["eps_surprise_dollar"] == -0.07
    assert q2["eps_beat_miss"] == "miss"
    assert q2["revenue_actual"] == 102.0
    assert q2["revenue_estimate"] == 98.0
    assert q2["revenue_surprise_m"] == 4.0
    assert q2["revenue_beat_miss"] == "beat"


def test_build_annual_growth_separates_actual_and_estimate():
    sales = [{"fiscal_year": 2024, "sales": 10_000_000_000, "sales_yoy": 0.20}]
    street = [{"fiscal_year": 2024, "eps": 4.50}]
    rows = build_annual_growth(
        street_actuals_eps=street,
        annual_sales_rows=sales,
        cy_eps=5.40,
        ny_eps=6.50,
        cy_sales=12_000_000_000,
        ny_sales=14_500_000_000,
        cy_label="2025",
        ny_label="2026",
    )
    act24 = next(r for r in rows if r["year"] == "2024")
    assert act24["eps_actual"] == 4.50
    assert act24["eps_estimate"] is None
    assert act24["sales_actual"] == 10000.0
    assert act24["is_estimate"] is False

    est25 = next(r for r in rows if r["year"] == "2025")
    assert est25["eps_actual"] is None
    assert est25["eps_estimate"] == 5.40
    assert est25["sales_actual"] is None
    assert est25["sales_estimate"] == 12000.0
    assert est25["is_estimate"] is True
