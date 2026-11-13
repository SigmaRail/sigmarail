"""Fast checks for the SigmaRail-generated LEAN project snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from sigmarail_studio_mcp.backtest_runner.project_staging import stage_lean_project
from sigmarail_studio_mcp.backtest_runner.project_registry import default_project_id, get_project


def test_stages_isolated_project_with_lab_code_and_selected_strategy(tmp_path: Path) -> None:
    first = stage_lean_project(tmp_path, job_id="job-001", strategy_id="strategy-abc")

    assert first.project_name == str(first.root)
    assert (first.root / "main.py").is_file()
    assert (first.root / "sigmarail_lab" / "lean" / "algorithm.py").is_file()
    assert (first.root / "sigmarail_spec" / "strategy" / "compiler.py").is_file()
    assert (first.root / "scripts" / "lean_backtest_composite.py").is_file()

    config = json.loads((first.root / "config.json").read_text(encoding="utf-8"))
    assert config["algorithm-type-name"] == "ClickHouseUniverseAlgorithm"
    assert config["parameters"]["sigmarail-strategy-id"] == "strategy-abc"
    assert "CLICKHOUSE_PASSWORD" not in json.dumps(config)

    manifest = json.loads((first.root / "sigmarail-run.json").read_text(encoding="utf-8"))
    assert manifest == {
        "job_id": "job-001",
        "strategy_id": "strategy-abc",
        "source_sha256": first.source_sha256,
    }


def test_rejects_path_traversal_in_job_id(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="job_id"):
        stage_lean_project(tmp_path, job_id="../escape", strategy_id="strategy-abc")


def test_registry_resolves_legacy_selection_to_sigmarail_source(tmp_path: Path) -> None:
    (tmp_path / "lean.json").write_text("{}", encoding="utf-8")
    assert default_project_id() == "SigmaRailTradingLab"

    project = get_project("VeraTradingLab", root=tmp_path)

    assert project["id"] == "SigmaRailTradingLab"
    assert project["generated_project"] is True
    assert Path(project["composite_wrapper"]).is_file()
