"""Shared test-mode ClickHouse fixtures, including optional Compose lifecycle."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pytest


def pytest_sessionstart(session):
    """Make every test session fail closed against non-test databases."""
    os.environ["SIGMARAIL_MODE"] = "test"
    from sigmarail import config as config_module

    config_module.app_config.mode = "test"
    config_module.app_config._config_cache = {
        "database": {
            "host": "127.0.0.1",
            "port": 19000,
            "http_port": 18123,
            "user": "default",
            "password": "",
            "database": "sigmarail_test",
            "production_database": "sigmarail",
        },
        "data": {"root": tempfile.gettempdir(), "test": tempfile.gettempdir(), "backups": None},
        "sharadar": {"api_key": "", "base_url": "https://api.sharadar.com/v1.0"},
    }
    config_module._root_config_cache = None


def pytest_addoption(parser):
    parser.addoption(
        "--sigmarail-clickhouse",
        action="store_true",
        default=False,
        help="Start an ephemeral ClickHouse with Docker Compose and run database tests.",
    )


@pytest.fixture(scope="session")
def sigmarail_synthetic_dataset(pytestconfig):
    """Generate provider-free CSVs outside the checkout for managed ClickHouse tests."""
    if not pytestconfig.getoption("--sigmarail-clickhouse"):
        yield None
        return

    from sigmarail.testing import generate_synthetic_dataset

    temp_dir = tempfile.TemporaryDirectory(prefix="sigmarail-synthetic-")
    fixture_dir = Path(temp_dir.name)
    manifest = generate_synthetic_dataset(fixture_dir)
    # ClickHouse's container entrypoint changes ownership of user_files to its
    # service account. Keep the generated files readable by both that account
    # and the host test process after the bind mount is prepared.
    for path in fixture_dir.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    fixture_dir.chmod(0o755)
    generated_env = {
        "SIGMARAIL_TEST_FIXTURE_DIR": str(fixture_dir),
        "SIGMARAIL_TEST_SYNTHETIC_MANIFEST": str(fixture_dir / "synthetic-manifest.json"),
        "SIGMARAIL_TEST_POPULATE_START": "2021-01-01",
        "SIGMARAIL_TEST_POPULATE_END": manifest["end_date"],
        # Ephemeral CI containers are discarded after the session; do not spend
        # the populate command's production-oriented 300s waiting for background
        # merges between every synthetic transform.
        "SIGMARAIL_POPULATE_MERGE_WAIT_SEC": "0",
        "SIGMARAIL_POPULATE_INTER_CHUNK_SLEEP_SEC": "0",
    }
    previous_generated = {key: os.environ.get(key) for key in generated_env}
    os.environ.update(generated_env)
    try:
        yield {"root": fixture_dir, "manifest": manifest}
    finally:
        for key, value in previous_generated.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        temp_dir.cleanup()


@pytest.fixture(scope="session")
def docker_compose_file(sigmarail_synthetic_dataset, pytestconfig):
    """Use SigmaRail's pinned service after generating its temporary source files."""
    return str(pytestconfig.rootpath / "docker-compose.test.yml")


@pytest.fixture(scope="session")
def docker_compose_project_name():
    """Give each pytest process an isolated Compose project and container."""
    return f"sigmarail-pytest-{os.getpid()}"


@pytest.fixture(scope="session")
def docker_setup():
    return ["up --wait"]


@pytest.fixture(scope="session")
def sigmarail_clickhouse_service(request, pytestconfig, sigmarail_synthetic_dataset):
    """Start Compose once per pytest session and export its mapped endpoints."""
    if not pytestconfig.getoption("--sigmarail-clickhouse"):
        yield None
        return

    if shutil.which("docker") is None:
        pytest.fail(
            "--sigmarail-clickhouse requires Docker and the Docker Compose plugin. "
            "Install Docker Desktop/Engine, start its daemon, then retry."
        )
    compose_check = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True, check=False
    )
    if compose_check.returncode:
        pytest.fail(
            "--sigmarail-clickhouse requires the Docker Compose v2 plugin. "
            "Install or enable Compose, then retry.\n"
            + compose_check.stderr.strip()
        )
    docker_check = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False
    )
    if docker_check.returncode:
        pytest.fail(
            "Docker is installed but its daemon is unavailable. Start Docker, then retry.\n"
            + docker_check.stderr.strip()
        )

    # pytest-docker owns startup and teardown; requesting it here makes the
    # service live for every test that consumes this session fixture.
    services = request.getfixturevalue("docker_services")
    http_port = services.port_for("clickhouse", 8123)
    native_port = services.port_for("clickhouse", 9000)
    compose_file = str(pytestconfig.rootpath / "docker-compose.test.yml")
    project = request.getfixturevalue("docker_compose_project_name")
    container_result = subprocess.run(
        [
            "docker", "compose", "-f", compose_file, "-p", project,
            "ps", "-q", "clickhouse",
        ],
        cwd=pytestconfig.rootpath,
        capture_output=True,
        text=True,
        check=False,
    )
    container_id = container_result.stdout.strip()
    if container_result.returncode or not container_id:
        pytest.fail(
            "Docker Compose started but SigmaRail could not identify its ClickHouse container.\n"
            + container_result.stderr.strip()
        )

    overrides = {
        # Keep the application rooted at this checkout, while supplying the
        # test-only connection settings directly to the session fixture below.
        "SIGMARAIL_HOME": str(pytestconfig.rootpath),
        "SIGMARAIL_MODE": "test",
        "SIGMARAIL_TEST_CLICKHOUSE_HOST": "127.0.0.1",
        "SIGMARAIL_TEST_CLICKHOUSE_HTTP_PORT": str(http_port),
        "SIGMARAIL_TEST_CLICKHOUSE_NATIVE_PORT": str(native_port),
        "SIGMARAIL_TEST_CLICKHOUSE_USER": "default",
        "SIGMARAIL_TEST_CLICKHOUSE_PASSWORD": "",
        "SIGMARAIL_TEST_CLICKHOUSE_CONTAINER": container_id,
        "SIGMARAIL_TEST_CLICKHOUSE_USER_FILES": "/var/lib/clickhouse/user_files",
        "SIGMARAIL_TEST_HTTP_PORT": str(http_port),
        "SIGMARAIL_TEST_USER": "default",
        "SIGMARAIL_TEST_PASSWORD": "",
        "SIGMARAIL_RUN_CLICKHOUSE_TESTS": "1",
        "SIGMARAIL_RUN_POPULATE_TESTS": "1",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    yield {"host": "127.0.0.1", "http_port": http_port, "native_port": native_port}
    try:
        logs = subprocess.run(
            ["docker", "compose", "-f", compose_file, "-p", project, "logs", "--no-color", "clickhouse"],
            cwd=pytestconfig.rootpath,
            capture_output=True,
            text=True,
            check=False,
        )
        if logs.stdout or logs.stderr:
            log_dir = Path(pytestconfig.rootpath) / "logs"
            log_dir.mkdir(exist_ok=True)
            (log_dir / f"pytest-clickhouse-{date.today().isoformat()}-{os.getpid()}.log").write_text(
                logs.stdout + logs.stderr, encoding="utf-8"
            )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def sigmarail_test_database(request, pytestconfig, sigmarail_clickhouse_service):
    """Initialize and populate the disposable test database once per run."""
    managed = pytestconfig.getoption("--sigmarail-clickhouse")
    if not managed and os.environ.get("SIGMARAIL_RUN_POPULATE_TESTS") != "1":
        pytest.skip("Use --sigmarail-clickhouse or SIGMARAIL_RUN_POPULATE_TESTS=1 for populated ClickHouse tests")

    from sigmarail import config as config_module
    import sigmarail.database as database_module

    app_config = config_module.app_config
    app_config.mode = "test"
    if managed:
        fixture_root = Path(os.environ["SIGMARAIL_TEST_FIXTURE_DIR"])
        app_config._config_cache = {
            "database": {
                "host": "127.0.0.1",
                "port": os.environ["SIGMARAIL_TEST_CLICKHOUSE_NATIVE_PORT"],
                "http_port": os.environ["SIGMARAIL_TEST_CLICKHOUSE_HTTP_PORT"],
                "user": "default",
                "password": "",
                "database": "sigmarail_test",
                "production_database": "sigmarail",
            },
            "data": {
                "root": str(fixture_root),
                "test": str(fixture_root),
                "backups": None,
            },
            "sharadar": {"api_key": "", "base_url": "https://api.sharadar.com/v1.0"},
        }
        config_module._root_config_cache = None
    else:
        app_config._config_cache = None
    if database_module._client_instance is not None:
        database_module._client_instance.close()
        database_module._client_instance = None
    get_client = database_module.get_client
    client = get_client()
    active_db = client.query("SELECT currentDatabase()").result_rows[0][0]
    if active_db != "sigmarail_test":
        client.close()
        pytest.fail(f"Refusing integration tests against unexpected database {active_db!r}")

    if managed:
        # The Compose service has fresh tmpfs storage for each pytest run.
        # Build its shared baseline once; individual tests may add their own rows.
        from sigmarail.database import initialize_database_command
        from sigmarail.load import DataLoader
        from sigmarail.populate import DataPopulator

        if not initialize_database_command():
            client.close()
            pytest.fail("Could not initialize the sigmarail_test schema")
        from screens.schema import apply_studio_schema

        apply_studio_schema(client)
        if not DataLoader().load_csv_files():
            client.close()
            pytest.fail("Could not load generated synthetic source fixtures")
        populator = DataPopulator()
        if not populator.populate_metrics(
            start_date=os.environ.get("SIGMARAIL_TEST_POPULATE_START", "2021-01-01"),
            end_date=os.environ.get("SIGMARAIL_TEST_POPULATE_END", "2024-12-31"),
            metrics_to_process=["all"],
        ):
            client.close()
            pytest.fail("Could not populate the shared sigmarail_test baseline")

    yield client
    client.close()


@pytest.fixture(scope="session")
def global_client(request, pytestconfig, sigmarail_test_database):
    """Connect only to a fully populated, explicitly enabled sigmarail_test database."""
    return sigmarail_test_database
