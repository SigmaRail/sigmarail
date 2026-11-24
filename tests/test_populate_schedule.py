"""Ported Vera populate schedule contracts for SigmaRail's schema-only pipeline."""

from unittest.mock import MagicMock, patch

from sigmarail.config import get_schema_contract
from sigmarail.populate import DataPopulator, _metric_sql_sort_key
from sigmarail.transform_sql import discover_transform_specs


def test_numeric_transform_filenames_sort_by_number_not_lexically(tmp_path):
    early = tmp_path / "98-early.sql"
    late = tmp_path / "100-late.sql"
    assert _metric_sql_sort_key(early) < _metric_sql_sort_key(late)


def test_dependency_transforms_precede_their_consumers():
    specs = discover_transform_specs()
    by_target = {spec.target: spec for spec in specs if spec.target}
    for spec in specs:
        for source in spec.sources:
            if source in by_target:
                assert by_target[source].order < spec.order, (
                    source, by_target[source].order, spec.target, spec.order
                )


def test_all_schedule_excludes_explicitly_held_vcp_transform():
    pop = DataPopulator.__new__(DataPopulator)
    pop.modules = []
    pop.client = MagicMock()
    pop.allowed_transform_targets = {
        table["name"] for table in get_schema_contract()
    } - pop.BASE_DATA_TABLES
    with patch("sigmarail.populate.transform_catalog", return_value=[]):
        specs = pop._get_transform_specs(["all"])
    assert all(spec.target != "screener_vcp_pivot_daily" for spec in specs)


def test_explicit_vcp_request_remains_held():
    pop = DataPopulator.__new__(DataPopulator)
    pop.modules = []
    pop.client = MagicMock()
    pop.allowed_transform_targets = {
        table["name"] for table in get_schema_contract()
    } - pop.BASE_DATA_TABLES
    with patch("sigmarail.populate.transform_catalog", return_value=[]):
        specs = pop._get_transform_specs(["screener_vcp_pivot_daily"])
    assert not any(spec.target == "screener_vcp_pivot_daily" for spec in specs)


def test_selected_extension_transform_is_discovered_and_selectable():
    pop = DataPopulator.__new__(DataPopulator)
    pop.modules = ["analyst_estimates"]
    pop.client = MagicMock()
    pop.allowed_transform_targets = {
        table["name"] for table in get_schema_contract(pop.modules)
    } - pop.BASE_DATA_TABLES
    with patch("sigmarail.populate.transform_catalog", return_value=[]):
        tables = set(pop._get_all_derived_tables())
        specs = pop._get_transform_specs(["ext_analyst_estimates_screener_estimates_daily"])
    assert "ext_analyst_estimates_screener_estimates_daily" in tables
    assert any(spec.target == "ext_analyst_estimates_screener_estimates_daily" for spec in specs)


def test_actuals_projection_joins_by_public_availability_time():
    from pathlib import Path

    sql = (
        Path(__file__).parents[1]
        / "src/sigmarail/sql/extensions/analyst_estimates/197-schema-screener_estimates_daily.sql"
    ).read_text()
    schema = (
        Path(__file__).parents[1]
        / "src/sigmarail/sql/extensions/analyst_estimates/196-schema-analyst_actuals.sql"
    ).read_text()
    consensus_schema = (
        Path(__file__).parents[1]
        / "src/sigmarail/sql/extensions/analyst_estimates/195-schema-analyst_consensus_asof.sql"
    ).read_text()
    assert "`available_at` DateTime64(3, 'America/New_York')" in schema
    assert "available_at > toDateTime64(0, 3, 'America/New_York')" in sql
    assert "px.date >= se.period_end_date" not in sql
    assert "15:59:59.999" in sql
    assert "available_at > toDateTime64(0, 3, 'America/New_York')" in sql
    assert "ASOF LEFT JOIN pivoted AS e" in sql
    assert "cur.available_at" in sql
    assert "cur.available_at - INTERVAL 90 DAY" in sql
    assert "cur.vendor = prior.vendor" in sql
    assert "snaps_single_vendor" in sql
    assert "`available_at` DateTime64(3, 'America/New_York')" in consensus_schema


def test_external_module_source_tables_use_the_extension_namespace():
    modules = {
        "aaii": ["ext_aaii_sentiment_survey"],
        "analyst_estimates": [
            "ext_analyst_estimates_analyst_consensus_asof",
            "ext_analyst_estimates_analyst_actuals",
        ],
        "etf": [
            "ext_etf_etf_classifications",
            "ext_etf_etf_holdings_snapshot",
            "ext_etf_etf_sector_weights_snapshot",
            "ext_etf_index_proxy_catalog",
        ],
        "macro": ["ext_macro_economic_daily"],
    }
    for module, expected in modules.items():
        contract = get_schema_contract([module])
        names = {table["name"] for table in contract}
        assert set(expected) <= names
        assert all(name.startswith(f"ext_{module}_") for name in expected)
