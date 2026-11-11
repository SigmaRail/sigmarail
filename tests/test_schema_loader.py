"""Schema loader phases and non-destructive reconciliation behavior."""

import json
from types import SimpleNamespace

import sigmarail.database as database


def test_reconciliation_adds_missing_columns_and_updates_comments():
    expected = [{"name": "prices", "columns": [
        {"name": "close", "type": "Float64", "comment": "Closing price"},
        {"name": "volume", "type": "UInt64", "comment": "Share volume"},
    ]}]
    actual = [("prices", "close", "Float64", "Old description")]

    statements, issues = database._schema_reconciliation_statements(expected, actual)

    assert not issues
    assert statements == [
        "ALTER TABLE `prices` COMMENT COLUMN `close` 'Closing price'",
        "ALTER TABLE `prices` ADD COLUMN IF NOT EXISTS `volume` UInt64 COMMENT 'Share volume'",
    ]


def test_reconciliation_reports_extra_columns_by_default():
    expected = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": ""}]}]
    actual = [("prices", "close", "Float64", ""), ("prices", "plugin_value", "String", "")]

    statements, issues = database._schema_reconciliation_statements(expected, actual)

    assert statements == []
    assert len(issues) == 1
    assert "plugin_value" in issues[0]
    assert "--drop-extra-columns" in issues[0]


def test_reconciliation_drops_extra_columns_only_when_explicitly_enabled():
    expected = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": ""}]}]
    actual = [("prices", "close", "Float64", ""), ("prices", "plugin_value", "String", "")]

    statements, issues = database._schema_reconciliation_statements(expected, actual, True)

    assert not issues
    assert statements == ["ALTER TABLE `prices` DROP COLUMN IF EXISTS `plugin_value`"]


def test_reconciliation_type_changes_require_an_explicit_migration():
    expected = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": ""}]}]
    actual = [("prices", "close", "Decimal(18, 4)", "")]

    statements, issues = database._schema_reconciliation_statements(expected, actual, True)

    assert statements == []
    assert "explicit migration required" in issues[0]


def test_reconciliation_ignores_type_formatting_whitespace_but_preserves_quoted_values():
    expected = [{"name": "prices", "columns": [
        {"name": "stage", "type": "Tuple(UInt32, UInt32, Float64)", "comment": ""},
        {"name": "label", "type": "Enum8('slow move' = 1)", "comment": ""},
    ]}]
    actual = [
        ("prices", "stage", "Tuple(\n UInt32,\n UInt32,\n Float64\n)", ""),
        ("prices", "label", "Enum8('slow  move'=1)", ""),
    ]

    statements, issues = database._schema_reconciliation_statements(expected, actual)

    assert statements == []
    assert len(issues) == 1
    assert "prices.label: type is" in issues[0]


def test_load_schema_creates_tables_then_drops_views_alters_and_recreates(tmp_path, monkeypatch):
    schema = tmp_path / "schema"
    schema.mkdir()
    first = schema / "001.sql"
    second = schema / "002.sql"
    first.write_text(
        "CREATE VIEW IF NOT EXISTS source_view AS SELECT close FROM prices;\n"
        "CREATE TABLE IF NOT EXISTS prices (close Float64) ENGINE = Memory;\n"
        "DROP VIEW IF EXISTS source_view;\n",
        encoding="utf-8",
    )
    second.write_text(
        "CREATE VIEW IF NOT EXISTS dependent_view AS SELECT close FROM source_view;\n"
        "DROP VIEW IF EXISTS dependent_view;\n",
        encoding="utf-8",
    )
    package = tmp_path / "package"
    (package / "spec").mkdir(parents=True)
    contract = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": "Closing"}]}]
    (package / "spec" / "lineage-manifest.json").write_text(json.dumps({"tables": contract}), encoding="utf-8")
    calls = []

    class FakeClient:
        def command(self, sql):
            calls.append(("command", " ".join(sql.split())))

        def query(self, sql):
            calls.append(("query", "system.columns"))
            return SimpleNamespace(result_rows=[("prices", "close", "Float64", "Old")])

    monkeypatch.setattr(database, "get_schema_dir", lambda: schema)
    monkeypatch.setattr(database, "get_schema_files", lambda: [first, second])
    monkeypatch.setattr(database, "get_database_config", lambda: SimpleNamespace(database="sigmarail_test"))
    monkeypatch.setattr(database, "_validate_test_mode_safety", lambda: None)
    monkeypatch.setattr(database, "get_client", lambda: FakeClient())
    monkeypatch.setattr(database, "__file__", str(package / "database.py"))

    assert database.load_schema()
    commands = [value for kind, value in calls if kind == "command"]
    assert commands[0].startswith("CREATE TABLE")
    assert commands[1] == "DROP VIEW IF EXISTS `dependent_view`" or commands[1] == "DROP VIEW IF EXISTS dependent_view"
    assert commands[2] == "DROP VIEW IF EXISTS source_view"
    assert commands[3].startswith("ALTER TABLE `prices` COMMENT COLUMN `close` 'Closing'")
    assert commands[4].startswith("CREATE VIEW IF NOT EXISTS source_view")
    assert commands[5].startswith("CREATE VIEW IF NOT EXISTS dependent_view")


def test_load_schema_preview_is_read_only_and_prints_actions(tmp_path, monkeypatch, capsys):
    schema = tmp_path / "schema"
    schema.mkdir()
    sql_file = schema / "001.sql"
    sql_file.write_text(
        "CREATE TABLE IF NOT EXISTS prices (close Float64) ENGINE = Memory;"
        "DROP VIEW IF EXISTS price_view;"
        "CREATE VIEW IF NOT EXISTS price_view AS SELECT close FROM prices;",
        encoding="utf-8",
    )
    package = tmp_path / "package"
    (package / "spec").mkdir(parents=True)
    contract = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": "Closing"}]}]
    (package / "spec" / "lineage-manifest.json").write_text(json.dumps({"tables": contract}), encoding="utf-8")
    commands = []

    class FakeClient:
        def command(self, sql):
            commands.append(sql)

        def query(self, sql):
            if "system.tables" in sql:
                return SimpleNamespace(result_rows=[("prices",)])
            return SimpleNamespace(result_rows=[("prices", "close", "Float64", "Old")])

    monkeypatch.setattr(database, "get_schema_dir", lambda: schema)
    monkeypatch.setattr(database, "get_schema_files", lambda: [sql_file])
    monkeypatch.setattr(database, "get_database_config", lambda: SimpleNamespace(database="sigmarail_test"))
    monkeypatch.setattr(database, "_validate_test_mode_safety", lambda: None)
    monkeypatch.setattr(database, "get_client", lambda: FakeClient())
    monkeypatch.setattr(database, "__file__", str(package / "database.py"))

    assert database.load_schema(apply=False)
    assert commands == []
    output = capsys.readouterr().out
    assert "Preview (read-only)" in output
    assert "COMMENT COLUMN `close` 'Closing'" in output
    assert "drop 1, create 1" in output


def test_schema_cli_defaults_to_preview_and_supports_apply(monkeypatch):
    import sys
    import sigmarail.schema as schema_cli

    calls = []
    monkeypatch.setattr(schema_cli, "process_shared_args", lambda args: None)
    monkeypatch.setattr(
        schema_cli,
        "load_schema",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    monkeypatch.setattr(sys, "argv", ["sigmarail-schema"])
    assert schema_cli.main() == 0
    monkeypatch.setattr(sys, "argv", ["sigmarail-schema", "--apply", "--drop-extra-columns"])
    assert schema_cli.main() == 0

    assert calls == [
        {"drop_extra_columns": False, "apply": False},
        {"drop_extra_columns": True, "apply": True},
    ]


def test_load_schema_stops_on_undeclared_columns_without_dropping_views(tmp_path, monkeypatch):
    schema = tmp_path / "schema"
    schema.mkdir()
    sql_file = schema / "001.sql"
    sql_file.write_text(
        "CREATE TABLE IF NOT EXISTS prices (close Float64) ENGINE = Memory;"
        "DROP VIEW IF EXISTS price_view;"
        "CREATE VIEW IF NOT EXISTS price_view AS SELECT close FROM prices;",
        encoding="utf-8",
    )
    package = tmp_path / "package"
    (package / "spec").mkdir(parents=True)
    contract = [{"name": "prices", "columns": [{"name": "close", "type": "Float64", "comment": ""}]}]
    (package / "spec" / "lineage-manifest.json").write_text(json.dumps({"tables": contract}), encoding="utf-8")
    calls = []

    class FakeClient:
        def command(self, sql):
            calls.append(" ".join(sql.split()))

        def query(self, sql):
            return SimpleNamespace(result_rows=[
                ("prices", "close", "Float64", ""),
                ("prices", "local_extension", "String", ""),
            ])

    monkeypatch.setattr(database, "get_schema_dir", lambda: schema)
    monkeypatch.setattr(database, "get_schema_files", lambda: [sql_file])
    monkeypatch.setattr(database, "get_database_config", lambda: SimpleNamespace(database="sigmarail_test"))
    monkeypatch.setattr(database, "_validate_test_mode_safety", lambda: None)
    monkeypatch.setattr(database, "get_client", lambda: FakeClient())
    monkeypatch.setattr(database, "__file__", str(package / "database.py"))

    assert not database.load_schema()
    assert len(calls) == 1 and calls[0].startswith("CREATE TABLE")


def test_http_sql_file_execution_preserves_statement_order(tmp_path, monkeypatch):
    sql_file = tmp_path / "ordered.sql"
    statements = ["DROP VIEW IF EXISTS sample_view", "CREATE VIEW sample_view AS SELECT 1 AS value"]
    sql_file.write_text(";\n".join(statements) + ";\n", encoding="utf-8")
    calls = []

    class FakeClient:
        def command(self, sql):
            calls.append(sql.strip())

    monkeypatch.setattr(database, "get_client", lambda: FakeClient())

    assert database._execute_sql_file_http(sql_file)
    assert calls == statements
