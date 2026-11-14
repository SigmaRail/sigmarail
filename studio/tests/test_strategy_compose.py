"""Tests for strategy composition (slice 2.1)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import screens.strategy_compose as strategy_compose
from screens.strategy_compose import (
    compose_strategy_v1,
    list_strategy_templates,
    load_framework_catalog,
    suggest_ir_id,
    validate_composed_spec,
)

_SAMPLE_UNIVERSE = {
    "version": 1,
    "from": "daily_screener",
    "select": ["ticker", "close", "rs_rating"],
    "where": {
        "type": "gte",
        "left": {"type": "col", "name": "rs_rating"},
        "right": {"type": "lit", "value": 70},
    },
    "order_by": [{"field": "rs_rating", "direction": "desc"}],
    "limit_per_day": 25,
}

_STUB_FRAMEWORK = {
    "UniverseSelection": {
        "Type": "VeraScreenerUniverseSelectionModel",
        "Parameters": {},
    },
    "Alpha": {
        "Type": "RsiAlphaModel",
        "Parameters": {"period": 14, "resolution": "Daily"},
    },
    "PortfolioConstruction": {
        "Type": "EqualWeightingPortfolioConstructionModel",
        "Parameters": {"min_weight": 0.05, "max_weight": 0.25, "max_positions": 10},
    },
    "RiskManagement": {
        "Type": "MaximumDrawdownPercentPerSecurity",
        "Parameters": {"maximum_drawdown_percent": 0.05},
    },
    "Execution": {
        "Type": "ImmediateExecutionModel",
        "Parameters": {},
    },
}


@pytest.fixture
def stub_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Register a one-off template JSON for override/merge tests (not shipped in product)."""
    tid = "compose_stub"
    monkeypatch.setattr(strategy_compose, "STRATEGY_TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(
        strategy_compose,
        "_STRATEGY_TEMPLATE_META",
        {tid: {"label": "Compose Stub", "description": "test-only"}},
    )
    (tmp_path / f"{tid}.json").write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Kind": "VeraLabV1",
                "VeraBase": {},
                "Framework": copy.deepcopy(_STUB_FRAMEWORK),
                "AlgorithmParameters": {"regime-source": "screener"},
            }
        ),
        encoding="utf-8",
    )
    return tid


def test_list_strategy_templates_empty() -> None:
    """Product ships no legacy framework JSON templates; Studio seed is catalog minervini_sepa."""
    assert list_strategy_templates() == []


def test_load_framework_catalog() -> None:
    catalog = load_framework_catalog()
    assert catalog.get("version") == 1
    assert isinstance(catalog.get("slots"), list)


def test_compose_replaces_universe() -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        framework=_STUB_FRAMEWORK,
    )
    assert spec["Kind"] == "VeraLabV1"
    assert spec["VeraBase"]["Universe"] == _SAMPLE_UNIVERSE
    assert spec["Framework"]["Alpha"]["Type"] == "RsiAlphaModel"


def test_compose_framework_overrides(stub_template: str) -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        template_id=stub_template,
        framework_overrides={
            "Alpha": {
                "Parameters": {"period": 21, "resolution": "Daily"},
            }
        },
    )
    assert spec["Framework"]["Alpha"]["Parameters"]["period"] == 21


def test_compose_framework_overrides_deep_merge(stub_template: str) -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        template_id=stub_template,
        framework_overrides={
            "PortfolioConstruction": {
                "Parameters": {
                    "max_positions": 15,
                    "max_weight": 0.2,
                },
            },
        },
    )
    pcm = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert pcm["max_positions"] == 15
    assert pcm["max_weight"] == 0.2
    assert pcm["min_weight"] == 0.05


def test_compose_rejects_flat_framework_overrides(stub_template: str) -> None:
    with pytest.raises(ValueError, match="unknown framework slot"):
        compose_strategy_v1(
            universe_spec=_SAMPLE_UNIVERSE,
            template_id=stub_template,
            framework_overrides={"max_positions": 10},
        )


def test_compose_requires_template_or_framework() -> None:
    with pytest.raises(ValueError, match="template_id is required"):
        compose_strategy_v1(universe_spec=_SAMPLE_UNIVERSE)


def test_compose_algorithm_parameters(stub_template: str) -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        template_id=stub_template,
        algorithm_parameters={"exit-mode": "custom"},
    )
    assert spec["AlgorithmParameters"]["exit-mode"] == "custom"
    assert spec["AlgorithmParameters"]["regime-source"] == "screener"


def test_compose_invalid_universe_version() -> None:
    bad = copy.deepcopy(_SAMPLE_UNIVERSE)
    bad.pop("version")
    with pytest.raises(ValueError, match="universe_query_v1"):
        compose_strategy_v1(universe_spec=bad, framework=_STUB_FRAMEWORK)


def test_compose_unknown_template() -> None:
    with pytest.raises(ValueError, match="unknown strategy template"):
        compose_strategy_v1(universe_spec=_SAMPLE_UNIVERSE, template_id="missing")


def test_suggest_ir_id_format() -> None:
    ir_id = suggest_ir_id("My Strategy", _SAMPLE_UNIVERSE)
    assert ir_id.startswith("studio-my-strategy-")
    assert len(ir_id.split("-")[-1]) == 6


def test_validate_composed_spec_uses_sigma_rail_schema() -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        framework=_STUB_FRAMEWORK,
    )
    ok, err = validate_composed_spec(spec)
    assert ok is True, err

    invalid = copy.deepcopy(spec)
    invalid["unexpected"] = True
    ok, err = validate_composed_spec(invalid)
    assert ok is False
    assert err is not None
    assert "unexpected" in err


def test_compose_custom_assembled_ensemble() -> None:
    assembled_fw = {
        "UniverseSelection": {
            "Type": "VeraScreenerUniverseSelectionModel",
            "Parameters": {},
        },
        "Alpha": {
            "Type": "CompositeAlphaModel",
            "Parameters": {
                "models": [
                    {
                        "Type": "VeraScreenerAlphaModel",
                        "Parameters": {"max_positions": 10, "stop_loss_pct": 0.08},
                    },
                    {
                        "Type": "RsiAlphaModel",
                        "Parameters": {"period": 14, "resolution": "Daily"},
                    },
                ]
            },
        },
        "PortfolioConstruction": {
            "Type": "ConfidenceWeightedPortfolioConstructionModel",
            "Parameters": {},
        },
        "RiskManagement": {
            "Type": "CompositeRiskManagementModel",
            "Parameters": {
                "models": [
                    {
                        "Type": "TrailingStopRiskManagementModel",
                        "Parameters": {"maximum_drawdown_percent": 0.05},
                    },
                    {
                        "Type": "MaximumSectorExposureRiskManagementModel",
                        "Parameters": {"maximum_sector_exposure": 0.25},
                    },
                ]
            },
        },
        "Execution": {
            "Type": "VolumeWeightedAveragePriceExecutionModel",
            "Parameters": {},
        },
    }

    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        framework=assembled_fw,
    )

    assert spec["Kind"] == "VeraLabV1"
    assert spec["SchemaVersion"] == 2
    assert spec["VeraBase"]["Universe"] == _SAMPLE_UNIVERSE
    assert spec["Framework"]["Alpha"]["Type"] == "CompositeAlphaModel"
    assert len(spec["Framework"]["Alpha"]["Parameters"]["models"]) == 2
    assert spec["Framework"]["RiskManagement"]["Type"] == "CompositeRiskManagementModel"
    assert len(spec["Framework"]["RiskManagement"]["Parameters"]["models"]) == 2
    assert spec["Framework"]["PortfolioConstruction"]["Type"] == "ConfidenceWeightedPortfolioConstructionModel"
    assert spec["Framework"]["Execution"]["Type"] == "VolumeWeightedAveragePriceExecutionModel"


def test_compose_all_qc_framework_permutations() -> None:
    """Adversarial validation: all supported QC Framework model permutations must compose and validate."""
    alpha_options = [
        {"Type": "RsiAlphaModel", "Parameters": {"period": 14, "resolution": "Daily"}},
        {"Type": "MacdAlphaModel", "Parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
        {"Type": "EmaCrossAlphaModel", "Parameters": {"fast_period": 10, "slow_period": 50}},
        {
            "Type": "CompositeAlphaModel",
            "Parameters": {
                "models": [
                    {"Type": "RsiAlphaModel", "Parameters": {"period": 14}},
                    {"Type": "MacdAlphaModel", "Parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
                ]
            },
        },
    ]

    pcm_options = [
        {"Type": "ConfidenceWeightedPortfolioConstructionModel", "Parameters": {"max_weight": 0.15}},
        {"Type": "RiskParityPortfolioConstructionModel", "Parameters": {"rebalance": "Daily"}},
        {"Type": "EqualWeightingPortfolioConstructionModel", "Parameters": {"rebalance": "Daily"}},
        {"Type": "SectorWeightingPortfolioConstructionModel", "Parameters": {"rebalance": "Weekly"}},
    ]

    risk_options = [
        {"Type": "TrailingStopRiskManagementModel", "Parameters": {"maximum_drawdown_percent": 0.05}},
        {"Type": "MaximumSectorExposureRiskManagementModel", "Parameters": {"maximum_sector_exposure": 0.30}},
        {"Type": "MaximumDrawdownPercentPerSecurity", "Parameters": {"maximum_drawdown_percent": 0.08}},
        {
            "Type": "CompositeRiskManagementModel",
            "Parameters": {
                "models": [
                    {"Type": "TrailingStopRiskManagementModel", "Parameters": {"maximum_drawdown_percent": 0.05}},
                    {"Type": "MaximumSectorExposureRiskManagementModel", "Parameters": {"maximum_sector_exposure": 0.25}},
                ]
            },
        },
    ]

    execution_options = [
        {"Type": "VolumeWeightedAveragePriceExecutionModel", "Parameters": {}},
        {"Type": "ImmediateExecutionModel", "Parameters": {}},
        {"Type": "StandardDeviationExecutionModel", "Parameters": {"resolution": "Minute"}},
    ]

    universe_options = [
        {"Type": "VeraScreenerUniverseSelectionModel", "Parameters": {}},
        {"Type": "ManualUniverseSelectionModel", "Parameters": {"symbols": ["AAPL", "NVDA", "SPY"]}},
        {"Type": "CoarseFundamentalUniverseSelectionModel", "Parameters": {"min_volume": 5000000, "min_price": 5}},
    ]

    for uni in universe_options:
        for alpha in alpha_options:
            for pcm in pcm_options:
                for risk in risk_options:
                    for exe in execution_options:
                        fw = {
                            "UniverseSelection": uni,
                            "Alpha": alpha,
                            "PortfolioConstruction": pcm,
                            "RiskManagement": risk,
                            "Execution": exe,
                        }
                        spec = compose_strategy_v1(
                            universe_spec=_SAMPLE_UNIVERSE,
                            framework=fw,
                        )
                        assert spec["Kind"] == "VeraLabV1"
                        assert spec["Framework"]["UniverseSelection"]["Type"] == uni["Type"]
                        assert spec["Framework"]["Alpha"]["Type"] == alpha["Type"]
                        assert spec["Framework"]["PortfolioConstruction"]["Type"] == pcm["Type"]
                        assert spec["Framework"]["RiskManagement"]["Type"] == risk["Type"]
                        assert spec["Framework"]["Execution"]["Type"] == exe["Type"]
