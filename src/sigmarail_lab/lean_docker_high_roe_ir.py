"""High-ROE quality basket VeraLabV1 JSON for LEAN Docker.

Must stay byte-identical to ``tests/fixtures/ir/high-roe-large-cap-quality-v1.json`` (see ``tests/test_resolver_kinds.py``).
"""

RAW_JSON = """{
  "SchemaVersion": 2,
  "Kind": "VeraLabV1",
  "Framework": {
    "UniverseSelection": {
      "Type": "HighRoeQualityUniverseSelectionModel",
      "Parameters": {
        "new_assets_per_month": 2,
        "min_market_cap_millions": 500,
        "min_ipo_days": 180
      }
    },
    "Alpha": {
      "Type": "ConstantAlphaModel",
      "Parameters": {
        "period_days": 30,
        "magnitude": 0.02
      }
    },
    "PortfolioConstruction": {
      "Type": "EqualWeightingPortfolioConstructionModel",
      "Parameters": {}
    },
    "Execution": {
      "Type": "ImmediateExecutionModel",
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
      "select": ["ticker", "overall_score"],
      "where": {
        "type": "gte",
        "left": { "type": "col", "name": "close" },
        "right": { "type": "lit", "value": 1 }
      },
      "order_by": [{ "field": "overall_score", "direction": "desc" }],
      "limit_per_day": 1
    }
  }
}
"""
