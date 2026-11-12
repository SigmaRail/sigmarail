"""ClickHouse client for backtest-job writes.

Resolves connection from CLICKHOUSE_* env vars (same convention as the algorithm runner).
Requires a user with INSERT privileges on backtest_jobs and strategy_algorithm_specs.
"""

from __future__ import annotations

import os
from typing import Any

import clickhouse_connect


def _get_settings() -> dict[str, Any]:
    return {
        "host": os.environ.get("CLICKHOUSE_HOST", "localhost").strip(),
        "port": int(os.environ.get("CLICKHOUSE_HTTP_PORT", os.environ.get("CLICKHOUSE_PORT", "8123"))),
        "username": os.environ.get("CLICKHOUSE_USER", "testuser").strip(),
        "password": os.environ.get("CLICKHOUSE_PASSWORD", "testanalysis").strip(),
        "database": os.environ.get("CLICKHOUSE_DATABASE", "vera").strip(),
    }


def get_client() -> Any:
    s = _get_settings()
    return clickhouse_connect.get_client(
        host=s["host"],
        port=s["port"],
        username=s["username"],
        password=s["password"],
        database=s["database"],
    )
