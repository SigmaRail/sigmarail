"""Cross-platform OS credential vault adapter for broker credentials."""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from api.models import LiveAccountProfile
from screens.execution import lean_projects_root


class CredentialVaultError(RuntimeError):
    pass


_SECURE_BACKENDS = (
    "keyring.backends.macOS",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
)


def _keyring_module() -> Any:
    try:
        import keyring
    except ImportError as exc:
        raise CredentialVaultError("Python keyring is not installed in the Studio environment") from exc
    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        raise CredentialVaultError("Could not access the operating-system credential store") from exc
    module = backend.__class__.__module__
    if getattr(backend, "priority", 0) <= 0 or not module.startswith(_SECURE_BACKENDS):
        raise CredentialVaultError(
            "No supported secure OS credential store is available; configure macOS Keychain, Windows Credential Manager, or Linux Secret Service"
        )
    return keyring


def credentials_configured(profile: LiveAccountProfile) -> bool:
    try:
        return get_credentials(profile) is not None
    except CredentialVaultError:
        return False


def get_credentials(profile: LiveAccountProfile) -> dict[str, str] | None:
    keyring = _keyring_module()
    try:
        value = keyring.get_password(profile.keyring_service, profile.keyring_username)
    except Exception as exc:
        raise CredentialVaultError("Could not read credentials from the operating-system vault") from exc
    if not value:
        return None
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CredentialVaultError("Stored broker credential entry is invalid") from exc
    if not isinstance(result, dict) or not result or any(
        not isinstance(key, str) or not isinstance(value, str) or not value
        for key, value in result.items()
    ):
        raise CredentialVaultError("Stored broker credentials are incomplete")
    return result


def store_credentials(
    profile: LiveAccountProfile,
    credentials: dict[str, str] | str,
    api_secret: str | None = None,
) -> None:
    # Keep the legacy two-argument form for migration callers and older tests.
    if isinstance(credentials, str):
        if not api_secret:
            raise CredentialVaultError("Both legacy credential values are required")
        payload = {"api_key": credentials, "api_secret": api_secret}
    else:
        payload = credentials
    if not payload or any(not isinstance(key, str) or not isinstance(value, str) or not value for key, value in payload.items()):
        raise CredentialVaultError("Credential values must be non-empty text")
    keyring = _keyring_module()
    try:
        keyring.set_password(
            profile.keyring_service,
            profile.keyring_username,
            json.dumps(payload, separators=(",", ":")),
        )
    except Exception as exc:
        raise CredentialVaultError("Could not save credentials to the operating-system vault") from exc


def delete_credentials(profile: LiveAccountProfile) -> None:
    keyring = _keyring_module()
    try:
        keyring.delete_password(profile.keyring_service, profile.keyring_username)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as exc:
        raise CredentialVaultError("Could not delete credentials from the operating-system vault") from exc


def verify_brokerage_connection(profile: LiveAccountProfile) -> dict[str, Any]:
    """Perform a read-only account check only for brokers with a known safe endpoint."""
    if profile.provider != "alpaca":
        return {
            "supported": False,
            "verified": False,
            "message": "Credentials are configured; connection not verified. Studio has no read-only check for this brokerage.",
            "feed_verified": False,
        }
    credentials = get_credentials(profile)
    if not credentials:
        return {
            "supported": True,
            "verified": False,
            "message": "Add the required Alpaca credentials before verifying the account.",
            "feed_verified": False,
        }
    if "api_key" in credentials:
        credentials = {
            "alpaca-api-key": credentials.get("api_key", ""),
            "alpaca-api-secret": credentials.get("api_secret", ""),
        }
    api_key = credentials.get("alpaca-api-key")
    api_secret = credentials.get("alpaca-api-secret")
    if not api_key or not api_secret:
        return {
            "supported": True,
            "verified": False,
            "message": "Required Alpaca credentials are incomplete.",
            "feed_verified": False,
        }

    endpoint = (
        "https://paper-api.alpaca.markets/v2/account"
        if profile.environment == "paper"
        else "https://api.alpaca.markets/v2/account"
    )
    request = urllib.request.Request(
        endpoint,
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = "Alpaca rejected the saved credentials." if exc.code in {401, 403} else f"Alpaca account check failed (HTTP {exc.code})."
        return {"supported": True, "verified": False, "message": message, "feed_verified": False}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {
            "supported": True,
            "verified": False,
            "message": "Could not complete the read-only Alpaca account check.",
            "feed_verified": False,
        }
    if not isinstance(payload, dict) or not payload.get("id"):
        return {
            "supported": True,
            "verified": False,
            "message": "Alpaca returned an unexpected account response.",
            "feed_verified": False,
        }
    return {
        "supported": True,
        "verified": True,
        "message": "Alpaca account connection verified with a read-only request. Data-feed entitlement is not verified.",
        "account_status": str(payload.get("status") or "unknown")[:32],
        "feed_verified": False,
    }


def migrate_legacy_lean_credentials(profile: LiveAccountProfile) -> bool:
    """Move paper Alpaca keys from lean.json to the OS vault and remove the file copy."""
    root = lean_projects_root().expanduser().resolve()
    config_path = root / "lean.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return credentials_configured(profile)

    if config.get("alpaca-paper-trading") is not True or config.get("alpaca-environment") != "paper":
        return credentials_configured(profile)

    existing = get_credentials(profile)
    api_key = config.get("alpaca-api-key")
    api_secret = config.get("alpaca-api-secret")
    if not existing and isinstance(api_key, str) and api_key and isinstance(api_secret, str) and api_secret:
        store_credentials(profile, api_key, api_secret)
        existing = {"api_key": api_key, "api_secret": api_secret}
    if not existing:
        return False

    changed = "alpaca-api-key" in config or "alpaca-api-secret" in config
    if changed:
        config.pop("alpaca-api-key", None)
        config.pop("alpaca-api-secret", None)
        fd, temporary_name = tempfile.mkstemp(prefix=".lean-config-", dir=root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(config, stream, indent=4)
                stream.write("\n")
            Path(temporary_name).replace(config_path)
            config_path.chmod(0o600)
        except Exception as exc:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise CredentialVaultError("Vault save succeeded, but the legacy LEAN config could not be scrubbed") from exc
    return True
