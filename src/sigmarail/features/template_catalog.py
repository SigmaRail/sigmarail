"""Git-versioned template catalog (C-TEMPLATE-CATALOG-V1).

Two kinds:

- ``screener`` — ``universe_query_v1`` JSON (examples/universe_query_v1/templates)
  plus MCP ``screen_stocks`` presets that have no dedicated JSON file.
- ``strategy`` — ``PipelineDocument`` from ``strategy.presets`` with catalog
  metadata (tags, why/how, status, embedded screener id).

ClickHouse ``vera_templates`` is the user overlay table; this module is the
system catalog. Status ``deprecated`` means keep-but-hide from default pickers;
Phase 2 hard-deletes those ids.
"""

from __future__ import annotations

from typing import Any, Literal

from .screen_preset_ir import list_preset_ir_ids, preset_to_universe_query_v1
from .screen_templates import list_template_ids, load_template_json

Kind = Literal["screener", "strategy"]
Status = Literal["active", "deprecated", "draft"]

_ACTIVE = "active"
_DEPRECATED = "deprecated"

# Short ids used by Studio / MCP that resolve onto a canonical catalog id.
_ALIASES: dict[str, str] = {
    "minervini": "minervini_trend_template",
    "canslim": "canslim_template",
    "fair_value": "fair_value_discount_compounders",
    "kullamagi": "kullamagi_breakout_momentum",
    "weinstein": "weinstein_stage_2_breakout",
    "breakouts": "breakout_quality_setups",
    "swing": "swing_pullback_sma20",
    "bull_flag": "bull_flag_breakouts",
    "squeeze": "volatility_squeeze_breakout",
    "pocket_pivot": "pocket_pivot_high_rs",
    "dividends": "dividend_growth_compounders",
    "komar": "julian_komar_best_winners",
    "julian_komar": "julian_komar_best_winners",
    "komar_growth": "julian_komar_growth_leaders",
}


def _meta(
    title: str,
    *,
    tags: list[str],
    description: str,
    why: str,
    how: str,
    status: Status = _ACTIVE,
    screener_template_id: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "tags": tags,
        "description": description,
        "why": why,
        "how": how,
        "status": status,
        "screener_template_id": screener_template_id,
    }


_SCREENER_META: dict[str, dict[str, Any]] = {
    "minervini_trend_template": _meta(
        "Minervini Trend Template (Standard)",
        tags=["minervini", "trend-template", "stage-2"],
        description="Full SEPA trend template: SMAs stacked, 200d rising, RS ≥ 70, 52w location.",
        why="Primary Stage-2 gate. Most SEPA work should start here, not the 1m/5m forks.",
        how="close>sma150>sma200, sma200 rising 30d, RS≥70, 30% above 52w low, within 25% of 52w high.",
    ),
    "vcp_triad_coiling": _meta(
        "VCP Direct L7 Triad",
        tags=["vcp", "minervini", "coiling"],
        description="ATR compression + volume dry-up + proximity to the 90d high, Stage-2/RS floors.",
        why="Continuous VCP suite is more selective than consolidation-day counts (~98% pass).",
        how="vcp_atr_compression_5d_90d≤0.40 AND vcp_volume_dryup_5d_90d≤0.70 AND vcp_proximity_90d≥0.90.",
    ),
    "setup_quality_leaders": _meta(
        "Setup Quality Leaders",
        tags=["setup-quality", "leaders", "vcp"],
        description="Composite setup_quality_rating ≥ 70 with RS and Stage-2 floors.",
        why="setup_quality already bakes VCP triad + tightness on L2; use it when you want the scored composite.",
        how="rt.setup_quality_rating≥70, rs_rating≥80, is_stage_2_advancing=1.",
    ),
    "pocket_pivot_high_rs": _meta(
        "Pocket Pivot in Strong Market Leaders",
        tags=["pocket-pivot", "leaders"],
        description="Constructive pullback near the 10-day SMA with RS ≥ 75.",
        why="SEPA add/entry on leaders that coiled without breaking the 50-day.",
        how="close within 2–5% of sma10d, above sma50d>sma200d, RS≥75.",
    ),
    "canslim_template": _meta(
        "CANSLIM Leader Filter",
        tags=["canslim", "oneil", "growth"],
        description="O'Neil EPS/sales screens + RS + bull-market gate, excluding AVOID.",
        why="Aligns JSON template with MCP screen_stocks canslim (bull market + classification).",
        how="screen_eps_quarterly/yearly + revenue quarterly, RS≥80, is_bull_market=1, not AVOID.",
    ),
    "julian_komar_best_winners": _meta(
        "Julian Komar Best Winners",
        tags=["komar", "momentum", "growth", "asymmetric"],
        description="Julian Komar's high-momentum leader screener: ≥70% above 52w low, ADR% ≥ 4.5%, price > 50 SMA, 3M/6M performance > 0, high dollar volume.",
        why="Small hunting ground of exceptional growth and momentum stocks with asymmetric upside.",
        how="close >= 1, atr_14_pct >= 4.5, price_70pct_above_52w_low = 1, perf_3m > 0, perf_6m > 0, close > sma50d, sma10d >= sma20d, dollar_volume >= 10M, sorted by perf_3m desc.",
    ),
    "julian_komar_growth_leaders": _meta(
        "Julian Komar Growth Leaders",
        tags=["komar", "growth", "earnings", "momentum"],
        description="Julian Komar momentum setup combined with 20%+ YoY revenue growth and 50%+ YoY EPS growth.",
        why="High-conviction fundamental growth filter on top of the technical momentum base.",
        how="Julian Komar technical criteria PLUS arq_revenue_growth_yoy >= 0.20 AND arq_eps_growth_yoy >= 0.50.",
    ),
    "weinstein_stage_2_breakout": _meta(
        "Stan Weinstein Stage 2 Advancing Breakouts",
        tags=["weinstein", "stage-2"],
        description="Weekly Stage-2 advancing with 50>200 and rising 200.",
        why="Stage-2 is the advancing phase; this is the weekly-stage companion to daily TT.",
        how="stage_code is 2A or 2B, close>sma50>sma200, sma200d_rising_30d, RS≥70.",
    ),
    "leaders": _meta(
        "Leaders",
        tags=["leaders", "rs"],
        description="High RS plus overall_score floor.",
        why="Simple MCP leaders preset used in daily scans.",
        how="rs_rating≥80 AND overall_score≥70.",
    ),
    "high_rs": _meta(
        "High Relative Strength",
        tags=["rs", "leaders"],
        description="RS rating ≥ 90 (aligned with MCP screen_stocks).",
        why="IBD-style RS leadership cut; IR previously used 85 and drifted from MCP.",
        how="rs_rating≥90, closeadj≥5.",
    ),
    "minervini_tt": _meta(
        "Minervini TT (flag)",
        tags=["minervini", "trend-template"],
        description="Binary minervini_tt_all_conditions_full flag.",
        why="Fast MCP equivalent of the standard trend template flag.",
        how="minervini_tt_all_conditions_full=1.",
    ),
    "inst_accumulating": _meta(
        "Institutional accumulating",
        tags=["ownership", "institutions"],
        description="Holder count rising on a complete calendar date.",
        why="Sponsorship confirmation, not a standalone entry.",
        how="inst_calendardate_complete=1 AND inst_shrholders_qoq_delta≥3.",
    ),
    "inst_accumulating_strong": _meta(
        "Institutional accumulating (strong)",
        tags=["ownership", "institutions"],
        description="Large quarter-over-quarter holder increase.",
        why="Stricter sponsorship gate.",
        how="inst_shrholders_qoq_delta≥10.",
    ),
    "insider_cluster_buy": _meta(
        "Insider cluster buy",
        tags=["ownership", "insiders"],
        description="Clustered officer/open-market buys.",
        why="Informed-flow confirmation.",
        how="insider_cluster_buy_flag=1.",
    ),
    "insider_net_buy": _meta(
        "Insider net buy",
        tags=["ownership", "insiders"],
        description="90d net-buy sentiment with at least one officer buy.",
        why="Officer buying is higher quality than generic insider flow.",
        how="insider_sentiment_90d=net_buy AND insider_officer_buys_90d≥1.",
    ),
    "capex_reinvesting": _meta(
        "Capex reinvesting",
        tags=["fundamentals", "capex"],
        description="MRT cash posture = reinvesting with CapEx present.",
        why="Growth companies putting cash back into the business.",
        how="mrt_cash_posture=2.",
    ),
    "capex_disciplined": _meta(
        "Capex disciplined",
        tags=["fundamentals", "capex"],
        description="MRT cash posture = disciplined with FCF/OCF ≥ 0.5.",
        why="Quality compounders that convert operating cash.",
        how="mrt_cash_posture=1 AND mrt_fcf_to_ocf≥0.5.",
    ),
    "minervini_trend_template_5m": _meta(
        "Minervini Trend Template (5-Month / Strict)",
        tags=["minervini", "deprecated"],
        description="Stricter 5-month 200-SMA fork of the standard TT.",
        why="Unlabeled duplicate of the standard template; use minervini_trend_template.",
        how="Same TT stack with a longer 200-SMA rising window.",
        status=_DEPRECATED,
    ),
    "minervini_trend_template_1m": _meta(
        "Minervini Trend Template (1-Month / Early)",
        tags=["minervini", "deprecated"],
        description="Early-turnaround 1-month 200-SMA fork.",
        why="Unlabeled duplicate; keep as a variant only if you explicitly want earlier turns.",
        how="Same TT stack with a shorter 200-SMA rising window.",
        status=_DEPRECATED,
    ),
    "vcp_tight": _meta(
        "VCP tight (has_vcp_setup flag)",
        tags=["vcp", "deprecated"],
        description="Legacy flag screen on has_vcp_setup. Prefer vcp_triad_coiling.",
        why="The old flag was consolidation-days≥5 (~98% pass). Ratings now use the triad, but this id is a duplicate.",
        how="has_vcp_setup=1 AND closeadj>sma50d.",
        status=_DEPRECATED,
    ),
    "minervini_vcp_breakout": _meta(
        "Minervini VCP & Stage 2 Consolidation",
        tags=["vcp", "deprecated"],
        description="Older VCP/stage template; redundant with vcp_triad_coiling + weinstein.",
        why="Consol-day / stage mix without the continuous triad.",
        how="Historic JSON predicates; do not use for new work.",
        status=_DEPRECATED,
    ),
    "piotroski_undervalued_compounders": _meta(
        "Piotroski Quality (misnamed)",
        tags=["value", "deprecated"],
        description="Misnamed value screen; not a Piotroski F-score implementation.",
        why="Name promised F-score quality; predicates do not compute it.",
        how="Do not use; Phase 2 hard-delete.",
        status=_DEPRECATED,
    ),
    "fair_value_discount_compounders": _meta(
        "Fair Value Discount Compounders",
        tags=["valuation", "deprecated"],
        description="Forecast/fair-value compounder screen (not an MCP screen_stocks preset).",
        why="Studio orphaned this as fair_value_discount; keep JSON, drop adapter-only alias.",
        how="Fair-value discount + growth + RS floors in the JSON file.",
        status=_DEPRECATED,
    ),
    "composite_alpha_breakout": _meta(
        "Composite alpha breakout (orphan)",
        tags=["breakout", "deprecated"],
        description="Studio-only IR that treated sma20d as a literal in one predicate.",
        why="Not in MCP screen_stocks; predicates are incorrect.",
        how="Phase 2 hard-delete.",
        status=_DEPRECATED,
    ),
    "insider_selling": _meta(
        "Insider selling",
        tags=["ownership", "insiders"],
        description="Net-sell sentiment or clustered open sells.",
        why="Risk/distribution watch, not an entry screen.",
        how="insider_sentiment_90d=net_sell OR insider_open_sells_90d≥2.",
        status=_DEPRECATED,
    ),
    "capex_mrt_art_disagree": _meta(
        "Capex MRT/ART disagree",
        tags=["fundamentals", "capex", "deprecated"],
        description="Diagnostic disagreement between MRT and ART cash posture.",
        why="Research diagnostic, not a tradable universe.",
        how="art_cash_posture_disagree=1.",
        status=_DEPRECATED,
    ),
}

_JSON_DEFAULT_DEPRECATED = {
    "minervini_momentum_leaders",
    "minervini_fundamental_growth",
    "minervini_high_tight_flag",
    "garp_minervini_forecast_template",
    "breakout_quality_setups",
    "strong_growth_technical_setups",
    "kullamagi_breakout_momentum",
    "unusual_volume_breakouts",
    "swing_pullback_sma20",
    "near_52w_high_breakout",
    "bull_flag_breakouts",
    "affordable_growth_compounders",
    "volatility_squeeze_breakout",
    "high_trend_intensity_volume",
    "dividend_growth_compounders",
}

_STRATEGY_META: dict[str, dict[str, Any]] = {
    "minervini_sepa": _meta(
        "Minervini SEPA",
        tags=["minervini", "sepa", "vcp"],
        description="Screen (NYSE/NASDAQ + $5 + 100k avg vol + book MTT) then ChartMill boolean screens, setup signal, pyramid.",
        why="Canonical Champion / SEPA strategy template. Universe is hygiene AND membership; Code 33 is an Alpha gate.",
        how="Universe ALL = hygiene AND named membership (book MTT). Screens 1–4 + Code 33 are as_gate boolean ASTs (count, min_screens=2). Setup filters are empty by default — apply setup_recipes (champion_setup_or) via Studio Measures or compose_minervini_sepa_with_setup(); then pyramid.",
        screener_template_id="minervini_trend_template",
    ),
    "minervini_sepa_eps_beat": _meta(
        "Minervini SEPA + EPS Beat",
        tags=["minervini", "sepa", "estimates", "policy"],
        description="Champion SEPA plus street EPS surprise gate (eps_beat) assigned to pcm_allow_entry.",
        why="Worked example of signal → policy rule without changing base Champion shortlist math.",
        how="Same as minervini_sepa (setup unseeded); adds as_gate eps_beat on eps_last_surprise_pct≥5% (not count_as_signal); pcm_allow_entry requires eps_beat. Apply champion_setup_or via compose for full SEPA setup_pass.",
        screener_template_id="minervini_trend_template",
    ),
    "minervini_sepa_eps_beat_override": _meta(
        "Minervini SEPA EPS Beat + Override",
        tags=["minervini", "sepa", "estimates", "policy", "override"],
        description="EPS beat gate plus PolicyOverride: when eps_beat → risk_per_trade_pct=1%.",
        why="Worked example of when→set geometry without forking Champion knobs permanently.",
        how="Same as minervini_sepa_eps_beat; policy_overrides size-up to 1% risk when eps_beat=1 (last-wins).",
        screener_template_id="minervini_trend_template",
    ),
    "minervini_sepa_weighted": _meta(
        "Minervini SEPA Weighted",
        tags=["minervini", "sepa", "weighted"],
        description="Champion SEPA with Screen 1 weighted 2× in screens_hit_w; eligibility still on screens_hit.",
        why="Opt-in weighted shortlist without changing base minervini_sepa count rank.",
        how="signal_weight=2 on screen_1; computed screens_hit_w; alpha_rank screens_hit_w→rs_rating; min_screens floor on unweighted screens_hit.",
        screener_template_id="minervini_trend_template",
    ),
    "momentum": _meta(
        "Momentum",
        tags=["momentum", "starter"],
        description="Liquid RS names ranked by momentum.",
        why="Minimal strategy template for compiler/runtime smoke.",
        how="close/volume/RS filter then momentum score top-N.",
        screener_template_id="high_rs",
    ),
    "value_momentum": _meta(
        "Value Momentum",
        tags=["momentum", "value", "deprecated"],
        description="Momentum + value + ROE blend. Redundant with momentum for most work.",
        why="Kept as a starter; prefer one momentum template unless you need the value mix.",
        how="Liquidity filter then 40/20/20/20 factor mix.",
        status=_DEPRECATED,
        screener_template_id="leaders",
    ),
    "minervini_breakout": _meta(
        "Minervini Breakout",
        tags=["minervini", "breakout", "deprecated"],
        description="TT + fundamentals + pivot-only setup. Prefer minervini_sepa.",
        why="Unlabeled subset of SEPA without VCP/pocket-pivot OR.",
        how="Same TT/fundamentals, breakout setup only.",
        status=_DEPRECATED,
        screener_template_id="minervini_trend_template",
    ),
    "minervini_pullback": _meta(
        "Minervini Pullback",
        tags=["minervini", "pullback", "deprecated"],
        description="TT + fundamentals + pullback/pocket-pivot setup. Prefer minervini_sepa.",
        why="Unlabeled subset of SEPA.",
        how="Same TT/fundamentals, pullback_ready OR pocket_pivot_score.",
        status=_DEPRECATED,
        screener_template_id="pocket_pivot_high_rs",
    ),
}


def _humanize(tid: str) -> str:
    return tid.replace("_", " ").title()


def _screener_meta_for(tid: str) -> dict[str, Any]:
    resolved = _ALIASES.get(tid, tid)
    if resolved in _SCREENER_META:
        return _SCREENER_META[resolved]
    if tid in _SCREENER_META:
        return _SCREENER_META[tid]
    return _meta(
        _humanize(tid),
        tags=["unlabeled", "deprecated"],
        description=f"JSON template {tid} (not in the active catalog).",
        why="Unlabeled or redundant; Phase 2 hard-delete unless promoted.",
        how="See the JSON file in examples/universe_query_v1/templates.",
        status=_DEPRECATED,
    )


def _screener_body(tid: str) -> dict[str, Any]:
    json_ids = set(list_template_ids())
    if tid in json_ids:
        return load_template_json(tid)
    return preset_to_universe_query_v1(tid)


def _record(
    *,
    template_id: str,
    kind: Kind,
    meta: dict[str, Any],
    body: dict[str, Any],
    source: str = "system",
) -> dict[str, Any]:
    return {
        "id": template_id,
        "kind": kind,
        "title": meta["title"],
        "tags": list(meta["tags"]),
        "description": meta["description"],
        "why": meta["why"],
        "how": meta["how"],
        "status": meta["status"],
        "screener_template_id": meta.get("screener_template_id") or "",
        "body": body,
        "source": source,
    }


def _all_screener_ids() -> list[str]:
    ids = set(list_template_ids())
    ids.update(_SCREENER_META)
    ids.update(list_preset_ir_ids())
    return sorted(ids)


def list_templates(
    *,
    kind: Kind | None = None,
    status: Status | None = None,
    include_body: bool = False,
) -> list[dict[str, Any]]:
    """List catalog rows. Default includes deprecated so callers can filter."""
    rows: list[dict[str, Any]] = []
    if kind in (None, "screener"):
        for tid in _all_screener_ids():
            meta = _screener_meta_for(tid)
            try:
                body = _screener_body(tid) if include_body else {}
            except ValueError:
                continue
            rows.append(_record(template_id=tid, kind="screener", meta=meta, body=body))
    if kind in (None, "strategy"):
        from .strategy.presets import PRESETS, get_preset

        for tid, raw in PRESETS.items():
            meta = _STRATEGY_META.get(
                tid,
                _meta(
                    str(raw.get("strategy_name") or tid),
                    tags=["strategy"],
                    description="",
                    why="",
                    how="",
                    status=_DEPRECATED,
                ),
            )
            body = get_preset(tid).model_dump(mode="json") if include_body else {}
            rows.append(_record(template_id=tid, kind="strategy", meta=meta, body=body))
    if status:
        rows = [r for r in rows if r["status"] == status]
    if not include_body:
        for row in rows:
            row.pop("body", None)
    return rows


def resolve_template_id(template_id: str) -> str:
    tid = (template_id or "").strip()
    return _ALIASES.get(tid, tid)


def get_template(template_id: str) -> dict[str, Any]:
    """Load one catalog record (alias-aware) including body."""
    tid = resolve_template_id(template_id)
    if not tid:
        raise ValueError("template id is required")
    from .strategy.presets import PRESETS, get_preset

    if tid in PRESETS:
        meta = _STRATEGY_META.get(
            tid,
            _meta(tid, tags=["strategy"], description="", why="", how="", status=_DEPRECATED),
        )
        rec = _record(
            template_id=tid,
            kind="strategy",
            meta=meta,
            body=get_preset(tid).model_dump(mode="json"),
        )
        rec["requested_id"] = template_id
        return rec

    json_ids = set(list_template_ids())
    if tid in json_ids or tid in _SCREENER_META or tid in set(list_preset_ir_ids()):
        meta = _screener_meta_for(tid)
        try:
            body = _screener_body(tid)
        except ValueError:
            body = {}
        rec = _record(template_id=tid, kind="screener", meta=meta, body=body)
        rec["requested_id"] = template_id
        return rec

    known = sorted(set(_all_screener_ids()) | set(PRESETS) | set(_ALIASES))
    raise ValueError(f"unknown template {template_id!r}; choose from: {', '.join(known)}")


def summary_row(record: dict[str, Any]) -> dict[str, Any]:
    """Picker-friendly subset (id/label plus catalog fields)."""
    return {
        "id": record["id"],
        "label": record["title"],
        "kind": record["kind"],
        "tags": record.get("tags") or [],
        "description": record.get("description") or "",
        "why": record.get("why") or "",
        "how": record.get("how") or "",
        "status": record["status"],
        "screener_template_id": record.get("screener_template_id") or "",
    }


__all__ = [
    "get_template",
    "list_templates",
    "resolve_template_id",
    "summary_row",
]
