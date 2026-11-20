from __future__ import annotations

import pytest

from sigmarail import config, credentials


def test_empty_local_password_resolves_username_and_password_from_keyring(monkeypatch):
    monkeypatch.setattr(config.app_config, "mode", "prod")
    monkeypatch.setattr(
        credentials,
        "get_clickhouse_credentials",
        lambda: {"user": "stockuser", "password": "test-secret"},
    )

    resolved = config._apply_local_clickhouse_keyring(config.DatabaseConfig())

    assert resolved.user == "stockuser"
    assert resolved.password == "test-secret"
    assert resolved.database == "sigmarail"
    assert resolved.host == "localhost"


def test_config_file_password_takes_precedence_over_keyring(monkeypatch):
    monkeypatch.setattr(config.app_config, "mode", "prod")
    monkeypatch.setattr(
        credentials,
        "get_clickhouse_credentials",
        lambda: pytest.fail("must not read Keychain when config already has a password"),
    )
    configured = config.DatabaseConfig(user="config-user", password="config-secret")

    resolved = config._apply_local_clickhouse_keyring(configured)

    assert resolved == configured


def test_test_mode_never_falls_back_to_local_keyring(monkeypatch):
    monkeypatch.setattr(config.app_config, "mode", "test")
    monkeypatch.setattr(
        credentials,
        "get_clickhouse_credentials",
        lambda: pytest.fail("test mode must not inspect local Keychain"),
    )

    resolved = config._apply_local_clickhouse_keyring(config.DatabaseConfig())

    assert resolved.user == "default"
    assert resolved.password == ""


def test_keyring_failure_does_not_replace_config(monkeypatch):
    monkeypatch.setattr(config.app_config, "mode", "prod")

    def raise_store_error():
        raise credentials.CredentialStoreError("vault unavailable")

    monkeypatch.setattr(credentials, "get_clickhouse_credentials", raise_store_error)
    configured = config.DatabaseConfig()

    assert config._apply_local_clickhouse_keyring(configured) == configured
