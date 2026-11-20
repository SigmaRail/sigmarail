"""Build Policy B graph JSON for TQQQ tactical (declarative)."""

from __future__ import annotations

from typing import Any


def tqqq_tactical_graph_v1_dict(
    *,
    base_weight: float = 0.10,
    qqq_pullback_min: float = 0.05,
    max_pct_from_sma20_entry: float = 0.08,
    trim_pct_from_sma20: float = 0.10,
    trim_fraction: float = 0.15,
) -> dict[str, Any]:
    """Nested if/else policy tree + universe select for SPY/QQQ/TQQQ."""
    w_entry = str(base_weight)
    w_trim = f"trim:{trim_fraction}"
    entry_cond = {
        "type": "all",
        "items": [
            {
                "type": "signal",
                "ticker": "QQQ",
                "column": "drawdown_from_50d_high",
                "lte": -qqq_pullback_min,
            },
            {"type": "signal", "ticker": "QQQ", "column": "up_days_last_3", "gte": 3},
            {"type": "signal", "ticker": "TQQQ", "column": "near_sma20_flag", "eq": 1},
            {
                "type": "signal",
                "ticker": "TQQQ",
                "column": "pct_from_sma20d",
                "lte": max_pct_from_sma20_entry,
            },
        ],
    }
    exit_cond = {
        "type": "any",
        "items": [
            {"type": "signal", "ticker": "TQQQ", "column": "two_closes_below_sma20", "eq": 1},
            {
                "type": "signal_compare",
                "ticker": "TQQQ",
                "left": "close",
                "op": "lt",
                "right": "first_up_day_low",
            },
        ],
    }
    trim_cond = {
        "type": "all",
        "items": [
            {
                "type": "signal",
                "ticker": "TQQQ",
                "column": "pct_from_sma20d",
                "gte": trim_pct_from_sma20,
            },
            {"type": "signal", "ticker": "TQQQ", "column": "downside_reversal_flag", "eq": 1},
        ],
    }
    policy = {
        "step": "if",
        "condition": {"type": "regime", "field": "spy_above200d", "eq": 1},
        "then": {
            "step": "if",
            "condition": exit_cond,
            "then": {"step": "weight", "mode": "specified", "weights": {"TQQQ": "0"}},
            "else": {
                "step": "if",
                "condition": trim_cond,
                "then": {"step": "weight", "mode": "specified", "weights": {"TQQQ": w_trim}},
                "else": {
                    "step": "if",
                    "condition": entry_cond,
                    "then": {
                        "step": "weight",
                        "mode": "specified",
                        "weights": {"TQQQ": w_entry},
                    },
                    "else": {"step": "weight", "mode": "specified", "weights": {"TQQQ": "$HOLD"}},
                },
            },
        },
        "else": {"step": "weight", "mode": "specified", "weights": {"TQQQ": "0"}},
    }
    universe = {
        "step": "select",
        "top_k": 3,
        "from": {
            "step": "filter",
            "source": "daily_screener",
            "sort": {"field": "overall_score", "direction": "desc"},
            "criteria": {
                "type": "in_tickers",
                "tickers": ["SPY", "QQQ", "TQQQ"],
            },
            "limit_per_day": 3,
        },
    }
    return {
        "schema_version": 1,
        "meta": {
            "title": "TQQQ Tactical - declarative graph v1",
            "policy_engine": "graph_v1",
        },
        "lean_framework": {
            "alpha": {
                "max_positions": 1,
                "min_hold_days": 0,
                "stop_loss_pct": 0,
                "stop_cooldown_days": 0,
                "circuit_drawdown_threshold": 1,
                "circuit_pause_days": 1,
            },
            "portfolio": {
                "max_positions": 1,
                "max_weight": 0.2,
                "min_weight": 0.05,
                "target_atr_risk": 0.01,
            },
            "regime": {"source": "market_regime_signals_daily"},
            "exits": {"mode": "topn"},
        },
        "root": {"step": "group", "children": [policy, universe]},
    }
