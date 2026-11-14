#!/usr/bin/env python3
"""Check or refresh the generated SigmaRail Trading Lab Spec runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
RUNTIME_FILES = ("expr.py", "evaluate.py", "entry_trigger_ast.py", "universe_query.py")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def expected_files(destination: Path) -> dict[str, bytes]:
    src = ROOT / "src/sigmarail_spec"
    content = {name: (src / name).read_bytes() for name in RUNTIME_FILES}
    for path in sorted((src / "strategy").glob("*.py")):
        content[f"strategy/{path.name}"] = path.read_bytes()
    content["data/fields.json"] = (src / "data/fields.json").read_bytes()
    content["__init__.py"] = (
        '"""LEAN-local vendor copy of the canonical SigmaRail contract/runtime."""\n\n'
        "from .expr import *  # noqa: F403\n"
        "from .evaluate import (\n"
        "    evaluate_entry_triggers, evaluate_single_trigger, evaluate_slot_bool,\n"
        "    evaluate_slot_number, evaluate_where_ast,\n"
        ")\n"
        "from .entry_trigger_ast import ENUM_TRIGGER_TYPES, compile_entry_trigger, trigger_eval_row\n"
        "from .strategy import *  # noqa: F403\n"
        "from .universe_query import UniverseQueryV1, universe_v1_allowed_columns\n"
    ).encode()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(content.items())}
    content[".vendored.json"] = _json_bytes(
        {
            "source": "packages/sigmarail-spec/src/sigmarail_spec",
            "generated_by": "packages/sigmarail-spec/tools/sync_lean_vendor.py",
            "files": hashes,
            "note": "generated artifact; edit packages/sigmarail-spec runtime, then sync this copy",
        }
    )
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=REPO_ROOT / "trading_lab/sigmarail_spec",
        help="SigmaRail Trading Lab vendor package directory",
    )
    parser.add_argument("--write", action="store_true", help="write expected vendor files")
    args = parser.parse_args()
    destination = args.destination.resolve()
    expected = expected_files(destination)
    mismatches = [name for name, body in expected.items() if not (destination / name).is_file() or (destination / name).read_bytes() != body]
    if args.write:
        destination.mkdir(parents=True, exist_ok=True)
        for name, body in expected.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        print(f"Synchronized {len(expected)} runtime vendor files to {destination}")
        return 0
    if mismatches:
        print("SigmaRail Trading Lab Spec vendor is stale or missing: " + ", ".join(mismatches))
        print(f"Run: python {Path(__file__).relative_to(ROOT)} --destination {destination} --write")
        return 1
    print(f"SigmaRail Trading Lab Spec vendor is current ({len(expected)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
