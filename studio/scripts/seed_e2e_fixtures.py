"""Seed deterministic E2E fixtures: strategy spec + optimizer session + run rows.

Usage: python scripts/seed_e2e_fixtures.py --test-id e2e-123
Creates: {tid}-strat (base spec), {tid}-strat-opt-01 (variant spec),
         session-{tid} (optimizer session), run-optimal-{tid} (completed run).
The variant ir_id matches the optimizer's `{base}-opt-%` scan pattern so the
session heatmap picks up the seeded point.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-id", required=True)
    args = parser.parse_args()
    tid = args.test_id

    from screens.ch import get_ch_client

    client = get_ch_client()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        end_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        # Base spec + one sweep variant spec (optimizer pattern `{base}-opt-%`)
        for ir_id, title in ((f"{tid}-strat", f"E2E base {tid}"), (f"{tid}-strat-opt-01", f"E2E variant {tid}")):
            client.insert(
                "strategy_algorithm_specs",
                [[ir_id, 1, title, '{"schema_version": 1}', f"seed {tid}", "", "", ""]],
                column_names=["ir_id", "spec_schema_version", "title", "algorithm_json", "notes", "portfolio_json", "pipeline_json", "compiler_version"],
            )

        client.command(
            """INSERT INTO strategy_optimizer_sessions
            (session_id, strategy_id, base_ir_id, title, objective, param_x_name,
             param_x_values, param_y_name, param_y_values, total_combinations,
             status, strategy_type, oos_days, constraints_json, max_concurrent,
             created_at, updated_at)
            VALUES (%(sid)s, 'VeraTradingLab', %(base)s, %(title)s, 'sharpe_ratio',
             'risk_per_trade_pct', [0.005, 0.01], NULL, [], 2, 'running',
             'euler', 0, '[]', 1, %(now)s, %(now)s)""",
            parameters={"sid": f"session-{tid}", "base": f"{tid}-strat", "title": f"E2E {tid}", "now": now},
        )

        client.insert(
            "strategy_runs",
            [[
                f"run-optimal-{tid}",          # run_id
                "VeraTradingLab",              # strategy_id
                "",                            # strategy_repo_url
                now,                           # run_timestamp
                "0" * 40,                      # git_commit (FixedString(40))
                "e2e",                         # git_branch
                "base",                        # run_type Enum8
                "e2e-fixture",                 # trigger
                (end := (now - timedelta(days=366)).date()),   # period_start
                (now - timedelta(days=1)).date(),              # period_end
                "",                            # image
                json.dumps({"risk_per_trade_pct": 0.01}),
                f"{tid}-strat-opt-01",         # ir_id (Nullable)
                0.05, 0.05, 1.5, 1.6, 0.08, 0.55, 1.8, 12,   # metrics
                0.0,                           # total_fees
                100000.0, 105000.0,            # start/end equity
                now,                           # created_at
            ]],
            column_names=[
                "run_id", "strategy_id", "strategy_repo_url", "run_timestamp",
                "git_commit", "git_branch", "run_type", "trigger",
                "period_start", "period_end", "image", "parameters", "ir_id",
                "total_return", "annual_return", "sharpe_ratio", "sortino_ratio",
                "max_drawdown", "win_rate", "profit_factor", "total_orders",
                "total_fees", "start_equity", "end_equity", "created_at",
            ],
        )
        print(f"seeded {tid}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
