"""Pipeline decompiler: VeraLabV1 JSON -> PipelineDocument (round-trip).

Best-effort inverse of ``compiler.compile_pipeline``. The decompiler lets the
UI, CLI, and MCP load any existing VeraLabV1 spec (however it was authored)
back into the staged pipeline view.
"""

from __future__ import annotations

import json
from typing import Any

from .field_registry import FACTOR_REGISTRY
from .pipeline import (
    AllocationPolicy,
    ExecutionConfig,
    ExitTranche,
    FilterCondition,
    FilterGroup,
    FilterNot,
    FilterNode,
    HedgeConfig,
    HedgeInstrument,
    ModelRef,
    PipelineBindings,
    PipelineDocumentation,
    PipelineDocument,
    PortfolioDocument,
    PyramidPhase,
    RiskConfig,
    SelectionRule,
    SizingConfig,
    SizingPolicy,
    SlotExpr,
    Stage,
    StageDocumentation,
    StageType,
    UniverseConfig,
    UniverseSource,
    bindings_to_policy_rules,
)


# column -> semantic factor name (reverse lookup for decompile)
_COLUMN_TO_FACTOR: dict[str, str] = {
    info.column: name for name, info in FACTOR_REGISTRY.items()
}


def _column_to_factor(column: str) -> str:
    """Map a physical column back to a semantic factor name (best effort)."""
    if column in _COLUMN_TO_FACTOR:
        return _COLUMN_TO_FACTOR[column]
    return column  # unknown columns pass through as their own name


def _decompile_operand(node: dict | None) -> str | dict:
    """Convert an IR operand node back to the pipeline representation."""
    node = node or {}
    operand_type = node.get("type", "lit")
    if operand_type == "col":
        return str(node.get("name", ""))
    if operand_type in {"lit", "formula"}:
        return dict(node)
    return {"type": "lit", "value": node.get("value")}


def _decompile_where(node: dict | None) -> FilterNode | None:
    """Translate a universe_query_v1 where AST back into recursive filters."""
    if not node:
        return None
    t = node.get("type")
    if t in {"all", "any"}:
        conditions: list[FilterNode] = []
        for item in node.get("items", []):
            decoded = _decompile_where(item)
            if decoded is not None:
                conditions.append(decoded)
        return FilterGroup(
            logic="and" if t == "all" else "or",
            name=node.get("name") if isinstance(node.get("name"), str) else None,
            conditions=conditions,
        )
    if t == "not":
        inner = _decompile_where(node.get("item") if isinstance(node.get("item"), dict) else None)
        if isinstance(inner, FilterCondition) and inner.op == "eq":
            return FilterCondition(
                op="neq",
                left=inner.left,
                right=inner.right,
                right_kind=inner.right_kind,
                expr=inner.expr,
            )
        if inner is not None:
            # No `neq` form exists for this one, so keep the negation explicit. Returning its
            # child positively (the old behaviour) silently inverted the filter.
            return FilterNot(item=inner)
        return None
    if t in ("gt", "gte", "lt", "lte", "eq"):
        left = _decompile_operand(node.get("left"))
        right_node = node.get("right") or {}
        right_type = right_node.get("type", "lit")
        if right_type == "col":
            right: str | dict = str(right_node.get("name", ""))
            right_kind = "col"
        elif right_type == "formula":
            right = dict(right_node)
            right_kind = "formula"
        else:
            right = right_node.get("value")
            right_kind = "lit"
        return FilterCondition(
            op=t,
            left=left,
            right=right,
            right_kind=right_kind,
        )
    return None


def _manual_symbols_from_universe(universe_spec: dict) -> list[str] | None:
    """Detect a manual ticker filter (``any(eq ticker …)``) in the universe where.

    The compiler lowers a manual symbol list to a store universe filtered by
    ``where any(eq ticker <sym>)``. Return the symbols so the decompiler can
    invert that back to a ``UniverseConfig(source=manual)``.
    """
    where = (universe_spec or {}).get("where") or {}
    if where.get("type") != "any":
        return None
    symbols: list[str] = []
    for item in where.get("items") or []:
        if item.get("type") != "eq":
            return None
        left = item.get("left") or {}
        right = item.get("right") or {}
        if left.get("type") != "col" or left.get("name") != "ticker":
            return None
        if right.get("type") != "lit":
            return None
        symbols.append(str(right.get("value")))
    return symbols or None


def _stage_documentation_records(algo: dict[str, Any]) -> list[dict[str, Any]]:
    raw = algo.get("stage-documentation")
    if not raw:
        return []
    try:
        records = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _restore_stage_documentation(stages: list[Stage], records: list[dict[str, Any]]) -> None:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        mode = record.get("mode")
        if isinstance(mode, str):
            by_mode.setdefault(mode, []).append(record)

    used_by_mode: dict[str, set[int]] = {}
    for stage in stages:
        mode = stage.mode.value
        candidates = by_mode.get(mode, [])
        used = used_by_mode.setdefault(mode, set())
        exact = next(
            (
                index
                for index, record in enumerate(candidates)
                if index not in used and record.get("name") == stage.name
            ),
            None,
        )
        if exact is None:
            exact = next((index for index in range(len(candidates)) if index not in used), None)
        if exact is None:
            continue
        used.add(exact)
        documentation = candidates[exact].get("documentation") or {}
        if isinstance(documentation, dict):
            stage.documentation = StageDocumentation.model_validate(documentation)


def _where_is_empty(where: dict | None) -> bool:
    if not where:
        return True
    if where.get("type") == "all" and not where.get("items"):
        return True
    return False


def _bindings_from_framework(framework: dict[str, Any]) -> PipelineBindings | None:
    """Reconstruct authored bindings from compiled Framework slot Parameters."""
    alpha_params = (framework.get("Alpha") or {}).get("Parameters") or {}
    pcm_params = (framework.get("PortfolioConstruction") or {}).get("Parameters") or {}
    risk_params = (framework.get("RiskManagement") or {}).get("Parameters") or {}

    bindings = PipelineBindings()
    if alpha_params.get("eligibility_expr"):
        bindings.alpha_eligibility = SlotExpr(
            kind="bool", where=dict(alpha_params["eligibility_expr"])
        )
    if alpha_params.get("setup_expr"):
        bindings.alpha_setup = SlotExpr(kind="bool", where=dict(alpha_params["setup_expr"]))
    row_rank = alpha_params.get("row_rank") or {}
    if isinstance(row_rank, dict) and row_rank.get("by"):
        bindings.alpha_rank = [str(c) for c in row_rank["by"]]
    if alpha_params.get("confidence_expr"):
        bindings.alpha_confidence = SlotExpr(
            kind="number", expr=dict(alpha_params["confidence_expr"])
        )
    if alpha_params.get("direction_expr"):
        bindings.alpha_direction = SlotExpr(
            kind="number", expr=dict(alpha_params["direction_expr"])
        )
    if alpha_params.get("magnitude_expr"):
        bindings.alpha_magnitude = SlotExpr(
            kind="number", expr=dict(alpha_params["magnitude_expr"])
        )
    if alpha_params.get("weight_expr"):
        bindings.alpha_weight = SlotExpr(
            kind="number", expr=dict(alpha_params["weight_expr"])
        )
    if alpha_params.get("insight_period_days") is not None:
        try:
            bindings.alpha_insight_period_days = int(alpha_params["insight_period_days"])
        except (TypeError, ValueError):
            bindings.alpha_insight_period_days = None
    if pcm_params.get("pcm_scale_expr"):
        bindings.pcm_scale = SlotExpr(kind="number", expr=dict(pcm_params["pcm_scale_expr"]))
    if pcm_params.get("pcm_allow_entry_expr"):
        bindings.pcm_allow_entry = SlotExpr(
            kind="bool", where=dict(pcm_params["pcm_allow_entry_expr"])
        )
    if risk_params.get("risk_skip_time_stop_expr"):
        bindings.risk_skip_time_stop = SlotExpr(
            kind="bool", where=dict(risk_params["risk_skip_time_stop_expr"])
        )
    if risk_params.get("risk_allow_pyramid_add_expr"):
        bindings.risk_allow_pyramid_add = SlotExpr(
            kind="bool", where=dict(risk_params["risk_allow_pyramid_add_expr"])
        )
    elif pcm_params.get("risk_allow_pyramid_add_expr"):
        bindings.risk_allow_pyramid_add = SlotExpr(
            kind="bool", where=dict(pcm_params["risk_allow_pyramid_add_expr"])
        )
    elif alpha_params.get("risk_allow_pyramid_add_expr"):
        bindings.risk_allow_pyramid_add = SlotExpr(
            kind="bool", where=dict(alpha_params["risk_allow_pyramid_add_expr"])
        )

    if any(
        getattr(bindings, field) is not None
        for field in (
            "alpha_eligibility",
            "alpha_setup",
            "alpha_rank",
            "alpha_confidence",
            "alpha_direction",
            "alpha_magnitude",
            "alpha_weight",
            "alpha_insight_period_days",
            "pcm_scale",
            "pcm_allow_entry",
            "risk_skip_time_stop",
            "risk_allow_pyramid_add",
        )
    ):
        return bindings
    return None


def _binding_fields_for_pipeline(
    framework: dict[str, Any],
) -> tuple[PipelineBindings | None, list, list]:
    """Bindings + policy_rules + policy_overrides for decompiled PipelineDocument."""
    from sigmarail.features.strategy.pipeline import PolicyOverride, SlotExpr

    bindings = _bindings_from_framework(framework)
    policy_rules = bindings_to_policy_rules(bindings) if bindings is not None else []
    pcm_params = (framework.get("PortfolioConstruction") or {}).get("Parameters") or {}
    risk_params = (framework.get("RiskManagement") or {}).get("Parameters") or {}
    raw = pcm_params.get("policy_overrides") or risk_params.get("policy_overrides") or []
    overrides: list = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            when = item.get("when")
            set_map = item.get("set")
            if not isinstance(when, dict) or not isinstance(set_map, dict):
                continue
            try:
                overrides.append(
                    PolicyOverride(
                        id=str(item.get("id") or f"ov_{len(overrides)}"),
                        label=item.get("label"),
                        when=SlotExpr(kind="bool", where=dict(when)),
                        set=dict(set_map),
                    )
                )
            except Exception:
                continue
    return bindings, policy_rules, overrides


def _screen_tree_from_slots(framework: dict[str, Any]) -> list[FilterNode]:
    """Prefer Universe.Parameters.screen; else membership + named_groups."""
    uni = (framework.get("UniverseSelection") or {}).get("Parameters") or {}
    screen_ast = uni.get("screen")
    if screen_ast and not _where_is_empty(screen_ast):
        node = _decompile_where(screen_ast)
        if node is None:
            return []
        if isinstance(node, FilterGroup):
            return [node]
        return [FilterGroup(logic="and", conditions=[node])]
    membership, named = _screen_params_from_slots(framework)
    nodes = _screen_nodes_from_params(membership, named)
    if len(nodes) > 1:
        return [FilterGroup(logic="or", conditions=nodes)]
    return nodes


def _screen_with_legacy_hygiene(
    framework: dict[str, Any], universe_sel: dict[str, Any]
) -> list[FilterNode]:
    """Load screen tree; AND leftover hygiene_where from old specs."""
    nodes = _screen_tree_from_slots(framework)
    hygiene = (universe_sel.get("Parameters") or {}).get("hygiene_where")
    if not hygiene or _where_is_empty(hygiene):
        return nodes
    hnode = _decompile_where(hygiene)
    if hnode is None:
        return nodes
    if not nodes:
        if isinstance(hnode, FilterGroup):
            return [hnode]
        return [FilterGroup(logic="and", conditions=[hnode])]
    return [FilterGroup(logic="and", conditions=[hnode, *nodes])]


def _screen_params_from_slots(framework: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Derived flag ASTs on Universe; fall back to legacy Alpha copies."""
    uni = (framework.get("UniverseSelection") or {}).get("Parameters") or {}
    alpha = (framework.get("Alpha") or {}).get("Parameters") or {}
    membership = uni.get("membership")
    if membership is None or _where_is_empty(membership):
        membership = alpha.get("membership")
    named = uni.get("named_groups") or alpha.get("named_groups") or {}
    return membership, named if isinstance(named, dict) else {}


def _screen_nodes_from_alpha(alpha_params: dict[str, Any]) -> list[FilterNode]:
    """Rebuild universe.screen from membership + named_groups (legacy Alpha params)."""
    return _screen_nodes_from_params(alpha_params.get("membership"), alpha_params.get("named_groups") or {})


def _screen_nodes_from_params(membership: Any, named_groups: Any) -> list[FilterNode]:
    """Rebuild universe.screen from membership + named_groups."""
    screen_nodes: list[FilterNode] = []
    named_groups = named_groups or {}
    if membership and not _where_is_empty(membership):
        mem_node = _decompile_where(membership)
        if mem_node is not None:
            if isinstance(mem_node, FilterGroup):
                mem_node.name = mem_node.name or "membership"
                screen_nodes.append(mem_node)
            else:
                screen_nodes.append(
                    FilterGroup(logic="and", name="membership", conditions=[mem_node])
                )
    if isinstance(named_groups, dict):
        for gname, gast in named_groups.items():
            if str(gname) == "code_33":
                # Code 33 is Alpha gate.where only — never a universe sibling.
                continue
            gnode = _decompile_where(gast) if gast else None
            if gnode is None:
                continue
            if isinstance(gnode, FilterGroup):
                gnode.name = str(gname)
                screen_nodes.append(gnode)
            else:
                screen_nodes.append(
                    FilterGroup(logic="and", name=str(gname), conditions=[gnode])
                )
    return screen_nodes


def _sizing_from_pcm(pcm: dict[str, Any]) -> SizingConfig:
    """Map PCM Type/Parameters back to SizingConfig (RiskBudgeted stays semantic)."""
    pcm_type = str(pcm.get("Type") or "")
    pcm_params = dict(pcm.get("Parameters") or {})
    if pcm_type == "RiskBudgetedPortfolioConstructionModel":
        rebalance = pcm_params.get("rebalance")
        if not rebalance and "rebalance_period_days" in pcm_params:
            try:
                rpd = int(pcm_params["rebalance_period_days"])
                if rpd <= 1:
                    rebalance = "daily"
                elif rpd <= 7:
                    rebalance = "weekly"
                else:
                    rebalance = "monthly"
            except (ValueError, TypeError):
                rebalance = None
        return SizingConfig(
            policy=SizingPolicy.RISK_BUDGETED,
            max_positions=pcm_params.get("max_positions"),
            max_weight=pcm_params.get("max_position_weight"),
            risk_per_trade_pct=pcm_params.get("risk_per_trade_pct"),
            rebalance=rebalance,
            honor_insight_confidence=pcm_params.get("honor_insight_confidence"),
            allow_adds_on_invested=pcm_params.get("allow_adds_on_invested"),
            default_stop_loss_pct=pcm_params.get("default_stop_loss_pct"),
            min_regime_fraction=pcm_params.get("min_regime_fraction"),
            regime_neutral_fraction=pcm_params.get("regime_neutral_fraction"),
            regime_bull_fraction=pcm_params.get("regime_bull_fraction"),
            scaled_max_positions_floor=pcm_params.get("scaled_max_positions_floor"),
            use_regime_scaling=pcm_params.get("use_regime_scaling"),
            enable_displacement=pcm_params.get("enable_displacement"),
            displacement_min_hold_days=pcm_params.get("displacement_min_hold_days"),
            displacement_max_incumbent_r=pcm_params.get("displacement_max_incumbent_r"),
            displacement_min_challenger_rs=pcm_params.get("displacement_min_challenger_rs"),
            displacement_min_challenger_screens=pcm_params.get("displacement_min_challenger_screens"),
            displacement_immune_rs=pcm_params.get("displacement_immune_rs"),
            enable_surrogates=pcm_params.get("enable_surrogates"),
            surrogate_sizing_mode=pcm_params.get("surrogate_sizing_mode"),
            prefer_capital_efficient_surrogates=pcm_params.get("prefer_capital_efficient_surrogates"),
            min_surrogate_adv=pcm_params.get("min_surrogate_adv"),
        )
    if pcm_type == "RiskParityPortfolioConstructionModel":
        return SizingConfig(
            policy=SizingPolicy.RISK_PARITY,
            max_positions=pcm_params.get("max_positions"),
            max_weight=pcm_params.get("max_weight"),
            rebalance=pcm_params.get("rebalance"),
        )
    if pcm_type == "ConfidenceWeightedPortfolioConstructionModel":
        return SizingConfig(
            policy=SizingPolicy.CONFIDENCE_WEIGHTED,
            max_weight=pcm_params.get("max_weight"),
        )
    if pcm_type == "EqualWeightingPortfolioConstructionModel":
        return SizingConfig(policy=SizingPolicy.EQUAL_WEIGHT)
    if pcm_type and pcm_type != "VeraScreenerPortfolioConstructionModel":
        return SizingConfig(model=ModelRef(type=pcm_type, parameters=pcm_params))
    return SizingConfig()


def _execution_from_slot(execution: dict[str, Any]) -> ExecutionConfig:
    exec_type = str(execution.get("Type") or "")
    exec_params = dict(execution.get("Parameters") or {})
    fill_session = exec_params.get("fill_session")
    if fill_session not in ("moo", "moc"):
        fill_session = "moo"
    if exec_type in ("", "VeraScreenerExecutionModel"):
        return ExecutionConfig(fill_session=fill_session)
    return ExecutionConfig(
        fill_session=fill_session,
        model=ModelRef(type=exec_type, parameters=exec_params),
    )


def _exit_stage_from_swing(swing_params: dict[str, Any]) -> Stage:
    tranches_raw = swing_params.get("tranches") or []
    tranches: list[ExitTranche] = []
    if tranches_raw:
        tranches = [ExitTranche.model_validate(t) for t in tranches_raw]
    elif swing_params.get("take_profit_r"):
        tranches = [
            ExitTranche(
                trigger_r=swing_params["take_profit_r"],
                sell_pct=swing_params.get("tranche1_sell_pct", 0.20),
            )
        ]
    return Stage(
        name="Sell Into Strength",
        mode=StageType.EXIT,
        tranches=tranches,
        max_hold_days=swing_params.get("max_holding_days"),
        trailing_stop_pct=swing_params.get("trailing_stop_pct"),
        atr_stop_multiplier=swing_params.get("atr_stop_multiplier"),
        max_stop_loss_pct=swing_params.get("max_stop_loss_pct"),
        use_atr_stops=swing_params.get("use_atr_stops"),
        breakeven_time_stop_days=swing_params.get("breakeven_time_stop_days"),
        max_single_weight=swing_params.get("max_single_weight"),
        breakeven_r_trigger=swing_params.get("breakeven_r_trigger"),
    )


def _apply_alpha_param_knobs(stages: list[Stage], alpha_params: dict[str, Any]) -> None:
    cooldown = alpha_params.get("stop_cooldown_days")
    for stage in stages:
        if (
            stage.mode == StageType.SIGNAL
            and stage.stop_cooldown_days is None
            and cooldown is not None
        ):
            stage.stop_cooldown_days = int(cooldown)


def _apply_pcm_pyramid_knobs(
    stages: list[Stage], pcm_params: dict[str, Any]
) -> None:
    """Fill pyramid stage from PCM Parameters (phases / add_trigger_pct)."""
    add_trigger = pcm_params.get("add_trigger_pct")
    phases = pcm_params.get("phases") or []
    for stage in stages:
        if stage.mode != StageType.PYRAMID:
            continue
        if stage.add_trigger_pct is None and add_trigger is not None:
            stage.add_trigger_pct = float(add_trigger)
        if not stage.phases and phases:
            stage.phases = [PyramidPhase.model_validate(p) for p in phases]


def _decompile_from_alpha_stages(
    spec: dict[str, Any], alpha_stages_raw: list[dict]
) -> PipelineDocument:
    """Rebuild PipelineDocument from Alpha.Parameters.stages + Risk/PCM/Regime."""
    framework = spec.get("Framework", {})
    alpha = framework.get("Alpha", {})
    alpha_params = alpha.get("Parameters", {}) or {}
    risk = framework.get("RiskManagement", {})
    pcm = framework.get("PortfolioConstruction", {})
    universe_sel = framework.get("UniverseSelection", {})
    execution = framework.get("Execution", {})
    algo = spec.get("AlgorithmParameters", {}) or {}
    vb = spec.get("VeraBase") or {}
    universe = vb.get("Universe", {})
    strategy_name = str(spec.get("title") or spec.get("Kind") or "Decompiled Strategy")

    stages: list[Stage] = []
    for raw in alpha_stages_raw:
        stages.append(Stage.model_validate(raw))

    # Exit from Risk Parameters.tranches (honesty) — Composite unwraps primary swing
    risk_type = str(risk.get("Type") or "")
    rp = risk.get("Parameters") or {}
    swing_params = rp
    if risk_type == "CompositeRiskManagementModel":
        for m in rp.get("models") or []:
            if isinstance(m, dict) and m.get("Type") == "SwingProgressiveRiskManagementModel":
                swing_params = m.get("Parameters") or {}
                risk_type = "SwingProgressiveRiskManagementModel"
                break
    if risk_type == "SwingProgressiveRiskManagementModel":
        stages.append(_exit_stage_from_swing(swing_params))
    _apply_alpha_param_knobs(stages, alpha_params)
    pcm_params = (pcm.get("Parameters") or {}) if isinstance(pcm, dict) else {}
    _apply_pcm_pyramid_knobs(stages, pcm_params)
    # Legacy: pyramid knobs still on Alpha Parameters
    if not any(s.mode == StageType.PYRAMID and s.phases for s in stages):
        _apply_pcm_pyramid_knobs(stages, alpha_params)

    hedge = None
    risk_params_full = risk.get("Parameters") or {}
    if risk.get("Type") == "VeraHedgeModel":
        instruments = risk_params_full.get("instruments") or []
        if instruments:
            hedge = HedgeConfig(
                instruments=[HedgeInstrument.model_validate(i) for i in instruments]
            )
    elif risk.get("Type") == "CompositeRiskManagementModel":
        for m in risk_params_full.get("models") or []:
            if isinstance(m, dict) and m.get("Type") == "VeraHedgeModel":
                instruments = (m.get("Parameters") or {}).get("instruments") or []
                if instruments:
                    hedge = HedgeConfig(
                        instruments=[
                            HedgeInstrument.model_validate(i) for i in instruments
                        ]
                    )
                break
    if hedge is None and algo.get("hedge-instruments"):
        tickers = [t.strip() for t in algo["hedge-instruments"].split(",") if t.strip()]
        hedge = HedgeConfig(
            instruments=[HedgeInstrument(ticker=t, max_allocation=0.25) for t in tickers]
        )

    regime_gate = None
    sources = vb.get("DataSources") or []
    regime_src = next((s for s in sources if isinstance(s, dict) and s.get("name") == "regime"), None)
    if regime_src:
        score = dict(regime_src.get("score") or {})
        if regime_src.get("table"):
            score.setdefault("source", regime_src["table"])
        if regime_src.get("uses"):
            score["uses"] = list(regime_src["uses"])
        if score:
            regime_gate = score
    elif vb.get("Regime"):
        regime_gate = dict(vb["Regime"])

    pipeline_doc = PipelineDocumentation()
    if algo.get("pipeline-documentation"):
        try:
            pipeline_doc = PipelineDocumentation.model_validate(
                json.loads(algo["pipeline-documentation"])
            )
        except (TypeError, ValueError):
            pass
    _restore_stage_documentation(stages, _stage_documentation_records(algo))

    universe_type = str(universe_sel.get("Type") or "")
    alpha_type = str(alpha.get("Type") or "")

    alpha_ref = None
    if alpha_type and alpha_type not in (
        "VeraScreenerAlphaModel",
        "VeraCompositeAlphaModel",
        "VeraPyramidAlphaModel",
    ):
        alpha_ref = ModelRef(type=alpha_type, parameters=dict(alpha_params))

    risk_model = None
    if risk.get("Type") not in (
        "NullRiskManagementModel",
        "SwingProgressiveRiskManagementModel",
        "CompositeRiskManagementModel",
        "VeraHedgeModel",
    ):
        risk_model = ModelRef(type=str(risk.get("Type")), parameters=dict(risk_params_full))

    sizing = _sizing_from_pcm(pcm)

    universe_cfg = UniverseConfig(
        screen=_screen_with_legacy_hygiene(framework, universe_sel),
        limit_per_day=universe.get("limit_per_day"),
    )
    manual_syms = _manual_symbols_from_universe(universe)
    if universe_type == "ManualUniverseSelectionModel" or manual_syms:
        universe_cfg = UniverseConfig(
            source=UniverseSource.MANUAL,
            symbols=manual_syms
            or list((universe_sel.get("Parameters") or {}).get("symbols") or []),
        )
    elif universe_type and universe_type != "VeraScreenerUniverseSelectionModel":
        universe_cfg = UniverseConfig(
            model=ModelRef(
                type=universe_type,
                parameters=dict(universe_sel.get("Parameters") or {}),
            )
        )

    execution_cfg = _execution_from_slot(execution)
    bindings, policy_rules, policy_overrides = _binding_fields_for_pipeline(framework)

    return PipelineDocument(
        strategy_name=strategy_name,
        stages=stages,
        gate_combine=alpha_params.get("gate_combine"),
        min_screens=alpha_params.get("min_screens"),
        max_entry_atr_pct=alpha_params.get("max_entry_atr_pct"),
        alpha=alpha_ref,
        universe=universe_cfg,
        sizing=sizing,
        risk=RiskConfig(
            model=risk_model,
            regime_gate=regime_gate,
            max_positions=alpha_params.get("max_positions"),
            time_stop_skip_if=(
                dict(risk.get("Parameters") or {}).get("time_stop_skip_if")
                if isinstance((risk.get("Parameters") or {}).get("time_stop_skip_if"), dict)
                else None
            ),
            circuit_breaker=(
                {
                    "drawdown": float(algo["circuit_drawdown_threshold"]),
                    "pause_days": int(algo["circuit_pause_days"]),
                }
                if algo.get("circuit_drawdown_threshold")
                else None
            ),
        ),
        execution=execution_cfg,
        hedge=hedge,
        documentation=pipeline_doc,
        bindings=bindings,
        policy_rules=policy_rules,
        policy_overrides=policy_overrides,
    )


def decompile_pipeline(spec: dict[str, Any]) -> PipelineDocument:
    """Decompile a VeraLabV1 JSON dict back into a PipelineDocument.

    Prefer ``Framework.Alpha.Parameters.stages`` (five-slot honesty). Legacy
    ``VeraBase.Pipeline`` is accepted once for old specs. Otherwise reconstruct
    heuristically from framework slots and membership / pushdown AST.
    """
    vb = spec.get("VeraBase") or {}
    framework = spec.get("Framework", {})
    alpha = framework.get("Alpha", {})
    alpha_params = alpha.get("Parameters", {}) or {}

    # Preferred: Alpha-card stages (C-STRATEGY-PIPELINE-SSOT amend)
    alpha_stages_raw = alpha_params.get("stages")
    if isinstance(alpha_stages_raw, list) and alpha_stages_raw:
        return _decompile_from_alpha_stages(spec, alpha_stages_raw)

    # Legacy: full Pipeline blob (deprecated)
    pipeline_raw = vb.get("Pipeline")
    if isinstance(pipeline_raw, dict) and "stages" in pipeline_raw:
        try:
            return PipelineDocument.model_validate(pipeline_raw)
        except Exception:
            pass

    risk = framework.get("RiskManagement", {})
    pcm = framework.get("PortfolioConstruction", {})
    universe_sel = framework.get("UniverseSelection", {})
    execution = framework.get("Execution", {})
    algo = spec.get("AlgorithmParameters", {})
    universe = vb.get("Universe", {})
    strategy_name = str(spec.get("title") or spec.get("Kind") or "Decompiled Strategy")

    stages: list[Stage] = []

    screen_nodes = _screen_with_legacy_hygiene(framework, universe_sel)
    if not screen_nodes:
        filter_src = universe.get("where")
        filter_node = _decompile_where(filter_src) if filter_src else None
        if filter_node is not None:
            stages.append(
                Stage(
                    name="Filter",
                    mode=StageType.FILTER,
                    filters=[filter_node],
                    max_candidates=universe.get("limit_per_day"),
                )
            )

    # --- score stages from gates[] (parallel Alpha evaluations) --------------
    gates_raw = alpha_params.get("gates") or []
    if isinstance(gates_raw, list) and gates_raw:
        for gate in gates_raw:
            if not isinstance(gate, dict):
                continue
            fields = list(gate.get("score_fields") or [])
            n = int(gate.get("top_k") or 15)
            weight = 1.0 / len(fields) if fields else 1.0
            gate_where = _decompile_where(gate.get("where")) if gate.get("where") else None
            factors = [{"name": _column_to_factor(f), "weight": weight} for f in fields]
            stages.append(
                Stage(
                    name=str(gate.get("id") or "Gate").replace("_", " ").title(),
                    id=str(gate["id"]) if gate.get("id") else None,
                    mode=StageType.SCORE,
                    as_gate=True,
                    count_as_signal=gate.get("count_as_signal", True),
                    signal_weight=float(gate.get("signal_weight") or 1.0),
                    omit_tt=bool(gate.get("omit_tt")),
                    require_flag=str(gate["require_flag"]) if gate.get("require_flag") else None,
                    optional_score_fields=list(gate.get("optional_score_fields") or []),
                    optional_min=dict(gate.get("optional_min") or {}),
                    factors=factors,
                    filters=[gate_where] if gate_where is not None else [],
                    selection=SelectionRule(method="top_n", n=n) if fields else None,
                )
            )

    # --- score stage from field_weights (or single-factor order_by) ----------
    field_weights = alpha_params.get("field_weights") or {}
    max_positions = alpha_params.get("max_positions") or 10
    selection_raw = alpha_params.get("selection") or {
        "method": "top_n",
        "n": max_positions,
    }
    if field_weights:
        factors = [
            {"name": _column_to_factor(k), "weight": w}
            for k, w in field_weights.items()
        ]
        stages.append(
            Stage(
                name="Rank",
                mode=StageType.SCORE,
                as_gate=False,
                factors=factors,
                selection=SelectionRule.model_validate(selection_raw),
            )
        )
    else:
        # Single-factor (VeraScreenerAlphaModel): reconstruct from universe order_by.
        order_by = universe.get("order_by") or []
        if order_by:
            field = order_by[0].get("field")
            if field and field not in ("overall_score",):
                stages.append(
                    Stage(
                        name="Rank",
                        mode=StageType.SCORE,
                        factors=[{"name": _column_to_factor(field), "weight": 1.0}],
                        selection=SelectionRule.model_validate(selection_raw),
                    )
                )

    # --- signal stage from setup_where and/or entry_triggers ---------------
    setup_where = alpha_params.get("setup_where")
    setup_node = _decompile_where(setup_where) if setup_where else None
    entry_triggers = alpha_params.get("entry_triggers") or []
    if setup_node is not None or entry_triggers:
        stages.append(
            Stage(
                name="Setup Group" if setup_node is not None else "Entry Signal",
                mode=StageType.SIGNAL,
                filters=[setup_node] if setup_node is not None else [],
                entry_triggers=entry_triggers,
                stop_loss=alpha_params.get("stop_loss"),
                max_positions=alpha_params.get("max_positions"),
            )
        )

    # --- pyramid stage from phases (PCM preferred; Alpha legacy fallback) ---
    pcm_params = (pcm.get("Parameters") or {}) if isinstance(pcm, dict) else {}
    phases = pcm_params.get("phases") or alpha_params.get("phases") or []
    add_trigger = pcm_params.get("add_trigger_pct")
    if add_trigger is None:
        add_trigger = alpha_params.get("add_trigger_pct")
    if phases:
        stages.append(
            Stage(
                name="Progressive Exposure",
                mode=StageType.PYRAMID,
                phases=[PyramidPhase.model_validate(p) for p in phases],
                add_trigger_pct=add_trigger,
            )
        )

    # --- exit stage from progressive risk model ----------------------------
    risk_type_raw = str(risk.get("Type") or "")
    rp = risk.get("Parameters") or {}
    swing_params = rp
    if risk_type_raw == "CompositeRiskManagementModel":
        for m in rp.get("models") or []:
            if isinstance(m, dict) and m.get("Type") == "SwingProgressiveRiskManagementModel":
                swing_params = m.get("Parameters") or {}
                risk_type_raw = "SwingProgressiveRiskManagementModel"
                break
    if risk_type_raw == "SwingProgressiveRiskManagementModel":
        stages.append(_exit_stage_from_swing(swing_params))
    _apply_alpha_param_knobs(stages, alpha_params)
    _apply_pcm_pyramid_knobs(stages, pcm_params)

    # --- hedge config from algorithm params --------------------------------
    hedge = None
    if algo.get("hedge-instruments"):
        tickers = [t.strip() for t in algo["hedge-instruments"].split(",") if t.strip()]
        hedge = HedgeConfig(
            instruments=[HedgeInstrument(ticker=t, max_allocation=0.25) for t in tickers]
        )

    # --- restore pipeline documentation -------------------------------------
    pipeline_doc = PipelineDocumentation()
    if algo.get("pipeline-documentation"):
        try:
            pipeline_doc = PipelineDocumentation.model_validate(json.loads(algo["pipeline-documentation"]))
        except (TypeError, ValueError):
            pass

    stage_records = _stage_documentation_records(algo)
    _restore_stage_documentation(stages, stage_records)

    # --- passthrough for slots we can't express semantically (lossless) ------
    alpha_type = str(alpha.get("Type") or "")
    risk_type = str(risk.get("Type") or "NullRiskManagementModel")
    universe_type = str(universe_sel.get("Type") or "")

    alpha_ref = None
    if alpha_type and alpha_type not in ("VeraScreenerAlphaModel", "VeraCompositeAlphaModel", "VeraPyramidAlphaModel"):
        alpha_ref = ModelRef(type=alpha_type, parameters=dict(alpha_params))

    risk_model = None
    if risk_type not in ("NullRiskManagementModel", "SwingProgressiveRiskManagementModel"):
        risk_model = ModelRef(type=risk_type, parameters=dict(risk.get("Parameters") or {}))

    sizing = _sizing_from_pcm(pcm)

    universe_cfg = UniverseConfig(
        screen=screen_nodes,
        limit_per_day=universe.get("limit_per_day"),
    )
    manual_syms = _manual_symbols_from_universe(universe)
    if universe_type == "ManualUniverseSelectionModel" or manual_syms:
        universe_cfg = UniverseConfig(
            source=UniverseSource.MANUAL,
            symbols=manual_syms or list((universe_sel.get("Parameters") or {}).get("symbols") or []),
        )
    elif universe_type and universe_type != "VeraScreenerUniverseSelectionModel":
        universe_cfg = UniverseConfig(model=ModelRef(type=universe_type, parameters=dict(universe_sel.get("Parameters") or {})))

    execution_cfg = _execution_from_slot(execution)

    risk_params = dict(risk.get("Parameters") or {})
    bindings, policy_rules, policy_overrides = _binding_fields_for_pipeline(framework)
    return PipelineDocument(
        strategy_name=strategy_name,
        stages=stages,
        gate_combine=alpha_params.get("gate_combine"),
        min_screens=alpha_params.get("min_screens"),
        max_entry_atr_pct=alpha_params.get("max_entry_atr_pct"),
        alpha=alpha_ref,
        universe=universe_cfg,
        sizing=sizing,
        risk=RiskConfig(
            model=risk_model,
            time_stop_skip_if=(
                dict(risk_params["time_stop_skip_if"])
                if isinstance(risk_params.get("time_stop_skip_if"), dict)
                else None
            ),
        ),
        execution=execution_cfg,
        hedge=hedge,
        documentation=pipeline_doc,
        bindings=bindings,
        policy_rules=policy_rules,
        policy_overrides=policy_overrides,
    )


def decompile_portfolio(spec: dict[str, Any]) -> PortfolioDocument:
    """Decompile a VeraLabV1 JSON dict back into a PortfolioDocument.

    A ``CompositeAlphaModel`` spec becomes a multi-leg portfolio (one leg per
    child alpha, each passed through verbatim via ``ModelRef``); anything else
    becomes a single-leg portfolio.
    """
    framework = spec.get("Framework", {})
    alpha = framework.get("Alpha", {})
    name = str(spec.get("title") or spec.get("Kind") or "Decompiled Portfolio")

    if alpha.get("Type") == "CompositeAlphaModel":
        children = (alpha.get("Parameters") or {}).get("models") or []
        legs = []
        for i, child in enumerate(children):
            child_type = str(child.get("Type") or "Alpha")
            leg_spec = {
                "SchemaVersion": 2,
                "Kind": "VeraLabV1",
                "title": f"{child_type}_{i}",
                "Framework": {
                    **framework,
                    "Alpha": {"Type": child.get("Type"), "Parameters": child.get("Parameters") or {}},
                },
                "AlgorithmParameters": spec.get("AlgorithmParameters", {}),
                "VeraBase": spec.get("VeraBase", {}),
            }
            legs.append(decompile_pipeline(leg_spec))

        alloc = AllocationPolicy()
        pcm_type = str(framework.get("PortfolioConstruction", {}).get("Type") or "")
        if pcm_type == "RiskParityPortfolioConstructionModel":
            alloc.base = "risk_parity"
        return PortfolioDocument(name=name, legs=legs, allocation=alloc)

    return PortfolioDocument(name=name, legs=[decompile_pipeline(spec)])
