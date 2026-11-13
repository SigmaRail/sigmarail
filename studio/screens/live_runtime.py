"""Opt-in controller for isolated local LEAN brokerage deployments.

This deliberately exposes a narrow set of actions. It is not a general Docker
or shell proxy, and it never accepts brokerage settings from the caller.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from screens.execution import lean_projects_root

_LOCK = threading.Lock()
_PROJECT_NAME = "SigmaRailTradingLab"
_MAX_CONCURRENT_DEPLOYMENTS = 2


class RuntimeErrorDetail(ValueError):
    """A safe-to-display runtime control error."""


@contextmanager
def profile_management_lock():
    """Serialize account-profile edits with LEAN start/stop operations."""
    if not _LOCK.acquire(blocking=False):
        raise RuntimeErrorDetail("A local LEAN operation is in progress; retry the account change shortly")
    try:
        yield
    finally:
        _LOCK.release()


def account_profile_is_in_use(profile_id: str) -> bool:
    """Fail closed when a profile is referenced by an active managed runtime."""
    state_path = _state_path()
    state = _read_state()
    if state is None and state_path.exists():
        raise RuntimeErrorDetail("Could not verify local LEAN runtime state; profile deletion is blocked")
    for deployment in _deployments(state).values():
        if str(deployment.get("account_profile_id") or "") != str(profile_id):
            continue
        if deployment.get("status") in {"starting", "stopping"}:
            return True
        output_dir = Path(str(deployment.get("output_dir") or ""))
        container = _container_for(output_dir)
        if deployment.get("status") == "running" and not container:
            raise RuntimeErrorDetail("Could not verify the LEAN container for this account; profile deletion is blocked")
        container_status = _inspect_container(container).get("status") if container else "not_found"
        if container_status == "running":
            return True
        if deployment.get("status") == "running" and container_status == "unknown":
            raise RuntimeErrorDetail("Could not verify the LEAN container for this account; profile deletion is blocked")
    return False


def controls_enabled() -> bool:
    return os.environ.get("SIGMARAIL_ENABLE_LOCAL_LEAN_CONTROL", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def request_is_loopback(remote_addr: str | None) -> bool:
    try:
        address = ipaddress.ip_address(remote_addr) if remote_addr else None
        if address and getattr(address, "ipv4_mapped", None):
            address = address.ipv4_mapped
        return bool(address and address.is_loopback)
    except ValueError:
        return False


def request_is_local_control(remote_addr: str | None, origin: str | None, host: str | None) -> bool:
    """Require a loopback peer and an explicitly configured Studio browser origin."""
    if not request_is_loopback(remote_addr) or not origin or not host:
        return False
    try:
        origin_parts = urlsplit(origin)
        host_parts = urlsplit(f"//{host}")
        origin_host = (origin_parts.hostname or "").lower()
        request_host = (host_parts.hostname or "").lower()
        from django.conf import settings

        allowed_origins = {str(value).rstrip("/") for value in getattr(settings, "CORS_ALLOWED_ORIGINS", [])}
        if origin.rstrip("/") not in allowed_origins:
            return False
        if origin_parts.scheme not in {"http", "https"} or origin_parts.path not in {"", "/"}:
            return False
        if not origin_host or origin_host != request_host:
            return False
        if origin_host == "localhost":
            return True
        return ipaddress.ip_address(origin_host).is_loopback
    except ValueError:
        return False


def _root() -> Path:
    return lean_projects_root().expanduser().resolve()


def _project() -> Path:
    root = _root()
    project = (root / _PROJECT_NAME).resolve()
    if root not in project.parents or not (project / "main.py").is_file():
        raise RuntimeErrorDetail("Configured SigmaRailTradingLab LEAN project was not found")
    if not (root / "lean.json").is_file():
        raise RuntimeErrorDetail("LEAN workspace configuration was not found")
    return project


def _state_path() -> Path:
    return Path.home() / ".sigmarail-studio" / "live-runtime.json"


def _read_state() -> dict[str, Any] | None:
    path = _state_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        # Migrate the original single-deployment record in memory. It is persisted
        # in the multi-deployment envelope on the next state update.
        if isinstance(value.get("deployments"), dict):
            return value
        if value.get("deployment_id"):
            return {"version": 2, "deployments": {str(value["deployment_id"]): value}}
        return {"version": 2, "deployments": {}}
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(value: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    payload = value if isinstance(value.get("deployments"), dict) else {
        "version": 2,
        "deployments": {str(value["deployment_id"]): value} if value.get("deployment_id") else {},
    }
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.parent.chmod(0o700)


def _deployments(state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not state:
        return {}
    value = state.get("deployments")
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items() if isinstance(item, dict)}
    if state.get("deployment_id"):
        return {str(state["deployment_id"]): state}
    return {}


def _runtime_root() -> Path:
    return Path.home() / ".sigmarail-studio" / "deployments"


def _deployment_project_path(deployment_id: str) -> Path:
    return _runtime_root() / deployment_id / "project"


def _snapshot_project(source: Path, destination: Path) -> None:
    """Copy LEAN source/config files into an isolated project so CLI targets one run."""
    excluded = {".git", ".venv", "venv", "env", "data", "storage", "live", "results", "backtest-output"}
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(part.startswith(".") or part in excluded for part in relative.parts):
            continue
        if not path.is_file() or (path.suffix.lower() not in {".py", ".cs", ".ipynb", ".css", ".html"} and path.name != "config.json"):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.name == "config.json":
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeErrorDetail("LEAN project config.json is invalid; deployment snapshot was not created") from exc
            if not isinstance(config, dict):
                raise RuntimeErrorDetail("LEAN project config.json must contain an object")
            target.write_text(json.dumps(_sanitize_project_config(config), indent=2) + "\n", encoding="utf-8")
            target.chmod(0o600)
        else:
            shutil.copy2(path, target)
    if not (destination / "main.py").is_file():
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeErrorDetail("Could not create an isolated LEAN source snapshot")


def _sanitize_project_config(value: Any) -> Any:
    """Retain required ClickHouse settings but remove credentials and IR overrides."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("_", "-")
            # The selected IR is passed by this deployment. Stale project parameters
            # must not override it, and a project path must not shadow the IR ID.
            if normalized in {
                "vera-lab-id", "vera-lab-path", "vera-lab-base64",
                "sigmarail-strategy-id", "sigmarail-strategy-path", "sigmarail-strategy-base64",
            }:
                continue
            # Keep database auth needed by LEAN's configured ClickHouse resolver,
            # including both lean.json's spelling and Docker's uppercase env spelling.
            if normalized != "clickhouse-password" and _is_secret_config_key(key):
                continue
            cleaned[key] = _sanitize_project_config(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_project_config(item) for item in value]
    return value


def _lean_binary() -> str:
    binary = shutil.which("lean")
    if not binary:
        raise RuntimeErrorDetail("LEAN CLI was not found on the Studio server PATH")
    return binary


def _is_secret_config_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in (
        "key", "secret", "token", "password", "private", "authorization", "auth-",
        "user-name", "username", "account-id", "account-number", "-account",
    ))


def _private_runtime_config(
    base: dict[str, Any], provider: str, data_provider: str, environment: str, credentials: dict[str, str]
) -> dict[str, Any]:
    """Copy workspace settings but exclude unrelated provider secrets from this run."""
    from screens.brokerage_catalog import BROKERAGES, DATA_PROVIDERS, get_brokerage, get_data_provider

    result = dict(base)
    allowed_credentials = {field["key"] for field in get_brokerage(provider)["credentials"]}
    allowed_credentials.update(field["key"] for field in get_data_provider(data_provider)["credentials"])
    all_broker_credentials = {field["key"] for broker in BROKERAGES.values() for field in broker["credentials"]}
    all_broker_credentials.update(field["key"] for data in DATA_PROVIDERS.values() for field in data["credentials"])
    for key in list(result):
        # Keep the ClickHouse connection used by the strategy's configured test/staging
        # data path; remove credentials for every brokerage except this selected profile.
        if key in all_broker_credentials and key not in allowed_credentials:
            result.pop(key, None)
        elif _is_secret_config_key(key) and key != "clickhouse-password" and key not in allowed_credentials:
            result.pop(key, None)
    descriptor = get_brokerage(provider)
    data_descriptor = get_data_provider(data_provider)
    environment_values: dict[str, str] = {}
    for selected in (descriptor, data_descriptor):
        environment_config = selected.get("environment_config")
        environments = selected.get("environments") or {}
        selected_environment = environment if environment in environments else "live" if "live" in environments else None
        if environment_config and selected_environment:
            value = environments[selected_environment]
            previous = environment_values.get(environment_config)
            if previous is not None and previous != value:
                raise RuntimeErrorDetail(
                    "The selected brokerage and live data feed require conflicting environments; choose a separate data provider"
                )
            environment_values[environment_config] = value
    result.update(environment_values)
    if provider == "alpaca":
        result["alpaca-paper-trading"] = environment == "paper"
    for key, value in credentials.items():
        result[key] = value
    return result


def _run(args: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "LEAN_NO_TELEMETRY": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeErrorDetail("LEAN command timed out; check the LEAN output directory") from exc
    except OSError as exc:
        raise RuntimeErrorDetail(f"Could not start LEAN command: {exc.strerror or 'OS error'}") from exc


def _container_for(output_dir: Path) -> str | None:
    config = output_dir / "config"
    try:
        value = json.loads(config.read_text(encoding="utf-8"))
        name = value.get("container") if isinstance(value, dict) else None
        return name if isinstance(name, str) and name else None
    except (OSError, json.JSONDecodeError):
        return None


def _inspect_container(name: str | None) -> dict[str, Any]:
    if not name:
        return {"status": "unknown", "container_name": None}
    docker = shutil.which("docker")
    if not docker:
        return {"status": "unknown", "container_name": name}
    result = _run([docker, "inspect", "--format", "{{.State.Status}}", name], cwd=_root(), timeout=10)
    status_value = result.stdout.strip() if result.returncode == 0 else "not_found"
    return {"status": status_value, "container_name": name}


def _latest_live_dir(project: Path) -> Path | None:
    live_root = project / "live"
    if not live_root.is_dir():
        return None
    for candidate in sorted(live_root.iterdir(), reverse=True):
        if candidate.is_dir() and (candidate / "log.txt").is_file():
            return candidate.resolve()
    return None


_RUNTIME_STATISTIC_KEYS = {
    "equity", "return", "net profit", "unrealized", "fees", "holdings", "volume",
    "probabilistic sharpe ratio",
}
_SUMMARY_STATISTIC_KEYS = {
    "total trades", "average win", "average loss", "compounding annual return",
    "drawdown", "expectancy", "net profit", "sharpe ratio", "probabilistic sharpe ratio",
    "loss rate", "win rate", "profit-loss ratio", "alpha", "beta", "annual standard deviation",
}


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _lean_metrics(output_dir: Path, allowed_live_root: Path | None) -> dict[str, Any] | None:
    """Read a small, allowlisted view of LEAN's per-algorithm result snapshot."""
    output_dir = output_dir.expanduser().resolve()
    if allowed_live_root is None:
        return None
    allowed_live_root = allowed_live_root.expanduser().resolve()
    if not _is_within(output_dir, allowed_live_root) or not output_dir.is_dir():
        return None

    candidates = sorted(output_dir.glob("L-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for result_path in candidates:
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            modified_at = datetime.fromtimestamp(result_path.stat().st_mtime, timezone.utc).isoformat()
            runtime_statistics = payload.get("runtimeStatistics")
            summary_statistics = payload.get("statistics")
            runtime = {
                str(key): str(value)
                for key, value in runtime_statistics.items()
                if str(key).strip().lower() in _RUNTIME_STATISTIC_KEYS
            } if isinstance(runtime_statistics, dict) else {}
            summary = {
                str(key): str(value)
                for key, value in summary_statistics.items()
                if str(key).strip().lower() in _SUMMARY_STATISTIC_KEYS
            } if isinstance(summary_statistics, dict) else {}

            raw_holdings = payload.get("holdings")
            holdings: list[dict[str, Any]] = []
            if isinstance(raw_holdings, dict):
                for symbol, holding in raw_holdings.items():
                    if not isinstance(holding, dict):
                        continue
                    item = {"symbol": str(symbol)}
                    for source, target in (
                        ("quantity", "quantity"), ("averagePrice", "average_price"),
                        ("marketPrice", "market_price"), ("marketValue", "market_value"),
                        ("unrealizedPnL", "unrealized_pnl"),
                    ):
                        value = holding.get(source)
                        if isinstance(value, (int, float, str)):
                            item[target] = value
                    holdings.append(item)

            raw_orders = payload.get("orders")
            orders: list[dict[str, Any]] = []
            if isinstance(raw_orders, dict):
                for order_id, order in raw_orders.items():
                    if not isinstance(order, dict):
                        continue
                    item = {"id": str(order.get("id", order_id))}
                    for source, target in (
                        ("symbol", "symbol"), ("status", "status"), ("type", "type"),
                        ("quantity", "quantity"), ("price", "price"), ("time", "time"),
                        ("lastUpdateTime", "updated_at"), ("lastFillTime", "filled_at"),
                    ):
                        value = order.get(source)
                        if isinstance(value, (int, float, str)):
                            item[target] = value
                    orders.append(item)
            orders.sort(key=lambda item: str(item.get("updated_at") or item.get("time") or ""), reverse=True)

            return {
                "as_of": modified_at,
                "algorithm_id": result_path.stem,
                "runtime_statistics": runtime,
                "summary_statistics": summary,
                "holdings": holdings,
                "recent_orders": orders[:10],
            }
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _container_config_source(name: str) -> Path | None:
    docker = shutil.which("docker")
    if not docker:
        return None
    result = _run([docker, "inspect", "--format", "{{json .Mounts}}", name], cwd=_root(), timeout=10)
    if result.returncode != 0:
        return None
    try:
        mounts = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    for mount in mounts if isinstance(mounts, list) else []:
        destination = str(mount.get("Destination") or "")
        source = mount.get("Source")
        if destination.endswith("/config.json") and isinstance(source, str):
            path = Path(source)
            try:
                path.chmod(0o600)
                path.parent.chmod(0o700)
            except OSError:
                pass
            return path
    return None


def _remove_runtime_config(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).resolve()
    # Only remove the protected, uniquely named temporary LEAN config directory.
    if path.name == "config.json" and path.parent.name.startswith(("lean-cli-", ".studio-lean-config-")):
        shutil.rmtree(path.parent, ignore_errors=True)


def _stop_started_container(binary: str, project: Path, container_name: str | None) -> None:
    """Best-effort cleanup when startup cannot be registered as a managed run."""
    if not container_name:
        return
    try:
        _run([binary, "live", "stop", str(project)], cwd=_root(), timeout=60)
    except RuntimeErrorDetail:
        pass
    docker = shutil.which("docker")
    if docker:
        try:
            _run([docker, "stop", "--time", "30", container_name], cwd=_root(), timeout=40)
        except RuntimeErrorDetail:
            pass


def _active_account(profile_id: str | None = None):
    from api.models import LiveAccountProfile
    from screens.credential_vault import CredentialVaultError, get_credentials

    try:
        if not profile_id:
            raise RuntimeErrorDetail("Select a brokerage account profile before starting LEAN")
        profile = LiveAccountProfile.objects.get(active=True, pk=profile_id)
    except Exception as exc:
        raise RuntimeErrorDetail("Could not read the local account profile database") from exc
    try:
        credentials = get_credentials(profile)
    except CredentialVaultError as exc:
        raise RuntimeErrorDetail(str(exc)) from exc
    if not credentials:
        raise RuntimeErrorDetail("Save this brokerage account's credentials in the operating-system credential vault first")
    # Compatibility with the initial Alpaca-paper prototype's vault schema.
    if profile.provider == "alpaca" and "api_key" in credentials:
        credentials = {
            "alpaca-api-key": credentials.get("api_key", ""),
            "alpaca-api-secret": credentials.get("api_secret", ""),
        }
    return profile, credentials


def runtime_status() -> dict[str, Any]:
    enabled = controls_enabled()
    state = _read_state()
    deployments = _deployments(state)
    if not deployments:
        project = _project()
        latest = _latest_live_dir(project)
        container = _container_for(latest) if latest else None
        inspected = _inspect_container(container)
        if inspected.get("status") == "running":
            metrics = _lean_metrics(latest, project / "live") if latest else None
            return {
                "enabled": enabled,
                "mode": "unknown",
                "project": _PROJECT_NAME,
                "status": "external_running",
                "active_count": 0,
                "max_concurrent": _MAX_CONCURRENT_DEPLOYMENTS,
                "deployments": [],
                "deployment": {
                    "project": _PROJECT_NAME,
                    "mode": "unknown",
                    "status": "external_running",
                    "container_name": container,
                    "container_status": "running",
                    "output_dir": str(latest),
                    "metrics": metrics,
                },
            }
        return {
            "enabled": enabled,
            "mode": "paper",
            "project": _PROJECT_NAME,
            "status": "idle",
            "active_count": 0,
            "max_concurrent": _MAX_CONCURRENT_DEPLOYMENTS,
            "deployments": [],
            "deployment": None,
        }
    status_deployments: list[dict[str, Any]] = []
    for item in deployments.values():
        deployment = item.copy()
        output_dir = Path(str(deployment.get("output_dir") or ""))
        deployment_id = str(deployment.get("deployment_id") or "")
        recorded_project = deployment.get("project_dir")
        if deployment_id and recorded_project:
            try:
                canonical_deployment_id = str(uuid.UUID(deployment_id))
            except ValueError:
                canonical_deployment_id = ""
            expected_project = _deployment_project_path(canonical_deployment_id).resolve() if canonical_deployment_id else None
            project_dir = Path(str(recorded_project)).expanduser().resolve()
            allowed_live_root = project_dir / "live" if expected_project and project_dir == expected_project else None
        else:
            allowed_live_root = _project() / "live"
        deployment["metrics"] = _lean_metrics(output_dir, allowed_live_root)
        inspected = _inspect_container(_container_for(output_dir))
        local_state = str(deployment.get("status") or "unknown")
        if local_state in {"running", "starting", "stopping"} and inspected["status"] in {"exited", "dead", "not_found"}:
            deployment["status"] = "stopped" if local_state != "starting" else "failed"
        elif local_state == "running" and inspected["status"] != "running":
            deployment["status"] = "unknown"
        deployment["container_name"] = inspected.get("container_name")
        deployment["container_status"] = inspected.get("status")
        status_deployments.append(deployment)
    status_deployments.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
    active = [item for item in status_deployments if item.get("status") in {"running", "starting", "stopping"}]
    aggregate_status = active[0]["status"] if active else (status_deployments[0].get("status") if status_deployments else "idle")
    return {
        "enabled": enabled,
        "mode": status_deployments[0].get("mode", "paper") if status_deployments else "paper",
        "project": _PROJECT_NAME,
        "status": aggregate_status or "unknown",
        "active_count": len(active),
        "max_concurrent": _MAX_CONCURRENT_DEPLOYMENTS,
        "deployments": status_deployments,
        "deployment": status_deployments[0] if status_deployments else None,
    }


def _assert_control_allowed(remote_addr: str | None, origin: str | None, host: str | None) -> None:
    if not controls_enabled():
        raise RuntimeErrorDetail("Local LEAN controls are disabled; set SIGMARAIL_ENABLE_LOCAL_LEAN_CONTROL=1 and restart Studio")
    if not request_is_local_control(remote_addr, origin, host):
        raise RuntimeErrorDetail("Trading controls require an allowed Studio origin on the local machine")


def start_deployment(
    *, remote_addr: str | None, origin: str | None, host: str | None, ir_id: str,
    approval_backtest_run_id: str, profile_id: str | None = None,
    live_confirmation: str | None = None, expected_environment: str | None = None,
) -> dict[str, Any]:
    _assert_control_allowed(remote_addr, origin, host)
    ir_id = (ir_id or "").strip()
    approval_backtest_run_id = (approval_backtest_run_id or "").strip()
    if not ir_id or not approval_backtest_run_id:
        raise RuntimeErrorDetail("A strategy and qualifying backtest run are required")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeErrorDetail("A local LEAN control action is already in progress")
    try:
        state = _read_state() or {"version": 2, "deployments": {}}
        current_deployments = _deployments(state)
        active_count = 0
        for current in current_deployments.values():
            container_state = _inspect_container(_container_for(Path(str(current.get("output_dir") or ""))))
            if container_state.get("status") == "running" or current.get("status") in {"starting", "stopping"}:
                active_count += 1
        if active_count >= _MAX_CONCURRENT_DEPLOYMENTS:
            raise RuntimeErrorDetail(f"Studio allows at most {_MAX_CONCURRENT_DEPLOYMENTS} concurrent LEAN deployments")
        profile, credentials = _active_account(profile_id)
        if expected_environment and profile.environment != expected_environment:
            raise RuntimeErrorDetail(f"Selected account is {profile.environment}; this action requires {expected_environment}")
        from screens.brokerage_catalog import get_brokerage
        descriptor = get_brokerage(profile.provider)
        from screens.brokerage_catalog import get_data_provider
        data_descriptor = get_data_provider(profile.data_provider)
        if profile.environment not in descriptor["environments"]:
            raise RuntimeErrorDetail("The selected account environment is not supported by this LEAN brokerage")
        is_live = profile.environment == "live"
        if is_live and live_confirmation != f"LIVE {profile.display_name}":
            raise RuntimeErrorDetail(f"Live deployment requires the exact confirmation: LIVE {profile.display_name}")
        try:
            from screens.ch import get_ch_client
            from screens.live_promotion import check_promotion_gate

            gate_client = get_ch_client()
            try:
                promotion_gate = check_promotion_gate(
                    gate_client,
                    approval_backtest_run_id=approval_backtest_run_id,
                    ir_id=ir_id,
                )
            finally:
                gate_client.close()
        except Exception as exc:
            raise RuntimeErrorDetail("Could not verify the approval backtest; no LEAN process was started") from exc
        if not promotion_gate.get("ok"):
            message = str(promotion_gate.get("error") or "The selected strategy/backtest pair is not eligible")
            raise RuntimeErrorDetail(f"Promotion gate failed; no LEAN process was started: {message}")
        root = _root()
        project = _project()
        binary = _lean_binary()
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeErrorDetail("Docker CLI was not found on the Studio server PATH")
        docker_check = _run([docker, "info", "--format", "{{.ServerVersion}}"], cwd=root, timeout=15)
        if docker_check.returncode != 0:
            raise RuntimeErrorDetail("Docker is unavailable; start Docker Desktop and retry")
        previous = _latest_live_dir(project)
        if previous:
            previous_name = _container_for(previous)
            if _inspect_container(previous_name).get("status") == "running":
                raise RuntimeErrorDetail("An unmanaged LEAN live container runs from the shared VeraTradingLab project; stop it before starting a Studio deployment")

        deployment_id = str(uuid.uuid4())
        isolated_project = _deployment_project_path(deployment_id)
        try:
            _snapshot_project(project, isolated_project)
        except OSError as exc:
            shutil.rmtree(isolated_project, ignore_errors=True)
            raise RuntimeErrorDetail("Could not create a private source snapshot for this LEAN deployment") from exc
        except RuntimeErrorDetail:
            shutil.rmtree(isolated_project, ignore_errors=True)
            raise
        output_dir = isolated_project / "live" / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')}_studio-{deployment_id[:8]}"
        state = {
            "deployment_id": deployment_id,
            "ir_id": ir_id,
            "approval_backtest_run_id": approval_backtest_run_id,
            "project": _PROJECT_NAME,
            "project_dir": str(isolated_project),
            "mode": profile.environment,
            "brokerage": descriptor["cli_name"],
            "data_provider": data_descriptor["cli_name"],
            "account_profile_id": str(profile.pk),
            "account_name": profile.display_name,
            "account_identifier": profile.account_identifier,
            "status": "starting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(output_dir),
        }
        current_deployments[deployment_id] = state
        state_envelope = {"version": 2, "deployments": current_deployments}
        _write_state(state_envelope)

        # Use a private one-run config overlay. Broker secrets come from Keychain / the
        # platform credential store and never enter the checked-in LEAN config or argv.
        config_overlay_dir = Path(tempfile.mkdtemp(prefix=".studio-lean-config-", dir=root))
        config_overlay_dir.chmod(0o700)
        config_overlay = root / "lean.json"
        runtime_config_path = config_overlay_dir / "lean.json"
        config = _private_runtime_config(
            json.loads(config_overlay.read_text(encoding="utf-8")),
            profile.provider,
            profile.data_provider,
            profile.environment,
            credentials,
        )
        runtime_config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        runtime_config_path.chmod(0o600)
        del credentials, config

        # The project config supplies local ClickHouse Docker environment settings. Only
        # non-secret correlation IDs are passed via this CLI argument.
        extra_docker = json.dumps({"environment": {"DEPLOYMENT_ID": deployment_id, "SIGMARAIL_STRATEGY_ID": ir_id}})
        command = [
            binary, "live", "deploy", str(isolated_project),
            "--lean-config", str(runtime_config_path),
            "--brokerage", descriptor["cli_name"],
            "--data-provider-live", data_descriptor["cli_name"],
        ]
        environment_args: dict[str, str] = {}
        for selected in (descriptor, data_descriptor):
            option = selected.get("environment_option")
            environments = selected.get("environments") or {}
            selected_environment = profile.environment if profile.environment in environments else "live" if "live" in environments else None
            if option and selected_environment:
                value = environments[selected_environment]
                previous = environment_args.get(option)
                if previous is not None and previous != value:
                    raise RuntimeErrorDetail(
                        "The selected brokerage and live data feed require conflicting environments; choose a separate data provider"
                    )
                environment_args[option] = value
        for option, value in environment_args.items():
            command.extend([option, value])
        command.extend([
            "--detach", "--no-update", "--output", str(output_dir),
            "--extra-docker-config", extra_docker,
        ])
        # Recheck strategy/run lineage after snapshot construction and immediately
        # before LEAN launch, so an in-place strategy edit cannot slip through the gate.
        try:
            launch_gate_client = get_ch_client()
            try:
                launch_gate = check_promotion_gate(
                    launch_gate_client,
                    approval_backtest_run_id=approval_backtest_run_id,
                    ir_id=ir_id,
                )
            finally:
                launch_gate_client.close()
        except Exception as exc:
            shutil.rmtree(config_overlay_dir, ignore_errors=True)
            state["status"] = "failed"
            state["error"] = "Could not recheck the approval backtest before LEAN launch"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Could not recheck the approval backtest; no LEAN process was started") from exc
        if (
            not launch_gate.get("ok")
            or launch_gate.get("ir_content_hash") != promotion_gate.get("ir_content_hash")
        ):
            shutil.rmtree(config_overlay_dir, ignore_errors=True)
            state["status"] = "failed"
            state["error"] = "Strategy or approval backtest changed before LEAN launch"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            detail = launch_gate.get("error") or "the saved strategy version changed during launch preparation"
            raise RuntimeErrorDetail(f"Promotion gate changed; no LEAN process was started: {detail}")
        try:
            result = _run(command, cwd=root, timeout=180)
        except RuntimeErrorDetail as exc:
            failed_container = _container_for(output_dir)
            _stop_started_container(binary, isolated_project, failed_container)
            state["status"] = "failed"
            state["error"] = "LEAN launch did not complete; inspect the local run output"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise exc
        finally:
            shutil.rmtree(config_overlay_dir, ignore_errors=True)
        if result.returncode != 0:
            failed_container = _container_for(output_dir)
            if failed_container and _inspect_container(failed_container).get("status") == "running":
                _stop_started_container(binary, isolated_project, failed_container)
            state["status"] = "failed"
            state["error"] = "LEAN failed to launch; inspect the run output locally"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("LEAN failed to launch the selected brokerage deployment; see the local run output")

        container = _container_for(output_dir)
        if not container or _inspect_container(container).get("status") != "running":
            state["status"] = "failed"
            state["error"] = "LEAN returned without a confirmed running Docker container"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("LEAN did not confirm a running container; no deployment was registered")
        mounted_config = _container_config_source(container)
        if not mounted_config:
            _stop_started_container(binary, isolated_project, container)
            state["status"] = "failed"
            state["error"] = "Could not verify the private mounted runtime config"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Could not verify the private Docker-mounted LEAN config; a stop was requested")

        # Register only after Docker confirms that the selected runtime is live. If registry
        # insertion fails, stop the just-started algorithm to avoid an untracked process.
        try:
            from screens.live_promotion import register_paper_deployment

            client = get_ch_client()
            try:
                registered = register_paper_deployment(
                    client,
                    deployment_id=deployment_id,
                    ir_id=ir_id,
                    approval_backtest_run_id=approval_backtest_run_id,
                    lean_environment=f"local-{profile.provider}-{profile.environment}",
                    brokerage=descriptor["cli_name"],
                    account_profile_id=str(profile.pk),
                    account_identifier=profile.account_identifier,
                    promotion_gate=launch_gate,
                )
            finally:
                client.close()
        except Exception as exc:
            _stop_started_container(binary, isolated_project, container)
            _remove_runtime_config(str(mounted_config) if mounted_config else None)
            state["status"] = "failed"
            state["error"] = "Registry write failed; LEAN stop was requested"
            current_deployments[deployment_id] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Deployment registry write failed; a stop was requested for safety") from exc

        state["status"] = "running"
        state["container_name"] = container
        state["runtime_config_source"] = str(mounted_config) if mounted_config else None
        state["registry"] = registered
        current_deployments[deployment_id] = state
        _write_state({"version": 2, "deployments": current_deployments})
        return {"deployment": state}
    finally:
        _LOCK.release()


def start_paper_deployment(**kwargs: Any) -> dict[str, Any]:
    """Backward-compatible name for callers from the paper-only prototype."""
    kwargs["expected_environment"] = "paper"
    return start_deployment(**kwargs)


def control_paper_deployment(
    *, remote_addr: str | None, origin: str | None, host: str | None, action: str,
    deployment_id: str | None = None, confirmation: str | None = None,
) -> dict[str, Any]:
    _assert_control_allowed(remote_addr, origin, host)
    if action not in {"stop", "liquidate"}:
        raise RuntimeErrorDetail("Unsupported deployment action")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeErrorDetail("A local LEAN control action is already in progress")
    try:
        state = _read_state()
        current_deployments = _deployments(state)
        if not deployment_id:
            active_ids = [
                key for key, value in current_deployments.items()
                if value.get("status") == "running"
            ]
            if len(active_ids) != 1:
                raise RuntimeErrorDetail("Select a specific deployment before controlling it")
            deployment_id = active_ids[0]
        selected = current_deployments.get(str(deployment_id))
        if not selected or selected.get("status") != "running":
            raise RuntimeErrorDetail("The selected Studio-managed deployment is not running")
        if action == "liquidate" and selected.get("mode") == "live":
            expected = f"LIQUIDATE {str(deployment_id)[-8:]}"
            if confirmation != expected:
                raise RuntimeErrorDetail(f"Live liquidation requires the exact confirmation: {expected}")
        if action == "stop" and selected.get("mode") == "live":
            expected = f"STOP {str(deployment_id)[-8:]}"
            if confirmation != expected:
                raise RuntimeErrorDetail(f"Stopping a live algorithm requires the exact confirmation: {expected}")
        state = selected.copy()
        project = _project()
        deployment_output = Path(str(state.get("output_dir") or "")).resolve()
        recorded_project = state.get("project_dir")
        if recorded_project:
            isolated_project = Path(str(recorded_project)).resolve()
            expected_project = _deployment_project_path(str(deployment_id)).resolve()
            if isolated_project != expected_project or not (isolated_project / "main.py").is_file():
                raise RuntimeErrorDetail("The selected deployment's isolated LEAN project could not be verified")
        else:
            # Existing single-runtime state created before per-deployment snapshots.
            isolated_project = project
            legacy_live_root = (project / "live").resolve()
            if legacy_live_root not in deployment_output.parents:
                raise RuntimeErrorDetail("The legacy deployment output is outside the configured LEAN project")
        if _latest_live_dir(isolated_project) != deployment_output:
            raise RuntimeErrorDetail("The active LEAN deployment is not the latest project run; refusing an ambiguous control action")
        container = _container_for(deployment_output)
        if _inspect_container(container).get("status") != "running":
            raise RuntimeErrorDetail("The tracked LEAN container is not running")
        binary = _lean_binary()
        verb = "liquidate" if action == "liquidate" else "stop"
        result = _run([binary, "live", verb, str(isolated_project)], cwd=_root(), timeout=90)
        if result.returncode != 0:
            raise RuntimeErrorDetail(f"LEAN {verb} failed; the deployment may still be active")
        if action == "liquidate":
            # Liquidation submits orders; leave LEAN running so the user can confirm
            # broker-side fills before choosing to stop the algorithm.
            state["last_action"] = "liquidate_orders_submitted"
            state["last_action_at"] = datetime.now(timezone.utc).isoformat()
            current_deployments[str(deployment_id)] = state
            _write_state({"version": 2, "deployments": current_deployments})
            return {"deployment": state}

        state["status"] = "stopping"
        current_deployments[str(deployment_id)] = state
        _write_state({"version": 2, "deployments": current_deployments})
        docker = shutil.which("docker")
        if not docker:
            state["status"] = "running"
            current_deployments[str(deployment_id)] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Docker CLI disappeared; LEAN may still be running")
        try:
            stop_result = _run([docker, "stop", "--time", "30", container], cwd=_root(), timeout=40)
        except RuntimeErrorDetail:
            inspected_after_error = _inspect_container(container)
            if inspected_after_error.get("status") in {"exited", "dead", "not_found"}:
                stop_result = subprocess.CompletedProcess([docker, "stop", container], 0, "", "")
            else:
                state["status"] = "running"
                current_deployments[str(deployment_id)] = state
                _write_state({"version": 2, "deployments": current_deployments})
                raise
        inspected_after_stop = _inspect_container(container)
        if inspected_after_stop.get("status") == "running":
            state["status"] = "running"
            current_deployments[str(deployment_id)] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Docker container is still running after the stop request")
        if stop_result.returncode != 0 and inspected_after_stop.get("status") not in {"exited", "dead", "not_found"}:
            state["status"] = "running"
            current_deployments[str(deployment_id)] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("Docker did not confirm the LEAN container stopped")
        state["status"] = "stopped"
        state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        state["last_action"] = action
        _remove_runtime_config(state.get("runtime_config_source"))
        state["runtime_config_source"] = None
        try:
            from screens.ch import get_ch_client
            from screens.live_promotion import update_deployment_status

            client = get_ch_client()
            try:
                update_deployment_status(client, state["deployment_id"], "stopped")
            finally:
                client.close()
        except Exception as exc:
            state["registry_update_error"] = "Local runtime stopped; registry status update failed"
            current_deployments[str(deployment_id)] = state
            _write_state({"version": 2, "deployments": current_deployments})
            raise RuntimeErrorDetail("LEAN stopped, but the deployment registry update failed") from exc
        current_deployments[str(deployment_id)] = state
        _write_state({"version": 2, "deployments": current_deployments})
        return {"deployment": state}
    finally:
        _LOCK.release()
