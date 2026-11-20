"""``vera-registry`` CLI: compile / check / validate / graph-export / graph-load.

Mirrors ``vera-lineage``: resolves the repo via ``--repo-root`` (default cwd),
never relies on ``package_data``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .compile import compile_registry, compiled_path, write_compiled
from .coverage import coverage_gaps, validate_staged_sources
from .graph_export import (
    build_graph,
    check_graph_drift,
    load_graph_into_clickhouse,
    write_graph,
)
from .validate import check_drift, validate_registry


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vera-registry",
        description="Compile and validate co-located *.entities.yaml sidecars.",
    )
    p.add_argument(
        "command",
        choices=["compile", "check", "validate", "validate-staged", "graph-export", "graph-load", "scaffold"],
    )
    p.add_argument(
        "--all-targets",
        action="store_true",
        help="With scaffold: draft entities for every transform target's schema sidecar",
    )
    p.add_argument(
        "--source",
        default=None,
        help="With scaffold: repo-relative sql/schema/*.sql file to scaffold",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="With scaffold: print what would change without writing",
    )
    p.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Path to VeraBase repo root (default: cwd)",
    )
    p.add_argument(
        "--coverage",
        action="store_true",
        help="With validate: report schema/transform sources missing a sidecar",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="With validate --coverage: treat coverage gaps as errors",
    )
    p.add_argument(
        "--paths",
        nargs="+",
        default=None,
        metavar="PATH",
        help="Repo-relative paths for validate-staged (default: none)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="With graph-export: fail if regeneration would change registry/graph.json",
    )
    args = p.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    staged_paths = list(args.paths or [])

    if args.command == "scaffold":
        from .scaffold import scaffold_all_targets, scaffold_source

        if args.all_targets:
            report = scaffold_all_targets(repo_root)
            errors = 0
            for table, res in sorted(report.items()):
                if "error" in res:
                    errors += 1
                    print(f" - {table}: {res['error']}")
                else:
                    print(f" - {table}: {res['schema']} +{res['added']} ={res['skipped']}")
            return 2 if errors else 0
        if args.source:
            if args.dry_run:
                from .ddl import parse_create_tables

                tables = parse_create_tables((repo_root / args.source).read_text(encoding="utf-8"))
                for table, cols in tables.items():
                    for col, meta in cols.items():
                        print(f" + vera.mart.{table}.{col}: {(meta.get('comment') or 'TODO')[:80]}")
                return 0
            res = scaffold_source(repo_root, args.source)
            print(f"added={len(res['added'])} skipped={len(res['skipped'])}")
            return 0
        print("scaffold requires --all-targets or --source <path>")
        return 2

    compiled, compile_errors = compile_registry(repo_root)

    if args.command == "compile":
        if compile_errors:
            print("Compile errors:")
            for e in compile_errors:
                print(f" - {e}")
            return 2
        out = write_compiled(compiled, repo_root)
        print(out.relative_to(repo_root).as_posix())
        print(f"{len(compiled['by_id'])} entities, {len(compiled['by_anchor'])} anchors")
        return 0

    if args.command == "check":
        errors = list(compile_errors) + check_drift(repo_root)
        if errors:
            print("Registry check failed:")
            for e in errors:
                print(f" - {e}")
            print("Run: vera-registry compile --repo-root <repo> (and commit registry/compiled.json)")
            return 2
        print(f"OK registry check ({len(compiled['by_id'])} entities)")
        return 0

    if args.command == "validate-staged":
        errors = validate_staged_sources(repo_root, staged_paths)
        if errors:
            print("Registry validate-staged failed:")
            for e in errors:
                print(f" - {e}")
            return 2
        print("OK registry validate-staged")
        return 0

    if args.command == "graph-export":
        if args.check:
            errors = check_graph_drift(repo_root)
            if errors:
                print("Graph export check failed:")
                for e in errors:
                    print(f" - {e}")
                return 2
            print("OK graph-export --check")
            return 0
        graph = build_graph(repo_root=repo_root)
        out = write_graph(graph, repo_root)
        print(out.relative_to(repo_root).as_posix())
        print(f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
        return 0

    if args.command == "graph-load":
        from sigmarail.features.ch_settings import connect_clickhouse, resolve_clickhouse_settings_unified

        client = connect_clickhouse(resolve_clickhouse_settings_unified())
        try:
            counts = load_graph_into_clickhouse(client, repo_root=repo_root)
        finally:
            client.close()
        print(f"loaded nodes={counts['nodes']} edges={counts['edges']}")
        return 0

    # validate
    errors = list(compile_errors) + validate_registry(repo_root)
    if not compiled_path(repo_root).is_file():
        errors.append("registry/compiled.json missing (run: vera-registry compile)")
    gaps = coverage_gaps(repo_root)
    if args.coverage:
        if gaps:
            print(f"Coverage gaps ({len(gaps)} sources without sidecar):")
            for g in gaps:
                print(f" - {g}")
        else:
            print("Coverage: all column-defining schema/transform sources have sidecars")
        if args.strict:
            for g in gaps:
                errors.append(f"coverage: {g} has no sibling *.entities.yaml")
    if errors:
        print("Registry validate failed:")
        for e in errors:
            print(f" - {e}")
        return 2
    msg = f"OK registry validate ({len(compiled['by_id'])} entities, locality clean)"
    if args.coverage and gaps and not args.strict:
        msg += f"; {len(gaps)} coverage gap(s) reported (use --strict to fail)"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
