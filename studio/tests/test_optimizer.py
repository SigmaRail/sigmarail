from unittest.mock import MagicMock, patch
import pytest

from screens.optimizer import (
    _deep_inject_param,
    generate_grid_combinations,
    create_and_launch_optimization_session,
    get_optimizer_session_heatmap,
)


def test_deep_inject_param():
    spec = {
        "Framework": {
            "Alpha": {"Type": "VeraScreenerAlphaModel", "Parameters": {}},
            "PortfolioConstruction": {"Type": "VeraScreenerPortfolioConstructionModel", "Parameters": {}},
            "RiskManagement": {"Type": "TrailingStopRiskManagementModel", "Parameters": {}},
        }
    }

    _deep_inject_param(spec, "stop_loss_pct", 0.06)
    assert spec["Framework"]["Alpha"]["Parameters"]["stop_loss_pct"] == 0.06

    _deep_inject_param(spec, "max_positions", 15)
    assert spec["Framework"]["Alpha"]["Parameters"]["max_positions"] == 15
    assert spec["Framework"]["PortfolioConstruction"]["Parameters"]["max_positions"] == 15

    _deep_inject_param(spec, "target_atr_risk", 0.005)
    assert spec["Framework"]["PortfolioConstruction"]["Parameters"]["target_atr_risk"] == 0.005

    _deep_inject_param(spec, "trailing_stop_pct", 0.04)
    assert spec["Framework"]["RiskManagement"]["Parameters"]["maximum_drawdown_percent"] == 0.04

    _deep_inject_param(spec, "max_sector_exposure", 0.20)
    assert spec["Framework"]["RiskManagement"]["Parameters"]["maximum_sector_exposure"] == 0.20


def test_generate_grid_combinations_1d():
    combos = generate_grid_combinations(
        param_x_name="stop_loss_pct",
        param_x_values=[0.05, 0.08, 0.10],
    )
    assert len(combos) == 3
    assert combos[0] == {"stop_loss_pct": 0.05}
    assert combos[1] == {"stop_loss_pct": 0.08}
    assert combos[2] == {"stop_loss_pct": 0.10}


def test_generate_grid_combinations_2d():
    combos = generate_grid_combinations(
        param_x_name="stop_loss_pct",
        param_x_values=[0.05, 0.08],
        param_y_name="target_atr_risk",
        param_y_values=[0.002, 0.004, 0.006],
    )
    assert len(combos) == 6
    assert combos[0] == {"stop_loss_pct": 0.05, "target_atr_risk": 0.002}
    assert combos[5] == {"stop_loss_pct": 0.08, "target_atr_risk": 0.006}


def test_create_and_launch_optimization_session():
    mock_client = MagicMock()
    mock_client.query.return_value.result_rows = [(
        '{"Framework": {}, "AlgorithmParameters": {"initial-cash": "50000", "benchmark": "QQQ"}, "VeraBase": {"Evaluation": {"initial_cash": 50000, "benchmark": "QQQ"}}}',
        "Test Strategy",
    )]

    with patch("screens.optimizer.save_spec") as mock_save, \
         patch("screens.optimizer.submit_backtest_job") as mock_submit:
        mock_submit.return_value = {"job_id": "test-job-1"}

        result = create_and_launch_optimization_session(
            base_ir_id="studio-test-spec",
            start_date="2025-01-01",
            end_date="2026-01-01",
            param_x_name="stop_loss_pct",
            param_x_values=[0.05, 0.08],
            param_y_name="target_atr_risk",
            param_y_values=[0.002, 0.004],
            client=mock_client,
        )

        assert result["total_combinations"] == 4
        assert len(result["jobs"]) == 4
        assert mock_submit.call_count == 4
        extra = mock_submit.call_args.kwargs["extra_env"]
        assert extra["initial-cash"] == "50000"
        assert extra["benchmark"] == "QQQ"
        assert extra["OPTIMIZER_SESSION_ID"]
        assert mock_client.command.call_count == 1


def test_get_optimizer_session_heatmap_and_pareto():
    mock_client = MagicMock()
    # Mock session row
    mock_client.query.side_effect = [
        # Session query
        MagicMock(result_rows=[(
            "opt-123", "VeraTradingLab", "studio-test-spec", "Test Opt", "sharpe_ratio",
            "stop_loss_pct", [0.05, 0.08], "target_atr_risk", [0.002, 0.004],
            4, "running", None, None, None, "2026-01-01T00:00:00", "2026-01-01T00:00:00"
        )]),
        # Runs query
        MagicMock(result_rows=[
            # run_id, ir_id, total_return, annual_return, sharpe, sortino, max_dd, win_rate, pf, orders, params, created_at
            ("run-1", "studio-test-spec-opt-01", 0.15, 0.15, 1.8, 2.2, 0.05, 0.65, 1.9, 40, '{"stop_loss_pct": 0.05, "target_atr_risk": 0.002}', "2026-01-01"),
            ("run-2", "studio-test-spec-opt-02", 0.25, 0.25, 2.4, 3.1, 0.08, 0.70, 2.4, 45, '{"stop_loss_pct": 0.05, "target_atr_risk": 0.004}', "2026-01-01"),
            ("run-3", "studio-test-spec-opt-03", 0.10, 0.10, 1.2, 1.5, 0.09, 0.55, 1.4, 35, '{"stop_loss_pct": 0.08, "target_atr_risk": 0.002}', "2026-01-01"),
            ("run-4", "studio-test-spec-opt-04", 0.18, 0.18, 1.9, 2.5, 0.07, 0.62, 2.0, 50, '{"stop_loss_pct": 0.08, "target_atr_risk": 0.004}', "2026-01-01"),
        ]),
        # Spec prefetch query
        MagicMock(result_rows=[]),
    ]

    result = get_optimizer_session_heatmap("opt-123", client=mock_client)
    assert result["completed_runs"] == 4
    assert result["is_done"] is True
    assert result["best_run"]["run_id"] == "run-2"
    assert result["best_run"]["sharpe_ratio"] == 2.4

    # Check 2D heatmap matrix (2 rows x 2 cols)
    sharpe_mat = result["heatmap"]["sharpe_matrix"]
    assert sharpe_mat[0][0] == 1.8  # (0.05, 0.002)
    assert sharpe_mat[1][0] == 2.4  # (0.05, 0.004)
    assert sharpe_mat[0][1] == 1.2  # (0.08, 0.002)
    assert sharpe_mat[1][1] == 1.9  # (0.08, 0.004)

    # Check Pareto Frontier
    pareto = result["pareto_frontier"]
    # run-1 (return 0.15, dd 0.05) and run-2 (return 0.25, dd 0.08) are pareto optimal
    # run-3 (return 0.10, dd 0.09) is dominated by run-1 and run-2
    # run-4 (return 0.18, dd 0.07) is pareto optimal or dominated? run-1 has lower dd (0.05 vs 0.07) and run-2 has higher return (0.25 vs 0.18) with higher dd (0.08 vs 0.07) -> run-4 is pareto optimal!
    assert len(pareto) >= 2
    pareto_run_ids = [p["run_id"] for p in pareto]
    assert "run-1" in pareto_run_ids
    assert "run-2" in pareto_run_ids
    assert "run-3" not in pareto_run_ids
