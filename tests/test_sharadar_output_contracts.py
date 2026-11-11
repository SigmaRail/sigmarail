"""Sharadar-only SQL contracts for the additional materialized outputs."""

import json
from pathlib import Path

from sigmarail.transform_sql import discover_transform_specs

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = json.loads((ROOT / "spec/lineage-manifest.json").read_text())
SCHEMA = ROOT / "src/sigmarail/sql/schema"


def test_each_derived_output_has_a_registered_materialization_transform():
    specs = {spec.target: spec for spec in discover_transform_specs() if spec.target}
    derived = {table["name"] for table in LINEAGE["tables"] if table["kind"] == "derived"}
    assert set(specs) == derived


def test_vcp_sql_is_present_but_population_is_safely_held():
    path = SCHEMA / "201-schema-screener_vcp_pivot_daily.sql"
    spec = next(s for s in discover_transform_specs() if s.target == "screener_vcp_pivot_daily")
    assert path.is_file()
    assert spec.config.get("on_hold") is True
    assert spec.config.get("max_memory_usage", 0) >= 6_500_000_000


def test_new_sharadar_marts_keep_expected_source_closure():
    specs = {spec.target: spec for spec in discover_transform_specs() if spec.target}
    expected = {
        "asset_returns_daily": {"daily_metrics"},
        "factor_residuals": {"asset_returns_daily", "sector_factor_residuals_daily", "tickers"},
        "group_strength_daily": {"relative_strength_ranks", "daily_metrics", "ticker_classification_daily"},
        "market_context_daily": {"market_regime_signals_daily", "broad_market_breadth", "daily_metrics"},
        "regime_signals_canonical": {"daily_metrics", "daily_metrics_derived", "broad_market_breadth", "stage_analysis", "daily_price_sequence"},
        "symbol_technical_features_daily": {"daily_metrics", "market_regime_signals_daily"},
        "ticker_rvab_daily": {"screener_price_tech_daily", "screener_factor_daily"},
    }
    for target, sources in expected.items():
        assert target in specs
        assert sources <= set(specs[target].sources), (target, specs[target].sources)
