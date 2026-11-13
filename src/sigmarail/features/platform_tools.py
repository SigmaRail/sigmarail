"""Platform MCP helpers: regime, screener presets, ADM discovery, optimizer scorecards."""

from __future__ import annotations

from sigmarail.features.alpha_evaluation import evaluate_factor_performance
from sigmarail.features.factor_matrix import evaluate_factor_matrix

import math
import os
from datetime import date, datetime, timedelta
from typing import Any

from sigmarail.features.l7_reads import PX_RT_FROM, PX_RT_SELECT

_ADM_ENTITIES: dict[str, dict[str, Any]] = {
    "security": {
        # tables resolved via _security_tables() (L7 join manifest + L4 daily_metrics)
        "anchor": "date",
        "key": "ticker",
    },
    "market_regime": {
        "tables": ["market_regime_signals_daily"],
        "anchor": "date",
        "key": "date",
    },
    "regime_composed": {
        "tables": ["regime_composed_daily"],
        "anchor": "date",
        "key": ("policy_name", "ticker", "date"),
    },
    "research_episode": {
        "tables": ["kb_documents", "kb_chunks", "kb_mentions"],
        "anchor": "publish_date",
        "key": "doc_id",
    },
    "broker_account": {
        "tables": [
            "broker_accounts_current",
            "broker_household_summary",
            "household_account_books",
        ],
        "anchor": "date",
        "key": "account_id",
    },
}

_ADM_JOIN_PATHS: list[dict[str, str]] = [
    {
        "from": "security",
        "to": "market_regime",
        "on": "security.date = market_regime.date",
        "note": "Point-in-time screener + market-wide regime for same session.",
    },
    {
        "from": "security",
        "to": "research_episode",
        "on": "kb_mentions.entity_value = security.ticker AND kb_documents.publish_date <= security.date",
        "note": "Narrative as-of: only episodes on or before screener date.",
    },
    {
        "from": "market_regime",
        "to": "regime_composed",
        "on": "market_regime.date = regime_composed.date AND regime_composed.ticker = 'SPY'",
        "note": "Composed policy row for index ticker on session date.",
    },
]

_OWNERSHIP_SELECT = (
    "ticker, date, inst_calendardate, inst_calendardate_complete, "
    "inst_shrholders, inst_shrholders_qoq_delta, inst_sponsor_trend, "
    "insider_sentiment_90d, insider_cluster_buy_flag, "
    "insider_officer_buys_90d, insider_open_buys_90d, insider_open_sells_90d, "
    "insider_net_buy_value_90d"
)

_SCREEN_PRESETS: dict[str, dict[str, Any]] = {
    "leaders": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT,
        "where": "px.rs_rating >= 80 AND rt.overall_score >= 70",
        "order_by": "rt.overall_score DESC",
    },
    "minervini_tt": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT,
        "where": "px.minervini_tt_all_conditions_full = 1",
        "order_by": "rt.minervini_score DESC",
    },
    # CANSLIM-oriented: O'Neil screen flags + RS + bull market gate (L7 ratings).
    "canslim": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT,
        "where": (
            "rt.screen_eps_quarterly = 1 AND rt.screen_revenue_quarterly = 1 "
            "AND px.rs_rating >= 80 AND rt.is_bull_market = 1 "
            "AND rt.classification NOT IN ('AVOID')"
        ),
        "order_by": "rt.oneil_score DESC, px.rs_rating DESC",
    },
    "vcp_tight": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT,
        "where": "rt.has_vcp_setup = 1 AND px.closeadj > px.sma50d",
        "order_by": "rt.overall_score DESC",
    },
    "vcp_triad_coiling": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": (
            PX_RT_SELECT
            + ", rt.setup_quality_rating AS setup_quality_rating"
            + ", px.vcp_atr_compression_5d_90d AS vcp_atr_compression_5d_90d"
            + ", px.vcp_volume_dryup_5d_90d AS vcp_volume_dryup_5d_90d"
            + ", px.vcp_proximity_90d AS vcp_proximity_90d"
        ),
        "where": (
            "px.vcp_atr_compression_5d_90d <= 0.40 "
            "AND px.vcp_volume_dryup_5d_90d <= 0.70 "
            "AND px.vcp_proximity_90d >= 0.90 "
            "AND px.rs_rating >= 70 "
            "AND rt.is_stage_2_advancing = 1"
        ),
        "order_by": "rt.setup_quality_rating DESC, px.rs_rating DESC",
    },
    "setup_quality_leaders": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT + ", rt.setup_quality_rating AS setup_quality_rating",
        "where": (
            "rt.setup_quality_rating >= 70 AND px.rs_rating >= 80 "
            "AND rt.is_stage_2_advancing = 1"
        ),
        "order_by": "rt.setup_quality_rating DESC, px.rs_rating DESC",
    },
    "high_rs": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": PX_RT_SELECT,
        # Keep the executable MCP preset aligned with the catalog IR contract.
        "where": "px.rs_rating >= 90 AND px.closeadj >= 5",
        "order_by": "px.rs_rating DESC, rt.overall_score DESC",
    },
    "julian_komar": {
        "table": "screener_price_tech_daily",
        "from_sql": PX_RT_FROM,
        "select": (
            PX_RT_SELECT
            + ", px.atr_14_pct AS atr_14_pct"
            + ", px.price_70pct_above_52w_low AS price_70pct_above_52w_low"
            + ", px.perf_3m AS perf_3m"
            + ", px.perf_6m AS perf_6m"
            + ", px.avg_vol_30d AS avg_vol_30d"
        ),
        "where": (
            "px.close >= 1.0 "
            "AND px.atr_14_pct >= 4.5 "
            "AND px.price_70pct_above_52w_low = 1 "
            "AND px.perf_3m > 0 "
            "AND px.perf_6m > 0 "
            "AND px.close > px.sma50d "
            "AND px.sma10d >= px.sma20d "
            "AND (px.close * px.avg_vol_30d) >= 10000000"
        ),
        "order_by": "px.perf_3m DESC, px.rs_rating DESC",
    },
    # Ownership presets read L7 ownership delivery (not the wide zipper View).
    "inst_accumulating": {
        "table": "screener_ownership_daily",
        "where": "inst_calendardate_complete = 1 AND inst_shrholders_qoq_delta >= 3",
        "order_by": "inst_shrholders_qoq_delta DESC",
        "select": _OWNERSHIP_SELECT,
    },
    "inst_accumulating_strong": {
        "table": "screener_ownership_daily",
        "where": "inst_calendardate_complete = 1 AND inst_shrholders_qoq_delta >= 10",
        "order_by": "inst_shrholders_qoq_delta DESC",
        "select": _OWNERSHIP_SELECT,
    },
    "insider_cluster_buy": {
        "table": "screener_ownership_daily",
        "where": "insider_cluster_buy_flag = 1",
        "order_by": "insider_net_buy_value_90d DESC",
        "select": _OWNERSHIP_SELECT,
    },
    "insider_net_buy": {
        "table": "screener_ownership_daily",
        "where": "insider_sentiment_90d = 'net_buy' AND insider_officer_buys_90d >= 1",
        "order_by": "insider_net_buy_value_90d DESC",
        "select": _OWNERSHIP_SELECT,
    },
    "insider_selling": {
        "table": "screener_ownership_daily",
        "where": "insider_sentiment_90d = 'net_sell' OR insider_open_sells_90d >= 2",
        # L7 slice has sell counts + net value, not insider_open_sell_value_90d.
        "order_by": "insider_open_sells_90d DESC, insider_net_buy_value_90d ASC",
        "select": _OWNERSHIP_SELECT,
    },
    # CapEx / cash-posture presets read L7 fund delivery (not the wide screener).
    "capex_reinvesting": {
        "table": "screener_fundamentals_daily",
        "where": "mrt_cash_posture = 2 AND mrt_capex IS NOT NULL",
        "order_by": "mrt_capex_to_ocf DESC",
        "select": (
            "ticker, date, mrt_capex, mrt_ncfo, mrt_fcf, mrt_capex_to_ocf, "
            "mrt_cash_posture, mrt_roa, art_cash_posture, art_cash_posture_disagree"
        ),
    },
    "capex_disciplined": {
        "table": "screener_fundamentals_daily",
        "where": "mrt_cash_posture = 1 AND mrt_fcf_to_ocf >= 0.5",
        "order_by": "mrt_fcf_to_ocf DESC",
        "select": (
            "ticker, date, mrt_capex, mrt_ncfo, mrt_fcf, mrt_capex_to_ocf, "
            "mrt_fcf_to_ocf, mrt_cash_posture, mrt_roa"
        ),
    },
    "capex_mrt_art_disagree": {
        "table": "screener_fundamentals_daily",
        "where": "art_cash_posture_disagree = 1",
        "order_by": "date DESC",
        "select": (
            "ticker, date, mrt_cash_posture, art_cash_posture, "
            "art_cash_posture_disagree, mrt_capex_to_ocf, art_capex_to_ocf"
        ),
    },
}


def _row_dict(client: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = client.query(sql, parameters=params or {})
    if not rows.result_rows:
        return None
    return dict(zip(rows.column_names, rows.result_rows[0]))


def _rows_dicts(client: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = client.query(sql, parameters=params or {})
    return [dict(zip(rows.column_names, r)) for r in rows.result_rows]


# Canonical ClickHouse table (no _v3/_v4 suffix after regime-table-consolidation).
REGIME_DAILY_TABLE = "market_regime_signals_daily"


def get_market_regime(client: Any, *, date: str) -> dict[str, Any]:
    d = (date or "").strip()[:10]
    if not d:
        raise ValueError("date is required (YYYY-MM-DD)")
    row = _row_dict(
        client,
        f"""
        SELECT
            date,
            breadth_200d_raw,
            breadth_200d,
            breadth_200d_stale_flag,
            breadth_50d,
            breadth_thrust,
            breadth_50d_zweig_thrust,
            clamp_override_zweig_fires,
            spy_close,
            spy_above200d,
            clamp_risk_off,
            effective_allocation_fraction,
            effective_allocation_tier,
            effective_source,
            allocation_reason,
            weekly_allocation_fraction,
            weekly_allocation_tier,
            early_promote_flag,
            risk_on_fast_flags,
            risk_off_fast_flags,
            allocation_fraction,
            allocation_tier
        FROM {REGIME_DAILY_TABLE} FINAL
        WHERE date = toDate(%(d)s)
        LIMIT 1
        """,
        {"d": d},
    )
    return {"date": d, "regime": row, "source_table": REGIME_DAILY_TABLE}


def explain_regime_allocation(
    client: Any,
    *,
    date: str,
    policy_name: str | None = None,
    ticker: str = "SPY",
) -> dict[str, Any]:
    d = (date or "").strip()[:10]
    if not d:
        raise ValueError("date is required")
    sym = (ticker or "SPY").strip().upper()
    policy = (policy_name or os.environ.get("SIGMARAIL_REGIME_POLICY_NAME") or "").strip()

    if policy:
        row = _row_dict(
            client,
            """
            SELECT
                policy_name,
                ticker,
                date,
                frac,
                contribution_by_signal,
                top_contributor,
                weights_entropy,
                policy_source,
                composer
            FROM regime_composed_daily
            WHERE date = toDate(%(d)s)
              AND ticker = %(ticker)s
              AND policy_name = %(policy)s
            LIMIT 1
            """,
            {"d": d, "ticker": sym, "policy": policy},
        )
        return {
            "date": d,
            "ticker": sym,
            "policy_name": policy,
            "composed": row,
            "source": "regime_composed_daily",
        }

    daily = get_market_regime(client, date=d)
    return {
        "date": d,
        "ticker": sym,
        "daily_regime": daily.get("regime"),
        "v3_daily": daily.get("regime"),  # deprecated alias; same row as daily_regime
        "source": REGIME_DAILY_TABLE,
        "hint": "Set policy_name for regime_composed_daily explainability.",
    }


def compare_regime_periods(
    client: Any,
    *,
    focus_start: str,
    focus_end: str,
    reference_start: str,
    reference_end: str,
) -> dict[str, Any]:
    def _window(label: str, start: str, end: str) -> dict[str, Any]:
        s, e = start[:10], end[:10]
        rows = client.query(
            """
            SELECT
                avg(breadth_200d) AS avg_breadth_200d,
                avg(breadth_50d) AS avg_breadth_50d,
                avg(effective_allocation_fraction) AS avg_allocation_fraction,
                avg(breadth_200d_stale_flag) AS avg_breadth_stale_flag,
                avg(spy_above200d) AS pct_spy_above_200d,
                avg(clamp_risk_off) AS pct_clamp_risk_off,
                count() AS n_days
            FROM market_regime_signals_daily FINAL
            WHERE date BETWEEN toDate(%(s)s) AND toDate(%(e)s)
            """,
            parameters={"s": s, "e": e},
        )
        if not rows.result_rows:
            return {"label": label, "start": s, "end": e, "n_days": 0}
        return {"label": label, "start": s, "end": e, **dict(zip(rows.column_names, rows.result_rows[0]))}

    focus = _window("focus", focus_start, focus_end)
    reference = _window("reference", reference_start, reference_end)
    deltas: dict[str, float | None] = {}
    for key in ("avg_breadth_200d", "avg_breadth_50d", "avg_allocation_fraction"):
        fv = focus.get(key)
        rv = reference.get(key)
        if fv is not None and rv is not None:
            deltas[key] = float(fv) - float(rv)
    return {"focus": focus, "reference": reference, "deltas": deltas}


def screen_stocks(
    client: Any,
    *,
    date: str,
    preset: str = "leaders",
    limit: int = 25,
) -> dict[str, Any]:
    d = (date or "").strip()[:10]
    if not d:
        raise ValueError("date is required")
    key = (preset or "leaders").strip().lower()
    spec = _SCREEN_PRESETS.get(key)
    if not spec:
        raise ValueError(
            f"unknown preset {preset!r}; choose from: {', '.join(sorted(_SCREEN_PRESETS))}"
        )
    limit = max(1, min(int(limit), 100))
    # The JSON preset IR is the catalog SSOT. Execute it directly whenever a
    # preset has a catalog definition so the MCP and Studio paths cannot drift.
    try:
        from sigmarail.features.screen_preset_ir import preset_to_universe_query_v1

        preset_ir = preset_to_universe_query_v1(key)
    except ValueError:
        preset_ir = None
    if preset_ir is not None:
        result = run_screener_ir(
            client,
            spec=preset_ir,
            as_of_date=d,
            limit=limit,
        )
        return {
            "date": d,
            "preset": key,
            "limit": limit,
            "table": str(spec.get("table") or "screener_price_tech_daily"),
            "effective_predicates": preset_ir.get("where"),
            "effective_order_by": preset_ir.get("order_by"),
            "source_template_id": key,
            "source_template_version": 1,
            "quality_status": "pending_unverified",
            "data_quality_run_id": None,
            "hits": result.get("rows", []),
            "count": result.get("row_count", 0),
        }
    table = str(spec.get("table") or "screener_price_tech_daily")
    select_cols = str(spec.get("select") or PX_RT_SELECT)
    from_sql = str(spec.get("from_sql") or f"{table} FINAL")
    # Qualify date when joining px/rt — bare `date` breaks FINAL+JOIN analyzers.
    date_pred = "px.date = toDate(%(d)s)" if " AS px " in from_sql else "date = toDate(%(d)s)"
    # CH 24+ experimental analyzer + FINAL LEFT JOIN + wide SELECT can raise
    # NOT_FOUND_COLUMN_IN_BLOCK (e.g. when selecting industry_group_rank).
    settings = (
        "\n        SETTINGS allow_experimental_analyzer = 0"
        if " AS px " in from_sql and "JOIN" in from_sql.upper()
        else ""
    )
    sql = f"""
        SELECT
            {select_cols}
        FROM {from_sql}
        WHERE {date_pred} AND ({spec['where']})
        ORDER BY {spec['order_by']}
        LIMIT %(limit)s{settings}
    """
    hits = _rows_dicts(client, sql, {"d": d, "limit": limit})
    return {
        "date": d,
        "preset": key,
        "limit": limit,
        "table": table,
        "effective_predicates": str(spec["where"]),
        "effective_order_by": str(spec["order_by"]),
        "quality_status": "pending_unverified",
        "data_quality_run_id": None,
        "hits": hits,
        "count": len(hits),
    }


def validate_screener_ir(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a user supplied UniverseQueryV1 without executing or persisting it."""
    import hashlib
    import json

    from sigmarail.features.ir.universe_query_v1 import (
        UniverseQueryV1,
        compile_universe_query_v1_single_day_param,
    )

    try:
        model = UniverseQueryV1.model_validate(spec)
        sql, params = compile_universe_query_v1_single_day_param(model)
    except Exception as exc:  # validation errors are returned as actionable field errors
        return {"valid": False, "errors": [str(exc)]}
    canonical = model.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "valid": True,
        "errors": [],
        "spec": canonical,
        "spec_hash": digest,
        "query_hash": hashlib.sha256(sql.encode()).hexdigest(),
        "parameter_names": sorted(params),
        "quality_status": "pending_unverified",
        "data_quality_run_id": None,
    }


def run_screener_ir(
    client: Any,
    *,
    spec: dict[str, Any],
    as_of_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Run a validated ad hoc screener with a bounded result size."""
    import hashlib
    import json
    import os
    from datetime import date

    from sigmarail.features.ir.universe_query_v1 import (
        UniverseQueryV1,
        compile_universe_query_v1_range_param,
        compile_universe_query_v1_single_day_param,
    )

    single_day = bool(as_of_date)
    date_range = bool(start_date or end_date)
    if single_day == date_range or (date_range and not (start_date and end_date)):
        raise ValueError("provide either as_of_date or both start_date and end_date")
    try:
        if single_day:
            date.fromisoformat(str(as_of_date))
        else:
            start = date.fromisoformat(str(start_date))
            end = date.fromisoformat(str(end_date))
            if start > end:
                raise ValueError("start_date must be on or before end_date")
    except ValueError as exc:
        raise ValueError(f"invalid evaluation date: {exc}") from exc

    cap = max(1, min(int(limit), int(os.environ.get("SIGMARAIL_QUERY_MAX_ROWS", "5000"))))
    model = UniverseQueryV1.model_validate(spec)
    if single_day:
        sql, params = compile_universe_query_v1_single_day_param(model)
        params["day"] = str(as_of_date)
        params["lim"] = min(cap, int(params.get("lim") or cap))
    else:
        sql, params = compile_universe_query_v1_range_param(model)
        params["start"] = str(start_date)
        params["end"] = str(end_date)
        params["lim"] = min(cap, int(params.get("lim") or cap))
        params["hard_limit"] = cap
        sql = f"SELECT * FROM ({sql}) AS _bounded_screener LIMIT {{hard_limit:UInt32}}"
    result = client.query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    canonical = model.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "as_of_date": str(as_of_date) if single_day else None,
        "start_date": str(start_date) if date_range else None,
        "end_date": str(end_date) if date_range else None,
        "spec_hash": digest,
        "effective_limit": cap,
        "row_count": len(rows),
        "rows": rows,
        "quality_status": "pending_unverified",
        "data_quality_run_id": None,
    }


def _security_tables() -> list[str]:
    """L7 screener ticker-grain tables (join manifest) + L4 daily_metrics."""
    from sigmarail.features.ir.l7_from import _join_manifest

    manifest = _join_manifest()
    l7 = [
        e["table"]
        for e in manifest["tables"]
        if "ticker" in e.get("grain", ["ticker", "date"])
    ]
    return l7 + ["daily_metrics"]


def describe_adm_entity(client: Any, *, entity: str) -> dict[str, Any]:
    name = (entity or "").strip().lower()
    meta = dict(_ADM_ENTITIES.get(name) or {})
    if not meta:
        raise ValueError(
            f"unknown entity {entity!r}; known: {', '.join(sorted(_ADM_ENTITIES))}"
        )
    if name == "security":
        meta["tables"] = _security_tables()
    tables = meta.get("tables", [])
    columns: dict[str, list[str]] = {}
    for t in tables:
        try:
            desc = client.query(f"DESCRIBE TABLE {t}")
            columns[t] = [str(r[0]) for r in desc.result_rows[:40]]
        except Exception as exc:
            columns[t] = [f"<describe failed: {exc}>"]
    return {"entity": name, "meta": meta, "sample_columns": columns}


def list_adm_join_paths(
    client: Any,
    *,
    from_entity: str | None = None,
    to_entity: str | None = None,
) -> dict[str, Any]:
    paths = list(_ADM_JOIN_PATHS)
    if from_entity:
        fe = from_entity.strip().lower()
        paths = [p for p in paths if p["from"] == fe]
    if to_entity:
        te = to_entity.strip().lower()
        paths = [p for p in paths if p["to"] == te]
    return {"paths": paths, "count": len(paths)}


def list_optimizer_runs(
    client: Any,
    *,
    limit: int = 50,
    policy_source: str | None = "search",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    src = (policy_source or "").strip().lower()
    if src == "search":
        sql = """
            SELECT policy_name, composer, parent_policy, created_at, notes
            FROM regime_policies_search FINAL
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
    elif src == "manual":
        sql = """
            SELECT policy_name, composer, parent_policy, created_at, notes
            FROM regime_policies_manual FINAL
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
    else:
        sql = """
            SELECT policy_name, composer, parent_policy, created_at, notes, policy_source
            FROM regime_policies
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
    runs = _rows_dicts(client, sql, {"limit": limit})
    return {"policy_source_filter": src or "all", "runs": runs, "count": len(runs)}


_SCORECARD_DAILY_SQL = """
SELECT
  rcd.date AS date,
  toFloat64(rcd.frac) AS frac,
  toFloat64(ar.close_ret) AS asset_ret,
  toFloat64(ar.cash_ret) AS cash_ret
FROM regime_composed_daily rcd
INNER JOIN asset_returns_daily ar
  ON ar.ticker = rcd.ticker AND ar.date = rcd.date
WHERE rcd.policy_name = %(policy)s
  AND rcd.ticker = %(asset)s
ORDER BY rcd.date
"""

_SCORECARD_WINDOWS: dict[str, tuple[date, date]] = {
    "train": (date(2015, 1, 1), date(2020, 12, 31)),
    "val": (date(2021, 1, 1), date(2023, 12, 31)),
    "test": (date(2024, 1, 1), date(2099, 12, 31)),
}

_ANN_FACTOR = 252.0


def _parse_row_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _filter_scorecard_window(rows: list[dict[str, Any]], window: str) -> list[dict[str, Any]]:
    win = (window or "pooled").strip().lower()
    if win in ("", "pooled", "all"):
        return rows
    bounds = _SCORECARD_WINDOWS.get(win)
    if not bounds:
        return rows
    start, end = bounds
    return [r for r in rows if start <= _parse_row_date(r["date"]) <= end]


def _compute_scorecard_from_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    equity = 1.0
    buyhold = 1.0
    peak = 1.0
    max_dd = 0.0
    strat_rets: list[float] = []
    turnovers: list[float] = []
    prev_frac: float | None = None
    upside_num = upside_den = downside_num = downside_den = 0.0

    for row in rows:
        frac = float(row["frac"])
        asset_ret = float(row["asset_ret"])
        cash_ret = float(row["cash_ret"])
        strat_ret = frac * asset_ret + (1.0 - frac) * cash_ret
        strat_ret = max(strat_ret, -0.999)
        equity *= 1.0 + strat_ret
        buyhold *= 1.0 + asset_ret
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - equity / peak)
        strat_rets.append(strat_ret)
        if prev_frac is not None:
            turnovers.append(abs(frac - prev_frac))
        prev_frac = frac
        if asset_ret > 0:
            upside_num += strat_ret
            upside_den += asset_ret
        elif asset_ret < 0:
            downside_num += strat_ret
            downside_den += asset_ret

    n = len(rows)
    start_date = _parse_row_date(rows[0]["date"])
    end_date = _parse_row_date(rows[-1]["date"])
    mean_ret = sum(strat_rets) / n
    std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in strat_rets) / n) if n > 1 else 0.0
    neg = [r for r in strat_rets if r < 0]
    std_neg = math.sqrt(sum(r * r for r in neg) / len(neg)) if neg else 0.0
    ann_ret = equity ** (_ANN_FACTOR / n) - 1.0 if n > 0 else 0.0
    sharpe = (mean_ret * math.sqrt(_ANN_FACTOR)) / std_ret if std_ret > 0 else 0.0
    sortino = (mean_ret * math.sqrt(_ANN_FACTOR)) / std_neg if std_neg > 0 else 0.0
    calmar = ann_ret / max_dd if max_dd > 0 else 0.0

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "n_days": n,
        "total_return": equity - 1.0,
        "annual_return": ann_ret,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "turnover_per_year": (sum(turnovers) / n) * _ANN_FACTOR if turnovers else 0.0,
        "time_at_100": sum(1 for r in rows if float(r["frac"]) >= 0.999) / n,
        "time_at_0": sum(1 for r in rows if float(r["frac"]) <= 0.001) / n,
        "excess_vs_buyhold": equity - buyhold,
        "upside_capture": upside_num / upside_den if upside_den else 0.0,
        "downside_capture": downside_num / downside_den if downside_den else 0.0,
    }


def get_policy_scorecard(
    client: Any,
    *,
    policy_name: str,
    asset_ticker: str = "SPY",
    window: str | None = None,
) -> dict[str, Any]:
    """Pooled / train / val / test scorecard via Python (avoids CH view recursion)."""
    policy = (policy_name or "").strip()
    if not policy:
        raise ValueError("policy_name is required")
    asset = (asset_ticker or "SPY").strip().upper()
    win = (window or "pooled").strip().lower()
    base = {
        "policy_name": policy,
        "asset_ticker": asset,
        "window": win,
        "contract": "C-MCP-OPTIMIZER-READ",
    }
    try:
        rows = _rows_dicts(client, _SCORECARD_DAILY_SQL, {"policy": policy, "asset": asset})
        if not rows:
            return {
                **base,
                "deferred": True,
                "scorecard": None,
                "reason": "no daily rows for policy/asset in regime_composed_daily",
            }
        filtered = _filter_scorecard_window(rows, win)
        if not filtered:
            return {
                **base,
                "deferred": True,
                "scorecard": None,
                "reason": f"no rows in window '{win}'",
            }
        card = _compute_scorecard_from_series(filtered)
        return {**base, "deferred": False, "scorecard": card, "materialized_via": "python_daily_series"}
    except Exception as exc:
        return {
            **base,
            "deferred": True,
            "scorecard": None,
            "reason": str(exc)[:500],
        }


def evaluate_alpha_performance(
    client: Any,
    *,
    factor_column: str | None = None,
    factor_expr: str | None = None,
    factor_table: str = "screener_factor_daily",
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    quantiles: int = 10,
    horizon: str = "5d",
    population: str = "all",
    universe_spec: dict | None = None,
) -> dict[str, Any]:
    """Pre-LEAN relative performance of a factor vs the EW active universe.

    Exactly one of ``factor_column`` / ``factor_expr`` is required;
    ``factor_expr`` is a whitelisted arithmetic expression over the factor
    table's columns. ``population`` selects the evaluation set — ``all``
    (whole table), ``universe`` (spec base WHERE), or ``eligible`` (plus the
    alpha ``post_where``) — the latter two take the compiled
    ``/VeraBase/Universe`` fragment via ``universe_spec``.

    Reads ``screener_forward_returns_daily`` (transform 132) joined to the factor
    table and ``market_regime_signals_daily``. Read-only; returns quantile
    spreads, Spearman IC/ICIR, regime attribution, and monotonicity score.
    """
    end = (end_date or date.today().isoformat()).strip()
    return evaluate_factor_performance(
        client,
        factor_column=factor_column,
        factor_expr=factor_expr,
        factor_table=factor_table,
        start_date=start_date,
        end_date=end,
        quantiles=quantiles,
        horizon=horizon,  # type: ignore[arg-type]
        population=population,
        universe_spec=universe_spec,
    )


def evaluate_alpha_matrix(
    client: Any,
    *,
    factors: list[dict[str, Any]],
    base_table: str | None = None,
    windows: list[dict[str, str]] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    quantiles: int = 10,
    horizon: str = "5d",
    population: str = "all",
    universe_spec: dict | None = None,
) -> dict[str, Any]:
    """Paired multi-factor evaluation matrix (VeraProjects#78).

    ``factors`` is a list of ``{"name", "table", "column"|"expr", "discrete"?}``
    candidates (max 50). All rules evaluate in one pass against the same
    population: quantile stats arrive paired ``(rule, bucket, ...)`` with the
    population-mean baseline as the primary spread (EW-universe spread kept as
    a diagnostic), plus per-rule coverage, daily IC/ICIR, pairwise score
    correlations, p95 scales, and the deterministic blend/gate derivations.

    ``windows`` splits the window list (e.g. H1/H2 stability); ``population`` /
    ``universe_spec`` behave as in ``evaluate_alpha_performance``.
    """
    result = evaluate_factor_matrix(
        client,
        factors=factors,
        base_table=base_table,
        windows=windows,
        start_date=start_date,
        end_date=end_date,
        quantiles=quantiles,
        horizon=horizon,  # type: ignore[arg-type]
        population=population,
        universe_spec=universe_spec,
    )
    result["quality_status"] = "pending_unverified"
    result["data_quality_run_id"] = None
    return result


def rs_blend_scores(
    client: Any,
    *,
    date: str,
    profile_id: str | None = None,
    version: int | None = None,
    weights: dict[str, float] | None = None,
    missing_policy: str | None = None,
    score_mode: str | None = None,
    tickers: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Score tickers under a registered RS blend profile or ad-hoc weights (VeraProjects#181).

    Thin serializable wrapper over ``sigmarail.features.rs_blend.rs_blend_scores``.
    Exactly one of ``profile_id`` (resolved from ``rs_blend_profile``) or
    ``weights`` (component weight map, e.g. ``{"perf_q4": 0.7, "perf_q3": 0.3}``)
    is required. ``score_mode`` is ``rerank_100`` (cohort percentile 0-100 —
    rs_rating semantics) or ``blend_pct`` (blended pct x 100);
    ``missing_policy`` is ``renorm`` | ``fallback_yearly`` | ``require_all``.
    ``tickers`` optionally restricts the cohort filter (rerank still happens
    over the full date cohort unless tickers restricts it — see rs_blend.py).

    Returns ``{date, profile_id, weights, missing_policy, score_mode, count,
    rows: [{ticker, blend, rating}]}`` sorted by rating desc, capped at
    ``limit`` rows.
    """
    from sigmarail.features.rs_blend import _fetch_profile, rs_blend_scores as _blend

    resolved: dict[str, Any] = {"profile_id": profile_id}
    if profile_id is not None:
        prof = _fetch_profile(client, profile_id, version)
        resolved = {
            "profile_id": profile_id,
            "version": prof["version"],
            "universe_id": prof["universe_id"],
        }
        weights = weights or prof["component_weights"]
        missing_policy = missing_policy or prof["missing_policy"]
        score_mode = score_mode or prof["score_mode"]

    rows = _blend(
        date,
        profile_id=profile_id,
        version=version,
        weights=weights,
        missing_policy=missing_policy,
        score_mode=score_mode,
        tickers=tickers,
        client=client,
    )
    out = [
        {"ticker": t, "blend": b, "rating": r}
        for t, b, r in rows
        if r is not None
    ]
    out.sort(key=lambda x: (x["rating"] is None, -(x["rating"] or 0.0)))
    return {
        "date": date,
        **resolved,
        "weights": weights,
        "missing_policy": missing_policy,
        "score_mode": score_mode,
        "count": len(out),
        "rows": out[: max(1, int(limit))],
    }
