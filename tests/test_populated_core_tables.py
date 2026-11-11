"""Full-populate integration assertions for the Sharadar-only schema."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = json.loads((ROOT / "spec/lineage-manifest.json").read_text(encoding="utf-8"))
ON_HOLD = {"screener_vcp_pivot_daily"}
EMPTY_SOURCE_FIXTURES = {"metrics", "sf2"}


def _count(client, table: str) -> int:
    return int(client.query(f"SELECT count() FROM `{table}`").result_rows[0][0])


def test_all_active_derived_tables_have_populated_rows(global_client) -> None:
    derived = {row["name"] for row in LINEAGE["tables"] if row["kind"] == "derived"}
    assert ON_HOLD <= derived
    empty = sorted(table for table in derived - ON_HOLD if _count(global_client, table) == 0)
    assert not empty, f"Active derived tables are empty after sigmarail-populate: {empty}"


def test_only_documented_source_fixtures_are_empty(global_client) -> None:
    sources = {row["name"] for row in LINEAGE["tables"] if row["kind"] == "sharadar_source"}
    empty = {table for table in sources if _count(global_client, table) == 0}
    assert empty <= EMPTY_SOURCE_FIXTURES
    for table in sources - EMPTY_SOURCE_FIXTURES:
        assert _count(global_client, table) > 0, f"Sharadar fixture table {table} is unexpectedly empty"
    for table in EMPTY_SOURCE_FIXTURES & sources:
        assert _count(global_client, table) == 0


def test_vcp_empty_state_matches_on_hold_schedule(global_client) -> None:
    from sigmarail.transform_sql import discover_transform_specs

    spec = next(s for s in discover_transform_specs() if s.target == "screener_vcp_pivot_daily")
    assert spec.config.get("on_hold") is True
    assert _count(global_client, "screener_vcp_pivot_daily") == 0
