import sys
import types

from sigmarail_studio_mcp.backtest_runner.runner import _update_postgres_job


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
