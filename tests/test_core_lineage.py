"""Guard SigmaRail's Sharadar-only schema boundary and transform dependency graph."""

import json
from pathlib import Path

from sigmarail.config import get_schema_files
from sigmarail.transform_sql import discover_transform_specs
from tools.generate_lineage_manifest import _actual_table_inputs, _load_objects

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = json.loads((ROOT / "spec/lineage-manifest.json").read_text(encoding="utf-8"))
PACKAGE_LINEAGE = json.loads(
    (ROOT / "src/sigmarail/spec/lineage-manifest.json").read_text(encoding="utf-8")
)
SCHEMA = json.loads((ROOT / "src/sigmarail/sql/schema-manifest.json").read_text(encoding="utf-8"))


def test_packaged_schema_is_exactly_the_explicit_core_allowlist():
    assert PACKAGE_LINEAGE == LINEAGE
    assert [path.name for path in get_schema_files()] == SCHEMA["files"]
    assert all(path.parent == ROOT / "src/sigmarail/sql/schema" for path in get_schema_files())
    forbidden = ("analyst", "estimate", "sentiment", "portfolio", "broker", "backtest")
    assert not any(any(token in name.lower() for token in forbidden) for name in SCHEMA["files"])


def test_all_included_tables_and_columns_resolve_only_to_sharadar_roots():
    raw = set(LINEAGE["raw_sharadar_tables"])
    assert raw == {
        "actions", "daily", "events", "metrics", "sep", "sf1", "sf2", "sf3",
        "sf3a", "sf3b", "sfp", "sp500", "tickers",
    }
    for table in LINEAGE["tables"]:
        roots = set(table["sharadar_roots"])
        assert roots and roots <= raw, table["name"]
        assert table["columns"], table["name"]
        for column in table["columns"]:
            if column["classification"] == "operational_metadata":
                assert column["lineage_roots"] == []
            else:
                assert column["lineage_roots"] == table["sharadar_roots"]


def test_external_overlay_fields_are_absent_and_explicitly_deferred():
    included = {table["name"] for table in LINEAGE["tables"]}
    table_columns = {
        table["name"]: {column["name"] for column in table["columns"]}
        for table in LINEAGE["tables"]
    }
    for table_name, fields in LINEAGE["excluded_fields"].items():
        assert not (set(fields) & table_columns.get(table_name, set()))
        assert all("external" in reason for reason in fields.values())
    assert {"screener_kb_daily", "screener_estimates_daily"} == {
        table["table"] for table in LINEAGE["deferred_external_tables"]
    }
    estimates = next(
        table for table in LINEAGE["deferred_external_tables"]
        if table["table"] == "screener_estimates_daily"
    )
    assert not estimates["included_sharadar_columns"]
    assert {"ticker", "date", "lastupdated"} <= set(estimates["excluded_columns"])
    assert "eps_cq_mean" in estimates["excluded_columns"]
    assert "sales_last_surprise_pct" in estimates["excluded_columns"]
    deferred = (
        LINEAGE["deferred_sharadar_features"]
        + LINEAGE["deferred_application_layers"]
    )
    assert all(item["table"] not in included for item in deferred)


def test_transform_sql_dependencies_match_declared_source_metadata():
    # _load_objects raises if a transform's COMMENT source list misses or adds
    # a real table reference in its SELECT body.
    raw, objects, _ = _load_objects()
    assert raw <= set(objects)


def test_unresolved_non_core_relation_is_not_accepted_as_sharadar_lineage():
    raw = set(LINEAGE["raw_sharadar_tables"])
    actual, unresolved = _actual_table_inputs("SELECT * FROM analyst_feed", raw)
    assert actual == []
    assert unresolved == ["analyst_feed"]


def test_every_derived_table_has_a_transform_and_topological_order():
    specs = discover_transform_specs()
    by_target = {spec.target: spec for spec in specs if spec.target}
    derived = {table["name"] for table in LINEAGE["tables"] if table["kind"] == "derived"}
    assert set(by_target) == derived
    for spec in specs:
        for source in spec.sources:
            if source in by_target:
                assert by_target[source].order < spec.order, (
                    source, by_target[source].order, spec.target, spec.order
                )
