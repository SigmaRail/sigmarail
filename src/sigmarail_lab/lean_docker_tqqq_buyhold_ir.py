"""TQQQ buy-and-hold baseline VeraLabV1 JSON for LEAN Docker.

Must stay byte-identical to ``tests/fixtures/ir/tqqq-buyhold-v1.json`` (see ``tests/test_resolver_kinds.py``).
"""

RAW_JSON = """{
  "SchemaVersion": 2,
  "Kind": "VeraLabV1",
  "Framework": {
    "UniverseSelection": {
      "Type": "VeraScreenerUniverseSelectionModel",
      "Parameters": {}
    },
    "Alpha": {
      "Type": "VeraTqqqTacticalAlphaModel",
      "Parameters": {
        "signal_ticker": "QQQ",
        "trade_ticker": "TQQQ",
        "base_weight": 1.0,
        "max_weight": 1.0,
        "buyhold_mode": true
      }
    },
    "PortfolioConstruction": {
      "Type": "VeraTqqqTacticalPortfolioConstructionModel",
      "Parameters": {
        "signal_ticker": "QQQ",
        "trade_ticker": "TQQQ",
        "base_weight": 1.0,
        "max_weight": 1.0,
        "buyhold_mode": true
      }
    },
    "Execution": {
      "Type": "VeraScreenerExecutionModel",
      "Parameters": {}
    },
    "RiskManagement": {
      "Type": "NullRiskManagementModel",
      "Parameters": {}
    }
  },
  "AlgorithmParameters": {},
  "VeraBase": {
    "Universe": {
      "version": 1,
      "from": "daily_screener",
      "select": [
        "ticker",
        "pct_from_sma20d",
        "drawdown_from_50d_high",
        "up_days_last_3",
        "near_sma20_flag",
        "downside_reversal_flag",
        "two_closes_below_sma20",
        "first_up_day_low",
        "extended_above_sma20_flag",
        "close"
      ],
      "where": {
        "type": "any",
        "items": [
          {
            "type": "eq",
            "left": { "type": "col", "name": "ticker" },
            "right": { "type": "lit", "value": "SPY" }
          },
          {
            "type": "eq",
            "left": { "type": "col", "name": "ticker" },
            "right": { "type": "lit", "value": "QQQ" }
          },
          {
            "type": "eq",
            "left": { "type": "col", "name": "ticker" },
            "right": { "type": "lit", "value": "TQQQ" }
          }
        ]
      },
      "order_by": [{ "field": "close", "direction": "desc" }],
      "limit_per_day": 10
    }
  }
}
"""
