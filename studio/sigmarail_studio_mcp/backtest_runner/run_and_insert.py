"""Entry point run as a detached subprocess for immediate=True jobs.

Calls run_job(..., detach=False) so the full blocking flow (lean backtest +
insert_strategy_run.py + job state update) runs to completion even after the
MCP session that launched it has ended.

Usage (internal — invoked by runner.run_job when detach=True):
    python -m sigmarail_studio_mcp.backtest_runner.run_and_insert \\
        --job-id UUID --ir-id SPEC_ID \\
        --start-date YYYY-MM-DD --end-date YYYY-MM-DD \\
        [--extra-env '{"KEY":"VAL"}']
        [--lean-project VeraTradingLab]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logger = logging.getLogger("vera.backtest.run_and_insert")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--ir-id", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--extra-env", default="{}")
    p.add_argument("--lean-project", default="")
    args = p.parse_args()

    extra_env: dict[str, str] = {}
    try:
        extra_env = json.loads(args.extra_env) or {}
    except Exception:
        pass

    lean_project = args.lean_project.strip() or extra_env.get("lean_project") or None

    from sigmarail_studio_mcp.backtest_runner.runner import run_job

    result = run_job(
        job_id=args.job_id,
        ir_id=args.ir_id,
        start_date=args.start_date,
        end_date=args.end_date,
        extra_env=extra_env or None,
        detach=False,
        lean_project=lean_project,
    )
    logger.info("completed: %s", result)
    sys.exit(0 if result["status"] == "done" else 1)


if __name__ == "__main__":
    main()
