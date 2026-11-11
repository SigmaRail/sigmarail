"""Unit tests for sigmarail.populate freshness edge cases (no ClickHouse required)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sigmarail.populate import DataPopulator
from sigmarail.transform_sql import parse_transform


def test_resolve_transform_start_date_uses_explicit():
    pop = DataPopulator.__new__(DataPopulator)
    sql = Path("01-daily-metrics.sql")
    assert pop._resolve_transform_start_date(sql, "2026-01-01", False) == "2026-01-01"


def test_resolve_transform_start_date_force_refresh_default():
    pop = DataPopulator.__new__(DataPopulator)
    sql = Path("01-daily-metrics.sql")
    assert pop._resolve_transform_start_date(sql, None, True) == "1999-01-01"


def test_get_freshness_skips_non_temporal_source():
    pop = DataPopulator.__new__(DataPopulator)
    pop.client = MagicMock()
    assert (
        pop._get_freshness_start_date_for_source("tickers", "entity_aliases")
        is None
    )
    pop.client.query.assert_not_called()


def test_get_freshness_skips_when_target_timestamp_none():
    pop = DataPopulator.__new__(DataPopulator)
    pop.client = MagicMock()
    assert (
        pop._get_freshness_start_date_for_source(
            "sep", "daily_price_sequence", target_timestamp_col="none"
        )
        is None
    )
    pop.client.query.assert_not_called()


def test_chunk_sql_params_force_refresh_when_sql_supports_it():
    pop = DataPopulator.__new__(DataPopulator)
    sql = "SELECT 1 WHERE {force_refresh:UInt8} = 1"
    assert pop._chunk_sql_params(sql, "2026-06-01", "2026-06-12", force_refresh=True) == {
        "chunk_start_date": "2026-06-01",
        "chunk_end_date": "2026-06-12",
        "force_refresh": 1,
    }
    assert pop._chunk_sql_params(sql, "2026-06-01", "2026-06-12", force_refresh=False)[
        "force_refresh"
    ] == 0


def test_daily_fundamentals_sql_injects_force_refresh():
    pop = DataPopulator.__new__(DataPopulator)
    sql = (
        Path(__file__).resolve().parents[1]
        / "src" / "sigmarail" / "sql"
        / "schema"
        / "15-schema-daily_fundamentals.sql"
    ).read_text(encoding="utf-8")
    params = pop._chunk_sql_params(sql, "2024-02-01", "2024-02-29", force_refresh=True)
    assert params["force_refresh"] == 1


def test_chunk_sql_params_omits_force_refresh_without_placeholder():
    pop = DataPopulator.__new__(DataPopulator)
    sql = "SELECT 1 WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}"
    params = pop._chunk_sql_params(sql, "2026-06-01", "2026-06-12", force_refresh=True)
    assert "force_refresh" not in params


def test_transform_can_scope_partition_local_final_setting():
    pop = DataPopulator.__new__(DataPopulator)
    sql = (
        Path(__file__).resolve().parents[1]
        / "src" / "sigmarail" / "sql"
        / "schema"
        / "83-schema-stage_analysis.sql"
    ).read_text(encoding="utf-8")
    spec = parse_transform(sql, name="stage-analysis")

    settings = pop._populate_query_settings(spec)

    assert settings["do_not_merge_across_partitions_select_final"] == 1


def test_transform_rejects_invalid_partition_local_final_setting():
    pop = DataPopulator.__new__(DataPopulator)
    spec = parse_transform(
        """CREATE OR REPLACE VIEW xform_test COMMENT '{\"order\": 1, \"target\": \"test\", \"sources\": [], \"chunk_size\": \"1m\", \"do_not_merge_across_partitions_select_final\": 2}' AS SELECT 1""",
        name="test",
    )

    with pytest.raises(ValueError, match="must be 0 or 1"):
        pop._populate_query_settings(spec)




def test_get_freshness_for_transform_skips_sep_when_target_has_no_timestamp():
    pop = DataPopulator.__new__(DataPopulator)
    pop.client = MagicMock()
    sql = Path(__file__).resolve().parents[1] / "src/sigmarail/sql/schema/06-schema-daily_price-sequence.sql"
    with patch.object(pop, "_parse_transform_config") as mock_cfg:
        mock_cfg.return_value = {
            "sources": ["sep", "sfp"],
            "target": "daily_price_sequence",
            "source_timestamp_column": "lastupdated",
            "target_timestamp_column": "none",
        }
        assert pop._get_freshness_start_date_for_transform(sql) is None
    pop.client.query.assert_not_called()
