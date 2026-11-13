"""Compile co-located ``*.entities.yaml`` sidecars into one generated aggregate.

The aggregate (``VeraBase/registry/compiled.json``) is a build artifact like
``sql/lineage/*.json`` -- committed, deterministic, never hand-edited.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from . import COMPILED_RELATIVE, SIDECAR_SUFFIX
from .ddl import table_for_source

# Directories that may contain sidecars (keeps the walk fast + scoped).
_WALK_DIRS = ("sql/schema", "sql/transform", "src")


def _repo_root() -> Path:
    # .../VeraBase/src/sigmarail.features/registry/compile.py -> VeraBase/
    return Path(__file__).resolve().parents[3]


def iter_sidecars(repo_root: Path):
    seen: set[Path] = set()
    for rel in _WALK_DIRS:
        base = repo_root / rel
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*" + SIDECAR_SUFFIX)):
            if f not in seen:
                seen.add(f)
                yield f


def _anchor_for(entity: dict[str, Any], source_path: Path) -> tuple[str | None, str | None]:
    """Return ``(anchor, table)`` for an entity given its sibling source."""
    binds = entity.get("binds") or {}
    if not isinstance(binds, dict):
        return None, None
    column = binds.get("column")
    if column:
        table = binds.get("table") or table_for_source(source_path)
        if table:
            return f"vera:{table}.{column}", table
        return None, None
    symbol = binds.get("symbol")
    if symbol:
        return f"vera:ir/{source_path.stem}.{symbol}", None
    return None, None


def compile_registry(repo_root: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Walk sidecars and build the compiled aggregate. Returns ``(compiled, errors)``."""
    root = repo_root or _repo_root()
    errors: list[str] = []
    entities: dict[str, dict[str, Any]] = {}
    by_anchor: dict[str, str] = {}
    alias_to_id: dict[str, str] = {}
    by_source: dict[str, list[str]] = {}
    warned_by: dict[str, list[str]] = {}

    for sidecar in iter_sidecars(root):
        rel_sidecar = sidecar.relative_to(root).as_posix()
        try:
            doc = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            errors.append(f"{rel_sidecar}: invalid YAML ({e})")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{rel_sidecar}: top-level must be a mapping")
            continue
        source_name = doc.get("source")
        if not source_name:
            errors.append(f"{rel_sidecar}: missing 'source'")
            continue
        source_path = sidecar.parent / str(source_name)
        rel_source = source_path.relative_to(root).as_posix() if source_path.exists() else str(source_name)
        ent_list = doc.get("entities") or []
        if not isinstance(ent_list, list):
            errors.append(f"{rel_sidecar}: 'entities' must be a list")
            continue
        for raw in ent_list:
            if not isinstance(raw, dict):
                errors.append(f"{rel_sidecar}: entity entries must be mappings")
                continue
            eid = raw.get("id")
            kind = raw.get("kind")
            if not eid or not kind:
                errors.append(f"{rel_sidecar}: entity missing 'id' or 'kind'")
                continue
            if eid in entities:
                errors.append(f"duplicate entity id {eid!r} ({rel_sidecar} and {entities[eid]['_source']})")
                continue
            anchor, table = _anchor_for(raw, source_path)
            ent = dict(raw)
            ent["_source"] = rel_source
            ent["_sidecar"] = rel_sidecar
            ent["_anchor"] = anchor
            ent["_table"] = table
            entities[eid] = ent
            by_source.setdefault(rel_source, []).append(eid)
            if anchor:
                if anchor in by_anchor:
                    errors.append(f"duplicate anchor {anchor!r} ({eid} and {by_anchor[anchor]})")
                else:
                    by_anchor[anchor] = eid
            for alias in raw.get("aliases") or []:
                alias_to_id.setdefault(str(alias), eid)
            target = raw.get("points_to")
            if target:
                warned_by.setdefault(str(target), []).append(eid)

    compiled = {
        "generated": True,
        "generator": "vera-registry",
        "schema_version": 1,
        "entities": {k: entities[k] for k in sorted(entities)},
        "by_id": sorted(entities),
        "by_anchor": {k: by_anchor[k] for k in sorted(by_anchor)},
        "alias_to_id": {k: alias_to_id[k] for k in sorted(alias_to_id)},
        "by_source": {k: sorted(by_source[k]) for k in sorted(by_source)},
        "warned_by": {k: sorted(warned_by[k]) for k in sorted(warned_by)},
    }
    return compiled, errors


def dumps(compiled: dict[str, Any]) -> str:
    return json.dumps(compiled, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def compiled_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / COMPILED_RELATIVE


def write_compiled(compiled: dict[str, Any], repo_root: Path | None = None) -> Path:
    out = compiled_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(compiled), encoding="utf-8")
    return out


def load_compiled(repo_root: Path | None = None) -> dict[str, Any] | None:
    p = compiled_path(repo_root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
