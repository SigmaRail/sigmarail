"""Static contracts for split-adjusted price returns and adjusted total returns."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "src/sigmarail/sql/schema"


def _sql(name: str) -> str:
    return (SCHEMA / name).read_text(encoding="utf-8")


def _assert_schema_and_projection(sql: str, table: str, fields: set[str]) -> None:
    table_ddl = sql.split(f"CREATE TABLE IF NOT EXISTS {table}", 1)[1].split("ENGINE =", 1)[0]
    view = sql.split(f"CREATE VIEW IF NOT EXISTS xform_{table}", 1)[1]
    view_columns = view.split("COMMENT", 1)[0]
    for field in fields:
        assert re.search(rf"`{re.escape(field)}`\s+Nullable\(Float64\)", table_ddl), field
        assert re.search(rf"^\s*{re.escape(field)},\s*$", view_columns, re.MULTILINE), field


def test_daily_adjusted_return_fields_are_defined_and_projected():
    sql = _sql("03-schema-daily_metrics_derived.sql")
    horizons = {"5d", "10d", "1m", "3m", "6m", "9m", "1y"}
    quarters = {"q1", "q2", "q3", "q4"}
    fields = {f"total_return_{horizon}" for horizon in horizons | quarters}
    _assert_schema_and_projection(sql, "daily_metrics_derived", fields)

    for field, lag in {
        "total_return_5d": 5,
        "total_return_10d": 10,
        "total_return_1m": 21,
        "total_return_3m": 63,
        "total_return_6m": 126,
        "total_return_9m": 189,
        "total_return_1y": 252,
    }.items():
        assert f"lagInFrame(closeadj, {lag})" in sql
        assert re.search(rf"closeadj\s*/\s*nullIf\(total_return_\w+_ago, 0\)\)\s*- 1 AS {field}", sql)

    for field in (f"total_return_{quarter}" for quarter in quarters):
        assert re.search(rf"AS {field}(?:,|\s)", sql)
    assert "closeadj" in sql.split("AS total_return_q4", 1)[0][-150:]


def test_weekly_adjusted_return_fields_are_defined_and_projected():
    sql = _sql("05-schema-weekly-metrics-derived.sql")
    fields = {f"total_return_{horizon}" for horizon in ("1w", "4w", "8w", "12w", "26w")}
    _assert_schema_and_projection(sql, "weekly_metrics_derived", fields)
    for weeks in (1, 4, 8, 12, 26):
        assert f"lagInFrame(closeadj, {weeks})" in sql
        assert f"AS total_return_{weeks}w" in sql


def test_screener_projects_daily_adjusted_return_horizons():
    sql = _sql("176-schema-screener_price_tech_daily.sql")
    fields = {f"total_return_{horizon}" for horizon in ("5d", "10d", "1m", "3m", "6m", "1y")}
    table_ddl = sql.split("CREATE TABLE IF NOT EXISTS screener_price_tech_daily", 1)[1].split("ENGINE =", 1)[0]
    view = sql.split("CREATE VIEW IF NOT EXISTS xform_screener_price_tech_daily", 1)[1]
    view_columns = view.split("COMMENT", 1)[0]
    for field in fields:
        assert f"`{field}` Nullable(Float64)" in table_ddl
        assert f"`{field}`" in view_columns
        assert f"dmd.{field}" in view
