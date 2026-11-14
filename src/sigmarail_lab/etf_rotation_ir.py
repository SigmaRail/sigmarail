"""Policy B graph IR for VUG/VTV/SGOV ETF rotation (Path 3).

Priority matches ``etf_rotation_state.resolve_rotation_state``:
clamp → demote_streak → distribution_count → weekly tiers → cash.
"""

from __future__ import annotations

import json
from typing import Any

from sigmarail_lab.etf_rotation_state import BASKET, CASH_ETF, DEFENSIVE_ETF, GROWTH_ETF


def _weight_step(vug: float, vtv: float, sgov: float) -> dict[str, Any]:
    return {
        "step": "weight",
        "mode": "specified",
        "weights": {
            GROWTH_ETF: str(vug),
            DEFENSIVE_ETF: str(vtv),
            CASH_ETF: str(sgov),
        },
    }


def etf_rotation_graph_v1_dict() -> dict[str, Any]:
    """Nested if/else policy + in_tickers universe for SPY/VUG/VTV/SGOV."""
    weekly_tiers = {
        "step": "if",
        "condition": {"type": "regime", "field": "regime_weekly_fraction", "gte": 0.25},
        "then": _weight_step(0.33, 0.67, 0.0),
        "else": _weight_step(0.0, 0.0, 1.0),
    }
    weekly_tiers = {
        "step": "if",
        "condition": {"type": "regime", "field": "regime_weekly_fraction", "gte": 0.60},
        "then": _weight_step(0.67, 0.33, 0.0),
        "else": weekly_tiers,
    }
    weekly_tiers = {
        "step": "if",
        "condition": {"type": "regime", "field": "regime_weekly_fraction", "gte": 0.99},
        "then": _weight_step(1.0, 0.0, 0.0),
        "else": weekly_tiers,
    }

    policy = {
        "step": "if",
        "condition": {"type": "regime", "field": "clamp_risk_off", "eq": 1},
        "then": _weight_step(0.0, 0.80, 0.20),
        "else": {
            "step": "if",
            "condition": {"type": "regime", "field": "daily_demote_streak", "gte": 3},
            "then": _weight_step(0.0, 0.70, 0.30),
            "else": {
                "step": "if",
                "condition": {
                    "type": "regime",
                    "field": "distribution_count_25d",
                    "gte": 8,
                },
                "then": _weight_step(0.0, 0.80, 0.20),
                "else": weekly_tiers,
            },
        },
    }

    universe = {
        "step": "select",
        "top_k": len(BASKET),
        "from": {
            "step": "filter",
            "source": "daily_screener",
            "sort": {"field": "overall_score", "direction": "desc"},
            "criteria": {
                "type": "in_tickers",
                "tickers": ["SPY", GROWTH_ETF, DEFENSIVE_ETF, CASH_ETF],
            },
            "limit_per_day": len(BASKET) + 1,
        },
    }

    return {
        "schema_version": 1,
        "meta": {
            "title": "ETF rotation VUG/VTV/SGOV — declarative graph v1",
            "policy_engine": "graph_v1",
        },
        "lean_framework": {
            "alpha": {
                "max_positions": 3,
                "min_hold_days": 0,
                "stop_loss_pct": 0,
                "stop_cooldown_days": 0,
                "circuit_drawdown_threshold": 1,
                "circuit_pause_days": 1,
            },
            "portfolio": {
                "max_positions": 3,
                "max_weight": 1.0,
                "min_weight": 0.001,
                "target_atr_risk": 0.001,
            },
            "regime": {"source": "market_regime_signals_daily"},
            "exits": {"mode": "topn"},
        },
        "root": {"step": "group", "children": [policy, universe]},
    }


def build_spec(
    *,
    ir_id: str,
    title: str = "ETF rotation VUG/VTV/SGOV — graph v1",
    notes: str = "",
) -> dict[str, Any]:
    """Return ``{ir_id, title, spec_json, notes, spec_schema_version}`` for ``save_spec``."""
    doc = etf_rotation_graph_v1_dict()
    return {
        "ir_id": ir_id,
        "title": title,
        "spec_json": json.dumps(doc),
        "notes": notes,
        "spec_schema_version": 1,
    }
