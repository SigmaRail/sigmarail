"""Spec lint (C-VERA-SPEC-LINT).

Each "regression guard" test below corresponds to a real false positive or a real miss
found while calibrating against the 12 `champion_vcp_reversal*` specs. They are the point
of the file: a linter that cries wolf is worse than none, and one that cannot see an
unknown node type is not a linter.

Hermetic on purpose — ``column_map`` and ``runtime_kwargs`` are injected, so these tests
need no ClickHouse and no ``vera_lab`` import.
"""

from __future__ import annotations

import pytest

from sigmarail_spec import strategy_lint as spec_lint

COLUMNS = {
    "close": ("close", "close"),
    "closeadj": ("closeadj", "closeadj"),
    "rs_rating": ("rs_rating", "rs_rating"),
    "high_52w": ("high_52w", "high_52w"),
    "atr_14_pct": ("atr_14_pct", "atr_14_pct"),
    "vcp_tightness_5d_90d": ("vcp_tightness_5d_90d", "vcp_tightness_5d_90d"),
}

KWARGS = {
    "VeraPyramidAlphaModel": {
        "setup_where",
        "eligibility_expr",
        "weight_expr",
        "gates",
        "row_rank",
    },
    "SwingProgressiveRiskManagementModel": {
        "trailing_arm_r",
        "trailing_stop_pct",
        "risk_skip_time_stop_expr",
    },
    "VeraScreenerUniverseSelectionModel": set(),  # takes only `store`
    "RiskBudgetedPortfolioConstructionModel": {"risk_per_trade_pct"},
}


def lint(doc: dict, **kw) -> list[spec_lint.LintIssue]:
    return spec_lint.lint_spec(
        doc, column_map=COLUMNS, runtime_kwargs=KWARGS, **kw
    )


def codes(issues) -> set[str]:
    return {i.code for i in issues}


def errors(issues) -> list[spec_lint.LintIssue]:
    return [i for i in issues if i.severity == "error"]


def alpha(**params) -> dict:
    return {"Framework": {"Alpha": {"Type": "VeraPyramidAlphaModel", "Parameters": params}}}


# --- calibration: a valid spec must be silent -----------------------------------------

def test_valid_spec_produces_no_issues() -> None:
    doc = {
        "VeraBase": {
            "Universe": {
                "select": ["close", "rs_rating"],
                "computed": [{"alias": "screens_hit", "kind": "int"}],
            }
        },
        "Framework": {
            "Alpha": {
                "Type": "VeraPyramidAlphaModel",
                "Parameters": {
                    "eligibility_expr": {
                        "type": "any",
                        "items": [
                            {"type": "gte", "left": {"type": "col", "name": "screens_hit"},
                             "right": {"type": "lit", "value": 1}},
                            {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
                             "right": {"type": "lit", "value": 85.0}},
                        ],
                    },
                    "weight_expr": {"type": "col", "name": "rs_rating"},
                },
            }
        },
    }
    assert lint(doc) == []


def test_regression_self_declared_computed_alias_is_in_scope() -> None:
    """Guard: referencing your own `computed` alias must not be flagged.

    `post_where` references `screens_hit`/`setup_pass` declared in the same document. A
    first cut treated them as unknown and produced 4 false errors on every real spec.
    """
    doc = {
        "VeraBase": {
            "Universe": {
                "computed": [
                    {"alias": "screens_hit", "kind": "int"},
                    {"alias": "setup_pass", "kind": "bool"},
                ],
                "post_where": {
                    "type": "all",
                    "items": [
                        {"type": "gte", "left": {"type": "col", "name": "screens_hit"},
                         "right": {"type": "lit", "value": 1}},
                        {"type": "eq", "left": {"type": "col", "name": "setup_pass"},
                         "right": {"type": "lit", "value": 1}},
                    ],
                },
            }
        }
    }
    assert lint(doc) == []


def test_regression_universe_forwarded_params_are_allowed() -> None:
    """Guard: screen/membership/named_groups are live despite the class declaring none.

    `VeraScreenerUniverseSelectionModel.__init__` is `(self, store)`, but the interpreter
    forwards membership/named_groups to the Alpha and the compiler lowers `screen` into
    the universe query. A class-only check called these dead — a false positive.
    """
    doc = {
        "Framework": {
            "UniverseSelection": {
                "Type": "VeraScreenerUniverseSelectionModel",
                "Parameters": {
                    "screen": {"type": "gte", "left": {"type": "col", "name": "close"},
                               "right": {"type": "lit", "value": 5.0}},
                    "membership": {"type": "gte", "left": {"type": "col", "name": "rs_rating"},
                                   "right": {"type": "lit", "value": 70}},
                    "named_groups": {"hygiene": {"type": "gte",
                                                 "left": {"type": "col", "name": "close"},
                                                 "right": {"type": "lit", "value": 5.0}}},
                },
            }
        }
    }
    assert "E201" not in codes(lint(doc))
    assert errors(lint(doc)) == []


def test_regression_position_namespace_is_not_a_column() -> None:
    """`__position.price` is a runtime namespace; flagging it would be a false positive."""
    doc = {"Framework": {"RiskManagement": {"Type": "SwingProgressiveRiskManagementModel",
                                            "Parameters": {
                                                "risk_skip_time_stop_expr": {
                                                    "type": "gt",
                                                    "left": {"type": "col", "name": "__position.price"},
                                                    "right": {"type": "col", "name": "__position.entry"},
                                                }}}}}
    assert lint(doc) == []


# --- E100: malformed expressions ------------------------------------------------------

def test_unknown_node_type_is_rejected() -> None:
    """Type-based discovery is blind here; location-based detection must catch it."""
    issues = lint(alpha(setup_where={"type": "frobnicate"}))
    assert "E100" in codes(issues)
    assert "frobnicate" in " ".join(i.message for i in issues)


def test_nested_unknown_node_type_is_rejected() -> None:
    issues = lint(alpha(setup_where={"type": "all", "items": [{"type": "nope"}]}))
    assert "E100" in codes(issues)


def test_formula_operator_whitelist_enforced() -> None:
    doc = alpha(setup_where={
        "type": "gte",
        "left": {"type": "col", "name": "close"},
        "right": {"type": "formula", "op": "%",
                  "args": [{"type": "col", "name": "close"}, {"type": "lit", "value": 2}]},
    })
    assert "E100" in codes(lint(doc))


def test_formula_arity_enforced() -> None:
    doc = alpha(setup_where={
        "type": "gte",
        "left": {"type": "col", "name": "close"},
        "right": {"type": "formula", "op": "*",
                  "args": [{"type": "lit", "value": 1}, {"type": "lit", "value": 2},
                           {"type": "lit", "value": 3}]},
    })
    assert "E100" in codes(lint(doc))


def test_expression_depth_limit_enforced() -> None:
    node: dict = {"type": "gte", "left": {"type": "col", "name": "close"},
                  "right": {"type": "lit", "value": 1}}
    for _ in range(30):
        node = {"type": "all", "items": [node]}
    assert "E101" in codes(lint(alpha(setup_where=node)))


def test_gates_where_is_discovered() -> None:
    """Sites inside `gates[]` must be found, not just top-level keys."""
    doc = alpha(gates=[{"where": {"type": "bogus_node"}}])
    assert "E100" in codes(lint(doc))


# --- E110: columns -------------------------------------------------------------------

def test_unknown_column_in_universe_subtree_is_an_error() -> None:
    doc = {"VeraBase": {"Universe": {"where": {
        "type": "gte", "left": {"type": "col", "name": "no_such_column"},
        "right": {"type": "lit", "value": 1}}}}}
    assert [i for i in lint(doc) if i.code == "E110" and i.severity == "error"]


def test_unknown_column_under_framework_is_warning_only() -> None:
    """Runtime rows carry aliases the registry cannot know — never a false error."""
    issues = lint(alpha(setup_where={
        "type": "gte", "left": {"type": "col", "name": "runtime_only_alias"},
        "right": {"type": "lit", "value": 1}}))
    ev = [i for i in issues if i.code == "E110"]
    assert ev and all(i.severity == "warning" for i in ev)
    assert errors(issues) == []


# --- E200/E201: parameters -----------------------------------------------------------

def test_unknown_parameter_name_is_rejected() -> None:
    """The exact `**_extra` trap: declared in the spec, not declared by the class."""
    doc = {"Framework": {"RiskManagement": {"Type": "SwingProgressiveRiskManagementModel",
                                            "Parameters": {"initial_risk_pct": 0.005}}}}
    issues = lint(doc)
    assert "E201" in codes(issues)


def test_declared_parameter_is_accepted() -> None:
    doc = {"Framework": {"RiskManagement": {"Type": "SwingProgressiveRiskManagementModel",
                                            "Parameters": {"trailing_arm_r": 1.0}}}}
    assert lint(doc) == []


def test_unknown_model_type_is_rejected() -> None:
    doc = {"Framework": {"Alpha": {"Type": "NoSuchAlpha", "Parameters": {}}}}
    assert "E200" in codes(lint(doc))


def test_parameter_check_skipped_when_runtime_unavailable() -> None:
    """Without introspection the linter still lints expressions, and says so by omission."""
    doc = alpha(initial_risk_pct=1)
    assert spec_lint.lint_spec(doc, column_map=COLUMNS, runtime_kwargs=None) == []


# --- introspection guards ------------------------------------------------------------

def test_discriminator_introspection_is_nonempty_and_includes_operands() -> None:
    """Guards the reflective lookup: an empty set would silently disable the linter."""
    names = spec_lint.expr_type_names()
    assert len(names) >= 15
    assert {"all", "any", "gte", "col", "lit", "formula"} <= names


def test_discriminators_are_shared_across_dialects() -> None:
    """`gte` exists in two dialects; both must be candidates or valid specs are rejected."""
    assert len(spec_lint.classes_by_type()["gte"]) >= 1
    assert {"col", "lit", "formula"} <= spec_lint.operand_type_names()


@pytest.mark.parametrize("sev", ["error", "warning"])
def test_render_summarises(sev: str) -> None:
    out = spec_lint.render([spec_lint.LintIssue(sev, "E100", "/x", "boom")])
    assert "E100" in out and "boom" in out


# --- non-AST column references: order_by / select / row_rank --------------------------

def test_unknown_column_in_order_by_is_an_error() -> None:
    """`order_by[].field` names a column but is a plain string, not a `col` node."""
    doc = {"VeraBase": {"Universe": {"order_by": [{"field": "no_such_column", "direction": "desc"}]}}}
    hits = [i for i in lint(doc) if i.code == "E110" and i.severity == "error"]
    assert hits and "no_such_column" in hits[0].message


def test_unknown_column_in_select_is_an_error() -> None:
    doc = {"VeraBase": {"Universe": {"select": ["close", "nope_not_a_column"]}}}
    assert [i for i in lint(doc) if i.code == "E110" and i.severity == "error"]


def test_row_rank_unknown_column_is_only_a_warning() -> None:
    """Runtime rows carry aliases the registry cannot know — never a false error."""
    doc = alpha(row_rank={"by": ["rs_rating", "definitely_not_a_column"], "min": {"rs_rating": 1}})
    hits = [i for i in lint(doc) if i.code == "E110"]
    assert hits and all(i.severity == "warning" for i in hits)
    assert errors(lint(doc)) == []


def test_valid_column_refs_are_silent() -> None:
    doc = {
        "VeraBase": {
            "Universe": {
                "select": ["close"],
                "computed": [{"alias": "screens_hit"}],
                "order_by": [{"field": "screens_hit", "direction": "desc"}],
            }
        },
        "Framework": {
            "Alpha": {
                "Type": "VeraPyramidAlphaModel",
                "Parameters": {"row_rank": {"by": ["rs_rating"], "min": {"rs_rating": 1}}},
            }
        },
    }
    assert lint(doc) == []


# --- committed parameter artifact (R5) ------------------------------------------------

def test_artifact_loader_reads_types(tmp_path) -> None:
    import json as _json

    path = tmp_path / "t.json"
    path.write_text(_json.dumps({"types": {"SomeAlpha": ["a", "b"], "LeanBuiltin": None}}))
    assert spec_lint.runtime_kwargs_from_artifact(path) == {
        "SomeAlpha": {"a", "b"},
        "LeanBuiltin": None,
    }


def test_artifact_loader_returns_none_when_unreadable(tmp_path) -> None:
    assert spec_lint.runtime_kwargs_from_artifact(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert spec_lint.runtime_kwargs_from_artifact(bad) is None


def test_known_but_uncheckable_type_skips_e201_but_passes_e200() -> None:
    """A Lean built-in is a valid Type whose parameters cannot be introspected here."""
    doc = {"Framework": {"Alpha": {"Type": "LeanBuiltin", "Parameters": {"whatever": 1}}}}
    assert spec_lint.lint_spec(doc, column_map=COLUMNS, runtime_kwargs={"LeanBuiltin": None}) == []


def test_unknown_type_still_rejected_when_table_is_present() -> None:
    doc = {"Framework": {"Alpha": {"Type": "Nope", "Parameters": {}}}}
    assert "E200" in codes(spec_lint.lint_spec(doc, column_map=COLUMNS, runtime_kwargs={"X": None}))


def test_committed_artifact_exists_and_is_well_formed() -> None:
    """The gate reads this in the Studio process, where vera_lab is not importable."""
    table = spec_lint.runtime_kwargs_from_artifact()
    assert table, "packaged runtime_param_table.json is missing or malformed"
    assert len(table) >= 50
    assert any(v is not None for v in table.values()), "no type has checkable parameters"
    assert any(v is None for v in table.values()), "no known-but-uncheckable type"


# --- precision pins (2026-10-02 corpus audit) -----------------------------------------
# Every one of the 40 flagged specs was verified to carry a real defect. These pin the two
# shapes that dominate, so any future loosening of the linter is a deliberate, tested act
# rather than a silent widening.

def test_redundant_op_on_a_comparison_is_rejected() -> None:
    """20 stored specs carry {"type":"eq","op":"eq",...}.

    The runtime dispatches on `type` and only reads `op` for `formula`, so the stray field
    is inert — but it violates C-VERA-EXPR-V1 (`extra="forbid"`), and a stale `op` is
    precisely the field that goes wrong when `type` is later changed.
    """
    doc = alpha(setup_where={"type": "eq", "op": "eq",
                             "left": {"type": "col", "name": "setup_pass"},
                             "right": {"type": "lit", "value": 1}})
    assert "E100" in codes(lint(doc))


def test_suffixed_vcp_column_passes_and_bare_name_fails() -> None:
    """research-vcp-factor-004 selects `vcp_tightness`; the real column is suffixed."""
    assert lint({"VeraBase": {"Universe": {"select": ["vcp_tightness_5d_90d"]}}}) == []
    hits = [i for i in lint({"VeraBase": {"Universe": {"select": ["vcp_tightness"]}}})
            if i.code == "E110" and i.severity == "error"]
    assert hits and "vcp_tightness" in hits[0].message


def test_param_live_on_one_model_is_dead_on_another() -> None:
    """`row_scale_denom` is on VeraPyramidAlphaModel, not the PCM — 13 specs set it there,
    where **_extra eats it silently."""
    doc = {"Framework": {"PortfolioConstruction": {
        "Type": "RiskBudgetedPortfolioConstructionModel",
        "Parameters": {"row_scale_denom": 5}}}}
    issues = spec_lint.lint_spec(doc, column_map=COLUMNS,
                                 runtime_kwargs={"RiskBudgetedPortfolioConstructionModel": {"max_positions"},
                                                 "VeraPyramidAlphaModel": {"row_scale_denom"}})
    assert "E201" in {i.code for i in issues}


# --- Phase 1 fixes (2026-10-02) -------------------------------------------------------

def test_regime_node_with_source_is_accepted() -> None:
    """Regression: this dialect lacked `source`, so a spec carrying it failed validation
    whenever the VeraTradingLab dialect was unavailable — which is the Studio process,
    where saves actually happen. Nine `regime` nodes in the corpus use it."""
    doc = alpha(eligibility_expr={
        "type": "regime", "field": "is_bear_market_active", "eq": 1,
        "source": "market_context",
    })
    assert lint(doc) == []


def test_default_columns_come_from_packaged_sigmarail_field_catalog() -> None:
    columns = spec_lint._registered_columns()
    assert "close" in columns
    assert "rs_rating" in columns



# --- E21x: rule action vocabulary ------------------------------------------------------

ACTIONS = {
    "exit": frozenset({"type", "fraction", "v"}),
    "ratchet_stop": frozenset({"type", "mode", "to", "v"}),
    "arm_cooldown": frozenset({"type", "days", "v"}),
    "skip": frozenset({"type", "v"}),
}


def _rules_doc(then: list) -> dict:
    return {
        "Framework": {
            "RiskManagement": {
                "Type": "SwingProgressiveRiskManagementModel",
                "Parameters": {
                    "rules": [
                        {
                            "name": "r",
                            "when": {"type": "gte",
                                     "left": {"type": "pos", "field": "r"},
                                     "right": {"type": "lit", "value": 3}},
                            "then": then,
                        }
                    ]
                },
            }
        }
    }


def test_rule_action_valid_passes() -> None:
    doc = _rules_doc([
        {"type": "ratchet_stop", "mode": "max",
         "to": {"type": "formula", "op": "*",
                "args": [{"type": "pos", "field": "highest_price"},
                         {"type": "lit", "value": 0.85}]}},
    ])
    assert not [i for i in lint(doc, action_vocabulary=ACTIONS) if i.code == "E212"]


def test_rule_action_null_extra_key_rejected() -> None:
    """Regression: compiler emitted null `days`/`flag`/`fraction` keys on ratchet_stop;
    the runtime models are extra=forbid so even a null extra key failed validation."""
    doc = _rules_doc([{"type": "ratchet_stop", "mode": "max", "to": {"type": "lit", "value": 1},
                       "days": None, "flag": None}])
    errs = [i for i in lint(doc, action_vocabulary=ACTIONS) if i.code == "E212"]
    assert {i.path.rsplit("/", 1)[-1] for i in errs} == {"days", "flag"}


def test_rule_action_unknown_type_rejected() -> None:
    doc = _rules_doc([{"type": "teleport", "to": {"type": "lit", "value": 1}}])
    assert "E211" in codes(lint(doc, action_vocabulary=ACTIONS))


def test_rule_empty_then_rejected() -> None:
    doc = _rules_doc([])
    assert "E210" in codes(lint(doc, action_vocabulary=ACTIONS))


def test_rule_checks_skipped_when_vocabulary_unavailable() -> None:
    doc = _rules_doc([{"type": "teleport"}])
    assert "E211" not in codes(lint(doc, action_vocabulary={}))
