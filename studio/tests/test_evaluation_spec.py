from __future__ import annotations

from screens.evaluation_spec import evaluation_extra_env, stamp_evaluation


def test_stamp_evaluation_writes_json_and_lean_params() -> None:
    spec = {
        "SchemaVersion": 2,
        "Kind": "VeraLabV1",
        "Framework": {},
        "AlgorithmParameters": {"regime-source": "screener"},
        "VeraBase": {"Universe": {"version": 1, "select": ["ticker"]}},
    }
    out = stamp_evaluation(
        spec,
        start_date="2024-01-02",
        end_date="2024-06-30",
        initial_cash=50000,
        benchmark="qqq",
    )
    ev = out["VeraBase"]["Evaluation"]
    assert ev == {
        "start_date": "2024-01-02",
        "end_date": "2024-06-30",
        "initial_cash": 50000,
        "benchmark": "QQQ",
    }
    algo = out["AlgorithmParameters"]
    assert algo["regime-source"] == "screener"
    assert algo["initial-cash"] == "50000"
    assert algo["benchmark"] == "QQQ"
    assert algo["start-date"] == "2024-01-02"
    assert algo["end-date"] == "2024-06-30"
    assert spec["AlgorithmParameters"] == {"regime-source": "screener"}


def test_evaluation_extra_env_for_lean_cli() -> None:
    stamped = stamp_evaluation(
        {"AlgorithmParameters": {}, "VeraBase": {}},
        start_date="2025-01-01",
        end_date="2026-01-01",
        initial_cash=25000,
        benchmark="IWM",
    )
    assert evaluation_extra_env(stamped) == {
        "initial-cash": "25000",
        "benchmark": "IWM",
    }
