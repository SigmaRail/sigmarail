"""Preview or apply the isolated Alpaca extension schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from sigmarail.config import create_shared_parser, process_shared_args
from sigmarail.database import _split_sql_statements, get_client, get_database_config


def schema_path() -> Path:
    return Path(__file__).resolve().parent / "sql" / "extensions" / "alpaca" / "schema.sql"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or apply SigmaRail's namespaced Alpaca extension schema.",
        parents=[create_shared_parser()],
    )
    parser.add_argument("--apply", action="store_true", help="Execute extension DDL; default is a read-only plan")
    args = parser.parse_args(argv)
    process_shared_args(args)
    source = schema_path()
    if not source.is_file():
        parser.error(f"Alpaca extension schema is missing: {source}")
    statements = _split_sql_statements(source.read_text(encoding="utf-8"))
    config = get_database_config()
    print(f"database={config.database} apply={'yes' if args.apply else 'no'}")
    for statement in statements:
        print(statement.strip() + ";")
    if args.apply:
        client = get_client(config)
        try:
            for statement in statements:
                client.command(statement)
        finally:
            client.close()
        print(f"applied_statements={len(statements)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
