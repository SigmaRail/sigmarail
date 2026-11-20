"""Strategy lineage helpers (screen hash + VeraLab AlgorithmParameters stamps)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

STUDIO_SCREEN_ID_KEY = "studio_screen_id"
STUDIO_SCREEN_NAME_KEY = "studio_screen_name"
STUDIO_SPEC_HASH_KEY = "studio_spec_hash"


def canonical_spec_json(universe_spec: dict[str, Any]) -> str:
    return json.dumps(universe_spec, sort_keys=True, separators=(",", ":"))


def universe_spec_hash(universe_spec: dict[str, Any]) -> str:
    payload = canonical_spec_json(universe_spec)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_lineage_parameters(
    universe_spec: dict[str, Any],
    *,
    screen_id: int | str | None = None,
    screen_name: str | None = None,
) -> dict[str, str]:
    """AlgorithmParameters stamps for compose (A0 lineage)."""
    out: dict[str, str] = {STUDIO_SPEC_HASH_KEY: universe_spec_hash(universe_spec)}
    if screen_id is not None:
        out[STUDIO_SCREEN_ID_KEY] = str(screen_id)
    name = (screen_name or "").strip()
    if name:
        out[STUDIO_SCREEN_NAME_KEY] = name
    return out


def merge_lineage_into_compose(
    algorithm_parameters: dict[str, Any] | None,
    lineage_parameters: dict[str, str],
) -> dict[str, Any]:
    merged = dict(algorithm_parameters or {})
    merged.update(lineage_parameters)
    return merged


__all__ = [
    "STUDIO_SCREEN_ID_KEY",
    "STUDIO_SCREEN_NAME_KEY",
    "STUDIO_SPEC_HASH_KEY",
    "build_lineage_parameters",
    "canonical_spec_json",
    "merge_lineage_into_compose",
    "universe_spec_hash",
]
