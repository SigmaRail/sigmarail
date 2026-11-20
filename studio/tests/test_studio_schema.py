from __future__ import annotations

from pathlib import Path

from screens import schema


def test_applies_studio_sql_files_directly_in_name_order(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "01-first.sql"
    second = tmp_path / "02-second.sql"
    first_sql = "-- first\nCREATE TABLE first_table (id UInt8);"
    second_sql = "-- second\nCREATE TABLE second_table (id UInt8);"
    first.write_text(first_sql + "\n", encoding="utf-8")
    second.write_text(second_sql + "\n", encoding="utf-8")
    monkeypatch.setattr(schema, "SCHEMA_DIR", tmp_path)
    calls: list[str] = []

    class Client:
        def command(self, query: str) -> None:
            calls.append(query)

    assert schema.apply_studio_schema(Client()) == ["01-first.sql", "02-second.sql"]
    assert calls == [first_sql, second_sql]
