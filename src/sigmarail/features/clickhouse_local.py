"""Start local native ClickHouse (clickhousectl + ~/.clickhouse) when HTTP is down.

Mirrors ``scripts/daily-update.sh`` ensure/start logic so MCP and query services
connect with the Vera ``stockuser`` / ``vera`` database profile from
``scripts/setup-clickhouse.sh``, not a bare clickhousectl default instance.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from sigmarail.features.ch_settings import ClickHouseSettings

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class LocalClickHousePaths:
    server_name: str
    data_root: Path
    config_path: Path
    users_path: Path
    http_ping_url: str


def is_local_host(host: str) -> bool:
    return host.strip().lower() in _LOCAL_HOSTS


def is_connection_refused_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "connection refused" in msg
        or "errno 61" in msg
        or "failed to establish a new connection" in msg
    )


def resolve_local_paths(
    *,
    server_name: str | None = None,
    config_path: str | Path | None = None,
    http_port: int | None = None,
) -> LocalClickHousePaths:
    """Resolve ~/.clickhouse paths (same defaults as ``scripts/daily-update.sh``)."""
    name = (server_name or os.environ.get("CLICKHOUSE_SERVER_NAME", "default")).strip() or "default"
    home = Path.home()
    data_root = Path(os.environ.get("CLICKHOUSE_DATA_ROOT", home / ".clickhouse" / "servers" / name))
    vera_cfg = data_root / "config" / "config.xml"
    legacy_cfg = data_root / "data" / "preprocessed_configs" / "config.xml"

    if config_path is not None:
        cfg = Path(config_path)
    elif os.environ.get("SIGMARAIL_CLICKHOUSE_CONFIG", "").strip():
        cfg = Path(os.environ["SIGMARAIL_CLICKHOUSE_CONFIG"].strip())
    elif vera_cfg.is_file():
        cfg = vera_cfg
    elif legacy_cfg.is_file():
        cfg = legacy_cfg
    elif os.environ.get("CLICKHOUSE_CONFIG", "").strip():
        env_cfg = Path(os.environ["CLICKHOUSE_CONFIG"].strip())
        cfg = env_cfg
        if env_cfg.is_file() and not str(env_cfg).startswith(str(home / ".clickhouse")):
            logger.warning(
                "CLICKHOUSE_CONFIG=%s is outside ~/.clickhouse and no Vera config at %s",
                env_cfg,
                vera_cfg,
            )
    else:
        cfg = vera_cfg

    port = http_port
    if port is None:
        port = int(os.environ.get("CLICKHOUSE_HTTP_PORT", "8123"))
    ping = os.environ.get("CLICKHOUSE_HTTP_URL", "").strip() or f"http://127.0.0.1:{port}/ping"

    users = Path(os.environ.get("CLICKHOUSE_USERS_CONFIG", home / ".clickhouse" / "users.xml"))

    return LocalClickHousePaths(
        server_name=name,
        data_root=data_root,
        config_path=cfg,
        users_path=users,
        http_ping_url=ping,
    )


def should_auto_start_clickhouse(settings: ClickHouseSettings) -> bool:
    if os.environ.get("SIGMARAIL_SKIP_CLICKHOUSE_START", "").strip() == "1":
        return False
    if os.environ.get("SIGMARAIL_AUTO_START_CLICKHOUSE", "").strip().lower() in ("0", "false", "no"):
        return False
    if os.environ.get("SIGMARAIL_MODE", "").strip().lower() == "test":
        return False
    return is_local_host(settings.host)


def clickhouse_http_ready(ping_url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(ping_url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _clickhouse_process_running() -> bool:
    for pattern in ("clickhouse server", "clickhouse-server"):
        try:
            proc = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return True
        except OSError:
            continue
    return False


def _stop_clickhouse_server() -> None:
    for pattern in ("clickhouse server", "clickhouse-server"):
        subprocess.run(
            ["pkill", "-f", pattern],
            capture_output=True,
            check=False,
        )
    time.sleep(2)


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = f"{local_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def _clickhouse_binary() -> Path | None:
    home = Path.home()
    ver_file = home / ".clickhouse" / "default"
    ver = ver_file.read_text(encoding="utf-8").strip() if ver_file.is_file() else "stable"
    candidate = home / ".clickhouse" / "versions" / ver / "clickhouse"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate

    found = shutil.which("clickhouse")
    if found:
        return Path(found)

    versions = sorted((home / ".clickhouse" / "versions").glob("*/clickhouse"))
    if versions:
        return versions[-1]
    return None


def _start_via_config_daemon(paths: LocalClickHousePaths) -> bool:
    if not paths.config_path.is_file():
        logger.error(
            "ClickHouse config not found at %s — run: cd VeraBase && ./scripts/setup-clickhouse.sh",
            paths.config_path,
        )
        return False

    ch_bin = _clickhouse_binary()
    if ch_bin is None:
        logger.error(
            "No clickhouse binary under ~/.clickhouse/versions — install: "
            "curl -fsSL https://clickhouse.com/cli | sh && clickhousectl local install stable"
        )
        return False

    cmd = [str(ch_bin), "server", f"--config-file={paths.config_path}", "--daemon"]
    logger.info("Starting ClickHouse daemon: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=_subprocess_env())
    if proc.returncode != 0:
        logger.warning("clickhouse server --daemon failed (%s): %s", proc.returncode, proc.stderr.strip())
        return False
    return True


def _vera_clickhouse_start_script() -> Path | None:
    """Resolve VeraBase/scripts/start-vera-clickhouse.sh when running from a dev checkout."""
    candidates = [
        Path(__file__).resolve().parents[2] / "scripts" / "start-vera-clickhouse.sh",
    ]
    root = os.environ.get("SIGMARAIL_PROJECT_ROOT", "").strip()
    if root:
        candidates.append(Path(root) / "scripts" / "start-vera-clickhouse.sh")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _start_via_vera_script() -> bool:
    script = _vera_clickhouse_start_script()
    if script is None:
        return False
    logger.info("Starting ClickHouse via %s", script)
    proc = subprocess.run(
        [str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    if proc.stdout.strip():
        logger.info("%s", proc.stdout.strip())
    if proc.returncode != 0:
        logger.warning(
            "start-vera-clickhouse.sh failed (%s): %s",
            proc.returncode,
            (proc.stderr or proc.stdout).strip(),
        )
        return False
    return True


def start_clickhouse_server_once(paths: LocalClickHousePaths) -> bool:
    """Start native ClickHouse once via scripts/start-vera-clickhouse.sh or config daemon."""
    if clickhouse_http_ready(paths.http_ping_url):
        return True

    if _start_via_vera_script():
        time.sleep(2)
        if clickhouse_http_ready(paths.http_ping_url):
            return True

    if _start_via_config_daemon(paths):
        time.sleep(2)
        if clickhouse_http_ready(paths.http_ping_url):
            return True

    return False


def wait_clickhouse_ready(
    paths: LocalClickHousePaths,
    *,
    retries: int | None = None,
    delay_sec: float | None = None,
) -> bool:
    max_retries = retries if retries is not None else int(os.environ.get("CLICKHOUSE_READY_RETRIES", "20"))
    delay = delay_sec if delay_sec is not None else float(os.environ.get("CLICKHOUSE_READY_DELAY", "3"))
    for _ in range(max_retries):
        if clickhouse_http_ready(paths.http_ping_url):
            return True
        time.sleep(delay)
    return False


def _verify_vera_http(settings: ClickHouseSettings, paths: LocalClickHousePaths) -> bool:
    """True when HTTP responds and the configured database is reachable."""
    if not clickhouse_http_ready(paths.http_ping_url):
        return False
    try:
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=settings.host,
            port=int(settings.http_port),
            username=settings.user,
            password=settings.password,
            database=settings.database,
            secure=settings.secure,
            connect_timeout=3,
            send_receive_timeout=3,
        )
        try:
            client.query("SELECT 1")
            return True
        finally:
            client.close()
    except Exception:
        return False


def is_missing_vera_database(exc: BaseException, settings: ClickHouseSettings) -> bool:
    msg = str(exc).lower()
    db = settings.database.lower()
    return db in msg and ("unknown_database" in msg or "does not exist" in msg)


def ensure_clickhouse_running(settings: ClickHouseSettings) -> None:
    """Ensure local ClickHouse is up before MCP/query clients connect."""
    if not should_auto_start_clickhouse(settings):
        return

    paths = resolve_local_paths(http_port=int(settings.http_port))
    max_rounds = int(os.environ.get("CLICKHOUSE_START_MAX_ROUNDS", "3"))

    if _verify_vera_http(settings, paths):
        logger.debug("ClickHouse already responding with database %s", settings.database)
        return

    if clickhouse_http_ready(paths.http_ping_url):
        logger.warning(
            "HTTP port open at %s but database %r unavailable — restarting with Vera config %s",
            paths.http_ping_url,
            settings.database,
            paths.config_path,
        )
        _stop_clickhouse_server()

    for round_idx in range(1, max_rounds + 1):
        if clickhouse_http_ready(paths.http_ping_url):
            return

        if _clickhouse_process_running():
            logger.info(
                "ClickHouse process exists but HTTP not ready (round %s/%s); stopping stale server",
                round_idx,
                max_rounds,
            )
            _stop_clickhouse_server()
        else:
            logger.info("ClickHouse not running (round %s/%s)", round_idx, max_rounds)

        if not start_clickhouse_server_once(paths):
            logger.warning("ClickHouse start attempt failed (round %s/%s)", round_idx, max_rounds)
        elif wait_clickhouse_ready(paths):
            if _verify_vera_http(settings, paths):
                logger.info("ClickHouse ready at %s (database %s)", paths.http_ping_url, settings.database)
                return
            logger.warning(
                "ClickHouse HTTP up but database %r still unavailable after round %s",
                settings.database,
                round_idx,
            )

        _stop_clickhouse_server()

    raise RuntimeError(
        f"ClickHouse did not become ready at {paths.http_ping_url}. "
        f"Config: {paths.config_path}. "
        "Run: cd VeraBase && ./scripts/setup-clickhouse.sh && ./scripts/start-vera-clickhouse.sh"
    )
