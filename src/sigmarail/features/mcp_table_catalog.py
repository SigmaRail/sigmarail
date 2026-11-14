"""MCP table exposure catalog — one allowlist for list/describe/explain/query."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "mcp_table_catalog.yaml"

SQL_JOIN_EXAMPLE = (
    "SELECT ow.ticker, ow.inst_shrholders_qoq_delta, px.rs_rating "
    "FROM screener_ownership_daily AS ow "
    "LEFT ANY JOIN screener_price_tech_daily AS px "
    "ON ow.ticker = px.ticker AND ow.date = px.date "
    "WHERE ow.date = '2026-08-12' AND ow.inst_shrholders_qoq_delta >= 10 "
    "ORDER BY ow.inst_shrholders_qoq_delta DESC LIMIT 25"
)

NOT_EXPOSED_HINT = (
    "not exposed on vera MCP list/describe/query_table_v1. "
    "Use a catalog table (see query_table_v1_spec_schema), a dedicated tool "
    "(screen_stocks, get_market_regime, get_portfolio_status), or mcp-clickhouse."
)


@dataclass(frozen=True)
class CatalogEntry:
    prefix: str
    table: str
    grain: str
    time_key: str
    entity_key: str | None


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


@lru_cache(maxsize=1)
def load_catalog() -> tuple[CatalogEntry, ...]:
    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    rows = raw.get("tables") or []
    out: list[CatalogEntry] = []
    seen_prefix: set[str] = set()
    seen_table: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("mcp_table_catalog.yaml tables entries must be mappings")
        prefix = str(row.get("prefix") or "").strip()
        table = str(row.get("table") or "").strip()
        if not prefix or not table:
            raise ValueError("catalog row requires prefix and table")
        if prefix in seen_prefix:
            raise ValueError(f"duplicate catalog prefix {prefix!r}")
        if table in seen_table:
            raise ValueError(f"duplicate catalog table {table!r}")
        seen_prefix.add(prefix)
        seen_table.add(table)
        out.append(
            CatalogEntry(
                prefix=prefix,
                table=table,
                grain=str(row.get("grain") or "daily").strip(),
                time_key=str(row.get("time_key") or "date").strip(),
                entity_key=_as_optional_str(row.get("entity_key")),
            )
        )
    if not out:
        raise ValueError("mcp_table_catalog.yaml has no tables")
    return tuple(out)


def prefix_to_table() -> dict[str, str]:
    return {e.prefix: e.table for e in load_catalog()}


def table_to_entry() -> dict[str, CatalogEntry]:
    return {e.table: e for e in load_catalog()}


def prefix_to_entry() -> dict[str, CatalogEntry]:
    return {e.prefix: e for e in load_catalog()}


def exposed_table_names() -> frozenset[str]:
    return frozenset(e.table for e in load_catalog())


def require_exposed_table(name: str) -> str:
    tbl = (name or "").strip()
    if not _TABLE_NAME.match(tbl):
        raise ValueError(
            "Invalid table name: use letters, digits, underscore; must start with letter or underscore"
        )
    if tbl not in exposed_table_names():
        raise ValueError(f"table {tbl!r} is {NOT_EXPOSED_HINT}")
    return tbl


def catalog_schema_defs() -> dict[str, Any]:
    mapping = prefix_to_table()
    return {
        "ScreenerJoinAlias": {
            "type": "object",
            "description": (
                "Required SQL AS alias on spec.sql. Physical columns stay bare; "
                "qualify as prefix.column after FROM <table> AS <prefix>."
            ),
            "properties": {
                prefix: {"const": table, "description": f"AS {prefix} → {table}"}
                for prefix, table in mapping.items()
            },
            "additionalProperties": False,
        },
        "sqlJoinExample": {
            "type": "string",
            "const": SQL_JOIN_EXAMPLE,
            "description": "Valid catalog join: ownership + price, agent-supplied date filter.",
        },
    }
