"""Stock Introspection Service for point-in-time technical and fundamental analysis.

Connects to ClickHouse tables (screener_price_tech_daily, screener_fundamentals_daily,
screener_ratings_daily, screener_stage_weekly_daily, screener_ownership_daily,
and screener_forecast_models_daily)
to generate a complete point-in-time dossier with full past and full future forward-walk series,
including the MarketSurge RS Line, smoothly interpolated Green Earnings Line,
FastGraphs Fair-Value corridor, and Forward Forecast Valuation Projections.
"""

from __future__ import annotations

from typing import Any
import datetime

from screens.marketsurge_payload import (
    build_annual_growth,
    enrich_as_of_kpis_street,
    ibd_fiscal_year_label,
    ibd_year_from_print_date,
    infer_fye_month,
    merge_forward_estimates,
    overlay_street_eps,
    overlay_street_eps_on_events,
    rollup_street_annual_eps,
)


def get_stock_introspection(
    client: Any,
    ticker: str,
    as_of: str,
    *,
    history_days: int = 2500,
    forward_days: int = 10000,
    include_dossier: bool | None = None,
) -> dict[str, Any]:
    """Fetch complete point-in-time stock overview, chart series with RS line & smooth EPS curves, fundamentals, and forward walk.

    When ``include_dossier`` is False, skip street actuals / annual rollup / peers so the
    chart path stays fast on Django runserver. Defaults to True only when ``history_days`` >= 100.
    """
    sym = ticker.strip().upper()
    as_of_date = as_of.strip()
    if include_dossier is None:
        include_dossier = int(history_days) >= 100
    if not sym:
        raise ValueError("ticker is required")
    if not as_of_date:
        raise ValueError("as_of date is required")

    # Resolve to nearest actual trading date on or before requested date (avoids running heavy joins on weekends)
    actual_date_sql = """
    SELECT date FROM screener_price_tech_daily
    WHERE ticker = %(ticker)s AND date <= toDate(%(as_of)s)
    ORDER BY date DESC LIMIT 1
    """
    actual_date_res = client.query(actual_date_sql, parameters={"ticker": sym, "as_of": as_of_date})
    if actual_date_res.result_rows:
        act_d = actual_date_res.result_rows[0][0]
        as_of_date = act_d.isoformat() if hasattr(act_d, "isoformat") else str(act_d)

    es_as_of = as_of_date
    try:
        es_date_sql = """
        SELECT max(date) FROM screener_estimates_daily
        WHERE ticker = %(ticker)s AND date <= toDate(%(as_of)s)
        """
        es_date_res = client.query(es_date_sql, parameters={"ticker": sym, "as_of": as_of_date})
        if es_date_res.result_rows and es_date_res.result_rows[0][0] is not None:
            es_d = es_date_res.result_rows[0][0]
            es_as_of = es_d.isoformat() if hasattr(es_d, "isoformat") else str(es_d)
    except Exception:
        es_as_of = as_of_date

    # 1. Fetch point-in-time as-of metrics
    as_of_sql = f"""
    SELECT
        p.ticker, p.date, p.company_name, p.sector, p.industry, p.exchange,
        p.open, p.high, p.low, p.close, p.volume,
        p.high_52w, p.low_52w,
        p.sma10d, p.sma20d, p.sma50d, p.sma150d, p.sma200d, p.ema21d,
        p.avg_vol_20d, p.avg_vol_50d,
        p.atr_14, p.atr_14_pct,
        p.perf_5d, p.perf_1m, p.perf_3m, p.perf_6m, p.perf_1y,
        p.price_above_sma50d, p.price_above_sma150d, p.price_above_sma200d,
        p.sma50d_above_sma150d, p.sma50d_above_sma200d, p.sma150d_above_sma200d,
        p.price_30pct_above_52w_low, p.price_within_25pct_52w_high, p.sma200d_rising_30d,
        p.stage_code, p.stage_duration, p.rs_rating, p.industry_group_rank,
        r.technical_rating, r.setup_quality_rating, r.overall_score, r.minervini_score, r.weinstein_score,
        r.growth_rating, r.profitability_rating,
        f.mrt_roe, f.mrt_roic, f.mrt_netmargin, f.mrt_grossmargin, f.mrt_revenue, f.mrt_epsdil,
        f.mrt_fcf, f.ary_revenue, f.ary_epsdil, f.ary_revenue_yoy_growth, f.mry_revenue, f.mry_epsdil,
        f.mrq_revenue, f.mrq_epsdil, f.mrq_grossmargin, f.mrq_netmargin, f.mrq_de,
        f.arq_revenue_growth_yoy, f.arq_eps_growth_yoy,
        o.inst_shrholders, o.inst_shrholders_qoq_pct, o.inst_sponsor_trend, o.insider_cluster_buy_flag,
        es.eps_cq_mean, es.eps_nq_mean, es.eps_cy_mean, es.eps_ny_mean,
        es.sales_cq_mean, es.sales_nq_mean, es.sales_cy_mean, es.sales_ny_mean,
        es.eps_cq_rev_pct_90d, es.eps_nq_rev_pct_90d, es.eps_cy_rev_pct_90d, es.eps_ny_rev_pct_90d,
        es.sales_nq_rev_pct_90d, es.sales_ny_rev_pct_90d, es.eps_last_surprise_pct,
        es.eps_last_reported, es.eps_last_estimate, es.eps_beat_flag,
        es.sales_last_reported, es.sales_last_estimate, es.sales_last_surprise_pct, es.sales_beat_flag,
        dv.marketcap, dv.pe, dv.ps,
        t.firstpricedate, t.location
    FROM screener_price_tech_daily p FINAL
    LEFT JOIN screener_ratings_daily r FINAL ON p.ticker = r.ticker AND p.date = r.date
    LEFT JOIN screener_fundamentals_daily f FINAL ON p.ticker = f.ticker AND p.date = f.date
    LEFT JOIN screener_ownership_daily o FINAL ON p.ticker = o.ticker AND p.date = o.date
    LEFT JOIN screener_estimates_daily es FINAL ON p.ticker = es.ticker AND es.date = toDate(%(es_as_of)s)
    LEFT JOIN daily_valuation dv ON p.ticker = dv.ticker AND p.date = dv.date
    LEFT JOIN vera.tickers t ON p.ticker = t.ticker
    WHERE p.ticker = %(ticker)s AND p.date = toDate(%(as_of)s)
    LIMIT 1
    """

    res_as_of = client.query(as_of_sql, parameters={"ticker": sym, "as_of": as_of_date, "es_as_of": es_as_of})
    if not res_as_of.result_rows:
        # Fallback to nearest trading date on or before as_of
        fallback_sql = f"""
        SELECT date FROM screener_price_tech_daily
        WHERE ticker = %(ticker)s AND date <= toDate(%(as_of)s)
        ORDER BY date DESC LIMIT 1
        """
        fb_res = client.query(fallback_sql, parameters={"ticker": sym, "as_of": as_of_date})
        if fb_res.result_rows:
            actual_date = fb_res.result_rows[0][0]
            actual_date_str = actual_date.isoformat() if hasattr(actual_date, "isoformat") else str(actual_date)
            return get_stock_introspection(
                client,
                sym,
                actual_date_str,
                history_days=history_days,
                forward_days=forward_days,
                include_dossier=include_dossier,
            )
        raise ValueError(f"No market data found for ticker {sym!r} on or before {as_of_date}")

    row = res_as_of.result_rows[0]
    col_names = res_as_of.column_names

    # Convert row to clean dict
    as_of_dict = {}
    for k, v in zip(col_names, row):
        if isinstance(v, (datetime.date, datetime.datetime)):
            as_of_dict[k] = v.isoformat()
        elif isinstance(v, float):
            as_of_dict[k] = round(v, 4)
        else:
            as_of_dict[k] = v

    # Ensure 21 EMA falls back to 20 SMA if None
    if as_of_dict.get("ema21d") is None and as_of_dict.get("sma20d") is not None:
        as_of_dict["ema21d"] = as_of_dict["sma20d"]

    close_val = as_of_dict.get("close") or 0.0
    high_52w = as_of_dict.get("high_52w") or close_val
    low_52w = as_of_dict.get("low_52w") or close_val
    sma50 = as_of_dict.get("sma50d") or 0.0
    sma150 = as_of_dict.get("sma150d") or 0.0
    sma200 = as_of_dict.get("sma200d") or 0.0
    rs_rating = as_of_dict.get("rs_rating") or 0.0

    # 2. Minervini 8-Point Trend Template Scorecard
    c1 = bool(close_val > sma150 and close_val > sma200)
    c2 = bool(sma150 > sma200)
    c3 = bool(as_of_dict.get("sma200d_rising_30d") == 1 or sma200 > 0)
    c4 = bool(sma50 > sma150 and sma50 > sma200)
    c5 = bool(close_val > sma50)
    c6 = bool(low_52w > 0 and close_val >= low_52w * 1.30)
    c7 = bool(high_52w > 0 and close_val >= high_52w * 0.75)
    c8 = bool(rs_rating >= 70)

    checklist_items = [
        {"id": "c1", "label": f"Close ${close_val:.2f} > 150 SMA (${sma150:.2f}) & 200 SMA (${sma200:.2f})", "passed": c1, "desc": "Price above the long-term trend averages"},
        {"id": "c2", "label": f"150 SMA (${sma150:.2f}) > 200 SMA (${sma200:.2f})", "passed": c2, "desc": "Shorter moving average is above the longer trend line"},
        {"id": "c3", "label": "200 SMA Trending Up", "passed": c3, "desc": "200-day moving average is advancing"},
        {"id": "c4", "label": f"50 SMA (${sma50:.2f}) > 150 SMA (${sma150:.2f}) & 200 SMA (${sma200:.2f})", "passed": c4, "desc": "The trend stack is aligned with the intermediate direction"},
        {"id": "c5", "label": f"Close ${close_val:.2f} > 50 SMA (${sma50:.2f})", "passed": c5, "desc": "Price remains above the 50-day baseline"},
        {"id": "c6", "label": f"Close ${close_val:.2f} is {((close_val/low_52w)-1)*100:.1f}% above 52W low (${low_52w:.2f})", "passed": c6, "desc": "+30% above the 52-week low threshold"},
        {"id": "c7", "label": f"Close ${close_val:.2f} is {((1 - close_val/high_52w))*100:.1f}% from 52W high (${high_52w:.2f})", "passed": c7, "desc": "Within 25% of the 52-week high"},
        {"id": "c8", "label": f"RS Rating Leader ({rs_rating:.0f}/99)", "passed": c8, "desc": "Relative strength score is at or above the leader threshold"},
    ]
    total_passed = sum(1 for item in checklist_items if item["passed"])

    trend_template = {
        "score": f"{total_passed}/8",
        "passed_count": total_passed,
        "all_passed": total_passed == 8,
        "items": checklist_items,
    }

    # 3. Query historical and future chart candle series with partition-pruned subqueries & ANY JOIN
    min_date_clause = ""
    min_date_spy = "WHERE ticker = 'SPY'"
    min_date_f = f"WHERE ticker = '{sym}'"
    if history_days and history_days < 9000:
        try:
            as_of_dt = datetime.date.fromisoformat(as_of_date)
            min_dt = as_of_dt - datetime.timedelta(days=history_days)
            min_date_str = min_dt.isoformat()
            min_date_clause = f"AND date >= toDate('{min_date_str}')"
            min_date_spy = f"WHERE ticker = 'SPY' AND date >= toDate('{min_date_str}')"
            min_date_f = f"WHERE ticker = '{sym}' AND date >= toDate('{min_date_str}')"
        except Exception:
            pass

    chart_sql = f"""
    SELECT
        p.date, p.open, p.high, p.low, p.close, p.volume,
        p.sma10d, p.sma20d, p.sma50d, p.sma200d, p.ema21d, p.avg_vol_50d,
        p.rs_rating,
        s.close AS spy_close,
        round((p.close / s.close) * 100, 4) AS rs_line,
        f.mrt_epsdil,
        f.mrq_epsdil,
        f.arq_eps_growth_yoy,
        f.mrq_revenue,
        f.arq_revenue_growth_yoy
    FROM (
        SELECT * FROM screener_price_tech_daily
        WHERE ticker = %(ticker)s {min_date_clause}
    ) p
    LEFT ANY JOIN (
        SELECT date, close FROM screener_price_tech_daily {min_date_spy}
    ) s ON p.date = s.date
    LEFT ANY JOIN (
        SELECT * FROM screener_fundamentals_daily {min_date_f}
    ) f ON p.date = f.date
    ORDER BY p.date ASC
    """
    res_chart = client.query(chart_sql, parameters={"ticker": sym})

    # First pass: calculate historical median P/E ratio (for FastGraphs & MarketSurge Green EPS scaling)
    pe_samples = []
    for r in res_chart.result_rows:
        c_price = float(r[4] or 0)
        ttm_eps = float(r[15]) if r[15] is not None else None
        if ttm_eps and ttm_eps > 0.05 and c_price > 0:
            pe = c_price / ttm_eps
            if 3.0 <= pe <= 120.0:
                pe_samples.append(pe)

    raw_median = float(sorted(pe_samples)[len(pe_samples) // 2]) if pe_samples else 20.0
    median_pe = round(max(10.0, min(raw_median, 30.0)), 1)

    chart_series: list[dict[str, Any]] = []
    forward_candles: list[dict[str, Any]] = []
    earnings_events: list[dict[str, Any]] = []

    last_seen_mrq = None

    for r in res_chart.result_rows:
        d_val = r[0]
        d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        is_fut = d_str > as_of_date

        close_p = round(float(r[4] or 0), 2)
        sma20_val = r[7]
        ema21_val = r[10] if r[10] is not None else sma20_val
        rs_score = r[12]
        spy_close_raw = r[13]
        rs_ratio = r[14]

        ttm_eps = round(float(r[15]), 3) if r[15] is not None else None
        mrq_eps = round(float(r[16]), 3) if r[16] is not None else None
        eps_growth_raw = r[17]
        mrq_rev = round(float(r[18]) / 1e6, 1) if r[18] is not None and r[18] > 1e6 else (round(float(r[18]), 1) if r[18] is not None else None)
        rev_growth_raw = r[19]

        eps_growth_yoy = round(float(eps_growth_raw) * 100, 1) if eps_growth_raw is not None and abs(eps_growth_raw) < 10 else None
        rev_growth_yoy = round(float(rev_growth_raw) * 100, 1) if rev_growth_raw is not None and abs(rev_growth_raw) < 10 else None

        # Check if this day is a quarterly earnings filing date
        is_earnings_report = False
        if mrq_eps is not None or mrq_rev is not None:
            mrq_tuple = (mrq_eps, mrq_rev)
            if last_seen_mrq is not None and mrq_tuple != last_seen_mrq:
                is_earnings_report = True
                earnings_events.append({
                    "date": d_str,
                    "eps": mrq_eps,
                    "eps_growth_yoy": eps_growth_yoy,
                    "revenue_m": mrq_rev,
                    "revenue_growth_yoy": rev_growth_yoy,
                    "is_future": is_fut,
                    "surprise_pct": None,
                })
            last_seen_mrq = mrq_tuple

        eps_line_val = round(ttm_eps * median_pe, 2) if ttm_eps and ttm_eps > 0 else None
        fair_value_15pe = round(ttm_eps * 15.0, 2) if ttm_eps and ttm_eps > 0 else None
        normal_pe_val = round(ttm_eps * median_pe, 2) if ttm_eps and ttm_eps > 0 else None

        candle = {
            "time": d_str,
            "open": round(float(r[1] or 0), 2),
            "high": round(float(r[2] or 0), 2),
            "low": round(float(r[3] or 0), 2),
            "close": close_p,
            "volume": float(r[5] or 0),
            "sma10": round(float(r[6]), 2) if r[6] is not None else None,
            "sma20": round(float(sma20_val), 2) if sma20_val is not None else None,
            "sma50": round(float(r[8]), 2) if r[8] is not None else None,
            "sma200": round(float(r[9]), 2) if r[9] is not None else None,
            "ema21": round(float(ema21_val), 2) if ema21_val is not None else None,
            "vol_sma50": float(r[11]) if r[11] is not None else None,
            "rs_rating": round(float(rs_score), 1) if rs_score is not None else None,
            "spy_close": round(float(spy_close_raw), 2) if spy_close_raw is not None else None,
            "rs_line": round(float(rs_ratio), 4) if rs_ratio is not None else None,
            "eps_trailing_12m": ttm_eps,
            "eps_line_val": eps_line_val,
            "fair_value_15pe": fair_value_15pe,
            "normal_pe_val": normal_pe_val,
            "is_earnings_report": is_earnings_report,
            "earnings_growth_yoy": eps_growth_yoy if is_earnings_report else None,
            "revenue_growth_yoy": rev_growth_yoy if is_earnings_report else None,
            "is_future": is_fut,
            "is_forecast": False,
        }
        chart_series.append(candle)
        if is_fut:
            forward_candles.append(candle)

    # 3b. Smooth continuous interpolation between quarterly earnings points (MarketSurge & FAST Graphs style)
    report_anchors: list[tuple[int, float]] = []
    for idx, c in enumerate(chart_series):
        ttm = c.get("eps_trailing_12m")
        if ttm is not None and ttm > 0:
            if c.get("is_earnings_report") or not report_anchors:
                report_anchors.append((idx, ttm))

    if len(report_anchors) >= 2:
        # Extend backwards to index 0 if needed
        first_idx, first_eps = report_anchors[0]
        second_idx, second_eps = report_anchors[1]
        drift_back = (second_eps - first_eps) / max(1, (second_idx - first_idx))
        for j in range(0, first_idx):
            steps = first_idx - j
            interp_eps = max(0.01, first_eps - steps * drift_back)
            chart_series[j]["eps_trailing_12m"] = round(interp_eps, 3)
            chart_series[j]["eps_line_val"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fair_value_15pe"] = round(interp_eps * 15.0, 2)
            chart_series[j]["normal_pe_val"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fair_value_price"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fv_band_p30"] = round(interp_eps * median_pe * 1.30, 2)
            chart_series[j]["fv_band_p10"] = round(interp_eps * median_pe * 1.10, 2)
            chart_series[j]["fv_band_m10"] = round(interp_eps * median_pe * 0.90, 2)
            chart_series[j]["fv_band_m30"] = round(interp_eps * median_pe * 0.70, 2)
            interp_eps = first_eps - steps * drift_back
            if chart_series[j].get("eps_trailing_12m") is None:
                chart_series[j]["eps_trailing_12m"] = round(max(0.01, interp_eps), 3)
            if interp_eps > 0:
                chart_series[j]["eps_line_val"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fair_value_15pe"] = round(interp_eps * 15.0, 2)
                chart_series[j]["normal_pe_val"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fair_value_price"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fv_band_p30"] = round(interp_eps * median_pe * 1.30, 2)
                chart_series[j]["fv_band_p10"] = round(interp_eps * median_pe * 1.10, 2)
                chart_series[j]["fv_band_m10"] = round(interp_eps * median_pe * 0.90, 2)
                chart_series[j]["fv_band_m30"] = round(interp_eps * median_pe * 0.70, 2)

        for k in range(len(report_anchors) - 1):
            idx_start, eps_start = report_anchors[k]
            idx_end, eps_end = report_anchors[k + 1]
            span = idx_end - idx_start
            if span <= 0:
                continue
            for j in range(idx_start, idx_end):
                ratio = (j - idx_start) / span
                interp_eps = eps_start + ratio * (eps_end - eps_start)
                if chart_series[j].get("eps_trailing_12m") is None:
                    chart_series[j]["eps_trailing_12m"] = round(interp_eps, 3)
                if interp_eps > 0:
                    chart_series[j]["eps_line_val"] = round(interp_eps * median_pe, 2)
                    chart_series[j]["fair_value_15pe"] = round(interp_eps * 15.0, 2)
                    chart_series[j]["normal_pe_val"] = round(interp_eps * median_pe, 2)
                    chart_series[j]["fair_value_price"] = round(interp_eps * median_pe, 2)
                    chart_series[j]["fv_band_p30"] = round(interp_eps * median_pe * 1.30, 2)
                    chart_series[j]["fv_band_p10"] = round(interp_eps * median_pe * 1.10, 2)
                    chart_series[j]["fv_band_m10"] = round(interp_eps * median_pe * 0.90, 2)
                    chart_series[j]["fv_band_m30"] = round(interp_eps * median_pe * 0.70, 2)

        # Extend smoothly from last report date to the end of the historical series
        last_idx, last_eps = report_anchors[-1]
        prev_idx, prev_eps = report_anchors[-2] if len(report_anchors) >= 2 else (last_idx - 60, last_eps)
        daily_drift = (last_eps - prev_eps) / max(1, (last_idx - prev_idx))

        for j in range(last_idx, len(chart_series)):
            steps = j - last_idx
            interp_eps = max(0.01, last_eps + steps * daily_drift)
            if chart_series[j].get("eps_trailing_12m") is None:
                chart_series[j]["eps_trailing_12m"] = round(interp_eps, 3)
            if interp_eps > 0:
                chart_series[j]["eps_line_val"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fair_value_15pe"] = round(interp_eps * 15.0, 2)
                chart_series[j]["normal_pe_val"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fair_value_price"] = round(interp_eps * median_pe, 2)
                chart_series[j]["fv_band_p30"] = round(interp_eps * median_pe * 1.30, 2)
                chart_series[j]["fv_band_p10"] = round(interp_eps * median_pe * 1.10, 2)
                chart_series[j]["fv_band_m10"] = round(interp_eps * median_pe * 0.90, 2)
                chart_series[j]["fv_band_m30"] = round(interp_eps * median_pe * 0.70, 2)

        # Extend smoothly from last report date to the end of the historical series
        last_idx, last_eps = report_anchors[-1]
        prev_idx, prev_eps = report_anchors[-2] if len(report_anchors) >= 2 else (last_idx - 60, last_eps)
        daily_drift = (last_eps - prev_eps) / max(1, (last_idx - prev_idx))

        for j in range(last_idx, len(chart_series)):
            steps = j - last_idx
            interp_eps = max(0.01, last_eps + steps * daily_drift)
            chart_series[j]["eps_trailing_12m"] = round(interp_eps, 3)
            chart_series[j]["eps_line_val"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fair_value_15pe"] = round(interp_eps * 15.0, 2)
            chart_series[j]["normal_pe_val"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fair_value_price"] = round(interp_eps * median_pe, 2)
            chart_series[j]["fv_band_p30"] = round(interp_eps * median_pe * 1.30, 2)
            chart_series[j]["fv_band_p10"] = round(interp_eps * median_pe * 1.10, 2)
            chart_series[j]["fv_band_m10"] = round(interp_eps * median_pe * 0.90, 2)
            chart_series[j]["fv_band_m30"] = round(interp_eps * median_pe * 0.70, 2)

    # 4. Point-in-Time Valuation Forecast Model Query (screener_forecast_models_daily)
    fc_sql = """
    SELECT growth_rate_pct, fwd_eps_1y, fwd_eps_2y, target_price_15x, target_price_normal_pe, fwd_cagr_2y_normal_pe, fwd_peg_ratio
    FROM screener_forecast_models_daily
    WHERE ticker = %(ticker)s AND date = toDate(%(as_of)s) AND model_type = 'historical_cagr_3y'
    LIMIT 1
    """
    res_fc = client.query(fc_sql, parameters={"ticker": sym, "as_of": as_of_date})

    # 4a. Continuous Historical Walk-Forward Expectation Tracks Query (1Y and 2Y Prior Targets)
    tracks_sql = """
    SELECT
        date,
        any(fwd_eps_1y * historical_median_pe) OVER (ORDER BY date ROWS BETWEEN 252 PRECEDING AND 252 PRECEDING) AS fwd_track_1y,
        any(target_price_normal_pe) OVER (ORDER BY date ROWS BETWEEN 504 PRECEDING AND 504 PRECEDING) AS fwd_track_2y
    FROM screener_forecast_models_daily
    WHERE ticker = %(ticker)s AND model_type = 'historical_cagr_3y'
    ORDER BY date ASC
    """
    res_tracks = client.query(tracks_sql, parameters={"ticker": sym})
    tracks_map: dict[str, tuple[float | None, float | None]] = {}
    for tr_row in res_tracks.result_rows:
        d_str = tr_row[0].isoformat() if hasattr(tr_row[0], "isoformat") else str(tr_row[0])
        tr1 = round(float(tr_row[1]), 2) if tr_row[1] is not None and tr_row[1] > 0 else None
        tr2 = round(float(tr_row[2]), 2) if tr_row[2] is not None and tr_row[2] > 0 else None
        tracks_map[d_str] = (tr1, tr2)

    # Attach historical walk-forward expectation tracks to candles
    for c in chart_series:
        t = c["time"]
        if t in tracks_map:
            c["fwd_track_1y"] = tracks_map[t][0]
            c["fwd_track_2y"] = tracks_map[t][1]
        else:
            c["fwd_track_1y"] = None
            c["fwd_track_2y"] = None

    current_ttm_eps = as_of_dict.get("mrt_epsdil") or (chart_series[-1]["eps_trailing_12m"] if chart_series else 1.0)

    def _cagr_pct(target_price: float, close_price: float) -> float | None:
        """Annualized CAGR from close to target over 2 years. None if undefined (negative ratio)."""
        if close_price <= 0:
            return None
        ratio = target_price / close_price
        if ratio <= 0:
            return None
        return round(max(-100.0, min((ratio ** 0.5 - 1) * 100, 200.0)), 2)

    if res_fc.result_rows:
        frow = res_fc.result_rows[0]
        growth_rate_pct = max(-20.0, min(float(frow[0]), 35.0))
        fwd_eps_1y = float(frow[1])
        fwd_eps_2y = float(frow[2])
        target_price_15x = float(frow[3])
        target_price_normal_pe = round(fwd_eps_2y * median_pe, 2)
        fwd_cagr_2y_normal_pe = _cagr_pct(target_price_normal_pe, close_val)
        fwd_peg_ratio = float(frow[6])
    else:
        # Dynamic fallback calculation
        growth_rate_pct = 8.0
        fwd_eps_1y = round(current_ttm_eps * (1 + (growth_rate_pct / 100)), 3)
        fwd_eps_2y = round(current_ttm_eps * ((1 + (growth_rate_pct / 100)) ** 2), 3)
        target_price_15x = round(fwd_eps_2y * 15.0, 2)
        target_price_normal_pe = round(fwd_eps_2y * median_pe, 2)
        fwd_cagr_2y_normal_pe = _cagr_pct(target_price_normal_pe, close_val)
        fwd_peg_ratio = round((close_val / max(0.01, current_ttm_eps)) / max(0.1, growth_rate_pct), 2) if current_ttm_eps > 0 else 0.0

    cagr_15x_2y = _cagr_pct(target_price_15x, close_val)
    current_fair_value = round(current_ttm_eps * median_pe, 2)
    val_spread = round(((close_val - current_fair_value) / max(0.01, current_fair_value)) * 100, 2) if current_fair_value > 0 else 0.0
    if val_spread <= -20.0:
        val_status = "Significantly Undervalued"
    elif val_spread <= -5.0:
        val_status = "Modestly Undervalued"
    elif val_spread <= 5.0:
        val_status = "Fairly Valued"
    elif val_spread <= 20.0:
        val_status = "Modestly Overvalued"
    else:
        val_status = "Significantly Overvalued"

    valuation_forecast = {
        "growth_rate_pct": growth_rate_pct,
        "fwd_eps_1y": fwd_eps_1y,
        "fwd_eps_2y": fwd_eps_2y,
        "target_price_15x": target_price_15x,
        "target_price_normal_pe": target_price_normal_pe,
        "fwd_cagr_2y_normal_pe": fwd_cagr_2y_normal_pe,
        "fwd_cagr_2y_15x": cagr_15x_2y,
        "fwd_peg_ratio": fwd_peg_ratio,
        "historical_median_pe": median_pe,
        "ttm_eps": current_ttm_eps,
        "fair_value_price": current_fair_value,
        "valuation_spread_pct": val_spread,
        "valuation_status": val_status,
    }

    # 4b. Generate Point-in-Time Forward Forecast Cone (500 Trading Days / 2 Years starting from as_of_date)
    anchor_idx = -1
    for idx, c in enumerate(chart_series):
        if c["time"] <= as_of_date:
            anchor_idx = idx
        else:
            break

    base_eps = current_ttm_eps or 1.0
    if anchor_idx >= 0 and chart_series[anchor_idx].get("eps_trailing_12m"):
        base_eps = chart_series[anchor_idx]["eps_trailing_12m"]

    growth_step_daily = (1 + (growth_rate_pct / 100)) ** (1.0 / 252.0) - 1.0

    try:
        anchor_d = datetime.date.fromisoformat(as_of_date)
    except Exception:
        anchor_d = datetime.date.today()

    curr_d = anchor_d
    forecast_days_map: dict[str, dict[str, Any]] = {}

    # Anchor day zero
    forecast_days_map[as_of_date] = {
        "forecast_eps": round(base_eps, 3),
        "forecast_pe_norm": round(base_eps * median_pe, 2),
        "forecast_pe_15": round(base_eps * 15.0, 2),
        "forecast_pe_10": round(base_eps * 10.0, 2),
        "forecast_pe_12_5": round(base_eps * 12.5, 2),
        "forecast_pe_17_5": round(base_eps * 17.5, 2),
        "forecast_pe_20": round(base_eps * 20.0, 2),
        "forecast_pe_25": round(base_eps * 25.0, 2),
        "is_fy1": False,
        "is_fy2": False,
    }

    for day_i in range(1, 505):
        curr_d += datetime.timedelta(days=1)
        if curr_d.weekday() >= 5:
            continue
        fut_d_str = curr_d.isoformat()
        projected_eps = base_eps * ((1.0 + growth_step_daily) ** day_i)

        pe_10 = round(projected_eps * 10.0, 2)
        pe_12_5 = round(projected_eps * 12.5, 2)
        pe_15 = round(projected_eps * 15.0, 2)
        pe_17_5 = round(projected_eps * 17.5, 2)
        pe_20 = round(projected_eps * 20.0, 2)
        pe_25 = round(projected_eps * 25.0, 2)
        pe_norm = round(projected_eps * median_pe, 2)

        is_fy1 = day_i == 252
        is_fy2 = day_i == 500

        forecast_days_map[fut_d_str] = {
            "forecast_eps": round(projected_eps, 3),
            "forecast_pe_norm": pe_norm,
            "forecast_pe_15": pe_15,
            "forecast_pe_10": pe_10,
            "forecast_pe_12_5": pe_12_5,
            "forecast_pe_17_5": pe_17_5,
            "forecast_pe_20": pe_20,
            "forecast_pe_25": pe_25,
            "is_fy1": is_fy1,
            "is_fy2": is_fy2,
        }

    # Apply ghost forecast bands to existing candles in chart_series
    existing_times = set()
    for c in chart_series:
        t = c["time"]
        existing_times.add(t)
        if t in forecast_days_map:
            fc_info = forecast_days_map[t]
            c["ghost_fair_value_15pe"] = fc_info["forecast_pe_15"]
            c["ghost_normal_pe"] = fc_info["forecast_pe_norm"]
            c["ghost_pe_10_0"] = fc_info["forecast_pe_10"]
            c["ghost_pe_12_5"] = fc_info["forecast_pe_12_5"]
            c["ghost_pe_15_0"] = fc_info["forecast_pe_15"]
            c["ghost_pe_17_5"] = fc_info["forecast_pe_17_5"]
            c["ghost_pe_20_0"] = fc_info["forecast_pe_20"]
            c["ghost_pe_25_0"] = fc_info["forecast_pe_25"]
            c["ghost_pe_normal"] = fc_info["forecast_pe_norm"]

    # For forecast dates beyond the latest historical candle in chart_series, append extension bars
    for fut_d_str, fc_info in sorted(forecast_days_map.items()):
        if fut_d_str not in existing_times:
            chart_series.append({
                "time": fut_d_str,
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": None,
                "sma10": None,
                "sma20": None,
                "sma50": None,
                "sma200": None,
                "ema21": None,
                "vol_sma50": None,
                "rs_rating": None,
                "rs_line": None,
                "eps_trailing_12m": fc_info["forecast_eps"],
                "eps_line_val": fc_info["forecast_pe_norm"],
                "fair_value_15pe": fc_info["forecast_pe_15"],
                "normal_pe_val": fc_info["forecast_pe_norm"],
                "ghost_fair_value_15pe": fc_info["forecast_pe_15"],
                "ghost_normal_pe": fc_info["forecast_pe_norm"],
                "ghost_pe_10_0": fc_info["forecast_pe_10"],
                "ghost_pe_12_5": fc_info["forecast_pe_12_5"],
                "ghost_pe_15_0": fc_info["forecast_pe_15"],
                "ghost_pe_17_5": fc_info["forecast_pe_17_5"],
                "ghost_pe_20_0": fc_info["forecast_pe_20"],
                "ghost_pe_25_0": fc_info["forecast_pe_25"],
                "ghost_pe_normal": fc_info["forecast_pe_norm"],
                "pe_10_0": fc_info["forecast_pe_10"],
                "pe_12_5": fc_info["forecast_pe_12_5"],
                "pe_15_0": fc_info["forecast_pe_15"],
                "pe_17_5": fc_info["forecast_pe_17_5"],
                "pe_20_0": fc_info["forecast_pe_20"],
                "pe_25_0": fc_info["forecast_pe_25"],
                "pe_normal": fc_info["forecast_pe_norm"],
                "fair_value_price": fc_info["forecast_pe_norm"],
                "fv_band_p30": round(fc_info["forecast_pe_norm"] * 1.30, 2),
                "fv_band_p10": round(fc_info["forecast_pe_norm"] * 1.10, 2),
                "fv_band_m10": round(fc_info["forecast_pe_norm"] * 0.90, 2),
                "fv_band_m30": round(fc_info["forecast_pe_norm"] * 0.70, 2),
                "fwd_track_1y": fc_info["forecast_pe_norm"] if day_i <= 252 else None,
                "fwd_track_2y": fc_info["forecast_pe_norm"],
                "is_earnings_report": bool(fc_info["is_fy1"] or fc_info["is_fy2"]),
                "earnings_growth_yoy": growth_rate_pct if (fc_info["is_fy1"] or fc_info["is_fy2"]) else None,
                "revenue_growth_yoy": None,
                "is_future": True,
                "is_forecast": True,
            })

    # 5. Compute Forward-Walk Outcome Performance Metrics
    forward_stats: dict[str, Any] = {
        "forward_sessions_available": len(forward_candles),
        "return_5d_pct": None,
        "return_20d_pct": None,
        "return_60d_pct": None,
        "return_250d_pct": None,
        "max_gain_pct": None,
        "max_loss_pct": None,
    }

    if forward_candles and close_val > 0:
        if len(forward_candles) >= 5:
            forward_stats["return_5d_pct"] = round(((forward_candles[4]["close"] / close_val) - 1) * 100, 2)
        if len(forward_candles) >= 20:
            forward_stats["return_20d_pct"] = round(((forward_candles[19]["close"] / close_val) - 1) * 100, 2)
        if len(forward_candles) >= 60:
            forward_stats["return_60d_pct"] = round(((forward_candles[59]["close"] / close_val) - 1) * 100, 2)
        elif len(forward_candles) > 0:
            forward_stats["return_60d_pct"] = round(((forward_candles[-1]["close"] / close_val) - 1) * 100, 2)

        if len(forward_candles) >= 250:
            forward_stats["return_250d_pct"] = round(((forward_candles[249]["close"] / close_val) - 1) * 100, 2)
        elif len(forward_candles) > 60:
            forward_stats["return_250d_pct"] = round(((forward_candles[-1]["close"] / close_val) - 1) * 100, 2)

        # MFE / MAE over the forward horizon
        horizon_slice = forward_candles[:250] if len(forward_candles) >= 250 else forward_candles
        max_high = max(c["high"] for c in horizon_slice)
        min_low = min(c["low"] for c in horizon_slice)
        forward_stats["max_gain_pct"] = round(((max_high / close_val) - 1) * 100, 2)
        forward_stats["max_loss_pct"] = round(((min_low / close_val) - 1) * 100, 2)

    # 5b. Point-in-Time Historical Forecast Calibration Scorecard (Evaluating Forecast vs Reality)
    forecast_calibration: dict[str, Any] = {
        "has_realized_history": len(forward_candles) >= 20,
        "forward_sessions_evaluated": len(forward_candles),
        "origin_date": as_of_date,
        "origin_price": close_val,
        "projected_eps_1y": fwd_eps_1y,
        "actual_eps_1y": None,
        "eps_beat_1y_pct": None,
        "projected_eps_2y": fwd_eps_2y,
        "actual_eps_2y": None,
        "eps_beat_2y_pct": None,
        "projected_target_normal_pe": target_price_normal_pe,
        "actual_peak_price": None,
        "actual_latest_price": None,
        "target_achieved_pct": None,
        "expected_cagr_2y": fwd_cagr_2y_normal_pe,
        "realized_cagr": None,
        "calibration_score_pct": None,
        "max_gain_mfe_pct": forward_stats.get("max_gain_pct"),
        "max_loss_mae_pct": forward_stats.get("max_loss_pct"),
    }

    if forward_candles and close_val > 0:
        actual_peak = max(c["high"] for c in forward_candles if c.get("high") is not None)
        actual_latest = forward_candles[-1]["close"]
        forecast_calibration["actual_peak_price"] = actual_peak
        forecast_calibration["actual_latest_price"] = actual_latest
        if target_price_normal_pe > 0:
            forecast_calibration["target_achieved_pct"] = round((actual_peak / target_price_normal_pe) * 100, 1)

        # Actual EPS ~1Y (252 bars) and ~2Y (500 bars) forward
        eps_candles_1y = [c for c in forward_candles[:255] if c.get("eps_trailing_12m") is not None]
        if eps_candles_1y:
            act_1y_eps = eps_candles_1y[-1]["eps_trailing_12m"]
            forecast_calibration["actual_eps_1y"] = act_1y_eps
            if fwd_eps_1y > 0 and act_1y_eps is not None:
                forecast_calibration["eps_beat_1y_pct"] = round(((act_1y_eps / fwd_eps_1y) - 1) * 100, 1)

        eps_candles_2y = [c for c in forward_candles if c.get("eps_trailing_12m") is not None]
        if len(forward_candles) >= 250 and eps_candles_2y:
            act_2y_eps = eps_candles_2y[-1]["eps_trailing_12m"]
            forecast_calibration["actual_eps_2y"] = act_2y_eps
            if fwd_eps_2y > 0 and act_2y_eps is not None:
                forecast_calibration["eps_beat_2y_pct"] = round(((act_2y_eps / fwd_eps_2y) - 1) * 100, 1)

        # Realized CAGR
        days_span = len(forward_candles)
        if days_span >= 60 and actual_latest > 0:
            years_span = days_span / 252.0
            realized_cagr = round(((actual_latest / close_val) ** (1.0 / max(0.1, years_span)) - 1) * 100, 1)
            forecast_calibration["realized_cagr"] = realized_cagr
            # Calibration score: 100 minus difference
            diff = abs(realized_cagr - fwd_cagr_2y_normal_pe) if fwd_cagr_2y_normal_pe is not None else None
            forecast_calibration["calibration_score_pct"] = max(0.0, min(100.0, round(100.0 - diff, 1))) if diff is not None else None

    # 6. Query Recent Quarterly Fundamentals (Up to 12 Quarters leading into as_of)
    # 6. Query Recent Quarterly Fundamentals (Up to 32 Quarters leading into as_of)
    q_sql = f"""
    SELECT
        date,
        mrq_revenue,
        mrq_epsdil,
        mrq_grossmargin,
        mrq_netmargin,
        arq_revenue_growth_yoy,
        arq_eps_growth_yoy
    FROM screener_fundamentals_daily
    WHERE ticker = %(ticker)s AND date <= toDate(%(as_of)s)
    ORDER BY date DESC
    LIMIT 3500
    """
    res_q = client.query(q_sql, parameters={"ticker": sym, "as_of": as_of_date})

    quarterly_growth: list[dict[str, Any]] = []
    seen_rev = set()

    for r in res_q.result_rows:
        rev = r[1]
        eps = r[2]
        if rev is None and eps is None:
            continue
        key = (round(float(rev), 2) if rev else 0, round(float(eps), 4) if eps else 0)
        if key in seen_rev:
            continue
        seen_rev.add(key)

        d_val = r[0]
        d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)

        quarterly_growth.append({
            "report_date": d_str,
            "revenue_m": round(float(rev) / 1e6, 1) if rev and rev > 1e6 else (round(float(rev), 1) if rev else None),
            "eps": round(float(eps), 2) if eps is not None else None,
            "gross_margin_pct": round(float(r[3]) * 100, 1) if r[3] is not None and r[3] < 1 else (round(float(r[3]), 1) if r[3] is not None else None),
            "net_margin_pct": round(float(r[4]) * 100, 1) if r[4] is not None and r[4] < 1 else (round(float(r[4]), 1) if r[4] is not None else None),
            "revenue_growth_yoy": round(float(r[5]) * 100, 1) if r[5] is not None and abs(r[5]) < 5 else (round(float(r[5]), 1) if r[5] is not None else None),
            "eps_growth_yoy": round(float(r[6]) * 100, 1) if r[6] is not None and abs(r[6]) < 5 else (round(float(r[6]), 1) if r[6] is not None else None),
        })
        if len(quarterly_growth) >= 32:
            break

    # 6b. Street actuals, fiscal year-end, annual sales, CY/NY estimates.
    # Skipped when include_dossier=False (Charts first paint, watchlist minis).
    analyst_actuals_rows: list[dict[str, Any]] = []
    annual_sales_rows: list[dict[str, Any]] = []
    cq_period_end = None
    nq_period_end = None
    cy_period_end = None
    ny_period_end = None
    fye_month: int | None = None
    annual_estimates_by_fy: dict[int, dict[str, float]] = {}
    if include_dossier:
        try:
            act_sql = """
            SELECT period_end_date, metric, reported, estimate_at_print, surprise_pct
            FROM analyst_actuals
            WHERE ticker = %(ticker)s AND metric IN ('eps', 'sales')
              AND period_end_date <= toDate(%(as_of)s)
            ORDER BY period_end_date ASC
            """
            act_res = client.query(act_sql, parameters={"ticker": sym, "as_of": as_of_date})
            for ar in act_res.result_rows:
                ped = ar[0]
                ped_str = ped.isoformat() if hasattr(ped, "isoformat") else str(ped)
                analyst_actuals_rows.append({
                    "period_end_date": ped_str,
                    "metric": str(ar[1] or "eps"),
                    "reported": float(ar[2]) if ar[2] is not None else None,
                    "estimate_at_print": float(ar[3]) if ar[3] is not None else None,
                    "surprise_pct": float(ar[4]) if ar[4] is not None else None,
                })
        except Exception:
            analyst_actuals_rows = []

        try:
            cons_sql = """
            SELECT relative_period, period_end_date, periodicity
            FROM analyst_consensus_asof
            WHERE ticker = %(ticker)s
              AND asof_date = (
                SELECT max(asof_date) FROM analyst_consensus_asof
                WHERE ticker = %(ticker)s AND asof_date <= toDate(%(as_of)s)
              )
              AND metric = 'eps'
              AND (
                (periodicity = 'Q' AND relative_period IN (0, 1))
                OR (periodicity = 'A' AND relative_period IN (0, 1))
              )
            """
            cons_res = client.query(cons_sql, parameters={"ticker": sym, "as_of": as_of_date})
            for cr in cons_res.result_rows:
                rel = int(cr[0])
                ped = cr[1]
                ped_str = ped.isoformat() if hasattr(ped, "isoformat") else (str(ped) if ped else None)
                periodicity = str(cr[2] or "")
                if periodicity == "A":
                    if rel == 0:
                        cy_period_end = ped_str
                        if ped_str and len(ped_str) >= 7:
                            fye_month = int(ped_str[5:7])
                    elif rel == 1:
                        ny_period_end = ped_str
                elif rel == 0:
                    cq_period_end = ped_str
                elif rel == 1:
                    nq_period_end = ped_str
        except Exception:
            pass

        try:
            cons_hist_sql = """
            SELECT
                period_end_date,
                metric,
                periodicity,
                argMax(mean, asof_date) AS estimate
            FROM analyst_consensus_asof
            WHERE ticker = %(ticker)s
              AND asof_date <= toDate(%(as_of)s)
            GROUP BY period_end_date, metric, periodicity
            ORDER BY period_end_date ASC
            """
            cons_hist_res = client.query(cons_hist_sql, parameters={"ticker": sym, "as_of": as_of_date})
            for chr_row in cons_hist_res.result_rows:
                ped = chr_row[0]
                ped_str = ped.isoformat() if hasattr(ped, "isoformat") else str(ped)
                m = str(chr_row[1] or "")
                p = str(chr_row[2] or "")
                val = float(chr_row[3]) if chr_row[3] is not None else None
                if val is None:
                    continue
                if p == "Q":
                    if m == "sales":
                        analyst_actuals_rows.append({
                            "period_end_date": ped_str,
                            "metric": "sales",
                            "reported": None,
                            "estimate_at_print": val,
                            "surprise_pct": None,
                        })
                    elif m == "eps":
                        if not any(a.get("period_end_date") == ped_str and a.get("metric") == "eps" for a in analyst_actuals_rows):
                            analyst_actuals_rows.append({
                                "period_end_date": ped_str,
                                "metric": "eps",
                                "reported": None,
                                "estimate_at_print": val,
                                "surprise_pct": None,
                            })
                elif p == "A":
                    try:
                        fy = int(ped_str[:4])
                        if fy not in annual_estimates_by_fy:
                            annual_estimates_by_fy[fy] = {}
                        if m == "eps":
                            annual_estimates_by_fy[fy]["eps_est"] = round(val, 2)
                        elif m == "sales":
                            annual_estimates_by_fy[fy]["sales_est"] = round(val / 1e6, 1) if val > 1e6 else round(val, 1)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        if fye_month is None:
            fye_month = infer_fye_month(
                [str(a.get("period_end_date") or "") for a in analyst_actuals_rows]
            )

        try:
            sales_sql = """
            SELECT
                min(date) AS first_date,
                ary_revenue,
                argMin(ary_revenue_yoy_growth, date) AS yoy,
                argMin(ary_epsdil, date) AS ary_eps,
                argMin(ary_eps_growth_yoy, date) AS ary_eps_yoy
            FROM screener_fundamentals_daily
            WHERE ticker = %(ticker)s AND date <= toDate(%(as_of)s)
              AND ary_revenue IS NOT NULL AND ary_revenue > 0
            GROUP BY ary_revenue
            ORDER BY first_date
            """
            sales_res = client.query(sales_sql, parameters={"ticker": sym, "as_of": as_of_date})
            sales_fye = fye_month or 1
            by_fy_sales: dict[int, dict[str, Any]] = {}
            for sr in sales_res.result_rows:
                rev = float(sr[1]) if sr[1] is not None else None
                if rev is None:
                    continue
                d_val = sr[0]
                d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
                fy = ibd_year_from_print_date(d_str, sales_fye)
                if fy is None:
                    continue
                eps_val = float(sr[3]) if sr[3] is not None else None
                eps_yoy_val = float(sr[4]) if sr[4] is not None else None
                by_fy_sales[fy] = {
                    "fiscal_year": fy,
                    "sales": rev,
                    "sales_yoy": float(sr[2]) if sr[2] is not None else None,
                    "eps": eps_val,
                    "eps_yoy": eps_yoy_val,
                }
            annual_sales_rows = [by_fy_sales[k] for k in sorted(by_fy_sales)]
            if len(annual_sales_rows) > 12:
                annual_sales_rows = annual_sales_rows[-12:]
        except Exception:
            annual_sales_rows = []

    earnings_events = overlay_street_eps_on_events(earnings_events, analyst_actuals_rows)
    quarterly_growth = overlay_street_eps(quarterly_growth, analyst_actuals_rows)

    quarterly_growth = merge_forward_estimates(
        quarterly_growth,
        cq_eps=as_of_dict.get("eps_cq_mean"),
        nq_eps=as_of_dict.get("eps_nq_mean"),
        cq_sales=as_of_dict.get("sales_cq_mean"),
        nq_sales=as_of_dict.get("sales_nq_mean"),
        cq_period_end=cq_period_end,
        nq_period_end=nq_period_end,
        max_reported=24,
    )

    street_annual = rollup_street_annual_eps(analyst_actuals_rows, fye_month=fye_month)
    cy_year = None
    ny_year = None
    try:
        as_of_year = int(as_of_date[:4])
        if cy_period_end:
            cy_year = str(ibd_fiscal_year_label(cy_period_end, fye_month or 1) or as_of_year)
        else:
            cy_year = str(as_of_year)
        if ny_period_end:
            ny_year = str(ibd_fiscal_year_label(ny_period_end, fye_month or 1) or (as_of_year + 1))
        else:
            ny_year = str(as_of_year + 1)
    except Exception:
        cy_year = "CY"
        ny_year = "NY"

    annual_growth = [] if not include_dossier else build_annual_growth(
        street_actuals_eps=street_annual,
        annual_sales_rows=annual_sales_rows,
        cy_eps=as_of_dict.get("eps_cy_mean"),
        ny_eps=as_of_dict.get("eps_ny_mean"),
        cy_sales=as_of_dict.get("sales_cy_mean"),
        ny_sales=as_of_dict.get("sales_ny_mean"),
        cy_label=cy_year,
        ny_label=ny_year,
        annual_estimates_by_fy=annual_estimates_by_fy,
    )

    as_of_dict = enrich_as_of_kpis_street(
        as_of_dict,
        {
            "eps_cq_mean": as_of_dict.get("eps_cq_mean"),
            "eps_nq_mean": as_of_dict.get("eps_nq_mean"),
            "eps_cy_mean": as_of_dict.get("eps_cy_mean"),
            "eps_ny_mean": as_of_dict.get("eps_ny_mean"),
            "sales_cq_mean": as_of_dict.get("sales_cq_mean"),
            "sales_nq_mean": as_of_dict.get("sales_nq_mean"),
            "sales_cy_mean": as_of_dict.get("sales_cy_mean"),
            "sales_ny_mean": as_of_dict.get("sales_ny_mean"),
            "eps_cq_rev_pct_90d": as_of_dict.get("eps_cq_rev_pct_90d"),
            "eps_nq_rev_pct_90d": as_of_dict.get("eps_nq_rev_pct_90d"),
            "eps_cy_rev_pct_90d": as_of_dict.get("eps_cy_rev_pct_90d"),
            "eps_ny_rev_pct_90d": as_of_dict.get("eps_ny_rev_pct_90d"),
            "sales_nq_rev_pct_90d": as_of_dict.get("sales_nq_rev_pct_90d"),
            "sales_ny_rev_pct_90d": as_of_dict.get("sales_ny_rev_pct_90d"),
            "eps_last_surprise_pct": as_of_dict.get("eps_last_surprise_pct"),
            "eps_last_reported": as_of_dict.get("eps_last_reported"),
            "eps_last_estimate": as_of_dict.get("eps_last_estimate"),
            "eps_beat_flag": as_of_dict.get("eps_beat_flag"),
            "sales_last_reported": as_of_dict.get("sales_last_reported"),
            "sales_last_estimate": as_of_dict.get("sales_last_estimate"),
            "sales_last_surprise_pct": as_of_dict.get("sales_last_surprise_pct"),
            "sales_beat_flag": as_of_dict.get("sales_beat_flag"),
        },
        {
            "firstpricedate": as_of_dict.get("firstpricedate"),
            "location": as_of_dict.get("location"),
        },
        {
            "marketcap": as_of_dict.get("marketcap"),
            "pe": as_of_dict.get("pe"),
            "ps": as_of_dict.get("ps"),
        },
    )

    # Ensure chart_series is strictly deduplicated and ascending sorted by time
    series_map: dict[str, dict[str, Any]] = {}
    for c in chart_series:
        series_map[c["time"]] = c
    chart_series_sorted = [series_map[t] for t in sorted(series_map.keys())]

    # 7. Query Top Industry Peers & Comparable Valuation Statistics (Prioritizing Exact SEC SIC Code)
    industry_peers: list[dict[str, Any]] = []
    peer_group_name = ""
    if include_dossier:
        try:
            peers_sql = """
            SELECT
                p.ticker,
                t.name AS company_name,
                t.sicindustry,
                p.close,
                p.rs_rating,
                fc.growth_rate_pct,
                fc.historical_median_pe,
                fc.target_price_15x,
                fc.target_price_normal_pe,
                fc.fwd_cagr_2y_normal_pe,
                fc.valuation_spread_pct,
                fc.valuation_status
            FROM screener_price_tech_daily p
            INNER JOIN (
                SELECT ticker, name, industry, sector, siccode, sicindustry FROM vera.tickers
                WHERE position(category, 'Common Stock') > 0 AND isdelisted = 'N'
            ) t ON p.ticker = t.ticker
            LEFT ANY JOIN screener_forecast_models_daily fc ON p.ticker = fc.ticker AND p.date = fc.date AND fc.model_type = 'historical_cagr_3y'
            WHERE p.date = toDate(%(as_of)s)
              AND t.siccode = (SELECT siccode FROM vera.tickers WHERE ticker = %(ticker)s LIMIT 1)
              AND p.ticker != %(ticker)s
              AND p.close > 0
            ORDER BY (p.close * p.avg_vol_20d) DESC
            LIMIT 6
            """
            res_peers = client.query(peers_sql, parameters={"as_of": as_of_date, "ticker": sym})

            if len(res_peers.result_rows) < 3:
                peers_sql_fallback = """
                SELECT
                    p.ticker,
                    t.name AS company_name,
                    t.industry,
                    p.close,
                    p.rs_rating,
                    fc.growth_rate_pct,
                    fc.historical_median_pe,
                    fc.target_price_15x,
                    fc.target_price_normal_pe,
                    fc.fwd_cagr_2y_normal_pe,
                    fc.valuation_spread_pct,
                    fc.valuation_status
                FROM screener_price_tech_daily p
                INNER JOIN (
                    SELECT ticker, name, industry, sector, siccode, sicindustry FROM vera.tickers
                    WHERE position(category, 'Common Stock') > 0 AND isdelisted = 'N'
                ) t ON p.ticker = t.ticker
                LEFT ANY JOIN screener_forecast_models_daily fc ON p.ticker = fc.ticker AND p.date = fc.date AND fc.model_type = 'historical_cagr_3y'
                WHERE p.date = toDate(%(as_of)s)
                  AND (t.industry = (SELECT industry FROM vera.tickers WHERE ticker = %(ticker)s LIMIT 1)
                       OR (t.industry = '' AND t.sector = (SELECT sector FROM vera.tickers WHERE ticker = %(ticker)s LIMIT 1)))
                  AND p.ticker != %(ticker)s
                  AND p.close > 0
                ORDER BY (p.close * p.avg_vol_20d) DESC
                LIMIT 6
                """
                res_peers = client.query(peers_sql_fallback, parameters={"as_of": as_of_date, "ticker": sym})

            for pr in res_peers.result_rows:
                if not peer_group_name and pr[2]:
                    peer_group_name = str(pr[2])
                industry_peers.append({
                    "ticker": str(pr[0]),
                    "company_name": str(pr[1] or pr[0]),
                    "peer_group": str(pr[2] or ""),
                    "close": round(float(pr[3]), 2) if pr[3] is not None else 0.0,
                    "rs_rating": round(float(pr[4]), 0) if pr[4] is not None else None,
                    "growth_rate_pct": round(float(pr[5]), 1) if pr[5] is not None else None,
                    "historical_median_pe": round(float(pr[6]), 1) if pr[6] is not None else 20.0,
                    "target_price_15x": round(float(pr[7]), 2) if pr[7] is not None else None,
                    "target_price_normal_pe": round(float(pr[8]), 2) if pr[8] is not None else None,
                    "fwd_cagr_2y_normal_pe": round(float(pr[9]), 1) if pr[9] is not None else None,
                    "valuation_spread_pct": round(float(pr[10]), 1) if pr[10] is not None else None,
                    "valuation_status": str(pr[11] or "Fairly Valued"),
                })
        except Exception:
            pass

    return {
        "ticker": sym,
        "as_of": as_of_date,
        "company_name": as_of_dict.get("company_name") or sym,
        "sector": as_of_dict.get("sector") or "General",
        "industry": as_of_dict.get("industry") or "General",
        "exchange": as_of_dict.get("exchange") or "US",
        "historical_median_pe": median_pe,
        "valuation_forecast": valuation_forecast,
        "as_of_kpis": as_of_dict,
        "trend_template": trend_template,
        "forward_stats": forward_stats,
        "forecast_calibration": forecast_calibration,
        "quarterly_growth": quarterly_growth,
        "annual_growth": annual_growth,
        "earnings_events": earnings_events,
        "industry_peers": industry_peers,
        "chart_series": chart_series_sorted,
    }
