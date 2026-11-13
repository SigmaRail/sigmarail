"""Shared core for Vera screener/query execution.

This package is intended to be imported by:
- VeraTradingLab (LEAN Python runtime)
- SigmaRail Studio MCP server (thin wrapper)
- A small REST service (thin wrapper)

Single source of truth: validate → compile (VeraLab IR) → execute (clickhouse_connect).
"""

from __future__ import annotations

# Keep package import lightweight.
# In environments where optional deps aren't installed yet, importing sigmarail.features
# should not fail if callers only need a submodule (e.g. lineage tooling).
try:
    from .api_types import (
        BrokerPositionsResponse,
        DescribeTableResponse,
        ExportFormat,
        ListDatabaseTablesResponse,
        QueryMode,
        ScreenRequest,
        ScreenResponse,
        TableColumnMetadata,
        TableQueryV1Response,
        UniverseRunRequest,
        UniverseRunResponse,
        UniverseRunSpec,
    )
    from .ch_settings import (
        ClickHouseSettings,
        connect_clickhouse,
        resolve_clickhouse_settings_from_env,
        resolve_clickhouse_settings_unified,
    )
    from .executor import ClickHouseExecutor
    from .ir.universe_query_v1 import UniverseQueryV1, universe_v1_column_sql_expression

    __all__ = [
        "BrokerPositionsResponse",
        "ClickHouseExecutor",
        "ClickHouseSettings",
        "DescribeTableResponse",
        "ExportFormat",
        "ListDatabaseTablesResponse",
        "QueryMode",
        "ScreenRequest",
        "ScreenResponse",
        "TableColumnMetadata",
        "TableQueryV1Response",
        "UniverseQueryV1",
        "universe_v1_column_sql_expression",
        "UniverseRunRequest",
        "UniverseRunResponse",
        "UniverseRunSpec",
        "connect_clickhouse",
        "resolve_clickhouse_settings_from_env",
        "resolve_clickhouse_settings_unified",
    ]
except Exception:  # pragma: no cover
    __all__: list[str] = []
