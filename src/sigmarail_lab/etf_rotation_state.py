"""Shared VUG/VTV/SGOV rotation state machine (CSV, ClickHouse, and graph JSON).

Default mapping remains legacy (clamp → demote≥3 → dist≥8 → weekly tiers).
SELECT-driven policies: use ``resolve_rotation_weights`` / ``ETF_ROTATION_POLICY``.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

# Basket tickers (SPY is benchmark-only, not a sleeve).
GROWTH_ETF = "VUG"
DEFENSIVE_ETF = "VTV"
CASH_ETF = "SGOV"
BASKET = (GROWTH_ETF, DEFENSIVE_ETF, CASH_ETF)

ALLOCATIONS: dict[str, dict[str, float]] = {
    "exits_only": {GROWTH_ETF: 0.00, DEFENSIVE_ETF: 0.80, CASH_ETF: 0.20},
    "demote": {GROWTH_ETF: 0.00, DEFENSIVE_ETF: 0.70, CASH_ETF: 0.30},
    "risk_on_100": {GROWTH_ETF: 1.00, DEFENSIVE_ETF: 0.00, CASH_ETF: 0.00},
    "risk_on_67": {GROWTH_ETF: 0.67, DEFENSIVE_ETF: 0.33, CASH_ETF: 0.00},
    "risk_on_33": {GROWTH_ETF: 0.33, DEFENSIVE_ETF: 0.67, CASH_ETF: 0.00},
    "risk_off": {GROWTH_ETF: 0.00, DEFENSIVE_ETF: 0.00, CASH_ETF: 1.00},
}

# CSV / export column contract
REGIME_CSV_COLUMNS = (
    "date",
    "clamp_risk_off",
    "daily_demote_streak",
    "distribution_count_25d",
    "weekly_allocation_fraction",
)

BACKTEST_START = "2023-07-01"
# VUG 6:1 split repaired in sfp/marts (2026-07); window through latest clean session.
BACKTEST_END = "2026-07-20"
INITIAL_CASH = 100_000


def prior_session_as_of(
    available: Mapping[str, Any],
    when: date,
    *,
    max_lookback: int = 10,
) -> str | None:
    """Calendar D-1, then walk back to the latest session date present in ``available``.

    Regime marts are trading-day keyed; Monday WeekStart must not look up Sunday.
    """
    d = when - timedelta(days=1)
    for _ in range(max_lookback):
        key = d.isoformat()
        if key in available:
            return key
        d -= timedelta(days=1)
    return None


def resolve_rotation_state(row: Mapping[str, Any]) -> str:
    """Map a regime row to an allocation state key (legacy hardcoded)."""
    if int(row.get("clamp_risk_off") or 0) == 1:
        return "exits_only"
    if int(row.get("daily_demote_streak") or 0) >= 3:
        return "demote"
    if int(row.get("distribution_count_25d") or 0) >= 8:
        return "exits_only"
    alloc = float(row.get("weekly_allocation_fraction") or 0.0)
    if alloc >= 0.99:
        return "risk_on_100"
    if alloc >= 0.60:
        return "risk_on_67"
    if alloc >= 0.25:
        return "risk_on_33"
    return "risk_off"


def weights_for_state(state: str) -> dict[str, float]:
    return dict(ALLOCATIONS[state])


def load_rotation_policy_params() -> dict[str, Any]:
    """Load policy params from env; empty → legacy mapping."""
    explicit = (os.environ.get("ETF_ROTATION_POLICY") or "").strip().lower()
    path = (os.environ.get("ETF_ROTATION_POLICY_JSON") or "").strip()
    if not path and explicit in ("ralph_winner", "best", "1", "true"):
        cand = Path(__file__).resolve().parents[1] / "results" / "ralph" / "best_policy.json"
        if cand.is_file():
            path = str(cand)
    if not path:
        return {"mode": "legacy_hardcoded"}
    data = json.loads(Path(path).read_text())
    if isinstance(data.get("params"), dict):
        return dict(data["params"])
    return dict(data)


def resolve_rotation_weights(row: Mapping[str, Any]) -> dict[str, float]:
    """Sleeve weights for a regime row (policy-aware)."""
    from sigmarail_lab.etf_rotation_policy import weights_from_policy

    return weights_from_policy(row, load_rotation_policy_params())


def comparison_summary(
    *,
    path: str,
    final_equity: float,
    initial_cash: float = INITIAL_CASH,
    n_state_transitions: int,
    state_day_histogram: Mapping[str, int],
    transitions: list[tuple[str, str]] | None = None,
    max_drawdown: float | None = None,
    trade_count: int | None = None,
) -> dict[str, Any]:
    """Machine-readable summary for cross-path comparison."""
    total_return_pct = (final_equity / initial_cash - 1.0) * 100.0 if initial_cash else 0.0
    out: dict[str, Any] = {
        "path": path,
        "final_equity": round(float(final_equity), 4),
        "total_return_pct": round(total_return_pct, 6),
        "n_state_transitions": int(n_state_transitions),
        "state_day_histogram": {k: int(v) for k, v in sorted(state_day_histogram.items())},
    }
    if transitions is not None:
        out["transitions"] = [{"date": d, "state": s} for d, s in transitions]
    if max_drawdown is not None:
        out["max_drawdown"] = round(float(max_drawdown), 6)
    if trade_count is not None:
        out["trade_count"] = int(trade_count)
    return out
