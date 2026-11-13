#!/usr/bin/env python3
"""SigmaRail configuration for Sharadar-to-ClickHouse data loading and transforms."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from platformdirs import user_config_dir

logger = logging.getLogger(__name__)


class AppConfig:
    def __init__(self) -> None:
        self.mode = os.environ.get("SIGMARAIL_MODE", "prod")
        self._config_cache: Optional[Dict[str, Any]] = None


app_config = AppConfig()

DEFAULT_LOG_LEVELS = {
    "root": "INFO",
    "sigmarail": "INFO",
    "clickhouse_driver": "WARNING",
    "clickhouse_driver.connection": "WARNING",
    "clickhouse_driver.streams.native": "WARNING",
    "numba": "WARNING",
    "numba.core.ssa": "WARNING",
    "numba.core.byteflow": "WARNING",
    "pandas": "WARNING",
}


def get_project_root() -> Path:
    """Return the user-configurable working directory for config and data files."""
    configured = os.environ.get("SIGMARAIL_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.cwd()


def get_config_dir() -> Path:
    """Return the default per-user configuration directory, or SIGMARAIL_HOME."""
    configured = os.environ.get("SIGMARAIL_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(user_config_dir("sigmarail", appauthor=False))


def _config_search_dirs() -> list[Path]:
    """Include legacy project-local configs for compatibility and user configs."""
    configured = os.environ.get("SIGMARAIL_HOME", "").strip()
    if configured:
        return [Path(configured).expanduser()]
    local_dir = Path.cwd()
    user_dir = get_config_dir()
    return [local_dir] if local_dir == user_dir else [local_dir, user_dir]


def get_schema_dir() -> Path:
    """Return the packaged, Sharadar-only SQL schema directory."""
    return Path(__file__).resolve().parent / "sql" / "schema"


def get_schema_files() -> list[Path]:
    """Return only the SQL files explicitly admitted to the core schema."""
    manifest_path = Path(__file__).resolve().parent / "sql" / "schema-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directory = get_schema_dir()
    files: list[Path] = []
    for filename in manifest["files"]:
        if Path(filename).name != filename or not filename.endswith(".sql"):
            raise ValueError(f"Invalid SigmaRail core schema filename: {filename!r}")
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"SigmaRail core schema file is missing: {path}")
        files.append(path)
    return files


def configure_logging(
    log_levels: Optional[Dict[str, str]] = None, detailed_output: bool = False
) -> None:
    levels = log_levels or DEFAULT_LOG_LEVELS
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, levels.get("root", "INFO").upper()))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    logs_dir = get_project_root() / "logs"
    logs_dir.mkdir(exist_ok=True)

    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )

    log_file = logs_dir / "sigmarail.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    if detailed_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    for logger_name, level in levels.items():
        if logger_name != "root":
            logging.getLogger(logger_name).setLevel(getattr(logging, level.upper()))

    logging.getLogger(__name__).info(
        "Logging configured - Level: %s, Detailed output: %s, Log file: %s",
        levels.get("root", "INFO"),
        detailed_output,
        log_file,
    )


def set_test_logging(level: str = "INFO") -> None:
    log_levels = {name: level.upper() for name in DEFAULT_LOG_LEVELS.keys()}
    configure_logging(log_levels)


def create_shared_parser() -> argparse.ArgumentParser:
    valid_modes = ["prod"]
    for config_dir in _config_search_dirs():
        for config_file in config_dir.glob("config-*.yaml"):
            mode = config_file.stem.replace("config-", "")
            if mode != "prod" and mode not in valid_modes:
                valid_modes.append(mode)

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--mode",
        type=str,
        default="prod",
        choices=valid_modes,
        help=f"Database mode ({', '.join(valid_modes)}).",
    )
    parent_parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override the default logging level for the 'sigmarail' logger.",
    )
    parent_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output and verbose logging",
    )
    return parent_parser


def process_shared_args(args: argparse.Namespace) -> None:
    valid_modes = ["prod"]
    for config_dir in _config_search_dirs():
        for config_file in config_dir.glob("config-*.yaml"):
            mode = config_file.stem.replace("config-", "")
            if mode != "prod" and mode not in valid_modes:
                valid_modes.append(mode)

    if args.mode not in valid_modes:
        print(
            f"ERROR: Invalid mode '{args.mode}'. Valid modes are: {', '.join(valid_modes)}"
        )
        sys.exit(1)

    if app_config.mode != args.mode:
        app_config.mode = args.mode
        app_config._config_cache = None
        print(f"Running in {args.mode} mode")
        sys.stdout.flush()

    app_config.verbose = getattr(args, "verbose", False)
    detailed_output = app_config.verbose or (
        args.log_level and args.log_level.upper() == "DEBUG"
    )

    log_levels = DEFAULT_LOG_LEVELS.copy()
    if args.log_level:
        for logger_name in log_levels:
            log_levels[logger_name] = args.log_level.upper()

    configure_logging(log_levels, detailed_output)


def _get_config_path() -> Path:
    filename = "config.yaml" if app_config.mode == "prod" else f"config-{app_config.mode}.yaml"
    configured = os.environ.get("SIGMARAIL_HOME", "").strip()
    if configured:
        return Path(configured).expanduser() / filename

    # Honor an existing project-local config for backwards compatibility.
    legacy_path = Path.cwd() / filename
    if legacy_path.exists():
        return legacy_path
    return get_config_dir() / filename


def _load_config_internal() -> Dict[str, Any]:
    if app_config._config_cache is not None:
        return app_config._config_cache

    config_path = _get_config_path()
    if not config_path.exists():
        message = f"Configuration file not found at {config_path}"
        if app_config.mode == "test":
            raise RuntimeError(
                f"{message}. Refusing to continue in test mode to prevent production database fallback."
            )
        logger.warning(message)
        app_config._config_cache = {}
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        app_config._config_cache = config
        return config
    except Exception as e:
        logger.error("Error loading configuration: %s", e)
        app_config._config_cache = {}
        return {}


def load_config() -> Dict[str, Any]:
    return _load_config_internal()


def update_config_value(path: str, value: Any) -> None:
    config_path = _get_config_path()
    config = _load_config_internal()
    keys = path.split(".")
    current = config
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, indent=2)
    app_config._config_cache = None


def get_config_value(path: str, default: Any = None) -> Any:
    config = _load_config_internal()
    keys = path.split(".")
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def is_verbose() -> bool:
    return getattr(app_config, "verbose", False)


def verbose_print(*args: Any, **kwargs: Any) -> None:
    if is_verbose():
        print(*args, **kwargs)


class DatabaseConfig(BaseModel):
    model_config = {"frozen": True}

    host: str = "localhost"
    port: int = 9000
    http_port: int = 8123
    user: str = "default"
    password: str = ""
    database: str = "sigmarail"
    connect_timeout: int = 30
    send_receive_timeout: int = 300
    use_production_screening: bool = False
    production_database: str = "sigmarail"


class DataConfig(BaseModel):
    model_config = {"frozen": True}

    root: str = "data/prod"
    test: str = "data/test"
    backups: Optional[str] = "data/backups"


class SharadarConfig(BaseModel):
    """Direct sharadar.com API (not Nasdaq Data Link). See https://sharadar.com/llms.txt."""

    model_config = {"frozen": True}

    api_key: str = ""
    # Documented host is v1.0; normalize_sharadar_base_url() rewrites legacy /v2.
    base_url: str = "https://api.sharadar.com/v1.0"


def normalize_sharadar_base_url(base_url: str) -> str:
    """Return a usable Sharadar API root (…/v1.0). /v2 404s as of 2026-08."""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "https://api.sharadar.com/v1.0"
    if raw.endswith("/v2"):
        return raw[: -len("/v2")] + "/v1.0"
    return raw


class RootConfig(BaseModel):
    model_config = {"frozen": True}

    mode: str = "prod"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    sharadar: SharadarConfig = Field(default_factory=SharadarConfig)


_root_config_cache: Optional[RootConfig] = None


def _apply_test_clickhouse_env_overrides(database: DatabaseConfig) -> DatabaseConfig:
    """Override DB connection from env when SIGMARAIL_MODE=test (Docker CI / mapped ports)."""
    if app_config.mode != "test":
        return database
    updates: Dict[str, Any] = {}
    host = os.environ.get("SIGMARAIL_TEST_CLICKHOUSE_HOST", "").strip()
    if host:
        updates["host"] = host
    http = os.environ.get("SIGMARAIL_TEST_CLICKHOUSE_HTTP_PORT", "").strip()
    if http:
        updates["http_port"] = int(http)
    native = os.environ.get("SIGMARAIL_TEST_CLICKHOUSE_NATIVE_PORT", "").strip()
    if native:
        updates["port"] = int(native)
    user = os.environ.get("SIGMARAIL_TEST_CLICKHOUSE_USER", "").strip()
    if user:
        updates["user"] = user
    if "SIGMARAIL_TEST_CLICKHOUSE_PASSWORD" in os.environ:
        updates["password"] = os.environ["SIGMARAIL_TEST_CLICKHOUSE_PASSWORD"]
    if updates:
        return database.model_copy(update=updates)
    return database


def _apply_local_clickhouse_keyring(database: DatabaseConfig) -> DatabaseConfig:
    """Use the native credential store only when local config has no password.

    Test mode deliberately skips this fallback so a missing test credential can never
    silently resolve to a local production credential.
    """
    if app_config.mode == "test" or database.password.strip():
        return database
    try:
        from sigmarail.credentials import get_clickhouse_credentials

        credentials = get_clickhouse_credentials()
    except Exception as exc:
        logger.debug("No local ClickHouse credential available from the OS vault: %s", exc)
        return database
    if not credentials:
        return database
    return database.model_copy(update=credentials)


def load_typed_config() -> RootConfig:
    global _root_config_cache
    if _root_config_cache is not None and app_config._config_cache is not None:
        return _root_config_cache

    raw = _load_config_internal()
    database = DatabaseConfig.model_validate(raw.get("database", {}))
    database = _apply_test_clickhouse_env_overrides(database)
    database = _apply_local_clickhouse_keyring(database)
    data = DataConfig.model_validate(raw.get("data", {}))
    sharadar_raw = dict(raw.get("sharadar") or {})
    if "base_url" in sharadar_raw:
        sharadar_raw["base_url"] = normalize_sharadar_base_url(
            str(sharadar_raw.get("base_url") or "")
        )
    sharadar = SharadarConfig.model_validate(sharadar_raw)

    _root_config_cache = RootConfig(
        mode=app_config.mode,
        database=database,
        data=data,
        sharadar=sharadar,
    )
    return _root_config_cache


def get_database_config() -> DatabaseConfig:
    return load_typed_config().database


def get_data_config() -> DataConfig:
    return load_typed_config().data


def get_sharadar_config() -> SharadarConfig:
    return load_typed_config().sharadar
