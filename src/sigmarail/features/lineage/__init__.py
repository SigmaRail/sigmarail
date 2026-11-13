"""SQL-to-column lineage extraction for VeraBase transforms.

This module produces deterministic JSON artifacts intended to be checked into the repo
and served through MCP/REST for column explanations.
"""

from __future__ import annotations

__all__ = ["generate_lineage_artifacts"]

from .generator import generate_lineage_artifacts
