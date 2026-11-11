"""Preview or apply the packaged SigmaRail core schema."""

import argparse

from sigmarail.config import create_shared_parser, process_shared_args
from sigmarail.database import load_schema


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or apply SigmaRail core tables and transform views.",
        parents=[create_shared_parser()],
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the schema plan. Without this flag, sigmarail-schema is read-only.",
    )
    parser.add_argument(
        "--drop-extra-columns",
        action="store_true",
        help="Plan deletion of undeclared core columns; requires --apply to execute.",
    )
    args = parser.parse_args()
    process_shared_args(args)
    return 0 if load_schema(drop_extra_columns=args.drop_extra_columns, apply=args.apply) else 1


if __name__ == "__main__":
    raise SystemExit(main())
