"""
ETF sector allocation + regime leverage VeraLab spec builder.

Use ``build_spec(...)`` to produce a JSON string ready for ``save_spec`` in
``vera-mcp-backtest``.  Defaults match ``tests/fixtures/ir/sector_etf_v1.json``.

Model overview
--------------
Regime tier 100 → 3x leveraged ETFs in top ``sector_long_n`` sectors (up to 90% exposure)
Regime tier  67 → 2x leveraged ETFs in top N sectors (up to 60% exposure)
Regime tier  33 → base sector ETFs in top N sectors (up to 30% exposure)
Regime tier   0 → inverse ETFs in bottom ``sector_short_n`` sectors (up to 40% exposure)

Sector selection is driven by avg RS rating of the underlying stocks in each sector
(computed daily from daily_screener, which excludes ETF tickers automatically).

Liquidity note
--------------
Some 2x ETFs (ROM, UCC, UGE, UYG, URE) have ADV < 100K — they will be included
but may exhibit slippage in backtests.  Use ``sector_long_n ≤ 3`` or remove sectors
without liquid levered ETFs to reduce exposure to illiquid instruments.
"""

from __future__ import annotations

import json
from typing import Any

from sigmarail_lab.ir.sector_etf_constants import DEFAULT_ETF_MAP


def build_spec(
    *,
    ir_id: str,
    title: str = "Sector ETF Allocation + Regime Leverage v1",
    sector_long_n: int = 4,
    sector_short_n: int = 3,
    broad_inverse_etf: str = "SPXS",
    etf_map: dict | None = None,
    max_long_exposure: float = 0.90,
    max_inverse_exposure: float = 0.40,
    max_weight_per_etf: float = 0.30,
    min_weight: float = 0.05,
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
        Unique spec identifier (used as ``SIGMARAIL_STRATEGY_ID`` in LEAN).
    sector_long_n : int
        Top N sectors to go long (1-11).
    sector_short_n : int
        Bottom N sectors to short via inverse ETFs when regime tier == 0 (1-11).
    broad_inverse_etf : str
        Fallback inverse ETF when a sector has no specific inverse (e.g. SPXS, SH).
    max_long_exposure : float
        Maximum gross long equity exposure before regime scaling (0..1).
        Actual exposure = max_long_exposure × weekly_allocation_fraction.
    max_inverse_exposure : float
        Maximum inverse ETF exposure when tier == 0 (0..1).
    max_weight_per_etf : float
        Per-ETF weight cap (0..1).
    min_weight : float
        Skip ETFs below this weight threshold (0..1).
    min_price, min_volume : float, int
        Screener filters for the stock universe (used to compute sector RS).
    limit_per_day : int
        Max screener rows/day (stock universe for RS computation).
    """
    resolved_etf_map = etf_map if etf_map is not None else DEFAULT_ETF_MAP
    # Derive always_include from the etf_map so they stay in sync.
    always_include = sorted(
        {sym for entry in resolved_etf_map.values() for sym in entry.values() if sym}
        | {"SPY", broad_inverse_etf}
    )

    doc: dict[str, Any] = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {
            "UniverseSelection": {
                "Type": "VeraScreenerUniverseSelectionModel",
                "Parameters": {},
            },
            "Alpha": {
                "Type": "VeraSectorEtfAlphaModel",
                "Parameters": {
                    "sector_long_n": sector_long_n,
                    "sector_short_n": sector_short_n,
                    "broad_inverse_etf": broad_inverse_etf,
                    "etf_map": resolved_etf_map,
                },
            },
            "PortfolioConstruction": {
                "Type": "VeraSectorEtfPortfolioConstructionModel",
                "Parameters": {
                    "max_long_exposure": max_long_exposure,
                    "max_inverse_exposure": max_inverse_exposure,
                    "max_weight_per_etf": max_weight_per_etf,
                    "min_weight": min_weight,
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
                        {"type": "in_tickers", "tickers": always_include},
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
                "always_include_tickers": always_include,
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
