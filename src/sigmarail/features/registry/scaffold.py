"""Draft entity sidecar entries from schema DDL ``COMMENT`` strings.

The entity layer is a scaffold: most ``*.entities.yaml`` sidecars are
``coverage: skip`` stubs. This module upgrades the *schema* sidecar for a mart
target by emitting one ``vera.mart.<table>.<column>`` concept entity per table
column, seeding ``title``/``definition`` from the column's DDL ``COMMENT``. It
never touches authored entities — re-runs are no-ops.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from ..sql_script import split_sql_statements

from .ddl import iter_schema_files, parse_create_tables

_ID_PREFIX = "vera.mart"


def _humanize(column: str) -> str:
    return column.replace("_", " ").replace(".", " ")


def _entity_for(table: str, column: str, comment: str | None) -> dict[str, Any]:
    ent: dict[str, Any] = {
        "id": f"{_ID_PREFIX}.{table}.{column}",
        "kind": "concept",
        "title": _humanize(column),
        "definition": comment if comment else f"TODO: define {_humanize(column)}",
        "binds": {"column": column, "table": table},
        "computability": "vera_native",
    }
    return ent


def _sidecar_path(schema_path: Path) -> Path:
    return schema_path.with_suffix("").with_name(schema_path.stem + ".entities.yaml")


def _load_sidecar(path: Path) -> dict[str, Any]:
    if path.is_file():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return doc if isinstance(doc, dict) else {}
    return {"version": 1}


def _xform_comment_target(sql_text: str) -> str | None:
    """``target`` from a ``CREATE VIEW ... COMMENT '<json>'`` transform."""
    m = re.search(r"(?is)\bCOMMENT\s+'((?:[^']|'')*)'", sql_text)
    if not m:
        return None
    try:
        cfg = json.loads(m.group(1).replace("''", "'"))
    except (json.JSONDecodeError, TypeError):
        return None
    target = cfg.get("target")
    return str(target).split(".")[-1] if target else None


def _transform_targets(repo_root: Path) -> list[str]:
    """All populate targets: xform view COMMENT JSON + legacy INSERT headers."""
    targets: list[str] = []
    for f in sorted((repo_root / "sql" / "schema").glob("*.sql")):
        for statement in split_sql_statements(f.read_text(encoding="utf-8")):
            if re.match(
                r"(?is)^\s*(?:--[^\n]*\n\s*)*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`?[A-Za-z_][\w]*`?\.)?`?xform_[A-Za-z0-9_]+`?\b",
                statement,
            ):
                t = _xform_comment_target(statement)
                if t:
                    targets.append(t)
    legacy_dir = repo_root / "sql" / "transform" / "metrics"
    if legacy_dir.is_dir():
        from .ddl import insert_target, transform_config_target

        for f in sorted(legacy_dir.glob("[0-9]*-*.sql")):
            text = f.read_text(encoding="utf-8")
            t = transform_config_target(text) or insert_target(text)
            if t:
                targets.append(t)
    return targets


def _table_to_schema_file(repo_root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for f in iter_schema_files(repo_root):
        for table in parse_create_tables(f.read_text(encoding="utf-8")):
            out.setdefault(table, f)
    return out


def scaffold_source(
    repo_root: Path,
    source_rel: str,
    *,
    externally_bound: set[tuple[str, str]] | None = None,
) -> dict[str, list[str]]:
    """Merge column entities into the schema file's sibling sidecar.

    ``source_rel`` is a repo-relative ``sql/schema/*.sql`` path.
    ``externally_bound`` holds ``(table, column)`` pairs already bound by
    *other* sidecars — authored entities always win anchor ownership.
    Returns ``{"added": [...], "skipped": [...]}`` of entity ids / column names.
    """
    repo_root = Path(repo_root)
    schema_path = repo_root / source_rel
    if not schema_path.is_file():
        raise FileNotFoundError(source_rel)

    tables = parse_create_tables(schema_path.read_text(encoding="utf-8"))
    if not tables:
        return {"added": [], "skipped": []}

    sidecar_path = _sidecar_path(schema_path)
    doc = _load_sidecar(sidecar_path)
    doc.setdefault("version", 1)
    doc["source"] = schema_path.name
    entities = doc.setdefault("entities", [])
    if not isinstance(entities, list):
        entities = []
        doc["entities"] = entities

    bound_cols = {
        str(e.get("binds", {}).get("column"))
        for e in entities
        if isinstance(e, dict) and isinstance(e.get("binds"), dict) and e["binds"].get("column")
    }
    existing_ids = {e.get("id") for e in entities if isinstance(e, dict)}

    added: list[str] = []
    skipped: list[str] = []
    for table, cols in tables.items():
        for column, meta in cols.items():
            eid = f"{_ID_PREFIX}.{table}.{column}"
            if (
                column in bound_cols
                or eid in existing_ids
                or (externally_bound is not None and (table, column) in externally_bound)
            ):
                skipped.append(column)
                continue
            entities.append(_entity_for(table, column, meta.get("comment")))
            added.append(eid)

    if entities:
        doc.pop("coverage", None)
    sidecar_path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return {"added": added, "skipped": skipped}


def _externally_bound_columns(repo_root: Path, exclude_sidecar: Path | None = None) -> set[tuple[str, str]]:
    """``(table, column)`` pairs bound by existing entities in *other* sidecars.

    Resolved via the compiler's anchor semantics, so ``binds.table`` overrides
    and source-derived tables are honored identically to ``by_anchor``.
    """
    from .compile import compile_registry

    compiled, _ = compile_registry(repo_root)
    bound: set[tuple[str, str]] = set()
    exclude = exclude_sidecar.relative_to(repo_root).as_posix() if exclude_sidecar else None
    for anchor, eid in (compiled.get("by_anchor") or {}).items():
        if not anchor.startswith("vera:") or "/" in anchor:
            continue
        ent = (compiled.get("entities") or {}).get(eid) or {}
        if exclude and ent.get("_sidecar") == exclude:
            continue
        m = re.fullmatch(r"vera:([A-Za-z_][A-Za-z0-9_]*)\.(.+)", anchor)
        if m:
            bound.add((m.group(1), m.group(2)))
    return bound


def scaffold_all_targets(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Scaffold every transform target's schema sidecar.

    Returns ``{table: {"schema": rel, "added": n, "skipped": n} | {"error": msg}}``.
    """
    repo_root = Path(repo_root)
    table_to_schema = _table_to_schema_file(repo_root)
    externally_bound = _externally_bound_columns(repo_root)
    report: dict[str, dict[str, Any]] = {}
    for target in sorted(set(_transform_targets(repo_root))):
        schema_path = table_to_schema.get(target)
        if schema_path is None:
            report[target] = {"error": "no schema file defines this table"}
            continue
        rel = schema_path.relative_to(repo_root).as_posix()
        try:
            res = scaffold_source(repo_root, rel, externally_bound=externally_bound)
        except Exception as e:  # noqa: BLE001 — report and continue per contract
            report[target] = {"error": str(e)}
            continue
        report[target] = {
            "schema": rel,
            "added": len(res["added"]),
            "skipped": len(res["skipped"]),
        }
    return report
