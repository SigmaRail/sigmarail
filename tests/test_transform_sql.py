"""Unit tests for sigmarail.transform_sql (no ClickHouse required)."""

from pathlib import Path

import pytest

from sigmarail.transform_sql import (
    chunk_insert_sql,
    parse_transform,
    slug_for_name,
    view_name_for,
)

VIEW_SQL = """-- =============================================================================
-- Relative Strength Final Assembly
-- =============================================================================
CREATE OR REPLACE VIEW xform_relative_strength (
    ticker,
    date,
    yearly_performance,
    lastupdated
)
COMMENT '{"order":50,"target":"relative_strength","sources":["relative_strength_ranks"],"chunk_size":"1m"}'
AS
WITH updates_dates AS (
    SELECT date FROM relative_strength_ranks
    WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
)
SELECT
    r.ticker,
    r.date,
    r.yearly_performance,
    now() AS lastupdated
FROM relative_strength_ranks AS r FINAL
WHERE r.date IN (SELECT date FROM updates_dates)
  AND r.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
"""

VIEW_NO_COLS_SQL = """CREATE OR REPLACE VIEW xform_market_trend_template
COMMENT '{"order":57,"target":"market_trend_template","sources":["daily_metrics"],"chunk_size":"1m"}'
AS
SELECT ticker, date, trend FROM daily_metrics
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
"""

VIEW_FORCE_REFRESH_SQL = """CREATE OR REPLACE VIEW xform_daily_metrics (ticker, date, lastupdated)
COMMENT '{"order":1,"target":"daily_metrics","sources":["sep","sfp"],"chunk_size":"1w"}'
AS
SELECT ticker, date, now() AS lastupdated
FROM sep FINAL
WHERE ({force_refresh:UInt8} = 1 OR needs_update = 1)
  AND date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
"""

INSERT_SQL = """-- @transform-config
-- sources:
--   - sep
--   - sfp
-- target: daily_metrics
-- chunk_size: 1w

INSERT INTO daily_metrics (
    ticker,
    date,
    lastupdated
)
SELECT ticker, date, now() AS lastupdated
FROM sep FINAL
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
"""

INSERT_QUALIFIED_SQL = """-- @transform-config
-- sources:
--   - industry_group_strength
-- target: broad_market_breadth
-- chunk_size: 1m

INSERT INTO sigmarail.broad_market_breadth (date, pct_above)
SELECT date, pct_above FROM industry_group_strength
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
"""

INSERT_NO_COLS_SQL = """-- @transform-config
-- sources:
--   - sep
-- target: daily_price_sequence
-- target_timestamp_column: none

INSERT INTO daily_price_sequence
SELECT DISTINCT date FROM sep FINAL
"""


class TestParseView:
    def test_view_shape_and_name(self):
        spec = parse_transform(VIEW_SQL, path=Path("450-xform-relative-strength.sql"))
        assert spec.shape == "view"
        assert spec.view_name == "xform_relative_strength"

    def test_columns(self):
        spec = parse_transform(VIEW_SQL)
        assert spec.columns == ["ticker", "date", "yearly_performance", "lastupdated"]

    def test_config_from_comment(self):
        spec = parse_transform(VIEW_SQL)
        assert spec.config["order"] == 50
        assert spec.config["chunk_size"] == "1m"
        assert spec.target == "relative_strength"
        assert spec.sources == ["relative_strength_ranks"]

    def test_params(self):
        spec = parse_transform(VIEW_SQL)
        assert spec.param_names == ["chunk_start_date", "chunk_end_date"]
        assert spec.param_types["chunk_start_date"] == "String"

    def test_body_is_select(self):
        spec = parse_transform(VIEW_SQL)
        assert spec.body.startswith("WITH updates_dates")
        assert "{chunk_start_date:String}" in spec.body

    def test_no_column_list(self):
        spec = parse_transform(VIEW_NO_COLS_SQL)
        assert spec.shape == "view"
        assert spec.columns is None
        assert spec.target == "market_trend_template"

    def test_force_refresh_param(self):
        spec = parse_transform(VIEW_FORCE_REFRESH_SQL)
        assert spec.param_names == ["force_refresh", "chunk_start_date", "chunk_end_date"]
        assert spec.param_types["force_refresh"] == "UInt8"

    def test_order_fallback_to_filename(self):
        spec = parse_transform(VIEW_NO_COLS_SQL, path=Path("457-xform-market-trend-template.sql"))
        spec.config.pop("order")
        assert spec.order == 457 % 400


class TestParseInsert:
    def test_insert_shape(self):
        spec = parse_transform(INSERT_SQL, path=Path("01-daily-metrics.sql"))
        assert spec.shape == "insert"
        assert spec.view_name is None
        assert spec.target == "daily_metrics"
        assert spec.columns == ["ticker", "date", "lastupdated"]

    def test_header_config(self):
        spec = parse_transform(INSERT_SQL)
        assert spec.config["chunk_size"] == "1w"
        assert spec.sources == ["sep", "sfp"]

    def test_db_qualified_target_uses_config(self):
        spec = parse_transform(INSERT_QUALIFIED_SQL)
        assert spec.target == "broad_market_breadth"

    def test_no_col_list_insert(self):
        spec = parse_transform(INSERT_NO_COLS_SQL)
        assert spec.columns is None
        assert spec.config["target_timestamp_column"] == "none"


class TestNaming:
    def test_view_name_for_xform_file(self):
        assert view_name_for(Path("450-xform-relative-strength.sql")) == "xform_relative_strength"

    def test_view_name_for_legacy_file(self):
        assert view_name_for(Path("50-relative-strength.sql")) == "xform_relative_strength"

    def test_slug_for_name(self):
        assert slug_for_name("xform_relative_strength") == "relative-strength"


class TestChunkInsert:
    def test_insert_rendering(self):
        spec = parse_transform(VIEW_SQL)
        sql = chunk_insert_sql(
            spec, {"chunk_start_date": "2024-01-01", "chunk_end_date": "2024-01-31"}
        )
        assert sql == (
            "INSERT INTO relative_strength (ticker, date, yearly_performance, lastupdated) "
            "SELECT * FROM xform_relative_strength("
            "chunk_start_date='2024-01-01', chunk_end_date='2024-01-31')"
        )

    def test_uint8_param_bare(self):
        spec = parse_transform(VIEW_FORCE_REFRESH_SQL)
        sql = chunk_insert_sql(
            spec,
            {"chunk_start_date": "2024-01-01", "chunk_end_date": "2024-01-07", "force_refresh": 1},
        )
        assert "force_refresh=1" in sql
        assert "force_refresh='1'" not in sql

    def test_undeclared_params_not_passed(self):
        spec = parse_transform(VIEW_SQL)
        sql = chunk_insert_sql(
            spec,
            {"chunk_start_date": "2024-01-01", "chunk_end_date": "2024-01-31", "force_refresh": 1},
        )
        assert "force_refresh" not in sql

    def test_no_col_list_positional_insert(self):
        spec = parse_transform(VIEW_NO_COLS_SQL)
        sql = chunk_insert_sql(
            spec, {"chunk_start_date": "2024-01-01", "chunk_end_date": "2024-01-31"}
        )
        assert sql.startswith("INSERT INTO market_trend_template SELECT * FROM")
        assert "(" in sql.split("SELECT * FROM")[1]

    def test_missing_target_raises(self):
        spec = parse_transform(VIEW_SQL)
        spec.target = None
        with pytest.raises(ValueError):
            chunk_insert_sql(spec, {"chunk_start_date": "x", "chunk_end_date": "y"})


class TestRunTransformFile:
    def test_insert_shape_sends_body_with_parameters(self):
        calls = []

        class FakeClient:
            def command(self, sql, parameters=None, settings=None):
                calls.append((sql, parameters))

        from sigmarail.transform_sql import run_transform_file

        run_transform_file(
            FakeClient(), INSERT_SQL, {"chunk_start_date": "a", "chunk_end_date": "b"}
        )
        assert len(calls) == 1
        assert calls[0][0].startswith("INSERT INTO daily_metrics")
        assert calls[0][1]["chunk_start_date"] == "a"

    def test_view_shape_registers_then_inserts(self):
        calls = []

        class FakeClient:
            def command(self, sql, parameters=None, settings=None):
                calls.append(sql)

        from sigmarail.transform_sql import run_transform_file

        run_transform_file(
            FakeClient(), VIEW_SQL, {"chunk_start_date": "a", "chunk_end_date": "b"}
        )
        assert calls[0].lstrip().startswith("CREATE OR REPLACE VIEW xform_relative_strength")
        assert calls[1].startswith("INSERT INTO relative_strength")

    def test_scoped_view_name_renames_registration(self):
        calls = []

        class FakeClient:
            def command(self, sql, parameters=None, settings=None):
                calls.append(sql)

        from sigmarail.transform_sql import run_transform_file

        run_transform_file(
            FakeClient(),
            VIEW_SQL,
            {"chunk_start_date": "a", "chunk_end_date": "b"},
            view_name="xform_heal_relative_strength",
        )
        assert "VIEW xform_heal_relative_strength" in calls[0]
        assert "xform_heal_relative_strength(" in calls[1]

    def test_explicit_registration_replaces_create_if_missing_schema_ddl(self):
        from sigmarail.transform_sql import parse_transform, register_transform_view

        ddl = """CREATE VIEW IF NOT EXISTS xform_create_only (ticker)
COMMENT '{"order":1,"target":"daily_metrics","sources":[],"chunk_size":"1m"}'
AS SELECT 'A' AS ticker"""
        spec = parse_transform(ddl)
        calls = []

        class FakeClient:
            def command(self, sql):
                calls.append(sql)

        register_transform_view(FakeClient(), spec)
        assert calls[0].startswith("CREATE OR REPLACE VIEW xform_create_only")
        assert "IF NOT EXISTS" not in calls[0]
