"""Git-pure enrichment helpers consumed by the MCP layer.

``explain_column`` stays ClickHouse-free: it reads the compiled registry +
parses ``COMMENT`` from ``sql/schema/*.sql``. ``describe_entity`` returns the
registry entry (KB evidence is wired to ClickHouse in a later slice).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .compile import load_compiled
from .ddl import column_comment as _column_comment


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def column_comment(repo_root: Path | None, table: str, column: str) -> str | None:
    return _column_comment(repo_root or _repo_root(), table, column)


def _alias_warnings(compiled: dict[str, Any], entity_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    index = compiled.get("warned_by") or compiled.get("points_to") or {}
    for warn_id in index.get(entity_id, []):
        ent = compiled.get("entities", {}).get(warn_id)
        if not ent:
            continue
        out.append(
            {
                "id": warn_id,
                "note": ent.get("note") or ent.get("definition"),
                "source": ent.get("_source"),
            }
        )
    return out


def _public_block(ent: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    ent = copy.deepcopy(ent)
    binds = ent.get("binds") or {}
    return {
        "id": ent.get("id"),
        "kind": ent.get("kind"),
        "title": ent.get("title"),
        "definition": ent.get("definition"),
        "narrative": ent.get("narrative"),
        "bindings": [binds] if binds else [],
        "aliases": ent.get("aliases", []),
        "related": ent.get("related", []),
        "falsifiers": ent.get("falsifiers", []),
        "tools": ent.get("tools") or [],
        "computability": ent.get("computability") or "narrative_only",
        "alias_warnings": _alias_warnings(compiled, str(ent.get("id"))),
        "sidecar": ent.get("_sidecar"),
        "source": "registry",
    }


def entity_for_column(
    repo_root: Path | None, table: str, column: str
) -> dict[str, Any] | None:
    """Return the public entity block bound to ``table.column``, or ``None``."""
    compiled = load_compiled(repo_root or _repo_root())
    if not compiled:
        return None
    eid = compiled.get("by_anchor", {}).get(f"vera:{table}.{column}")
    if not eid:
        return None
    ent = compiled.get("entities", {}).get(eid)
    if not ent:
        return None
    return _public_block(ent, compiled)


def describe_entity(repo_root: Path | None, entity_id: str) -> dict[str, Any]:
    """Registry entry for an entity id or alias (git-only; KB evidence empty)."""
    compiled = load_compiled(repo_root or _repo_root())
    if not compiled:
        return {"entity": None, "kb_evidence": [], "evidence_source": "none", "found": False}
    eid = entity_id
    if eid not in compiled.get("entities", {}):
        eid = compiled.get("alias_to_id", {}).get(entity_id, "")
    ent = compiled.get("entities", {}).get(eid)
    if not ent:
        return {"entity": None, "kb_evidence": [], "evidence_source": "none", "found": False}
    return {
        "entity": _public_block(ent, compiled),
        "kb_evidence": [],
        "evidence_source": "none",
        "found": True,
    }
