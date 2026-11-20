"""Sidecar coverage: column-defining sources must have a sibling ``*.entities.yaml``.

Report mode lists gaps; strict mode promotes gaps to validation errors. Pre-commit
uses :func:`validate_staged_sources` for staged paths only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import SIDECAR_SUFFIX
from .ddl import insert_target, parse_create_tables, transform_config_target

# Paths relative to repo root that never require a sidecar (admin, grants, etc.).
_COVERAGE_SKIP_PREFIXES = (
    "sql/admin/",
    "sql/grants/",
)


def sidecar_for_source(source: Path) -> Path:
    """Sibling sidecar path for a ``.sql`` or ``.py`` source file."""
    if source.suffix in (".sql", ".py"):
        return source.with_suffix(SIDECAR_SUFFIX)
    return source.parent / f"{source.name}{SIDECAR_SUFFIX}"


def _skip_path(rel: str) -> bool:
    return any(rel.startswith(p) for p in _COVERAGE_SKIP_PREFIXES)


def _source_defines_columns(source: Path) -> bool:
    if not source.is_file():
        return False
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".sql":
        if parse_create_tables(text):
            return True
        return bool(transform_config_target(text) or insert_target(text))
    return False


def iter_sources_requiring_sidecar(repo_root: Path):
    """Yield repo-relative paths for sources that should have a sidecar."""
    schema_dir = repo_root / "sql" / "schema"
    if schema_dir.is_dir():
        for f in sorted(schema_dir.glob("*.sql")):
            rel = f.relative_to(repo_root).as_posix()
            if _skip_path(rel) or not _source_defines_columns(f):
                continue
            yield rel

    transform_dir = repo_root / "sql" / "transform"
    if transform_dir.is_dir():
        for f in sorted(transform_dir.rglob("*.sql")):
            rel = f.relative_to(repo_root).as_posix()
            if _skip_path(rel) or not _source_defines_columns(f):
                continue
            yield rel


def _sidecar_covers_source(sidecar: Path, source: Path) -> bool:
    if not sidecar.is_file():
        return False
    try:
        doc = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return False
    if not isinstance(doc, dict):
        return False
    if doc.get("coverage") == "skip":
        return True
    source_name = doc.get("source")
    if not source_name:
        return False
    return (sidecar.parent / str(source_name)).resolve() == source.resolve()


def coverage_gaps(repo_root: Path) -> list[str]:
    """Repo-relative source paths with no valid sibling sidecar."""
    gaps: list[str] = []
    for rel in iter_sources_requiring_sidecar(repo_root):
        source = repo_root / rel
        sidecar = sidecar_for_source(source)
        if not _sidecar_covers_source(sidecar, source):
            gaps.append(rel)
    return gaps


def validate_staged_sources(repo_root: Path, staged_paths: list[str]) -> list[str]:
    """Fail when a staged schema/transform ``.sql`` lacks a sibling sidecar."""
    errors: list[str] = []
    for rel in staged_paths:
        rel = rel.strip().lstrip("./")
        if not rel:
            continue
        if _skip_path(rel):
            continue
        path = repo_root / rel
        if not path.is_file():
            continue
        if path.suffix.lower() != ".sql":
            continue
        if not (
            rel.startswith("sql/schema/")
            or rel.startswith("sql/transform/")
        ):
            continue
        if not _source_defines_columns(path):
            continue
        sidecar = sidecar_for_source(path)
        if not _sidecar_covers_source(sidecar, path):
            expected = sidecar.relative_to(repo_root).as_posix()
            errors.append(
                f"{rel}: staged source change requires sibling sidecar {expected!r} "
                f"(or sidecar with coverage: skip)"
            )
    return errors
