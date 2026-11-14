"""deploy domain: live trading deployments (read side) + paper promotion (Component 2)."""
from __future__ import annotations

from typing import Any

from sigmarail_studio_mcp.ch import call, get_client


def list_deployments(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    from sigmarail.features.live_report import list_live_deployments

    return call(list_live_deployments, status=status, limit=limit)


def status(deployment_id: str) -> dict[str, Any]:
    from sigmarail.features.live_report import get_live_status

    return call(get_live_status, deployment_id=deployment_id)


def performance(deployment_id: str, days: int = 30) -> dict[str, Any]:
    from sigmarail.features.live_report import get_live_performance

    return call(get_live_performance, deployment_id=deployment_id, days=days)


# --- Paper promotion (Component 2: implementation plan) ----------------------


def evaluate_promotion_gate(ir_id: str, run_id: str) -> dict[str, Any]:
    """Pre-flight eligibility: run exists, job done, IR matches (+ report metrics)."""
    from screens.live_promotion import check_promotion_gate

    def _check(client: Any) -> dict[str, Any]:
        return check_promotion_gate(client, approval_backtest_run_id=run_id, ir_id=ir_id)

    return call(_check)


def register_paper_deployment(
    ir_id: str,
    run_id: str,
    deployment_id: str | None = None,
    lean_environment: str = "live-alpaca",
    brokerage: str = "AlpacaBrokerage",
) -> dict[str, Any]:
    """Gate-then-INSERT into ``live_deployments`` (raises on gate failure)."""
    from screens.live_promotion import register_paper_deployment as _register

    def _reg(client: Any) -> dict[str, Any]:
        return _register(
            client,
            deployment_id=deployment_id or "",
            ir_id=ir_id,
            approval_backtest_run_id=run_id,
            lean_environment=lean_environment,
            brokerage=brokerage,
        )

    return call(_reg)
