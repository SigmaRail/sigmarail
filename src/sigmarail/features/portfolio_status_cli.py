"""CLI for unified portfolio status."""

from __future__ import annotations

import argparse
import json
import sys

from vera.database import get_client
from sigmarail.features.portfolio_status import get_portfolio_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Household portfolio status from ClickHouse broker mirror")
    parser.add_argument("--mode", default="prod", help="SIGMARAIL_MODE (default: prod)")
    parser.add_argument(
        "--scope",
        default="household_yaml",
        choices=["household_yaml", "all_production", "account_id", "book"],
    )
    parser.add_argument("--account-id", default=None)
    parser.add_argument("--book", default=None)
    parser.add_argument("--include-cash-equivalents", action="store_true")
    parser.add_argument("--no-performance", action="store_true")
    parser.add_argument("--include-drift", action="store_true")
    args = parser.parse_args(argv)

    client = get_client()
    try:
        payload = get_portfolio_status(
            client,
            scope=args.scope,
            account_id=args.account_id,
            book=args.book,
            include_cash_equivalents=args.include_cash_equivalents,
            include_performance=not args.no_performance,
            include_drift=args.include_drift,
        )
    finally:
        client.close()

    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
