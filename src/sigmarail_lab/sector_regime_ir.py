"""
Sector allocation + regime exposure VeraLab spec builder.

Use ``build_spec(...)`` to produce a JSON string suitable for ``save_spec`` in
``vera-mcp-backtest``.  Defaults match ``tests/fixtures/ir/sector_regime_v1.json``.

Key design choices:
- Broad universe (price ≥ $10, volume ≥ 500K) so every sector has enough coverage.
- ``projection: [sector, rs_rating, ...]`` enables per-sector RS ranking at runtime.
- Equity budget = ``weekly_allocation_fraction × max_total_exposure`` — smoothed weekly
  regime signal drives allocation, daily clamps stop new entries but don't force exits.
- Top ``sector_top_n`` sectors by avg RS get proportional budget slices.
- Within each sector: top ``stocks_per_sector`` by overall_score, ATR-sized.
"""

from __future__ import annotations

import json
from typing import Any


def build_spec(
    *,
    ir_id: str,
    title: str = "Sector Allocation + Regime Exposure v1",
    sector_top_n: int = 4,
    stocks_per_sector: int = 5,
    max_total_exposure: float = 0.90,
    max_weight_per_stock: float = 0.12,
    min_weight: float = 0.02,
    target_atr_risk: float = 0.003,
    min_hold_days: int = 5,
    stop_loss_pct: float = 0.08,
    stop_cooldown_days: int = 10,
    circuit_drawdown_threshold: float = 0.10,
    circuit_pause_days: int = 20,
    min_price: float = 10.0,
    min_volume: int = 500_000,
    limit_per_day: int = 500,
    notes: str = "",
) -> dict[str, Any]:
    """
    Return ``{ir_id, title, spec_json, notes}`` — pass directly to ``save_spec``.

    Parameters
    ----------
    ir_id : str
        Unique identifier (used as ``SIGMARAIL_STRATEGY_ID`` inside LEAN).
    sector_top_n : int
        Number of top-ranked sectors to invest in.
    stocks_per_sector : int
        Maximum positions per sector.
    max_total_exposure : float
        Maximum gross equity exposure before regime scaling (0..1).
    max_weight_per_stock : float
        Hard cap per individual position weight (0..1).
    min_weight : float
        Minimum position weight; positions below this are skipped.
    target_atr_risk : float
        Target daily P&L risk per position as fraction of portfolio (0..1).
    min_price, min_volume : float, int
        Universe filters (applied in addition to SPY always-include).
    limit_per_day : int
        Maximum rows from daily_screener per date (controls memory).
    """
    doc: dict[str, Any] = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {
            "UniverseSelection": {
                "Type": "VeraScreenerUniverseSelectionModel",
                "Parameters": {},
            },
            "Alpha": {
                "Type": "VeraSectorAlphaModel",
                "Parameters": {
                    "sector_top_n": sector_top_n,
                    "stocks_per_sector": stocks_per_sector,
                    "min_hold_days": min_hold_days,
                    "stop_loss_pct": stop_loss_pct,
                    "stop_cooldown_days": stop_cooldown_days,
                    "circuit_drawdown_threshold": circuit_drawdown_threshold,
                    "circuit_pause_days": circuit_pause_days,
                },
            },
            "PortfolioConstruction": {
                "Type": "VeraSectorPortfolioConstructionModel",
                "Parameters": {
                    "sector_top_n": sector_top_n,
                    "stocks_per_sector": stocks_per_sector,
                    "max_total_exposure": max_total_exposure,
                    "max_weight_per_stock": max_weight_per_stock,
                    "min_weight": min_weight,
                    "target_atr_risk": target_atr_risk,
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
        "VeraBase": {
            "Universe": {
                "source": "daily_screener",
                "criteria": {
                    "type": "any",
                    "items": [
                        {"type": "in_tickers", "tickers": ["SPY"]},
                        {
                            "type": "all",
                            "items": [
                                {"type": "gte", "column": "close", "value": min_price},
                                {"type": "gte", "column": "volume", "value": min_volume},
                            ],
                        },
                    ],
                },
                "projection": ["sector", "rs_rating", "overall_score", "atr_pct_14d"],
                "limit_per_day": limit_per_day,
                "always_include_tickers": ["SPY"],
                "sort_field": "overall_score",
                "sort_direction": "desc",
            }
        },
    }
    return {
        "ir_id": ir_id,
        "title": title,
        "spec_json": json.dumps(doc),
        "notes": notes,
        "spec_schema_version": 2,
    }
