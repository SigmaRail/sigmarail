from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sigmarail.features.ir.universe_query_v1 import UniverseQueryV1

UniverseRunSpec = UniverseQueryV1


QueryMode = Literal["detail", "analytical", "export"]
ExportFormat = Literal[
    "objects",  # list[dict] (default)
    "json_each_row",  # NDJSON text (one object per line)
    "json_compact_each_row_with_names_and_types",  # NDJSON arrays + header rows
    "csv_with_names",
    "parquet",
]

class UniverseRunRequest(BaseModel):
    """Range load for backtests: ``universe_query_v1`` JSON over [start_date, end_date]."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2024-01-02",
                    "end_date": "2024-01-10",
                    "spec": {
                        "version": 1,
                        "from": "daily_screener",
                        "version": 2,
                        "spine": "screener_price_tech_daily",
                        "select": ["ticker", "close", "high_52w", "overall_score", "atr_14_pct"],
                        "where": {
                            "type": "all",
                            "items": [
                                {
                                    "type": "gt",
                                    "left": {"type": "col", "name": "close"},
                                    "right": {"type": "col", "name": "high_52w"},
                                }
                            ],
                        },
                        "order_by": [{"field": "overall_score", "direction": "desc"}],
                        "limit_per_day": 50,
                    },
                    "mode": "detail",
                    "export_format": "objects",
                    "limit": 500000,
                },
                {
                    "start_date": "2024-01-02",
                    "end_date": "2024-01-10",
                    "spec": {
                        "version": 1,
                        "from": "daily_screener",
                        "version": 2,
                        "spine": "screener_price_tech_daily",
                        "select": ["ticker", "close", "overall_score"],
                        "where_sql": "close > 0 AND overall_score > 50",
                        "order_by": [{"field": "overall_score", "direction": "desc"}],
                        "limit_per_day": 50,
                    },
                    "mode": "detail",
                    "export_format": "objects",
                },
            ]
        },
    )

    start_date: str = Field(description="ISO date (YYYY-MM-DD)")
    end_date: str = Field(description="ISO date (YYYY-MM-DD)")
    spec: UniverseRunSpec = Field(
        description=(
            "**universe_query_v1** (``version``=1, ``from``=daily_screener, ``select``, exactly one of "
            "``where`` or ``where_sql``, ``order_by``, ``limit_per_day``). See "
            "**universe_query_v1 / v2** (``version``=2, ``spine``=screener_price_tech_daily, ``select``, exactly one of "
            "``where`` or ``where_sql``, ``order_by``, ``limit_per_day``). Joins are auto-resolved from selected columns. See "
            "``docs/UNIVERSE_QUERY_V1_LLM.md``."
        )
    )
    mode: QueryMode = "detail"
    export_format: ExportFormat = "objects"
    limit: int | None = Field(default=None, ge=1, le=5_000_000)


class UniverseRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: str
    end_date: str
    mode: QueryMode
    row_count: int
    rows: list[dict[str, Any]] | None = None
    text: str | None = None
    export_format: ExportFormat | None = None
    truncated: bool = False
    # --- frame contract echo (C-API-SURFACE-V1) ---------------------------
    # The runtime evaluates Alpha/PCM/Risk expressions off these columns, so the
    # frame states what it carried rather than leaving it to be inferred.
    registry_digest: str = ""
    select: list[str] = Field(default_factory=list)
    computed_aliases: list[str] = Field(default_factory=list)
    order_by: list[dict[str, Any]] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)


class ScreenRequest(BaseModel):
    """A single-day screener run against daily_screener (``universe_query_v1`` only)."""

    model_config = ConfigDict(extra="forbid")

    as_of_date: str | None = Field(
        default=None, description="ISO date (YYYY-MM-DD); omit to use max(date) in daily_screener"
    )
    spec: UniverseRunSpec = Field(
        description="universe_query_v1 (``where`` or optional ``where_sql``; see ``docs/UNIVERSE_QUERY_V1_LLM.md``)."
    )
    mode: QueryMode = "detail"
    export_format: ExportFormat = "objects"
    limit: int | None = Field(
        default=None,
        ge=1,
        le=50_000,
        description="Optional additional cap. Applied after spec.limit_per_day.",
    )


class ScreenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: str
    mode: QueryMode
    row_count: int
    summary: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    text: str | None = None
    export_format: ExportFormat | None = None
    truncated: bool = False
    # --- frame contract echo (C-API-SURFACE-V1); see UniverseRunResponse ----
    registry_digest: str = ""
    select: list[str] = Field(default_factory=list)
    computed_aliases: list[str] = Field(default_factory=list)
    order_by: list[dict[str, Any]] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)


class TableColumnMetadata(BaseModel):
    """One row from ``system.columns`` (see :func:`sigmarail.features.clickhouse_schema.query_describe_table`)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    position: int
    type: str
    default_kind: str = ""
    default_expression: str = ""
    comment: str = ""


class TableMetadata(BaseModel):
    """One row from ``system.tables`` for the described table."""

    model_config = ConfigDict(extra="forbid")

    engine: str = ""
    partition_key: str = ""
    sorting_key: str = ""
    primary_key: str = ""
    total_rows: int | None = None
    comment: str = ""


class DescribeTableResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str
    table: str
    column_count: int
    columns: list[TableColumnMetadata]
    table_metadata: TableMetadata | None = None
    total_column_count: int = 0
    full_table_columns_with_comment: int = 0
    full_table_columns_empty_comment: int = 0
    sparse_column_comments: bool = False
    describe_truncated: bool = False
    describe_truncation_limit: int | None = None


class TableSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    engine: str
    total_rows: int | None = None
    comment: str = ""


class ListDatabaseTablesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str
    limit: int
    name_prefix: str | None = None
    row_count: int
    tables: list[TableSummary]


class TableQueryV1Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str
    table: str
    row_count: int
    limit: int
    offset: int
    sql: str
    rows: list[dict[str, Any]]


class BrokerPositionsResponse(BaseModel):
    """Latest holdings from ``broker_positions_flat`` (same core as MCP ``query_table_v1``)."""

    model_config = ConfigDict(extra="forbid")

    positions: list[dict[str, Any]]
    count: int
    as_of_snapshot: Any | None = None


# --- Compatibility / registry surface (C-API-SURFACE-V1) ---------------------
# A spec is only meaningful against a dialect + a field registry. These models
# make that explicit so an out-of-process client (the LEAN container) can check
# before it runs, instead of discovering drift as an HTTP 422 mid-backtest.


class DialectInfo(BaseModel):
    """The expression dialect the service compiles with (``C-VERA-EXPR-V1``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    version: str


class MetaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: str
    dialect: DialectInfo
    registry_digest: str
    field_count: int
    l7_sources: list[str] = Field(default_factory=list)


class ReadyResponse(BaseModel):
    """Readiness: the warehouse is reachable and the registry is resolved."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    registry_digest: str
    field_count: int
    clickhouse: bool
    detail: str = ""


class SourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefix: str
    table: str


class SourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_digest: str
    count: int
    sources: list[SourceSummary]


class RegistryField(BaseModel):
    """One resolved field: the logical/physical name → SQL expression + output alias."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sql: str
    alias: str


class SourceFieldCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    registry_digest: str
    field_count: int
    fields: list[RegistryField]
