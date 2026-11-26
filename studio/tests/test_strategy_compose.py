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
    "Alpha": {
        "Type": "SigmaRailScreenerAlphaModel",
        "Parameters": {"signal_mode": "screen", "signal_duration_days": 14},
    },
    "PortfolioConstruction": {
        "Type": "SigmaRailScreenerPortfolioConstructionModel",
        "Parameters": {"min_weight": 0.05, "max_weight": 0.25, "max_positions": 10},
    },
    "RiskManagement": {
        "Type": "SigmaRailRiskManagementModel",
        "Parameters": {"rules": []},
    },
    "Execution": {
        "Type": "SigmaRailScreenerExecutionModel",
        "Parameters": {"fill_session": "moo"},
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
                "SchemaVersion": 3,
                "Kind": "SigmaRailStrategyV1",
                "SigmaRail": {},
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
    assert catalog.get("version") == 2
    assert isinstance(catalog.get("slots"), list)


def test_compose_replaces_universe() -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        framework=_STUB_FRAMEWORK,
    )
    assert spec["Kind"] == "SigmaRailStrategyV1"
    assert spec["Framework"]["UniverseSelection"]["Parameters"]["query"] == _SAMPLE_UNIVERSE
    assert spec["Framework"]["Alpha"]["Type"] == "SigmaRailScreenerAlphaModel"


def test_compose_framework_overrides(stub_template: str) -> None:
    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        template_id=stub_template,
        framework_overrides={
            "Alpha": {
                "Parameters": {"signal_duration_days": 21},
            }
        },
    )
    assert spec["Framework"]["Alpha"]["Parameters"]["signal_duration_days"] == 21


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
        "Alpha": {
            "Type": "SigmaRailScreenerAlphaModel",
            "Parameters": {"signal_mode": "composite_score", "signals": [{"field_weights": {"rs_rating": 1.0}}]},
        },
        "PortfolioConstruction": {
            "Type": "SigmaRailScreenerPortfolioConstructionModel",
            "Parameters": {"allocation_policy": "equal_weight", "max_positions": 10},
        },
        "RiskManagement": {
            "Type": "SigmaRailRiskManagementModel",
            "Parameters": {"rules": [{"kind": "trailing_stop", "parameters": {"maximum_drawdown_percent": 0.05}}]},
        },
        "Execution": {
            "Type": "SigmaRailScreenerExecutionModel",
            "Parameters": {"fill_session": "moo"},
        },
    }

    spec = compose_strategy_v1(
        universe_spec=_SAMPLE_UNIVERSE,
        framework=assembled_fw,
    )

    assert spec["Kind"] == "SigmaRailStrategyV1"
    assert spec["SchemaVersion"] == 3
    assert spec["Framework"]["UniverseSelection"]["Parameters"]["query"] == _SAMPLE_UNIVERSE
    assert spec["Framework"]["Alpha"]["Type"] == "SigmaRailScreenerAlphaModel"
    assert spec["Framework"]["Alpha"]["Parameters"]["signals"][0]["field_weights"] == {"rs_rating": 1.0}
    assert spec["Framework"]["RiskManagement"]["Type"] == "SigmaRailRiskManagementModel"
    assert spec["Framework"]["RiskManagement"]["Parameters"]["rules"][0]["kind"] == "trailing_stop"
    assert spec["Framework"]["PortfolioConstruction"]["Type"] == "SigmaRailScreenerPortfolioConstructionModel"
    assert spec["Framework"]["Execution"]["Type"] == "SigmaRailScreenerExecutionModel"


def test_compose_rejects_alternate_lean_classes() -> None:
    framework = copy.deepcopy(_STUB_FRAMEWORK)
    framework["Alpha"]["Type"] = "ConstantAlphaModel"
    with pytest.raises(ValueError, match="fixed SigmaRail implementation"):
        compose_strategy_v1(universe_spec=_SAMPLE_UNIVERSE, framework=framework)
