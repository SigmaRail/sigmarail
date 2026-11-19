"""ClickHouse client helper for Screening Studio API."""

from __future__ import annotations

from typing import Any


def get_ch_client() -> Any:
    """Return a fresh ClickHouse client.

    Studio and Core share SigmaRail's database configuration and test-mode
    safety checks. A fresh client per request also avoids sharing a
    clickhouse-connect client across concurrent DRF requests.
    """
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
