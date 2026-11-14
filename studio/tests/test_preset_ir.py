"""SigmaRail-owned presets compile through the core universe query contract."""

from __future__ import annotations

import json

import pytest
from django.test import Client

from screens.adapter import ALL_SCREEN_PRESETS, list_screen_presets, preset_to_universe_spec
from screens.ir_preview import validate_universe_ir_spec


@pytest.mark.parametrize("preset_id", ALL_SCREEN_PRESETS)
def test_preset_ir_validates(preset_id: str) -> None:
    spec = preset_to_universe_spec(preset_id)
    _, sql, params = validate_universe_ir_spec(spec)
    assert spec["version"] in (1, 2)
    assert "ticker" in spec["select"]
    assert isinstance(spec["where"], dict)
    assert "screener_price_tech_daily" in sql
    assert "start_date" in params and "end_date" in params


def test_adapter_presets_are_local_core_templates() -> None:
    for preset_id in ALL_SCREEN_PRESETS:
        spec = preset_to_universe_spec(preset_id)
        assert isinstance(spec, dict)
        validate_universe_ir_spec(spec)


@pytest.mark.django_db
def test_preset_universe_endpoint() -> None:
    response = Client().get("/api/screens/presets/leaders/universe")
    assert response.status_code == 200
    body = response.json()
    assert body["preset_id"] == "leaders"
    assert body["spec"]["order_by"][0]["field"] == "overall_score"


@pytest.mark.django_db
def test_compose_from_screen_preset_preserves_strategy_wire_shape() -> None:
    response = Client().post(
        "/api/backtests/compose",
        data=json.dumps(
            {
                "framework": {
                    "UniverseSelection": {"Type": "VeraScreenerUniverseSelectionModel", "Parameters": {}},
                    "Alpha": {"Type": "RsiAlphaModel", "Parameters": {"period": 14, "resolution": "Daily"}},
                    "PortfolioConstruction": {"Type": "EqualWeightingPortfolioConstructionModel", "Parameters": {}},
                    "RiskManagement": {"Type": "MaximumDrawdownPercentPerSecurity", "Parameters": {}},
                    "Execution": {"Type": "ImmediateExecutionModel", "Parameters": {}},
                },
                "title": "Leaders BT",
                "universe": {"source": "screen_preset", "preset_id": "leaders"},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["spec"]["VeraBase"]["Universe"]["version"] in (1, 2)
    assert response.json()["lineage"]["studio_spec_hash"]


@pytest.mark.django_db
def test_presets_list_marks_core_templates_backtestable() -> None:
    data = Client().get("/api/screens/presets").json()
    leaders = next(item for item in data if item["id"] == "leaders")
    assert leaders["backtestable"] is True
    assert {item["id"] for item in list_screen_presets()} == set(ALL_SCREEN_PRESETS)
