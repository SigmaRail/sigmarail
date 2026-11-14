"""Compile a zipper-free FROM clause over L7 screener tables.

``from: screener`` is the canonical logical universe source id (``daily_screener``
is a deprecated alias); generated SQL joins only the L7 tables that own the
referenced columns. Column→table resolution derives from the L7 join manifest
(``sql/schema/screener_l7_join.yaml``) + ``screener_*`` DDL, plus the curated
``_EXTRAS`` overrides.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
import sqlglot
from sqlglot import exp

from sigmarail.features.sql_script import split_sql_statements

# Logical name → (prefix, physical column). Spine keys + zipper-computed + VeraLab aliases.
_EXTRAS: dict[str, tuple[str, str]] = {
    "ticker": ("px", "ticker"),
    "date": ("px", "date"),
    "is_stage_2_advancing": ("rt", "is_stage_2_advancing"),
    "atr_14_pct": ("px", "atr_14_pct"),
    "spy_atr_14": ("rv", "spy_atr_14"),
    "spy_atr_missing": ("rv", "spy_atr_missing"),
    "rvab_score": ("rv", "rvab_score"),
    "atr_stop_baseline": ("rv", "atr_stop_baseline"),
    "above_21ema": ("rv", "above_21ema"),
    "growth_rate_pct": ("fc", "growth_rate_pct"),
    "fwd_eps_1y": ("fc", "fwd_eps_1y"),
    "fwd_eps_2y": ("fc", "fwd_eps_2y"),
    "target_price_15x": ("fc", "target_price_15x"),
    "target_price_normal_pe": ("fc", "target_price_normal_pe"),
    "fwd_cagr_2y_normal_pe": ("fc", "fwd_cagr_2y_normal_pe"),
    "fwd_peg_ratio": ("fc", "fwd_peg_ratio"),
    "eps_ny_rev_pct_90d": ("es", "eps_ny_rev_pct_90d"),
    "eps_nq_rev_pct_90d": ("es", "eps_nq_rev_pct_90d"),
    "eps_last_reported": ("es", "eps_last_reported"),
    "eps_last_estimate": ("es", "eps_last_estimate"),
    "eps_last_surprise_pct": ("es", "eps_last_surprise_pct"),
    "eps_beat_flag": ("es", "eps_beat_flag"),
    "sales_last_reported": ("es", "sales_last_reported"),
    "sales_last_estimate": ("es", "sales_last_estimate"),
    "sales_last_surprise_pct": ("es", "sales_last_surprise_pct"),
    "sales_beat_flag": ("es", "sales_beat_flag"),
}

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "sql" / "schema"
_JOIN_MANIFEST_PATH = _SCHEMA_DIR / "screener_l7_join.yaml"


@lru_cache(maxsize=1)
def _join_manifest() -> dict[str, Any]:
    """Load the L7 join graph manifest (table/prefix/grain single source of truth)."""
    data = yaml.safe_load(_JOIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("tables"):
        raise RuntimeError(f"invalid L7 join manifest: {_JOIN_MANIFEST_PATH}")
    return data


@lru_cache(maxsize=1)
def column_homes() -> dict[str, tuple[str, str]]:
    """logical/physical output name → (prefix, physical column on that table)."""
    homes: dict[str, tuple[str, str]] = dict(_EXTRAS)
    for entry in _join_manifest()["tables"]:
        path = _SCHEMA_DIR / entry["schema"]
        if not path.is_file():
            continue
        for statement in split_sql_statements(path.read_text(encoding="utf-8")):
            if "CREATE TABLE" not in statement.upper():
                continue
            try:
                ddl = sqlglot.parse_one(statement, read="clickhouse")
            except sqlglot.errors.ParseError:
                continue
            if not isinstance(ddl, exp.Create) or ddl.kind.upper() != "TABLE":
                continue
            definition = ddl.this
            if not isinstance(definition, exp.Schema):
                continue
            table = definition.this
            if not isinstance(table, exp.Table) or table.name != entry["table"]:
                continue
            for column in definition.expressions:
                if not isinstance(column, exp.ColumnDef):
                    continue
                name = column.this.name
                # Dotted ClickHouse identifiers are physical source names (for
                # example, `mrs.weekly_allocation_tier`), not L7 logical names.
                # Treating the dot as part of a logical name would compile an
                # invalid `mx.mrs.weekly_allocation_tier` reference.
                if name in ("ticker", "date", "lastupdated") or "." in name:
                    continue
                homes.setdefault(name, (entry["prefix"], name))
            break
    return homes


def l7_physical_tables() -> list[str]:
    """Physical L7 table names from the join manifest (CH ``system.columns`` scope)."""
    return [str(e["table"]) for e in _join_manifest()["tables"]]


def l7_table_prefixes() -> dict[str, str]:
    """Physical table name → join prefix (px, fd, …)."""
    return {str(e["table"]): str(e["prefix"]) for e in _join_manifest()["tables"]}


def qualify_column(name: str) -> str:
    """Return ``prefix.physical`` for an allowlisted zipper/L7 column name."""
    key = name.strip().strip("`")
    if key.startswith("dm.") or key.startswith("dmd.") or key.startswith("sa."):
        key = key.split(".", 1)[1]
    home = column_homes().get(key)
    if home is None:
        raise ValueError(f"unknown L7 column: {name!r}")
    prefix, physical = home
    return f"{prefix}.{physical}"


def prefixes_for(names: set[str]) -> set[str]:
    out = {"px"}
    homes = column_homes()
    for raw in names:
        key = raw.strip().strip("`")
        if key.startswith("dm.") or key.startswith("dmd.") or key.startswith("sa."):
            key = key.split(".", 1)[1]
        home = homes.get(key)
        if home:
            out.add(home[0])
    return out


def l7_from_sql(
    column_names: set[str] | None = None,
    *,
    date_between_sql: str | None = None,
) -> str:
    """FROM … LEFT ANY JOIN … covering ``column_names`` (always includes the spine).

    ``date_between_sql`` is the ClickHouse fragment after ``BETWEEN`` (e.g.
    ``toDate({start:String}) AND toDate({end:String})``). When set, each
    date-grained join also predicates ``prefix.date BETWEEN …`` so range
    queries do not hash-join the full right table (MEMORY_LIMIT_EXCEEDED).
    """
    manifest = _join_manifest()
    spine = manifest["spine"]
    join_kw = "LEFT ANY JOIN" if manifest.get("join_type", "any") == "any" else "LEFT JOIN"
    by_prefix = {e["prefix"]: e for e in manifest["tables"]}
    spine_entry = by_prefix[spine]
    needed = prefixes_for(column_names or set())
    parts = [f"{spine_entry['table']} AS {spine} FINAL"]
    for entry in manifest["tables"]:
        prefix = entry["prefix"]
        if prefix == spine or prefix not in needed:
            continue
        grain = set(entry.get("grain", ["ticker", "date"]))
        on_parts = [f"{spine}.date = {prefix}.date"]
        if "ticker" in grain:
            on_parts.insert(0, f"{spine}.ticker = {prefix}.ticker")
        if date_between_sql and "date" in grain:
            on_parts.append(f"{prefix}.date BETWEEN {date_between_sql}")
        on = " AND ".join(on_parts)
        # ClickHouse can raise NOT_FOUND_COLUMN_IN_BLOCK when FINAL is applied
        # on the right side of LEFT ANY JOIN. The L7 read fragments follow the
        # same rule; reserve FINAL for the price spine.
        parts.append(f"{join_kw} {entry['table']} AS {prefix} ON {on}")
    return "\n            ".join(parts)


def resolve_joins_for_columns(column_names: set[str] | None = None) -> list[dict[str, Any]]:
    """Return explicit join descriptors for tables needed by ``column_names`` (excluding spine)."""
    manifest = _join_manifest()
    spine = manifest["spine"]
    needed = prefixes_for(column_names or set())
    joins: list[dict[str, Any]] = []
    join_type = "left_any" if manifest.get("join_type", "any") == "any" else "left"
    for entry in manifest["tables"]:
        prefix = entry["prefix"]
        if prefix == spine or prefix not in needed:
            continue
        joins.append({
            "table": str(entry["table"]),
            "type": join_type,
            "on": list(entry.get("grain", ["ticker", "date"])),
        })
    return joins
