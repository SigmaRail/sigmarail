"""catalog domain: table / join / column surface.

Single source of truth is ``sql/schema/screener_l7_join.yaml`` + the L7 ``screener_*``
DDL (via ``l7_from.column_homes()``), plus the static ADM entity registry.
"""
from __future__ import annotations

from typing import Any


def _manifest() -> dict[str, Any]:
    from vera_query_core.ir.l7_from import _join_manifest

    return _join_manifest()


def list_tables() -> dict[str, Any]:
    """List the L7 screener tables and their join metadata (spine/grain/prefix)."""
    manifest = _manifest()
    return {"spine": manifest["spine"], "join_type": manifest.get("join_type", "any"), "tables": manifest["tables"]}


def list_columns() -> dict[str, Any]:
    """List the screener column surface (logical/physical name -> owning table)."""
    from vera_query_core.ir.l7_from import column_homes

    manifest = _manifest()
    prefix_to_table = {e["prefix"]: e["table"] for e in manifest["tables"]}
    columns = {
        name: {
            "prefix": prefix,
            "physical": physical,
            "table": prefix_to_table.get(prefix, prefix),
        }
        for name, (prefix, physical) in sorted(column_homes().items())
    }
    return {"count": len(columns), "columns": columns}


def list_join_paths(from_entity: str | None = None, to_entity: str | None = None) -> dict[str, Any]:
    """Join paths: the L7 spine star (from manifest) + cross-entity ADM paths."""
    from vera_query_core import platform_tools

    manifest = _manifest()
    spine = manifest["spine"]
    star = []
    for entry in manifest["tables"]:
        prefix = entry["prefix"]
        if prefix == spine:
            continue
        grain = entry.get("grain", ["ticker", "date"])
        on = " AND ".join(f"{spine}.{k} = {prefix}.{k}" for k in grain)
        star.append({"from": spine, "to": entry["table"], "on": on, "note": "L7 spine star"})

    adm = list(platform_tools._ADM_JOIN_PATHS)
    if from_entity:
        fe = from_entity.strip().lower()
        adm = [p for p in adm if p["from"] == fe]
    if to_entity:
        te = to_entity.strip().lower()
        adm = [p for p in adm if p["to"] == te]
    return {"star": star, "adm": adm}


def describe_entity(entity: str) -> dict[str, Any]:
    """Static ADM entity metadata (tables/keys/anchors; no ClickHouse needed)."""
    from vera_query_core import platform_tools

    name = (entity or "").strip().lower()
    meta = dict(platform_tools._ADM_ENTITIES.get(name) or {})
    if not meta:
        raise ValueError(f"unknown entity {entity!r}; known: {', '.join(sorted(platform_tools._ADM_ENTITIES))}")
    if name == "security":
        meta["tables"] = platform_tools._security_tables()
    return {"entity": name, "meta": meta}
