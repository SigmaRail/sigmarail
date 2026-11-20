"""ClickHouse client helper for Screening Studio API."""

from __future__ import annotations

from typing import Any


def get_ch_client() -> Any:
    """Return a fresh ClickHouse client.

    AppTension's configured direct query path is the canonical connection in
    deployed environments. The legacy SigmaRail config-file fallback remains
    available for local Studio-only runs and tests.
    """
    from django.conf import settings

    if getattr(settings, "SIGMARAIL_CLICKHOUSE_ENABLED", False):
        from apps.sigmarail_bridge.core_data import _clickhouse_client

        return _clickhouse_client()

    import clickhouse_connect

    from sigmarail.config import get_database_config

    config = get_database_config()
    return clickhouse_connect.get_client(
        host=config.host,
        port=config.http_port,
        username=config.user,
        password=config.password,
        database=config.database,
        connect_timeout=config.connect_timeout,
        send_receive_timeout=config.send_receive_timeout or 3600,
        # Level 2 remains read-only but permits safe per-query limits such as
        # max_execution_time used by the screen compiler.
        settings={"readonly": 2},
    )
