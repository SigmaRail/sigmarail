#!/usr/bin/env python3
"""Regenerate module table contracts from their ordered SQL manifests."""

from __future__ import annotations

import json
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_lineage_manifest import _columns_from_create  # noqa: E402

EXTENSIONS = ROOT / "src" / "sigmarail" / "sql" / "extensions"


def build_contract(module: str, files: list[str], source_boundary: str) -> dict:
    tables: list[dict] = []
    seen: set[str] = set()
    for filename in files:
        if Path(filename).name != filename or not filename.endswith(".sql"):
            raise ValueError(f"Invalid SQL filename in {module}: {filename!r}")
        sql_path = EXTENSIONS / module / filename
        sql = sql_path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z_]\w*)`?",
            sql,
            re.I,
        ):
            name = match.group(1)
            if name in seen:
                raise ValueError(f"Duplicate table {name!r} in module {module}")
            columns = _columns_from_create(sql, name)
            if not columns:
                raise ValueError(f"Could not parse columns for {module}.{name}")
            seen.add(name)
            tables.append(
                {
                    "name": name,
                    "kind": "external_extension",
                    "module": module,
                    "schema_file": filename,
                    "columns": columns,
                }
            )
    return {
        "contract_version": 1,
        "module": module,
        "source_boundary": source_boundary,
        "tables": tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed extension contracts differ from the SQL source.",
    )
    args = parser.parse_args()
    registry_path = EXTENSIONS / "modules.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    stale: list[str] = []
    for module, metadata in sorted(registry["modules"].items()):
        manifest_path = EXTENSIONS / module / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("module") != module:
            raise ValueError(f"Module manifest identity mismatch: {manifest_path}")
        contract = build_contract(
            module,
            manifest["files"],
            metadata["source_boundary"],
        )
        destination = EXTENSIONS / module / "contract.json"
        rendered = json.dumps(contract, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != rendered:
                stale.append(str(destination.relative_to(ROOT)))
        else:
            destination.write_text(rendered, encoding="utf-8")
        verb = "checked" if args.check else "generated"
        print(f"{verb} {destination.relative_to(ROOT)} ({len(contract['tables'])} tables)")
    if stale:
        print("Stale extension contract(s): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
