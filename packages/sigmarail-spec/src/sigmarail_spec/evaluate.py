"""Row-level evaluators for the canonical dialect.

Moved from VeraTradingLab's `vera_lab/runtime/signal_evaluation.py` on consolidation,
because the evaluator must handle every node the dialect declares and the two had to
stop living in different repos. Imports only `typing` (+ stdlib) — pure by construction.
"""

from __future__ import annotations

from typing import Any


def evaluate_single_trigger(
    row: dict[str, Any],
    trigger: dict[str, Any],
    current_price: float | None = None,
) -> bool:
    """Evaluate one EntryTrigger against an L7 screener row.

    Two forms (EXPRESSION_SURFACE §11): ``{"expr": <BoolExprItem>}`` — the
    convergent AST form, evaluated by ``evaluate_slot_bool`` over the row
    plus injected ``__px``/``__close_px`` context columns — and the legacy
    enum ``{"type": "pivot_breakout", ...}`` dispatch below.
    """
    expr = trigger.get("expr") if isinstance(trigger, dict) else None
    if isinstance(expr, dict):
        from .entry_trigger_ast import trigger_eval_row

        return evaluate_slot_bool(trigger_eval_row(row, current_price), expr)
    ttype = str(trigger.get("type") or "").strip().lower()

    if ttype in ("pivot_breakout", "breakout"):
        lookback = trigger.get("lookback_days")
        use_short_pivot = False
        if lookback is not None:
            try:
                use_short_pivot = 1 <= int(lookback) <= 10
            except (TypeError, ValueError):
                use_short_pivot = False
        # lookback 1-10 → high_5d; unset or >= 90 → high_90d
        pivot_raw = row.get("high_5d") if use_short_pivot else row.get("high_90d")
        high_val = row.get("high")
        breakout_sig = bool(row.get("breakout_signal"))

        # Price condition
        if pivot_raw is not None and float(pivot_raw) > 0:
            pivot = float(pivot_raw)
            price_cleared = (high_val is not None and float(high_val) >= pivot) or breakout_sig
            if not price_cleared:
                return False
            # Still above pivot, and not chasing more than ~5% through it
            if current_price is not None and current_price > 0:
                if current_price < pivot * 0.98:  # more than 2% below breakout level
                    return False
                if current_price > pivot * 1.05:
                    return False
        elif not breakout_sig:
            return False

        # Volume condition
        vol_mult = float(trigger.get("volume_multiplier") or 1.0)
        vol = row.get("volume")
        avg_vol = row.get("avg_vol_50d")
        if avg_vol is not None and float(avg_vol) > 0:
            if vol is None or float(vol) < float(avg_vol) * vol_mult:
                return False

        return True

    elif ttype == "vcp_complete":
        compression = row.get("vcp_atr_compression_5d_90d")
        dryup = row.get("vcp_volume_dryup_5d_90d")
        max_compression = float(trigger.get("max_compression") or 0.40)
        max_dryup = float(trigger.get("max_dryup") or 0.70)
        if compression is None or float(compression) > max_compression:
            return False
        if dryup is None or float(dryup) > max_dryup:
            return False

        close_px = current_price if current_price is not None else row.get("close")
        high_90d = row.get("high_90d")
        proximity = row.get("vcp_proximity_90d")
        min_prox = float(trigger.get("min_proximity") or 0.90)
        if proximity is not None:
            if float(proximity) < min_prox:
                return False
        elif close_px is not None and high_90d is not None and float(high_90d) > 0:
            if float(close_px) < float(high_90d) * min_prox:
                return False

        return True

    elif ttype == "pullback_to_sma":
        pullback_ready = bool(row.get("pullback_ready"))
        pocket_pivot = float(row.get("pocket_pivot_score") or 0.0) >= 30.0
        if not (pullback_ready or pocket_pivot):
            return False

        # Check proximity to moving average if present
        sma_period = trigger.get("sma_period") or 50
        sma_col = f"sma{int(sma_period)}d"
        sma_val = row.get(sma_col) or row.get("sma50d")
        close_px = current_price if current_price is not None else row.get("close")
        if sma_val is not None and float(sma_val) > 0 and close_px is not None:
            max_dev = float(trigger.get("max_deviation_pct") or 0.05)
            # Price must be at or within max_dev below SMA
            if float(close_px) < float(sma_val) * (1.0 - max_dev):
                return False

        return True

    elif ttype == "ema_cross":
        ema_21 = row.get("ema_21d")
        sma_50 = row.get("sma50d")
        if ema_21 is not None and sma_50 is not None:
            return float(ema_21) >= float(sma_50)
        return True

    # Unknown or unhandled trigger types pass through
    return True


def _eval_operand(row: dict[str, Any], operand: Any) -> float | None:
    if operand is None:
        return None
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return float(operand)
    if isinstance(operand, str):
        val = row.get(operand)
        return None if val is None else float(val)
    if not isinstance(operand, dict):
        return None
    kind = operand.get("type")
    if kind == "lit":
        val = operand.get("value")
        if val is None or isinstance(val, bool):
            return None if val is None else float(val)
        return float(val)
    if kind == "col":
        val = row.get(operand.get("name"))
        return None if val is None else float(val)
    if kind == "pos":
        # Runtime position binding. Slot evaluators merge the position dict
        # into the row under this internal namespace, so a binding reads like
        # any other lookup — and row-only evaluations see ``None``.
        val = row.get(f"__position.{operand.get('field')}")
        return None if val is None else float(val)
    if kind == "ref":
        # Namespaced runtime binding (superset of ``pos``). ``ns="pos"`` reads
        # the same ``__position.`` namespace the ``pos`` node does; other
        # namespaces resolve under ``__<ns>.``. Missing namespace/field → None.
        ns = operand.get("ns")
        ns_key = "__position" if ns == "pos" else f"__{ns}"
        val = row.get(f"{ns_key}.{operand.get('field')}")
        return None if val is None else float(val)
    if kind == "formula":
        args = operand.get("args") or []
        if len(args) != 2:
            return None
        left = _eval_operand(row, args[0])
        right = _eval_operand(row, args[1])
        if left is None or right is None:
            return None
        op = operand.get("op")
        if op == "*":
            return left * right
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "/":
            return left / right if right else None
    if kind == "min":
        vals = [_eval_operand(row, a) for a in (operand.get("args") or [])]
        return None if not vals or any(v is None for v in vals) else min(vals)
    if kind == "max":
        vals = [_eval_operand(row, a) for a in (operand.get("args") or [])]
        return None if not vals or any(v is None for v in vals) else max(vals)
    if kind == "clamp":
        v = _eval_operand(row, operand.get("value"))
        lo = _eval_operand(row, operand.get("min"))
        hi = _eval_operand(row, operand.get("max"))
        if v is None or lo is None or hi is None:
            return None
        return min(max(v, lo), hi)
    if kind == "abs":
        v = _eval_operand(row, operand.get("arg"))
        return None if v is None else abs(v)
    if kind == "cond":
        # fail-closed `when` (slot semantics): missing data → `otherwise`, which is
        # exactly the graceful-fallback branch this node exists for.
        if evaluate_slot_bool(row, operand.get("when")):
            return _eval_operand(row, operand.get("then"))
        return _eval_operand(row, operand.get("otherwise"))
    return None


# Row-predicate nodes that carry their operands as fields instead of `left`/`right`.
_FLAT_PREDICATES = ("col_gte", "col_lte", "col_eq", "between", "in_tickers")


def _eval_row_predicate(row: dict[str, Any], node: dict[str, Any]) -> bool | None:
    """Evaluate the flat row-predicate nodes; ``None`` when the node is not one of them.

    Shared by ``evaluate_where_ast`` and ``evaluate_slot_bool`` on purpose: those two used to
    carry near-identical comparison dispatch, and duplicated dispatch is the drift this
    package exists to remove. Missing data returns ``False`` — matching how the ``gt``/``gte``
    family already treats a ``None`` operand in *both* evaluators — while ``None`` here means
    only "not my node type", so each caller keeps its own documented fallback (fail-open for
    `where`, fail-closed for slots).

    These five were declared by the dialect but never implemented, so each one silently took
    the caller's fallback: inside a `where` that meant **True**, i.e. an unimplemented filter
    passed everything. `in_tickers` is the ETF universe mechanism, so that fallback disabled
    the universe restriction outright.
    """
    ntype = node.get("type")
    if ntype not in _FLAT_PREDICATES:
        return None
    if ntype == "in_tickers":
        tickers = node.get("tickers") or []
        val = row.get("ticker")
        if val is None:
            return False
        return val in tickers
    if ntype == "between":
        val = _eval_operand(row, {"type": "col", "name": node.get("column")})
        lo = _eval_operand(row, {"type": "lit", "value": node.get("min")})
        hi = _eval_operand(row, {"type": "lit", "value": node.get("max")})
        if val is None or lo is None or hi is None:
            return False
        return lo <= val <= hi
    val = _eval_operand(row, {"type": "col", "name": node.get("column")})
    rhs = _eval_operand(row, {"type": "lit", "value": node.get("value")})
    if val is None or rhs is None:
        return False
    if ntype == "col_gte":
        return val >= rhs
    if ntype == "col_lte":
        return val <= rhs
    return val == rhs


_COMPARATORS = ("gt", "gte", "lt", "lte", "eq", "neq")


def _eval_bool(
    row: dict[str, Any], node: dict[str, Any] | None, *, unknown: bool | None
) -> bool | None:
    """Tri-state bool core shared by ``evaluate_where_ast`` / ``evaluate_slot_bool``.

    Returns ``True``/``False``, or ``None`` — *unresolvable* — when the subtree
    bottoms out on an unimplemented or unrecognized node type. ``None``
    propagates through combinators so an unknown construct can never be
    laundered into a definite answer by negation: ``not <bogus>`` stays
    unresolvable rather than inverting a fallback ``False`` into ``True``.
    ``unknown`` is the per-site leaf for unrecognized nodes (``True`` for the
    fail-open filter path, ``None`` for the fail-closed slot path); each
    boundary maps any residual ``None`` to its documented contract.

    Missing *data* is deliberately not tri-state: a comparator whose operand
    evaluates to ``None`` resolves ``False`` ("cannot verify"), so
    ``not (absent_col > 0)`` remains ``True`` — the permissive reading an
    optional-context ``when`` wants. Lint, not negation semantics, is what must
    stop a genuinely unknown column.
    """
    if not node:
        return unknown
    ntype = node.get("type")
    if ntype == "all":
        items = node.get("items") or []
        if not items:
            return unknown
        saw_none = False
        for i in items:
            v = _eval_bool(row, i, unknown=unknown)
            if v is False:
                return False
            if v is None:
                saw_none = True
        return None if saw_none else True
    if ntype == "any":
        items = node.get("items") or []
        if not items:
            return unknown
        saw_none = False
        for i in items:
            v = _eval_bool(row, i, unknown=unknown)
            if v is True:
                return True
            if v is None:
                saw_none = True
        return None if saw_none else False
    if ntype == "not":
        v = _eval_bool(row, node.get("item"), unknown=unknown)
        return None if v is None else not v
    if ntype in _COMPARATORS:
        left = _eval_operand(row, node.get("left"))
        right = _eval_operand(row, node.get("right"))
        if left is None or right is None:
            return False
        if ntype == "gt":
            return left > right
        if ntype == "gte":
            return left >= right
        if ntype == "lt":
            return left < right
        if ntype == "lte":
            return left <= right
        if ntype == "neq":
            return left != right
        return left == right
    pred = _eval_row_predicate(row, node)
    return pred if pred is not None else unknown


def evaluate_where_ast(row: dict[str, Any], node: dict[str, Any] | None) -> bool:
    """Evaluate a universe_query_v1 where AST against one store row.

    Unknown node types return True (legacy filter fallback). Prefer
    ``evaluate_slot_bool`` for eligibility / skip-stop / allow-entry.
    """
    v = _eval_bool(row, node, unknown=True)
    return v if v is not None else True


def _merge_contexts(
    row: dict[str, Any],
    position: dict[str, Any] | None,
    contexts: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Merge runtime context dicts into the row namespace.

    ``position`` is shorthand for ``contexts["pos"]`` (merged under
    ``__position.`` — the historical key). Any other ``ns`` merges under
    ``__<ns>.`` so ``{"type":"ref","ns":ns,"field":f}`` resolves it.
    """
    merged = dict(row or {})
    ctx = dict(contexts or {})
    if position:
        ctx.setdefault("pos", position)
    for ns, bag in ctx.items():
        if not bag:
            continue
        prefix = "__position" if ns == "pos" else f"__{ns}"
        for k, v in bag.items():
            key = str(k)
            if not key.startswith("__"):
                key = f"{prefix}.{key}"
            merged[key] = v
    return merged


def evaluate_slot_number(
    row: dict[str, Any],
    expr: dict[str, Any] | None,
    *,
    position: dict[str, Any] | None = None,
    contexts: dict[str, dict[str, Any]] | None = None,
) -> float | None:
    """Fail-closed number eval for PCM scale / Alpha confidence SlotExpr."""
    if not expr:
        return None
    return _eval_operand(_merge_contexts(row, position, contexts), expr)


def evaluate_slot_bool(
    row: dict[str, Any],
    node: dict[str, Any] | None,
    *,
    position: dict[str, Any] | None = None,
    contexts: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Fail-closed bool eval for setup / eligibility / risk skip SlotExpr.

    Unknown ops, missing cols, and empty nodes → False (do not enter / do not
    skip). "Fail-closed" holds under negation too: an *unresolvable* node
    (unimplemented/unknown type) propagates ``None`` up to this boundary, so
    ``not <bogus>`` is False, not the inverted-fallback True it once returned.
    A comparator with a missing operand still resolves False — negating it is
    the permissive "feature absent → not blocked" reading.
    """
    merged = _merge_contexts(row, position, contexts)
    return _eval_bool(merged, node, unknown=None) is True


def evaluate_entry_triggers(
    row: dict[str, Any],
    triggers: list[dict[str, Any]],
    current_price: float | None = None,
) -> bool:
    """Evaluate whether an L7 screener row satisfies the entry triggers (OR logic)."""
    if not triggers:
        return True
    return any(evaluate_single_trigger(row, t, current_price=current_price) for t in triggers)
