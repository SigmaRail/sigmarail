from __future__ import annotations

import argparse
from pathlib import Path

from .generator import generate_lineage_artifacts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vera-lineage", description="Generate deterministic lineage JSON artifacts.")
    p.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Path to VeraBase repo root (default: cwd)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Fail if regeneration would change any artifacts.",
    )
    args = p.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    out_dir = repo_root / "sql/lineage"

    before: dict[Path, str] = {}
    if args.check and out_dir.exists():
        for f in sorted(out_dir.glob("*.json")):
            before[f] = f.read_text(encoding="utf-8")

    written = generate_lineage_artifacts(repo_root, out_dir=out_dir)

    if not args.check:
        for w in written:
            print(w.as_posix())
        return 0

    changed: list[str] = []
    for f in sorted(out_dir.glob("*.json")):
        after = f.read_text(encoding="utf-8")
        if before.get(f) != after:
            changed.append(f.as_posix())

    if changed:
        print("Lineage artifacts out of date:")
        for c in changed:
            print(f" - {c}")
        print("Run: vera-lineage --repo-root <repo> (and commit updated artifacts).")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
