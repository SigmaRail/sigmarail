"""Unit tests for the pipeline compiler (no ClickHouse)."""

from __future__ import annotations

import json

import pytest

from sigmarail_spec.strategy import (
    PipelineDocument,
    compile_pipeline,
)
from sigmarail_spec.strategy.presets import get_preset, list_presets


def _momentum_doc() -> PipelineDocument:
    return PipelineDocument.model_validate(
        {
            "strategy_name": "Momentum",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "filters": [
                        {"op": "gte", "left": "close", "right": 10},
                        {"op": "gte", "left": "rs_rating", "right": 70},
                    ],
                    "max_candidates": 101,
                },
                {
                    "name": "Rank",
                    "mode": "score",
                    "factors": [{"name": "momentum", "weight": 1.0}],
                    "selection": {"method": "top_n", "n": 10},
                },
            ],
        }
    )


def _leaf_count(nodes: list) -> int:
    return sum(
        _leaf_count(item["items"]) if item.get("type") in {"all", "any"} else 1
        for item in nodes
    )


def test_compile_momentum_single_factor() -> None:
    doc = _momentum_doc()
    spec = compile_pipeline(doc)
    assert spec["Kind"] == "VeraLabV1"
    assert spec["SchemaVersion"] == 2
    assert spec["Framework"]["Alpha"]["Type"] == "VeraScreenerAlphaModel"
    universe = spec["VeraBase"]["Universe"]
    assert "rs_rating" in universe["select"]
    assert universe["where"]["type"] == "all"
    assert len(universe["where"]["items"]) == 2


def test_compile_composite_multi_factor() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Value Momentum",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "filters": [{"op": "gte", "left": "close", "right": 10}],
                    "max_candidates": 101,
                },
                {
                    "name": "Rank",
                    "mode": "score",
                    "factors": [
                        {"name": "momentum", "weight": 0.50},
                        {"name": "value", "weight": 0.50},
                    ],
                    "selection": {"method": "top_n", "n": 10},
                },
            ],
        }
    )
    spec = compile_pipeline(doc)
    alpha = spec["Framework"]["Alpha"]
    assert alpha["Type"] == "VeraCompositeAlphaModel"
    # field_weights keys are physical L7 columns, not semantic factor names
    assert alpha["Parameters"]["field_weights"] == {
        "rs_rating": 0.50,
        "valuation_rating": 0.50,
    }
    universe = spec["VeraBase"]["Universe"]
    assert "rs_rating" in universe["select"]
    assert "valuation_rating" in universe["select"]


def test_compile_preserves_stage_documentation() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Documented",
            "stages": [
                {
                    "name": "Quality Filter",
                    "mode": "filter",
                    "filters": [{"op": "gte", "left": "close", "right": 10}],
                    "documentation": {
                        "purpose": "Keep liquid candidates",
                        "inputs": ["close", "volume"],
                        "expression": "close >= 10",
                        "confirmation": "At least one candidate remains",
                        "effect": "Narrows the universe",
                        "variables": {"min_price": "10"},
                        "notes": "Applied before ranking",
                    },
                },
                {
                    "name": "Momentum Rank",
                    "mode": "score",
                    "factors": [{"name": "momentum", "weight": 1.0}],
                    "documentation": {
                        "purpose": "Rank by momentum",
                        "variables": {"factor": "momentum"},
                    },
                },
            ],
        }
    )

    spec = compile_pipeline(doc)
    records = json.loads(spec["AlgorithmParameters"]["stage-documentation"])

    assert [record["mode"] for record in records] == ["filter", "score"]
    assert records[0]["name"] == "Quality Filter"
    assert records[0]["documentation"]["purpose"] == "Keep liquid candidates"
    assert records[1]["documentation"]["variables"] == {"factor": "momentum"}


def test_compile_passes_unknown_factor_as_raw_column() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Raw",
            "stages": [
                {
                    "name": "Rank",
                    "mode": "score",
                    "factors": [{"name": "not_a_real_factor", "weight": 1.0}],
                    "selection": {"method": "top_n", "n": 5},
                },
            ],
        }
    )
    spec = compile_pipeline(doc)
    # Unknown factor passes through as a raw physical column (flexible slots).
    assert spec["VeraBase"]["Universe"]["order_by"][0]["field"] == "not_a_real_factor"
def test_compile_pyramid_uses_pyramid_alpha() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Pyramid",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "filters": [{"op": "gte", "left": "close", "right": 10}],
                    "max_candidates": 50,
                },
                {
                    "name": "Rank",
                    "mode": "score",
                    "factors": [{"name": "momentum", "weight": 1.0}],
                    "selection": {"method": "top_n", "n": 10},
                },
                {
                    "name": "Scale In",
                    "mode": "pyramid",
                    "phases": [
                        {"name": "test", "size_pct": 0.50},
                        {"name": "full", "size_pct": 0.50},
                    ],
                },
            ],
        }
    )
    spec = compile_pipeline(doc)
    assert spec["Framework"]["Alpha"]["Type"] == "VeraPyramidAlphaModel"
    pcm = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert len(pcm["phases"]) == 2


def test_compile_exit_maps_to_progressive_risk() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Exit",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "filters": [{"op": "gte", "left": "close", "right": 10}],
                    "max_candidates": 50,
                },
                {
                    "name": "Sell",
                    "mode": "exit",
                    "tranches": [{"trigger_r": 2.5, "sell_pct": 0.20}],
                    "max_hold_days": 25,
                    "trailing_stop_pct": 0.15,
                },
            ],
        }
    )
    spec = compile_pipeline(doc)
    risk = spec["Framework"]["RiskManagement"]
    assert risk["Type"] == "SwingProgressiveRiskManagementModel"
    assert risk["Parameters"]["take_profit_r"] == 2.5
    assert risk["Parameters"]["max_holding_days"] == 25


def test_compile_hedge_alone_does_not_write_dead_algorithm_param() -> None:
    """Hedge config without uses[] must not emit dead hedge-instruments blob."""
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Hedged",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "filters": [{"op": "gte", "left": "close", "right": 10}],
                    "max_candidates": 50,
                },
            ],
            "hedge": {"instruments": [{"ticker": "SH", "max_allocation": 0.25}]},
        }
    )
    spec = compile_pipeline(doc)
    assert "hedge-instruments" not in (spec.get("AlgorithmParameters") or {})


def test_presets_compile() -> None:
    for preset in list_presets():
        doc = get_preset(preset["id"])
        spec = compile_pipeline(doc)
        assert spec["Kind"] == "VeraLabV1"
        assert spec["VeraBase"]["Universe"]["select"]


def test_minervini_preset_full_pipeline() -> None:
    from sigmarail_spec.strategy.setup_recipes import compose_minervini_sepa_with_setup

    doc = compose_minervini_sepa_with_setup()
    spec = compile_pipeline(doc)
    universe = spec["VeraBase"]["Universe"]
    assert universe["where"]["type"] == "all"
    where_blob = json.dumps(universe["where"])
    assert "vcp_atr_compression_5d_90d" not in where_blob
    assert "sma50d" in where_blob
    assert "code_33" not in where_blob
    assert "vcp_atr_compression_5d_90d" in universe["select"]
    assert "vcp_volume_dryup_5d_90d" in universe["select"]
    assert "ary_eps_growth_3y_cagr" in universe["select"] or "arq_eps_acceleration_q3" in universe["select"]
    alpha = spec["Framework"]["Alpha"]["Parameters"]
    assert alpha.get("setup_where")
    assert "vcp_atr_compression_5d_90d" in json.dumps(alpha["setup_where"])
    gate_ids = {g["id"] for g in alpha.get("gates") or []}
    assert "screen_1" in gate_ids
    assert "code_33" in gate_ids
    assert "screens_hit" in {c["alias"] for c in (universe.get("computed") or [])}
    assert spec["Framework"]["Alpha"]["Type"] == "VeraPyramidAlphaModel"
    risk_type = spec["Framework"]["RiskManagement"]["Type"]
    assert risk_type in (
        "SwingProgressiveRiskManagementModel",
        "CompositeRiskManagementModel",
    )
    if risk_type == "CompositeRiskManagementModel":
        models = spec["Framework"]["RiskManagement"]["Parameters"]["models"]
        assert any(m["Type"] == "VeraHedgeModel" for m in models)
        swing = next(m for m in models if m["Type"] == "SwingProgressiveRiskManagementModel")
        assert len(swing["Parameters"]["tranches"]) == 3
    else:
        assert len(spec["Framework"]["RiskManagement"]["Parameters"]["tranches"]) == 3
    assert "hedge-instruments" not in (spec.get("AlgorithmParameters") or {})
    assert "regime-gate" not in (spec.get("AlgorithmParameters") or {})
    assert any(s.get("name") == "regime" for s in spec["VeraBase"]["DataSources"])
    assert "membership" in spec["Framework"]["UniverseSelection"]["Parameters"]
    assert "membership" not in spec["Framework"]["Alpha"]["Parameters"]


def test_compile_nested_group_lowers_to_all_and_any() -> None:
    """FilterGroup trees recurse into nested all/any (mirrors decompiler)."""
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Nested",
            "stages": [
                {
                    "name": "Filter",
                    "mode": "filter",
                    "max_candidates": 101,
                    "filters": [
                        {"op": "gte", "left": "close", "right": 5},
                        {
                            "logic": "or",
                            "conditions": [
                                {"op": "gte", "left": "rs_rating", "right": 90},
                                {
                                    "logic": "and",
                                    "conditions": [
                                        {"op": "eq", "left": "pullback_ready", "right": 1},
                                        {
                                            "op": "gte",
                                            "left": "close",
                                            "right": {
                                                "type": "formula",
                                                "op": "*",
                                                "args": [
                                                    {"type": "col", "name": "low_52w"},
                                                    {"type": "lit", "value": 1.30},
                                                ],
                                            },
                                            "right_kind": "formula",
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }
    )
    spec = compile_pipeline(doc)
    universe = spec["VeraBase"]["Universe"]
    where = universe["where"]
    assert where["type"] == "all"
    assert [item["type"] for item in where["items"]] == ["gte", "any"]
    any_group = where["items"][1]
    assert [item["type"] for item in any_group["items"]] == ["gte", "all"]
    nested_all = any_group["items"][1]
    formula = nested_all["items"][1]["right"]
    assert formula["type"] == "formula"
    assert formula["args"][0] == {"type": "col", "name": "low_52w"}
    # Formula-referenced columns must be projected for the compiled query.
    assert "low_52w" in universe["select"]


def test_stage_names_must_be_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        PipelineDocument.model_validate(
            {
                "strategy_name": "Dup",
                "stages": [
                    {"name": "A", "mode": "filter", "filters": []},
                    {"name": "A", "mode": "score", "factors": []},
                ],
            }
        )


def test_depends_on_must_reference_existing_stage() -> None:
    with pytest.raises(ValueError, match="depends_on"):
        PipelineDocument.model_validate(
            {
                "strategy_name": "BadDep",
                "stages": [
                    {"name": "A", "mode": "filter", "filters": []},
                    {"name": "B", "mode": "score", "factors": [], "depends_on": "missing"},
                ],
            }
        )


def test_signal_trigger_and_atr_columns_walked_into_select() -> None:
    """Entry triggers and ATR stop loss are walked into universe select."""
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "TriggerSelectTest",
            "stages": [
                {
                    "name": "Signal",
                    "mode": "signal",
                    "entry_triggers": [
                        {"type": "pivot_breakout", "lookback_days": 5, "volume_multiplier": 1.5}
                    ],
                    "stop_loss": {"type": "atr", "multiplier": 2.0},
                }
            ],
        }
    )
    spec = compile_pipeline(doc)
    select = spec["VeraBase"]["Universe"]["select"]
    for expected in ("high", "high_90d", "volume", "avg_vol_50d", "breakout_signal", "atr_14_pct"):
        assert expected in select, f"{expected} missing from select"


def test_compile_merges_trigger_columns_into_skinny_select() -> None:
    """Skinny user select still receives trigger-required columns (auto-fill)."""
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "SkinnySelectFilled",
            "universe": {
                "source": "screener",
                "select": ["ticker", "close"],  # skinny select omitting high_90d
            },
            "stages": [
                {
                    "name": "Signal",
                    "mode": "signal",
                    "entry_triggers": [
                        {"type": "pivot_breakout", "lookback_days": 5, "volume_multiplier": 1.5}
                    ],
                }
            ],
        }
    )
    spec = compile_pipeline(doc)
    select = spec["VeraBase"]["Universe"]["select"]
    assert "high_90d" in select
    assert "ticker" in select
    assert "close" in select


def test_neq_lowers_to_not_eq() -> None:
    doc = PipelineDocument.model_validate(
        {
            "strategy_name": "Exclude Bio",
            "universe": {
                "source": "screener",
                "screen": [
                    {
                        "op": "neq",
                        "left": "industry",
                        "right": "Biotechnology",
                        "right_kind": "lit",
                    }
                ],
            },
            "stages": [
                {
                    "name": "Rank",
                    "mode": "score",
                    "factors": [{"name": "momentum", "weight": 1.0}],
                }
            ],
        }
    )
    spec = compile_pipeline(doc)
    where = spec["VeraBase"]["Universe"]["where"]
    assert where == {
        "type": "not",
        "item": {
            "type": "eq",
            "left": {"type": "col", "name": "industry"},
            "right": {"type": "lit", "value": "Biotechnology"},
        },
    }
    assert "industry" in spec["VeraBase"]["Universe"]["select"]


