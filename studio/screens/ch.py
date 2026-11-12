"""ClickHouse client helper for Screening Studio API."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any


def _ensure_verabasel_path() -> None:
    """Prefer monorepo VeraBase/src over any stale installed package."""
    configured = os.environ.get("VERA_BASE_SOURCE", "").strip()
    candidates = [Path(configured).expanduser()] if configured else [
        parent / "VeraBase" / "src" for parent in Path(__file__).resolve().parents
    ]
    vb_src = next((path for path in candidates if path.is_dir()), None)
    if vb_src is None:
        return
    path = str(vb_src)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


def get_ch_client() -> Any:
    """Return a fresh ClickHouse client.

    Studio and Core share SigmaRail's database configuration and test-mode
    safety checks. A fresh client per request also avoids sharing a
    clickhouse-connect client across concurrent DRF requests.
    """
    from sigmarail.database import get_client

    return get_client()
