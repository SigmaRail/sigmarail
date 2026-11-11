"""ClickHouse-backed schema and generated-source checks."""

import json
import os
import re
from pathlib import Path

import clickhouse_connect
import pytest

from sigmarail.config import get_schema_files
from sigmarail.sql_script import split_sql_statements


@pytest.fixture(scope="module")
def test_client(request, pytestconfig):
    if pytestconfig.getoption("--sigmarail-clickhouse"):
        # Reuse the session client and initialized fixture database managed by pytest.
        yield request.getfixturevalue("global_client")
        return
    if os.environ.get("SIGMARAIL_RUN_CLICKHOUSE_TESTS") != "1":
        pytest.skip("Set SIGMARAIL_RUN_CLICKHOUSE_TESTS=1 to use the disposable sigmarail_test database")
    client = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=int(os.environ.get("SIGMARAIL_TEST_HTTP_PORT", "8134")),
        username=os.environ.get("SIGMARAIL_TEST_USER", "default"),
        password=os.environ.get("SIGMARAIL_TEST_PASSWORD", ""),
        database="sigmarail_test",
        connect_timeout=3,
    )
    active_db = client.query("SELECT currentDatabase()").result_rows[0][0]
    if active_db != "sigmarail_test":
        client.close()
        pytest.fail(f"Refusing schema integration test against unexpected database {active_db!r}")
    yield client
    client.close()


def test_clickhouse_has_all_schema_objects(test_client):
    expected = set()
    for path in get_schema_files():
        for statement in split_sql_statements(path.read_text(encoding="utf-8")):
            head = statement.strip()
            match = re.match(
                r"(?is)^CREATE\s+(?:TABLE|(?:MATERIALIZED\s+)?VIEW)\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)",
                head,
            )
            if match:
                expected.add(match.group(1))
    actual = {
        row[0]
        for row in test_client.query(
            "SELECT name FROM system.tables WHERE database = currentDatabase()"
        ).result_rows
    }
    assert expected <= actual, f"Schema objects missing from sigmarail_test: {sorted(expected - actual)}"
    assert {"sep", "sfp", "tickers", "daily", "daily_metrics", "screener_price_tech_daily"} <= actual


def test_clickhouse_loaded_generated_synthetic_sources(test_client):
    manifest_path = os.environ.get("SIGMARAIL_TEST_SYNTHETIC_MANIFEST")
    if not manifest_path:
        pytest.skip("generated-source count contract applies to pytest-managed synthetic data")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert manifest["provider_data"] is False
    for table, row_count in manifest["tables"].items():
        actual = test_client.query(f"SELECT count() FROM `{table}`").result_rows[0][0]
        assert actual == row_count, f"{table}: expected {row_count} synthetic rows, got {actual}"
