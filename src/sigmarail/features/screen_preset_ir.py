"""Map screen_stocks L7 presets to universe_query_v1 documents.

Contract alignment: predicates mirror ``platform_tools._SCREEN_PRESETS`` so
Studio compose/backtest can use the same criteria as MCP ``screen_stocks``.
"""

from __future__ import annotations

import copy
from typing import Any

# Shared selects for equity px⋈rt screens (must include overall_score for VeraScreener).
_EQUITY_SELECT: list[str] = [
    "ticker",
    "close",
    "closeadj",
    "rs_rating",
    "overall_score",
    "minervini_score",
    "oneil_score",
    "classification",
    "sma50d",
    "atr_14_pct",
]

_OWNERSHIP_SELECT: list[str] = [
    "ticker",
    "overall_score",
    "inst_calendardate_complete",
    "inst_shrholders_qoq_delta",
    "insider_cluster_buy_flag",
    "insider_sentiment_90d",
    "insider_officer_buys_90d",
    "insider_net_buy_value_90d",
    "insider_open_sells_90d",
]

_CAPEX_SELECT: list[str] = [
    "ticker",
    "overall_score",
    "mrt_capex",
    "mrt_ncfo",
    "mrt_fcf",
    "mrt_capex_to_ocf",
    "mrt_fcf_to_ocf",
    "mrt_cash_posture",
    "mrt_roa",
    "art_cash_posture",
    "art_cash_posture_disagree",
    "art_capex",
]


def _col(name: str) -> dict[str, Any]:
    return {"type": "col", "name": name}


def _lit(value: Any) -> dict[str, Any]:
    return {"type": "lit", "value": value}


def _cmp(op: str, left: str | dict[str, Any], right: Any) -> dict[str, Any]:
    l = left if isinstance(left, dict) else _col(str(left))
    r = right if isinstance(right, dict) else _lit(right)
    return {"type": op, "left": l, "right": r}


def _all(*items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "all", "items": list(items)}


def _any(*items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "any", "items": list(items)}


def _not_eq(col: str, value: Any) -> dict[str, Any]:
    return {"type": "not", "item": _cmp("eq", col, value)}


def _formula(op: str, *args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "formula", "op": op, "args": list(args)}


def _spec(
    *,
    where: dict[str, Any],
    order_field: str,
    select: list[str],
    limit_per_day: int = 50,
) -> dict[str, Any]:
    order_by = [{"field": order_field, "direction": "desc"}]
    if order_field != "rs_rating" and "rs_rating" in select:
        order_by.append({"field": "rs_rating", "direction": "desc"})
    if "overall_score" in select and order_field != "overall_score":
        order_by.append({"field": "overall_score", "direction": "desc"})
    return {
        "version": 1,
        "from": "daily_screener",
        "select": list(select),
        "where": where,
        "order_by": order_by,
        "limit_per_day": limit_per_day,
    }


_PRESET_IR: dict[str, dict[str, Any]] = {
    "leaders": _spec(
        where=_all(
            _cmp("gte", "rs_rating", 80),
            _cmp("gte", "overall_score", 70),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="overall_score",
        select=_EQUITY_SELECT,
    ),
    "minervini_tt": _spec(
        where=_all(
            _cmp("eq", "minervini_tt_all_conditions_full", 1),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="rs_rating",
        select=_EQUITY_SELECT + ["minervini_tt_all_conditions_full"],
    ),
    "canslim": _spec(
        where=_all(
            _cmp("eq", "screen_eps_quarterly", 1),
            _cmp("eq", "screen_revenue_quarterly", 1),
            _cmp("gte", "rs_rating", 80),
            _cmp("eq", "is_bull_market", 1),
            _cmp("gte", "closeadj", 5.0),
            _not_eq("classification", "AVOID"),
        ),
        order_field="oneil_score",
        select=_EQUITY_SELECT
        + ["screen_eps_quarterly", "screen_revenue_quarterly", "is_bull_market"],
    ),
    "vcp_tight": _spec(
        where=_all(
            _cmp("eq", "has_vcp_setup", 1),
            _cmp("gt", "closeadj", _col("sma50d")),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="overall_score",
        select=_EQUITY_SELECT + ["has_vcp_setup"],
    ),
    "vcp_triad_coiling": _spec(
        where=_all(
            _cmp("lte", "vcp_atr_compression_5d_90d", 0.40),
            _cmp("lte", "vcp_volume_dryup_5d_90d", 0.70),
            _cmp("gte", "vcp_proximity_90d", 0.90),
            _cmp("gte", "rs_rating", 70),
            _cmp("eq", "is_stage_2_advancing", 1),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="setup_quality_rating",
        select=_EQUITY_SELECT
        + [
            "setup_quality_rating",
            "vcp_atr_compression_5d_90d",
            "vcp_volume_dryup_5d_90d",
            "vcp_proximity_90d",
            "is_stage_2_advancing",
        ],
    ),
    "setup_quality_leaders": _spec(
        where=_all(
            _cmp("gte", "setup_quality_rating", 70),
            _cmp("gte", "rs_rating", 80),
            _cmp("eq", "is_stage_2_advancing", 1),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="setup_quality_rating",
        select=_EQUITY_SELECT + ["setup_quality_rating", "is_stage_2_advancing"],
    ),
    "high_rs": _spec(
        where=_all(
            _cmp("gte", "rs_rating", 90),
            _cmp("gte", "closeadj", 5.0),
        ),
        order_field="rs_rating",
        select=_EQUITY_SELECT,
    ),
    "julian_komar": _spec(
        where=_all(
            _cmp("gte", "close", 1.0),
            _cmp("gte", "atr_14_pct", 4.5),
            _cmp("eq", "price_70pct_above_52w_low", 1),
            _cmp("gt", "perf_3m", 0.0),
            _cmp("gt", "perf_6m", 0.0),
            _cmp("gt", "close", _col("sma50d")),
            _cmp("gte", "sma10d", _col("sma20d")),
            _cmp("gte", _formula("*", _col("close"), _col("avg_vol_30d")), 10000000.0),
        ),
        order_field="perf_3m",
        select=_EQUITY_SELECT
        + [
            "price_70pct_above_52w_low",
            "perf_3m",
            "perf_6m",
            "sma10d",
            "sma20d",
            "avg_vol_30d",
        ],
    ),
    "inst_accumulating": _spec(
        where=_all(
            _cmp("eq", "inst_calendardate_complete", 1),
            _cmp("gte", "inst_shrholders_qoq_delta", 3),
        ),
        order_field="inst_shrholders_qoq_delta",
        select=_OWNERSHIP_SELECT,
    ),
    "inst_accumulating_strong": _spec(
        where=_all(
            _cmp("eq", "inst_calendardate_complete", 1),
            _cmp("gte", "inst_shrholders_qoq_delta", 10),
        ),
        order_field="inst_shrholders_qoq_delta",
        select=_OWNERSHIP_SELECT,
    ),
    "insider_cluster_buy": _spec(
        where=_all(_cmp("eq", "insider_cluster_buy_flag", 1)),
        order_field="insider_net_buy_value_90d",
        select=_OWNERSHIP_SELECT,
    ),
    "insider_net_buy": _spec(
        where=_all(
            _cmp("eq", "insider_sentiment_90d", "net_buy"),
            _cmp("gte", "insider_officer_buys_90d", 1),
        ),
        order_field="insider_net_buy_value_90d",
        select=_OWNERSHIP_SELECT,
    ),
    "insider_selling": _spec(
        where=_any(
            _cmp("eq", "insider_sentiment_90d", "net_sell"),
            _cmp("gte", "insider_open_sells_90d", 2),
        ),
        order_field="insider_open_sells_90d",
        select=_OWNERSHIP_SELECT,
    ),
    "capex_reinvesting": _spec(
        where=_all(
            _cmp("eq", "mrt_cash_posture", 2),
            # mrt_capex IS NOT NULL → gte 0 is imperfect; use where_sql-free: neq null via lit
            # Prefer presence via not eq empty — CH Null: use gte large negative as soft stand-in
            _cmp("gte", "mrt_capex_to_ocf", -1e12),
        ),
        order_field="mrt_capex_to_ocf",
        select=_CAPEX_SELECT,
    ),
    "capex_disciplined": _spec(
        where=_all(
            _cmp("eq", "mrt_cash_posture", 1),
            _cmp("gte", "mrt_fcf_to_ocf", 0.5),
        ),
        order_field="mrt_fcf_to_ocf",
        select=_CAPEX_SELECT,
    ),
    "capex_mrt_art_disagree": _spec(
        where=_all(_cmp("eq", "art_cash_posture_disagree", 1)),
        order_field="mrt_capex_to_ocf",
        select=_CAPEX_SELECT,
    ),
}


def list_preset_ir_ids() -> list[str]:
    return sorted(_PRESET_IR.keys())


def preset_to_universe_query_v1(preset: str) -> dict[str, Any]:
    """Return a deep-copied ``universe_query_v1`` for a known screen_stocks preset."""
    key = (preset or "").strip().lower()
    if key not in _PRESET_IR:
        known = ", ".join(list_preset_ir_ids())
        raise ValueError(f"unknown screen preset {preset!r}; choose from: {known}")
    return copy.deepcopy(_PRESET_IR[key])


__all__ = [
    "list_preset_ir_ids",
    "preset_to_universe_query_v1",
]
