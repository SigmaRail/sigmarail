"""Fresh ClickHouse client per call (no shared process-wide client)."""
from __future__ import annotations

from typing import Any, Callable

from screens.ch import get_ch_client


def get_client() -> Any:
    """Use SigmaRail's configured client and safety checks."""
    return get_ch_client()


def call(fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    """Run ``fn(client, **kwargs)`` with a fresh client; wrap errors as envelopes."""
    client = get_client()
    try:
        return fn(client, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
    finally:
        client.close()


def try_call(fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    """Run ``fn(**kwargs)`` (no client); wrap errors as envelopes."""
    try:
        return fn(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "code": "query_failed"}
