"""Component 4 Tier 1: Pareto non-dominated sorting + OOS efficiency guard.

Exercises the same frontier math as ``screens.optimizer`` heatmap assembly
(return vs drawdown, constraint filtering, OOS efficiency) on synthetic grids.
"""
from __future__ import annotations


def pareto_frontier(points: list[dict]) -> list[dict]:
    """Mirror of the dominance loop in get_optimizer_session_heatmap."""
    compliant = [p for p in points if p.get("passes_constraints", True)]
    frontier = []
    for p1 in compliant:
        if any(
            (p2["total_return"] >= p1["total_return"] and p2["max_drawdown"] <= p1["max_drawdown"])
            and (p2["total_return"] > p1["total_return"] or p2["max_drawdown"] < p1["max_drawdown"])
            for p2 in compliant
            if p2["run_id"] != p1["run_id"]
        ):
            continue
        frontier.append(p1)
    return sorted(frontier, key=lambda p: p["max_drawdown"])


def oos_efficiency(in_sample_sharpe: float, oos_sharpe: float) -> float:
    return round(oos_sharpe / max(0.01, in_sample_sharpe), 3)


def _grid() -> list[dict]:
    return [
        {"run_id": f"r{i}", "total_return": r, "max_drawdown": dd, "passes_constraints": True}
        for i, (r, dd) in enumerate(
            [
                (0.10, 0.05),  # frontier
                (0.08, 0.04),  # frontier
                (0.09, 0.06),  # dominated by (0.10, 0.05)
                (0.05, 0.03),  # frontier
                (0.05, 0.05),  # dominated by (0.05, 0.03)
            ]
        )
    ]


def test_non_dominated_sorting():
    frontier = pareto_frontier(_grid())
    ids = {p["run_id"] for p in frontier}
    assert ids == {"r0", "r1", "r3"}


def test_constraint_filtering():
    pts = _grid()
    pts[0]["passes_constraints"] = False
    frontier = pareto_frontier(pts)
    assert "r0" not in {p["run_id"] for p in frontier}


def test_oos_efficiency_guard_flags_overfit():
    eff = oos_efficiency(3.0, 0.4)
    assert eff == 0.133
    assert eff < 0.5  # collapsed OOS -> overfit flag threshold


def test_oos_efficiency_healthy():
    eff = oos_efficiency(1.5, 1.32)
    assert eff == 0.88
    assert eff >= 0.5
