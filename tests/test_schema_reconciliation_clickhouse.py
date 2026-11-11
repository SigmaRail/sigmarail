"""Real ClickHouse verification for SigmaRail's safe column ALTER statements."""

from __future__ import annotations

from uuid import uuid4

from sigmarail.database import _schema_reconciliation_statements


def test_clickhouse_reconciliation_adds_comments_and_explicitly_drops_extra(global_client):
    """Exercise planned DDL against the disposable sigmarail_test service."""
    database_name = global_client.query("SELECT currentDatabase()").result_rows[0][0]
    assert database_name == "sigmarail_test", f"Refusing integration test against {database_name!r}"

    table_name = f"sigmarail_test_schema_reconcile_{uuid4().hex[:12]}"
    qtable = f"`{table_name}`"
    global_client.command(
        f"CREATE TABLE {qtable} (base_value UInt8 COMMENT 'old description', "
        "extension_value String) ENGINE = Memory"
    )
    try:
        rows = global_client.query(
            "SELECT table, name, type, comment FROM system.columns "
            f"WHERE database = currentDatabase() AND table = '{table_name}'"
        ).result_rows
        contract = [{
            "name": table_name,
            "columns": [
                {"name": "base_value", "type": "UInt8", "comment": "updated description"},
                {"name": "added_value", "type": "String", "comment": "new field"},
            ],
        }]
        statements, issues = _schema_reconciliation_statements(
            contract, list(rows), drop_extra_columns=True
        )
        assert not issues
        assert len(statements) == 3
        for statement in statements:
            # The planner uses unqualified identifiers because SigmaRail's client is
            # connected directly to the configured database.
            global_client.command(statement.replace("`" + table_name + "`", qtable))

        after = {
            name: (column_type, comment)
            for _, name, column_type, comment in global_client.query(
                "SELECT table, name, type, comment FROM system.columns "
                f"WHERE database = currentDatabase() AND table = '{table_name}'"
            ).result_rows
        }
        assert after == {
            "base_value": ("UInt8", "updated description"),
            "added_value": ("String", "new field"),
        }
    finally:
        global_client.command(f"DROP TABLE IF EXISTS {qtable}")
