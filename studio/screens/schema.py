"""Apply Studio-owned ClickHouse SQL files in filename order."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SCHEMA_DIR = Path(__file__).resolve().parent / "sql" / "schema"


def apply_studio_schema(client: Any | None = None) -> list[str]:
    """Execute each Studio schema file as one SQL command and return applied names.

    Files are ordered by name and passed to ClickHouse unchanged. The runner does
    not inspect tables or split SQL objects out of files.
    """
    if client is None:
        from screens.ch import get_ch_client

        client = get_ch_client()
    applied: list[str] = []
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8").strip()
        if not sql:
            continue
        client.command(sql)
        applied.append(path.name)
    return applied


def main() -> int:
    applied = apply_studio_schema()
    print(f"Applied {len(applied)} SigmaRail Studio schema file(s)")
    return 0
