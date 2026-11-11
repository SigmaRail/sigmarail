"""Config path defaults and compatibility behavior for installed SigmaRail."""

from __future__ import annotations

from pathlib import Path

import pytest

from sigmarail import config as config_module


@pytest.fixture(autouse=True)
def reset_app_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module.app_config, "mode", "prod")
    monkeypatch.setattr(config_module.app_config, "_config_cache", None)


def use_test_user_config_dir(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(
        config_module,
        "user_config_dir",
        lambda appname, appauthor=False: str(path / appname),
    )


def test_default_config_uses_lowercase_platformdirs_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("SIGMARAIL_HOME", raising=False)
    use_test_user_config_dir(monkeypatch, tmp_path / "user-config")

    assert config_module.get_config_dir() == tmp_path / "user-config" / "sigmarail"
    assert config_module._get_config_path() == (
        tmp_path / "user-config" / "sigmarail" / "config.yaml"
    )


def test_sigmarail_home_overrides_user_and_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "config.yaml").write_text("database: {}\n", encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setenv("SIGMARAIL_HOME", str(tmp_path / "custom-sigmarail"))
    use_test_user_config_dir(monkeypatch, tmp_path / "user-config")

    assert config_module.get_config_dir() == tmp_path / "custom-sigmarail"
    assert config_module._get_config_path() == (
        tmp_path / "custom-sigmarail" / "config.yaml"
    )


def test_existing_project_config_remains_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    local_config = project / "config.yaml"
    local_config.write_text("database: {}\n", encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.delenv("SIGMARAIL_HOME", raising=False)
    use_test_user_config_dir(monkeypatch, tmp_path / "user-config")

    assert config_module._get_config_path() == local_config


def test_test_mode_uses_per_user_test_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    user_config = tmp_path / "user-config" / "sigmarail"
    user_config.mkdir(parents=True)
    test_config = user_config / "config-test.yaml"
    test_config.write_text("database: {}\n", encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.delenv("SIGMARAIL_HOME", raising=False)
    use_test_user_config_dir(monkeypatch, tmp_path / "user-config")
    config_module.app_config.mode = "test"

    assert config_module._get_config_path() == test_config
    assert config_module.create_shared_parser().parse_args(["--mode", "test"]).mode == "test"


def test_update_config_value_creates_user_config_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    user_config = tmp_path / "user-config" / "sigmarail"
    monkeypatch.chdir(project)
    monkeypatch.delenv("SIGMARAIL_HOME", raising=False)
    use_test_user_config_dir(monkeypatch, tmp_path / "user-config")

    config_module.update_config_value("database.host", "localhost")

    config_path = user_config / "config.yaml"
    assert config_path.is_file()
    assert config_module.yaml.safe_load(config_path.read_text(encoding="utf-8")) == {
        "database": {"host": "localhost"}
    }
