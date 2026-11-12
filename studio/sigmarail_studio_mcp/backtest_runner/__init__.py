"""Backtest runner and strategy composition for sigmarail-studio MCP.

Migrated from vera-mcp-backtest to make sigmarail-studio self-contained.
"""

from sigmarail_studio_mcp.backtest_runner.runner import (
    cancel_job,
    investigate_job,
    preflight,
    python_for_lean,
    run_job,
    save_spec,
    submit_job,
    tail_log,
    worker_heartbeat_recent,
)
from sigmarail_studio_mcp.backtest_runner.strategy import (
    compile_pipeline,
    compile_preset,
    create_spec_from_strategy_template,
    decompile_spec,
    get_template,
    list_factors,
    list_presets,
    list_templates,
    submit_backtest_from_template,
)

__all__ = [
    # runner
    "cancel_job",
    "investigate_job",
    "preflight",
    "python_for_lean",
    "run_job",
    "save_spec",
    "submit_job",
    "tail_log",
    "worker_heartbeat_recent",
    # strategy
    "compile_pipeline",
    "compile_preset",
    "create_spec_from_strategy_template",
    "decompile_spec",
    "get_template",
    "list_factors",
    "list_presets",
    "list_templates",
    "submit_backtest_from_template",
]
