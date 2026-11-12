"""Preset → universe_query_v1 bridge tests."""

from __future__ import annotations

import json

import pytest
from django.test import Client

pytest.importorskip(
    "vera_query_core",
    reason="preset IR compatibility tests require the optional Vera runtime",
)

from screens.adapter import ALL_SCREEN_PRESETS, preset_to_universe_spec
from screens.ir_preview import validate_universe_ir_spec
from vera_query_core.screen_preset_ir import list_preset_ir_ids, preset_to_universe_query_v1


@pytest.mark.parametrize("preset_id", list(list_preset_ir_ids()))
def test_preset_ir_validates(preset_id: str) -> None:
    spec = preset_to_universe_query_v1(preset_id)
    validate_universe_ir_spec(spec)
    assert spec["version"] == 1
    assert "ticker" in spec["select"]
    assert "overall_score" in spec["select"]
    assert isinstance(spec["where"], dict)


def test_adapter_preset_covers_all_studio_presets() -> None:
    for pid in ALL_SCREEN_PRESETS:
        spec = preset_to_universe_spec(pid)
        assert isinstance(spec, dict)
        validate_universe_ir_spec(spec)


@pytest.mark.django_db
def test_preset_universe_endpoint() -> None:
    c = Client()
    resp = c.get("/api/screens/presets/leaders/universe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset_id"] == "leaders"
    assert body["spec"]["order_by"][0]["field"] == "overall_score"


@pytest.mark.django_db
def test_compose_from_screen_preset() -> None:
    c = Client()
    resp = c.post(
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
    assert resp.status_code == 200
    assert resp.json()["spec"]["VeraBase"]["Universe"]["version"] == 1
    assert resp.json()["lineage"]["studio_spec_hash"]


@pytest.mark.django_db
def test_presets_list_marks_backtestable() -> None:
    c = Client()
    resp = c.get("/api/screens/presets")
    assert resp.status_code == 200
    data = resp.json()
    leaders = next(p for p in data if p["id"] == "leaders")
    assert leaders.get("backtestable") is True
