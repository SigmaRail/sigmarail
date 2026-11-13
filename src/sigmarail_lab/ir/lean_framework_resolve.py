"""Load LeanFrameworkV1 JSON from env (mirror pattern of resolver.py; no ClickHouse)."""

from __future__ import annotations

import base64
import os
from pathlib import Path


class LeanFrameworkJsonResolutionError(RuntimeError):
    pass


def resolve_lean_framework_v1_raw() -> str:
    """
    Precedence:
      1. LEAN_FRAMEWORK_V1_PATH — file (optional LEAN_FRAMEWORK_V1_PROJECT_ROOT for relative)
      2. LEAN_FRAMEWORK_V1_BASE64 — inline JSON (cap LEAN_FRAMEWORK_V1_BASE64_MAX)
    """
    path = (os.environ.get("LEAN_FRAMEWORK_V1_PATH") or "").strip()
    project_root = (os.environ.get("LEAN_FRAMEWORK_V1_PROJECT_ROOT") or "").strip()
    b64 = (os.environ.get("LEAN_FRAMEWORK_V1_BASE64") or "").strip()

    if path:
        p = path
        if not os.path.isabs(p):
            if project_root:
                p = os.path.join(project_root, p)
            else:
                p = os.path.abspath(p)
        if not os.path.isfile(p):
            raise LeanFrameworkJsonResolutionError(
                f"LEAN_FRAMEWORK_V1_PATH is not a file: {path!r} (resolved {p!r})"
            )
        return Path(p).read_text(encoding="utf-8")

    if b64:
        max_b64 = int(os.environ.get("LEAN_FRAMEWORK_V1_BASE64_MAX", "1048576"))
        if len(b64) > max_b64:
            raise LeanFrameworkJsonResolutionError("LEAN_FRAMEWORK_V1_BASE64 exceeds size cap")
        try:
            return base64.standard_b64decode(b64).decode("utf-8")
        except Exception as e:
            raise LeanFrameworkJsonResolutionError(f"Invalid LEAN_FRAMEWORK_V1_BASE64: {e}") from e

    raise LeanFrameworkJsonResolutionError(
        "No LeanFrameworkV1 JSON: set LEAN_FRAMEWORK_V1_PATH or LEAN_FRAMEWORK_V1_BASE64"
    )
