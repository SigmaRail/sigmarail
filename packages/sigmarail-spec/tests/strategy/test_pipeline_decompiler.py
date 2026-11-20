"""Unit tests for the pipeline decompiler round-trip (no ClickHouse)."""

from __future__ import annotations

from sigmarail_spec.strategy import (
    FilterCondition,
    FilterGroup,
    PipelineDocument,
    compile_pipeline,
    decompile_pipeline,
)
from sigmarail_spec.strategy.presets import get_preset
from sigmarail_spec.strategy.setup_recipes import compose_minervini_sepa_with_setup


def _round_trip(preset_id: str) -> tuple[PipelineDocument, PipelineDocument]:
    doc = get_preset(preset_id)
    spec = compile_pipeline(doc)
    return doc, decompile_pipeline(spec)


def _leaf_count(nodes: list) -> int:
    return sum(
        _leaf_count(item.conditions) if isinstance(item, FilterGroup) else 1
        for item in nodes
    )


def _named_groups(nodes: list) -> list[FilterGroup]:
    found: list[FilterGroup] = []
    for item in nodes:
        if not isinstance(item, FilterGroup):
            continue
        if item.name:
            found.append(item)
        found.extend(_named_groups(item.conditions))
    return found


def test_momentum_round_trip() -> None:
    original, decompiled = _round_trip("momentum")
    # Filter stage survived
    filter_stages = [s for s in decompiled.stages if s.mode.value == "filter"]
    assert filter_stages, "filter stage lost in round-trip"
    # Score stage survived with momentum factor
    score_stages = [s for s in decompiled.stages if s.mode.value == "score"]
    assert score_stages
    factor_names = {f.name for f in score_stages[0].factors}
    assert "momentum" in factor_names


def test_value_momentum_round_trip() -> None:
    original, decompiled = _round_trip("value_momentum")
    score_stages = [s for s in decompiled.stages if s.mode.value == "score"]
    assert score_stages
    factor_names = {f.name for f in score_stages[0].factors}
    assert {"momentum", "value", "roe", "trend_1y"} <= factor_names


def test_minervini_round_trip_stages() -> None:
    original, decompiled = _round_trip("minervini_sepa")
    modes = {s.mode.value for s in decompiled.stages}
    names = {g.name for g in _named_groups(decompiled.universe.screen)}
    assert "membership" in names
    assert "code_33" not in names
    leaves = [
        n
        for n in decompiled.universe.screen
        for n in (n.conditions if isinstance(n, FilterGroup) else [n])
    ]
    assert any(
        isinstance(n, FilterCondition)
        and n.op == "neq"
        and n.left == "industry"
        and n.right == "Biotechnology"
        for n in leaves
    )
    assert "score" in modes
    assert "signal" in modes
    assert "pyramid" in modes
    assert "exit" in modes
    assert decompiled.hedge is None
    pyr = next(s for s in decompiled.stages if s.mode.value == "pyramid")
    assert pyr.add_trigger_pct == 0.08
    assert decompiled.execution.fill_session == "moo"
    assert decompiled.sizing.policy.value == "risk_budgeted"
    assert decompiled.sizing.honor_insight_confidence is True


def test_minervini_keeps_blend_rank_as_gate_false() -> None:
    original, decompiled = _round_trip("minervini_sepa")
    blend = [s for s in decompiled.stages if s.mode.value == "score" and not s.as_gate]
    assert blend, "as_gate=false VCP Ranking must survive decompile"
    factor_names = {f.name for s in blend for f in s.factors}
    assert factor_names & {"momentum", "rs_rating", "technical"}


def test_round_trip_recompiles() -> None:
    """Decompiled pipeline must compile back to a valid spec without error."""
    original = get_preset("minervini_sepa")
    spec1 = compile_pipeline(original)
    decompiled = decompile_pipeline(spec1)
    spec2 = compile_pipeline(decompiled)
    assert spec2["Kind"] == "VeraLabV1"
    assert spec2["Framework"]["Alpha"]["Type"] == "VeraPyramidAlphaModel"


def test_decompile_restores_stage_documentation() -> None:
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

    decompiled = decompile_pipeline(compile_pipeline(doc))
    filter_stage = next(stage for stage in decompiled.stages if stage.mode.value == "filter")
    score_stage = next(stage for stage in decompiled.stages if stage.mode.value == "score")

    assert filter_stage.documentation.purpose == "Keep liquid candidates"
    assert filter_stage.documentation.inputs == ["close", "volume"]
    assert filter_stage.documentation.expression == "close >= 10"
    assert filter_stage.documentation.confirmation == "At least one candidate remains"
    assert filter_stage.documentation.effect == "Narrows the universe"
    assert filter_stage.documentation.variables == {"min_price": "10"}
    assert filter_stage.documentation.notes == "Applied before ranking"
    assert score_stage.documentation.purpose == "Rank by momentum"
    assert score_stage.documentation.variables == {"factor": "momentum"}

    recompilation = decompile_pipeline(compile_pipeline(decompiled))
    recompilation_filter = next(
        stage for stage in recompilation.stages if stage.mode.value == "filter"
    )
    recompilation_score = next(
        stage for stage in recompilation.stages if stage.mode.value == "score"
    )
    assert recompilation_filter.documentation.purpose == "Keep liquid candidates"
    assert recompilation_score.documentation.purpose == "Rank by momentum"


def test_ssot_pipeline_round_trip() -> None:
    """Alpha.Parameters.stages restores authored Alpha-card stages (not VeraBase.Pipeline)."""
    doc = get_preset("minervini_sepa")
    spec = compile_pipeline(doc)
    assert "Pipeline" not in spec["VeraBase"] or spec["VeraBase"].get("Pipeline") is None
    alpha_stages = spec["Framework"]["Alpha"]["Parameters"]["stages"]
    assert len(alpha_stages) >= 3
    decompiled = decompile_pipeline(spec)
    names = {g.name for g in _named_groups(decompiled.universe.screen)}
    assert "membership" in names
    assert "code_33" not in names
    signal_stages = [s for s in decompiled.stages if s.mode.value == "signal"]
    assert any(s.name == "Setup Group" for s in signal_stages)


def test_legacy_decompile_preserves_filter_conditions() -> None:
    # The plain preset carries no setup filters; setup recipes do.
    doc = compose_minervini_sepa_with_setup()
    spec = compile_pipeline(doc)
    # Exercise legacy AST decompilation (no Alpha stages, no Pipeline)
    spec["Framework"]["Alpha"]["Parameters"].pop("stages", None)
    spec["VeraBase"].pop("Pipeline", None)
    decompiled = decompile_pipeline(spec)
    root = next(g for g in _named_groups(decompiled.universe.screen) if g.name == "membership")
    assert _leaf_count(root.conditions) >= 3
    signal_stage = next(s for s in decompiled.stages if s.mode.value == "signal")
    assert signal_stage.filters
    setup_root = signal_stage.filters[0]
    assert isinstance(setup_root, FilterGroup)
    assert _leaf_count(setup_root.conditions) >= 6


def test_legacy_decompile_preserves_nested_groups_and_formulas() -> None:
    doc = compose_minervini_sepa_with_setup()
    spec = compile_pipeline(doc)
    spec["Framework"]["Alpha"]["Parameters"].pop("stages", None)
    spec["VeraBase"].pop("Pipeline", None)
    decompiled = decompile_pipeline(spec)
    root = next(g for g in _named_groups(decompiled.universe.screen) if g.name == "membership")
    assert root.logic == "and"

    signal_stage = next(s for s in decompiled.stages if s.mode.value == "signal")
    setup_group = signal_stage.filters[0]
    assert isinstance(setup_group, FilterGroup)
    assert setup_group.logic == "or"
    assert _leaf_count(setup_group.conditions) == 6

    formula_conditions = []
    def collect(nodes: list) -> None:
        for item in nodes:
            if isinstance(item, FilterGroup):
                collect(item.conditions)
            elif item.right_kind == "formula":
                formula_conditions.append(item)

    collect(root.conditions)
    collect(setup_group.conditions)
    assert len(formula_conditions) >= 3
    assert all(isinstance(item.right, dict) for item in formula_conditions)
