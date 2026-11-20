"""Studio preview evaluation for slot rule tables (PCM + Risk).

Lets the UI answer "what would this rule table decide for <ticker> on <date>?"
by evaluating authored ``when`` clauses with the *same* evaluator and the
*same* unit-context contract the LEAN runtime uses:

- ``row`` is the ticker's row from the spec's own compiled
  ``universe_query_v1`` for that day — the same T-1 screener row the runtime
  binds as ``col``.
- ``contexts`` (``cand``/``hold``/``acct``/``pyr``/``regime`` for PCM,
  ``pos`` for Risk) are caller-supplied unit shape — the pieces the runtime
  fills from live portfolio state that a preview cannot know.
- Terminality + non-terminal mutations mirror the interpreter: priority
  order, a terminal action ends the pass, and ``displace`` frees a slot that
  downstream rules observe.
"""

from __future__ import annotations

from typing import Any

from sigmarail_spec import evaluate_slot_bool, get_document

from screens.ir_preview import validate_universe_ir_spec


ACTION_TERMINAL = get_document("sigmarail-spec://v1/strategy/runtime-capabilities")["_terminal"]


def _latest_date_for_ticker(client: Any, ticker: str) -> str | None:
    res = client.query(
        "SELECT max(date) FROM screener_price_tech_daily WHERE ticker = %(t)s",
        parameters={"t": ticker},
    )
    if res.result_rows and res.result_rows[0][0] is not None:
        d = res.result_rows[0][0]
        return d.isoformat() if hasattr(d, "isoformat") else str(d)
    return None


def fetch_universe_row(
    client: Any,
    *,
    universe_spec: dict[str, Any],
    ticker: str,
    as_of: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Run the spec's universe for one day and return ``(date, row)``.

    ``row`` is the raw compiled select output for ``ticker`` — the same dict
    the runtime's ``_store_row`` hands to ``evaluate_slot_bool`` as ``col``.
    Returns ``(date, None)`` when the ticker isn't in that day's universe.
    """
    ticker_u = str(ticker or "").strip().upper()
    if not ticker_u:
        raise ValueError("ticker is required")
    day = str(as_of or "").strip() or _latest_date_for_ticker(client, ticker_u)
    if not day:
        raise ValueError(f"no screener data for {ticker_u}")

    _spec, sql, params = validate_universe_ir_spec(universe_spec)
    params = dict(params)
    params["day"] = day
    result = client.query(sql, parameters=params, settings={"allow_experimental_analyzer": 0})
    rows = [dict(zip(result.column_names, r)) for r in result.result_rows]
    for r in rows:
        t = r.get("ticker") or r.get("Ticker") or r.get("symbol")
        if str(t or "").upper() == ticker_u:
            return day, r
    return day, None


def evaluate_rule_table(
    row: dict[str, Any] | None,
    rules: list[dict[str, Any]],
    contexts: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Evaluate ``rules`` for one unit, mirroring the runtime interpreter.

    Returns per-rule match state in evaluation order plus the winning
    decision (first rule whose ``then`` contains a terminal action). The
    shared ``acct`` mutation of a non-terminal ``displace`` is applied so a
    downstream ``enter`` sees the freed slot — same as ``_apply_unit_rules``.
    """
    ctx: dict[str, dict[str, Any]] = {
        ns: dict((contexts or {}).get(ns) or {})
        for ns in ("cand", "hold", "acct", "pyr", "regime", "pos")
    }
    row = dict(row or {})

    per_rule: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None
    for idx, rule in sorted(
        enumerate(rules or []),
        key=lambda x: (x[1].get("priority", 0) if isinstance(x[1], dict) else 0, x[0]),
    ):
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name") or f"rule_{idx}")
        rec: dict[str, Any] = {
            "name": name,
            "priority": rule.get("priority", 0),
            "matched": False,
            "error": None,
        }
        try:
            matched = evaluate_slot_bool(row, rule.get("when"), contexts=ctx)
        except Exception as exc:
            matched, rec["error"] = False, f"{type(exc).__name__}: {exc}"
        rec["matched"] = bool(matched)
        if not matched:
            per_rule.append(rec)
            continue

        actions = [a for a in rule.get("then") or [] if isinstance(a, dict)]
        rec["actions"] = actions
        terminal = False
        for a in actions:
            if ACTION_TERMINAL.get(a.get("type"), False):
                terminal = True
            if a.get("type") == "displace":
                acct = ctx["acct"]
                acct["slots_remaining"] = float(acct.get("slots_remaining") or 0.0) + 1.0
            if a.get("type") == "set_flag" and a.get("flag"):
                ctx["hold"][str(a["flag"])] = 1.0
        if terminal:
            winner = rec
        per_rule.append(rec)
        if terminal:
            break

    return {
        "per_rule": per_rule,
        "decision": {
            "rule": winner["name"] if winner else None,
            "actions": winner["actions"] if winner else [],
        },
        "contexts": ctx,
    }
