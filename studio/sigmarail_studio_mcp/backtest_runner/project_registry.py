"""Resolve SigmaRail-owned LEAN projects and optional local project entries."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PROJECT_ID = "SigmaRailTradingLab"
_RESERVED_PROJECT_IDS = {_DEFAULT_PROJECT_ID}
_REGISTRY_FILENAME = "lean_projects.yaml"


def _repo_root() -> Path:
    configured = (os.environ.get("SIGMARAIL_REPO_ROOT") or "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[3]


def lean_workspace_root() -> Path:
    """Locate the isolated LEAN workspace owned by this SigmaRail checkout."""
    configured = (os.environ.get("SIGMARAIL_LEAN_WORKSPACE_ROOT") or "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = _repo_root() / ".sigmarail" / "lean"

    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "lean.json"
    if not config_path.exists():
        template = _repo_root() / "deploy" / "lean" / "lean.json"
        if not template.is_file():
            raise RuntimeError(f"SigmaRail LEAN workspace template is missing: {template}")
        config_path.write_bytes(template.read_bytes())
    return root


def _registry_path(root: Path | None = None) -> Path:
    return (root or lean_workspace_root()) / _REGISTRY_FILENAME


def _sigmarail_project(root: Path | None = None) -> dict[str, Any]:
    configured = (os.environ.get("SIGMARAIL_TRADING_LAB_SOURCE") or "").strip()
    source_root = (
        Path(configured).expanduser().resolve()
        if configured
        else _repo_root() / "trading_lab"
    )
    lean_root = root or lean_workspace_root()
    return {
        "id": _DEFAULT_PROJECT_ID,
        "label": "SigmaRail Trading Lab",
        "lean_cli_name": "sigmarail-run",
        "workspace_root_env": "SIGMARAIL_LEAN_WORKSPACE_ROOT",
        "composite_wrapper": str(source_root / "scripts" / "lean_backtest_composite.py"),
        "lean_config_template": str(source_root / "lean_config_template.json"),
        "default_image": "lean-local:latest",
        "spec_kinds": ["SigmaRailStrategyV1"],
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
        if not isinstance(entry, dict) or entry.get("id") in _RESERVED_PROJECT_IDS:
            continue
        if enabled_only and not entry.get("enabled", True):
            continue
        projects.append(entry)
    return projects


def get_project(project_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Return the in-repo SigmaRail project or a configured project."""
    pid = (project_id or _DEFAULT_PROJECT_ID).strip()
    if pid == _DEFAULT_PROJECT_ID:
        project = _sigmarail_project(root)
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
