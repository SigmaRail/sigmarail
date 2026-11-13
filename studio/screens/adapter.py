"""Screen preview adapter over SigmaRail's schema-bound universe API."""

from __future__ import annotations

from typing import Any

from screens.exchange import enrich_rows_with_exchange
from screens.ir_preview import list_templates, load_template

_PRESET_TARGETS = {
    "leaders": "minervini_trend_template",
    "minervini_tt": "minervini_trend_template",
    "canslim": "canslim_template",
    "vcp_triad_coiling": "minervini_vcp_breakout",
    "setup_quality_leaders": "breakout_quality_setups",
    "high_rs": "minervini_momentum_leaders",
}
_PRESET_LABELS = {
    "leaders": "Leaders",
    "minervini_tt": "Minervini TT",
    "canslim": "CANSLIM",
    "vcp_triad_coiling": "VCP triad coiling",
    "setup_quality_leaders": "Setup quality leaders",
    "high_rs": "High relative strength",
}

_CORE_ROW_KEYS = {
    "ticker",
    "date",
    "close",
    "closeadj",
    "rs_rating",
    "overall_score",
    "minervini_score",
    "oneil_score",
    "classification",
    "industry_group_rank",
}


def list_screen_presets() -> list[dict[str, str]]:
    """List only local templates that compile against SigmaRail core fields."""
    supported = {row["id"] for row in list_templates()}
    return [
        {
            "id": preset,
            "label": _PRESET_LABELS[preset],
            "backtestable": True,
        }
        for preset, target in _PRESET_TARGETS.items()
        if target in supported
    ]


ALL_SCREEN_PRESETS: tuple[str, ...] = tuple(_PRESET_TARGETS)


def preset_to_universe_spec(preset: str) -> dict[str, Any]:
    """Resolve a supported preset to a local SigmaRail universe template."""
    preset_key = (preset or "").strip().lower()
    if preset_key not in ALL_SCREEN_PRESETS:
        raise ValueError(f"unknown screen preset {preset_key!r}")
    spec = load_template(_PRESET_TARGETS[preset_key])["spec"]
    if preset_key == "leaders":
        spec["order_by"] = [{"field": "overall_score", "direction": "desc"}]
    return spec


def preview_screen(
    client: Any,
    *,
    as_of: str,
    preset: str = "leaders",
    limit: int = 50,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Run a named SigmaRail universe template; optionally filter by ticker set."""
    preset_key = (preset or "leaders").strip().lower()
    if preset_key not in ALL_SCREEN_PRESETS:
        raise ValueError(f"unknown screen preset {preset_key!r}")

    from screens.ir_preview import preview_universe_ir

    spec = preset_to_universe_spec(preset_key)
    spec["limit_per_day"] = min(max(int(limit), 1), 100)
    raw = preview_universe_ir(client, as_of=as_of, spec_dict=spec)
    hits = list(raw.get("rows") or [])

    if tickers:
        allow = {t.strip().upper() for t in tickers if t and str(t).strip()}
        if allow:
            hits = [h for h in hits if str(h.get("ticker") or "").upper() in allow]

    rows: list[dict[str, Any]] = []
    for h in hits:
        rows.append(
            {
                "ticker": str(h.get("ticker") or "").upper(),
                "date": str(h.get("date") or as_of),
                "close": h.get("closeadj") if h.get("closeadj") is not None else h.get("close"),
                "rs_rating": h.get("rs_rating"),
                "overall_score": h.get("overall_score"),
                "minervini_score": h.get("minervini_score"),
                "oneil_score": h.get("oneil_score"),
                "classification": h.get("classification"),
                "industry_group_rank": h.get("industry_group_rank"),
                # Pass through extra fields for ownership/capex presets
                **{k: h[k] for k in h if k not in _CORE_ROW_KEYS},
            }
        )

    enrich_rows_with_exchange(client, rows)

    return {
        "as_of": raw.get("as_of") or as_of,
        "preset": preset_key,
        "limit": int(raw.get("limit") or limit),
        "table": "screener_price_tech_daily",
        "count": len(rows),
        "rows": rows,
        "screen_ir": "universe_query_v1",
        "note": "Preset expands from a local SigmaRail template and runs through the schema-bound core universe query.",
    }


def list_trading_session_dates(client: Any, *, limit: int = 10000) -> list[str]:
    """Recent distinct trading dates from L7 price tech (DESC) for as-of scrubber."""
    n = min(max(int(limit), 1), 10000)
    result = client.query(
        "SELECT DISTINCT date FROM screener_price_tech_daily "
        f"ORDER BY date DESC LIMIT {n}"
    )
    dates: list[str] = []
    for row in result.result_rows:
        d = row[0]
        dates.append(d.isoformat() if hasattr(d, "isoformat") else str(d))
    return dates


def screen_turnover(
    client: Any,
    *,
    as_of: str,
    preset: str = "leaders",
    limit: int = 50,
) -> dict[str, Any]:
    """Compare preset membership on ``as_of`` vs prior trading day."""
    dates = list_trading_session_dates(client, limit=120)
    as_of_s = as_of.strip()
    if as_of_s not in dates:
        raise ValueError(
            f"as_of {as_of_s!r} not found in recent trading dates (need prior session)"
        )
    idx = dates.index(as_of_s)
    if idx + 1 >= len(dates):
        raise ValueError(f"no prior trading day before {as_of_s!r}")
    prior = dates[idx + 1]

    cur = preview_screen(client, as_of=as_of_s, preset=preset, limit=limit)
    prev = preview_screen(client, as_of=prior, preset=preset, limit=limit)
    cur_set = {r["ticker"] for r in cur["rows"]}
    prev_set = {r["ticker"] for r in prev["rows"]}
    added = sorted(cur_set - prev_set)
    removed = sorted(prev_set - cur_set)
    retained = cur_set & prev_set
    return {
        "as_of": as_of_s,
        "prior": prior,
        "preset": (preset or "leaders").strip().lower(),
        "added": added,
        "removed": removed,
        "retained_count": len(retained),
    }


def get_market_context(
    client: Any,
    *,
    start_date: str,
    end_date: str,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Fetch market context daily data for the date range."""
    n = min(max(int(limit), 1), 5000)
    # Select all key market context columns
    select_cols = [
        "date",
        "weekly_allocation_fraction",
        "weekly_allocation_tier",
        "composite_score_normalized",
        "market_regime_signal",
        "is_bear_market_active",
        "allocation_note",
        "breadth_200d",
        "breadth_50d",
        "spy_close",
        "spy_sma200d",
        "spy_sma50d",
        "spy_above200d",
        "spy_above50d",
        "spy_below200d",
        "spy_below200d_3d",
        "ma50_gt_ma200",
        "ma50_slope_pos",
        "ma200_slope_pos",
        "ma_stack_score",
        "risk_on_fast_flags",
        "risk_off_fast_flags",
        "clamp_risk_off",
        "breadth_thrust",
        "ftd",
        "distribution_count_25d",
        "breadth55_days15",
        "is_bear_market_enhanced",
        "bear_severity",
        "bear_market_score",
        "pct_near_52w_high",
        "pct_near_52w_low",
        "pct_above_sma20d",
        "pct_above_sma50d",
        "pct_above_sma200d",
        "pct_above_sma20d_sma5",
        "pct_above_sma50d_sma5",
        "pct_above_sma200d_sma5",
        "price_vs_sma30w_pct",
        "price_vs_sma40w_pct",
        "sma30w_vs_sma40w_pct",
        "sma40w_slope_pct",
        "trend_score",
        "pct_sp500_above_sma40w",
        "pct_stocks_above_sma200",
        "market_sma200_trend_strength",
        "vix_close",
        "vix_sma20d",
        "vix_sma50d",
        "vix_sma200d",
        "vix_vs_sma20d_pct",
        "vix_vs_sma50d_pct",
        "vix_vs_sma200d_pct",
        "vix_contango_proxy",
        "vix_spike_flag",
        "vix_above_sma200d",
        "uvxy_vs_vix_basis",
        "svxy_vs_vix_basis",
    ]
    cols_str = ", ".join(select_cols)
    result = client.query(
        f"SELECT {cols_str} FROM market_context_daily FINAL "
        f"WHERE date BETWEEN toDate('{start_date}') AND toDate('{end_date}') "
        f"ORDER BY date ASC LIMIT {n}"
    )
    rows: list[dict[str, Any]] = []
    for row in result.result_rows:
        rows.append(dict(zip(select_cols, row)))
    return rows


# Formula Presets CRUD
_FORMULA_PRESETS_TABLE = "formula_presets"


def list_formula_presets(client: Any, *, active_only: bool = True) -> list[dict[str, Any]]:
    """List all formula presets, optionally filtering to active only."""
    where = "WHERE is_active = 1" if active_only else ""
    sql = f"""
        SELECT id, label, expr, description, category, is_active, created_at, updated_at, created_by
        FROM formula_presets FINAL
        {"WHERE is_active = 1" if active_only else ""}
        ORDER BY category, label
    """
    result = client.query(sql)
    return [dict(zip(["id", "label", "expr", "description", "category", "is_active", "created_at", "updated_at", "created_by"], row)) for row in result.result_rows]


def get_formula_preset(client: Any, preset_id: str) -> dict[str, Any] | None:
    """Get a single formula preset by ID."""
    sql = "SELECT id, label, expr, description, category, is_active, created_at, updated_at, created_by FROM formula_presets FINAL WHERE id = {preset_id:String}"
    result = client.query(sql, parameters={"preset_id": preset_id})
    if not result.result_rows:
        return None
    row = result.result_rows[0]
    return dict(zip(["id", "label", "expr", "description", "category", "is_active", "created_at", "updated_at", "created_by"], row))


def create_formula_preset(
    client: Any,
    *,
    label: str,
    expr: str,
    description: str,
    category: str = "Custom",
    created_by: str = "user",
) -> dict[str, Any]:
    """Create a new formula preset."""
    import uuid
    preset_id = str(uuid.uuid4())
    sql = f"""
        INSERT INTO formula_presets (id, label, expr, description, category, is_active, created_by)
        VALUES ('{preset_id}', '{label}', '{expr}', '{description}', '{category}', 1, '{created_by}')
    """
    client.query(sql)
    return get_formula_preset(client, preset_id) or {}


def update_formula_preset(
    client: Any,
    preset_id: str,
    *,
    label: str | None = None,
    expr: str | None = None,
    description: str | None = None,
    category: str | None = None,
    is_active: int | None = None,
) -> dict[str, Any] | None:
    """Update an existing formula preset."""
    updates = []
    if label is not None:
        updates.append(f"label = '{label}'")
    if expr is not None:
        updates.append(f"expr = '{expr}'")
    if description is not None:
        updates.append(f"description = '{description}'")
    if category is not None:
        updates.append(f"category = '{category}'")
    if is_active is not None:
        updates.append(f"is_active = {is_active}")
    if not updates:
        return get_formula_preset(preset_id)

    updates.append("updated_at = now()")
    sql = f"ALTER TABLE formula_presets UPDATE {', '.join(updates)} WHERE id = '{preset_id}'"
    client.query(sql)
    return get_formula_preset(client, preset_id)


def delete_formula_preset(client: Any, preset_id: str) -> bool:
    """Soft delete a formula preset (mark as inactive)."""
    sql = f"ALTER TABLE formula_presets UPDATE is_active = 0, updated_at = now() WHERE id = '{preset_id}'"
    client.query(sql)
    return True
