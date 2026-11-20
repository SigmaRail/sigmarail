"""Validation for the entity registry: locality, anchors, drift (git-only).

Locality is the core rule: every ``binds`` in a sidecar must resolve inside the
sidecar's *sibling* source. A sidecar may not document a column defined in
another file. Runs offline (``PLATFORM_GATE_SKIP_CH=1``).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import SIDECAR_SUFFIX
from .compile import compile_registry, compiled_path, dumps, iter_sidecars
from .ddl import column_exists_in_source

_VALID_KINDS = {"concept", "adm_entity", "instrument", "alias_warning"}
_VALID_COMPUTABILITY = {"vera_native", "derivable", "narrative_only"}
_VERABASE_SOURCE_PREFIXES = ("sql/", "src/")


def validate_registry(repo_root: Path) -> list[str]:
    errors: list[str] = []
    compiled, compile_errors = compile_registry(repo_root)
    errors.extend(compile_errors)
    known_ids = set(compiled.get("by_id", []))

    for sidecar in iter_sidecars(repo_root):
        rel = sidecar.relative_to(repo_root).as_posix()
        try:
            doc = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue  # already reported by compile
        if not isinstance(doc, dict):
            continue
        source_name = doc.get("source")
        if not source_name:
            continue
        source_path = sidecar.parent / str(source_name)
        if not source_path.is_file():
            errors.append(f"{rel}: orphan sidecar -- sibling source {source_name!r} not found")
            continue
        for ent in doc.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            eid = ent.get("id", "<no-id>")
            kind = ent.get("kind")
            if kind not in _VALID_KINDS:
                errors.append(f"{rel}: {eid} has unknown kind {kind!r} (allowed: {sorted(_VALID_KINDS)})")
            computability = ent.get("computability") or "narrative_only"
            if computability not in _VALID_COMPUTABILITY:
                errors.append(
                    f"{rel}: {eid} has unknown computability {computability!r} "
                    f"(allowed: {sorted(_VALID_COMPUTABILITY)})"
                )
            for tool in ent.get("tools") or []:
                if not isinstance(tool, dict):
                    errors.append(f"{rel}: {eid} tools entries must be mappings")
                    continue
                if tool.get("role") == "gate" and computability != "vera_native":
                    errors.append(
                        f"{rel}: {eid} tools role=gate requires computability=vera_native "
                        f"(got {computability!r})"
                    )
            binds = ent.get("binds") or {}
            if isinstance(binds, dict):
                col = binds.get("column")
                sym = binds.get("symbol")
                target = col or sym
                if target and not column_exists_in_source(source_path, str(target)):
                    errors.append(
                        f"{rel}: {eid} binds {target!r} but it is not defined in sibling "
                        f"{source_name!r} (locality violation)"
                    )
            pt = ent.get("points_to")
            if pt and pt not in known_ids:
                errors.append(f"{rel}: {eid} points_to unknown entity {pt!r}")
            for related in ent.get("related") or []:
                if related not in known_ids:
                    errors.append(f"{rel}: {eid} related entry {related!r} is unknown")

    # No-influencer-concept-nodes: every concept must resolve under VeraBase sql/|src/.
    for eid, ent in (compiled.get("entities") or {}).items():
        if ent.get("kind") != "concept":
            continue
        src = str(ent.get("_source") or "")
        if not any(src.startswith(pfx) for pfx in _VERABASE_SOURCE_PREFIXES):
            errors.append(
                f"{eid}: kind=concept requires _source under VeraBase sql/ or src/ "
                f"(got {src!r}) — influencer frameworks may not mint concept nodes"
            )
    return errors


def check_drift(repo_root: Path) -> list[str]:
    """Fail if the on-disk compiled.json differs from a fresh compile."""
    compiled, _ = compile_registry(repo_root)
    fresh = dumps(compiled)
    out = compiled_path(repo_root)
    if not out.is_file():
        return [f"missing {out.relative_to(repo_root).as_posix()} (run: vera-registry compile)"]
    current = out.read_text(encoding="utf-8")
    if current != fresh:
        return ["registry/compiled.json is stale (run: vera-registry compile and commit)"]
    return []
