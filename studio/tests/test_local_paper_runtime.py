"""Credential-vault and local LEAN paper-runtime tests; no broker or Docker calls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from api.models import LiveAccountProfile
from screens import brokerage_catalog, credential_vault, live_runtime


class _FakeKeyring:
    class errors:
        class PasswordDeleteError(Exception):
            pass

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.values[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.values:
            raise self.errors.PasswordDeleteError()
        del self.values[(service, username)]


def _profile(**overrides) -> LiveAccountProfile:
    values = {
        "provider": "alpaca",
        "environment": "paper",
        "keyring_service": "studio-tests/alpaca-paper",
        "keyring_username": "credentials",
    }
    values.update(overrides)
    return LiveAccountProfile(**values)


def test_credential_vault_round_trip_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    keyring = _FakeKeyring()
    monkeypatch.setattr(credential_vault, "_keyring_module", lambda: keyring)
    profile = _profile()

    credential_vault.store_credentials(profile, "test-key", "test-secret")
    assert credential_vault.get_credentials(profile) == {
        "api_key": "test-key",
        "api_secret": "test-secret",
    }
    assert credential_vault.credentials_configured(profile)

    credential_vault.delete_credentials(profile)
    assert credential_vault.get_credentials(profile) is None


def test_credential_vault_rejects_insecure_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnsafeBackend:
        __module__ = "keyring.backends.fail"
        priority = 1

    module = ModuleType("keyring")
    module.get_keyring = lambda: UnsafeBackend()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", module)

    with pytest.raises(credential_vault.CredentialVaultError, match="No supported secure OS"):
        credential_vault._keyring_module()


def test_credential_vault_wraps_backend_save_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenKeyring(_FakeKeyring):
        def set_password(self, service: str, username: str, value: str) -> None:
            raise RuntimeError("backend unavailable")

    monkeypatch.setattr(credential_vault, "_keyring_module", BrokenKeyring)
    with pytest.raises(credential_vault.CredentialVaultError, match="Could not save credentials"):
        credential_vault.store_credentials(_profile(), "test-key", "test-secret")


def test_alpaca_connection_verification_uses_read_only_paper_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"id":"account-id","status":"ACTIVE"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["key"] = request.get_header("Apca-api-key-id")
        captured["secret"] = request.get_header("Apca-api-secret-key")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(credential_vault, "get_credentials", lambda _profile: {
        "alpaca-api-key": "test-key", "alpaca-api-secret": "test-secret",
    })
    monkeypatch.setattr(credential_vault.urllib.request, "urlopen", fake_urlopen)
    result = credential_vault.verify_brokerage_connection(_profile())
    assert result["verified"] is True
    assert result["feed_verified"] is False
    assert captured == {
        "url": "https://paper-api.alpaca.markets/v2/account",
        "method": "GET", "key": "test-key", "secret": "test-secret", "timeout": 8,
    }
    assert "test-secret" not in str(result)


def test_project_snapshot_includes_lean_config_without_unselected_secrets(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("# strategy\n", encoding="utf-8")
    (source / "config.json").write_text(json.dumps({
        "algorithm-language": "Python",
        "clickhouse-password": "test-clickhouse-password",
        "parameters": {"vera-lab-id": "stale-ir", "start-date": "2026-01-01"},
        "docker": {"image": "lean:local", "environment": {
            "KEEP": "yes", "ALPACA-API-SECRET": "unselected",
            "CLICKHOUSE_PASSWORD": "container-clickhouse-password",
            "VERA_LAB_ID": "stale-env-ir", "VERA_LAB_PATH": "stale/path.json",
        }},
    }), encoding="utf-8")
    destination = tmp_path / "isolated"

    live_runtime._snapshot_project(source, destination)

    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    assert config["algorithm-language"] == "Python"
    assert config["clickhouse-password"] == "test-clickhouse-password"
    assert config["docker"]["image"] == "lean:local"
    assert config["docker"]["environment"] == {
        "KEEP": "yes", "CLICKHOUSE_PASSWORD": "container-clickhouse-password",
    }
    assert config["parameters"] == {"start-date": "2026-01-01"}
    assert (destination / "config.json").stat().st_mode & 0o777 == 0o600


def test_legacy_credentials_are_scrubbed_only_after_vault_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyring = _FakeKeyring()
    config_path = tmp_path / "lean.json"
    config_path.write_text(
        json.dumps(
            {
                "alpaca-paper-trading": True,
                "alpaca-environment": "paper",
                "alpaca-api-key": "legacy-key",
                "alpaca-api-secret": "legacy-secret",
                "unrelated-setting": "preserved",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(credential_vault, "lean_projects_root", lambda: tmp_path)
    monkeypatch.setattr(credential_vault, "_keyring_module", lambda: keyring)

    assert credential_vault.migrate_legacy_lean_credentials(_profile()) is True
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert "alpaca-api-key" not in updated
    assert "alpaca-api-secret" not in updated
    assert updated["unrelated-setting"] == "preserved"
    assert credential_vault.get_credentials(_profile()) == {
        "api_key": "legacy-key",
        "api_secret": "legacy-secret",
    }
    assert os.stat(config_path).st_mode & 0o777 == 0o600


def test_legacy_credentials_remain_when_vault_save_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenKeyring(_FakeKeyring):
        def set_password(self, service: str, username: str, value: str) -> None:
            raise RuntimeError("backend unavailable")

    config_path = tmp_path / "lean.json"
    original = {
        "alpaca-paper-trading": True,
        "alpaca-environment": "paper",
        "alpaca-api-key": "legacy-key",
        "alpaca-api-secret": "legacy-secret",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(credential_vault, "lean_projects_root", lambda: tmp_path)
    monkeypatch.setattr(credential_vault, "_keyring_module", BrokenKeyring)

    with pytest.raises(credential_vault.CredentialVaultError):
        credential_vault.migrate_legacy_lean_credentials(_profile())
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


@pytest.mark.django_db
def test_account_api_saves_metadata_but_never_returns_credentials() -> None:
    client = Client()
    payload = {
        "display_name": "Research paper",
        "account_identifier": "paper-123",
        "credentials": {"api_key": "secret-key", "api_secret": "secret-value"},
    }
    with patch("api.views.store_credentials") as store, patch(
        "api.views.migrate_legacy_lean_credentials", return_value=True
    ), patch("api.views.credentials_configured", return_value=True):
        response = client.post(
            "/api/live/accounts",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_HOST="localhost:8001",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Research paper"
    assert body["account_identifier"] == "paper-123"
    assert body["credentials_configured"] is True
    assert "secret-key" not in response.content.decode()
    assert "secret-value" not in response.content.decode()
    store.assert_called_once()
    profile = LiveAccountProfile.objects.get()
    assert profile.account_identifier == "paper-123"


@pytest.mark.django_db
def test_account_api_rejects_remote_writes() -> None:
    client = Client(REMOTE_ADDR="100.64.0.8")
    response = client.post(
        "/api/live/accounts",
        data=json.dumps({"credentials": {"api_key": "k", "api_secret": "s"}}),
        content_type="application/json",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_HOST="localhost:8001",
    )
    assert response.status_code == 403
    assert LiveAccountProfile.objects.count() == 0


@pytest.mark.django_db
def test_account_api_allows_multiple_profiles_for_same_broker_environment() -> None:
    client = Client()
    base = {
        "provider": "alpaca", "environment": "paper",
        "credentials": {"alpaca-api-key": "key", "alpaca-api-secret": "secret"},
    }
    with patch("api.views.store_credentials"), patch("api.views.migrate_legacy_lean_credentials", return_value=True), patch("api.views.credentials_configured", return_value=True):
        first = client.post("/api/live/accounts", data=json.dumps({**base, "display_name": "Paper one"}), content_type="application/json", HTTP_ORIGIN="http://localhost:5173", HTTP_HOST="localhost:8001")
        second = client.post("/api/live/accounts", data=json.dumps({**base, "display_name": "Paper two"}), content_type="application/json", HTTP_ORIGIN="http://localhost:5173", HTTP_HOST="localhost:8001")
    assert first.status_code == second.status_code == 200
    profiles = list(LiveAccountProfile.objects.order_by("display_name"))
    assert len(profiles) == 2
    assert profiles[0].provider == profiles[1].provider == "alpaca"
    assert profiles[0].environment == profiles[1].environment == "paper"
    assert profiles[0].keyring_service != profiles[1].keyring_service


@pytest.mark.django_db
def test_disabled_account_stays_disabled_when_metadata_is_edited() -> None:
    profile = LiveAccountProfile.objects.create(
        provider="alpaca", data_provider="alpaca", environment="paper",
        display_name="Paper account", active=False,
        keyring_service="studio-tests/disabled-profile",
    )
    client = Client()
    with patch("api.views.store_credentials"), patch("api.views.credentials_configured", return_value=False):
        response = client.post(
            "/api/live/accounts",
            data=json.dumps({"id": str(profile.pk), "provider": "alpaca", "data_provider": "alpaca", "environment": "paper", "display_name": "Renamed account"}),
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_HOST="localhost:8001",
        )
    assert response.status_code == 200
    profile.refresh_from_db()
    assert profile.display_name == "Renamed account"
    assert profile.active is False


@pytest.mark.django_db
def test_profile_delete_is_rejected_while_deployment_uses_account() -> None:
    profile = LiveAccountProfile.objects.create(
        provider="alpaca", data_provider="alpaca", environment="paper",
        display_name="Paper account", keyring_service="studio-tests/active-profile",
    )
    client = Client()
    with patch("api.views.live_runtime.account_profile_is_in_use", return_value=True), patch("api.views.delete_credentials") as delete:
        response = client.delete(
            f"/api/live/accounts/{profile.pk}",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_HOST="localhost:8001",
        )
    assert response.status_code == 409
    assert LiveAccountProfile.objects.filter(pk=profile.pk).exists()
    delete.assert_not_called()


def test_local_control_requires_loopback_and_allowed_matching_origin() -> None:
    assert live_runtime.request_is_local_control(
        "127.0.0.1", "http://localhost:5173", "localhost:8001"
    )
    assert not live_runtime.request_is_local_control(
        "100.64.0.8", "http://localhost:5173", "localhost:8001"
    )
    assert not live_runtime.request_is_local_control(
        "127.0.0.1", "http://example.test", "localhost:8001"
    )


def test_account_profile_in_use_reconciles_stale_running_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "live-runtime.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(live_runtime, "_state_path", lambda: state_path)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: {"deployments": {
        "deployment-id": {
            "account_profile_id": "profile-id",
            "status": "running",
            "output_dir": str(tmp_path / "run"),
        },
    }})
    monkeypatch.setattr(live_runtime, "_container_for", lambda _path: "lean-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "exited"})
    assert live_runtime.account_profile_is_in_use("profile-id") is False


def test_account_profile_delete_fails_closed_when_running_container_cannot_be_inspected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "live-runtime.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(live_runtime, "_state_path", lambda: state_path)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: {"deployments": {
        "deployment-id": {
            "account_profile_id": "profile-id",
            "status": "running",
            "output_dir": str(tmp_path / "run"),
        },
    }})
    monkeypatch.setattr(live_runtime, "_container_for", lambda _path: "lean-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "unknown"})
    with pytest.raises(live_runtime.RuntimeErrorDetail, match="Could not verify the LEAN container"):
        live_runtime.account_profile_is_in_use("profile-id")


def test_runtime_status_detects_unmanaged_running_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "VeraTradingLab"
    output_dir = project / "live" / "external-run"
    monkeypatch.setattr(live_runtime, "_read_state", lambda: None)
    monkeypatch.setattr(live_runtime, "_project", lambda: project)
    monkeypatch.setattr(live_runtime, "_latest_live_dir", lambda _project: output_dir)
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "external-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "running"})

    result = live_runtime.runtime_status()
    assert result["status"] == "external_running"
    assert result["mode"] == "unknown"
    assert result["deployment"]["container_name"] == "external-container"


def test_runtime_status_tracks_two_isolated_deployments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first_id = "10000000-0000-4000-8000-000000000001"
    second_id = "10000000-0000-4000-8000-000000000002"
    deployments_root = tmp_path / "deployments"
    monkeypatch.setattr(live_runtime, "_runtime_root", lambda: deployments_root)
    first = {
        "deployment_id": first_id,
        "status": "running",
        "started_at": "2026-11-04T10:00:00+00:00",
        "project_dir": str(deployments_root / first_id / "project"),
        "output_dir": str(deployments_root / first_id / "project" / "live" / "run"),
    }
    second = {
        "deployment_id": second_id,
        "status": "running",
        "started_at": "2026-11-04T11:00:00+00:00",
        "project_dir": str(deployments_root / second_id / "project"),
        "output_dir": str(deployments_root / second_id / "project" / "live" / "run"),
    }
    monkeypatch.setattr(live_runtime, "_read_state", lambda: {"version": 2, "deployments": {first_id: first, second_id: second}})
    monkeypatch.setattr(live_runtime, "_container_for", lambda output: Path(output).parents[1].name)
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda name: {"status": "running", "container_name": name})

    result = live_runtime.runtime_status()

    assert result["active_count"] == 2
    assert [item["deployment_id"] for item in result["deployments"]] == [second_id, first_id]
    assert result["max_concurrent"] == 2


def test_lean_metrics_reads_allowlisted_per_algorithm_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "deployment" / "live" / "run"
    output.mkdir(parents=True)
    result_path = output / "L-test-algorithm.json"
    result_path.write_text(json.dumps({
        "runtimeStatistics": {
            "Equity": "$25,420.00", "Return": "2.4%", "Unrealized": "$420.00",
            "Net Profit": "$600.00", "Fees": "-$12.00", "Holdings": "$17,320.00",
            "Volume": "$8,400.00", "API key": "must-not-be-returned",
        },
        "statistics": {"Drawdown": "3.1%", "Sharpe Ratio": "1.4", "Private token": "redacted"},
        "holdings": {"NVDA": {
            "quantity": 5, "averagePrice": 800.0, "marketPrice": 884.0,
            "marketValue": 4420.0, "unrealizedPnL": 420.0,
        }},
        "orders": {"42": {
            "id": 42, "symbol": "NVDA", "status": "Filled", "type": "Market",
            "quantity": 5, "price": 884.0, "time": "2026-11-05T14:00:00Z",
        }},
    }), encoding="utf-8")

    result = live_runtime._lean_metrics(output, output.parent)

    assert result is not None
    assert result["algorithm_id"] == "L-test-algorithm"
    assert result["runtime_statistics"]["Equity"] == "$25,420.00"
    assert result["summary_statistics"]["Drawdown"] == "3.1%"
    assert "API key" not in result["runtime_statistics"]
    assert "Private token" not in result["summary_statistics"]
    assert result["holdings"][0]["unrealized_pnl"] == 420.0
    assert result["recent_orders"][0]["status"] == "Filled"


def test_lean_metrics_refuses_snapshot_outside_managed_root(tmp_path: Path) -> None:
    output = tmp_path / "other" / "run"
    output.mkdir(parents=True)
    (output / "L-test.json").write_text("{}", encoding="utf-8")

    assert live_runtime._lean_metrics(output, tmp_path / "managed") is None


def test_start_rejects_more_than_two_concurrent_deployments(monkeypatch: pytest.MonkeyPatch) -> None:
    deployments = {
        str(index): {"deployment_id": str(index), "status": "running", "output_dir": f"/tmp/{index}/live/run"}
        for index in range(2)
    }
    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: {"version": 2, "deployments": deployments})
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "running-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "running"})
    project_access = MagicMock()
    monkeypatch.setattr(live_runtime, "_root", project_access)

    with pytest.raises(live_runtime.RuntimeErrorDetail, match="at most 2 concurrent"):
        live_runtime.start_paper_deployment(
            remote_addr="127.0.0.1",
            origin="http://localhost:5173",
            host="localhost:8001",
            ir_id="ir-test",
            approval_backtest_run_id="run-test",
        )
    project_access.assert_not_called()


def test_paper_start_rejects_live_profile_before_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: None)
    profile = SimpleNamespace(provider="alpaca", data_provider="alpaca", environment="live", display_name="Test account")
    monkeypatch.setattr(live_runtime, "_active_account", lambda _profile_id: (profile, {"alpaca-api-key": "k", "alpaca-api-secret": "s"}))
    lean_binary = MagicMock()
    monkeypatch.setattr(live_runtime, "_lean_binary", lean_binary)

    with pytest.raises(live_runtime.RuntimeErrorDetail, match="requires paper"):
        live_runtime.start_paper_deployment(
            remote_addr="127.0.0.1",
            origin="http://localhost:5173",
            host="localhost:8001",
            ir_id="ir-test",
            approval_backtest_run_id="run-test",
        )
    lean_binary.assert_not_called()


def test_live_start_requires_typed_confirmation_before_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: None)
    monkeypatch.setattr(live_runtime, "_root", lambda: tmp_path)
    monkeypatch.setattr(live_runtime, "_project", lambda: tmp_path / "VeraTradingLab")
    profile = SimpleNamespace(provider="alpaca", data_provider="alpaca", environment="live", display_name="Real profile", account_identifier="")
    monkeypatch.setattr(live_runtime, "_active_account", lambda _profile_id: (profile, {"alpaca-api-key": "k", "alpaca-api-secret": "s"}))
    lean_binary = MagicMock()
    monkeypatch.setattr(live_runtime, "_lean_binary", lean_binary)
    with pytest.raises(live_runtime.RuntimeErrorDetail, match="exact confirmation"):
        live_runtime.start_deployment(
            remote_addr="127.0.0.1", origin="http://localhost:5173", host="localhost:8001",
            ir_id="ir-test", approval_backtest_run_id="run-test", profile_id="profile-id",
            expected_environment="live", live_confirmation="",
        )
    lean_binary.assert_not_called()


def test_runtime_config_drops_unselected_broker_secrets_and_keeps_selected() -> None:
    result = live_runtime._private_runtime_config(
        {"clickhouse-password": "db-secret", "alpaca-api-key": "old", "tradier-access-token": "old-token", "exante-shared-key": "old", "safe": "yes"},
        "alpaca", "alpaca", "paper", {"alpaca-api-key": "selected", "alpaca-api-secret": "selected-secret"},
    )
    assert result["alpaca-api-key"] == "selected"
    assert result["alpaca-api-secret"] == "selected-secret"
    assert "tradier-access-token" not in result
    assert "exante-shared-key" not in result
    assert result["clickhouse-password"] == "db-secret"
    assert result["safe"] == "yes"

    ib_with_polygon = live_runtime._private_runtime_config(
        {"ib-password": "old", "polygon-api-key": "old", "tradier-access-token": "old", "safe": "yes"},
        "interactive_brokers", "polygon", "live", {"ib-user-name": "ib-user", "ib-password": "ib-pass", "ib-account": "DU1", "polygon-api-key": "feed-key"},
    )
    assert ib_with_polygon["ib-password"] == "ib-pass"
    assert ib_with_polygon["polygon-api-key"] == "feed-key"
    assert "tradier-access-token" not in ib_with_polygon


def test_brokerage_catalog_validates_credentials_and_environment_values() -> None:
    assert all(item["default_data_provider"] in brokerage_catalog.DATA_PROVIDERS for item in brokerage_catalog.BROKERAGES.values())
    assert brokerage_catalog.get_brokerage("alpaca")["environments"] == {"paper": "paper", "live": "live"}
    assert brokerage_catalog.validate_credentials("tradier", {"tradier-account-id": "acct", "tradier-access-token": "token"}) == {
        "tradier-account-id": "acct", "tradier-access-token": "token",
    }
    with pytest.raises(ValueError, match="required"):
        brokerage_catalog.validate_credentials("alpaca", {"alpaca-api-key": "key"})
    with pytest.raises(ValueError, match="unsupported"):
        brokerage_catalog.validate_credentials("alpaca", {"arbitrary-shell-value": "x"})
    with pytest.raises(ValueError, match="Unsupported"):
        brokerage_catalog.get_brokerage("arbitrary")
    with pytest.raises(ValueError, match="listed options"):
        brokerage_catalog.validate_credentials(
            "bybit",
            {"bybit-api-key": "key", "bybit-api-secret": "secret", "bybit-vip-level": "VIP99"},
        )


def test_start_passes_secrets_only_in_temporary_config_and_registers_after_container_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "VeraTradingLab"
    project.mkdir()
    (project / "main.py").write_text("# test project\n", encoding="utf-8")
    (project / "config.json").write_text(json.dumps({
        "algorithm-language": "Python",
        "clickhouse-password": "db-secret",
        "parameters": {"vera-lab-id": "stale-ir"},
        "docker": {"environment": {"CLICKHOUSE_PASSWORD": "container-db-secret", "VERA_LAB_PATH": "wrong.json"}},
    }), encoding="utf-8")
    (tmp_path / "lean.json").write_text('{"safe-setting":"preserved"}\n', encoding="utf-8")
    mounted_config = tmp_path / "lean-cli-secret" / "config.json"
    existing = {
        "existing-deployment": {
            "deployment_id": "existing-deployment",
            "status": "running",
            "output_dir": str(tmp_path / "existing" / "live" / "run"),
        }
    }
    profile = SimpleNamespace(pk="profile-id", provider="alpaca", data_provider="alpaca", environment="paper", display_name="Alpaca paper", account_identifier="paper-id")
    captured_config: dict[str, object] = {}
    writes: list[dict[str, object]] = []
    commands: list[list[str]] = []

    def fake_run(args, **_kwargs):
        commands.append(args)
        if args[0] == "/usr/bin/docker":
            return subprocess.CompletedProcess(args, 0, "Docker 1\n", "")
        config_file = Path(args[args.index("--lean-config") + 1])
        captured_config.update(json.loads(config_file.read_text(encoding="utf-8")))
        assert config_file.stat().st_mode & 0o777 == 0o600
        return subprocess.CompletedProcess(args, 0, "started\n", "")

    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: {"version": 2, "deployments": existing})
    monkeypatch.setattr(live_runtime, "_write_state", lambda state: writes.append(state.copy()))
    monkeypatch.setattr(live_runtime, "_root", lambda: tmp_path)
    monkeypatch.setattr(live_runtime, "_project", lambda: project)
    monkeypatch.setattr(live_runtime, "_deployment_project_path", lambda deployment_id: tmp_path / "managed" / deployment_id / "project")
    monkeypatch.setattr(
        live_runtime,
        "_active_account",
        lambda _profile_id: (profile, {"alpaca-api-key": "test-key", "alpaca-api-secret": "test-secret"}),
    )
    monkeypatch.setattr(live_runtime, "_lean_binary", lambda: "/usr/bin/lean")
    monkeypatch.setattr(live_runtime.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(live_runtime, "_latest_live_dir", lambda _project: None)
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "studio-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "running"})
    monkeypatch.setattr(live_runtime, "_container_config_source", lambda _name: mounted_config)
    monkeypatch.setattr(live_runtime, "_run", fake_run)
    ch_client = MagicMock()
    monkeypatch.setattr("screens.ch.get_ch_client", lambda: ch_client)
    monkeypatch.setattr(
        "screens.live_promotion.check_promotion_gate",
        lambda _client, **kwargs: {"ok": True, "run_id": kwargs["approval_backtest_run_id"], "ir_id": kwargs["ir_id"], "ir_content_hash": "strategy-hash"},
    )
    register = MagicMock(return_value={"deployment_id": "deployment-id", "status": "running"})
    monkeypatch.setattr("screens.live_promotion.register_paper_deployment", register)

    result = live_runtime.start_paper_deployment(
        remote_addr="127.0.0.1",
        origin="http://localhost:5173",
        host="localhost:8001",
        ir_id="ir-test",
        approval_backtest_run_id="run-test",
        profile_id="profile-id",
    )

    assert captured_config["alpaca-api-key"] == "test-key"
    assert captured_config["alpaca-api-secret"] == "test-secret"
    assert captured_config["alpaca-environment"] == "paper"
    assert "--data-provider-live" in commands[-1]
    assert commands[-1][commands[-1].index("--data-provider-live") + 1] == "Alpaca"
    assert commands[-1].count("--alpaca-environment") == 1
    assert commands[-1][commands[-1].index("--alpaca-environment") + 1] == "paper"
    assert "test-key" not in " ".join(commands[-1])
    assert "test-secret" not in " ".join(commands[-1])
    assert (tmp_path / "lean.json").read_text(encoding="utf-8") == '{"safe-setting":"preserved"}\n'
    assert not list(tmp_path.glob(".studio-lean-config-*"))
    assert result["deployment"]["status"] == "running"
    assert len(writes[-1]["deployments"]) == 2
    assert writes[-1]["deployments"][result["deployment"]["deployment_id"]]["status"] == "running"
    assert Path(commands[-1][commands[-1].index("deploy") + 1]) == Path(result["deployment"]["project_dir"])
    isolated_config = json.loads((Path(result["deployment"]["project_dir"]) / "config.json").read_text(encoding="utf-8"))
    assert isolated_config["algorithm-language"] == "Python"
    assert isolated_config["clickhouse-password"] == "db-secret"
    assert isolated_config["parameters"] == {}
    assert isolated_config["docker"]["environment"] == {"CLICKHOUSE_PASSWORD": "container-db-secret"}
    docker_config = json.loads(commands[-1][commands[-1].index("--extra-docker-config") + 1])
    assert docker_config["environment"]["VERA_LAB_ID"] == "ir-test"
    assert "VERA_LAB_PATH" not in docker_config["environment"]
    register.assert_called_once()
    assert ch_client.close.call_count == 3


def test_start_does_not_register_when_container_is_not_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "VeraTradingLab"
    project.mkdir()
    (project / "main.py").write_text("# test project\n", encoding="utf-8")
    (tmp_path / "lean.json").write_text("{}\n", encoding="utf-8")
    profile = SimpleNamespace(pk="profile-id", provider="alpaca", data_provider="alpaca", environment="paper", display_name="Alpaca paper", account_identifier="")
    writes: list[dict[str, object]] = []
    run = MagicMock(
        side_effect=lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "ok", "")
    )
    stop_cleanup = MagicMock()
    register = MagicMock()

    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: None)
    monkeypatch.setattr(live_runtime, "_write_state", lambda state: writes.append(state.copy()))
    monkeypatch.setattr(live_runtime, "_root", lambda: tmp_path)
    monkeypatch.setattr(live_runtime, "_project", lambda: project)
    monkeypatch.setattr(live_runtime, "_deployment_project_path", lambda deployment_id: tmp_path / "managed" / deployment_id / "project")
    monkeypatch.setattr(live_runtime, "_active_account", lambda _profile_id: (profile, {"alpaca-api-key": "k", "alpaca-api-secret": "s"}))
    monkeypatch.setattr(live_runtime, "_lean_binary", lambda: "/usr/bin/lean")
    monkeypatch.setattr(live_runtime.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(live_runtime, "_latest_live_dir", lambda _project: None)
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "studio-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "exited"})
    monkeypatch.setattr(live_runtime, "_run", run)
    monkeypatch.setattr(live_runtime, "_stop_started_container", stop_cleanup)
    ch_client = MagicMock()
    monkeypatch.setattr("screens.ch.get_ch_client", lambda: ch_client)
    monkeypatch.setattr(
        "screens.live_promotion.check_promotion_gate",
        lambda _client, **kwargs: {"ok": True, "run_id": kwargs["approval_backtest_run_id"], "ir_id": kwargs["ir_id"], "ir_content_hash": "strategy-hash"},
    )
    monkeypatch.setattr("screens.live_promotion.register_paper_deployment", register)

    with pytest.raises(live_runtime.RuntimeErrorDetail, match="did not confirm a running container"):
        live_runtime.start_paper_deployment(
            remote_addr="127.0.0.1",
            origin="http://localhost:5173",
            host="localhost:8001",
            ir_id="ir-test",
            approval_backtest_run_id="run-test",
        )

    assert next(iter(writes[-1]["deployments"].values()))["status"] == "failed"
    register.assert_not_called()
    stop_cleanup.assert_not_called()
    assert ch_client.close.call_count == 2


def test_failed_promotion_preflight_never_invokes_lean_or_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = SimpleNamespace(
        pk="profile-id", provider="alpaca", data_provider="alpaca", environment="paper",
        display_name="Alpaca paper", account_identifier="paper-id",
    )
    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: None)
    monkeypatch.setattr(live_runtime, "_active_account", lambda _profile_id: (profile, {"alpaca-api-key": "k", "alpaca-api-secret": "s"}))
    monkeypatch.setattr(live_runtime, "_run", MagicMock(side_effect=AssertionError("must not invoke Docker or LEAN")))
    monkeypatch.setattr(live_runtime.shutil, "which", MagicMock(side_effect=AssertionError("must not inspect Docker")))
    client = MagicMock()
    monkeypatch.setattr("screens.ch.get_ch_client", lambda: client)
    monkeypatch.setattr(
        "screens.live_promotion.check_promotion_gate",
        lambda *_args, **_kwargs: {"ok": False, "error": "backtest is not eligible"},
    )

    with pytest.raises(live_runtime.RuntimeErrorDetail, match="no LEAN process was started: backtest is not eligible"):
        live_runtime.start_paper_deployment(
            remote_addr="127.0.0.1", origin="http://localhost:5173", host="localhost:8001",
            ir_id="ir-test", approval_backtest_run_id="run-test", profile_id="profile-id",
        )
    client.close.assert_called_once()


def test_stop_closes_container_removes_runtime_config_and_updates_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "VeraTradingLab" / "live" / "latest"
    runtime_config = tmp_path / "lean-cli-studio" / "config.json"
    runtime_config.parent.mkdir()
    runtime_config.write_text("private config", encoding="utf-8")
    selected_state = {
        "deployment_id": "deployment-id",
        "status": "running",
        "output_dir": str(output_dir),
        "project_dir": str(tmp_path / "managed" / "deployment-id" / "project"),
        "runtime_config_source": str(runtime_config),
    }
    other_state = {
        "deployment_id": "other-deployment",
        "status": "running",
        "output_dir": str(tmp_path / "managed" / "other-deployment" / "project" / "live" / "latest"),
        "project_dir": str(tmp_path / "managed" / "other-deployment" / "project"),
    }
    state = {"version": 2, "deployments": {"deployment-id": selected_state, "other-deployment": other_state}}
    isolated_project = Path(selected_state["project_dir"])
    isolated_project.mkdir(parents=True)
    (isolated_project / "main.py").write_text("# snapshot\n", encoding="utf-8")
    writes: list[dict[str, object]] = []
    run = MagicMock(
        side_effect=[
            subprocess.CompletedProcess(["lean"], 0, "stopped", ""),
            subprocess.CompletedProcess(["docker"], 0, "studio-container", ""),
        ]
    )
    inspect = MagicMock(side_effect=[{"status": "running"}, {"status": "exited"}])
    client = MagicMock()
    update_registry = MagicMock()

    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: state)
    monkeypatch.setattr(live_runtime, "_write_state", lambda value: writes.append(value.copy()))
    monkeypatch.setattr(live_runtime, "_project", lambda: output_dir.parents[1])
    monkeypatch.setattr(live_runtime, "_deployment_project_path", lambda _deployment_id: isolated_project)
    monkeypatch.setattr(live_runtime, "_latest_live_dir", lambda _project: output_dir)
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "studio-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", inspect)
    monkeypatch.setattr(live_runtime, "_lean_binary", lambda: "/usr/bin/lean")
    monkeypatch.setattr(live_runtime.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(live_runtime, "_run", run)
    monkeypatch.setattr("screens.ch.get_ch_client", lambda: client)
    monkeypatch.setattr("screens.live_promotion.update_deployment_status", update_registry)

    result = live_runtime.control_paper_deployment(
        remote_addr="127.0.0.1",
        origin="http://localhost:5173",
        host="localhost:8001",
        action="stop",
        deployment_id="deployment-id",
    )

    assert result["deployment"]["status"] == "stopped"
    assert not runtime_config.parent.exists()
    assert writes[-1]["deployments"]["deployment-id"]["runtime_config_source"] is None
    assert writes[-1]["deployments"]["other-deployment"]["status"] == "running"
    assert run.call_args_list[0].args[0][3] == str(isolated_project)
    update_registry.assert_called_once_with(client, "deployment-id", "stopped")
    client.close.assert_called_once()


def test_liquidate_submits_orders_without_stopping_or_updating_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "VeraTradingLab" / "live" / "latest"
    state = {
        "deployment_id": "deployment-id",
        "status": "running",
        "output_dir": str(output_dir),
        "project_dir": str(tmp_path / "managed" / "deployment-id" / "project"),
    }
    isolated_project = Path(state["project_dir"])
    isolated_project.mkdir(parents=True)
    (isolated_project / "main.py").write_text("# snapshot\n", encoding="utf-8")
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "ok", ""))
    write = MagicMock()
    monkeypatch.setattr(live_runtime, "_assert_control_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_runtime, "_read_state", lambda: state)
    monkeypatch.setattr(live_runtime, "_write_state", write)
    monkeypatch.setattr(live_runtime, "_project", lambda: output_dir.parents[1])
    monkeypatch.setattr(live_runtime, "_deployment_project_path", lambda _deployment_id: isolated_project)
    monkeypatch.setattr(live_runtime, "_latest_live_dir", lambda _project: output_dir)
    monkeypatch.setattr(live_runtime, "_container_for", lambda _output: "studio-container")
    monkeypatch.setattr(live_runtime, "_inspect_container", lambda _name: {"status": "running"})
    monkeypatch.setattr(live_runtime, "_lean_binary", lambda: "/usr/bin/lean")
    monkeypatch.setattr(live_runtime, "_run", run)

    result = live_runtime.control_paper_deployment(
        remote_addr="127.0.0.1", origin="http://localhost:5173", host="localhost:8001", action="liquidate"
    )

    assert result["deployment"]["status"] == "running"
    assert result["deployment"]["last_action"] == "liquidate_orders_submitted"
    assert run.call_args.args[0][1:3] == ["live", "liquidate"]
    assert run.call_args.args[0][3] == str(isolated_project)
    write.assert_called_once()
