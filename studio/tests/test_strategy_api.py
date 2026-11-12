"""Django API tests for strategy pipeline endpoints."""

from __future__ import annotations

import json

import django
from django.test import Client


def _setup():
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


_setup()


def test_factors_endpoint() -> None:
    c = Client()
    r = c.get("/api/strategy/factors")
    assert r.status_code == 200
    assert "momentum" in r.json()["factors"]


def test_presets_endpoint() -> None:
    c = Client()
    r = c.get("/api/strategy/presets")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["presets"]]
    assert "minervini_sepa" in ids


def test_preset_detail_endpoint() -> None:
    c = Client()
    r = c.get("/api/strategy/presets/minervini_sepa")
    assert r.status_code == 200
    assert r.json()["stages"]


def test_compile_endpoint() -> None:
    c = Client()
    pipeline = {
        "strategy_name": "Test",
        "stages": [
            {
                "name": "F",
                "mode": "filter",
                "filters": [{"op": "gte", "left": "close", "right": 10}],
                "max_candidates": 50,
            },
            {
                "name": "R",
                "mode": "score",
                "factors": [{"name": "momentum", "weight": 1.0}],
                "selection": {"method": "top_n", "n": 5},
            },
        ],
    }
    r = c.post(
        "/api/strategy/pipelines/compile",
        data=json.dumps(pipeline),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["Kind"] == "VeraLabV1"


def test_compile_decompile_preserves_recursive_filter_group() -> None:
    c = Client()
    pipeline = {
        "strategy_name": "Nested",
        "stages": [
            {
                "name": "F",
                "mode": "filter",
                "filters": [
                    {
                        "logic": "and",
                        "conditions": [
                            {"op": "gt", "left": "close", "right": "sma50d", "right_kind": "col"},
                            {
                                "logic": "or",
                                "conditions": [
                                    {"op": "gte", "left": "rs_rating", "right": 70},
                                    {"op": "gte", "left": "volume", "right": "avg_vol_50d", "right_kind": "col"},
                                ],
                            },
                        ],
                    }
                ],
                "max_candidates": 50,
            }
        ],
    }
    compiled = c.post(
        "/api/strategy/pipelines/compile",
        data=json.dumps(pipeline),
        content_type="application/json",
    )
    assert compiled.status_code == 200
    decompiled = c.post(
        "/api/strategy/pipelines/decompile",
        data=json.dumps(compiled.json()),
        content_type="application/json",
    )
    assert decompiled.status_code == 200
    root = decompiled.json()["stages"][0]["filters"][0]
    assert root["logic"] == "and"
    assert root["conditions"][1]["logic"] == "or"


def test_compile_passes_unknown_factor_as_raw_column() -> None:
    c = Client()
    pipeline = {
        "strategy_name": "Raw",
        "stages": [
            {
                "name": "R",
                "mode": "score",
                "factors": [{"name": "bogus", "weight": 1.0}],
                "selection": {"method": "top_n", "n": 5},
            },
        ],
    }
    r = c.post(
        "/api/strategy/pipelines/compile",
        data=json.dumps(pipeline),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["Kind"] == "VeraLabV1"


def test_compile_portfolio_endpoint() -> None:
    c = Client()
    portfolio = {
        "name": "all_weather",
        "legs": [
            {"strategy_name": "equity", "stages": [{"name": "r", "mode": "score", "factors": [{"name": "momentum", "weight": 1.0}], "selection": {"method": "top_n", "n": 5}}]},
            {"strategy_name": "bonds", "stages": [{"name": "r", "mode": "score", "factors": [{"name": "value", "weight": 1.0}], "selection": {"method": "top_n", "n": 5}}]},
        ],
        "allocation": {"base": "risk_parity"},
    }
    r = c.post(
        "/api/strategy/pipelines/compile-portfolio",
        data=json.dumps(portfolio),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["Framework"]["Alpha"]["Type"] == "CompositeAlphaModel"


def test_decompile_portfolio_endpoint() -> None:
    c = Client()
    portfolio = {
        "name": "all_weather",
        "legs": [{"strategy_name": "equity", "stages": [{"name": "r", "mode": "score", "factors": [{"name": "momentum", "weight": 1.0}], "selection": {"method": "top_n", "n": 5}}]}],
        "allocation": {},
    }
    compiled = c.post(
        "/api/strategy/pipelines/compile-portfolio",
        data=json.dumps(portfolio),
        content_type="application/json",
    ).json()
    r = c.post(
        "/api/strategy/pipelines/decompile-portfolio",
        data=json.dumps(compiled),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert len(r.json()["legs"]) == 1


def test_golden_minervini_round_trip() -> None:
    from vera_query_core.strategy.presets import get_preset

    c = Client()
    preset = get_preset("minervini_sepa").model_dump(mode="json", exclude_none=True)
    compile_resp = c.post(
        "/api/strategy/pipelines/compile",
        data=json.dumps(preset),
        content_type="application/json",
    )
    assert compile_resp.status_code == 200
    spec = compile_resp.json()
    assert "DataSources" in spec["VeraBase"]
    assert "Pipeline" not in spec["VeraBase"] or spec["VeraBase"].get("Pipeline") is None
    assert "regime-gate" not in (spec.get("AlgorithmParameters") or {})
    assert "entry_triggers" in spec["Framework"]["Alpha"]["Parameters"]
    assert spec["Framework"]["Alpha"]["Type"] == "VeraPyramidAlphaModel"

    decompile_resp = c.post(
        "/api/strategy/pipelines/decompile",
        data=json.dumps(spec),
        content_type="application/json",
    )
    assert decompile_resp.status_code == 200
    decompiled = decompile_resp.json()
    assert decompiled["strategy_name"] == preset["strategy_name"]
    # SEPA honesty (C-STRATEGY-PIPELINE-SSOT): criteria live in membership/bindings,
    # not filter stages — the bare preset carries score/signal/pyramid/exit only.
    dec_modes = {s["mode"] for s in decompiled["stages"]}
    assert "filter" not in dec_modes
    # Every authored (mode, name) stage must survive the compile → decompile round trip.
    src_pairs = {(s["mode"], s["name"]) for s in preset["stages"]}
    dec_pairs = {(s["mode"], s["name"]) for s in decompiled["stages"]}
    assert src_pairs <= dec_pairs, f"lost stages: {sorted(src_pairs - dec_pairs)}"
    assert "Setup Group" in {s["name"] for s in decompiled["stages"]}
    modes = {s["mode"] for s in decompiled["stages"]}
    assert "pyramid" in modes
    assert "exit" in modes
    assert decompiled["risk"].get("regime_gate") is not None
    uses = (decompiled["risk"].get("regime_gate") or {}).get("uses") or []
    assert "scale_exposure" in uses
    assert "skip_pyramid_adds" in uses


def test_pipeline_schema_contract() -> None:
    """Verify that exported Pydantic schema for PipelineDocument matches expected fields in TS."""
    from vera_query_core.strategy.pipeline import PipelineDocument

    schema = PipelineDocument.model_json_schema()
    expected_top_fields = {
        "strategy_name",
        "stages",
        "universe",
        "sizing",
        "alpha",
        "hedge",
        "risk",
        "execution",
        "documentation",
    }
    assert expected_top_fields.issubset(set(schema.get("properties", {}).keys()))

    stage_schema = schema.get("$defs", {}).get("Stage", {})
    expected_stage_fields = {
        "name",
        "mode",
        "depends_on",
        "filters",
        "factors",
        "selection",
        "entry_triggers",
        "phases",
        "tranches",
        "instruments",
        "max_candidates",
        "max_positions",
        "stop_loss",
        "max_hold_days",
        "trailing_stop_pct",
        "documentation",
    }
    assert expected_stage_fields.issubset(set(stage_schema.get("properties", {}).keys()))
