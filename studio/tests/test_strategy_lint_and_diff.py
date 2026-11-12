"""Component 4 Tier 1: strategy_diff semantic diff + strategy_lint runtime contracts.

Covers ``sigmarail_studio_mcp.domains.strategy.strategy_diff`` and
``strategy_lint`` without ClickHouse (pure AST validation).
"""
from __future__ import annotations

import json

from sigmarail_studio_mcp.domains.strategy import strategy_diff, strategy_lint

from vera_query_core.strategy import PipelineDocument


def _minimal_pipeline() -> dict:
    return {
        "strategy_name": "lint-test",
        "universe": {"source": "screener"},
        "stages": [],
        "bindings": {},
        "risk": {},
        "execution": {},
    }


def _valid_pipeline_json(
    extra_bindings: dict | None = None,
    merge_bindings: bool = True,
) -> str:
    doc = _minimal_pipeline()
    if extra_bindings:
        if merge_bindings:
            doc["bindings"] = {**(doc["bindings"] or {}), **extra_bindings}
        else:
            doc["bindings"] = extra_bindings
    validated = PipelineDocument.model_validate(doc)
    return validated.model_dump_json()


def test_runtime_xor_conflict_is_error():
    payload = _valid_pipeline_json(
        extra_bindings={
            "pcm_scale": {"kind": "number", "expr": {"col": "weight"}},
            "alpha_confidence": {"kind": "number", "expr": {"lit": 0.8}},
        },
    )
    res = strategy_lint(payload)
    assert res["valid"] is False
    assert any(
        "pcm_scale" in (d.get("message") or "") and d.get("severity") == "error"
        for d in res["diagnostics"]
    )


def test_runtime_xor_absent_passes():
    payload = _valid_pipeline_json(
        extra_bindings={"alpha_confidence": {"kind": "number", "expr": {"lit": 0.8}}},
    )
    res = strategy_lint(payload)
    assert res["valid"] is True
    assert res["diagnostics"] == []


def test_risk_insight_tag_is_warning_not_error():
    payload = _valid_pipeline_json(
        extra_bindings={
            "risk_allow_pyramid_add": {"kind": "bool", "where": {"field": "insight.confidence", "op": "gt", "value": 0.7}},
        },
    )
    res = strategy_lint(payload)
    assert res["valid"] is True
    assert any(d.get("severity") == "warning" for d in res["diagnostics"])


def test_invalid_json_rejected():
    res = strategy_lint("{not json")
    assert res["valid"] is False
    assert res["code"] == "invalid_argument"


def test_diff_detects_slot_change():
    a = _valid_pipeline_json()
    b_doc = json.loads(a)
    b_doc["risk"] = {**(b_doc.get("risk") or {}), "max_positions": 8}
    b = PipelineDocument.model_validate(b_doc).model_dump_json()
    res = strategy_diff(a, b)
    assert res["has_diff"] is True
    assert any(d["slot"] == "risk" for d in res["diffs"])


def test_diff_identical_specs_no_diff():
    a = _valid_pipeline_json()
    res = strategy_diff(a, a)
    assert res["has_diff"] is False
    assert res["diffs"] == []
