"""Strategy-stage evidence must observe the LEAN loop without changing targets."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from sigmarail_lab.runtime.store_backed_loop import run_store_backed_rebalance


class _Symbol:
    def __init__(self, value: str):
        self.Value = value


class _Target:
    def __init__(self, ticker: str, quantity: int):
        self.Symbol = _Symbol(ticker)
        self.Quantity = quantity


def test_store_loop_records_stages_and_preserves_returned_targets() -> None:
    session = date(2026, 11, 19)
    algorithm = SimpleNamespace(
        Time=SimpleNamespace(date=lambda: session),
        _decision_universe_rows={"AAPL": {"rs_rating": 95, "close": 210.0}},
        _strategy_content_hash="a" * 64,
        Portfolio=SimpleNamespace(items=lambda: []),
    )
    insight = SimpleNamespace(
        Symbol=_Symbol("AAPL"), Direction="Up", Confidence=0.8,
        Magnitude=0.05, Weight=0.1, Period="timedelta(days=1)",
    )
    alpha = MagicMock()
    alpha.Update.return_value = [insight]
    target = _Target("AAPL", 10)
    portfolio = MagicMock()
    portfolio.CreateTargets.return_value = [target]
    risk = MagicMock()
    risk.ManageRisk.return_value = []
    execution = MagicMock()

    result = run_store_backed_rebalance(algorithm, alpha, portfolio, risk, execution)

    assert result == [target]
    assert [event["stage"] for event in algorithm._strategy_decision_events] == [
        "universe", "alpha", "portfolio", "risk", "execution",
    ]
    assert all(event["strategy_content_hash"] == "a" * 64 for event in algorithm._strategy_decision_events)
    assert all(event["as_of"] == "2026-11-18" for event in algorithm._strategy_decision_events)
    assert algorithm._strategy_decision_events[-1]["outcome"] == "target passed to execution model"
    execution.Execute.assert_called_once_with(algorithm, [target])
