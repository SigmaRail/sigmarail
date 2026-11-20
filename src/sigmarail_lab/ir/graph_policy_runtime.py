"""Evaluate Policy B graph if/weight steps (declarative sizing)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union

from .models import (
    FilterStep,
    GraphStep,
    GroupStep,
    IfStep,
    SelectStep,
    WeightStep,
)
from .policy_eval import evaluate_bool_expr
from .signal_context import SignalContext

Action = Literal["enter", "hold", "trim", "exit", "flat"]


def parse_graph(data: dict[str, Any]) -> GraphStep:
    """Parse a JSON dict into a GraphStep model using Pydantic discriminator."""
    from pydantic import TypeAdapter
    return TypeAdapter(GraphStep).validate_python(data)


@dataclass
class PolicyState:
    current_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    targets: dict[str, float]
    action: Action


def is_policy_graph(root: GraphStep) -> bool:
    """True when root contains if/weight policy tree (not universe-only graph)."""

    def walk(node: GraphStep) -> bool:
        if isinstance(node, (IfStep, WeightStep)):
            return True
        if isinstance(node, GroupStep):
            return any(walk(c) for c in node.children)
        return False

    return walk(root)


def _parse_weight_value(raw: str, *, current: float) -> tuple[float, Action]:
    s = (raw or "").strip()
    if s.startswith("trim:"):
        frac = float(s.split(":", 1)[1])
        return max(0.0, current * (1.0 - frac)), "trim"
    if s in ("$HOLD", "hold"):
        return current, "hold"
    if s in ("$CASH", "cash", "0", "0.0"):
        return 0.0, "flat"
    return float(s), "enter"


def _apply_weight_step(step: WeightStep, state: PolicyState) -> PolicyDecision:
    targets: dict[str, float] = dict(state.current_weights)
    action: Action = "hold"
    if step.mode == "specified" and step.weights:
        for ticker, raw in step.weights.items():
            t = ticker.strip().upper()
            if t.startswith("$"):
                continue
            cur = targets.get(t, 0.0)
            w, act = _parse_weight_value(str(raw), current=cur)
            targets[t] = w
            if act != "hold":
                action = act
    return PolicyDecision(targets=targets, action=action)


def _evaluate_node(node: GraphStep, ctx: SignalContext, state: PolicyState, algorithm=None) -> PolicyDecision:
    if algorithm:
        algorithm.Debug(f"EVAL NODE: type={type(node).__name__}")
    if isinstance(node, IfStep):
        cond_result = evaluate_bool_expr(node.condition, ctx, algorithm)
        if algorithm:
            algorithm.Debug(f"EVAL NODE: IfStep condition={cond_result}")
        return _evaluate_node(
            node.then if cond_result else node.else_, ctx, state, algorithm
        )
    if isinstance(node, WeightStep):
        return _apply_weight_step(node, state)
    if isinstance(node, GroupStep):
        for child in node.children:
            if isinstance(child, IfStep):
                cond_result = evaluate_bool_expr(child.condition, ctx, algorithm)
                branch = child.then if cond_result else child.else_
                return _evaluate_node(branch, ctx, state, algorithm)
            if isinstance(child, WeightStep):
                return _apply_weight_step(child, state)
            if isinstance(child, GroupStep) and is_policy_graph(child):
                dec = _evaluate_node(child, ctx, state, algorithm)
                if dec.action != "hold" or dec.targets != state.current_weights:
                    return dec
        return PolicyDecision(targets=dict(state.current_weights), action="hold")
    return PolicyDecision(targets=dict(state.current_weights), action="hold")


def evaluate_graph(
    root: GraphStep,
    ctx: SignalContext,
    *,
    state: PolicyState | None = None,
    algorithm=None,
) -> PolicyDecision:
    st = state or PolicyState()
    return _evaluate_node(root, ctx, st, algorithm)
