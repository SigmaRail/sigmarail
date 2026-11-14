"""Schema-driven ``daily_screener`` column names for legacy SQL compilation.

Physical names and overrides come from :mod:`sigmarail.features.ir.universe_v1_column_registry`
(refreshed from ClickHouse when a client is available).

For full column metadata (types, comments), use :mod:`sigmarail.features.clickhouse_schema`.
"""

from __future__ import annotations

import re

from .universe_v1_column_registry import get_universe_v1_col_sql_map

# Public type: any physical (or overridden logical) column name.
ScreenerColumn = str

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sql_ident(column: ScreenerColumn) -> str:
    """ClickHouse identifier (quote dotted / non-simple names)."""
    v = str(column).strip().strip("`")
    if not v:
        raise ValueError("empty column identifier")
    if "." in v or not _SAFE_IDENT.match(v):
        return f"`{v.replace('`', '')}`"
    return v


def available_columns() -> frozenset[ScreenerColumn]:
    """All known columns (physical + overrides) for ``daily_screener``."""
    return frozenset(get_universe_v1_col_sql_map().keys())
