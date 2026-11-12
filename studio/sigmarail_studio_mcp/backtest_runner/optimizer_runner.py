"""LEAN native optimizer runner and config builder (QuantConnect.Optimizer).

Builds optimizer.json / OptimizationNodePacket configurations for:
- QuantConnect.Optimizer.Strategies.EulerSearchOptimizationStrategy
- QuantConnect.Optimizer.Strategies.GridSearchOptimizationStrategy
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("vera.backtest.optimizer_runner")


def build_optimizer_config(
    *,
    optimization_id: str,
    strategy_type: str = "euler",
    target_metric: str = "Statistics.Sharpe Ratio",
    extremum: str = "max",
    target_value: float | None = None,
    parameters: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
    euler_segments: int = 4,
    max_concurrent: int = 4,
    out_of_sample_days: int = 0,
    algorithm_type_name: str = "VeraTradingLab",
    algorithm_language: str = "Python",
) -> dict[str, Any]:
    """Construct a QuantConnect.Optimizer.OptimizationNodePacket JSON dictionary."""
    strategy_class = (
        "QuantConnect.Optimizer.Strategies.EulerSearchOptimizationStrategy"
        if strategy_type.lower() == "euler"
        else "QuantConnect.Optimizer.Strategies.GridSearchOptimizationStrategy"
    )

    lean_params: list[dict[str, Any]] = []
    for p in parameters:
        param_dict: dict[str, Any] = {
            "name": p["name"],
            "min": float(p["min"]),
            "max": float(p["max"]),
        }
        if "step" in p and p["step"] is not None:
            param_dict["step"] = float(p["step"])
        if "min_step" in p and p["min_step"] is not None:
            param_dict["min-step"] = float(p["min_step"])
        elif "step" in p and p["step"] is not None:
            param_dict["min-step"] = float(p["step"]) / euler_segments if strategy_type.lower() == "euler" else float(p["step"])
        lean_params.append(param_dict)

    lean_constraints: list[dict[str, Any]] = []
    for c in constraints or []:
        lean_constraints.append({
            "target": c.get("target", "Drawdown"),
            "operator": c.get("operator", "lessOrEqual"),
            "target-value": float(c.get("target_value", c.get("target-value", 0.25))),
        })

    criterion: dict[str, Any] = {
        "target": target_metric,
        "extremum": extremum,
    }
    if target_value is not None:
        criterion["target-value"] = float(target_value)

    config: dict[str, Any] = {
        "algorithm-type-name": algorithm_type_name,
        "algorithm-language": algorithm_language,
        "optimizer-close-automatically": True,
        "optimization-strategy": strategy_class,
        "optimization-strategy-settings": {
            "$type": "QuantConnect.Optimizer.Strategies.StepBaseOptimizationStrategySettings, QuantConnect.Optimizer",
            "default-segment-amount": max(2, int(euler_segments)),
        },
        "optimization-criterion": criterion,
        "constraints": lean_constraints,
        "parameters": lean_params,
        "maximum-concurrent-backtests": max(1, int(max_concurrent)),
    }

    if out_of_sample_days > 0:
        config["out-of-sample-days"] = int(out_of_sample_days)

    return config


def write_optimizer_config_file(config: dict[str, Any], output_dir: Path) -> Path:
    """Write optimizer.json to target output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = output_dir / "optimizer.json"
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return cfg_path
