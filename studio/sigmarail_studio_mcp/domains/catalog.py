"""Catalog domain backed by SigmaRail's generated dataset and relationship registry."""
from __future__ import annotations

from typing import Any


def _manifest() -> dict[str, Any]:
    from sigmarail.query import _module_manifest

    return _module_manifest()


def list_tables() -> dict[str, Any]:
    """List registered core datasets and relationship metadata."""
    manifest = _manifest()
    return {
        "spine": "screener_price_tech_daily",
        "join_type": "declared_relationships",
        "tables": manifest["datasets"],
        "joins": manifest["joins"],
    }


def list_columns() -> dict[str, Any]:
    """List registered core fields, physical columns and owning datasets."""
    from sigmarail.query import _column_index, _datasets

    datasets = _datasets()
    columns = {}
    candidates: dict[str, list[tuple[str, str, str, dict[str, Any]]]] = {}
    for field_id, (dataset_id, physical, meta) in sorted(_column_index().items()):
        name = str(meta["name"])
        candidates.setdefault(name, []).append((field_id, dataset_id, physical, meta))
    for name, choices in candidates.items():
        field_id, dataset_id, physical, meta = next(
            (row for row in choices if row[1] == "sigmarail.core.screener_price_tech_daily"),
            choices[0],
        )
        columns[name] = {
            "id": field_id,
            "dataset_id": dataset_id,
            "physical": physical,
            "table": datasets[dataset_id]["table"],
            "type": meta.get("type"),
            "description": meta.get("comment", ""),
        }
    return {"count": len(columns), "columns": columns}


def list_join_paths(from_entity: str | None = None, to_entity: str | None = None) -> dict[str, Any]:
    """Return declared SigmaRail join relationships (core only)."""
    manifest = _manifest()
    joins = list(manifest["joins"])
    if from_entity:
        joins = [row for row in joins if row["from_dataset"] == from_entity.strip()]
    if to_entity:
        joins = [row for row in joins if row["to_dataset"] == to_entity.strip()]
    return {"relationships": joins}


def describe_entity(entity: str) -> dict[str, Any]:
    """Describe one generated core dataset by its stable ID or physical table name."""
    from sigmarail.query import _core_tables, _datasets

    tables = _core_tables()
    datasets = _datasets()
    name = (entity or "").strip()
    dataset = datasets.get(name)
    if dataset is None:
        dataset = next((row for row in datasets.values() if row["table"] == name), None)
    if dataset is None:
        raise ValueError(f"unknown SigmaRail core dataset {entity!r}")
    return {"entity": dataset["dataset_id"], "meta": {**dataset, "schema": tables[dataset["table"]]}}
