"""SQL contract for ChartMill Q2/Q3 YoY acceleration and PMI flags."""

from __future__ import annotations

from pathlib import Path

SQL_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "sigmarail" / "sql"
    / "schema"
    / "167-schema-arq_derived.sql"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "sigmarail" / "sql" / "schema" / "167-schema-arq_derived.sql"
)
L7_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "sigmarail" / "sql"
    / "schema"
    / "177-schema-screener_fundamentals_daily.sql"
)
DAILY_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "sigmarail" / "sql" / "schema" / "15-schema-daily_fundamentals.sql"
)
DAILY_SQL = (
    Path(__file__).resolve().parents[1]
    / "src" / "sigmarail" / "sql"
    / "schema"
    / "15-schema-daily_fundamentals.sql"
)


def test_arq_derived_sql_defines_q2_q3_and_pmi() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    for col in (
        "eps_acceleration_q2",
        "eps_acceleration_q3",
        "revenue_acceleration_q2",
        "revenue_acceleration_q3",
        "pmi_up_q2",
        "pmi_up_q3",
    ):
        assert col in sql, col
    assert "THEN NULL" in sql
    assert "ALTER TABLE" not in sql or "UPDATE" not in sql


def test_schemas_expose_l7_prefixed_flags() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    l7 = L7_PATH.read_text(encoding="utf-8")
    daily = DAILY_PATH.read_text(encoding="utf-8")
    for col in (
        "eps_acceleration_q2",
        "eps_acceleration_q3",
        "pmi_up_q3",
    ):
        assert col in schema, col
    for col in (
        "arq_eps_acceleration_q2",
        "arq_eps_acceleration_q3",
        "arq_revenue_acceleration_q2",
        "arq_revenue_acceleration_q3",
        "arq_pmi_up_q2",
        "arq_pmi_up_q3",
    ):
        assert col in l7, col
        assert col in daily, col


def test_daily_fundamentals_sql_honors_force_refresh() -> None:
    sql = DAILY_SQL.read_text(encoding="utf-8")
    assert "{force_refresh:UInt8}" in sql
