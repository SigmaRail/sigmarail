"""CLI: author, compile, and inspect staged strategy pipelines.

Subcommands:
    factors                      List semantic factors and L7 column mappings.
    presets                      List named strategy presets.
    compile   --preset | --file  Compile a PipelineDocument to VeraLabV1 JSON.
    decompile --file             Decompile a VeraLabV1 spec to a PipelineDocument.
    validate  --preset | --file  Validate a PipelineDocument (exit 1 on error).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"file not found: {path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vera strategy pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("factors", help="List semantic factors")

    sub.add_parser("presets", help="List named presets")

    comp = sub.add_parser("compile", help="Compile a PipelineDocument to VeraLabV1")
    comp.add_argument("--preset", default=None, help="Named preset id")
    comp.add_argument("--file", default=None, help="Path to a PipelineDocument JSON file")
    comp.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")

    dec = sub.add_parser("decompile", help="Decompile a VeraLabV1 spec to a PipelineDocument")
    dec.add_argument("--file", required=True, help="Path to a VeraLabV1 JSON file")
    dec.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")

    val = sub.add_parser("validate", help="Validate a PipelineDocument")
    val.add_argument("--preset", default=None, help="Named preset id")
    val.add_argument("--file", default=None, help="Path to a PipelineDocument JSON file")

    imp = sub.add_parser("import", help="Decompile legacy specs and persist PortfolioDocument source")
    imp.add_argument("--dry-run", action="store_true", help="Decompile but do not persist")

    args = parser.parse_args(argv)

    from sigmarail.features.strategy import (
        PipelineDocument,
        compile_pipeline,
        decompile_pipeline,
        list_factors,
    )
    from sigmarail.features.strategy.presets import get_preset, list_presets

    if args.command == "factors":
        print(json.dumps(list_factors(), indent=2))
        return 0

    if args.command == "presets":
        print(json.dumps(list_presets(), indent=2))
        return 0

    def _load_document() -> PipelineDocument:
        if args.preset:
            return get_preset(args.preset)
        if args.file:
            return PipelineDocument.model_validate(_load_json(args.file))
        raise SystemExit("provide --preset or --file")

    if args.command == "compile":
        doc = _load_document()
        spec = compile_pipeline(doc)
        print(json.dumps(spec, indent=2 if args.pretty else None))
        return 0

    if args.command == "decompile":
        spec = _load_json(args.file)
        doc = decompile_pipeline(spec)
        print(json.dumps(doc.model_dump(), indent=2 if args.pretty else None))
        return 0

    if args.command == "validate":
        doc = _load_document()
        try:
            compile_pipeline(doc)
        except Exception as exc:  # noqa: BLE001
            print(f"INVALID: {exc}", file=sys.stderr)
            return 1
        print("VALID")
        return 0

    if args.command == "import":
        from sigmarail.features.ch_settings import connect_clickhouse, resolve_clickhouse_settings_unified
        from sigmarail.features.strategy.migration import import_from_db

        client = connect_clickhouse(resolve_clickhouse_settings_unified())
        try:
            out = import_from_db(client, persist=not args.dry_run)
        finally:
            client.close()
        print(f"imported {out['ok']}/{out['total']} (failed {out['failed']})")
        for r in out["results"]:
            if not r["ok"]:
                print(f"  XX {r['ir_id']}: {r['error']}")
        return 0 if out["failed"] == 0 else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
