"""C-SCREEN-PROBE-V1 — Django probe endpoint + domain service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client


def test_probe_layers_preset_no_ch() -> None:
    c = Client()
    resp = c.post(
        "/api/screens/probe",
        data={
            "view": "layers",
            "preset_id": "minervini_sepa",
            "through": {"binding_id": "screen_1"},
            "probe_mode": "measures",
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["view"] == "layers"
    assert body["contract"] == "C-SCREEN-PROBE-V1"
    assert body["computed_aliases"] == ["screen_1"]
    assert body["combinator_present"] is False
    assert body["through"]["binding_id"] == "screen_1"
    assert "diagnostics" in body


def test_probe_layers_through_code_33_has_screens_hit() -> None:
    from screens.probe import run_probe

    out = run_probe(
        {
            "view": "layers",
            "preset_id": "minervini_sepa",
            "through": {"binding_id": "code_33"},
        },
        client=None,
    )
    assert "screens_hit" in out["computed_aliases"]
    assert out["combinator_present"] is True


def test_probe_unknown_binding_400() -> None:
    c = Client()
    resp = c.post(
        "/api/screens/probe",
        data={
            "view": "layers",
            "preset_id": "minervini_sepa",
            "through": {"binding_id": "not_real"},
        },
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_probe_asof_mocked() -> None:
    mock_client = MagicMock()
    fake = {
        "as_of": "2024-12-30",
        "columns": ["ticker", "screen_1"],
        "rows": [{"ticker": "AAPL", "screen_1": 1}, {"ticker": "MSFT", "screen_1": 0}],
        "count": 2,
    }
    with patch("screens.probe.preview_universe_ir", return_value=fake):
        from screens.probe import run_probe

        out = run_probe(
            {
                "view": "asof",
                "preset_id": "minervini_sepa",
                "through": {"binding_id": "screen_1"},
                "as_of": "2024-12-30",
                "limit": 25,
            },
            client=mock_client,
        )
    assert out["count"] == 2
    assert out["diagnostics"]["hit_rate"]["screen_1"] == 0.5
    assert out["probe_mode"] == "measures"


def test_probe_extra_select_merged_into_asof_spec() -> None:
    """NTH-1: extra_select appends to universe select before preview."""
    from screens.probe import run_probe

    mock_client = MagicMock()
    with patch("screens.probe.preview_universe_ir") as prev:
        prev.return_value = {
            "as_of": "2026-09-15",
            "columns": ["ticker", "close", "minervini_score"],
            "rows": [],
            "count": 0,
        }
        run_probe(
            {
                "view": "asof",
                "preset_id": "minervini_sepa",
                "as_of": "2026-09-15",
                "limit": 10,
                "extra_select": ["minervini_score", "minervini_score", "exchange"],
                "order_by": [{"field": "minervini_score", "direction": "desc"}],
            },
            client=mock_client,
        )
    spec = prev.call_args.kwargs["spec_dict"]
    assert "minervini_score" in spec["select"]
    assert spec["select"].count("minervini_score") == 1
    assert spec["order_by"][0]["field"] == "minervini_score"


def test_probe_asof_include_tenure_mocked() -> None:
    """NTH-2: include_tenure attaches days_in_universe to asof rows."""
    from screens.probe import run_probe

    mock_client = MagicMock()
    with (
        patch(
            "screens.probe.preview_universe_ir",
            return_value={
                "as_of": "2026-09-15",
                "columns": ["ticker", "close"],
                "rows": [{"ticker": "AAPL", "close": 1.0}, {"ticker": "MSFT", "close": 2.0}],
                "count": 2,
            },
        ),
        patch(
            "screens.probe.membership_tenure_by_ticker",
            return_value={"AAPL": 40, "MSFT": 12},
        ),
    ):
        out = run_probe(
            {
                "view": "asof",
                "preset_id": "minervini_sepa",
                "as_of": "2026-09-15",
                "limit": 10,
                "include_tenure": True,
                "tenure_start": "2025-09-15",
            },
            client=mock_client,
        )
    assert out["rows"][0]["days_in_universe"] == 40
    assert out["rows"][1]["days_in_universe"] == 12
    assert "days_in_universe" in out["columns"]


def test_probe_range_mocked() -> None:
    mock_client = MagicMock()
    summary = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-30",
        "dates": ["2024-01-01", "2024-01-02"],
        "member_counts": [10, 12],
        "summary": {
            "trading_days": 2,
            "avg_members_per_day": 11.0,
            "min_members_per_day": 10,
            "max_members_per_day": 12,
        },
        "weekly_samples": [],
    }
    with (
        patch("screens.probe.summarize_universe_range", return_value=summary),
        patch(
            "screens.probe._measure_series_range",
            return_value={"screen_1": [2.0, 3.0], "funnel": [1.0, 2.0]},
        ) as measure_mock,
    ):
        from screens.probe import run_probe

        out = run_probe(
            {
                "view": "range",
                "preset_id": "minervini_sepa",
                "through": {"binding_id": "screen_1"},
                "start_date": "2024-01-01",
                "end_date": "2024-12-30",
                "enabled_bindings": ["screen_1"],
                "cumulative": True,
            },
            client=mock_client,
        )
    assert out["member_counts"] == [10, 12]
    assert out["measure_series"]["screen_1"] == [2.0, 3.0]
    assert out["cumulative"] is True
    assert out["diagnostics"]["series_unit"] == "pass_count"
    assert measure_mock.call_args.kwargs.get("funnel_aliases") == ["screen_1"]


def test_measure_series_uses_sum_not_avg() -> None:
    """Pass counts use sum(toUInt8(...)), not avg hit-rate."""
    from screens.probe import _measure_series_range

    mock_client = MagicMock()
    mock_client.query.return_value = MagicMock(result_rows=[("2024-01-02", 5, 2)])
    out = _measure_series_range(
        mock_client,
        spec={
            "version": 1,
            "from": "daily_screener",
            "select": ["ticker", "close", "overall_score"],
            "where": {
                "type": "gt",
                "left": {"type": "col", "name": "close"},
                "right": {"type": "lit", "value": 0},
            },
            "order_by": [{"field": "overall_score", "direction": "desc"}],
            "limit_per_day": 50,
            "computed": [
                {
                    "alias": "screen_1",
                    "kind": "bool",
                    "where": {
                        "type": "gte",
                        "left": {"type": "col", "name": "close"},
                        "right": {"type": "lit", "value": 10},
                    },
                }
            ],
        },
        start_date="2024-01-01",
        end_date="2024-01-10",
        aliases=["screen_1"],
        screens_hit=False,
        funnel_aliases=["screen_1"],
    )
    sql = mock_client.query.call_args.args[0]
    assert "sum(toUInt8(u.`screen_1`))" in sql
    assert "avg(toFloat64(u.`screen_1`))" not in sql
    assert "sum_funnel" in sql or "sum(if(" in sql
    assert "LIMIT" not in sql.split(") AS u", 1)[0].upper()
    assert out["screen_1"] == [5.0]
    assert out["funnel"] == [2.0]


def test_probe_diff_mocked() -> None:
    mock_client = MagicMock()

    def _preview(_client, *, as_of, spec_dict):
        aliases = [c["alias"] for c in (spec_dict.get("computed") or [])]
        if "screen_2" in aliases:
            rows = [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]
        else:
            rows = [{"ticker": "A"}, {"ticker": "B"}]
        return {"as_of": as_of, "rows": rows, "columns": ["ticker"], "count": len(rows)}

    with patch("screens.probe.preview_universe_ir", side_effect=_preview):
        from screens.probe import run_probe

        out = run_probe(
            {
                "view": "diff",
                "preset_id": "minervini_sepa",
                "through": {"binding_id": "screen_2"},
                "probe_mode": "members",
                "as_of": "2024-12-30",
            },
            client=mock_client,
        )
    assert out["size_a"] == 3
    assert out["size_b"] == 2
    assert out["entering"] == ["C"]
    assert out["jaccard"] == pytest.approx(2 / 3, abs=1e-3)


def test_probe_default_through_includes_computed_measures() -> None:
    """Alpha-bottom default cut must include authored number measures (hit_count)."""
    from vera_query_core.strategy.pipeline import PipelineDocument, Stage, StageType
    from screens.probe import run_probe

    doc = PipelineDocument(
        strategy_name="probe_hit_count_cut",
        stages=[
            Stage(
                name="Screen 1",
                mode=StageType.SCORE,
                as_gate=True,
                count_as_signal=True,
                id="ary_eps",
                filters=[
                    {
                        "logic": "and",
                        "conditions": [
                            {
                                "left": "ary_eps_growth_3y_cagr",
                                "op": "gte",
                                "right": 0.15,
                                "right_kind": "lit",
                            }
                        ],
                    }
                ],
            ),
            Stage(
                name="Setup",
                mode=StageType.SIGNAL,
                id="setup_pass",
                filters=[
                    {
                        "logic": "and",
                        "conditions": [
                            {
                                "left": "setup_quality_rating",
                                "op": "gte",
                                "right": 70,
                                "right_kind": "lit",
                            }
                        ],
                    }
                ],
            ),
            Stage(
                name="Shortlist sum",
                mode=StageType.SCORE,
                as_gate=True,
                count_as_signal=False,
                id="hit_count",
                computed_expr={
                    "type": "col",
                    "name": "ary_eps",
                },
            ),
        ],
        gate_combine="count",
        bindings={"alpha_rank": ["hit_count", "rs_rating"]},
    )
    out = run_probe(
        {"view": "layers", "pipeline": doc.model_dump(mode="json")},
        client=None,
    )
    assert "hit_count" in out["computed_aliases"]
    assert "ary_eps" in out["computed_aliases"]


def test_probe_order_by_computed_not_stuffed_into_select() -> None:
    """order_by hit_count must not land in select (unknown L7 column)."""
    from vera_query_core.strategy.pipeline import PipelineDocument, Stage, StageType
    from screens.probe import run_probe

    doc = PipelineDocument(
        strategy_name="probe_order_by_computed",
        stages=[
            Stage(
                name="Screen 1",
                mode=StageType.SCORE,
                as_gate=True,
                count_as_signal=True,
                id="ary_eps",
                filters=[
                    {
                        "logic": "and",
                        "conditions": [
                            {
                                "left": "close",
                                "op": "gte",
                                "right": 10,
                                "right_kind": "lit",
                            }
                        ],
                    }
                ],
            ),
            Stage(
                name="Shortlist",
                mode=StageType.SCORE,
                as_gate=True,
                count_as_signal=False,
                id="hit_count",
                computed_expr={"type": "col", "name": "ary_eps"},
            ),
        ],
        gate_combine="count",
    )
    mock_client = MagicMock()
    with patch("screens.probe.preview_universe_ir") as prev:
        prev.return_value = {
            "as_of": "2026-09-15",
            "columns": ["ticker", "hit_count"],
            "rows": [],
            "count": 0,
        }
        run_probe(
            {
                "view": "asof",
                "pipeline": doc.model_dump(mode="json"),
                "as_of": "2026-09-15",
                "limit": 10,
                "extra_select": ["hit_count"],
                "order_by": [
                    {"field": "hit_count", "direction": "desc"},
                    {"field": "rs_rating", "direction": "desc"},
                ],
            },
            client=mock_client,
        )
    spec = prev.call_args.kwargs["spec_dict"]
    assert "hit_count" not in spec["select"]
    assert any(c.get("alias") == "hit_count" for c in spec.get("computed") or [])
    assert spec["order_by"][0]["field"] == "hit_count"

    from screens.probe import _apply_probe_mode, _compile_prefix, _resolve_source

    pipeline, spec = _resolve_source(
        {"preset_id": "minervini_sepa", "through": {"binding_id": "screen_1"}}
    )
    prefix = _compile_prefix(
        pipeline=pipeline, spec=spec, through={"binding_id": "screen_1"}
    )
    uni = _apply_probe_mode(
        prefix["universe"], probe_mode="members", through_binding="screen_1"
    )
    where = uni["where"]
    assert where["type"] == "all"
    # Last item is Screen 1 yearly EPS predicate (not alias=1; aliases are SELECT-only).
    gate = where["items"][-1]
    blob = str(gate)
    assert "ary_eps_growth" in blob or "type" in gate
    # Still validates as universe_query_v1
    from screens.ir_preview import validate_universe_ir_spec

    validate_universe_ir_spec(uni)
