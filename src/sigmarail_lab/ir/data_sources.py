"""Data Source specifications for graph policy - mirrors screener universe_query_v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DataSourceJoin(BaseModel):
    """Join specification matching screener join syntax."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["left_any", "inner", "left", "right", "full"] = "left_any"
    table: str
    on: list[str]  # join keys
    select: list[str] | None = None  # columns to select from joined table


class DataSourceWhere(BaseModel):
    """Where clause - simplified for runtime evaluation (not full AST)."""
    model_config = ConfigDict(extra="forbid")

    # Simple field=value filters for runtime
    filters: dict[str, Any] = Field(default_factory=dict)


class DataSourceSpec(BaseModel):
    """Specification for a data source — graph policy and store-backed VeraLabV1.

    Store-backed specs set ``Type`` (loader class), ``grain`` (session | ticker_date |
    daily), optional ``uses`` / ``score`` for regime policy (C-REGIME-POLICY-V1).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str  # unique name, e.g. "regime", "vix", "macro"
    table: str = ""  # ClickHouse table name (optional when Type implies loader)
    select: list[str] = Field(default_factory=list)  # columns to select
    date_column: str = "date"  # date column name for as_of filtering
    grain: str = "daily"  # daily | weekly | monthly | session | ticker_date
    where: DataSourceWhere | None = None
    joins: list[DataSourceJoin] | None = None

    # Store-backed catalog (C-VERALAB-V1 DataSources)
    loader_type: str | None = Field(default=None, alias="Type")
    as_of: str | None = None
    uses: list[str] = Field(default_factory=list)
    score: dict[str, Any] | None = None

    # Runtime config
    cache_per_date: bool = True  # cache entire row per date

    @classmethod
    def from_database(
        cls,
        name: str,
        table: str,
        client: Any,
        *,
        date_column: str = "date",
        grain: str = "daily",
        where: DataSourceWhere | None = None,
        exclude_columns: list[str] | None = None,
        include_columns: list[str] | None = None,
    ) -> "DataSourceSpec":
        """Build DataSourceSpec by inspecting the database table schema.

        Args:
            name: Unique name for this data source
            table: ClickHouse table name
            client: ChHttpClient instance for querying schema
            date_column: Date column name for filtering
            grain: Data grain (daily/weekly/monthly)
            where: Optional filter conditions
            exclude_columns: Columns to exclude from select
            include_columns: If specified, only include these columns
        """
        # Query table schema
        sql = f"DESCRIBE {table}"
        rows = client.query_json_each_row(sql, max_rows=1000)

        # Get all column names from schema
        all_columns = [row["name"] for row in rows if row.get("name")]

        # Filter columns
        if include_columns:
            select = [c for c in include_columns if c in all_columns]
        else:
            select = all_columns
        if exclude_columns:
            select = [c for c in select if c not in exclude_columns]

        # Ensure date_column is in select
        if date_column not in select:
            select.insert(0, date_column)

        return cls(
            name=name,
            table=table,
            select=select,
            date_column=date_column,
            grain=grain,
            where=where,
        )


# Default data source catalog - extendable via config
DEFAULT_DATA_SOURCES: dict[str, DataSourceSpec] = {
    "regime": DataSourceSpec(
name="regime",
table="market_regime_signals_daily",
select=[
    "date",
    "clamp_risk_off",
    "weekly_allocation_fraction",
    "weekly_allocation_tier",
    "spy_close",
    "spy_above200d",
    "breadth_200d",
    "breadth_50d",
    "distribution_count_25d",
    "daily_demote_streak",
    "effective_allocation_fraction",
    "effective_allocation_tier",
    "effective_source",
],
date_column="date",
grain="daily",
    ),
    "regime_composed": DataSourceSpec(
name="regime_composed",
table="regime_composed_daily",
select=[
    "date",
    "policy_name",
    "frac",
    "top_contributor",
],
date_column="date",
grain="daily",
where=DataSourceWhere(filters={"ticker": "SPY"}),
    ),
    "vix": DataSourceSpec(
name="vix",
table="market_context_daily",
select=[
    "date",
    "vix_spike_flag",
    "vix_contango_proxy",
    "vix_close",
    "vix_term_structure",
],
date_column="date",
grain="daily",
    ),
    "macro": DataSourceSpec(
name="macro",
table="macro_economic_daily",
select=[
    "date",
    "real_gdp_qoq",
    "cpi_yoy",
    "unemployment_rate",
    "fed_funds_rate",
],
date_column="date",
grain="daily",
    ),
    "technical": DataSourceSpec(
name="technical",
table="symbol_technical_features_daily",
select=[
    "date",
    "ticker",
    "close",
    "sma20d",
    "sma50d",
    "sma200d",
    "rsi14d",
    "atr_14_pct",
    "rs_rating",
],
date_column="date",
grain="daily",
    ),
}


class DataSourceCatalog(BaseModel):
    """Catalog of data sources for graph policy."""
    model_config = ConfigDict(extra="forbid")

    sources: dict[str, DataSourceSpec] = Field(default_factory=lambda: DEFAULT_DATA_SOURCES.copy())

    def get(self, name: str) -> DataSourceSpec | None:
        return self.sources.get(name)

    def register(self, spec: DataSourceSpec) -> None:
        self.sources[spec.name] = spec

    def get_select_columns(self, name: str) -> list[str]:
        spec = self.get(name)
        return spec.select if spec else []

    def build_query(self, name: str, as_of: str, *, ticker: str | None = None) -> str:
        """Build ClickHouse query for a source at a specific date."""
        spec = self.get(name)
        if not spec:
            raise ValueError(f"Unknown data source: {name}")

        cols = ", ".join(spec.select)
        date_col = spec.date_column
        where_clause = f"{date_col} = toDate('{as_of}')"

        if spec.where and spec.where.filters:
            for k, v in spec.where.filters.items():
                if isinstance(v, str):
                    where_clause += f" AND {k} = '{v}'"
                else:
                    where_clause += f" AND {k} = {v}"

        if ticker and "ticker" in spec.select:
            where_clause += f" AND ticker = '{ticker}'"

        if spec.joins:
            # For now, use simple approach - joins would need more complex handling
            join_clauses = []
            for join in spec.joins:
                join_on = " AND ".join(join.on)
                join_clauses.append(
                    f"{join.type.upper()} JOIN {join.table} ON {join_on}"
                )
            join_sql = " ".join(join_clauses)
            return f"""
            SELECT {cols}
            FROM {spec.table}
            {join_sql}
            WHERE {where_clause}
            LIMIT 1
            FORMAT JSONEachRow
            """

        return f"""
        SELECT {cols}
        FROM {spec.table}
        WHERE {where_clause}
        LIMIT 1
        FORMAT JSONEachRow
        """

    @classmethod
    def from_database(cls, client: Any, *, name_prefix: str | None = None) -> "DataSourceCatalog":
        """Build catalog by discovering tables in the database.

        Scans for known pattern tables and creates DataSourceSpecs from their schemas.
        """
        catalog = cls()
        # This would require knowing which tables are data sources
        # For now, return empty catalog - users register sources explicitly
        return catalog

    def discover_from_client(self, client: Any, table_names: list[str]) -> None:
        """Discover and register data sources from a list of table names."""
        for table in table_names:
            try:
                spec = DataSourceSpec.from_database(
                    name=table.replace("_daily", ""),
                    table=table,
                    client=client,
                )
                self.register(spec)
            except Exception:
                # Skip tables that can't be read
                pass