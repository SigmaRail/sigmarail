"""universe_query_v1 field catalog, IR preview, and screen templates."""

from __future__ import annotations

import json
from importlib.resources import files as package_files
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from screens.exchange import enrich_rows_with_exchange

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Shown first; the rest of the catalog is every unique L7 column from system.columns.
_PRIORITY_FIELDS: tuple[str, ...] = (
    "ticker",
    "date",
    "exchange",
    "sector",
    "industry",
    "company_name",
    "close",
    "closeadj",
    "high",
    "volume",
    "avg_vol_50d",
    "rs_rating",
    "technical_rating",
    "setup_quality_rating",
    "high_growth_momentum_rating",
    "valuation_rating",
    "overall_score",
    "minervini_score",
    "oneil_score",
    "classification",
    "industry_group_rank",
    "is_leading_industry",
    "sma21d",
    "sma50d",
    "sma150d",
    "sma200d",
    "sma200_lag_30d",
    "sma200d_rising_30d",
    "high_52w",
    "low_52w",
    "atr_14_pct",
    "has_vcp_setup",
    "vcp_atr_compression_5d_90d",
    "vcp_volume_dryup_5d_90d",
    "vcp_proximity_90d",
    "vcp_tightness_5d_90d",
    "is_stage_2_advancing",
    "breakout_signal",
    "is_bull_market",
    "minervini_tt_all_conditions_full",
    "minervini_tt_all_conditions_light",
    "minervini_tt_score_full",
    "screen_eps_quarterly",
    "screen_revenue_quarterly",
    "stage_code",
    "stage_duration",
    "valuation_spread_pct",
    "valuation_status",
    "fwd_cagr_2y_normal_pe",
    "target_price_normal_pe",
    "target_price_15x",
    "fwd_eps_1y",
    "fwd_eps_2y",
    "fwd_peg_ratio",
    "growth_rate_pct",
    "eps_cq_mean",
    "eps_nq_mean",
    "eps_cy_mean",
    "eps_ny_mean",
    "eps_ny_rev_pct_90d",
    "eps_nq_rev_pct_90d",
    "eps_last_reported",
    "eps_last_estimate",
    "eps_last_surprise_pct",
    "eps_beat_flag",
    "sales_last_reported",
    "sales_last_estimate",
    "sales_last_surprise_pct",
    "sales_beat_flag",
    "sales_ny_mean",
)

_TEMPLATE_LABELS: dict[str, str] = {
    "fair_value_discount_compounders": "Fair Value Discount Compounders (Undervalued + High Growth)",
    "garp_minervini_forecast_template": "GARP & Growth Momentum (Minervini + 2Y CAGR)",
    "minervini_trend_template_5m": "Minervini Trend Template (5-Month 200 SMA / Strict)",
    "minervini_trend_template_1m": "Minervini Trend Template (1-Month 200 SMA / Early Turnaround)",
    "minervini_momentum_leaders": "Minervini Momentum Leaders (RS 85+ & 52W Highs)",
    "minervini_fundamental_growth": "Minervini Fundamental Growth Champions",
    "minervini_vcp_breakout": "Minervini VCP & Stage 2 Consolidation",
    "minervini_high_tight_flag": "Minervini High Tight Flag / Power Play",
    "minervini_trend_template": "Minervini Trend Template (Standard)",
    "canslim_template": "CANSLIM Leader Filter",
    "breakout_quality_setups": "Chartmill Breakout Setups (High Technical & Setup Ratings)",
    "strong_growth_technical_setups": "Chartmill Strong Growth & Technical Setups",
    "kullamagi_breakout_momentum": "Kristjan Kullamägi Continuation & Momentum Breakouts",
    "weinstein_stage_2_breakout": "Stan Weinstein Stage 2 Advancing Breakouts",
    "unusual_volume_breakouts": "Unusual Volume Breakouts (2x+ 50D Vol)",
    "swing_pullback_sma20": "Swing Trading - Pullback to 20-Day SMA",
    "near_52w_high_breakout": "Near 52-Week High Breakouts & Strong RS",
    "bull_flag_breakouts": "Bull Flag Continuation Breakouts",
    "affordable_growth_compounders": "Affordable Growth Compounders (GARP)",
    "volatility_squeeze_breakout": "Volatility Squeeze Play (Low ATR Contraction)",
    "pocket_pivot_high_rs": "Pocket Pivot in Strong Market Leaders",
    "high_trend_intensity_volume": "High Trend Intensity on Volume Surge",
    "piotroski_undervalued_compounders": "Piotroski Quality & Undervalued Compounders",
    "dividend_growth_compounders": "Quality Dividend Growth Compounders",
    # Aliases for short ids
    "minervini": "Minervini Trend Template (Standard)",
    "canslim": "canslim_template",
    "fair_value": "fair_value_discount_compounders",
    "kullamagi": "kullamagi_breakout_momentum",
    "weinstein": "weinstein_stage_2_breakout",
    "breakouts": "breakout_quality_setups",
    "swing": "swing_pullback_sma20",
    "bull_flag": "bull_flag_breakouts",
    "squeeze": "volatility_squeeze_breakout",
    "pocket_pivot": "pocket_pivot_high_rs",
    "dividends": "dividend_growth_compounders",
    "julian_komar_best_winners": "Julian Komar Best Winners",
    "julian_komar_growth_leaders": "Julian Komar Growth Leaders",
    "julian_komar": "Julian Komar Best Winners",
    "komar": "Julian Komar Best Winners",
    "komar_growth": "Julian Komar Growth Leaders",
}

_TEMPLATE_ALIASES: dict[str, str] = {
    "minervini": "minervini_trend_template",
    "canslim": "canslim_template",
    "vcp": "vcp_triad_coiling",
    "julian_komar": "julian_komar_best_winners",
    "komar": "julian_komar_best_winners",
    "komar_growth": "julian_komar_growth_leaders",
}


def _categorize_field(name: str) -> str:
    nl = name.lower()
    if nl.startswith("fwd_eps") or nl.startswith("fwd_") or nl in {
        "growth_rate_pct",
        "target_price_15x",
        "target_price_normal_pe",
        "fwd_cagr_2y_normal_pe",
        "fwd_peg_ratio",
    }:
        return "forecast"
    if nl.startswith("eps_") or nl.startswith("sales_") or nl in {"est_vendor", "eps_basis"}:
        return "estimates"
    if any(
        tok in nl
        for tok in (
            "sma", "ema", "rs_", "close", "high", "low", "volume", "vol_", "atr",
            "vcp", "stage", "breakout", "price", "adx", "macd", "rsi", "vwap",
            "pivot", "trend", "minervini", "above_", "below_", "bollinger",
            "perf_", "relative_strength", "obv", "slope"
        )
    ):
        return "technicals"
    if any(
        tok in nl
        for tok in (
            "score", "classification", "rating", "screen_", "rank", "oneil",
            "overall", "weinstein", "composite"
        )
    ):
        return "ratings"
    if any(
        tok in nl
        for tok in (
            "eps", "revenue", "margin", "ebit", "fcf", "income", "sales",
            "pe_", "pb_", "debt", "cash", "capex", "arq_", "art_", "ary_",
            "fund", "sector", "industry", "growth", "valuation", "dividend"
        )
    ):
        return "fundamentals"
    if any(tok in nl for tok in ("inst_", "insider", "owner", "sponsor")):
        return "ownership"
    return "other"


_CATEGORY_LABELS: dict[str, str] = {
    "technicals": "Momentum & Technicals",
    "ratings": "Ratings & Scores",
    "fundamentals": "Fundamentals & Valuation",
    "forecast": "Valuation & Forecast",
    "estimates": "Estimates (street consensus)",
    "ownership": "Institutional & Ownership",
    "other": "General Metrics",
}

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "fwd_cagr_2y_normal_pe": "Estimated 2-year annualized rate of return (CAGR %) if price converges to its historical median P/E multiple.",
    "target_price_normal_pe": "2-year projected target price based on forward EPS and historical normal median P/E.",
    "target_price_15x": "Graham 15x Fair Value target price based on forward EPS estimates.",
    "fwd_eps_1y": "1-year forward projected diluted EPS (based on 3-year historical CAGR run-rate and sustainable growth).",
    "fwd_eps_2y": "2-year forward projected diluted EPS.",
    "fwd_peg_ratio": "Forward PEG ratio (Trailing P/E divided by projected fundamental growth rate).",
    "growth_rate_pct": "Projected annual fundamental EPS growth rate percentage.",
    "eps_cq_mean": "Street consensus EPS mean for the current unreported quarter (L7 es).",
    "eps_nq_mean": "Street consensus EPS mean for the next quarter.",
    "eps_cy_mean": "Street consensus EPS mean for the current fiscal year.",
    "eps_ny_mean": "Street consensus EPS mean for the next fiscal year.",
    "eps_ny_rev_pct_90d": "90-day revision in next-year EPS consensus mean (Δ / abs prior).",
    "eps_nq_rev_pct_90d": "90-day revision in next-quarter EPS consensus mean.",
    "eps_last_surprise_pct": "Latest reported EPS surprise vs estimate-at-print.",
    "eps_last_reported": "Latest reported quarterly diluted EPS at print.",
    "eps_last_estimate": "Street consensus EPS estimate at the time of print.",
    "eps_beat_flag": "Latest quarterly EPS print outcome: 1 = Beat, -1 = Miss, 0 = In-line / none.",
    "sales_last_reported": "Latest reported quarterly sales/revenue at print.",
    "sales_last_estimate": "Street consensus sales estimate at the time of print.",
    "sales_last_surprise_pct": "Latest reported sales surprise vs estimate-at-print.",
    "sales_beat_flag": "Latest quarterly sales print outcome: 1 = Beat, -1 = Miss, 0 = In-line / none.",
    "sales_ny_mean": "Street consensus sales mean for the next fiscal year.",
    "sma200_lag_30d": "200-day SMA lagged 30 trading days (soft TT rising: sma200d > sma200_lag_30d).",
    "rs_rating": "1-year weighted relative price performance percentile rank vs universe (1 to 99). Higher indicates stronger market leadership.",
    "technical_rating": "Algorithmic composite technical score based on multi-timeframe moving averages, trend structure, and momentum.",
    "setup_quality_rating": "Quantitative pattern tightness score measuring consolidation base, volatility contraction, and volume dry-up.",
    "high_growth_momentum_rating": "Momentum rating tailored for high-growth acceleration leaders combining RS and velocity.",
    "valuation_rating": "Fundamental valuation percentile score comparing multiples (P/E, P/S, EV/EBITDA) within industry peers.",
    "overall_score": "Master composite score blending technical trend, relative strength, setup quality, and fundamental health.",
    "minervini_score": "Mark Minervini Trend Template composite adherence score based on 8 Stage 2 trend criteria.",
    "oneil_score": "William O'Neil CANSLIM composite rating blending earnings acceleration, relative strength, and group rank.",
    "industry_group_rank": "Industry group relative strength rank (1 to 197). Lower number indicates top-performing leading industry.",
    "is_leading_industry": "Boolean flag indicating stock belongs to a top quartile (leading) industry group.",
    "is_stage_2_advancing": "Stan Weinstein Stage 2 confirmation flag indicating sustained uptrend above rising 30-week / 200-day moving average.",
    "has_vcp_setup": "Volatility Contraction Pattern flag indicating progressive compression of price swings with drying volume.",
    "breakout_signal": "Binary trigger indicating price cleared resistance on above-average expansion volume.",
    "is_bull_market": "Market regime filter flag indicating benchmark index is in a confirmed market uptrend.",
    "atr_14_pct": "14-day Average True Range expressed as a percentage of current price (volatility & risk metric).",
    "atr_14": "14-day Average True Range in dollar terms.",
    "avg_vol_50d": "50-day average daily trading volume in shares (liquidity filter).",
    "dollar_volume": "Average daily dollar volume traded (Price × 50d Average Volume).",
    "sma21d": "21-day simple moving average price (short-term swing trend).",
    "sma50d": "50-day simple moving average price (institutional support level).",
    "sma150d": "150-day simple moving average price (intermediate trend baseline).",
    "sma200d": "200-day simple moving average price (primary long-term trend baseline).",
    "sma200d_rising_30d": "Flag indicating the 200-day moving average is in an active upward slope over the last 30 trading days.",
    "high_52w": "Highest closing price achieved in the past 52 weeks.",
    "low_52w": "Lowest closing price recorded in the past 52 weeks.",
    "close": "Latest closing share price in USD.",
    "volume": "Latest trading day volume in shares.",
    "exchange": "Listing venue from L7 price/tech (e.g. NASDAQ, NYSE).",
    "sector": "Primary macroeconomic sector classification.",
    "industry": "Granular industry group classification.",
    "market_cap": "Total market capitalization in USD.",
    "dividend_rating": "Dividend safety and yield percentile rating.",
    "growth_rating": "Quarterly EPS & sales growth rate acceleration percentile.",
    "health_rating": "Balance sheet leverage and liquidity health score.",
    "stage_code": "Detailed daily market stage token, including substages when available (for example 2A or 2B).",
    "stage_duration": "Consecutive valid daily observations in the current detailed stage.",
}


def _humanize_label(name: str) -> str:
    labels = {
        "rs_rating": "RS Rating",
        "avg_rs_rating": "Average RS Rating",
        "technical_rating": "Technical Rating",
        "setup_quality_rating": "Setup Quality",
        "high_growth_momentum_rating": "High Growth Momentum",
        "valuation_rating": "Valuation Rating",
        "overall_score": "Overall Score",
        "industry_group_rank": "Industry Group Rank",
        "eps_last_reported": "Last Reported EPS",
        "eps_last_estimate": "Last EPS Estimate at Print",
        "eps_last_surprise_pct": "Last EPS Surprise %",
        "eps_beat_flag": "Last EPS Beat Flag",
        "sales_last_reported": "Last Reported Sales",
        "sales_last_estimate": "Last Sales Estimate at Print",
        "sales_last_surprise_pct": "Last Sales Surprise %",
        "sales_beat_flag": "Last Sales Beat Flag",
        "atr_14_pct": "ATR % (14d)",
        "atr_14": "ATR (14d)",
        "sma200d_rising_30d": "200 SMA Rising (30d)",
        "is_stage_2_advancing": "Stage 2 Advancing",
        "has_vcp_setup": "VCP Setup",
        "breakout_signal": "Breakout Signal",
        "dollar_volume": "Dollar Volume",
        "avg_vol_50d": "50-Day Average Volume",
        "perf_1m": "1-Month Performance",
        "perf_3m": "3-Month Performance",
        "perf_6m": "6-Month Performance",
        "perf_1y": "1-Year Performance",
        "eps_cq_mean": "EPS CQ Mean (street)",
        "eps_ny_mean": "EPS NY Mean (street)",
        "eps_ny_rev_pct_90d": "NY EPS 90d revision %",
        "eps_nq_rev_pct_90d": "NQ EPS 90d revision %",
        "eps_last_surprise_pct": "Last EPS surprise %",
        "sma200_lag_30d": "SMA200 lagged 30d",
        "sales_ny_mean": "Sales NY Mean (street)",
    }
    if name in labels:
        return labels[name]
    return name.replace("_", " ").title().strip()


def _load_ch_column_meta() -> dict[str, dict[str, str]]:
    """Field metadata from SigmaRail's SQL-generated core universe registry."""
    from sigmarail.universe import field_catalog

    meta: dict[str, dict[str, str]] = {}
    for field in field_catalog():
        col_name = str(field["name"])
        if col_name in ("lastupdated",) or col_name in meta:
            continue
        meta[col_name] = {
            "table": str(field["table"]),
            "type": str(field["type"]),
            "comment": str(field.get("description") or ""),
            "prefix": str(field["prefix"]),
        }
    if not meta:
        raise RuntimeError("SigmaRail core registry returned no universe fields")
    return meta


def list_screen_fields() -> list[dict[str, Any]]:
    """Field catalog from the SQL-generated SigmaRail universe contract."""
    ch_meta = _load_ch_column_meta()
    keys = set(ch_meta)

    selected: list[str] = []
    seen: set[str] = set()

    for name in _PRIORITY_FIELDS:
        if name in keys and name not in seen:
            selected.append(name)
            seen.add(name)

    for name in sorted(keys):
        if name not in seen:
            selected.append(name)
            seen.add(name)

    out: list[dict[str, Any]] = []
    for name in selected:
        cat = _categorize_field(name)
        meta = ch_meta[name]
        comment = (meta.get("comment") or "").strip()
        desc = comment or _FIELD_DESCRIPTIONS.get(name) or f"{meta['type']} on {meta['table']}"
        prefix = meta["prefix"]
        prefixed_name = f"{prefix}.{name}"

        out.append(
            {
                "name": name,
                "prefixed_name": prefixed_name,
                "prefix": prefix,
                "label": _humanize_label(name),
                "category": cat,
                "category_label": _CATEGORY_LABELS.get(cat, cat.title()),
                "type": meta["type"],
                "table": meta["table"],
                "sql_expr": f"{prefix}.`{name}`",
                "description": desc,
            }
        )
    return out


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_completable_type(col_type: str) -> bool:
    t = col_type.lower()
    return "string" in t or t.startswith("enum")


def list_field_values(name: str, q: str = "", limit: int = 40) -> list[str]:
    """Distinct values for a string/enum L7 column from ClickHouse (latest date)."""
    col = name.strip()
    if not _IDENT_RE.match(col):
        raise ValueError(f"invalid field name {name!r}")
    meta = _load_ch_column_meta().get(col)
    if meta is None:
        raise ValueError(f"unknown field {col!r}")
    if not _is_completable_type(meta["type"]):
        return []
    table = meta["table"]
    if not _IDENT_RE.match(table):
        raise ValueError(f"invalid table {table!r}")
    lim = max(1, min(int(limit), 100))
    needle = (q or "").strip()

    from screens.ch import get_ch_client

    client = get_ch_client()
    where = [
        f"date = (SELECT max(date) FROM `{table}`)",
        f"toString(`{col}`) != ''",
    ]
    params: dict[str, Any] = {"lim": lim}
    if needle:
        where.append(f"positionCaseInsensitiveUTF8(toString(`{col}`), {{q:String}}) > 0")
        params["q"] = needle
    sql = (
        f"SELECT DISTINCT toString(`{col}`) AS v FROM `{table}` FINAL "
        f"WHERE {' AND '.join(where)} ORDER BY v LIMIT {{lim:UInt32}}"
    )
    res = client.query(
        sql,
        parameters=params,
        settings={
            "max_execution_time": 15,
            "max_rows_to_read": 1_000_000_000,
            "timeout_before_checking_execution_speed": 0,
        },
    )
    out: list[str] = []
    for row in res.result_rows:
        val = str(row[0]).strip()
        if val:
            out.append(val)
    return out


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        try:
            value = float(value)
        except (OverflowError, ValueError):
            return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    # numpy / CH scalar wrappers
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return _json_safe(value.item())
    except Exception:
        pass
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _shape_preview_rows(raw_rows: list[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    """Align IR rows with preset preview shape when columns are present."""
    shaped: list[dict[str, Any]] = []
    for h in raw_rows:
        ticker = str(h.get("ticker") or "").upper()
        close = h.get("closeadj") if h.get("closeadj") is not None else h.get("close")
        row: dict[str, Any] = {
            "ticker": ticker,
            "date": str(h.get("date") or as_of),
            "close": close,
            "rs_rating": h.get("rs_rating"),
            "technical_rating": h.get("technical_rating"),
            "setup_quality_rating": h.get("setup_quality_rating"),
            "high_growth_momentum_rating": h.get("high_growth_momentum_rating"),
            "avg_vol_50d": h.get("avg_vol_50d"),
            "overall_score": h.get("overall_score"),
            "minervini_score": h.get("minervini_score"),
            "oneil_score": h.get("oneil_score"),
            "classification": h.get("classification"),
            "industry_group_rank": h.get("industry_group_rank"),
        }
        core = set(row.keys()) | {"closeadj"}
        for k, v in h.items():
            if k not in core:
                row[k] = v
        shaped.append({k: _json_safe(v) for k, v in row.items()})
    return shaped


def validate_universe_ir_spec(spec_dict: dict[str, Any]) -> Any:
    """Validate and compile a universe query with the SigmaRail query compiler."""
    if not isinstance(spec_dict, dict):
        raise ValueError("spec must be an object")
    try:
        from sigmarail.universe import compile_universe_spec

        sql, params = compile_universe_spec(spec_dict)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"failed to compile SigmaRail universe query: {exc}") from exc
    return spec_dict, sql, params


def preview_universe_ir(
    client: Any,
    *,
    as_of: str,
    spec_dict: dict[str, Any],
) -> dict[str, Any]:
    """Validate ``universe_query_v1``, compile single-day SQL, execute, return ranked rows."""
    as_of_s = str(as_of or "").strip()
    if not as_of_s:
        raise ValueError("as_of is required")

    from sigmarail.universe import compile_universe_spec, universe_run

    sql, params = compile_universe_spec(spec_dict, start_date=as_of_s, end_date=as_of_s)

    result = universe_run(
        {
            "start_date": as_of_s,
            "end_date": as_of_s,
            "limit": 500_000,
            "spec": spec_dict,
        },
        client=client,
    )
    if result.get("error"):
        raise ValueError(result["error"])
    rows = _shape_preview_rows(list(result.get("rows") or []), as_of_s)
    enrich_rows_with_exchange(client, rows)
    return {
        "as_of": as_of_s,
        "count": len(rows),
        "rows": rows,
        "screen_ir": "universe_query_v1",
        "spec": spec_dict,
        "sql": sql.strip(),
        "params": {k: params[k] for k in sorted(params)},
        "columns": list(rows[0]) if rows else [],
        "limit": int(spec_dict.get("limit_per_day", 5000)),
    }


def list_templates() -> list[dict[str, str]]:
    """List versioned templates shipped with SigmaRail Studio."""
    rows: list[dict[str, str]] = []
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        template_id = path.stem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _normalize_core_template(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        rows.append(
            {
                "id": template_id,
                "label": _TEMPLATE_LABELS.get(template_id, _humanize_label(template_id)),
                "kind": "screener",
                "tags": [],
                "description": "",
                "why": "",
                "how": "",
                "status": "active",
                "screener_template_id": "",
            }
        )
    for alias, target in _TEMPLATE_ALIASES.items():
        target_row = next((r for r in rows if r["id"] == target), None)
        if target_row is not None:
            rows.append(
                {
                    "id": alias,
                    "label": _TEMPLATE_LABELS.get(alias, target_row["label"]),
                    "kind": "screener",
                    "tags": target_row.get("tags") or [],
                    "description": target_row.get("description") or "",
                    "why": target_row.get("why") or "",
                    "how": target_row.get("how") or "",
                    "status": target_row.get("status") or "active",
                    "screener_template_id": "",
                }
            )
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        uniq.append(row)
    return uniq


def load_template(name: str) -> dict[str, Any]:
    """Load template JSON; normalize to ``{id, label, screen_ir, spec}``."""
    tid = (name or "").strip()
    if not tid or "/" in tid or "\\" in tid or ".." in tid:
        raise ValueError(f"invalid template id {name!r}")
    file_stem = _TEMPLATE_ALIASES.get(tid, tid)
    local_path = TEMPLATES_DIR / f"{file_stem}.json"
    if local_path.is_file():
        raw = json.loads(local_path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"unknown template {tid!r}")

    if (
        isinstance(raw, dict)
        and raw.get("version") in (1, 2)
        and isinstance(raw.get("select"), list)
        and raw.get("where") is not None
    ):
        raw = _normalize_core_template(raw)
        return {
            "id": tid,
            "label": _TEMPLATE_LABELS.get(tid, _humanize_label(tid)),
            "screen_ir": "universe_query_v1",
            "spec": raw,
        }
    raise ValueError(f"template {tid!r} missing universe_query_v1 spec")


def _normalize_core_template(raw: dict[str, Any]) -> dict[str, Any]:
    """Resolve declared joins through SigmaRail's registry and reject non-core fields."""
    from sigmarail.universe import compile_universe_spec, field_catalog

    spec = json.loads(json.dumps(raw))
    allowed_tables = {item["table"] for item in field_catalog()}
    for join in spec.get("joins") or []:
        if not isinstance(join, dict) or join.get("table") not in allowed_tables:
            raise ValueError("template declares a join outside SigmaRail core datasets")
    # SigmaRail infers the approved join path from registered fields; client join
    # declarations are not passed to the query compiler.
    spec.pop("joins", None)
    compile_universe_spec(spec)
    return spec


def get_universe_ir_schema() -> dict[str, Any]:
    """Return the JSON schema for the universe_query_v1 specification.

    The published SigmaRail Spec owns this wire schema.
    """
    path = package_files("sigmarail_spec").joinpath("data", "strategy", "universe-query.json")
    return json.loads(path.read_text(encoding="utf-8"))
