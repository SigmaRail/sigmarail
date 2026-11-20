"""Core module query contracts and ClickHouse execution checks."""

from __future__ import annotations

from datetime import date

import pytest

from sigmarail_spec.data_query import DataQueryV1, QueryPredicate


def _field_id(table: str, column_name: str) -> str:
    from sigmarail.query import _core_tables

    table_row = _core_tables()[table]
    return next(column["id"] for column in table_row["columns"] if column["name"] == column_name)


def test_compile_query_uses_declared_ids_and_parameterized_values() -> None:
    from sigmarail.query import compile_query

    query = DataQueryV1(
        module_id="sigmarail.core",
        dataset_id="sigmarail.core.screener_price_tech_daily",
        select=[
            {"field_id": _field_id("screener_price_tech_daily", "ticker")},
            {"field_id": _field_id("screener_price_tech_daily", "close")},
        ],
        as_of_date=date(2024, 12, 31),
        where=QueryPredicate(op="eq", field_id=_field_id("screener_price_tech_daily", "ticker"), value="AAPL"),
    )

    sql, parameters = compile_query(query)

    assert "screener_price_tech_daily" in sql
    assert "`screener_price_tech_daily` AS d0 FINAL" in sql
    assert "AAPL" not in sql
    assert "AAPL" in parameters.values()
    assert parameters["as_of_date"] == "2024-12-31"


def test_compile_joined_query_places_clickhouse_alias_before_final() -> None:
    from sigmarail.query import _module_manifest, compile_query

    relation = next(
        row for row in _module_manifest()["joins"]
        if row["from_dataset"] == "sigmarail.core.screener_price_tech_daily"
        and row["to_dataset"] == "sigmarail.core.screener_fundamentals_daily"
    )
    query = DataQueryV1(
        module_id="sigmarail.core",
        dataset_id="sigmarail.core.screener_price_tech_daily",
        joins=[{"relationship_id": relation["id"]}],
        select=[
            {"field_id": _field_id("screener_price_tech_daily", "ticker")},
            {"field_id": _field_id("screener_fundamentals_daily", "mrt_roe"), "alias": "roe"},
        ],
        as_of_date=date(2024, 12, 31),
    )

    sql, _ = compile_query(query)

    assert "`screener_price_tech_daily` AS d0 FINAL" in sql
    assert "`screener_fundamentals_daily` AS d1 FINAL" in sql


def test_compile_query_rejects_undeclared_join() -> None:
    from sigmarail.query import compile_query

    query = DataQueryV1(
        module_id="sigmarail.core",
        dataset_id="sigmarail.core.screener_price_tech_daily",
        joins=[{"relationship_id": "sigmarail.core.join.not_declared"}],
        select=[{"field_id": _field_id("screener_price_tech_daily", "ticker")}],
        as_of_date=date(2024, 12, 31),
    )

    with pytest.raises(ValueError, match="not declared"):
        compile_query(query)


@pytest.mark.integration
def test_core_query_reads_synthetic_rows_and_declared_join(global_client) -> None:
    from sigmarail.query import _module_manifest, query_dataset

    relation = next(
        row for row in _module_manifest()["joins"]
        if row["from_dataset"] == "sigmarail.core.screener_price_tech_daily"
        and row["to_dataset"] == "sigmarail.core.screener_fundamentals_daily"
    )
    query = DataQueryV1(
        module_id="sigmarail.core",
        dataset_id="sigmarail.core.screener_price_tech_daily",
        joins=[{"relationship_id": relation["id"]}],
        select=[
            {"field_id": _field_id("screener_price_tech_daily", "ticker")},
            {"field_id": _field_id("screener_price_tech_daily", "date")},
            {"field_id": _field_id("screener_price_tech_daily", "close")},
            {"field_id": _field_id("screener_fundamentals_daily", "mrt_roe"), "alias": "roe"},
        ],
        as_of_date=date(2024, 12, 31),
        where=QueryPredicate(op="eq", field_id=_field_id("screener_price_tech_daily", "ticker"), value="AAPL"),
        limit=10,
    )

    result = query_dataset(query, client=global_client)

    assert "error" not in result, result
    assert result["row_count"] == 1
    assert result["rows"][0]["ticker"] == "AAPL"
    assert result["rows"][0]["date"] == "2024-12-31"
    assert result["rows"][0]["close"] is not None
