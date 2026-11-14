"""Secure operating-system credential storage used by SigmaRail local installs."""

from __future__ import annotations

import json
from typing import Any


CLICKHOUSE_KEYRING_SERVICE = "sigmarail/clickhouse"
CLICKHOUSE_KEYRING_ACCOUNT = "local"
_SECURE_BACKENDS = (
    "keyring.backends.macOS",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
)


class CredentialStoreError(RuntimeError):
    """Raised when a supported secure credential backend is unavailable."""


def _keyring() -> Any:
    try:
        import keyring
    except ImportError as exc:
        raise CredentialStoreError("Install SigmaRail's keyring support to use Keychain") from exc
    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        raise CredentialStoreError("Could not access the operating-system credential store") from exc
    module = backend.__class__.__module__
    if getattr(backend, "priority", 0) <= 0 or not module.startswith(_SECURE_BACKENDS):
        raise CredentialStoreError("No supported secure operating-system credential store is available")
    return keyring


def get_clickhouse_credentials() -> dict[str, str] | None:
    """Return the local ClickHouse username/password from the native OS vault."""
    keyring = _keyring()
    try:
        stored = keyring.get_password(CLICKHOUSE_KEYRING_SERVICE, CLICKHOUSE_KEYRING_ACCOUNT)
    except Exception as exc:
        raise CredentialStoreError("Could not read ClickHouse credentials from the OS vault") from exc
    if not stored:
        return None
    try:
        value = json.loads(stored)
    except json.JSONDecodeError as exc:
        raise CredentialStoreError("Stored ClickHouse credential entry is invalid") from exc
    if not isinstance(value, dict):
        raise CredentialStoreError("Stored ClickHouse credential entry is invalid")
    username = value.get("username")
    password = value.get("password")
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise CredentialStoreError("Stored ClickHouse credential entry is incomplete")
    return {"user": username.strip(), "password": password}


def set_clickhouse_credentials(username: str, password: str) -> None:
    """Store local ClickHouse credentials without writing them to SigmaRail config files."""
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise ValueError("ClickHouse username and password must both be non-empty")
    keyring = _keyring()
    try:
        keyring.set_password(
            CLICKHOUSE_KEYRING_SERVICE,
            CLICKHOUSE_KEYRING_ACCOUNT,
            json.dumps({"username": username.strip(), "password": password}, separators=(",", ":")),
        )
    except Exception as exc:
        raise CredentialStoreError("Could not save ClickHouse credentials to the OS vault") from exc


def delete_clickhouse_credentials() -> None:
    """Remove the local ClickHouse credential entry from the native OS vault."""
    keyring = _keyring()
    try:
        keyring.delete_password(CLICKHOUSE_KEYRING_SERVICE, CLICKHOUSE_KEYRING_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as exc:
        raise CredentialStoreError("Could not delete ClickHouse credentials from the OS vault") from exc
