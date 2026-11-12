"""Load Lean project entries from lean_projects.yaml at the LeanProjects root."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PROJECT_ID = "VeraTradingLab"
_REGISTRY_FILENAME = "lean_projects.yaml"


def lean_projects_root() -> Path:
    """Locate the LeanProjects workspace root (contains lean.json)."""
    env = os.environ.get("LEAN_PROJECTS_ROOT", "").strip()
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "lean.json").exists():
            return parent
    raise RuntimeError(
        "Cannot locate LeanProjects root (no lean.json found in parents). "
        "Set LEAN_PROJECTS_ROOT env var."
    )


def _registry_path(root: Path | None = None) -> Path:
    return (root or lean_projects_root()) / _REGISTRY_FILENAME


@lru_cache(maxsize=1)
def load_registry(root: Path | None = None) -> dict[str, Any]:
    """Return parsed lean_projects.yaml as {projects: [dict, ...]}."""
    path = _registry_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"Lean project registry not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid registry format in {path}")
    projects = data.get("projects")
    if not isinstance(projects, list):
        raise ValueError(f"Registry must contain a 'projects' list: {path}")
    return data


def list_projects(*, enabled_only: bool = True, root: Path | None = None) -> list[dict[str, Any]]:
    projects = load_registry(root).get("projects", [])
    out: list[dict[str, Any]] = []
    for entry in projects:
        if not isinstance(entry, dict):
            continue
        if enabled_only and not entry.get("enabled", True):
            continue
        out.append(entry)
    return out


def get_project(project_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Return registry entry for project_id or raise KeyError."""
    pid = (project_id or _DEFAULT_PROJECT_ID).strip()
    for entry in load_registry(root).get("projects", []):
        if isinstance(entry, dict) and entry.get("id") == pid:
            return entry
    raise KeyError(f"Unknown lean project: {pid}")


def resolve_output_rel(project_id: str, job_id: str, *, root: Path | None = None) -> str:
    """Relative output path under LEAN_PROJECTS_ROOT, e.g. VeraTradingLab/results/{job_id}."""
    project = get_project(project_id, root=root)
    lean_cli_name = str(project.get("lean_cli_name") or project.get("id") or project_id)
    return f"{lean_cli_name}/results/{job_id}"


def default_project_id() -> str:
    return _DEFAULT_PROJECT_ID
