"""Resolve SigmaRail-owned LEAN projects and optional local project entries."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PROJECT_ID = "SigmaRailTradingLab"
_COMPATIBLE_PROJECT_IDS = {_DEFAULT_PROJECT_ID, "VeraTradingLab"}
_REGISTRY_FILENAME = "lean_projects.yaml"


def lean_projects_root() -> Path:
    """Locate the LEAN CLI workspace; the strategy source lives in SigmaRail."""
    configured = (os.environ.get("LEAN_PROJECTS_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    for parent in (Path.cwd(), *Path(__file__).resolve().parents):
        if (parent / "lean.json").is_file():
            return parent
        candidate = parent / "LeanProjects"
        if (candidate / "lean.json").is_file():
            return candidate
    raise RuntimeError(
        "Cannot locate a LEAN CLI workspace (lean.json not found). "
        "Set LEAN_PROJECTS_ROOT to the workspace containing lean.json."
    )


def _registry_path(root: Path | None = None) -> Path:
    return (root or lean_projects_root()) / _REGISTRY_FILENAME


def _sigmarail_project(root: Path | None = None) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    source_root = repo_root / "trading_lab"
    lean_root = root or lean_projects_root()
    return {
        "id": _DEFAULT_PROJECT_ID,
        "label": "SigmaRail Trading Lab",
        "lean_cli_name": "sigmarail-run",
        "workspace_root_env": "LEAN_PROJECTS_ROOT",
        "composite_wrapper": str(source_root / "scripts" / "lean_backtest_composite.py"),
        "lean_config_overlay": "lean-composite.json",
        "default_image": "lean-local:latest",
        "spec_kinds": ["VeraLabV1"],
        "runner_entry": "main.py",
        "generated_project": True,
        "lean_workspace": str(lean_root),
        "enabled": True,
    }


@lru_cache(maxsize=1)
def load_registry(root: Path | None = None) -> dict[str, Any]:
    """Return the optional local project registry, if one exists."""
    path = _registry_path(root)
    if not path.is_file():
        return {"projects": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid registry format in {path}")
    projects = data.get("projects")
    if not isinstance(projects, list):
        raise ValueError(f"Registry must contain a 'projects' list: {path}")
    return data


def list_projects(*, enabled_only: bool = True, root: Path | None = None) -> list[dict[str, Any]]:
    projects = [_sigmarail_project(root)]
    for entry in load_registry(root).get("projects", []):
        if not isinstance(entry, dict) or entry.get("id") in _COMPATIBLE_PROJECT_IDS:
            continue
        if enabled_only and not entry.get("enabled", True):
            continue
        projects.append(entry)
    return projects


def get_project(project_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Return a project; the old project ID resolves to the in-repo SigmaRail lab."""
    pid = (project_id or _DEFAULT_PROJECT_ID).strip()
    if pid in _COMPATIBLE_PROJECT_IDS:
        project = _sigmarail_project(root)
        project["requested_id"] = pid
        return project
    for entry in load_registry(root).get("projects", []):
        if isinstance(entry, dict) and entry.get("id") == pid:
            return entry
    raise KeyError(f"Unknown LEAN project: {pid}")


def resolve_output_rel(project_id: str, job_id: str, *, root: Path | None = None) -> str:
    """Return the run-specific output folder inside its generated project."""
    project = get_project(project_id, root=root)
    lean_cli_name = str(project.get("lean_cli_name") or project.get("id") or project_id)
    return f"{lean_cli_name}/results/{job_id}"


def default_project_id() -> str:
    return _DEFAULT_PROJECT_ID
