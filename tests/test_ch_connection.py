from sigmarail_lab.runtime.ch_connection import resolve_clickhouse_settings


def test_explicit_empty_password_is_preserved(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "")

    settings = resolve_clickhouse_settings()

    assert settings.password == ""


def test_missing_password_uses_the_runtime_default(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)

    settings = resolve_clickhouse_settings()

    assert settings.password == "testanalysis"
