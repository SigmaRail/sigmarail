"""Named strategy presets, expressed as PipelineDocument JSON.

Presets are data, not code — the compiler turns each into a VeraLabV1 spec.
"""

from __future__ import annotations

from copy import deepcopy

from .pipeline import (
    PipelineDocument,
    PolicyRule,
    PortfolioDocument,
    SlotExpr,
    champion_default_bindings,
    champion_default_policy_rules,
)
from .setup_recipes import (
    CHAMPION_SETUP_OR as _MINERVINI_SETUP_GROUP,
    POCKET_PIVOT as _MINERVINI_POCKET_PIVOT_SETUP,
    VOLUME_THRUST_BREAKOUT as _MINERVINI_BREAKOUT_SETUP,
    VCP_COMPRESSION as _MINERVINI_VCP_SETUP,
)

# --- Presets ------------------------------------------------------------

_MOMENTUM = {
    "strategy_name": "Momentum",
    "stages": [
        {
            "name": "Liquidity Filter",
            "mode": "filter",
            "filters": [
                {"op": "gte", "left": "close", "right": 10},
                {"op": "gte", "left": "volume", "right": 500000},
                {"op": "gte", "left": "rs_rating", "right": 70},
            ],
            "max_candidates": 101,
        },
        {
            "name": "Rank",
            "mode": "score",
            "factors": [{"name": "momentum", "weight": 1.0}],
            "selection": {"method": "top_n", "n": 10},
        },
    ],
}

_VALUE_MOMENTUM = {
    "strategy_name": "Value Momentum",
    "stages": [
        {
            "name": "Liquidity Filter",
            "mode": "filter",
            "filters": [
                {"op": "gte", "left": "close", "right": 10},
                {"op": "gte", "left": "volume", "right": 500000},
                {"op": "gte", "left": "rs_rating", "right": 60},
            ],
            "max_candidates": 101,
        },
        {
            "name": "Multi-Factor Rank",
            "mode": "score",
            "factors": [
                {"name": "momentum", "weight": 0.40},
                {"name": "value", "weight": 0.20},
                {"name": "roe", "weight": 0.20},
                {"name": "trend_1y", "weight": 0.20},
            ],
            "selection": {"method": "top_n", "n": 10},
        },
    ],
}

# Book MTT (8-point) as primitives — no minervini_tt_* / sma200d_rising_30d flags.
# SMA200 rising ~1 month is sma200d > sma200_lag_30d. Liquidity lives on hygiene.
_MINERVINI_TREND_TEMPLATE = {
    "logic": "and",
    "conditions": [
        {"op": "gt", "left": "close", "right": "sma50d", "right_kind": "col"},
        {"op": "gt", "left": "close", "right": "sma150d", "right_kind": "col"},
        {"op": "gt", "left": "close", "right": "sma200d", "right_kind": "col"},
        {"op": "gt", "left": "sma50d", "right": "sma150d", "right_kind": "col"},
        {"op": "gt", "left": "sma50d", "right": "sma200d", "right_kind": "col"},
        {"op": "gt", "left": "sma150d", "right": "sma200d", "right_kind": "col"},
        {"op": "gt", "left": "sma200d", "right": "sma200_lag_30d", "right_kind": "col"},
        {"op": "gte", "left": "rs_rating", "right": 70},
        {
            "op": "gte",
            "left": "close",
            "right": {
                "type": "formula",
                "op": "*",
                "args": [
                    {"type": "col", "name": "high_52w"},
                    {"type": "lit", "value": 0.75},
                ],
            },
            "right_kind": "formula",
        },
        {
            "op": "gte",
            "left": "close",
            "right": {
                "type": "formula",
                "op": "*",
                "args": [
                    {"type": "col", "name": "low_52w"},
                    {"type": "lit", "value": 1.3},
                ],
            },
            "right_kind": "formula",
        },
    ],
}

_MINERVINI_FUNDAMENTAL_GROWTH = {
    "logic": "and",
    "conditions": [
        {"op": "gte", "left": "mrt_roe", "right": 0.15},
        {"op": "gte", "left": "mrt_netmargin", "right": 0.05},
        # Top-decile ROE within its industry — measured 2026-09-30 as the strongest leadership
        # factor on the trend+growth base (+2.24% med / 64.3% up vs +0.79% / 55.1%). See
        # docs/plans/vera-price-action-entry-plan.md Workstream G.
        {"op": "gte", "left": "mrt_roe_industry_rank", "right": 90},
    ],
}

_MINERVINI_PULLBACK_SETUP = {
    "logic": "or",
    "conditions": [
        {"op": "gte", "left": "pocket_pivot_score", "right": 30},
        {
            "logic": "and",
            "conditions": [
                {"op": "eq", "left": "pullback_ready", "right": 1},
                {"op": "eq", "left": "three_up_days", "right": 1},
            ],
        },
    ],
}

# ChartMill Screen 1–4 + Code 33 leaves (boolean AST, not rank/top_k).
# ChartMill Screen 5/6 (1∧3 / 2∧4 convenience presets) are omitted.
_SCREEN_1_YEARLY_EPS = [
    {"op": "gte", "left": "ary_eps_growth_3y_cagr", "right": 0.15},
    {"op": "eq", "left": "ary_eps_acceleration_fy", "right": 1},
]
_SCREEN_2_QUARTERLY_EPS = [
    {"op": "gte", "left": "arq_eps_growth_qoq", "right": 0.25},
    {"op": "eq", "left": "arq_eps_acceleration_q2", "right": 1},
]
_SCREEN_3_YEARLY_REVENUE = [
    {"op": "gte", "left": "ary_revenue_growth_3y_cagr", "right": 0.15},
    {"op": "eq", "left": "ary_revenue_acceleration_fy", "right": 1},
]
_SCREEN_4_QUARTERLY_REVENUE = [
    {"op": "gte", "left": "arq_revenue_growth_qoq", "right": 0.25},
    {"op": "eq", "left": "arq_revenue_acceleration_q2", "right": 1},
]
# Code 33 is Alpha gate.where only — no 0.25 YoY floor.
_MINERVINI_CODE_33 = {
    "logic": "and",
    "conditions": [
        {"op": "eq", "left": "arq_eps_acceleration_q3", "right": 1},
        {"op": "eq", "left": "arq_revenue_acceleration_q3", "right": 1},
        {"op": "eq", "left": "arq_pmi_up_q3", "right": 1},
    ],
}

_MINERVINI_MEMBERSHIP = {
    "logic": "and",
    "name": "membership",
    "conditions": deepcopy(_MINERVINI_TREND_TEMPLATE)["conditions"],
}

# ChartMill Part 1: Universe = hygiene AND named membership (book MTT).
# Code 33 is not a universe sibling.
_MINERVINI_HYGIENE = {
    "logic": "and",
    "name": "hygiene",
    "conditions": [
        {"op": "gte", "left": "close", "right": 5.0},
        {"op": "gte", "left": "avg_vol_50d", "right": 100000},
        {"op": "neq", "left": "industry", "right": "Biotechnology", "right_kind": "lit"},
        {
            "logic": "or",
            "conditions": [
                {"op": "eq", "left": "exchange", "right": "NYSE", "right_kind": "lit"},
                {"op": "eq", "left": "exchange", "right": "NASDAQ", "right_kind": "lit"},
            ],
        },
        deepcopy(_MINERVINI_MEMBERSHIP),
    ],
}

_MINERVINI_SEPA = {
    "strategy_name": "Minervini SEPA",
    "gate_combine": "count",
    # Admit at 1+ screen or RS >= 85 so leading momentum names are captured
    "min_screens": 1,
    "min_rs_rating": 85.0,
    "rank_by_rs": True,
    "sizing": {
        "policy": "risk_budgeted",
        "risk_per_trade_pct": 0.008,
        "max_weight": 0.25,
        "honor_insight_confidence": True,
        "allow_adds_on_invested": True,
        "default_stop_loss_pct": 0.05,
        "min_regime_fraction": 0.15,
    },
    "execution": {
        "type": "market_order",
        "fill_session": "moo",
    },
    "universe": {
        "source": "screener",
        "limit_per_day": 2000,
        "screen": [deepcopy(_MINERVINI_HYGIENE)],
    },
    "stages": [
        {
            "id": "screen_1",
            "name": "Screen 1 Yearly EPS",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": True,
            "require_flag": "in_membership",
            "documentation": {
                "purpose": "Yearly EPS growth + acceleration (ChartMill Screen 1).",
            },
            "filters": [{"logic": "and", "conditions": deepcopy(_SCREEN_1_YEARLY_EPS)}],
        },
        {
            "id": "screen_2",
            "name": "Screen 2 Quarterly EPS",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": True,
            "require_flag": "in_membership",
            "documentation": {
                "purpose": "Quarterly EPS growth + acceleration (ChartMill Screen 2).",
            },
            "filters": [{"logic": "and", "conditions": deepcopy(_SCREEN_2_QUARTERLY_EPS)}],
        },
        {
            "id": "screen_3",
            "name": "Screen 3 Yearly Revenue",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": True,
            "require_flag": "in_membership",
            "documentation": {
                "purpose": "Yearly revenue growth + acceleration (ChartMill Screen 3).",
            },
            "filters": [{"logic": "and", "conditions": deepcopy(_SCREEN_3_YEARLY_REVENUE)}],
        },
        {
            "id": "screen_4",
            "name": "Screen 4 Quarterly Revenue",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": True,
            "require_flag": "in_membership",
            "documentation": {
                "purpose": "Quarterly revenue growth + acceleration (ChartMill Screen 4).",
            },
            "filters": [{"logic": "and", "conditions": deepcopy(_SCREEN_4_QUARTERLY_REVENUE)}],
        },
        {
            "id": "code_33",
            "name": "Code 33",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": True,
            "require_flag": "in_membership",
            "documentation": {
                "purpose": "Code 33 acceleration flags; counted in screens_hit (count_as_signal).",
            },
            "filters": [deepcopy(_MINERVINI_CODE_33)],
        },
        # Authored hit: gate with expression payload (Σ bool gates).
        {
            "id": "screens_hit",
            "name": "Screens hit",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": "Count of Screen 1–4 + Code 33 bools; Insight ✓ → primary ORDER BY.",
            },
            "computed_expr": {
                "type": "formula",
                "op": "+",
                "args": [
                    {
                        "type": "formula",
                        "op": "+",
                        "args": [
                            {
                                "type": "formula",
                                "op": "+",
                                "args": [
                                    {
                                        "type": "formula",
                                        "op": "+",
                                        "args": [
                                            {"type": "col", "name": "screen_1"},
                                            {"type": "col", "name": "screen_2"},
                                        ],
                                    },
                                    {"type": "col", "name": "screen_3"},
                                ],
                            },
                            {"type": "col", "name": "screen_4"},
                        ],
                    },
                    {"type": "col", "name": "code_33"},
                ],
            },
            "filters": [],
            "factors": [],
        },
        # Field measure so rs_rating can appear in Insights ORDER BY (Insight ✓ / alpha_rank).
        {
            "id": "rs_rating",
            "name": "RS Rating",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": (
                    "L7 rs_rating as a field measure — required for rank tie in ORDER BY "
                    "(not bare select harvest)."
                ),
            },
            "computed_expr": {"type": "col", "name": "rs_rating"},
            "filters": [],
            "factors": [],
        },
        # Insight property Measures (SQL math → row cols; Insights bind aliases).
        {
            "id": "insight_dir",
            "name": "Insight Direction",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": (
                    "RS rank gap vs 21d SMA: rs_rating - sma21d_rs_rating "
                    "(sign → Up / Down / Flat; bound as alpha_direction)."
                ),
            },
            "computed_expr": {
                "type": "formula",
                "op": "-",
                "args": [
                    {"type": "col", "name": "rs_rating"},
                    {"type": "col", "name": "sma21d_rs_rating"},
                ],
            },
            "filters": [],
            "factors": [],
        },
        {
            "id": "mag_thrust",
            "name": "Magnitude thrust (RS)",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": (
                    "Signed RS gap size (rs_rating - sma21d_rs_rating)/100; "
                    "bound as alpha_magnitude (Alpha clamps ±0.25)."
                ),
            },
            "computed_expr": {
                "type": "formula",
                "op": "/",
                "args": [
                    {
                        "type": "formula",
                        "op": "-",
                        "args": [
                            {"type": "col", "name": "rs_rating"},
                            {"type": "col", "name": "sma21d_rs_rating"},
                        ],
                    },
                    {"type": "lit", "value": 100},
                ],
            },
            "filters": [],
            "factors": [],
        },
        {
            "id": "w_conviction",
            "name": "Weight conviction",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": "screens_hit/5 portfolio-weight hint; bound as alpha_weight.",
            },
            "computed_expr": {
                "type": "formula",
                "op": "/",
                "args": [
                    {"type": "col", "name": "screens_hit"},
                    {"type": "lit", "value": 5},
                ],
            },
            "filters": [],
            "factors": [],
        },
        {
            "id": "conf_scale",
            "name": "Confidence scale",
            "mode": "score",
            "as_gate": True,
            "count_as_signal": False,
            "documentation": {
                "purpose": "screens_hit/5 signal quality; bound as alpha_confidence.",
            },
            "computed_expr": {
                "type": "formula",
                "op": "/",
                "args": [
                    {"type": "col", "name": "screens_hit"},
                    {"type": "lit", "value": 5},
                ],
            },
            "filters": [],
            "factors": [],
        },
        {
            "id": "setup_pass",
            "name": "Setup Group",
            "mode": "signal",
            "count_as_signal": False,
            "documentation": {
                "purpose": (
                    "Empty by default — add setup recipes (breakout / VCP / pocket) in Studio "
                    "Measures or via compose_minervini_sepa_with_setup()."
                ),
            },
            "filters": [],
            "max_candidates": 100,
        },
        # Optional blend rank (as_gate=false). Count shortlist uses screens_hit; this
        # survives decompile for field_weights / probe — not the primary ORDER BY.
        {
            "name": "VCP Ranking",
            "mode": "score",
            "as_gate": False,
            "count_as_signal": False,
            "factors": [
                {"name": "momentum", "weight": 0.30},
                {"name": "technical", "weight": 0.25},
                {"name": "setup", "weight": 0.20},
                {"name": "accumulation", "weight": 0.15},
                {"name": "growth_momentum", "weight": 0.10},
            ],
            "selection": {"method": "top_n", "n": 50},
        },
        {
            "name": "Entry Signal",
            "mode": "signal",
            "entry_triggers": [
                {"type": "pivot_breakout", "lookback_days": 5, "volume_multiplier": 1.2}
            ],
            "stop_loss": {
                "type": "atr",
                "multiplier": 2.0,
                "initial_risk_pct": 0.005,
                "max_stop_loss_pct": 0.05,
            },
            "stop_cooldown_days": 10,
            "max_positions": 10,
        },
        {
            "name": "Progressive Exposure",
            "mode": "pyramid",
            # Require ~1.5R cushion at Dist=5% before adding (reduces pyramid-into-gap).
            "add_trigger_pct": 0.08,
            "phases": [
                {"name": "test", "size_pct": 0.50},
                {"name": "add", "size_pct": 0.25},
                {"name": "full", "size_pct": 0.25},
            ],
        },
        {
            "name": "Sell Into Strength",
            "mode": "exit",
            "tranches": [
                {"trigger_r": 2.5, "sell_pct": 0.20},
                {"trigger_r": 4.5, "sell_pct": 0.33},
                {"trigger_r": 8.0, "sell_pct": 0.33},
            ],
            "max_hold_days": 63,
            "trailing_stop_pct": 0.15,
            "atr_stop_multiplier": 2.0,
            "max_stop_loss_pct": 0.05,
            "use_atr_stops": True,
            "breakeven_time_stop_days": 10,
            "max_single_weight": 0.20,
            "breakeven_r_trigger": 1.5,
        },
    ],
    "risk": {
        "circuit_breaker": {"drawdown": 0.10, "pause_days": 20},
        # Skip time-stop via bindings.risk_skip_time_stop (SlotExpr) only — no legacy sugar.
        "regime_gate": {
            "source": "regime_signals_canonical",
            "threshold": 0.50,
            "signal_weights": {
                "s_ma200_macro": 0.40,
                "s_breadth200": 0.35,
                "s_breadth50": 0.25,
            },
            "confirm_on_days": 3,
            "confirm_off_days": 1,
            "missing_action": "block",
            "uses": ["scale_exposure", "skip_pyramid_adds", "block_new_longs"],
        },
        "max_positions": 10,
    },
    "bindings": champion_default_bindings(
        min_screens=1, min_rs_rating=85.0, rank_by_rs=True, include_setup=False
    ).model_dump(mode="python"),
    "policy_rules": [
        r.model_dump(mode="python")
        for r in champion_default_policy_rules(
            min_screens=1, min_rs_rating=85.0, rank_by_rs=True, include_setup=False
        )
    ],
}

_MINERVINI_SEPA_EPS_BEAT = deepcopy(_MINERVINI_SEPA)
_MINERVINI_SEPA_EPS_BEAT["strategy_name"] = "Minervini SEPA EPS Beat"
_MINERVINI_SEPA_EPS_BEAT["stages"] = list(_MINERVINI_SEPA_EPS_BEAT["stages"])
_MINERVINI_SEPA_EPS_BEAT["stages"].insert(
    5,
    {
        "id": "eps_beat",
        "name": "EPS Beat",
        "mode": "score",
        "as_gate": True,
        "count_as_signal": False,
        "require_flag": "in_membership",
        "documentation": {
            "purpose": "Latest EPS surprise at or above 5% (street consensus).",
        },
        "filters": [
            {
                "logic": "and",
                "conditions": [
                    {"op": "gte", "left": "eps_last_surprise_pct", "right": 0.05},
                ],
            }
        ],
    },
)
_MINERVINI_SEPA_EPS_BEAT["policy_rules"] = [
    r.model_dump(mode="python")
    for r in champion_default_policy_rules(min_screens=2, include_setup=False)
] + [
    PolicyRule(
        id="pcm_eps_beat",
        label="EPS beat gate",
        role="pcm_allow_entry",
        slot=SlotExpr(
            kind="bool",
            where={
                "type": "eq",
                "left": {"type": "col", "name": "eps_beat"},
                "right": {"type": "lit", "value": 1},
            },
        ),
    ).model_dump(mode="python"),
]

_MINERVINI_SEPA_EPS_BEAT_OVERRIDE = deepcopy(_MINERVINI_SEPA_EPS_BEAT)
_MINERVINI_SEPA_EPS_BEAT_OVERRIDE["strategy_name"] = "Minervini SEPA EPS Beat + Risk Override"
_MINERVINI_SEPA_EPS_BEAT_OVERRIDE["policy_overrides"] = [
    {
        "id": "eps_beat_size_up",
        "label": "Size up on EPS beat",
        "when": {
            "kind": "bool",
            "where": {
                "type": "eq",
                "left": {"type": "col", "name": "eps_beat"},
                "right": {"type": "lit", "value": 1},
            },
        },
        "set": {"risk_per_trade_pct": 0.01},
    }
]

# Opt-in weighted shortlist: Screen 1 worth 2×; floor still unweighted screens_hit.
_MINERVINI_SEPA_WEIGHTED = deepcopy(_MINERVINI_SEPA)
_MINERVINI_SEPA_WEIGHTED["strategy_name"] = "Minervini SEPA Weighted"
for _st in _MINERVINI_SEPA_WEIGHTED["stages"]:
    _sid = _st.get("id")
    if _sid == "screen_1":
        _st["signal_weight"] = 2.0
    # Weighted combinator still needs count_as_signal gates (unweighted screens_hit
    # stays the authored Σ expression / sum_aliases from those same aliases).
    if _sid in ("screen_1", "screen_2", "screen_3", "screen_4", "code_33"):
        _st["count_as_signal"] = True
_wb = deepcopy(_MINERVINI_SEPA_WEIGHTED.get("bindings") or {})
_wb["alpha_rank"] = ["screens_hit_w", "rs_rating"]
_wb["alpha_rank_directions"] = {"screens_hit_w": "desc", "rs_rating": "desc"}
# Weighted shortlist: still use unweighted conf_scale / w_conviction (screens_hit/5).
_MINERVINI_SEPA_WEIGHTED["bindings"] = _wb
_MINERVINI_SEPA_WEIGHTED["policy_rules"] = [
    r.model_dump(mode="python")
    for r in champion_default_policy_rules(min_screens=2, include_setup=False)
]

_MINERVINI_BREAKOUT = {
    "strategy_name": "Minervini Breakout",
    "stages": [
        {
            "name": "Trend Template",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_TREND_TEMPLATE)],
            "max_candidates": 500,
        },
        {
            "name": "Fundamental Growth",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_FUNDAMENTAL_GROWTH)],
            "max_candidates": 100,
        },
        {
            "name": "Breakout Setup",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_BREAKOUT_SETUP)],
            "max_candidates": 100,
        },
    ],
}

_MINERVINI_PULLBACK = {
    "strategy_name": "Minervini Pullback",
    "stages": [
        {
            "name": "Trend Template",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_TREND_TEMPLATE)],
            "max_candidates": 500,
        },
        {
            "name": "Fundamental Growth",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_FUNDAMENTAL_GROWTH)],
            "max_candidates": 100,
        },
        {
            "name": "Pullback Setup",
            "mode": "filter",
            "filters": [deepcopy(_MINERVINI_PULLBACK_SETUP)],
            "max_candidates": 100,
        },
    ],
}

PRESETS: dict[str, dict] = {
    "momentum": _MOMENTUM,
    "value_momentum": _VALUE_MOMENTUM,
    "minervini_sepa": _MINERVINI_SEPA,
    "minervini_sepa_eps_beat": _MINERVINI_SEPA_EPS_BEAT,
    "minervini_sepa_eps_beat_override": _MINERVINI_SEPA_EPS_BEAT_OVERRIDE,
    "minervini_sepa_weighted": _MINERVINI_SEPA_WEIGHTED,
    "minervini_breakout": _MINERVINI_BREAKOUT,
    "minervini_pullback": _MINERVINI_PULLBACK,
}


def list_presets() -> list[dict]:
    """Presets as a list of {id, name, stages, status, tags, description}."""
    from sigmarail.features.template_catalog import list_templates

    meta = {r["id"]: r for r in list_templates(kind="strategy")}
    out = []
    for preset_id, raw in PRESETS.items():
        info = meta.get(preset_id, {})
        out.append(
            {
                "id": preset_id,
                "name": raw["strategy_name"],
                "stages": [s["mode"] for s in raw["stages"]],
                "description": info.get("description") or "",
                "tags": info.get("tags") or [],
                "status": info.get("status") or "active",
                "screener_template_id": info.get("screener_template_id") or "",
            }
        )
    return out


def get_preset(preset_id: str) -> PipelineDocument:
    """Load a named preset as a validated PipelineDocument."""
    key = (preset_id or "").strip()
    if key not in PRESETS:
        raise ValueError(f"unknown preset {preset_id!r}; known: {sorted(PRESETS)}")
    return PipelineDocument.model_validate(deepcopy(PRESETS[key]))


# --- Portfolio presets (Level 2: legs + allocation) -------------------------

_ALL_WEATHER = {
    "name": "All Weather",
    "legs": [
        {
            "strategy_name": "equities",
            "stages": [],
            "universe": {"source": "manual", "symbols": ["VTI"]},
            "alpha": {"type": "ConstantAlphaModel", "parameters": {}},
        },
        {
            "strategy_name": "long_treasury",
            "stages": [],
            "universe": {"source": "manual", "symbols": ["TLT"]},
            "alpha": {"type": "ConstantAlphaModel", "parameters": {}},
        },
        {
            "strategy_name": "gold",
            "stages": [],
            "universe": {"source": "manual", "symbols": ["GLD"]},
            "alpha": {"type": "ConstantAlphaModel", "parameters": {}},
        },
        {
            "strategy_name": "tips",
            "stages": [],
            "universe": {"source": "manual", "symbols": ["TIP"]},
            "alpha": {"type": "ConstantAlphaModel", "parameters": {}},
        },
    ],
    "allocation": {
        "base": "risk_parity",
        "rebalance": "weekly",
        "regime": {
            "signal": "economic_environment",
            "map": {
                "reflation": {"equities": 0.20, "long_treasury": 0.10, "gold": 0.40, "tips": 0.30},
                "goldilocks": {"equities": 0.45, "long_treasury": 0.20, "gold": 0.10, "tips": 0.25},
                "stagflation": {"equities": 0.10, "long_treasury": 0.15, "gold": 0.45, "tips": 0.30},
                "deflation": {"equities": 0.15, "long_treasury": 0.50, "gold": 0.10, "tips": 0.25},
            },
        },
        "vol_target": {"target_vol": 0.10},
    },
}

PORTFOLIO_PRESETS: dict[str, dict] = {
    "all_weather": _ALL_WEATHER,
}


def list_portfolio_presets() -> list[dict]:
    """Portfolio presets as a list of {id, name, legs} for API/CLI surfaces."""
    return [
        {"id": preset_id, "name": raw["name"], "legs": [leg["strategy_name"] for leg in raw["legs"]]}
        for preset_id, raw in PORTFOLIO_PRESETS.items()
    ]


def get_portfolio_preset(preset_id: str) -> PortfolioDocument:
    """Load a named portfolio preset as a validated PortfolioDocument."""
    key = (preset_id or "").strip()
    if key not in PORTFOLIO_PRESETS:
        raise ValueError(f"unknown portfolio preset {preset_id!r}; known: {sorted(PORTFOLIO_PRESETS)}")
    return PortfolioDocument.model_validate(deepcopy(PORTFOLIO_PRESETS[key]))
