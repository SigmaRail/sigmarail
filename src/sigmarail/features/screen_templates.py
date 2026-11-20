"""Canonical ``universe_query_v1`` screen templates (single catalog for Studio + docs)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "examples" / "universe_query_v1" / "templates"

_TEMPLATE_LABELS: dict[str, str] = {
    "fair_value_discount_compounders": "Fair Value Discount Compounders",
    "garp_minervini_forecast_template": "GARP Minervini Forecast Template",
    "minervini_trend_template": "Minervini Trend Template (Standard)",
    "vcp_triad_coiling": "VCP Direct L7 Triad",
    "setup_quality_leaders": "Setup Quality Leaders",
    "minervini_trend_template_5m": "Minervini Trend Template (5-Month 200 SMA / Strict)",
    "minervini_trend_template_1m": "Minervini Trend Template (1-Month 200 SMA / Early Turnaround)",
    "minervini_momentum_leaders": "Minervini Momentum Leaders (RS 85+ & 52W Highs)",
    "minervini_fundamental_growth": "Minervini Fundamental Growth Champions",
    "minervini_vcp_breakout": "Minervini VCP & Stage 2 Consolidation",
    "minervini_high_tight_flag": "Minervini High Tight Flag / Power Play",
    "canslim_template": "CANSLIM Leader Filter",
    "breakout_quality_setups": "Chartmill Breakout Setups (High Technical & Setup Ratings)",
    "strong_growth_technical_setups": "Chartmill Strong Growth & Technical Setups",
    "kullamagi_breakout_momentum": "Kristjan Kullamägi Continuation & Momentum Breakouts",
    "weinstein_stage_2_breakout": "Stan Weinstein Stage 2 Advancing Breakouts",
    "unusual_volume_breakouts": "Unusual Volume Breakouts (2x+ 50D Vol)",
    "swing_pullback_sma20": "Swing Trading - Pullback to 20-Day SMA",
    "near_52w_high_breakout": "Near 52-Week High Breakouts & Strong RS",
    "bull_flag_breakouts": "Bull Flag Continuation Breakouts",
    "affordable_growth_compounders": "Affordable Growth Compounders (GARP)",
    "volatility_squeeze_breakout": "Volatility Squeeze Play (Low ATR Contraction)",
    "pocket_pivot_high_rs": "Pocket Pivot in Strong Market Leaders",
    "high_trend_intensity_volume": "High Trend Intensity on Volume Surge",
    "piotroski_undervalued_compounders": "Piotroski Quality & Undervalued Compounders",
    "dividend_growth_compounders": "Quality Dividend Growth Compounders",
}


def templates_dir() -> Path:
    return _TEMPLATES_DIR


@lru_cache(maxsize=1)
def list_template_ids() -> tuple[str, ...]:
    if not _TEMPLATES_DIR.is_dir():
        return ()
    return tuple(sorted(p.stem for p in _TEMPLATES_DIR.glob("*.json")))


def load_template_json(template_id: str) -> dict:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template id is required")
    path = _TEMPLATES_DIR / f"{tid}.json"
    if not path.is_file():
        known = ", ".join(list_template_ids()) or "(none)"
        raise ValueError(f"unknown template {tid!r}; choose from: {known}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_templates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for tid in list_template_ids():
        label = _TEMPLATE_LABELS.get(tid, tid.replace("_", " ").title())
        out.append({"id": tid, "label": label})
    return out


__all__ = [
    "list_template_ids",
    "list_templates",
    "load_template_json",
    "templates_dir",
]
