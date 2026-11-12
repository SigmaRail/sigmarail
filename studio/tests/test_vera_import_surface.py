"""Pin the `vera_query_core` surface this app imports.

SigmaRailStudio depends on VeraBase (`vera`) in-process — 114 import sites — and the
two are always deployed together, so in-process imports are the intended design, not a
wart. What is *not* intended is that the surface grows silently.

Before this test the app imported 21 distinct `vera_query_core` submodules, none of them
declared in `pyproject.toml`, all resolved through a PYTHONPATH convention. Two failure
modes followed, both observed:

* a module could be imported from a checkout where it did not exist yet, and the failure
  surfaced at request time rather than install time;
* nobody could tell which parts of VeraBase were app API and which were incidental.

So: adding a surface is fine, but it has to be a deliberate edit here. Removing one
without updating this list also fails, so the list cannot rot into a lie.
"""

from __future__ import annotations

import ast
import pathlib

STUDIO = pathlib.Path(__file__).resolve().parents[1]
_SKIP = {".venv", "node_modules", "dist", "__pycache__"}

# Every `vera_query_core` import surface the app uses. Grouped by intent so a reviewer
# can see what kind of coupling a new entry would be.
VERA_IMPORT_SURFACE = frozenset(
    {
        # --- contracts: models, IR, presets, templates (the shared vocabulary) --------
        "vera_query_core",
        "vera_query_core.ir",
        "vera_query_core.screen_preset_ir",
        "vera_query_core.screen_templates",
        "vera_query_core.template_catalog",
        "vera_query_core.strategy",
        # --- operations: data reads that also exist as /v1 endpoints -----------------
        "vera_query_core.alpha_evaluation",
        "vera_query_core.backtest_report",
        "vera_query_core.broker_tools",
        "vera_query_core.ch_settings",
        "vera_query_core.gate_tools",
        "vera_query_core.kb_episode",
        "vera_query_core.kb_pipeline",
        "vera_query_core.kb_search",
        "vera_query_core.lineage",
        "vera_query_core.live_report",
        "vera_query_core.narrative_tools",
        "vera_query_core.platform_tools",
        "vera_query_core.portfolio_status",
        "vera_query_core.risk_sizing",
        "vera_query_core.tv_chart",
        "vera_query_core.vera_price_chart",
    }
)


def _surface(path: pathlib.Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        for name in names:
            if name == "vera_query_core" or name.startswith("vera_query_core."):
                parts = name.split(".")
                found.add(".".join(parts[:2]) if len(parts) > 1 else "vera_query_core")
    return found


def _app_surface() -> set[str]:
    out: set[str] = set()
    for path in STUDIO.rglob("*.py"):
        if _SKIP & set(path.parts):
            continue
        out |= _surface(path)
    return out


def test_import_surface_matches_the_pinned_list() -> None:
    actual = _app_surface()
    added = sorted(actual - VERA_IMPORT_SURFACE)
    gone = sorted(VERA_IMPORT_SURFACE - actual)
    assert not added, (
        "new vera_query_core import surface(s) — declare them here deliberately, and "
        "check whether the capability already has a /v1 endpoint: " + ", ".join(added)
    )
    assert not gone, (
        "these surfaces are listed but no longer imported — remove them so the list "
        "stays truthful: " + ", ".join(gone)
    )


def test_surface_list_is_not_empty() -> None:
    assert len(VERA_IMPORT_SURFACE) >= 20


def test_legacy_runtime_is_explicitly_optional() -> None:
    """The default SigmaRail app must not require private compatibility packages."""
    import json

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
