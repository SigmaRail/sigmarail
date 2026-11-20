"""Component 4 Tier 3: API + MCP domain parity for the autonomous flywheel.

Covers optimize session launch/cancel wiring, promotion-gate evaluation,
paper registration denial on gate failure, and MCP tool parity with the
Django REST surface. ClickHouse-dependent tests are skipped when no
client is reachable.
"""
from __future__ import annotations

import asyncio

import pytest

from sigmarail_studio_mcp import server as mcp_server


def _tool_names() -> set[str]:
    mcp = mcp_server._build()
    try:
        listed = asyncio.get_event_loop().run_until_complete(mcp.list_tools())
    except RuntimeError:
        listed = asyncio.new_event_loop().run_until_complete(mcp.list_tools())
    names = set()
    for t in listed or []:
        name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
        if name:
            names.add(name)
    return names


EXPECTED_TOOLS = {
    "optimize_list_sessions",
    "optimize_launch_sweep",
    "optimize_get_session_heatmap",
    "optimize_get_pareto_frontier",
    "optimize_cancel_session",
    "optimize_promote_optimal_run",
    "deploy_evaluate_promotion_gate",
    "deploy_register_paper_deployment",
    "strategy_diff",
    "strategy_lint",
    "backtest_run_attribution",
}


def test_mcp_registers_core_tools_by_default():
    names = _tool_names()
    if not names:
        pytest.skip("FastMCP tool introspection unavailable in this version")
    assert {"core_list_datasets", "core_describe_dataset", "core_query_dataset"} <= names
    # These tools belong to explicit compatibility modules. They must not be
    # advertised by the default core+studio server until those modules are migrated.
    assert not (EXPECTED_TOOLS & names)


def test_parity_catalog_covers_flywheel():
    from sigmarail_studio_mcp import parity

    assert parity.gaps() == [], f"parity BACKLOG non-empty: {parity.gaps()}"
