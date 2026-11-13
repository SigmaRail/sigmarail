"""The Universe frame contract for ``universe_query_v1`` runs.

A Universe query is not just "rows" — the runtime evaluates the Alpha, PCM and
Risk expressions *off the returned columns*, so the frame is an interface:

* VeraBase compiles and executes the screen (``executor.run_universe_range``).
* The runtime reads ``select`` / ``computed`` aliases per row, in SQL ``ORDER BY``
  order (pyramid adds walk that order).

The contract is derived here once — ``strategy/compiler.py`` already harvests the
columns its slot expressions need (``_harvest_select_col``) and appends them to the
select list — so the service can echo it on every execution response and clients can
assert their model requirements are satisfied *before* running a backtest, instead of
silently degrading (missing ``setup_pass`` → fallback path; missing ``vcp_pivot_line``
→ empty pivots → fixed stop).

See ``C-API-SURFACE-V1``.
"""

from __future__ import annotations

from typing import Any


def _as_dict(spec: Any) -> dict[str, Any]:
    """Accept an ``universe_query_v1`` dict or its pydantic model."""
    if isinstance(spec, dict):
        return spec
    dump = getattr(spec, "model_dump", None)
    if callable(dump):
        return dump()
    raise TypeError(f"expected universe_query_v1 dict or model, got {type(spec)!r}")


def frame_contract(spec: Any) -> dict[str, list[Any]]:
    """``select`` / ``computed_aliases`` / ``order_by`` / ``required_fields``.

    ``required_fields`` is the union of the select list and the computed aliases —
    i.e. every column the frame must carry for the caller to evaluate its
    expressions.
    """
    s = _as_dict(spec)

    select = [str(c) for c in (s.get("select") or [])]

    aliases: list[str] = []
    for item in s.get("computed") or []:
        if isinstance(item, dict):
            alias = item.get("alias")
            if alias:
                aliases.append(str(alias))
        elif isinstance(item, str):
            aliases.append(item)

    order_by: list[dict[str, str]] = []
    for ob in s.get("order_by") or []:
        if isinstance(ob, dict):
            order_by.append(
                {
                    "field": str(ob.get("field") or ""),
                    "direction": str(ob.get("direction") or "desc"),
                }
            )
        elif isinstance(ob, str):
            order_by.append({"field": ob, "direction": "desc"})

    return {
        "select": select,
        "computed_aliases": aliases,
        "order_by": order_by,
        "required_fields": list(dict.fromkeys(select + aliases)),
    }
