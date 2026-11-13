"""Non-mutating output sanitization for run/report artifacts (never storage)."""
from __future__ import annotations

from functools import wraps
import json
import re
from typing import Any

REDACTED = "[REDACTED]"
SAFE_ERROR = "Unable to load run/report data"


def _normalized(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _credential(key: str) -> bool:
    name = _normalized(key)
    return any(part in name for part in (
        "password", "passwd", "secret", "token", "apikey", "accesskey",
        "privatekey", "consumerkey", "authorization", "credential",
    )) or name in {"pwd", "auth", "key"}


def _configuration(key: str) -> bool:
    return _normalized(key) in {
        "config", "configuration", "configjson", "configurationjson",
        "environment", "env", "extraenv", "artifactjson", "parameters",
        "leanconfig", "dockerconfig", "extradockerconfig",
        "algorithmconfiguration", "algorithmconfigurationjson",
    }


def sanitize_artifact(value: Any, *, configuration: bool = False, _depth: int = 0,
                      _within_configuration: bool = False, _environment: bool = False) -> Any:
    """Copy containers, redact credentials, and retain JSON strings as strings.

    Opaque non-configuration strings are preserved; this is not secret scanning.
    Malformed/opaque configuration is withheld, without logging its contents.
    """
    if _depth > 64:
        return REDACTED
    def visit(item: Any, config: bool = False, environment: bool = False) -> Any:
        return sanitize_artifact(
            item, configuration=config, _depth=_depth + 1,
            _within_configuration=_within_configuration or configuration,
            _environment=environment,
        )

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = _normalized(str(key))
            if _credential(str(key)):
                result[key] = REDACTED
            elif name in {"error", "errormessage", "exception", "traceback"}:
                result[key] = SAFE_ERROR if item else item
            else:
                result[key] = visit(item, _configuration(str(key)), name in {"env", "extraenv", "environment"})
        return result
    if isinstance(value, (list, tuple)):
        items = [visit(item, configuration, _environment) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    if isinstance(value, str):
        if value == REDACTED:
            return value
        stripped = value.lstrip()
        if stripped.startswith(('{', '[', '"')):
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                return REDACTED if configuration or _within_configuration else value
            return json.dumps(visit(decoded, configuration, _environment), ensure_ascii=False)
        if "=" in value and (not configuration or _environment):
            key, item = value.split("=", 1)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                return key + "=" + (REDACTED if _credential(key) else visit(item, _configuration(key)))
        if configuration:
            return REDACTED
    return value


def safe_artifact_output(function):
    """Sanitize before serialization and suppress boundary exception details."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return sanitize_artifact(function(*args, **kwargs))
        except Exception:
            return {"error": SAFE_ERROR, "code": "query_failed"}
    return wrapped
