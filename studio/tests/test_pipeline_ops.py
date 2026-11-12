"""Unit tests for pipeline_ops (no ClickHouse)."""

from __future__ import annotations

import pytest

from screens.pipeline_ops import apply_pipeline_ops, compile_and_hash


def _mini_pipeline() -> dict:
    return {
        "strategy_name": "Probe Patch Fixture",
        "gate_combine": "count",
        "min_screens": 1,
        "universe": {
            "source": "screener",
            "screen": [
                {
                    "logic": "and",
                    "conditions": [
                        {"op": "gte", "left": "rs_rating", "right": 80, "right_kind": "lit"},
                    ],
                }
            ],
        },
        "stages": [
            {
                "id": "screen_1",
                "name": "Screen 1",
                "mode": "score",
                "as_gate": True,
                "filters": [
                    {
                        "logic": "and",
                        "conditions": [
                            {
                                "id": "c-rs",
                                "op": "gte",
                                "left": "rs_rating",
                                "right": 90,
                                "right_kind": "lit",
                            }
                        ],
                    }
                ],
            }
        ],
        "sizing": {"policy": "equal_weight", "max_positions": 5},
        "risk": {"max_positions": 5},
        "execution": {"type": "market_order"},
    }


def test_add_condition_requires_rationale() -> None:
    with pytest.raises(ValueError, match="rationale"):
        apply_pipeline_ops(
            _mini_pipeline(),
            [
                {
                    "op": "add_condition",
                    "binding_id": "screen_1",
                    "condition": {"op": "gte", "left": "close", "right": 10, "right_kind": "lit"},
                    "annotation": {},
                }
            ],
        )


def test_add_condition_annotates_and_compiles() -> None:
    patched, changelog = apply_pipeline_ops(
        _mini_pipeline(),
        [
            {
                "op": "add_condition",
                "binding_id": "screen_1",
                "condition": {"op": "gte", "left": "close", "right": 10, "right_kind": "lit"},
                "annotation": {"rationale": "probe sparse; require price floor"},
            }
        ],
    )
    conds = patched["stages"][0]["filters"][0]["conditions"]
    assert len(conds) == 2
    assert conds[1]["annotation"]["rationale"].startswith("probe sparse")
    assert changelog[0]["op"] == "add_condition"
    spec, h = compile_and_hash(patched)
    assert spec["Kind"] == "VeraLabV1"
    assert len(h) == 64


def test_remove_condition_changelog() -> None:
    patched, changelog = apply_pipeline_ops(
        _mini_pipeline(),
        [
            {
                "op": "remove_condition",
                "binding_id": "screen_1",
                "condition_id": "c-rs",
                "annotation": {"rationale": "saturated hit_rate"},
            }
        ],
    )
    conds = patched["stages"][0]["filters"][0]["conditions"]
    assert conds == []
    assert changelog[0]["action"] == "removed"
    docs = patched["stages"][0]["documentation"]
    assert docs["filter_changelog"][0]["id"] == "c-rs"


def test_pipeline_ops_endpoint_dry_run(monkeypatch) -> None:
    from unittest.mock import patch

    from django.test import Client

    existing = {
        "ir_id": "spec-agent-loop-fixture",
        "title": "Fixture",
        "notes": "",
        "is_template": False,
        "ir_content_hash": "a" * 64,
        "pipeline_document": _mini_pipeline(),
    }

    c = Client()
    with patch("api.views.get_spec_by_ir_id", return_value=existing):
        with patch("api.views.get_ch_client", return_value=object()):
            resp = c.post(
                "/api/backtests/specs/spec-agent-loop-fixture/pipeline-ops",
                data={
                    "dry_run": True,
                    "expected_hash": "a" * 64,
                    "ops": [
                        {
                            "op": "add_condition",
                            "binding_id": "screen_1",
                            "condition": {
                                "op": "gte",
                                "left": "close",
                                "right": 5,
                                "right_kind": "lit",
                            },
                            "annotation": {"rationale": "dry run add"},
                        }
                    ],
                },
                content_type="application/json",
            )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["dry_run"] is True
    assert body["changelog"][0]["op"] == "add_condition"
    assert "saved" not in body
    assert body["pipeline_document"]["stages"][0]["filters"][0]["conditions"]


def test_pipeline_ops_conflict_409() -> None:
    from unittest.mock import patch

    from django.test import Client

    existing = {
        "ir_id": "spec-agent-loop-fixture",
        "title": "Fixture",
        "is_template": False,
        "ir_content_hash": "b" * 64,
        "pipeline_document": _mini_pipeline(),
    }
    c = Client()
    with patch("api.views.get_spec_by_ir_id", return_value=existing):
        with patch("api.views.get_ch_client", return_value=object()):
            resp = c.post(
                "/api/backtests/specs/spec-agent-loop-fixture/pipeline-ops",
                data={
                    "dry_run": True,
                    "expected_hash": "a" * 64,
                    "ops": [
                        {
                            "op": "remove_condition",
                            "binding_id": "screen_1",
                            "condition_id": "c-rs",
                            "annotation": {"rationale": "x"},
                        }
                    ],
                },
                content_type="application/json",
            )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


def test_pipeline_ops_allows_is_template_tag() -> None:
    """Template tag is editable in place (not fork-only)."""
    from unittest.mock import patch

    from django.test import Client

    existing = {
        "ir_id": "tmpl-editable-fixture",
        "title": "Tagged Template",
        "is_template": True,
        "ir_content_hash": "c" * 64,
        "pipeline_document": _mini_pipeline(),
    }
    c = Client()
    with patch("api.views.get_spec_by_ir_id", return_value=existing):
        with patch("api.views.get_ch_client", return_value=object()):
            resp = c.post(
                "/api/backtests/specs/tmpl-editable-fixture/pipeline-ops",
                data={
                    "dry_run": True,
                    "expected_hash": "c" * 64,
                    "ops": [
                        {
                            "op": "add_condition",
                            "binding_id": "screen_1",
                            "condition": {
                                "op": "gte",
                                "left": "close",
                                "right": 5,
                                "right_kind": "lit",
                            },
                            "annotation": {"rationale": "template patch ok"},
                        }
                    ],
                },
                content_type="application/json",
            )
    assert resp.status_code == 200, resp.content


def test_pipeline_ops_catalog_prefix_fork_only() -> None:
    from unittest.mock import patch

    from django.test import Client

    existing = {
        "ir_id": "catalog:minervini_sepa",
        "title": "Catalog",
        "is_template": True,
        "ir_content_hash": "d" * 64,
        "pipeline_document": _mini_pipeline(),
    }
    c = Client()
    with patch("api.views.get_spec_by_ir_id", return_value=existing):
        with patch("api.views.get_ch_client", return_value=object()):
            resp = c.post(
                "/api/backtests/specs/catalog:minervini_sepa/pipeline-ops",
                data={
                    "dry_run": True,
                    "ops": [
                        {
                            "op": "add_condition",
                            "binding_id": "screen_1",
                            "condition": {
                                "op": "gte",
                                "left": "close",
                                "right": 5,
                                "right_kind": "lit",
                            },
                            "annotation": {"rationale": "should fail"},
                        }
                    ],
                },
                content_type="application/json",
            )
    assert resp.status_code == 400
    assert "fork-only" in resp.json()["detail"]
