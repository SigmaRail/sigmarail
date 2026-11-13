"""lean domain: Lean framework Type discovery (AST)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import try_call


def discover_types(
    slot: str | None = None,
    include_unwired: bool = True,
    lean_root: str | None = None,
    include_vera_screener_ids: bool = True,
) -> dict[str, Any]:
    """List LEAN framework types and SigmaRail wiring metadata."""
    from sigmarail_lab.ir.lean_framework_discovery import discover_lean_framework_types

    return try_call(
        discover_lean_framework_types,
        lean_root=lean_root,
        slot=slot,
        include_unwired=include_unwired,
        include_vera_screener_ids=include_vera_screener_ids,
    )
