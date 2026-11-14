"""Co-located entity registry (Phase A).

Semantics for warehouse columns, metrics, ADM entities, and instruments are
authored in ``*.entities.yaml`` sidecars that live **next to** the source that
defines the thing (locality). ``vera-registry compile`` walks the tree and emits
a single generated aggregate ``VeraBase/registry/compiled.json``; the MCP layer
reads only that aggregate (git-pure, no ClickHouse).

Public helpers used by the MCP server and platform gate:

- :func:`sigmarail.features.registry.enrich.entity_for_column`
- :func:`sigmarail.features.registry.enrich.column_comment`
- :func:`sigmarail.features.registry.enrich.describe_entity`
"""

from __future__ import annotations

SIDECAR_SUFFIX = ".entities.yaml"
COMPILED_RELATIVE = "registry/compiled.json"

__all__ = ["SIDECAR_SUFFIX", "COMPILED_RELATIVE"]
