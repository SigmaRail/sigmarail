"""Build VeraLab JSON specs for TQQQ tactical and buy-and-hold baselines."""

from __future__ import annotations

import json
from typing import Any


def _tqqq_universe_block(trade_ticker: str = "TQQQ") -> dict[str, Any]:
    always = ["SPY", "QQQ", trade_ticker]
    return {
        "source": "daily_screener",
        "criteria": {
            "type": "in_tickers",
            "tickers": always,
        },
        "projection": [
            "pct_from_sma20d",
            "drawdown_from_50d_high",
            "up_days_last_3",
            "near_sma20_flag",
            "downside_reversal_flag",
            "two_closes_below_sma20",
            "first_up_day_low",
            "extended_above_sma20_flag",
            "close",
        ],
        "limit_per_day": 10,
        "always_include_tickers": always,
    }


def build_tactical_spec(
    *,
    ir_id: str,
    title: str = "TQQQ Tactical v1 (SMA proxy)",
    notes: str = "",
    **alpha_params: Any,
) -> dict[str, Any]:
    params = {
        "signal_ticker": "QQQ",
        "trade_ticker": "TQQQ",
        "base_weight": 0.10,
        "max_weight": 0.20,
        "qqq_pullback_min": 0.05,
        "max_pct_from_sma20_entry": 0.08,
        "trim_pct_from_sma20": 0.10,
        "trim_fraction_on_reversal": 0.15,
        "exit_on_two_closes_below_sma20": True,
        "exit_on_close_below_first_up_day_low": True,
        "require_spy_bull": True,
        **alpha_params,
    }
    doc: dict[str, Any] = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {
            "UniverseSelection": {
                "Type": "VeraScreenerUniverseSelectionModel",
                "Parameters": {},
            },
            "Alpha": {
                "Type": "VeraTqqqTacticalAlphaModel",
                "Parameters": params,
            },
            "PortfolioConstruction": {
                "Type": "VeraTqqqTacticalPortfolioConstructionModel",
                "Parameters": params,
            },
            "Execution": {
                "Type": "VeraScreenerExecutionModel",
                "Parameters": {},
            },
            "RiskManagement": {
                "Type": "NullRiskManagementModel",
                "Parameters": {},
            },
        },
        "AlgorithmParameters": {},
        "VeraBase": {"Universe": _tqqq_universe_block(params["trade_ticker"])},
    }
    return {
        "ir_id": ir_id,
        "title": title,
        "spec_json": json.dumps(doc),
        "notes": notes,
        "spec_schema_version": 2,
    }


def build_buyhold_spec(
    *,
    ir_id: str,
    trade_ticker: str = "TQQQ",
    target_weight: float = 1.0,
    title: str | None = None,
    notes: str = "Buy-and-hold baseline for tactical comparison",
) -> dict[str, Any]:
    title = title or f"{trade_ticker} Buy-and-Hold v1"
    always = ["SPY", "QQQ", trade_ticker]
    doc: dict[str, Any] = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {
            "UniverseSelection": {
                "Type": "VeraScreenerUniverseSelectionModel",
                "Parameters": {},
            },
            "Alpha": {
                "Type": "VeraTqqqTacticalAlphaModel",
                "Parameters": {
                    "signal_ticker": "QQQ",
                    "trade_ticker": trade_ticker,
                    "base_weight": target_weight,
                    "max_weight": target_weight,
                    "buyhold_mode": True,
                },
            },
            "PortfolioConstruction": {
                "Type": "VeraTqqqTacticalPortfolioConstructionModel",
                "Parameters": {
                    "signal_ticker": "QQQ",
                    "trade_ticker": trade_ticker,
                    "base_weight": target_weight,
                    "max_weight": target_weight,
                    "buyhold_mode": True,
                },
            },
            "Execution": {
                "Type": "VeraScreenerExecutionModel",
                "Parameters": {},
            },
            "RiskManagement": {
                "Type": "NullRiskManagementModel",
                "Parameters": {},
            },
        },
        "AlgorithmParameters": {},
        "VeraBase": {"Universe": _tqqq_universe_block(trade_ticker)},
    }
    return {
        "ir_id": ir_id,
        "title": title,
        "spec_json": json.dumps(doc),
        "notes": notes,
        "spec_schema_version": 2,
    }
