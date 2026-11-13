"""Resolve VeraLab JSON from env: file path, ClickHouse ir_id, or base64."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Literal, Union

from .models import VeraLab
from .sigmarail_lab_v1_bind import VeraLabV1BindingProxy, bind_sigmarail_lab_v1, bind_sigmarail_lab_v1_with_graph
from .sigmarail_lab_v1_json import VeraLabV1Document
from ..runtime.sigmarail_api_client import (
    SigmaRailApiClient,
    SigmaRailApiError,
    resolve_sigmarail_api_service_api_key,
    resolve_sigmarail_api_service_url,
)


class VeraLabResolutionError(RuntimeError):
    pass


SourceKind = Literal["file", "api", "base64", "bundled"]

MainRunnerSpec = Union[VeraLab, VeraLabV1BindingProxy]


def parse_algorithm_spec_for_main_py(raw: str) -> MainRunnerSpec:
    """
    Branch on agent JSON Kind for main.py (ClickHouseUniverseAlgorithm).

    - VeraLabV1: explicit Framework + VeraBase facet (preferred).
    - schema_version 1 with ``root``: graph Policy B (lowers to universe_query_v1).
    - Pipeline schema_version 1 (flat universe/alpha/…): removed — use VeraLabV1.
    - LeanFrameworkV1: wrong entrypoint — use LEAN_FRAMEWORK_V1_*.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise VeraLabResolutionError(f"Invalid algorithm JSON: {e}") from e
    kind = data.get("Kind")
    if kind == "LeanFrameworkV1":
        raise VeraLabResolutionError(
            "Kind LeanFrameworkV1 uses LEAN_FRAMEWORK_V1_* (see tests/test_lean_framework_v1.py), "
            "not SIGMARAIL_LAB_* with main.py"
        )
    if kind == "VeraLabV1":
        try:
            doc = VeraLabV1Document.model_validate(data)
        except Exception as e:
            raise VeraLabResolutionError(f"VeraLabV1 validation failed: {e}") from e
        try:
            bound, policy_graph = bind_sigmarail_lab_v1_with_graph(doc)
        except Exception as e:
            raise VeraLabResolutionError(f"VeraLabV1 bind failed: {e}") from e
        return VeraLabV1BindingProxy(bound, policy_graph)
    try:
        spec = VeraLab.model_validate(data)
    except Exception as e:
        raise VeraLabResolutionError(f"algorithm JSON validation failed: {e}") from e
    if spec.root is None:
        raise VeraLabResolutionError(
            "Pipeline VeraLab (schema_version 1 without Kind VeraLabV1) was removed; "
            "use Kind VeraLabV1 with VeraBase.Universe universe_query_v1"
        )
    return spec


@dataclass(frozen=True)
class ResolvedVeraLab:
    spec: MainRunnerSpec
    raw_json: str
    source: SourceKind
    """Where JSON was loaded from."""
    ir_id: str | None
    """Set when loaded from ClickHouse by id."""
    content_hash_sha256: str
    """Hex sha256 of raw_json UTF-8 bytes."""


def _baseline_fixture_rel() -> str:
    return "tests/fixtures/ir/baseline.json"


def _norm_sigmarail_lab_path(path: str) -> str:
    s = path.replace("\\", "/").lstrip("/")
    while s.startswith("./"):
        s = s[2:]
    return s


def _bundled_ir_modules() -> dict[str, str]:
    """Relative SIGMARAIL_STRATEGY_PATH (normalized) -> ``sigmarail_lab.*`` module name."""
    return {
        _baseline_fixture_rel(): "sigmarail_lab.lean_docker_baseline_ir",
        "tests/fixtures/ir/tqqq-tactical-v1.json": "sigmarail_lab.lean_docker_tqqq_tactical_ir",
        "docs/examples/ir/tqqq-tactical-v1.json": "sigmarail_lab.lean_docker_tqqq_tactical_ir",
        "tests/fixtures/ir/tqqq-buyhold-v1.json": "sigmarail_lab.lean_docker_tqqq_buyhold_ir",
        "docs/examples/ir/tqqq-buyhold-v1.json": "sigmarail_lab.lean_docker_tqqq_buyhold_ir",
        "tests/fixtures/ir/tqqq-tactical-graph-v1.json": "sigmarail_lab.lean_docker_tqqq_tactical_graph_ir",
        "tests/fixtures/ir/etf_rotation_graph_v1.json": "sigmarail_lab.lean_docker_etf_rotation_graph_ir",
        "docs/examples/ir/tqqq-tactical-graph-v1.json": "sigmarail_lab.lean_docker_tqqq_tactical_graph_ir",
        "tests/fixtures/ir/high-roe-large-cap-quality-v1.json": "sigmarail_lab.lean_docker_high_roe_ir",
        "tests/fixtures/ir/all-weather-v1.json": "sigmarail_lab.lean_docker_all_weather_ir",
    }


def _bundled_module_for_missing_path(path: str, resolved: str) -> str | None:
    """Module providing ``RAW_JSON`` when LEAN Docker omitted the fixture file."""
    if os.path.isfile(resolved):
        return None
    norm = _norm_sigmarail_lab_path(path)
    rnorm = resolved.replace("\\", "/")
    for rel, module in _bundled_ir_modules().items():
        if norm == rel or norm.endswith("/" + rel) or rnorm.endswith("/" + rel):
            return module
    return None


def _should_use_bundled_baseline_ir(path: str, resolved: str) -> bool:
    """Backward-compatible alias for baseline-only checks."""
    return _bundled_module_for_missing_path(path, resolved) is not None


def _fetch_from_sigmarail(ir_id: str, algorithm=None) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", ir_id):
        raise VeraLabResolutionError("ir_id must match [a-zA-Z0-9_.-]+")
    base_url = resolve_sigmarail_api_service_url(algorithm)
    if not base_url:
        raise VeraLabResolutionError(
            "SIGMARAIL_STRATEGY_ID requires SIGMARAIL_API_URL so Lean can fetch the saved spec from SigmaRail"
        )
    client = SigmaRailApiClient(
        base_url,
        api_key=resolve_sigmarail_api_service_api_key(algorithm),
    )
    try:
        result = client.strategy_spec(ir_id)
    except SigmaRailApiError as exc:
        raise VeraLabResolutionError(f"SigmaRail strategy fetch failed for {ir_id!r}: {exc}") from exc
    raw = result.get("algorithm_json")
    if not raw or not isinstance(raw, str):
        raise VeraLabResolutionError(f"SigmaRail returned no algorithm_json for ir_id={ir_id!r}")
    return raw


def resolve_sigmarail_lab(algorithm=None) -> ResolvedVeraLab:
    """
    Precedence:
      1. SIGMARAIL_STRATEGY_PATH — read file when present; if missing but path is the CI
         baseline fixture (``tests/fixtures/ir/baseline.json``), use bundled copy
         (LEAN Docker omits ``.json`` from project sync).
      2. SIGMARAIL_STRATEGY_ID — fetch algorithm_json through SigmaRail Studio's API
      3. SIGMARAIL_STRATEGY_BASE64 — inline JSON (optional; capped)
    If none resolve, raise VeraLabResolutionError.
    """
    path = (os.environ.get("SIGMARAIL_STRATEGY_PATH") or "").strip()
    project_root = (os.environ.get("SIGMARAIL_STRATEGY_ROOT") or "").strip()
    ir_id_env = (os.environ.get("SIGMARAIL_STRATEGY_ID") or "").strip()
    b64 = (os.environ.get("SIGMARAIL_STRATEGY_BASE64") or "").strip()

    raw: str | None = None
    source: SourceKind = "file"
    ir_id: str | None = None

    if path:
        p = path
        if not os.path.isabs(p):
            if project_root:
                p = os.path.join(project_root, p)
            else:
                p = os.path.abspath(p)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                raw = f.read()
            source = "file"
        elif (mod := _bundled_module_for_missing_path(path, p)):
            import importlib

            raw = importlib.import_module(mod).RAW_JSON
            source = "bundled"
        else:
            raise VeraLabResolutionError(f"SIGMARAIL_STRATEGY_PATH is not a file: {path!r} (resolved {p!r})")
    elif ir_id_env:
        raw = _fetch_from_sigmarail(ir_id_env, algorithm)
        source = "api"
        ir_id = ir_id_env
    elif b64:
        max_b64 = int(os.environ.get("SIGMARAIL_STRATEGY_BASE64_MAX", "1048576"))
        if len(b64) > max_b64:
            raise VeraLabResolutionError("SIGMARAIL_STRATEGY_BASE64 exceeds size cap")
        try:
            raw = base64.standard_b64decode(b64).decode("utf-8")
        except Exception as e:
            raise VeraLabResolutionError(f"Invalid SIGMARAIL_STRATEGY_BASE64: {e}") from e
        source = "base64"
    else:
        raise VeraLabResolutionError(
            "No algorithm JSON: set SIGMARAIL_STRATEGY_PATH, SIGMARAIL_STRATEGY_ID, or SIGMARAIL_STRATEGY_BASE64"
        )

    assert raw is not None
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    spec = parse_algorithm_spec_for_main_py(raw)

    return ResolvedVeraLab(
        spec=spec,
        raw_json=raw,
        source=source,
        ir_id=ir_id,
        content_hash_sha256=h,
    )
