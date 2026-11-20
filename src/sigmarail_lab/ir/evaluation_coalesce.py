"""Resolve research Evaluation (dates, cash, benchmark) for Initialize / live."""

from __future__ import annotations

from typing import Any, Callable

DEFAULT_START = "2022-01-01"
DEFAULT_END = "2022-12-31"
DEFAULT_CASH = 100_000
DEFAULT_BENCHMARK = "SPY"

GetParameter = Callable[[str], Any]


def _as_eval_dict(evaluation: Any) -> dict[str, Any]:
    if evaluation is None:
        return {}
    if isinstance(evaluation, dict):
        return evaluation
    dump = getattr(evaluation, "model_dump", None)
    if callable(dump):
        return dump()
    return {
        "start_date": getattr(evaluation, "start_date", None),
        "end_date": getattr(evaluation, "end_date", None),
        "initial_cash": getattr(evaluation, "initial_cash", None),
        "benchmark": getattr(evaluation, "benchmark", None),
    }


def _pick(*vals: Any) -> str | None:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def coalesce_research_evaluation(
    *,
    get_parameter: GetParameter | None = None,
    parameter_map: dict[str, str] | None = None,
    evaluation: Any = None,
) -> tuple[str, str, int, str]:
    """CLI GetParameter wins, then AlgorithmParameters, then VeraBase.Evaluation.

    Live trading (future) uses cash + benchmark from the same sources; job dates
    still come from the backtest/optimizer submit window.
    """
    gp = get_parameter or (lambda _k: None)
    pm = parameter_map or {}
    ev = _as_eval_dict(evaluation)

    start = _pick(gp("start-date"), pm.get("start-date"), ev.get("start_date")) or DEFAULT_START
    end = _pick(gp("end-date"), pm.get("end-date"), ev.get("end_date")) or DEFAULT_END
    cash_s = _pick(gp("initial-cash"), pm.get("initial-cash"), ev.get("initial_cash"))
    try:
        cash = int(float(cash_s)) if cash_s else DEFAULT_CASH
    except (TypeError, ValueError):
        cash = DEFAULT_CASH
    bench = (
        _pick(gp("benchmark"), pm.get("benchmark"), ev.get("benchmark")) or DEFAULT_BENCHMARK
    ).upper()
    return start, end, cash, bench
