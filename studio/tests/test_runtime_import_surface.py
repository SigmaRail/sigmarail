"""Keep SigmaRail runtime imports inside SigmaRail-owned packages."""

from __future__ import annotations

import ast
import json
from importlib.resources import files
from pathlib import Path

STUDIO = Path(__file__).absolute().parents[1]


def test_default_app_startup_imports_without_legacy_runtime() -> None:
    """Import API and default MCP modules with SigmaRail packages only."""
    import api.views  # noqa: F401
    import sigmarail_studio_mcp.ch  # noqa: F401
    import sigmarail_studio_mcp.server  # noqa: F401


def test_startup_modules_defer_legacy_imports_until_feature_calls() -> None:
    startup = [
        STUDIO / "screens" / "backtest.py",
        STUDIO / "screens" / "live_promotion.py",
        STUDIO / "screens" / "adapter.py",
        STUDIO / "sigmarail_studio_mcp" / "ch.py",
    ]
    for path in startup:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        eager = [
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and (node.module == "sigmarail.features" or node.module.startswith("sigmarail.features."))
        ]
        assert not eager, f"{path.name} has eager Vera imports: {eager}"


def test_existing_capability_modules_remain_registered_during_migration() -> None:
    manifest = json.loads(
        files("sigmarail_studio_mcp")
        .joinpath("data", "module-catalog.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["default_enabled"] == ["core", "studio"]
    by_name = {row["name"]: row for row in manifest["modules"]}
    assert set(by_name) == {
        "core", "studio", "screening", "strategy", "backtesting",
        "portfolio", "deployment", "knowledge",
    }
    assert {name for name, row in by_name.items() if row["default_enabled"]} == {"core", "studio"}
    assert all(by_name[name]["migration_status"] == "ported_pending_schema_validation" for name in (
        "screening", "strategy", "backtesting", "portfolio", "deployment", "knowledge"
    ))
    assert by_name["strategy"]["requires"] == ["sigmarail-spec", "sigmarail-lean"]
    assert by_name["strategy"]["target_requires"] == ["sigmarail-spec", "sigmarail-lean"]


def test_application_and_mcp_have_no_vera_package_imports() -> None:
    roots = [
        STUDIO.parent / "src" / "sigmarail",
        STUDIO.parent / "src" / "sigmarail_lab",
        STUDIO.parent / "trading_lab",
        STUDIO,
    ]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                offenders.extend(
                    f"{path.relative_to(STUDIO.parent)}:{name}"
                    for name in names
                    if name == "vera_query_core"
                    or name.startswith("vera_query_core.")
                    or name == "vera_lab"
                    or name.startswith("vera_lab.")
                    or name == "vera_spec"
                    or name.startswith("vera_spec.")
                )
    assert not offenders, offenders
