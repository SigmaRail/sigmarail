"""Compose the current SigmaRail strategy wire document from a universe query.

Studio Browse seeds from the git catalog (``minervini_sepa``) only.
Legacy built-in framework JSON templates under ``strategy_templates/`` were removed.
``compose_strategy_v1`` accepts an explicit ``framework`` assembly, or a
``template_id`` when a test/fixture registers meta + a JSON file.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from screens.ir_preview import validate_universe_ir_spec

STRATEGY_TEMPLATES_DIR = Path(__file__).resolve().parent / "strategy_templates"
FRAMEWORK_CATALOG_PATH = Path(__file__).resolve().parent / "framework_catalog.json"

_FRAMEWORK_SLOTS: tuple[str, ...] = (
    "UniverseSelection",
    "Alpha",
    "PortfolioConstruction",
    "Execution",
    "RiskManagement",
)

# Empty on purpose — Studio catalog seed is ``minervini_sepa`` (Pipeline AST), not these.
_STRATEGY_TEMPLATE_META: dict[str, dict[str, str]] = {}


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "untitled").lower()).strip("-")
    return slug[:48] or "untitled"


def _load_template_json(template_id: str) -> dict[str, Any]:
    tid = (template_id or "").strip()
    if not tid or "/" in tid or "\\" in tid or ".." in tid:
        raise ValueError(f"invalid template id {template_id!r}")
    if tid not in _STRATEGY_TEMPLATE_META:
        raise ValueError(f"unknown strategy template {template_id!r}")
    path = STRATEGY_TEMPLATES_DIR / f"{tid}.json"
    if not path.is_file():
        raise ValueError(f"strategy template file missing for {tid!r}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"template {tid!r} must be a JSON object")
    return raw


def _assert_universe_query_v1(universe_spec: dict[str, Any]) -> None:
    if not isinstance(universe_spec, dict):
        raise ValueError("universe spec must be an object")
    # UniverseQueryV1 accepts version 1 or 2 (default 2, the spine/joins form this repo
    # mandates). The compose path historically rejected version 2, silently forcing callers
    # back onto the legacy version-1 shape; the model itself has accepted both all along.
    if universe_spec.get("version") not in (1, 2):
        raise ValueError("universe spec must be universe_query_v1 (version 1 or 2)")
    select = universe_spec.get("select")
    if not isinstance(select, list) or not select:
        raise ValueError("universe spec must include a non-empty select list")
    validate_universe_ir_spec(universe_spec)


def list_strategy_templates() -> list[dict[str, str]]:
    """Return strategy template catalog entries (id, label, description)."""
    out: list[dict[str, str]] = []
    for tid, meta in sorted(_STRATEGY_TEMPLATE_META.items()):
        out.append(
            {
                "id": tid,
                "label": meta["label"],
                "description": meta["description"],
            }
        )
    return out


def load_framework_catalog() -> dict[str, Any]:
    """Load static Lean framework Type catalog (no LEAN_ROOT required)."""
    if not FRAMEWORK_CATALOG_PATH.is_file():
        raise FileNotFoundError(f"framework catalog missing: {FRAMEWORK_CATALOG_PATH}")
    raw = json.loads(FRAMEWORK_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("framework catalog must be a JSON object")
    return raw


def suggest_ir_id(title: str, universe_spec: dict[str, Any]) -> str:
    """Suggest a stable-ish ir_id: ``studio-{slug}-{6char_hash}``."""
    slug = _slugify(title)
    payload = json.dumps(universe_spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:6]
    return f"studio-{slug}-{digest}"


def compose_assembled_ensemble_v1(
    *,
    universe_spec: dict[str, Any],
    framework: dict[str, Any],
    algorithm_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble an ensemble strategy directly from custom Framework slots."""
    _assert_universe_query_v1(universe_spec)
    if not isinstance(framework, dict):
        raise ValueError("framework must be an object")

    spec = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "VeraBase": {
            "Universe": copy.deepcopy(universe_spec),
        },
        "Framework": copy.deepcopy(framework),
        "AlgorithmParameters": copy.deepcopy(algorithm_parameters or {"regime-source": "screener"}),
    }
    return spec


def compose_strategy_v1(
    *,
    universe_spec: dict[str, Any],
    template_id: str | None = None,
    framework: dict[str, Any] | None = None,
    framework_overrides: dict[str, Any] | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deep-copy a strategy template or use custom assembled framework, injecting universe + overrides."""
    _assert_universe_query_v1(universe_spec)
    if framework is not None:
        return compose_assembled_ensemble_v1(
            universe_spec=universe_spec,
            framework=framework,
            algorithm_parameters=algorithm_parameters,
        )

    if not template_id:
        raise ValueError(
            "template_id is required when framework is omitted "
            "(legacy built-in templates removed; use catalog minervini_sepa / assembled framework)"
        )

    tid = (template_id or "").strip()
    if tid == "custom_assembled":
        raise ValueError(
            "custom_assembled requires an assembled framework object "
            "(or a precompiled VeraLabV1 spec); load a catalog strategy such as minervini_sepa"
        )

    spec = copy.deepcopy(_load_template_json(template_id))

    vera_base = spec.setdefault("VeraBase", {})
    if not isinstance(vera_base, dict):
        raise ValueError("template VeraBase must be an object")
    vera_base["Universe"] = copy.deepcopy(universe_spec)

    if framework_overrides:
        fw = spec.setdefault("Framework", {})
        if not isinstance(fw, dict):
            raise ValueError("template Framework must be an object")
        for slot, override in framework_overrides.items():
            if slot not in _FRAMEWORK_SLOTS:
                raise ValueError(f"unknown framework slot {slot!r}")
            if not isinstance(override, dict):
                raise ValueError(f"framework override for {slot!r} must be an object")
            slot_obj = fw.setdefault(slot, {})
            if not isinstance(slot_obj, dict):
                raise ValueError(f"template Framework.{slot} must be an object")
            _merge_framework_slot(slot_obj, override)

    if algorithm_parameters is not None:
        if not isinstance(algorithm_parameters, dict):
            raise ValueError("algorithm_parameters must be an object")
        algo = spec.setdefault("AlgorithmParameters", {})
        if not isinstance(algo, dict):
            raise ValueError("template AlgorithmParameters must be an object")
        merged = dict(algo)
        merged.update(algorithm_parameters)
        spec["AlgorithmParameters"] = merged

    return spec


def _merge_framework_slot(slot_obj: dict[str, Any], override: dict[str, Any]) -> None:
    """Shallow-merge slot fields; deep-merge ``Parameters`` so partial UI overrides keep siblings."""
    for key, value in override.items():
        if key == "Parameters" and isinstance(value, dict):
            existing = slot_obj.get("Parameters")
            if isinstance(existing, dict):
                merged_params = dict(existing)
                merged_params.update(copy.deepcopy(value))
                slot_obj["Parameters"] = merged_params
            else:
                slot_obj["Parameters"] = copy.deepcopy(value)
        else:
            slot_obj[key] = copy.deepcopy(value)


def validate_composed_spec(spec: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate the executable strategy against the canonical SigmaRail Spec schema."""
    try:
        from jsonschema import Draft202012Validator
        from sigmarail_spec import get_document

        schema_document = get_document("strategy/execution.json")
        schema = schema_document["executable_strategy_schema"]
        errors = sorted(
            Draft202012Validator(schema).iter_errors(spec),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except Exception as exc:
        return False, f"SigmaRail strategy schema could not be loaded: {exc}"
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        if len(errors) > 8:
            detail += f"; and {len(errors) - 8} more validation error(s)"
        return False, detail
    return True, None


__all__ = [
    "STRATEGY_TEMPLATES_DIR",
    "compose_assembled_ensemble_v1",
    "compose_strategy_v1",
    "list_strategy_templates",
    "load_framework_catalog",
    "suggest_ir_id",
    "validate_composed_spec",
]
