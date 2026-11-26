import sys
import types

from sigmarail_studio_mcp.backtest_runner.runner import (
    _lean_container_name,
    _stop_lean_container,
    _update_postgres_job,
    _write_lean_clickhouse_config,
)


class _FakeJobQuery:
    def __init__(self, manager, matches=True):
        self.manager = manager
        self.matches = matches

    def filter(self, **criteria):
        status = criteria.get("status")
        statuses = criteria.get("status__in")
        matches = self.matches
        if status is not None:
            matches = matches and self.manager.status == status
        if statuses is not None:
            matches = matches and self.manager.status in statuses
        return _FakeJobQuery(self.manager, matches)

    def update(self, **updates):
        if not self.matches:
            return 0
        self.manager.status = updates["status"]
        return 1

    def exists(self):
        return self.matches


class _FakeJobManager:
    def __init__(self, status):
        self.status = status

    def filter(self, **criteria):
        return _FakeJobQuery(self).filter(**criteria)


def test_running_update_does_not_overwrite_cancelled_job(monkeypatch):
    jobs = _FakeJobManager("cancelled")
    apps = types.ModuleType("apps")
    apps.__path__ = []
    bridge = types.ModuleType("apps.sigmarail_bridge")
    bridge.__path__ = []
    models = types.ModuleType("apps.sigmarail_bridge.models")
    models.WorkspaceBacktestReference = types.SimpleNamespace(objects=jobs)
    django = types.ModuleType("django")
    django.setup = lambda: None
    timezone = types.ModuleType("django.utils.timezone")
    timezone.now = lambda: None
    django_utils = types.ModuleType("django.utils")
    django_utils.timezone = timezone

    for name, module in {
        "django": django,
        "django.utils": django_utils,
        "django.utils.timezone": timezone,
        "apps": apps,
        "apps.sigmarail_bridge": bridge,
        "apps.sigmarail_bridge.models": models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    assert not _update_postgres_job("job-1", status="running")
    assert jobs.status == "cancelled"


def test_job_scoped_lean_container_name_is_safe_and_deterministic():
    assert _lean_container_name("job-1") == "sigmarail-lean-job-1"
    try:
        _lean_container_name("../unsafe")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe job id was accepted as a Docker container name")


def test_lean_config_overlay_records_container_for_cancel(tmp_path):
    from json import loads

    source = tmp_path / "source.json"
    source.write_text('{"data-folder":"data","environments":{"backtesting":{}}}')
    path = _write_lean_clickhouse_config(
        lean_root=tmp_path,
        project={"lean_config_template": str(source)},
        job_id="job-2",
        host="127.0.0.1",
        port="8123",
        database="sigmarail",
        user="tester",
        password="test",
    )
    assert loads(path.read_text())["container-name"] == "sigmarail-lean-job-2"


def test_cancel_stops_deterministic_lean_container(monkeypatch):
    stopped = []

    class Container:
        status = "running"

        def reload(self):
            return None

        def stop(self, timeout):
            stopped.append(timeout)
            self.status = "exited"

    class Client:
        containers = types.SimpleNamespace(get=lambda name: _container if name == "sigmarail-lean-job-3" else None)

        def close(self):
            return None

    _container = Container()
    docker = types.ModuleType("docker")
    docker.from_env = Client
    errors = types.ModuleType("docker.errors")
    errors.NotFound = type("NotFound", (Exception,), {})
    monkeypatch.setitem(sys.modules, "docker", docker)
    monkeypatch.setitem(sys.modules, "docker.errors", errors)
    _stop_lean_container("job-3")
    assert stopped == [10]
