"""Enum ``entry_triggers`` → bool AST lowering (EXPRESSION_SURFACE §11).

The enum form (``{"type": "pivot_breakout", ...}``) is a procedural switch in
``evaluate_single_trigger`` — a predicate dressed as config. The convergent
form is ``{"expr": <BoolExprItem>}``: evaluated by ``evaluate_slot_bool``
against the screener row plus injected context columns:

* ``__px`` — the live price, injected *only when provided* (band checks that
  must skip when no live price exists test its presence),
* ``__close_px`` — ``current_price`` falling back to ``row["close"]``
  (mirrors the legacy ``close_px`` computation).

Dunder names are deliberately non-L7: they cannot collide with physical
columns and are exempt from lint's column checks.

``compile_entry_trigger`` is generation-side tooling: materializers emit the
AST form so stored specs carry the predicate itself, searchable and mutable.
The enum path remains in ``evaluate_single_trigger`` for stored-spec
compatibility; ``tests`` pin enum ≡ compiled-AST equivalence.
"""

from __future__ import annotations

from typing import Any

# Presence sentinel — the dialect has no ``has`` node, so "column is present"
# is ``gte(col, -1e18)``. Values that plausibly reach -1e18 do not exist in L7.
_PRESENT = -1e18


def _col(name: str) -> dict:
    return {"type": "col", "name": name}


def _lit(v: float | int) -> dict:
    return {"type": "lit", "value": v}


def _gt(a: Any, b: Any) -> dict:
    return {"type": "gt", "left": a, "right": b}


def _gte(a: Any, b: Any) -> dict:
    return {"type": "gte", "left": a, "right": b}


def _lte(a: Any, b: Any) -> dict:
    return {"type": "lte", "left": a, "right": b}


def _mul(a: Any, b: Any) -> dict:
    return {"type": "formula", "op": "*", "args": [a, b]}


def _all(*items: dict) -> dict:
    return {"type": "all", "items": list(items)}


def _any(*items: dict) -> dict:
    return {"type": "any", "items": list(items)}


def _not(item: dict) -> dict:
    return {"type": "not", "item": item}


def _present(name: str) -> dict:
    return _gte(_col(name), _lit(_PRESENT))


def _flag(name: str) -> dict:
    """Truthy-column leaf — ``bool(row.get(name))`` spelled as a comparator
    (bare ``col`` is an operand, not a bool node; ``neq x 0`` matches Python
    truthiness for numbers/strings/bools and resolves False when absent)."""
    return {"type": "neq", "left": _col(name), "right": _lit(0)}


def _pivot_breakout(t: dict) -> dict:
    lookback = t.get("lookback_days")
    short = False
    if lookback is not None:
        try:
            short = 1 <= int(lookback) <= 10
        except (TypeError, ValueError):
            short = False
    pivot = _col("high_5d" if short else "high_90d")
    vol_mult = float(t.get("volume_multiplier") or 1.0)

    # Price leg: (pivot>0 AND (high>=pivot OR breakout) AND (px absent OR px
    # within 0.98p..1.05p)) OR (pivot invalid AND breakout)
    price = _any(
        _all(
            _gt(pivot, _lit(0)),
            _any(_gte(_col("high"), pivot), _flag("breakout_signal")),
            _any(
                _not(_gt(_col("__px"), _lit(0))),
                _all(
                    _gte(_col("__px"), _mul(pivot, _lit(0.98))),
                    _lte(_col("__px"), _mul(pivot, _lit(1.05))),
                ),
            ),
        ),
        _all(_not(_gt(pivot, _lit(0))), _flag("breakout_signal")),
    )
    # Volume leg: avg_vol absent/nonpos → skip; else volume >= avg*mult
    volume = _any(
        _not(_gt(_col("avg_vol_50d"), _lit(0))),
        _gte(_col("volume"), _mul(_col("avg_vol_50d"), _lit(vol_mult))),
    )
    return _all(price, volume)


def _vcp_complete(t: dict) -> dict:
    max_comp = float(t.get("max_compression") or 0.40)
    max_dry = float(t.get("max_dryup") or 0.70)
    min_prox = float(t.get("min_proximity") or 0.90)
    prox = _col("vcp_proximity_90d")
    high90 = _col("high_90d")
    close = _col("__close_px")

    # proximity present → require >= min; absent → close fallback only when
    # both close_px and high_90d are present (else pass)
    proximity_ok = _any(
        _all(_present("vcp_proximity_90d"), _gte(prox, _lit(min_prox))),
        _all(
            _not(_present("vcp_proximity_90d")),
            _any(
                _not(_present("__close_px")),
                _not(_gt(high90, _lit(0))),
                _gte(close, _mul(high90, _lit(min_prox))),
            ),
        ),
    )
    return _all(
        _lte(_col("vcp_atr_compression_5d_90d"), _lit(max_comp)),
        _lte(_col("vcp_volume_dryup_5d_90d"), _lit(max_dry)),
        proximity_ok,
    )


def _pullback_to_sma(t: dict) -> dict:
    period = t.get("sma_period") or 50
    try:
        sma_col = f"sma{int(period)}d"
    except (TypeError, ValueError):
        sma_col = "sma50d"
    max_dev = float(t.get("max_deviation_pct") or 0.05)
    close = _col("__close_px")
    # sma_val = row[smaN] or row[sma50d] — coalesce via cond
    sma_val = {
        "type": "cond",
        "when": _gt(_col(sma_col), _lit(0)),
        "then": _col(sma_col),
        "otherwise": _col("sma50d"),
    }
    return _all(
        _any(_flag("pullback_ready"), _gte(_col("pocket_pivot_score"), _lit(30))),
        _any(
            _not(_gt(sma_val, _lit(0))),
            _not(_present("__close_px")),
            _gte(close, _mul(sma_val, _lit(1.0 - max_dev))),
        ),
    )


def _ema_cross(_t: dict) -> dict:
    ema = _col("ema_21d")
    sma = _col("sma50d")
    # both present → ema >= sma; otherwise pass
    return _any(
        _not(_present("ema_21d")),
        _not(_present("sma50d")),
        _gte(ema, sma),
    )


_COMPILERS = {
    "pivot_breakout": _pivot_breakout,
    "breakout": _pivot_breakout,
    "vcp_complete": _vcp_complete,
    "pullback_to_sma": _pullback_to_sma,
    "ema_cross": _ema_cross,
}

ENUM_TRIGGER_TYPES = frozenset(_COMPILERS)


def compile_entry_trigger(trigger: dict[str, Any]) -> dict | None:
    """Lower an enum trigger to its equivalent bool AST.

    Returns ``None`` for ``{"expr": ...}`` (already AST) and unknown enum
    types — the legacy evaluator treats those as pass-through, so there is
    no AST to emit.
    """
    if not isinstance(trigger, dict):
        return None
    ttype = str(trigger.get("type") or "").strip().lower()
    fn = _COMPILERS.get(ttype)
    return None if fn is None else fn(trigger)


def trigger_eval_row(row: dict[str, Any], current_price: float | None = None) -> dict:
    """The injected context columns a trigger ``expr`` evaluates against."""
    out = dict(row or {})
    close = current_price if current_price is not None else out.get("close")
    if close is not None:
        out["__close_px"] = close
    if current_price is not None:
        out["__px"] = current_price
    return out


__all__ = ["ENUM_TRIGGER_TYPES", "compile_entry_trigger", "trigger_eval_row"]
