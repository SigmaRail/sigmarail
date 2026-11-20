"""Qualify VeraLab screener columns onto L7 tables.

``source: daily_screener`` stays the logical IR id. Generated SQL joins only
the L7 tables that own the referenced columns (compact map — not the full
zipper). Keep this aligned with ``sigmarail_lab.ir.screener_columns.ScreenerColumn``.
"""

from __future__ import annotations

# logical name → (prefix, physical column)
_HOMES: dict[str, tuple[str, str]] = {
    "ticker": ("px", "ticker"),
    "date": ("px", "date"),
    "close": ("px", "close"),
    "volume": ("px", "volume"),
    "open": ("px", "open"),
    "high": ("px", "high"),
    "low": ("px", "low"),
    "sector": ("px", "sector"),
    "rs_rating": ("px", "rs_rating"),
    "sma200d": ("px", "sma200d"),
    "minervini_tt_score_full": ("px", "minervini_tt_score_full"),
    "atr_pct_14d": ("px", "atr_14_pct"),
    "has_vcp_setup": ("rt", "has_vcp_setup"),
    "is_stage_2_advancing": ("rt", "is_stage_2_advancing"),
    "overall_score": ("rt", "overall_score"),
    "pct_from_sma20d": ("tf", "pct_from_sma20d"),
    "drawdown_from_50d_high": ("tf", "drawdown_from_50d_high"),
    "up_days_last_3": ("tf", "up_days_last_3"),
    "downside_reversal_flag": ("tf", "downside_reversal_flag"),
    "near_sma20_flag": ("tf", "near_sma20_flag"),
    "two_closes_below_sma20": ("tf", "two_closes_below_sma20"),
    "factor_residual_60d": ("fa", "factor_residual_60d"),
    "factor_rolling_alpha_60d": ("fa", "factor_rolling_alpha_60d"),
    "factor_alpha_tstat_60d": ("fa", "factor_alpha_tstat_60d"),
    "factor_beta_mkt_60d": ("fa", "factor_beta_mkt_60d"),
    "factor_beta_sector_60d": ("fa", "factor_beta_sector_60d"),
    "factor_r2_60d": ("fa", "factor_r2_60d"),
    "factor_residual_252d": ("fa", "factor_residual_252d"),
    "factor_rolling_alpha_252d": ("fa", "factor_rolling_alpha_252d"),
    "factor_alpha_tstat_252d": ("fa", "factor_alpha_tstat_252d"),
    "factor_beta_mkt_252d": ("fa", "factor_beta_mkt_252d"),
    "factor_beta_sector_252d": ("fa", "factor_beta_sector_252d"),
    "factor_r2_252d": ("fa", "factor_r2_252d"),
}

_TABLES: dict[str, str] = {
    "px": "screener_price_tech_daily",
    "rt": "screener_ratings_daily",
    "fa": "screener_factor_daily",
    "tf": "symbol_technical_features_daily",
}

_JOIN_ORDER: tuple[str, ...] = ("tf", "rt", "fa")


def qualify_column(name: str) -> str:
    key = str(name).strip().strip("`")
    home = _HOMES.get(key)
    if home is None:
        raise ValueError(f"unknown L7 column: {name!r}")
    prefix, physical = home
    return f"{prefix}.{physical}"


def prefixes_for(names: set[str]) -> set[str]:
    out = {"px"}
    for raw in names:
        key = str(raw).strip().strip("`")
        home = _HOMES.get(key)
        if home:
            out.add(home[0])
    return out


def l7_from_sql(column_names: set[str] | None = None) -> str:
    needed = prefixes_for(column_names or set())
    parts = ["screener_price_tech_daily AS px FINAL"]
    for prefix in _JOIN_ORDER:
        if prefix not in needed:
            continue
        table = _TABLES[prefix]
        on = f"px.ticker = {prefix}.ticker AND px.date = {prefix}.date"
        parts.append(f"LEFT ANY JOIN {table} AS {prefix} FINAL ON {on}")
    return "\n            ".join(parts)
