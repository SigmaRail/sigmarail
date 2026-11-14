"""HTTP client for Studio Django REST (MCP façade; no ClickHouse)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def studio_base_url() -> str:
    return (os.environ.get("STUDIO_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")


def studio_post(path: str, body: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
    """POST JSON to Studio. Raises ValueError on HTTP/transport errors."""
    url = f"{studio_base_url()}{path if path.startswith('/') else '/' + path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            msg = parsed.get("detail") or detail
        except Exception:
            msg = detail or str(exc)
        raise ValueError(f"Studio HTTP {exc.code}: {msg}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            f"Studio unreachable at {studio_base_url()} ({exc.reason}). "
            "Start Screening Studio and set STUDIO_BASE_URL if needed."
        ) from exc


__all__ = ["studio_base_url", "studio_post"]
