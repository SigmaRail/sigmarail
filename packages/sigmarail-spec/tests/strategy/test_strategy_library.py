"""Library-level tests for strategy compile / decompile / validate.

These assertions used to run against the ``/v1/strategy/*`` endpoints. Those endpoints were
removed (``C-API-SURFACE-V1``): compiling a spec is a **library** capability
(``vera_query_core.strategy``), reached in-process by Studio and the MCP servers, so the
same coverage now targets the library directly — no HTTP, no second transport.
"""

from __future__ import annotations

from sigmarail_spec.strategy import (
    PipelineDocument,
    compile_pipeline,
    decompile_pipeline,
    list_factors,
)
from sigmarail_spec.strategy.presets import list_presets

_PIPELINE = {
    "strategy_name": "Test",
    "stages": [
        {
            "name": "Filter",
            "mode": "filter",
            "filters": [{"op": "gte", "left": "close", "right": 10}],
            "max_candidates": 50,
        }
    ],
}

_PIPELINE_WITH_RANK = {
    "strategy_name": "Test",
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
            "selection": {"method": "top_n", "n": 5},
        },
    ],
}


def test_list_factors() -> None:
    assert "momentum" in list_factors()


def test_list_presets() -> None:
    ids = [p["id"] for p in list_presets()]
    assert "minervini_sepa" in ids


def test_compile_produces_a_veralab_v1_document() -> None:
    spec = compile_pipeline(PipelineDocument.model_validate(_PIPELINE_WITH_RANK))
    assert spec["Kind"] == "VeraLabV1"


def test_compile_decompile_round_trip() -> None:
    spec = compile_pipeline(PipelineDocument.model_validate(_PIPELINE))
    doc = decompile_pipeline(spec)
    assert doc.model_dump()["stages"]


def test_compile_allows_unknown_factor_as_raw_column() -> None:
    bad = {
        "strategy_name": "Raw",
        "stages": [
            {
                "name": "Rank",
                "mode": "score",
                "factors": [{"name": "bogus", "weight": 1.0}],
                "selection": {"method": "top_n", "n": 5},
            },
        ],
    }
    compile_pipeline(PipelineDocument.model_validate(bad))  # must not raise
