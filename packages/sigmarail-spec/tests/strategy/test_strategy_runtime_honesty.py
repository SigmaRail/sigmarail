"""Honesty tests for query-AST universe ownership and runtime framework slots.

These encode Done when for slice strategy-runtime-honesty. They must fail on the
pre-honesty compiler (membership in Universe.where, regime-gate blob, missing
DataSources) and pass after the compiler/IR cleanup.
"""

from __future__ import annotations

import json

import pytest

from sigmarail_spec.strategy import PipelineDocument, compile_pipeline
from sigmarail_spec.strategy.presets import get_preset


def _where_mentions(where: dict | None, needle: str) -> bool:
    if not where:
        return False
    blob = json.dumps(where)
    return needle in blob


def test_sepa_has_no_hygiene_where() -> None:
    """Screen tree is the query WHERE; no universe model slot is compiled."""
    spec = compile_pipeline(get_preset("minervini_sepa"))
    assert spec["Framework"]["UniverseSelection"]["Type"] == "SigmaRailClickHouseUniverseSelection"
    where = spec["Framework"]["UniverseSelection"]["Parameters"]["query"]["where"]
    assert where["type"] == "all"
    assert where.get("name") == "hygiene"
    items = where.get("items") or []
    assert any(
        item.get("type") == "any"
        for item in items
        if isinstance(item, dict)
    )
    blob = json.dumps(where)
    assert "avg_vol_50d" in blob
    assert "exchange" in blob
    assert "NYSE" in blob
    assert "NASDAQ" in blob
    assert "industry" in blob
    assert "Biotechnology" in blob
    assert "code_33" not in blob
    assert not _where_mentions(where, "vcp_atr_compression")


def test_sepa_universe_owns_membership_and_pushdown_keeps_smas() -> None:
    """The query AST owns membership and its predicate; alpha owns setup conditions."""
    from sigmarail_spec.strategy.setup_recipes import compose_minervini_sepa_with_setup

    spec = compile_pipeline(compose_minervini_sepa_with_setup())
    alpha = spec["Framework"]["Alpha"]["Parameters"]
    membership = spec["Framework"]["UniverseSelection"]["Parameters"]["query"]["where"]
    assert membership is not None
    assert "membership" not in alpha
    assert "named_groups" not in alpha
    assert _where_mentions(membership, "sma50d")
    assert not _where_mentions(membership, "sma200d_rising_30d")
    assert not _where_mentions(membership, "minervini_tt")

    pushdown = spec["Framework"]["UniverseSelection"]["Parameters"]["query"]["where"]
    assert _where_mentions(pushdown, "sma50d")
    assert not _where_mentions(pushdown, "vcp_atr_compression")
    assert not _where_mentions(pushdown, "high_90d")
    setup = alpha.get("setup_where")
    assert setup is not None
    assert _where_mentions(setup, "vcp_atr_compression") or _where_mentions(setup, "high_90d")
    assert alpha.get("gates")


def test_compiled_spec_has_datasources_no_regime_gate_blob() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    algo = spec.get("AlgorithmParameters") or {}
    assert "regime-gate" not in algo
    sources = spec["SigmaRail"].get("DataSources") or []
    names = {s.get("name") for s in sources}
    assert "equity" in names
    assert "regime" in names
    assert "bars" in names
    regime = next(s for s in sources if s["name"] == "regime")
    assert regime.get("Type") == "SigmaRailMarketRegimeSignalsDaily"
    assert "score" in regime or regime.get("table")


def test_compiled_spec_does_not_persist_full_pipeline_as_strategy_ssot() -> None:
    """SigmaRail.Pipeline must not re-own the whole strategy (exit/sizing/regime)."""
    spec = compile_pipeline(get_preset("minervini_sepa"))
    pipeline = spec["SigmaRail"].get("Pipeline")
    assert pipeline is None or pipeline.get("deprecated") is True
    alpha = spec["Framework"]["Alpha"]["Parameters"]
    assert "stages" in alpha


def test_risk_parameters_include_all_exit_tranches() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    risk = spec["Framework"]["RiskManagement"]
    assert risk["Type"] == "SigmaRailRiskManagementModel"
    progressive = next(rule for rule in risk["Parameters"]["rules"] if rule["kind"] == "progressive")
    tranches = progressive["parameters"].get("tranches")
    assert isinstance(tranches, list)
    assert len(tranches) >= 3
    assert tranches[0]["trigger_r"] == 2.5
    assert tranches[1]["trigger_r"] == 4.5
    assert tranches[2]["trigger_r"] == 8.0


def test_hedge_use_without_sigmarail_hedge_model_fails_compile() -> None:
    doc = get_preset("minervini_sepa")
    raw = doc.model_dump(mode="json")
    raw["risk"]["regime_gate"] = {
        **(raw["risk"].get("regime_gate") or {}),
        "source": "regime_signals_canonical",
        "uses": ["hedge"],
    }
    bad = PipelineDocument.model_validate(raw)
    with pytest.raises(ValueError, match="hedge"):
        compile_pipeline(bad)


def test_momentum_pushdown_still_filters_in_universe_facet() -> None:
    """Non-SEPA: membership still pushdown into SigmaRail.Universe.where for CH."""
    spec = compile_pipeline(get_preset("momentum"))
    pushdown = spec["Framework"]["UniverseSelection"]["Parameters"]["query"]["where"]
    assert _where_mentions(pushdown, "rs_rating") or _where_mentions(pushdown, "close")
    membership = spec["Framework"]["UniverseSelection"]["Parameters"]["query"]["where"]
    assert membership is not None
    assert spec["Framework"]["UniverseSelection"]["Type"] == "SigmaRailClickHouseUniverseSelection"


def test_champion_pcm_has_live_knobs_no_lean_pcm_leftovers() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    pcm = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert pcm.get("honor_insight_confidence") is True
    assert pcm.get("allow_adds_on_invested") is True
    assert abs(float(pcm["default_stop_loss_pct"]) - 0.05) < 1e-9
    assert pcm.get("use_regime_scaling") is True
    assert "hold_policy" not in pcm
    assert "exit_when_no_bars" not in pcm
    assert "max_total_exposure" not in pcm
    assert "skip_pyramid_adds" in (pcm.get("uses") or [])
    assert "phases" in pcm
    assert abs(float(pcm["add_trigger_pct"]) - 0.08) < 1e-9


def test_champion_execution_fill_session_moo() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    exe = spec["Framework"]["Execution"]
    assert exe["Type"] == "SigmaRailScreenerExecutionModel"
    assert exe["Parameters"].get("fill_session") == "moo"


def test_champion_pcm_has_add_trigger_no_pyramid_circuit() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    alpha = spec["Framework"]["Alpha"]["Parameters"]
    pcm = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert spec["Framework"]["Alpha"]["Type"] == "SigmaRailScreenerAlphaModel"
    assert "add_trigger_pct" not in alpha or alpha.get("add_trigger_pct") is None
    assert abs(float(pcm["add_trigger_pct"]) - 0.08) < 1e-9
    assert "circuit_drawdown_threshold" not in alpha


def test_champion_has_no_silent_sh_hedge() -> None:
    preset = get_preset("minervini_sepa")
    assert preset.hedge is None
    assert preset.risk.max_sector_exposure is None
    spec = compile_pipeline(preset)
    risk = spec["Framework"]["RiskManagement"]
    assert risk["Type"] == "SigmaRailRiskManagementModel"
    blob = json.dumps(risk)
    assert "SigmaRailHedgeModel" not in blob
    assert '"SH"' not in blob


def test_champion_risk_stamps_exit_knobs() -> None:
    spec = compile_pipeline(get_preset("minervini_sepa"))
    risk = spec["Framework"]["RiskManagement"]
    assert risk["Type"] == "SigmaRailRiskManagementModel"
    params = next(rule["parameters"] for rule in risk["Parameters"]["rules"] if rule["kind"] == "progressive")
    assert params.get("atr_stop_multiplier") == 2.0
    assert params.get("use_atr_stops") is True
    assert params.get("max_holding_days") == 63
    assert params.get("max_single_weight") == 0.20
    assert params.get("breakeven_r_trigger") == 1.5
    assert params.get("breakeven_time_stop_days") == 10


def test_champion_decompile_round_trips_honesty_knobs() -> None:
    from sigmarail_spec.strategy.decompiler import decompile_pipeline

    spec = compile_pipeline(get_preset("minervini_sepa"))
    back = decompile_pipeline(spec)
    assert back.execution.fill_session == "moo"
    assert back.sizing.policy.value == "risk_budgeted"
    assert back.sizing.honor_insight_confidence is True
    assert back.sizing.use_regime_scaling is True
    pyr = next(s for s in back.stages if s.mode.value == "pyramid")
    assert pyr.add_trigger_pct == 0.08
    ex = next(s for s in back.stages if s.mode.value == "exit")
    assert ex.atr_stop_multiplier == 2.0
    again = compile_pipeline(back)
    assert again["Framework"]["Execution"]["Parameters"]["fill_session"] == "moo"
    assert again["Framework"]["PortfolioConstruction"]["Parameters"].get(
        "use_regime_scaling"
    ) is True
