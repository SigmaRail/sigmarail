"""Keep the default SigmaRail app independent of its legacy compatibility runtime."""

from __future__ import annotations

import ast
import json
import pathlib

STUDIO = pathlib.Path(__file__).resolve().parents[1]


def test_default_app_startup_imports_without_legacy_runtime() -> None:
    """Import API and default MCP modules; CI intentionally has no VeraBase checkout."""
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
            and (node.module == "vera_query_core" or node.module.startswith("vera_query_core."))
        ]
        assert not eager, f"{path.name} has eager Vera imports: {eager}"


def test_legacy_runtime_is_explicitly_optional() -> None:
    manifest = json.loads(
        (STUDIO / "sigmarail_studio_mcp" / "data" / "module-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["default_enabled"] == ["core", "studio"]
    assert all(
        row["compatibility"] and not row["default_enabled"]
        for row in manifest["modules"]
        if row["name"] not in {"core", "studio"}
    )
