"""Stamp research Evaluation (dates, cash, benchmark) onto a VeraLabV1 spec."""

from __future__ import annotations

import copy
from typing import Any


def stamp_evaluation(
    spec: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    initial_cash: float | int,
    benchmark: str,
) -> dict[str, Any]:
    """Write VeraBase.Evaluation and string AlgorithmParameters for LEAN GetParameter.

    Live trading (future) reads cash + benchmark from the same block; dates are the
    research window used by backtest/optimizer jobs.
    """
    out = copy.deepcopy(spec)
    cash = int(initial_cash)
    bench = str(benchmark or "SPY").strip().upper() or "SPY"
    start = str(start_date or "").strip()
    end = str(end_date or "").strip()

    vera_base = out.setdefault("VeraBase", {})
    if not isinstance(vera_base, dict):
        raise ValueError("VeraBase must be an object")
    vera_base["Evaluation"] = {
        "start_date": start,
        "end_date": end,
        "initial_cash": cash,
        "benchmark": bench,
    }

    algo = out.setdefault("AlgorithmParameters", {})
    if not isinstance(algo, dict):
        raise ValueError("AlgorithmParameters must be an object")
    algo["initial-cash"] = str(cash)
    algo["benchmark"] = bench
    if start:
        algo["start-date"] = start
    if end:
        algo["end-date"] = end
    return out


def evaluation_extra_env(spec: dict[str, Any] | None) -> dict[str, str]:
    """LEAN CLI --parameter values for a stamped spec (job extra_env)."""
    if not isinstance(spec, dict):
        return {}
    algo = spec.get("AlgorithmParameters")
    if not isinstance(algo, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("initial-cash", "benchmark"):
        raw = algo.get(key)
        if raw is not None and str(raw).strip():
            out[key] = str(raw).strip()
    return out
