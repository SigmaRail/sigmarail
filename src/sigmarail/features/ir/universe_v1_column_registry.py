"""Schema-driven L7 column surface for ``universe_query_v1``.

Physical column names come from ClickHouse ``system.columns`` when a client is
available (refreshed from ``ClickHouseExecutor``), otherwise from the L7
``screener_*`` schema DDL via :func:`l7_from.column_homes`.

Only :data:`UNIVERSE_V1_COLUMN_OVERRIDES` needs code edits for special SQL
(coercions, logical aliases like ``sma21d`` → ``sma20d``).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
from typing import Any

# --- Small curated layer (edit here only for coercions / aliases) ------------

EXCLUDED_PHYSICAL: frozenset[str] = frozenset(
    {
        # Operational / ingestion metadata — not useful in universe screens.
        "lastupdated",
    }
)

UNIVERSE_V1_COLUMN_OVERRIDES: dict[str, tuple[str, str]] = {
    # Normalized date for stable comparisons / sorting
    "date": ("toDate(px.date)", "date"),
    "close": ("px.close", "close"),
    "volume": ("px.volume", "volume"),
    # L7 screener spine is equity-only; no physical security_type column.
    # Constant lets Universe hygiene ``eq security_type Equity`` compile.
    "security_type": ("'Equity'", "security_type"),
    "has_vcp_setup": ("rt.has_vcp_setup", "has_vcp_setup"),
    # C3: the VCP satellite's pivot line (prefix vp), for pivot-derived stops
    "vcp_pivot_line": ("vp.pivot_line", "vcp_pivot_line"),
    "is_stage_2_advancing": ("rt.is_stage_2_advancing", "is_stage_2_advancing"),
    "high_52w": ("px.high_52w", "high_52w"),
    # Stakeholder / legacy naming
    "sma21d": ("px.sma20d", "sma21d"),
    # Declared alias in 02-schema-daily_metrics.entities.yaml (aliases: [ema21, 21_ema,
    # ema_21d]); injected by compiler._TRIGGER_SELECT["ema_cross"] and read by the
    # runtime's bar requirements. Without this the select column cannot resolve.
    "ema_21d": ("px.ema21d", "ema_21d"),
    "breakout_signal": ("px.breakout_signal", "breakout_signal"),
    "stage_primary": ("st.stage_primary", "stage_primary"),
    # Legacy logical name → canonical percent column
    "atr_pct_14d": ("px.atr_14_pct", "atr_14_pct"),
    # Forecast models daily fields
    "growth_rate_pct": ("fc.growth_rate_pct", "growth_rate_pct"),
    "fwd_eps_1y": ("fc.fwd_eps_1y", "fwd_eps_1y"),
    "fwd_eps_2y": ("fc.fwd_eps_2y", "fwd_eps_2y"),
    "target_price_15x": ("fc.target_price_15x", "target_price_15x"),
    "target_price_normal_pe": ("fc.target_price_normal_pe", "target_price_normal_pe"),
    "fwd_cagr_2y_normal_pe": ("fc.fwd_cagr_2y_normal_pe", "fwd_cagr_2y_normal_pe"),
    "fwd_peg_ratio": ("fc.fwd_peg_ratio", "fwd_peg_ratio"),
    "eps_ny_rev_pct_90d": ("es.eps_ny_rev_pct_90d", "eps_ny_rev_pct_90d"),
    "eps_nq_rev_pct_90d": ("es.eps_nq_rev_pct_90d", "eps_nq_rev_pct_90d"),
    "eps_last_reported": ("es.eps_last_reported", "eps_last_reported"),
    "eps_last_estimate": ("es.eps_last_estimate", "eps_last_estimate"),
    "eps_last_surprise_pct": ("es.eps_last_surprise_pct", "eps_last_surprise_pct"),
    "eps_beat_flag": ("es.eps_beat_flag", "eps_beat_flag"),
    "sales_last_reported": ("es.sales_last_reported", "sales_last_reported"),
    "sales_last_estimate": ("es.sales_last_estimate", "sales_last_estimate"),
    "sales_last_surprise_pct": ("es.sales_last_surprise_pct", "sales_last_surprise_pct"),
    "sales_beat_flag": ("es.sales_beat_flag", "sales_beat_flag"),
}


def _auto_sql_expression(physical_name: str) -> str:
    """Qualified L7 expression for a physical / logical column name."""
    from sigmarail.features.ir.l7_from import qualify_column

    n = physical_name.strip().strip("`")
    if not n:
        raise ValueError("empty column name")
    try:
        return qualify_column(n)
    except ValueError:
        if "." in n or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", n):
            return f"`{n.replace('`', '')}`"
        return n


def _auto_output_alias(physical_name: str) -> str:
    """JSON-safe output alias (dots → underscores)."""
    return physical_name.strip().strip("`").replace(".", "_")


def _merge_registry(physical: frozenset[str]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for name in physical:
        if name in EXCLUDED_PHYSICAL:
            continue
        sql_expr = _auto_sql_expression(name)
        alias = _auto_output_alias(name)
        out[name] = (sql_expr, alias)
        if "." in sql_expr:
            out[sql_expr] = (sql_expr, alias)
    for k, v in UNIVERSE_V1_COLUMN_OVERRIDES.items():
        out[k] = v
        if "." in v[0]:
            out[v[0]] = v
    return out


_lock = threading.Lock()
_registry: dict[str, tuple[str, str]] | None = None
_live_columns_loaded: bool = False


@lru_cache(maxsize=1)
def _fallback_physical_columns() -> frozenset[str]:
    from sigmarail.features.ir.l7_from import column_homes

    cols = frozenset(column_homes().keys())
    if not cols:
        raise RuntimeError("empty L7 column surface from column_homes()")
    return cols


def get_universe_v1_col_sql_map() -> dict[str, tuple[str, str]]:
    """Mutable registry map (logical / physical name → (sql_expr, output_alias))."""
    global _registry
    with _lock:
        if _registry is None:
            _registry = _merge_registry(_fallback_physical_columns())
        return _registry


def registry_digest() -> str:
    """Stable digest of the resolved column surface.

    Clients (LEAN, Studio, MCP) record what they compiled/validated against, so a
    registry refresh cannot silently change what a stored spec means. Served by
    ``GET /v1/meta`` and echoed on execution responses (``C-API-SURFACE-V1``).
    """
    payload = json.dumps(
        {
            name: [sql, alias]
            for name, (sql, alias) in sorted(get_universe_v1_col_sql_map().items())
        },
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def l7_sources() -> dict[str, str]:
    """``{prefix: physical_table}`` for the L7 join surface (e.g. ``px`` → ``screener_price_tech_daily``)."""
    from sigmarail.features.ir.l7_from import l7_table_prefixes

    return {prefix: table for table, prefix in l7_table_prefixes().items()}


def source_field_catalog(source: str) -> list[dict[str, str]]:
    """Resolved registry entries homed on one L7 prefix, sorted by name."""
    prefix = str(source).strip().strip(".")
    if not prefix:
        raise ValueError("empty source prefix")
    needle = f"{prefix}."
    out: list[dict[str, str]] = []
    for name, (sql, alias) in sorted(get_universe_v1_col_sql_map().items()):
        if sql.startswith(needle):
            out.append({"name": name, "sql": sql, "alias": alias})
    return out


def try_refresh_universe_v1_columns_from_client(client: Any) -> None:
    """Load column names from live ClickHouse (once per process unless reset)."""
    global _registry, _live_columns_loaded
    with _lock:
        if _live_columns_loaded:
            return
        q = (
            "SELECT name FROM system.columns "
            "WHERE database = currentDatabase() AND `table` IN {t:Array(String)} "
            "ORDER BY position"
        )
        tables = [
            "screener_price_tech_daily",
            "screener_fundamentals_daily",
            "screener_ratings_daily",
            "screener_stage_weekly_daily",
            "screener_ownership_daily",
            "screener_factor_daily",
            "screener_kb_daily",
            "symbol_technical_features_daily",
            "market_context_daily",
            "ticker_rvab_daily",
            "screener_forecast_models_daily",
            "screener_estimates_daily",
            "screener_vcp_pivot_daily",
        ]
        r = client.query(q, parameters={"t": tables})
        physical = frozenset(str(row[0]) for row in r.result_rows)
        if not physical:
            raise RuntimeError("L7 screener tables have no columns in system.columns")
        _registry = _merge_registry(physical)
        _live_columns_loaded = True


def invalidate_universe_v1_column_registry() -> None:
    """Drop every cached column view so the next lookup re-derives from source.

    **Both** caches must go. `l7_from.column_homes()` carries its own `lru_cache` on top of
    this registry's, so clearing only `_registry` leaves the DDL-derived column set stale
    for the life of the process. In a long-lived Studio that means a spec referencing a
    newly-added `screener_*` column is rejected until restart — silently, with the gate
    claiming the column does not exist.
    """
    global _registry, _live_columns_loaded
    with _lock:
        _registry = None
        _live_columns_loaded = False
    _fallback_physical_columns.cache_clear()
    from sigmarail.features.ir import l7_from

    l7_from.column_homes.cache_clear()


def reset_universe_v1_column_registry_for_tests() -> None:
    """Clear cached registry (unit tests)."""
    invalidate_universe_v1_column_registry()
