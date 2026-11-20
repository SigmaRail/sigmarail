"""Runtime resolution of action args — the operand-args half of the rule
contract (EXPRESSION_SURFACE §11 / ``sigmarail_lab.ir.rules.ACTION_REGISTRY``).

Numeric action args are operands evaluated through the slot evaluator with
the unit (PCM) or position (Risk) context; bare literals stay accepted for
stored-spec compatibility. Evaluation failures resolve to the caller's
default — an action arg that can't evaluate behaves like an absent arg,
not like a silent zero.
"""

from __future__ import annotations

from typing import Any

from sigmarail_spec.evaluate import evaluate_slot_number


def action_arg_number(
    row: dict[str, Any],
    action: dict[str, Any],
    key: str,
    *,
    position: dict[str, Any] | None = None,
    contexts: dict[str, dict[str, Any]] | None = None,
    default: float | None = None,
) -> float | None:
    """Resolve ``action[key]`` to a number.

    Dict args evaluate as operand ASTs; scalars coerce directly; anything
    else (missing, unresolvable, eval error) returns ``default``.
    """
    v = action.get(key)
    if v is None:
        return default
    if isinstance(v, dict):
        try:
            out = evaluate_slot_number(row, v, position=position, contexts=contexts)
        except Exception:
            out = None
        return default if out is None else float(out)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


__all__ = ["action_arg_number"]
