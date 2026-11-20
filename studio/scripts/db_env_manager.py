#!/usr/bin/env python3
"""Database environment management and synthetic run cleanup utility.

Maintains strict separation between the production ClickHouse database ('vera')
and the test/simulation environment ('vera_test').
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from screens.ch import get_ch_client


def get_status(client: Any) -> None:
    """Print run and artifact statistics across databases."""
    prod_runs = client.query("SELECT count() FROM vera.strategy_runs FINAL").result_rows[0][0]
    prod_artifacts = client.query("SELECT count() FROM vera.strategy_run_artifacts FINAL").result_rows[0][0]
    prod_synthetic = client.query(
        "SELECT count() FROM vera.strategy_runs FINAL WHERE run_id LIKE 'run-opt-%' OR trigger = 'studio_optimizer'"
    ).result_rows[0][0]

    print("=== Database Status ===")
    print(f"Production database (vera):")
    print(f"  • Total strategy_runs: {prod_runs}")
    print(f"  • Total strategy_run_artifacts: {prod_artifacts}")
    print(f"  • Synthetic / Mock test runs: {prod_synthetic}")

    try:
        test_runs = client.query("SELECT count() FROM vera_test.strategy_runs FINAL").result_rows[0][0]
        print(f"\nTest database (vera_test):")
        print(f"  • Total strategy_runs: {test_runs}")
    except Exception:
        print("\nTest database (vera_test): Ready (empty / isolated)")


def clean_synthetic_runs(client: Any, dry_run: bool = False) -> None:
    """Purge synthetic/mock test runs from the production database."""
    synthetic_runs = client.query(
        "SELECT run_id, ir_id, trigger, run_timestamp FROM vera.strategy_runs FINAL "
        "WHERE run_id LIKE 'run-opt-%' OR trigger = 'studio_optimizer' OR run_type = 'synthetic'"
    ).result_rows

    synthetic_artifacts = client.query(
        "SELECT count() FROM vera.strategy_run_artifacts FINAL WHERE run_id LIKE 'run-opt-%'"
    ).result_rows[0][0]

    print(f"Found {len(synthetic_runs)} synthetic runs and {synthetic_artifacts} synthetic artifacts in 'vera'.")

    if not synthetic_runs and synthetic_artifacts == 0:
        print("✓ Production database is already clean. No synthetic runs found.")
        return

    if dry_run:
        print("Dry run enabled — no deletions performed.")
        for r in synthetic_runs:
            print(f"  [DryRun] Would delete run {r[0]} ({r[1]})")
        return

    print("Purging synthetic artifacts from vera.strategy_run_artifacts...")
    client.command("ALTER TABLE vera.strategy_run_artifacts DELETE WHERE run_id LIKE 'run-opt-%'")

    print("Purging synthetic runs from vera.strategy_runs...")
    client.command(
        "ALTER TABLE vera.strategy_runs DELETE WHERE run_id LIKE 'run-opt-%' OR trigger = 'studio_optimizer' OR run_type = 'synthetic'"
    )

    print("Waiting for ClickHouse mutations to complete...")
    for _ in range(10):
        muts = client.query(
            "SELECT table, mutation_id FROM system.mutations WHERE is_done = 0 AND database = 'vera'"
        ).result_rows
        if not muts:
            break
        time.sleep(1)

    client.command("OPTIMIZE TABLE vera.strategy_runs FINAL")
    client.command("OPTIMIZE TABLE vera.strategy_run_artifacts FINAL")

    remaining = client.query(
        "SELECT count() FROM vera.strategy_runs FINAL WHERE run_id LIKE 'run-opt-%' OR trigger = 'studio_optimizer'"
    ).result_rows[0][0]

    print(f"✓ Cleanup complete! Remaining synthetic runs in production: {remaining}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ClickHouse test vs prod environment data.")
    parser.add_argument("--status", action="store_true", help="Display environment and database status.")
    parser.add_argument("--clean-synthetic", action="store_true", help="Purge synthetic runs from production database.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without deleting data.")

    args = parser.parse_args()

    client = get_ch_client()

    if args.clean_synthetic:
        clean_synthetic_runs(client, dry_run=args.dry_run)
    else:
        get_status(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
