"""HARD entry-gate + position-management tools (Vera methodology in code).

``evaluate_entry_gate`` scope = **Model 2 swing stock entries**
(``entry_gate_rules.yaml`` ``scope: model2_swing_stocks``). A closed gate
does not freeze Model 1 SPYM / UPRO sleeve management — see
``docs/ai/rules/financial-domain.md``.

Thresholds live in ``entry_gate_rules.yaml`` — the single source shared with
the registry graph exporter. This module owns evaluation *flow* only:
rule ordering, terminal-on-close, ``closed > caution > open`` precedence,
and the trailing-window fetch for the demote-cooloff rule.

Contract boundaries (see plan "Gate tools and computability graph"):
- Never reads ``graph_*`` tables — the graph describes rules, it never decides.
- No network I/O — anything not in ClickHouse (e.g. earnings date) is a
  caller-supplied parameter; absent means "N/A — data not provided",
  never a silent pass.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .risk_sizing import compute_balance_at_risk

ENTRY_GATE_RULES_PATH = Path(__file__).resolve().parent / "entry_gate_rules.yaml"

# Columns the gate needs from market_regime_signals_daily.
GATE_FIELDS = (
    "effective_source",
    "daily_demote_streak",
    "distribution_count_25d",
    "ftd",
    "breadth_thrust",
    "effective_allocation_tier",
    "ma_stack_score",
)

# Rule 5 needs trailing 25 (incl. as-of); rule 7 needs 5 before as-of.
_WINDOW_FETCH_ROWS = 30

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gte": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
}

_manifest_cache: dict[str, Any] | None = None


def load_entry_gate_rules(path: Path | None = None) -> dict[str, Any]:
    """Parse the rules manifest. Cached for the default path."""
    global _manifest_cache
    if path is None and _manifest_cache is not None:
        return _manifest_cache
    p = path or ENTRY_GATE_RULES_PATH
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rules = sorted(doc.get("rules") or [], key=lambda r: r.get("order", 0))
    manifest = {"version": doc.get("version"), "source_table": doc.get("source_table"), "rules": rules}
    if path is None:
        _manifest_cache = manifest
    return manifest


def _coerce(row_value: Any, manifest_value: Any) -> tuple[Any, Any]:
    if isinstance(manifest_value, (int, float)) and not isinstance(manifest_value, bool):
        try:
            return float(row_value), float(manifest_value)
        except (TypeError, ValueError):
            return row_value, manifest_value
    return str(row_value), str(manifest_value)


def _cond_holds(row: dict[str, Any], cond: dict[str, Any]) -> bool:
    metric = cond["metric"]
    if metric not in row or row[metric] is None:
        return False
    op = _OPS[cond["op"]]
    a, b = _coerce(row[metric], cond["value"])
    return bool(op(a, b))


def _lookback_window(rows: list[dict[str, Any]], lb: dict[str, Any]) -> list[dict[str, Any]]:
    n = int(lb["window_sessions"])
    if lb.get("include_asof"):
        return rows[-n:]
    return rows[:-1][-n:]


def _lookback_hit(rows: list[dict[str, Any]], lb: dict[str, Any]) -> bool:
    """Evaluate lookback modes: ``any_row`` (OR over rows, AND over conds) or
    ``none_row`` (hit when no row matches ANY cond — OR across conds)."""
    window = _lookback_window(rows, lb)
    if "none_row" in lb:
        conds = lb["none_row"] or []
        any_match = any(any(_cond_holds(r, c) for c in conds) for r in window)
        return not any_match
    conds = lb.get("any_row") or []
    return any(all(_cond_holds(r, c) for c in conds) for r in window)


def evaluate_entry_gate_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure evaluation over trailing regime rows (ascending by date).

    ``rows[-1]`` is the as-of row; earlier rows feed lookback rules only.
    """
    if not rows:
        return {"error": "no regime rows at or before as_of_date", "code": "regime_row_missing"}
    manifest = manifest or load_entry_gate_rules()
    current = rows[-1]

    missing = [k for k in GATE_FIELDS if k not in current or current[k] is None]
    if missing:
        return {
            "error": f"as-of regime row missing required gate fields: {', '.join(missing)}",
            "code": "regime_row_incomplete",
            "missing_fields": missing,
            "row_date": str(current.get("date")),
        }

    hit_rules: list[str] = []
    caution_rules: list[str] = []
    constraints: dict[str, Any] | None = None
    reason = ""

    for rule in manifest["rules"]:
        applies_when = rule.get("applies_when")
        if applies_when:
            conds = applies_when if isinstance(applies_when, list) else [applies_when]
            if not all(_cond_holds(current, c) for c in conds):
                continue

        if "lookback" in rule:
            hit = _lookback_hit(rows, rule["lookback"])
        else:
            hit = all(_cond_holds(current, c) for c in rule.get("all") or [])
        if not hit:
            continue

        if rule["outcome"] == "closed":
            hit_rules.append(rule["id"])
            if not reason:
                reason = rule.get("summary") or rule["id"]
            if rule.get("terminal", True):
                break
        elif rule["outcome"] == "caution":
            caution_rules.append(rule["id"])
            if constraints is None:
                constraints = rule.get("constraints") or {}

    if hit_rules:
        gate = "closed"
    elif caution_rules:
        gate = "caution"
        reason = reason or "elevated caution — see constraints"
    else:
        gate = "open"
        reason = "no entry gate rule hit — gate open"

    lookback_demote_dates = [
        str(r.get("date"))
        for r in rows[:-1][-5:]
        if str(r.get("effective_source")) == "daily_demote"
    ]
    fields = {k: current.get(k) for k in GATE_FIELDS}
    fields["lookback_demote_dates"] = lookback_demote_dates
    return {
        "gate": gate,
        "hit_rules": hit_rules,
        "caution_rules": caution_rules,
        "constraints": constraints if gate == "caution" else None,
        "reason": reason,
        "fields": fields,
        "row_date": str(current.get("date")),
        "rules_version": manifest.get("version"),
    }


def fetch_regime_window(client: Any, *, as_of_date: str) -> list[dict[str, Any]]:
    """Trailing regime rows ending at the latest session <= as_of_date, ascending."""
    d = (as_of_date or "").strip()[:10]
    if not d:
        raise ValueError("as_of_date is required (YYYY-MM-DD)")
    result = client.query(
        f"""
        SELECT date, {", ".join(GATE_FIELDS)}
        FROM market_regime_signals_daily FINAL
        WHERE date <= toDate(%(d)s)
        ORDER BY date DESC
        LIMIT {_WINDOW_FETCH_ROWS}
        """,
        parameters={"d": d},
    )
    rows = [dict(zip(result.column_names, r)) for r in result.result_rows]
    rows.reverse()
    return rows


def evaluate_entry_gate(client: Any, *, as_of_date: str) -> dict[str, Any]:
    """HARD entry gate: financial-domain Entry Gate Rules from the manifest."""
    rows = fetch_regime_window(client, as_of_date=as_of_date)
    out = evaluate_entry_gate_rows(rows)
    out["as_of_date"] = (as_of_date or "").strip()[:10]
    out["source_table"] = "market_regime_signals_daily"
    return out


# ---------------------------------------------------------------------------
# Gate 2.5b — position management
# ---------------------------------------------------------------------------

EARNINGS_WINDOW_DAYS = {"new": 21, "add": 14}
SLOT_CAP_FRACTION = 0.67
SLOT_CAP_MAX_SWINGS = 3
NA_NOT_PROVIDED = "N/A — data not provided"


def _parse_date(value: str | None) -> _date | None:
    if not value:
        return None
    return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def evaluate_position_management(
    client: Any,
    *,
    ticker: str,
    entry: float,
    stop: float,
    targets: list[float],
    as_of_date: str | None = None,
    action: str = "new",
    earnings_date: str | None = None,
    no_average_down: bool | None = None,
    exit_plan: str | None = None,
    gate_result: dict[str, Any] | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Gate 2.5b pass/fail table (position-management.yaml thresholds).

    ``earnings_date`` is caller-supplied only (no network calls in gate
    tools); absent -> that check reports N/A, never a silent pass.
    """
    sym = (ticker or "").strip().upper()
    act = (action or "new").strip().lower()
    if act not in EARNINGS_WINDOW_DAYS:
        raise ValueError(f"action must be one of {sorted(EARNINGS_WINDOW_DAYS)}")
    checks: list[dict[str, str]] = []

    # R:R >= 3:1 vs R1 (nearest target above entry) — position-management.yaml.
    risk = float(entry) - float(stop)
    if risk <= 0:
        checks.append(_check("rr_3to1", "fail", f"stop {stop} not below entry {entry}"))
    elif not targets:
        checks.append(_check("rr_3to1", "na", "no targets provided"))
    else:
        above = sorted(float(t) for t in targets if float(t) > float(entry))
        if not above:
            checks.append(_check("rr_3to1", "fail", "no target above entry (R1 undefined)"))
        else:
            reward = above[0] - float(entry)
            rr = reward / risk
            status = "pass" if rr >= 3.0 else "fail"
            checks.append(
                _check(
                    "rr_3to1",
                    status,
                    f"R:R {rr:.2f}:1 to R1={above[0]:.2f} (risk {risk:.2f}, reward {reward:.2f})",
                )
            )

    # BAR <= budget (balance_at_risk_cap) — existing helper.
    bar = compute_balance_at_risk(client, account_id=account_id)
    if "error" in bar:
        checks.append(_check("bar_budget", "na", f"BAR unavailable: {bar['error']}"))
        open_swings: int | None = None
    else:
        status = "fail" if bar.get("over_budget") else "pass"
        approx = " (all stops inferred — approximate)" if bar.get("approximate") else ""
        checks.append(
            _check(
                "bar_budget",
                status,
                f"total BAR {bar.get('total_bar_pct', 0):.2%} vs budget {bar.get('bar_budget_pct', 0):.0%}{approx}",
            )
        )
        open_swings = len(bar.get("positions") or [])

    # Earnings window: new -> >3wk (Gate 2), add -> >2wk (earnings_discipline).
    window_days = EARNINGS_WINDOW_DAYS[act]
    ref = _parse_date(as_of_date) or _date.today()
    edate = _parse_date(earnings_date)
    if edate is None:
        checks.append(_check("earnings_window", "na", NA_NOT_PROVIDED))
    else:
        days_until = (edate - ref).days
        if 0 <= days_until <= window_days:
            checks.append(
                _check("earnings_window", "fail", f"earnings {edate} in {days_until}d (<= {window_days}d for {act})")
            )
        else:
            checks.append(_check("earnings_window", "pass", f"earnings {edate} is {days_until}d out (> {window_days}d)"))

    # Regime slot cap (regime_swing_slot_cap): applies at fraction <= 0.67.
    regime_row = None
    if as_of_date:
        rows = fetch_regime_window(client, as_of_date=as_of_date)
        regime_row = rows[-1] if rows else None
    else:
        result = client.query(
            "SELECT date, effective_allocation_fraction FROM market_regime_signals_daily FINAL "
            "ORDER BY date DESC LIMIT 1"
        )
        if result.result_rows:
            regime_row = dict(zip(result.column_names, result.result_rows[0]))
    fraction = None
    if regime_row is not None:
        fraction = regime_row.get("effective_allocation_fraction")
        if fraction is None and regime_row.get("effective_allocation_tier") is not None:
            fraction = float(regime_row["effective_allocation_tier"]) / 100.0
    if fraction is None:
        checks.append(_check("regime_slots", "na", "regime row unavailable"))
    elif float(fraction) > SLOT_CAP_FRACTION:
        checks.append(_check("regime_slots", "pass", f"regime fraction {float(fraction):.2f} > {SLOT_CAP_FRACTION} — cap not active"))
    elif open_swings is None:
        checks.append(_check("regime_slots", "na", "open swing count unavailable (BAR failed)"))
    else:
        projected = open_swings + (1 if act == "new" else 0)
        status = "pass" if projected <= SLOT_CAP_MAX_SWINGS else "fail"
        checks.append(
            _check(
                "regime_slots",
                status,
                f"{open_swings} open swings (+{1 if act == 'new' else 0} {act}) vs cap {SLOT_CAP_MAX_SWINGS} "
                f"at fraction {float(fraction):.2f}; reminder: max 1 new Tier-1 per week",
            )
        )

    # No average-down / exit plan — pass-through; tool validates presence only.
    if no_average_down is None:
        checks.append(_check("no_average_down", "na", NA_NOT_PROVIDED))
    else:
        checks.append(
            _check(
                "no_average_down",
                "pass" if no_average_down else "fail",
                "plan does not add to a loser" if no_average_down else "plan averages down",
            )
        )
    if exit_plan is None or not str(exit_plan).strip():
        checks.append(_check("exit_plan", "na", NA_NOT_PROVIDED))
    else:
        checks.append(_check("exit_plan", "pass", str(exit_plan).strip()))

    # Entry-gate caution constraints passthrough (size multiplier).
    size_multiplier = None
    if gate_result and gate_result.get("gate") == "caution":
        size_multiplier = (gate_result.get("constraints") or {}).get("size_multiplier")

    statuses = [c["status"] for c in checks]
    overall = "fail" if "fail" in statuses else ("review" if "na" in statuses else "pass")
    return {
        "ticker": sym,
        "action": act,
        "as_of_date": (as_of_date or "").strip()[:10] or str(ref),
        "entry": float(entry),
        "stop": float(stop),
        "targets": [float(t) for t in targets],
        "checks": checks,
        "overall": overall,
        "size_multiplier": size_multiplier,
        "note": "Gate 2.5b — thresholds from docs/ai/strategies/position-management.yaml",
    }
