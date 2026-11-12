"""Save-time risk-ladder materialization (C-FW-RULES spec-truth contract).

``screens/risk_rules`` bridges to ``vera_lab.ir.risk_ladder`` — the single
source of truth for the generated SwingProgressive ladder. When the
VeraTradingLab sibling tree is absent the helpers must degrade to no-ops
rather than fail (runtime regenerates the identical table internally).
"""

from __future__ import annotations

import pytest

from screens.risk_rules import (
    generate_swing_risk_ladder,
    hydrate_rule_descriptions,
    materialize_swing_risk_rules,
    seed_pipeline_risk_rules,
)

_LADDER = generate_swing_risk_ladder()
requires_vera_lab = pytest.mark.skipif(
    _LADDER is None, reason="vera_lab not importable from this environment"
)


def _spec(rules=None, params=None):
    p = dict(params or {})
    if rules is not None:
        p["rules"] = rules
    return {
        "Framework": {
            "RiskManagement": {
                "Type": "SwingProgressiveRiskManagementModel",
                "Parameters": p,
            }
        }
    }


@requires_vera_lab
def test_generate_default_ladder_shape():
    names = [r["name"] for r in _LADDER]
    assert "hard_stop" in names and "tranche1" in names and "breakeven_trigger" in names
    assert all(isinstance(r.get("then"), list) and r["then"] for r in _LADDER)


@requires_vera_lab
def test_materialize_injects_rules_into_knobs_only_spec():
    spec = _spec(params={"take_profit_r": 3.0, "trailing_stop_pct": 0.12})
    assert materialize_swing_risk_rules(spec) is True
    rules = spec["Framework"]["RiskManagement"]["Parameters"]["rules"]
    assert len(rules) >= 8
    # Concentration capping moved to the PCM drift cap — the ladder is
    # position-lifecycle only (stops, trails, tranches, time stops).
    assert "max_weight_cap" not in {r["name"] for r in rules}
    t1 = next(r for r in rules if r["name"] == "tranche1")
    assert "3.0" in str(t1["when"])  # spec's own knob embedded in the literal


@requires_vera_lab
def test_materialize_preserves_authored_rules():
    authored = [{"name": "mine", "priority": 0,
                 "when": {"type": "all", "items": []},
                 "then": [{"type": "exit", "fraction": 1.0}]}]
    spec = _spec(rules=authored, params={"take_profit_r": 9.9})
    # Authored rules are never clobbered; init_stop seeds independently —
    # authored rules say nothing about the position-init stop, so the default
    # AST still materializes and the function reports the write.
    assert materialize_swing_risk_rules(spec) is True
    params = spec["Framework"]["RiskManagement"]["Parameters"]
    assert params["rules"] == authored
    assert params["init_stop"]["type"] == "cond"


@requires_vera_lab
def test_materialize_preserves_authored_init_stop():
    authored_stop = {
        "type": "formula",
        "op": "*",
        "args": [
            {"type": "col", "name": "__position.entry"},
            {"type": "lit", "value": 0.9},
        ],
    }
    spec = _spec(params={"init_stop": authored_stop})
    assert materialize_swing_risk_rules(spec) is True  # rules still seed
    params = spec["Framework"]["RiskManagement"]["Parameters"]
    assert params["init_stop"] == authored_stop
    assert len(params["rules"]) >= 8


@requires_vera_lab
def test_materialize_init_stop_reflects_knobs():
    spec = _spec(params={"use_atr_stops": False, "max_stop_loss_pct": 0.08})
    assert materialize_swing_risk_rules(spec) is True
    init_stop = spec["Framework"]["RiskManagement"]["Parameters"]["init_stop"]
    # use_atr_stops=False bakes the choice at generation: plain pct formula,
    # no dead conditional in the stored AST.
    assert init_stop["type"] == "formula"
    assert "0.08" in str(init_stop)


def test_materialize_noop_for_other_risk_types():
    spec = {"Framework": {"RiskManagement": {"Type": "NullRiskManagementModel",
                                             "Parameters": {}}}}
    assert materialize_swing_risk_rules(spec) is False
    assert spec["Framework"]["RiskManagement"]["Parameters"] == {}


def test_seed_pipeline_risk_rules_mirrors_spec():
    spec = _spec(rules=[{"name": "r1", "priority": 0,
                         "when": {"type": "all", "items": []},
                         "then": [{"type": "exit", "fraction": 1.0}]}])
    doc = {"stages": [{"mode": "exit", "name": "exits"}]}
    assert seed_pipeline_risk_rules(spec, doc) is True
    assert doc["stages"][0]["rules"][0]["name"] == "r1"


def test_seed_pipeline_risk_rules_never_clobbers_authored():
    spec = _spec(rules=[{"name": "spec_rule"}])
    doc = {"stages": [{"mode": "exit", "rules": [{"name": "authored"}]}]}
    assert seed_pipeline_risk_rules(spec, doc) is False
    assert doc["stages"][0]["rules"] == [{"name": "authored"}]


def test_seed_pipeline_risk_rules_noop_without_spec_rules():
    doc = {"stages": [{"mode": "exit", "name": "exits"}]}
    assert seed_pipeline_risk_rules(_spec(), doc) is False
    assert "rules" not in doc["stages"][0]


@requires_vera_lab
def test_hydrate_rule_descriptions_fills_canonical_rules():
    spec = _spec()
    assert materialize_swing_risk_rules(spec) is True
    rules = spec["Framework"]["RiskManagement"]["Parameters"]["rules"]
    for r in rules:
        r.pop("description", None)
    doc = {"stages": [{"mode": "exit", "rules": [dict(r) for r in rules]}]}
    filled = hydrate_rule_descriptions(spec, doc)
    assert filled == 2 * len(rules)
    assert all(r.get("description") for r in rules)
    assert all(r.get("description") for r in doc["stages"][0]["rules"])


@requires_vera_lab
def test_hydrate_rule_descriptions_never_clobbers_authored():
    spec = _spec(rules=[{"name": "my_custom_rule",
                         "when": {"type": "all", "items": []},
                         "then": [{"type": "exit", "fraction": 1.0}]},
                        {"name": "chandelier_trail",
                         "description": "hand-written intent",
                         "when": {"type": "all", "items": []},
                         "then": [{"type": "exit", "fraction": 1.0}]}])
    filled = hydrate_rule_descriptions(spec, None)
    assert filled == 0
    rules = spec["Framework"]["RiskManagement"]["Parameters"]["rules"]
    assert rules[0].get("description") is None
    assert rules[1]["description"] == "hand-written intent"


def test_hydrate_rule_descriptions_noop_without_rules():
    assert hydrate_rule_descriptions(_spec(), None) == 0
