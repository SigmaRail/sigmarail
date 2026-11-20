"""
Resolve ClickHouse HTTP settings: CLICKHOUSE_* env, then LEAN parameters / lean.json.

Precedence per field: non-empty env var → GetParameter/Config aliases → default.
"""

from __future__ import annotations

import os

from .ch_http import ChHttpSettings

# Defaults when neither env nor LEAN params provide a value (matches historical main.py).
_DEFAULT_HOST = "brooklawn.atmire.us"
_DEFAULT_PORT = "8123"
_DEFAULT_DATABASE = "vera"
_DEFAULT_USER = "testuser"
_DEFAULT_PASSWORD = "testanalysis"


def _env_or_param(algorithm, env_key: str, param_keys: tuple[str, ...], default: str) -> str:
    v = os.environ.get(env_key)
    if v is not None and str(v).strip() != "":
        return str(v).strip()
    if algorithm is not None:
        from .lean_runtime_parameters import get_param

        p = get_param(*param_keys, algorithm=algorithm, default=None)
        if p is not None and str(p).strip() != "":
            return str(p).strip()
    return default


def resolve_clickhouse_settings(algorithm=None) -> ChHttpSettings:
    """
    Build ChHttpSettings.

    Env: CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_DATABASE, CLICKHOUSE_USER,
    CLICKHOUSE_PASSWORD.

    Parameter aliases (when algorithm is set): clickhouse-host / vera-host, etc.
    """
    host = _env_or_param(
        algorithm,
        "CLICKHOUSE_HOST",
        ("clickhouse-host", "vera-host"),
        _DEFAULT_HOST,
    )
    port = _env_or_param(
        algorithm,
        "CLICKHOUSE_PORT",
        ("clickhouse-http-port", "vera-port"),
        _DEFAULT_PORT,
    )
    database = _env_or_param(
        algorithm,
        "CLICKHOUSE_DATABASE",
        ("clickhouse-database", "vera-database"),
        _DEFAULT_DATABASE,
    )
    user = _env_or_param(
        algorithm,
        "CLICKHOUSE_USER",
        ("clickhouse-user", "vera-user"),
        _DEFAULT_USER,
    )
    password = _env_or_param(
        algorithm,
        "CLICKHOUSE_PASSWORD",
        ("clickhouse-password", "vera-password"),
        _DEFAULT_PASSWORD,
    )
    return ChHttpSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )
