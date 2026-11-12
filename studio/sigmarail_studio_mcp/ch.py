"""Fresh ClickHouse client per call (no shared process-wide client)."""
from __future__ import annotations

from typing import Any, Callable

from vera_query_core.ch_settings import connect_clickhouse, resolve_clickhouse_settings_unified


def get_client() -> Any:
    settings = resolve_clickhouse_settings_unified(require_password=False)
    return connect_clickhouse(settings)


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
