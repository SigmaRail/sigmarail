"""All-weather fixed-universe VeraLabV1 JSON for LEAN Docker.

Must stay byte-identical to ``tests/fixtures/ir/all-weather-v1.json``.
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
      "Type": "ConstantAlphaModel",
      "Parameters": { "period_days": 30, "magnitude": 0.25 }
    },
    "PortfolioConstruction": {
      "Type": "VeraScreenerPortfolioConstructionModel",
      "Parameters": {
        "max_positions": 4,
        "max_weight": 0.3,
        "min_weight": 0.2,
        "target_atr_risk": 0.004
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
      "select": ["ticker", "close", "atr_14_pct"],
      "where": {
        "type": "any",
        "items": [
          { "type": "eq", "left": { "type": "col", "name": "ticker" }, "right": { "type": "lit", "value": "VTI" } },
          { "type": "eq", "left": { "type": "col", "name": "ticker" }, "right": { "type": "lit", "value": "TLT" } },
          { "type": "eq", "left": { "type": "col", "name": "ticker" }, "right": { "type": "lit", "value": "GLD" } },
          { "type": "eq", "left": { "type": "col", "name": "ticker" }, "right": { "type": "lit", "value": "TIP" } }
        ]
      },
      "order_by": [{ "field": "close", "direction": "desc" }],
      "limit_per_day": 10
    }
  }
}
"""
