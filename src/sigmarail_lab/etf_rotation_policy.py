"""SELECT-driven ETF rotation policy: map regime features → VUG/VTV/SGOV weights.

VUG-DD epoch: ``mode: cascade_weights`` reads ``cascade_weights`` (preferred) or
``cascade_sleeve`` from regime rows. Soft gate: Calmar > VUG and return ≥ 0.90×VUG.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

DEFAULT_PARAMS: dict[str, Any] = {
    "demote_streak_cut": 3,
    "dist_25d_cut": 8,
    "equity_budget_when_demote": 0.5,
    "equity_budget_when_dist": 0.2,
    "equity_budget_when_clamp": 0.0,
    "growth_share_breaks": [0.25, 0.60, 0.99],
    "growth_share_of_equity": [0.33, 0.67, 1.0],
}

# Incremental VUG ladder (not binary all-in/all-out).
# FULL → SOFT (precrash SMA50) → CRASH_SOFT / CRASH_HARD (tiered 200d).
CASCADE_DEFAULT_PARAMS: dict[str, Any] = {
    "mode": "cascade_weights",
    "rel_mom_lookback": "3m",
    "persist_exit": 2,
    "persist_reentry": 2,
    "require_spy_confirm": True,
    "from_cash_prefer": "vug_only",
    "defensive_enabled": False,
    "precrash_enabled": True,
    "emergency_rebalance": True,
    # Ladder: FULL → soft (70/30) → hard → crash soft/hard
    "w_full": {"VUG": 1.0, "VTV": 0.0, "SGOV": 0.0},
    "w_soft": {"VUG": 0.7, "VTV": 0.0, "SGOV": 0.3},  # pre-crash trim
    "w_hard": {"VUG": 0.4, "VTV": 0.3, "SGOV": 0.3},
    "w_crash": {"VUG": 0.0, "VTV": 0.0, "SGOV": 1.0},  # legacy alias → hard
    "w_crash_soft": {"VUG": 0.5, "VTV": 0.0, "SGOV": 0.5},
    "w_crash_hard": {"VUG": 0.25, "VTV": 0.0, "SGOV": 0.75},
    # Oversold residual (close/sma50 - 1): more negative → faster / larger reentry
    "oversold_soft": -0.03,
    "oversold_hard": -0.08,
    "aggressive_reentry": True,
    "enhance": "none",
    # ttl_fuse: force FULL after N days in CRASH_HARD if no new VUG low since entry.
    "ttl_days": 40,
    # depth_scale: [depth_under_sma200_threshold, vug_weight] bands, ascending.
    "depth_bands": [[0.03, 0.80], [0.08, 0.60], [0.15, 0.45], [1.0, 0.35]],
    # dd_ratchet: VUG weight added to w_crash_hard["VUG"] per recovery-third stage.
    "ratchet_step": 0.17,
    # vol_clock: reenter FULL from CRASH_HARD if 20d realized vol <= this percentile
    # of trailing vol history (once >=100 observations are available).
    "vol_reenter_pct": 40,
}

BASELINE_HARDCODED_PARAMS: dict[str, Any] = {
    "mode": "legacy_hardcoded",
    "note": "Uses resolve_rotation_state + ALLOCATIONS (demote→VTV).",
}


def equity_budget(row: Mapping[str, Any], params: Mapping[str, Any]) -> float:
    if int(row.get("clamp_risk_off") or 0) == 1:
        return float(params.get("equity_budget_when_clamp", 0.0))
    if int(row.get("distribution_count_25d") or 0) >= int(params.get("dist_25d_cut", 8)):
        return float(params.get("equity_budget_when_dist", 0.2))
    if int(row.get("daily_demote_streak") or 0) >= int(params.get("demote_streak_cut", 3)):
        return float(params.get("equity_budget_when_demote", 0.5))
    return 1.0


def growth_share_of_equity(row: Mapping[str, Any], params: Mapping[str, Any]) -> float:
    breaks = list(params.get("growth_share_breaks") or [0.25, 0.60, 0.99])
    shares = list(params.get("growth_share_of_equity") or [0.33, 0.67, 1.0])
    w = float(row.get("weekly_allocation_fraction") or 0.0)
    if w >= float(breaks[2]):
        return float(shares[2])
    if w >= float(breaks[1]):
        return float(shares[1])
    if w >= float(breaks[0]):
        return float(shares[0])
    return 0.0


def _norm_weights(w: Mapping[str, float]) -> dict[str, float]:
    vug = float(w.get("VUG", 0))
    vtv = float(w.get("VTV", 0))
    sgov = float(w.get("SGOV", 0))
    s = vug + vtv + sgov
    if s <= 0:
        return {"VUG": 0.0, "VTV": 0.0, "SGOV": 1.0}
    return {"VUG": vug / s, "VTV": vtv / s, "SGOV": sgov / s}


def weights_from_policy(row: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, float]:
    if params.get("mode") == "legacy_hardcoded":
        from sigmarail_lab.etf_rotation_state import resolve_rotation_state, weights_for_state

        return weights_for_state(resolve_rotation_state(row))

    if params.get("mode") == "fixed_weights":
        return _norm_weights(params.get("weights") or {"VUG": 1.0, "VTV": 0.0, "SGOV": 0.0})

    if params.get("mode") == "cascade_weights":
        if isinstance(row.get("cascade_weights"), dict):
            return _norm_weights(row["cascade_weights"])
        sleeve = str(row.get("cascade_sleeve") or "VUG").upper()
        if sleeve == "VTV":
            return {"VUG": 0.0, "VTV": 1.0, "SGOV": 0.0}
        if sleeve == "SGOV":
            return {"VUG": 0.0, "VTV": 0.0, "SGOV": 1.0}
        if sleeve == "SOFT":
            return _norm_weights(params.get("w_soft") or CASCADE_DEFAULT_PARAMS["w_soft"])
        if sleeve == "HARD":
            return _norm_weights(params.get("w_hard") or CASCADE_DEFAULT_PARAMS["w_hard"])
        if sleeve == "CRASH_SOFT":
            return _norm_weights(
                params.get("w_crash_soft")
                or params.get("w_crash")
                or CASCADE_DEFAULT_PARAMS["w_crash_soft"]
            )
        if sleeve in ("CRASH_HARD", "CRASH"):
            return _norm_weights(
                params.get("w_crash_hard")
                or params.get("w_crash")
                or CASCADE_DEFAULT_PARAMS["w_crash_hard"]
            )
        return {"VUG": 1.0, "VTV": 0.0, "SGOV": 0.0}

    budget = max(0.0, min(1.0, equity_budget(row, params)))
    gshare = max(0.0, min(1.0, growth_share_of_equity(row, params)))
    return _norm_weights(
        {"VUG": budget * gshare, "VTV": budget * (1.0 - gshare), "SGOV": 1.0 - budget}
    )


def is_static_bh_disqualified(params: Mapping[str, Any]) -> bool:
    return params.get("mode") == "fixed_weights"


def params_to_json(params: Mapping[str, Any]) -> str:
    return json.dumps(dict(params), sort_keys=True)
