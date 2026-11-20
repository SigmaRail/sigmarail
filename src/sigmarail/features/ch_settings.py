from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ClickHouseSettings:
    host: str
    http_port: int
    database: str
    user: str
    password: str
    secure: bool = False
    timeout_seconds: float = 30.0


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


_CLICKHOUSE_ENV_KEYS = (
    "CLICKHOUSE_HOST",
    "CLICKHOUSE_PORT",
    "CLICKHOUSE_HTTP_PORT",
    "CLICKHOUSE_USER",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_DATABASE",
    "CLICKHOUSE_SECURE",
)


def has_clickhouse_env_override() -> bool:
    """True if any ``CLICKHOUSE_*`` env var is set (non-empty)."""
    return any(os.environ.get(k, "").strip() for k in _CLICKHOUSE_ENV_KEYS)


def resolve_clickhouse_settings_from_env(*, require_password: bool = True) -> ClickHouseSettings:
    """
    Resolve ClickHouse HTTP connection settings from CLICKHOUSE_* environment variables.

    This mirrors how LEAN projects tend to pass settings via docker.environment in config.json.
    """
    host = _env("CLICKHOUSE_HOST", "localhost")
    port_s = os.environ.get("CLICKHOUSE_HTTP_PORT", "").strip() or os.environ.get(
        "CLICKHOUSE_PORT", "8123"
    )
    user = _env("CLICKHOUSE_USER", "default")
    password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    if require_password and password == "":
        raise RuntimeError("Missing required environment variable: CLICKHOUSE_PASSWORD")
    database = _env("CLICKHOUSE_DATABASE", "vera")
    secure = os.environ.get("CLICKHOUSE_SECURE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    timeout = float(os.environ.get("CLICKHOUSE_TIMEOUT_SECONDS", "30").strip())
    return ClickHouseSettings(
        host=host,
        http_port=int(port_s),
        database=database,
        user=user,
        password=password,
        secure=secure,
        timeout_seconds=timeout,
    )


def resolve_clickhouse_settings_unified(*, require_password: bool = True) -> ClickHouseSettings:
    """
    ClickHouse settings for services and MCP: ``CLICKHOUSE_*`` env when set, otherwise
    Vera ``config.yaml`` / ``get_database_config()`` (same as local Cursor without env).
    """
    if has_clickhouse_env_override():
        return resolve_clickhouse_settings_from_env(require_password=require_password)
    from vera.config import get_database_config

    db = get_database_config()
    pwd = db.password or ""
    if require_password and not str(pwd).strip():
        raise RuntimeError("Missing database password in config (set CLICKHOUSE_PASSWORD or config password)")
    return ClickHouseSettings(
        host=db.host,
        http_port=int(db.http_port),
        database=db.database,
        user=db.user,
        password=str(pwd),
        secure=False,
        timeout_seconds=float(db.connect_timeout),
    )


def connect_clickhouse(
    settings: ClickHouseSettings,
    *,
    auto_start: bool | None = None,
):  # type: ignore[no-untyped-def]
    """Create a ``clickhouse_connect`` HTTP client from settings.

    When ``auto_start`` is true (default for localhost prod), starts native
    ClickHouse from ``~/.clickhouse`` (``scripts/setup-clickhouse.sh`` config)
    if HTTP is down. Set ``SIGMARAIL_SKIP_CLICKHOUSE_START=1`` to disable.
    """
    import clickhouse_connect

    from sigmarail.features.clickhouse_local import (
        ensure_clickhouse_running,
        is_connection_refused_error,
        is_missing_vera_database,
        should_auto_start_clickhouse,
    )

    if auto_start is None:
        auto_start = should_auto_start_clickhouse(settings)

    def _client():  # type: ignore[no-untyped-def]
        return clickhouse_connect.get_client(
            host=settings.host,
            port=int(settings.http_port),
            username=settings.user,
            password=settings.password,
            database=settings.database,
            secure=settings.secure,
            connect_timeout=int(settings.timeout_seconds),
            send_receive_timeout=int(settings.timeout_seconds),
        )

    if not auto_start:
        return _client()

    try:
        return _client()
    except Exception as exc:
        if not (
            is_connection_refused_error(exc)
            or is_missing_vera_database(exc, settings)
        ):
            raise
        ensure_clickhouse_running(settings)
        return _client()
