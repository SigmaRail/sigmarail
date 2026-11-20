#!/usr/bin/env python3
"""Compose Champion SEPA + setup recipes and print / optionally write VeraLabV1 JSON.

Usage:
  python -m sigmarail.features.strategy.compose_champion_cli
  python -m sigmarail.features.strategy.compose_champion_cli --preset minervini_sepa_eps_beat -o /tmp/sepa.json

Maintained companion to ``tests/vera/test_setup_recipes_compose.py``.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--preset",
        default="minervini_sepa",
        help="Bare preset id (setup applied from recipes)",
    )
    p.add_argument(
        "--setup-recipe",
        default="champion_setup_or",
        help="setup_recipes id (default champion_setup_or)",
    )
    p.add_argument("-o", "--output", help="Write VeraLabV1 JSON to path")
    p.add_argument(
        "--list-recipes",
        action="store_true",
        help="Print setup recipe catalog and exit",
    )
    args = p.parse_args(argv)

    from sigmarail.features.strategy.setup_recipes import (
        compose_minervini_sepa_with_setup,
        list_setup_recipes,
    )
    from sigmarail.features.strategy import compile_pipeline

    if args.list_recipes:
        print(json.dumps(list_setup_recipes(), indent=2))
        return 0

    doc = compose_minervini_sepa_with_setup(
        preset_id=args.preset,
        setup_recipe_id=args.setup_recipe,
    )
    spec = compile_pipeline(doc)
    text = json.dumps(spec, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
