"""
Resolve ClickHouse HTTP settings: CLICKHOUSE_* env, then LEAN parameters / lean.json.

Precedence per field: env var → GetParameter/Config aliases → default.
An explicitly empty ClickHouse password is valid and disables password auth.
"""

from __future__ import annotations

import os

from .ch_http import ChHttpSettings

# Defaults when neither env nor LEAN params provide a value (matches historical main.py).
_DEFAULT_HOST = "brooklawn.atmire.us"
_DEFAULT_PORT = "8123"
_DEFAULT_DATABASE = "sigmarail"
_DEFAULT_USER = "testuser"
_DEFAULT_PASSWORD = "testanalysis"


def _env_or_param(
    algorithm,
    env_key: str,
    param_keys: tuple[str, ...],
    default: str,
    *,
    allow_empty: bool = False,
) -> str:
    v = os.environ.get(env_key)
    if v is not None and (allow_empty or str(v).strip() != ""):
        return str(v).strip()
    if algorithm is not None:
        from .lean_runtime_parameters import get_param

        p = get_param(*param_keys, algorithm=algorithm, default=None)
        if p is not None and (allow_empty or str(p).strip() != ""):
            return str(p).strip()
    return default


def resolve_clickhouse_settings(algorithm=None) -> ChHttpSettings:
    """
    Build ChHttpSettings.

    Env: CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_DATABASE, CLICKHOUSE_USER,
    CLICKHOUSE_PASSWORD.

    LEAN parameters use the same CLICKHOUSE_* names as the worker environment.
    """
    host = _env_or_param(
        algorithm,
        "CLICKHOUSE_HOST",
        ("clickhouse-host",),
        _DEFAULT_HOST,
    )
    port = _env_or_param(
        algorithm,
        "CLICKHOUSE_PORT",
        ("clickhouse-http-port",),
        _DEFAULT_PORT,
    )
    database = _env_or_param(
        algorithm,
        "CLICKHOUSE_DATABASE",
        ("clickhouse-database",),
        _DEFAULT_DATABASE,
    )
    user = _env_or_param(
        algorithm,
        "CLICKHOUSE_USER",
        ("clickhouse-user",),
        _DEFAULT_USER,
    )
    password = _env_or_param(
        algorithm,
        "CLICKHOUSE_PASSWORD",
        ("clickhouse-password",),
        _DEFAULT_PASSWORD,
        allow_empty=True,
    )
    return ChHttpSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )
