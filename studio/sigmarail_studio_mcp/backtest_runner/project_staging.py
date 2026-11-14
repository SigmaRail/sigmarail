"""Build an isolated LEAN project directory from SigmaRail's maintained lab source."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StagedProject:
    """Filesystem paths and provenance for one generated LEAN project."""

    root: Path
    project_name: str
    source_sha256: str


def trading_lab_source_root() -> Path:
    configured = (os.environ.get("SIGMARAIL_TRADING_LAB_SOURCE") or "").strip()
    if configured:
        lab = Path(configured).expanduser().resolve()
        repo_root = lab.parent if lab.name == "trading_lab" else lab
    else:
        # backtest_runner/project_staging.py -> studio package -> repo root
        repo_root = Path(__file__).resolve().parents[3]
        lab = repo_root / "trading_lab"
    if not (lab / "main.py").is_file() or not (repo_root / "src" / "sigmarail_lab").is_dir():
        raise FileNotFoundError(
            f"SigmaRail Trading Lab source is incomplete: {lab}. "
            "Set SIGMARAIL_TRADING_LAB_SOURCE to the repo's trading_lab directory."
        )
    return repo_root


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    excluded = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or any(part in excluded for part in path.relative_to(source).parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        relative = path.relative_to(source).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def stage_lean_project(lean_root: Path, *, job_id: str, strategy_id: str) -> StagedProject:
    """Copy maintained source into a per-run LEAN project and inject run metadata.

    No strategy source is generated dynamically. The staged folder is a snapshot
    of ``trading_lab/`` plus a minimal LEAN config and the selected strategy ID.
    """
    safe_job_id = str(job_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", safe_job_id):
        raise ValueError("job_id contains unsupported path characters")
    repo_root = trading_lab_source_root()
    lab_source = repo_root / "trading_lab"
    source_digest = hashlib.sha256(
        (_source_digest(lab_source) + _source_digest(repo_root / "src" / "sigmarail_lab")).encode("ascii")
    ).hexdigest()
    relative = Path(".sigmarail") / "runs" / safe_job_id / "project"
    destination = (lean_root / relative).resolve()
    workspace = lean_root.resolve()
    if workspace not in destination.parents:
        raise ValueError("generated LEAN project must remain inside LEAN_PROJECTS_ROOT")

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        lab_source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
    )
    shutil.copytree(
        repo_root / "src" / "sigmarail_lab",
        destination / "sigmarail_lab",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
    )

    template_path = destination / "config.json.template"
    if template_path.is_file():
        config: dict[str, Any] = json.loads(template_path.read_text(encoding="utf-8"))
    else:
        config = {}
    config.update(
        {
            "algorithm-language": "Python",
            "algorithm-location": "main.py",
            "algorithm-type-name": "ClickHouseUniverseAlgorithm",
            "parameters": {"sigmarail-strategy-id": str(strategy_id)},
        }
    )
    (destination / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (destination / "sigmarail-run.json").write_text(
        json.dumps(
            {
                "job_id": safe_job_id,
                "strategy_id": str(strategy_id),
                "source_sha256": source_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return StagedProject(
        root=destination,
        project_name=str(destination),
        source_sha256=source_digest,
    )
