"""Save-time PCM-ladder materialization (C-FW-RULES Phase 2 spec-truth contract).

``screens/pcm_rules`` bridges to ``vera_lab.ir.pcm_ladder`` — the single
source of truth for the generated RiskBudgeted allocation table. When the
VeraTradingLab sibling tree is absent the helpers must degrade to no-ops
rather than fail (runtime regenerates the identical table internally).
"""

from __future__ import annotations

import pytest

from screens.pcm_rules import (
    generate_pcm_ladder,
    generate_pcm_size_expr,
    hydrate_pcm_rule_descriptions,
    materialize_pcm_rules,
    pcm_bindings_catalog,
    seed_pipeline_pcm_rules,
)

_LADDER = generate_pcm_ladder()
requires_vera_lab = pytest.mark.skipif(
    _LADDER is None, reason="vera_lab not importable from this environment"
)


def _spec(rules=None, size_expr=None, params=None):
    p = dict(params or {})
    if rules is not None:
        p["rules"] = rules
    if size_expr is not None:
        p["size_expr"] = size_expr
    return {
        "Framework": {
            "PortfolioConstruction": {
                "Type": "RiskBudgetedPortfolioConstructionModel",
                "Parameters": p,
            }
        }
    }


@requires_vera_lab
def test_generate_default_ladder_shape():
    names = [r["name"] for r in _LADDER]
    assert "new_entry" in names
    assert all(isinstance(r.get("then"), list) and r["then"] for r in _LADDER)
    # PCM vocabulary only — no risk-slot actions leak into the allocation table.
    risk_only = {"exit", "trim", "ratchet_stop", "cap_weight"}
    for r in _LADDER:
        assert {a["type"] for a in r["then"]}.isdisjoint(risk_only)


@requires_vera_lab
def test_materialize_injects_rules_and_size_expr():
    spec = _spec(params={"max_position_weight": 0.20})
    assert materialize_pcm_rules(spec) is True
    params = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    rules = params["rules"]
    assert {r["name"] for r in rules} >= {"new_entry", "down_flatten"}
    assert params["size_expr"]["type"] in {"min", "cond", "formula"}
    # Magnitudes bake as literals — the materialized AST is the whole policy.
    assert "0.2" in str(params["size_expr"]) or "0.2" in str(rules)


@requires_vera_lab
def test_materialize_preserves_authored_rules():
    authored = [{"name": "mine", "priority": 0,
                 "when": {"type": "all", "items": []},
                 "then": [{"type": "skip"}]}]
    spec = _spec(rules=authored)
    # Authored rules are never clobbered; size_expr seeds independently.
    assert materialize_pcm_rules(spec) is True
    params = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert params["rules"] == authored
    assert params["size_expr"] is not None


@requires_vera_lab
def test_materialize_preserves_authored_size_expr():
    authored_expr = {"type": "lit", "value": 0.05}
    spec = _spec(size_expr=authored_expr)
    assert materialize_pcm_rules(spec) is True  # rules still seed
    params = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert params["size_expr"] == authored_expr
    assert params["rules"]


def test_materialize_noop_for_other_pcm_types():
    spec = {"Framework": {"PortfolioConstruction": {
        "Type": "EqualWeightingPortfolioConstructionModel", "Parameters": {}}}}
    assert materialize_pcm_rules(spec) is False
    assert spec["Framework"]["PortfolioConstruction"]["Parameters"] == {}


def test_seed_pipeline_pcm_rules_mirrors_spec():
    rule = {"name": "r1", "priority": 0,
            "when": {"type": "all", "items": []},
            "then": [{"type": "skip"}]}
    spec = _spec(rules=[rule], size_expr={"type": "lit", "value": 0.1})
    doc = {"sizing": {"policy": "risk_budgeted"}}
    assert seed_pipeline_pcm_rules(spec, doc) is True
    assert doc["sizing"]["rules"][0]["name"] == "r1"
    assert doc["sizing"]["size_expr"] == {"type": "lit", "value": 0.1}


def test_seed_pipeline_pcm_rules_never_clobbers_authored():
    spec = _spec(rules=[{"name": "spec_rule"}])
    doc = {"sizing": {"rules": [{"name": "authored"}]}}
    assert seed_pipeline_pcm_rules(spec, doc) is False
    assert doc["sizing"]["rules"] == [{"name": "authored"}]


def test_seed_pipeline_pcm_rules_noop_without_spec_rules():
    doc = {"sizing": {"policy": "risk_budgeted"}}
    assert seed_pipeline_pcm_rules(_spec(), doc) is False
    assert "rules" not in doc["sizing"]


@requires_vera_lab
def test_hydrate_pcm_rule_descriptions_fills_canonical_rules():
    spec = _spec()
    assert materialize_pcm_rules(spec) is True
    rules = spec["Framework"]["PortfolioConstruction"]["Parameters"]["rules"]
    for r in rules:
        r.pop("description", None)
    doc = {"sizing": {"rules": [dict(r) for r in rules]}}
    filled = hydrate_pcm_rule_descriptions(spec, doc)
    assert filled == 2 * len(rules)
    assert all(r.get("description") for r in rules)
    assert all(r.get("description") for r in doc["sizing"]["rules"])


@requires_vera_lab
def test_hydrate_pcm_rule_descriptions_never_clobbers_authored():
    spec = _spec(rules=[{"name": "my_custom_rule",
                         "when": {"type": "all", "items": []},
                         "then": [{"type": "skip"}]},
                        {"name": "new_entry",
                         "description": "hand-written intent",
                         "when": {"type": "all", "items": []},
                         "then": [{"type": "enter"}]}])
    filled = hydrate_pcm_rule_descriptions(spec, None)
    assert filled == 0
    rules = spec["Framework"]["PortfolioConstruction"]["Parameters"]["rules"]
    assert rules[0].get("description") is None
    assert rules[1]["description"] == "hand-written intent"


def test_hydrate_pcm_rule_descriptions_noop_without_rules():
    assert hydrate_pcm_rule_descriptions(_spec(), None) == 0


@requires_vera_lab
def test_pcm_bindings_catalog_namespaces():
    catalog = pcm_bindings_catalog()
    assert catalog is not None
    assert {"cand", "hold", "acct", "pyr", "regime"} <= set(catalog)
    assert all(isinstance(v, list) and v for v in catalog.values())
    fields = {(b["ns"] if "ns" in b else ns, b["field"]) for ns, items in catalog.items() for b in items}
    assert ("cand", "is_new") in fields or any(b["field"] == "is_new" for b in catalog["cand"])


@requires_vera_lab
def test_materialize_injects_book_exprs():
    """Phase 3: scale/slots/order exprs materialize alongside rules+size_expr."""
    spec = _spec(params={"use_regime_scaling": True, "scaled_max_positions_floor": 3})
    assert materialize_pcm_rules(spec) is True
    params = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert "scale_expr" in params and "slots_expr" in params and "order_expr" in params
    # The floor + capacity knobs bake as literals inside slots_expr.
    assert "3.0" in str(params["slots_expr"]) or "3" in str(params["slots_expr"])
    assert params["order_expr"] == {"type": "ref", "ns": "cand", "field": "rank"}


@requires_vera_lab
def test_materialize_preserves_authored_book_exprs():
    authored = {"type": "lit", "value": 0.5}
    spec = _spec(params={"scale_expr": authored})
    materialize_pcm_rules(spec)
    params = spec["Framework"]["PortfolioConstruction"]["Parameters"]
    assert params["scale_expr"] == authored
    assert "slots_expr" in params  # siblings still seed independently


@requires_vera_lab
def test_displacement_cooldown_flows_into_ladder():
    """displacement_cooldown_days is a real knob now — it lands in the
    displace action args, not just a description string."""
    spec = _spec(params={"enable_displacement": True, "displacement_cooldown_days": 21})
    materialize_pcm_rules(spec)
    rules = spec["Framework"]["PortfolioConstruction"]["Parameters"]["rules"]
    displace = next(r for r in rules if r["name"] == "displace_weakest")
    assert displace["then"][0]["cooldown_days"] == 21


def test_seed_pipeline_pcm_rules_mirrors_book_exprs():
    spec = _spec(
        params={
            "rules": [{"name": "r", "when": {"type": "all", "items": []},
                       "then": [{"type": "skip"}]}],
            "scale_expr": {"type": "lit", "value": 1.0},
            "order_expr": {"type": "ref", "ns": "cand", "field": "rank"},
        }
    )
    doc = {"sizing": {"policy": "risk_budgeted"}}
    assert seed_pipeline_pcm_rules(spec, doc) is True
    assert doc["sizing"]["scale_expr"] == {"type": "lit", "value": 1.0}
    assert doc["sizing"]["order_expr"] == {"type": "ref", "ns": "cand", "field": "rank"}
    assert "slots_expr" not in doc["sizing"]  # absent on spec stays absent


def test_seed_pipeline_pcm_rules_never_clobbers_authored_book_expr():
    spec = _spec(params={"scale_expr": {"type": "lit", "value": 1.0}})
    doc = {"sizing": {"scale_expr": {"type": "lit", "value": 0.5}}}
    assert seed_pipeline_pcm_rules(spec, doc) is False
    assert doc["sizing"]["scale_expr"] == {"type": "lit", "value": 0.5}
