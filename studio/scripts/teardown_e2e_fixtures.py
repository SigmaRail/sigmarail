"""Teardown E2E fixtures for a --test-id (idempotent)."""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-id", required=True)
    args = parser.parse_args()
    tid = args.test_id

    from screens.ch import get_ch_client

    client = get_ch_client()
    try:
        client.command(
            "ALTER TABLE strategy_runs DELETE WHERE run_id LIKE %(pat)s",
            parameters={"pat": f"%{tid}%"},
        )
        client.command(
            "ALTER TABLE strategy_optimizer_sessions DELETE WHERE session_id LIKE %(pat)s",
            parameters={"pat": f"%{tid}%"},
        )
        client.command(
            "ALTER TABLE strategy_algorithm_specs DELETE WHERE ir_id LIKE %(pat)s",
            parameters={"pat": f"%{tid}%"},
        )
        client.command(
            "ALTER TABLE live_deployments DELETE WHERE ir_id LIKE %(pat)s",
            parameters={"pat": f"%{tid}%"},
        )
        print(f"tore down {tid}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
