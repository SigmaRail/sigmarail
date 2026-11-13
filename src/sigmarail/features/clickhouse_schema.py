"""ClickHouse catalog helpers: list tables, describe columns (used by MCP and REST)."""

from __future__ import annotations

import os
import re
from typing import Any

import clickhouse_connect

from sigmarail.features.mcp_table_catalog import exposed_table_names, require_exposed_table

_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_PREFIX = re.compile(r"^[A-Za-z0-9_]{0,64}$")


def rows_to_dicts(result: Any) -> list[dict[str, Any]]:
    cols = result.column_names
    return [dict(zip(cols, r)) for r in result.result_rows]


def validate_table_identifier(name: str) -> str:
    n = name.strip()
    if not _TABLE_NAME.match(n):
        raise ValueError(
            "Invalid table name: use letters, digits, underscore; must start with letter or underscore"
        )
    return n


def validate_table_name_prefix(prefix: str | None) -> str | None:
    if prefix is None or not prefix.strip():
        return None
    p = prefix.strip()
    if not _TABLE_PREFIX.match(p):
        raise ValueError("Invalid name_prefix: use only letters, digits, underscore (max 64 chars)")
    return p


def session_database(client: clickhouse_connect.driver.Client) -> str:
    row = client.query("SELECT currentDatabase()").result_rows
    if not row or row[0][0] is None:
        raise RuntimeError("currentDatabase() returned no value")
    return str(row[0][0])


def clamp_schema_list_limit(limit: int | None) -> int:
    mx = int(os.environ.get("MCP_SCHEMA_LIST_MAX", "500").strip())
    d = int(os.environ.get("MCP_SCHEMA_LIST_DEFAULT", "200").strip())
    if limit is None:
        v = d
    else:
        v = int(limit)
    if v < 1:
        v = 1
    return min(v, mx)


def query_list_database_tables(
    client: clickhouse_connect.driver.Client,
    *,
    limit: int | None = None,
    name_prefix: str | None = None,
) -> dict[str, Any]:
    """Tables and views in the session database from ``system.tables``."""
    db = session_database(client)
    lim = clamp_schema_list_limit(limit)
    prefix = validate_table_name_prefix(name_prefix)
    like_pat = f"{prefix}%" if prefix else "%"
    allowed = sorted(exposed_table_names())
    q = """
    SELECT name, engine, total_rows, comment
    FROM system.tables
    WHERE database = {db:String}
      AND is_temporary = 0
      AND name IN {names:Array(String)}
      AND name LIKE {like:String}
    ORDER BY name
    LIMIT {lim:UInt32}
    """
    rows = rows_to_dicts(
        client.query(q, parameters={"db": db, "like": like_pat, "lim": lim, "names": allowed})
    )
    allowed_set = frozenset(allowed)
    rows = [r for r in rows if str(r.get("name") or "") in allowed_set]
    return {
        "database": db,
        "limit": lim,
        "name_prefix": prefix,
        "row_count": len(rows),
        "tables": rows,
    }


def query_describe_table(
    client: clickhouse_connect.driver.Client,
    table: str,
) -> dict[str, Any]:
    """Column definitions for one table from ``system.columns`` (ordered by position)."""
    tbl = require_exposed_table(table)
    db = session_database(client)
    q = """
    SELECT name, position, type, default_kind, default_expression, comment
    FROM system.columns
    WHERE database = {db:String} AND table = {tbl:String}
    ORDER BY position
    """
    rows = rows_to_dicts(client.query(q, parameters={"db": db, "tbl": tbl}))
    if not rows:
        raise ValueError(f"No columns found for table {tbl!r} in database {db!r} (missing or no access)")
    return {
        "database": db,
        "table": tbl,
        "column_count": len(rows),
        "columns": rows,
    }
