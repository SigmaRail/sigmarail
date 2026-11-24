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


def test_runtime_configuration_reads_container_secret_files(monkeypatch, tmp_path):
    clickhouse_password = tmp_path / "clickhouse-password"
    clickhouse_password.write_text("runtime-db-secret\n", encoding="utf-8")
    sharadar_key = tmp_path / "sharadar-key"
    sharadar_key.write_text("runtime-source-secret\n", encoding="utf-8")
    monkeypatch.setattr(config.app_config, "mode", "prod")
    monkeypatch.setattr(config.app_config, "_config_cache", None)
    monkeypatch.setattr(config, "_root_config_cache", None)
    monkeypatch.setenv("SIGMARAIL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIGMARAIL_DATABASE_HOST", "clickhouse.internal")
    monkeypatch.setenv("SIGMARAIL_DATABASE_NAME", "sigmarail")
    monkeypatch.setenv("SIGMARAIL_DATABASE_USER", "loader")
    monkeypatch.setenv("SIGMARAIL_DATABASE_PASSWORD_FILE", str(clickhouse_password))
    monkeypatch.setenv("SIGMARAIL_SHARADAR_API_KEY_FILE", str(sharadar_key))
    monkeypatch.setattr(
        credentials,
        "get_clickhouse_credentials",
        lambda: pytest.fail("mounted secret should take precedence over Keychain"),
    )
    monkeypatch.setattr(
        credentials,
        "get_sharadar_api_key",
        lambda: pytest.fail("mounted secret should take precedence over Keychain"),
    )

    result = config.load_typed_config()

    assert result.database.host == "clickhouse.internal"
    assert result.database.user == "loader"
    assert result.database.password == "runtime-db-secret"
    assert result.sharadar.api_key == "runtime-source-secret"


def test_missing_runtime_secret_file_fails_without_echoing_secret_path(monkeypatch, tmp_path):
    monkeypatch.setattr(config.app_config, "mode", "prod")
    monkeypatch.setattr(config.app_config, "_config_cache", None)
    monkeypatch.setattr(config, "_root_config_cache", None)
    monkeypatch.setenv("SIGMARAIL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIGMARAIL_SHARADAR_API_KEY_FILE", str(tmp_path / "missing-secret"))
    monkeypatch.setattr(credentials, "get_clickhouse_credentials", lambda: None)
    monkeypatch.setattr(credentials, "get_sharadar_api_key", lambda: None)

    with pytest.raises(RuntimeError, match="Could not read runtime secret file for SIGMARAIL_SHARADAR_API_KEY") as exc:
        config.load_typed_config()

    assert str(tmp_path) not in str(exc.value)


def test_sharadar_key_can_be_stored_and_read_from_keyring(monkeypatch):
    values = {}

    class FakeKeyring:
        def set_password(self, service, account, value):
            values[(service, account)] = value

        def get_password(self, service, account):
            return values.get((service, account))

        def delete_password(self, service, account):
            values.pop((service, account), None)

    monkeypatch.setattr(credentials, "_keyring", lambda: FakeKeyring())

    credentials.set_sharadar_api_key(" test-api-key ")

    assert credentials.get_sharadar_api_key() == "test-api-key"
    credentials.delete_sharadar_api_key()
    assert credentials.get_sharadar_api_key() is None
