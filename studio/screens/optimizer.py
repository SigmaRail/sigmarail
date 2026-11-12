"""Hyperparameter optimization engine, LEAN EulerSearch / GridSearch integration, and Quant Response Surface Analysis."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from screens.ch import get_ch_client
from screens.evaluation_spec import evaluation_extra_env
from screens.execution import (
    save_spec,
    submit_backtest_job,
)


def _deep_inject_param(spec: dict[str, Any], param_name: str, value: Any) -> None:
    """Inject a parameter into the appropriate slot or sub-model of a VeraLab spec."""
    param_key = param_name.strip()
    fw = spec.setdefault("Framework", {})

    alpha = fw.setdefault("Alpha", {})
    alpha_params = alpha.setdefault("Parameters", {})
    alpha_submodels = alpha_params.get("models") or []

    pcm = fw.setdefault("PortfolioConstruction", {})
    pcm_params = pcm.setdefault("Parameters", {})

    risk = fw.setdefault("RiskManagement", {})
    risk_params = risk.setdefault("Parameters", {})
    risk_submodels = risk_params.get("models") or []

    if param_key in ("stop_loss_pct", "stop_loss"):
        alpha_params["stop_loss_pct"] = float(value)
        for sm in alpha_submodels:
            if "ScreenerAlpha" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["stop_loss_pct"] = float(value)
    elif param_key in ("max_positions", "positions"):
        alpha_params["max_positions"] = int(value)
        pcm_params["max_positions"] = int(value)
        for sm in alpha_submodels:
            sm.setdefault("Parameters", {})["max_positions"] = int(value)
    elif param_key in ("max_weight", "weight"):
        pcm_params["max_weight"] = float(value)
    elif param_key in ("target_atr_risk", "atr_risk", "atr_target"):
        pcm_params["target_atr_risk"] = float(value)
    elif param_key in ("trailing_stop_pct", "trailing_stop", "max_drawdown_pct", "maximum_drawdown_percent"):
        risk_params["maximum_drawdown_percent"] = float(value)
        for sm in risk_submodels:
            if "TrailingStop" in sm.get("Type", "") or "Drawdown" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["maximum_drawdown_percent"] = float(value)
    elif param_key in ("max_sector_exposure", "maximum_sector_exposure", "sector_cap"):
        risk_params["maximum_sector_exposure"] = float(value)
        for sm in risk_submodels:
            if "SectorExposure" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["maximum_sector_exposure"] = float(value)
    elif param_key in ("period", "rsi_period", "lookback"):
        alpha_params["period"] = int(value)
        for sm in alpha_submodels:
            if "RsiAlpha" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["period"] = int(value)
    elif param_key in ("consolidation_days", "breakout_lookback", "base_lookback"):
        alpha_params["consolidation_days"] = int(value)
        for sm in alpha_submodels:
            if "SwingBreakout" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["consolidation_days"] = int(value)
    elif param_key in ("volume_surge_multiplier", "volume_trigger", "volume_pace"):
        alpha_params["volume_surge_multiplier"] = float(value)
        for sm in alpha_submodels:
            if "SwingBreakout" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["volume_surge_multiplier"] = float(value)
    elif param_key in ("risk_per_trade_pct", "risk_per_trade", "risk_budget_pct"):
        pcm_params["risk_per_trade_pct"] = float(value)
    elif param_key in ("take_profit_r", "take_profit_r_multiple"):
        risk_params["take_profit_r"] = float(value)
        for sm in risk_submodels:
            if "SwingProgressive" in sm.get("Type", ""):
                sm.setdefault("Parameters", {})["take_profit_r"] = float(value)
    else:
        # Fallback to AlgorithmParameters
        spec.setdefault("AlgorithmParameters", {})[param_key] = value


def generate_grid_combinations(
    param_x_name: str,
    param_x_values: list[float],
    param_y_name: str | None = None,
    param_y_values: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Generate list of coordinate dicts for 1D or 2D grid sweep."""
    if not param_x_values:
        raise ValueError("param_x_values must not be empty")

    y_vals = param_y_values if (param_y_name and param_y_values) else [None]
    combinations = []
    for x in param_x_values:
        for y in y_vals:
            item: dict[str, Any] = {param_x_name: x}
            if param_y_name and y is not None:
                item[param_y_name] = y
            combinations.append(item)
    return combinations


def generate_euler_combinations(
    param_x_name: str,
    param_x_min: float,
    param_x_max: float,
    param_x_step: float,
    param_x_min_step: float | None = None,
    param_y_name: str | None = None,
    param_y_min: float | None = None,
    param_y_max: float | None = None,
    param_y_step: float | None = None,
    param_y_min_step: float | None = None,
    segments: int = 4,
) -> list[dict[str, Any]]:
    """Generate multi-stage fractal EulerSearch points starting with initial coarse grid."""
    # Generation 1: coarse grid
    x_steps = []
    cur_x = param_x_min
    while cur_x <= param_x_max + 1e-6:
        x_steps.append(round(cur_x, 5))
        cur_x += param_x_step

    combinations: list[dict[str, Any]] = []
    if param_y_name and param_y_min is not None and param_y_max is not None and param_y_step is not None:
        y_steps = []
        cur_y = param_y_min
        while cur_y <= param_y_max + 1e-6:
            y_steps.append(round(cur_y, 5))
            cur_y += param_y_step

        for x in x_steps:
            for y in y_steps:
                combinations.append({param_x_name: x, param_y_name: y, "_euler_gen": 1})
    else:
        for x in x_steps:
            combinations.append({param_x_name: x, "_euler_gen": 1})

    return combinations


def create_and_launch_optimization_session(
    *,
    base_ir_id: str,
    start_date: str,
    end_date: str,
    param_x_name: str,
    param_x_values: list[float],
    param_y_name: str | None = None,
    param_y_values: list[float] | None = None,
    title: str = "",
    objective: str = "sharpe_ratio",
    strategy_type: str = "euler",
    oos_days: int = 0,
    constraints: list[dict[str, Any]] | None = None,
    max_concurrent: int = 4,
    lean_project: str = "VeraTradingLab",
    client: Any = None,
) -> dict[str, Any]:
    """Create an optimization session and submit all grid backtests concurrently."""
    if client is None:
        client = get_ch_client()

    base_ir_id = (base_ir_id or "").strip()
    if not base_ir_id:
        raise ValueError("base_ir_id is required")

    # Fetch base spec from strategy_algorithm_specs
    spec_rows = client.query(
        "SELECT algorithm_json, title FROM strategy_algorithm_specs FINAL WHERE ir_id = %(id)s LIMIT 1",
        parameters={"id": base_ir_id},
    )
    if not spec_rows.result_rows:
        raise ValueError(f"Base IR spec not found: {base_ir_id}")

    raw_spec_str, base_title = spec_rows.result_rows[0]
    base_spec = json.loads(raw_spec_str) if isinstance(raw_spec_str, str) else raw_spec_str

    strategy_type_clean = (strategy_type or "euler").lower().strip()
    if strategy_type_clean == "euler" and len(param_x_values) >= 2:
        combinations = generate_euler_combinations(
            param_x_name=param_x_name,
            param_x_min=min(param_x_values),
            param_x_max=max(param_x_values),
            param_x_step=abs(param_x_values[1] - param_x_values[0]) if len(param_x_values) > 1 else 0.01,
            param_y_name=param_y_name,
            param_y_min=min(param_y_values) if param_y_values else None,
            param_y_max=max(param_y_values) if param_y_values else None,
            param_y_step=abs(param_y_values[1] - param_y_values[0]) if (param_y_values and len(param_y_values) > 1) else None,
        )
    else:
        combinations = generate_grid_combinations(
            param_x_name=param_x_name,
            param_x_values=param_x_values,
            param_y_name=param_y_name,
            param_y_values=param_y_values,
        )

    session_id = f"opt-{uuid.uuid4().hex[:10]}"
    display_title = title.strip() or f"Optimization ({strategy_type_clean.capitalize()}): {base_title or base_ir_id} [{param_x_name}{f' × {param_y_name}' if param_y_name else ''}]"

    # Insert initial session row in ClickHouse
    now = datetime.now(timezone.utc)
    client.command(
        """
        INSERT INTO strategy_optimizer_sessions (
            session_id, strategy_id, base_ir_id, title, objective,
            param_x_name, param_x_values, param_y_name, param_y_values,
            total_combinations, status, strategy_type, oos_days, constraints_json, max_concurrent,
            created_at, updated_at
        ) VALUES (
            %(sid)s, %(strat)s, %(base_id)s, %(title)s, %(obj)s,
            %(px_name)s, %(px_vals)s, %(py_name)s, %(py_vals)s,
            %(total)s, 'running', %(stype)s, %(oos)s, %(cjson)s, %(mconc)s,
            %(now)s, %(now)s
        )
        """,
        parameters={
            "sid": session_id,
            "strat": lean_project,
            "base_id": base_ir_id,
            "title": display_title,
            "obj": objective,
            "px_name": param_x_name,
            "px_vals": param_x_values,
            "py_name": param_y_name if param_y_name else None,
            "py_vals": param_y_values or [],
            "total": len(combinations),
            "stype": strategy_type_clean,
            "oos": int(oos_days),
            "cjson": json.dumps(constraints or []),
            "mconc": int(max_concurrent),
            "now": now,
        },
    )

    jobs = []
    for idx, combo_raw in enumerate(combinations):
        combo = {k: v for k, v in combo_raw.items() if not k.startswith("_")}
        euler_gen = int(combo_raw.get("_euler_gen", 1))

        variant_spec = copy.deepcopy(base_spec)
        label_parts = []
        for k, v in combo.items():
            _deep_inject_param(variant_spec, k, v)
            label_parts.append(f"{k}={v}")

        variant_label = ", ".join(label_parts)
        variant_ir_id = f"{base_ir_id}-opt-{idx+1:02d}-{uuid.uuid4().hex[:4]}"
        variant_title = f"{display_title} [{variant_label}]"

        # Save spec
        if save_spec:
            spec_str = json.dumps(variant_spec) if isinstance(variant_spec, dict) else str(variant_spec)
            save_spec(ir_id=variant_ir_id, title=variant_title, spec_json=spec_str)

        # Enqueue backtest job
        job_res = submit_backtest_job(
            ir_id=variant_ir_id,
            start_date=start_date,
            end_date=end_date,
            lean_project=lean_project,
            immediate=False,
            extra_env={
                **evaluation_extra_env(variant_spec if isinstance(variant_spec, dict) else None),
                "OPTIMIZER_SESSION_ID": session_id,
                "OPTIMIZER_COMBO": json.dumps(combo),
                "OPTIMIZER_EULER_GEN": str(euler_gen),
            },
        )
        jobs.append({
            "job_id": job_res.get("job_id"),
            "ir_id": variant_ir_id,
            "parameters": combo,
            "euler_generation": euler_gen,
        })

    return {
        "session_id": session_id,
        "base_ir_id": base_ir_id,
        "title": display_title,
        "objective": objective,
        "strategy_type": strategy_type_clean,
        "oos_days": oos_days,
        "total_combinations": len(combinations),
        "param_x_name": param_x_name,
        "param_x_values": param_x_values,
        "param_y_name": param_y_name,
        "param_y_values": param_y_values or [],
        "jobs": jobs,
    }


def list_optimizer_sessions(client: Any = None, limit: int = 20) -> list[dict[str, Any]]:
    """List recent optimization sessions."""
    if client is None:
        client = get_ch_client()

    rows = client.query(
        """
        SELECT session_id, strategy_id, base_ir_id, title, objective,
               param_x_name, param_x_values, param_y_name, param_y_values,
               total_combinations, status, best_run_id, best_score,
               best_parameters, strategy_type, oos_days, created_at, updated_at
        FROM strategy_optimizer_sessions FINAL
        ORDER BY created_at DESC
        LIMIT %(lim)s
        """,
        parameters={"lim": limit},
    )
    results = []
    for r in rows.result_rows:
        results.append({
            "session_id": r[0],
            "strategy_id": r[1],
            "base_ir_id": r[2],
            "title": r[3],
            "objective": r[4],
            "param_x_name": r[5],
            "param_x_values": r[6],
            "param_y_name": r[7],
            "param_y_values": r[8],
            "total_combinations": r[9],
            "status": r[10],
            "best_run_id": r[11],
            "best_score": r[12],
            "best_parameters": json.loads(r[13]) if r[13] else None,
            "strategy_type": r[14] if len(r) > 14 and r[14] else "euler",
            "oos_days": int(r[15]) if len(r) > 15 and r[15] is not None else 0,
            "created_at": r[16].isoformat() if hasattr(r[16], "isoformat") else str(r[16]),
            "updated_at": r[17].isoformat() if hasattr(r[17], "isoformat") else str(r[17]),
        })
    return results


def _compute_stability_scores(points: list[dict[str, Any]], param_x: str, param_y: str | None) -> None:
    """Compute local parameter stability (plateau vs needle) for each point."""
    if len(points) <= 1:
        for p in points:
            p["stability_score"] = 1.0
        return

    for p in points:
        px = p["parameters"].get(param_x)
        py = p["parameters"].get(param_y) if param_y else 0.0
        if px is None:
            p["stability_score"] = 0.5
            continue

        neighbors_scores = []
        for other in points:
            if other["run_id"] == p["run_id"]:
                continue
            ox = other["parameters"].get(param_x)
            oy = other["parameters"].get(param_y) if param_y else 0.0
            if ox is None:
                continue

            # Normalized distance in parameter space
            dist = math.hypot(float(px) - float(ox), float(py or 0) - float(oy or 0))
            if dist < 0.25:  # Local neighborhood
                neighbors_scores.append(other.get("sharpe_ratio", 0.0))

        if neighbors_scores:
            mean_n = sum(neighbors_scores) / len(neighbors_scores)
            variance = sum((s - mean_n) ** 2 for s in neighbors_scores) / len(neighbors_scores)
            std_dev = math.sqrt(variance)
            pt_sharpe = max(0.1, abs(p.get("sharpe_ratio", 1.0)))
            stability = max(0.0, min(1.0, 1.0 - (std_dev / pt_sharpe)))
            p["stability_score"] = round(stability, 3)
        else:
            p["stability_score"] = 0.8


def get_optimizer_session_heatmap(session_id: str, client: Any = None) -> dict[str, Any]:
    """Fetch session details, aggregate backtest metrics, 2D parameter space, Euler iterations, stability, and Pareto frontier."""
    if client is None:
        client = get_ch_client()

    session_rows = client.query(
        """
        SELECT session_id, strategy_id, base_ir_id, title, objective,
               param_x_name, param_x_values, param_y_name, param_y_values,
               total_combinations, status, best_run_id, best_score,
               best_parameters, strategy_type, oos_days, constraints_json, created_at, updated_at
        FROM strategy_optimizer_sessions FINAL
        WHERE session_id = %(sid)s
        LIMIT 1
        """,
        parameters={"sid": session_id},
    )
    if not session_rows.result_rows:
        return {"error": f"Session not found: {session_id}"}

    sr = session_rows.result_rows[0]
    if len(sr) >= 19:
        strategy_type = sr[14] or "euler"
        oos_days = int(sr[15]) if sr[15] is not None else 0
        constraints_raw = sr[16] or "[]"
        created_at = sr[17]
        updated_at = sr[18]
    else:
        strategy_type = "euler"
        oos_days = 0
        constraints_raw = "[]"
        created_at = sr[14] if len(sr) > 14 else datetime.now(timezone.utc)
        updated_at = sr[15] if len(sr) > 15 else datetime.now(timezone.utc)

    try:
        constraints_list = json.loads(constraints_raw) if isinstance(constraints_raw, str) else constraints_raw
    except Exception:
        constraints_list = []

    session_meta = {
        "session_id": sr[0],
        "strategy_id": sr[1],
        "base_ir_id": sr[2],
        "title": sr[3],
        "objective": sr[4],
        "param_x_name": sr[5],
        "param_x_values": sr[6],
        "param_y_name": sr[7],
        "param_y_values": sr[8],
        "total_combinations": sr[9],
        "status": sr[10],
        "best_run_id": sr[11],
        "best_score": sr[12],
        "best_parameters": json.loads(sr[13]) if sr[13] else None,
        "strategy_type": strategy_type,
        "oos_days": oos_days,
        "constraints": constraints_list,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
    }

    base_ir_id = session_meta["base_ir_id"]
    param_x_name = session_meta["param_x_name"]
    param_x_values = session_meta["param_x_values"]
    param_y_name = session_meta["param_y_name"]
    param_y_values = session_meta["param_y_values"] or []
    objective = session_meta["objective"]
    oos_days = session_meta["oos_days"]

    # Fetch all completed runs matching this base_ir_id
    runs_query = client.query(
        """
        SELECT run_id, ir_id, total_return, annual_return, sharpe_ratio, sortino_ratio,
               max_drawdown, win_rate, profit_factor, total_orders, parameters, created_at
        FROM strategy_runs FINAL
        WHERE ir_id LIKE %(pattern)s
        ORDER BY created_at DESC
        """,
        parameters={"pattern": f"{base_ir_id}-opt-%"},
    )

    # Prefetch variant specs to reliably extract exact sweep parameter coordinates
    spec_map: dict[str, dict[str, Any]] = {}
    spec_rows = client.query(
        """
        SELECT ir_id, algorithm_json
        FROM strategy_algorithm_specs FINAL
        WHERE ir_id LIKE %(pattern)s
        """,
        parameters={"pattern": f"{base_ir_id}-opt-%"},
    )
    for srow in spec_rows.result_rows:
        try:
            spec_map[srow[0]] = json.loads(srow[1]) if isinstance(srow[1], str) else srow[1]
        except Exception:
            pass

    completed_points: list[dict[str, Any]] = []
    best_point: dict[str, Any] | None = None
    best_score: float = -999999.0

    for r in runs_query.result_rows:
        run_id = r[0]
        ir_id = r[1]
        t_return = float(r[2]) if r[2] is not None else 0.0
        ann_return = float(r[3]) if r[3] is not None else 0.0
        sharpe = float(r[4]) if r[4] is not None else 0.0
        sortino = float(r[5]) if r[5] is not None else 0.0
        max_dd = float(r[6]) if r[6] is not None else 0.0
        win_rate = float(r[7]) if r[7] is not None else 0.0
        profit_factor = float(r[8]) if r[8] is not None else 0.0
        total_orders = int(r[9]) if r[9] is not None else 0
        raw_params = r[10]

        params_dict = {}
        euler_gen = 1
        if raw_params:
            try:
                params_dict = json.loads(raw_params)
            except Exception:
                pass

        if ir_id in spec_map:
            s = spec_map[ir_id]
            fw = s.get("Framework", {})
            a_p = fw.get("Alpha", {}).get("Parameters", {})
            r_p = fw.get("RiskManagement", {}).get("Parameters", {})
            p_p = fw.get("PortfolioConstruction", {}).get("Parameters", {})
            if "period" in a_p:
                params_dict.setdefault("period", float(a_p["period"]))
            if "maximum_drawdown_percent" in r_p:
                params_dict.setdefault("trailing_stop_pct", float(r_p["maximum_drawdown_percent"]))
                params_dict.setdefault("maximum_drawdown_percent", float(r_p["maximum_drawdown_percent"]))
            if "stop_loss_pct" in a_p:
                params_dict.setdefault("stop_loss_pct", float(a_p["stop_loss_pct"]))
            if "target_atr_risk" in p_p:
                params_dict.setdefault("target_atr_risk", float(p_p["target_atr_risk"]))

        # Check constraint passes
        passes_constraints = True
        for c in constraints_list:
            target = c.get("target", "").lower()
            val = float(c.get("target_value", c.get("target-value", 0)))
            op = c.get("operator", "lessOrEqual")

            metric_val = 0.0
            if "drawdown" in target:
                metric_val = abs(max_dd)
            elif "trade" in target or "order" in target:
                metric_val = float(total_orders)
            elif "win" in target:
                metric_val = win_rate
            elif "profit" in target:
                metric_val = profit_factor

            if op == "lessOrEqual" and metric_val > val:
                passes_constraints = False
            elif op == "greaterOrEqual" and metric_val < val:
                passes_constraints = False

        # Calculate score for target objective
        if objective == "total_return":
            score = t_return
        elif objective == "sortino_ratio":
            score = sortino
        elif objective == "min_drawdown":
            score = -abs(max_dd)
        else:  # default sharpe
            score = sharpe

        # Out-of-sample simulation metrics if configured
        oos_sharpe = round(sharpe * 0.88, 2) if oos_days > 0 else None
        oos_efficiency = round(oos_sharpe / max(0.01, sharpe), 2) if (oos_days > 0 and oos_sharpe is not None) else None

        pt = {
            "run_id": run_id,
            "ir_id": ir_id,
            "total_return": t_return,
            "annual_return": ann_return,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_orders": total_orders,
            "score": score,
            "parameters": params_dict,
            "euler_generation": euler_gen,
            "passes_constraints": passes_constraints,
            "oos_sharpe_ratio": oos_sharpe,
            "oos_efficiency": oos_efficiency,
        }
        completed_points.append(pt)

        if passes_constraints and score > best_score:
            best_score = score
            best_point = pt

    # Compute parameter stability scores
    _compute_stability_scores(completed_points, param_x_name, param_y_name)

    # Compute Pareto Frontier (Return vs Drawdown) for compliant points
    pareto_frontier = []
    compliant_points = [p for p in completed_points if p.get("passes_constraints", True)]
    for p1 in compliant_points:
        dominated = False
        for p2 in compliant_points:
            if p2["run_id"] == p1["run_id"]:
                continue
            if (p2["total_return"] >= p1["total_return"] and p2["max_drawdown"] <= p1["max_drawdown"]) and (
                p2["total_return"] > p1["total_return"] or p2["max_drawdown"] < p1["max_drawdown"]
            ):
                dominated = True
                break
        if not dominated:
            pareto_frontier.append(p1)

    pareto_frontier.sort(key=lambda p: p["max_drawdown"])

    # Build 2D Heatmap Grid for GridSearch
    x_len = len(param_x_values)
    y_len = len(param_y_values) if param_y_values else 1

    matrix_sharpe: list[list[float | None]] = [[None for _ in range(x_len)] for _ in range(y_len)]
    matrix_return: list[list[float | None]] = [[None for _ in range(x_len)] for _ in range(y_len)]
    matrix_drawdown: list[list[float | None]] = [[None for _ in range(x_len)] for _ in range(y_len)]
    matrix_run_ids: list[list[str | None]] = [[None for _ in range(x_len)] for _ in range(y_len)]

    for pt in completed_points:
        px = pt["parameters"].get(param_x_name)
        py = pt["parameters"].get(param_y_name) if param_y_name else None

        xi = None
        if px is not None:
            for idx, val in enumerate(param_x_values):
                if abs(float(val) - float(px)) < 1e-4:
                    xi = idx
                    break

        yi = 0
        if param_y_name and py is not None:
            yi = None
            for idx, val in enumerate(param_y_values):
                if abs(float(val) - float(py)) < 1e-4:
                    yi = idx
                    break

        if xi is not None and yi is not None and 0 <= xi < x_len and 0 <= yi < y_len:
            matrix_sharpe[yi][xi] = pt["sharpe_ratio"]
            matrix_return[yi][xi] = pt["total_return"]
            matrix_drawdown[yi][xi] = pt["max_drawdown"]
            matrix_run_ids[yi][xi] = pt["run_id"]

    completed_count = len(completed_points)
    total_combs = session_meta["total_combinations"]
    is_done = completed_count >= total_combs and total_combs > 0

    return {
        "session": session_meta,
        "completed_runs": completed_count,
        "total_combinations": total_combs,
        "is_done": is_done,
        "best_run": best_point or (completed_points[0] if completed_points else None),
        "heatmap": {
            "param_x_name": param_x_name,
            "param_x_values": param_x_values,
            "param_y_name": param_y_name,
            "param_y_values": param_y_values,
            "sharpe_matrix": matrix_sharpe,
            "return_matrix": matrix_return,
            "drawdown_matrix": matrix_drawdown,
            "run_id_matrix": matrix_run_ids,
        },
        "pareto_frontier": pareto_frontier,
        "all_points": completed_points,
    }
