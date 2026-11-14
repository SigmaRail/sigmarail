"""Run artifacts / equity curve unit tests (mocked CH)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from screens.run_artifacts import get_run_equity_curve, get_run_orders, list_run_artifacts


def _equity_payload() -> dict:
    return {
        "charts": {
            "Strategy Equity": {
                "series": {
                    "Equity": {
                        "values": [
                            [1700000000, 100000.0, 100000.0],
                            [1700086400, 101500.0, 101500.0],
                        ]
                    }
                }
            }
        }
    }


def test_get_run_equity_curve_from_backtest_results() -> None:
    client = MagicMock()
    result = MagicMock()
    result.result_rows = [(json.dumps(_equity_payload()),)]
    client.query.return_value = result
    out = get_run_equity_curve(client, "run-1")
    assert out["source"] == "backtest_results"
    assert out["count"] == 2
    assert out["points"][0]["equity"] == 100000.0


def test_list_run_artifacts() -> None:
    client = MagicMock()
    result = MagicMock()
    result.column_names = ["artifact_type", "json_bytes", "created_at"]
    result.result_rows = [("summary", 120, None), ("backtest_results", 9000, None)]
    client.query.return_value = result
    out = list_run_artifacts(client, "run-1")
    assert out["count"] == 2


def test_get_run_orders_from_dict() -> None:
    client = MagicMock()
    empty = MagicMock()
    empty.result_rows = []
    payload = MagicMock()
    payload.result_rows = [
        (
            json.dumps(
                {
                    "orders": {
                        "1": {"symbolValue": "AAPL", "status": "filled"},
                        "2": {"symbolValue": "MSFT", "status": "filled"},
                    }
                }
            ),
        )
    ]
    client.query.side_effect = [empty, payload]
    out = get_run_orders(client, "run-1", limit=10)
    assert out["source"] == "backtest_results.orders"
    assert out["total"] == 2


def test_get_run_orders_from_array() -> None:
    client = MagicMock()
    result = MagicMock()
    result.result_rows = [(json.dumps([{"symbolValue": "AAPL", "status": "filled"}]),)]
    client.query.return_value = result
    out = get_run_orders(client, "run-1", limit=10)
    assert out["source"] == "order_events"
    assert out["count"] == 1


def test_get_run_artifact_preview() -> None:
    from screens.run_artifacts import get_run_artifact_preview

    client = MagicMock()
    result = MagicMock()
    result.result_rows = [(json.dumps({"ok": True, "n": 1}),)]
    client.query.return_value = result
    out = get_run_artifact_preview(client, "run-1", "summary")
    assert out["error"] is None
    assert out["preview"] is not None
    assert '"ok": true' in out["preview"].lower() or '"ok": true' in out["preview"]


@pytest.mark.django_db
def test_equity_endpoint_mocked() -> None:
    with patch("api.views.get_ch_client") as mock_ch, patch(
        "api.views.get_run_equity_curve",
        return_value={"run_id": "r1", "points": [{"t": 1, "equity": 1.0}], "count": 1},
    ):
        mock_ch.return_value = MagicMock()
        c = Client()
        resp = c.get("/api/backtests/runs/r1/equity")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_get_run_monthly_returns_from_rolling_window() -> None:
    from screens.run_artifacts import get_run_monthly_returns

    client = MagicMock()
    result = MagicMock()
    payload = {
        "rollingWindow": {
            "M1_20250831": {"portfolioStatistics": {"totalNetProfit": "0.025"}},
            "M1_20250930": {"portfolioStatistics": {"totalNetProfit": "-0.010"}},
        }
    }
    result.result_rows = [(json.dumps(payload),)]
    client.query.return_value = result
    out = get_run_monthly_returns(client, "run-1")
    assert out["years"] == [2025]
    assert out["matrix"]["2025"]["8"] == 0.025
    assert out["matrix"]["2025"]["9"] == -0.010
    assert out["total_months"] == 2
    assert out["win_months"] == 1


def test_get_run_trade_analytics() -> None:
    from screens.run_artifacts import get_run_trade_analytics

    client = MagicMock()
    result = MagicMock()
    payload = {
        "totalPerformance": {
            "tradeStatistics": {
                "totalNumberOfTrades": 10,
                "numberOfWinningTrades": 7,
                "numberOfLosingTrades": 3,
                "averageProfit": "150.0",
                "averageLoss": "-80.0",
                "expectancy": "0.45",
            },
            "portfolioStatistics": {
                "winRate": "0.70",
                "profitLossRatio": "1.875",
            },
            "closedTrades": [
                {
                    "id": "t1",
                    "symbols": [{"value": "NVDA"}],
                    "entryPrice": 100.0,
                    "exitPrice": 110.0,
                    "direction": 0,
                    "quantity": 10.0,
                    "profitLoss": 100.0,
                    "mae": 2.0,
                    "mfe": 12.0,
                    "duration": "2.00:00:00",
                    "isWin": True,
                }
            ],
        }
    }
    result.result_rows = [(json.dumps(payload),)]
    client.query.return_value = result
    out = get_run_trade_analytics(client, "run-1")
    assert out["trade_statistics"]["total_trades"] == 10
    assert out["trade_statistics"]["winning_trades"] == 7
    assert len(out["excursions"]) == 1
    assert out["excursions"][0]["symbol"] == "NVDA"
    assert out["excursions"][0]["is_win"] is True


@pytest.mark.django_db
def test_monthly_returns_and_trade_analytics_endpoints() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value = MagicMock()
        with patch("api.views.get_run_monthly_returns", return_value={"run_id": "r1", "years": [2025]}):
            c = Client()
            resp = c.get("/api/backtests/runs/r1/monthly-returns")
            assert resp.status_code == 200
            assert resp.json()["years"] == [2025]

        with patch("api.views.get_run_trade_analytics", return_value={"run_id": "r1", "trade_statistics": {"total_trades": 5}}):
            resp = c.get("/api/backtests/runs/r1/trade-analytics")
            assert resp.status_code == 200
            assert resp.json()["trade_statistics"]["total_trades"] == 5


def test_compare_runs_logic() -> None:
    from screens.run_artifacts import compare_runs

    client = MagicMock()
    # Mock query result for strategy_runs
    runs_res = MagicMock()
    runs_res.column_names = ["run_id", "ir_id", "total_return", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown", "win_rate", "profit_factor", "total_orders", "total_fees", "start_equity", "end_equity", "period_start", "period_end", "trigger", "run_timestamp", "git_commit", "git_branch"]
    runs_res.result_rows = [
        ("r1", "ir-1", 0.05, 0.05, 1.2, 1.5, 0.04, 0.65, 1.8, 20, 50.0, 100000.0, 105000.0, "2025-01-01", "2025-12-31", "manual", None, None, None),
        ("r2", "ir-2", 0.10, 0.10, 1.8, 2.1, 0.06, 0.70, 2.2, 30, 80.0, 100000.0, 110000.0, "2025-01-01", "2025-12-31", "manual", None, None, None),
    ]

    # Mock equity artifact query
    eq_res = MagicMock()
    eq_res.result_rows = [(json.dumps(_equity_payload()),)]

    # Side effect: first query is strategy_runs, then artifacts for r1, then artifacts for r2
    client.query.side_effect = [runs_res, eq_res, eq_res, eq_res, eq_res]

    out = compare_runs(client, ["r1", "r2"])
    assert out["count"] == 2
    assert out["runs"][0]["run_id"] == "r1"
    assert out["runs"][1]["run_id"] == "r2"
    assert out["runs"][0]["metrics"]["total_return"] == 0.05
    assert out["runs"][1]["metrics"]["total_return"] == 0.10


@pytest.mark.django_db
def test_compare_runs_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value = MagicMock()
        with patch("api.views.compare_runs", return_value={"runs": [{"run_id": "r1"}], "count": 1}):
            c = Client()
            resp = c.get("/api/backtests/compare?run_ids=r1,r2")
            assert resp.status_code == 200
            assert resp.json()["count"] == 1


def test_get_run_attribution() -> None:
    from datetime import date
    from screens.run_artifacts import get_run_attribution

    client = MagicMock()
    # Mock backtest_results artifact
    art_res = MagicMock()
    payload = {
        "totalPerformance": {
            "closedTrades": [
                {
                    "id": "t1",
                    "symbols": [{"value": "NVDA"}],
                    "entryTime": "2026-02-01 09:30:00",
                    "exitTime": "2026-02-05 16:00:00",
                    "profitLoss": 250.0,
                    "return_pct": 0.05,
                    "isWin": True,
                },
                {
                    "id": "t2",
                    "symbols": [{"value": "PFE"}],
                    "entryTime": "2026-02-01 09:30:00",
                    "exitTime": "2026-02-05 16:00:00",
                    "profitLoss": -100.0,
                    "return_pct": -0.02,
                    "isWin": False,
                },
            ]
        }
    }
    art_res.result_rows = [(json.dumps(payload),)]

    # Mock tickers query
    sec_res = MagicMock()
    sec_res.result_rows = [
        ("NVDA", "Technology", "Semiconductors"),
        ("PFE", "Healthcare", "Biotechnology"),
    ]

    # Mock market_regime_signals query
    reg_res = MagicMock()
    reg_res.result_rows = [
        (date(2026, 1, 26), 65.0, 0, 100.0),
    ]

    client.query.side_effect = [art_res, sec_res, reg_res]

    out = get_run_attribution(client, "run-1")
    assert len(out["sectors"]) == 2
    assert out["sectors"][0]["sector"] == "Technology"
    assert out["sectors"][0]["total_pnl"] == 250.0
    assert out["sectors"][1]["sector"] == "Healthcare"
    assert out["sectors"][1]["total_pnl"] == -100.0
    assert out["summary"]["total_pnl"] == 150.0
    assert len(out["regimes"]) >= 1


@pytest.mark.django_db
def test_attribution_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value = MagicMock()
        with patch("api.views.get_run_attribution", return_value={"run_id": "r1", "sectors": []}):
            c = Client()
            resp = c.get("/api/backtests/runs/r1/attribution")
            assert resp.status_code == 200
            assert resp.json()["run_id"] == "r1"


def test_get_ticker_candles() -> None:
    from datetime import date
    from screens.run_artifacts import get_ticker_candles

    client = MagicMock()
    sep_res = MagicMock()
    sep_res.result_rows = [
        (date(2026, 1, 2), 100.0, 105.0, 99.0, 104.0, 1000000.0, 104.0),
        (date(2026, 1, 5), 104.0, 108.0, 103.0, 107.0, 1200000.0, 107.0),
    ]

    t_res = MagicMock()
    t_res.result_rows = [("NVIDIA CORP", "Technology", "Semiconductors")]

    client.query.side_effect = [sep_res, t_res]

    out = get_ticker_candles(client, "NVDA", "2026-01-01", "2026-01-10")
    assert out["ticker"] == "NVDA"
    assert out["count"] == 2
    assert out["candles"][0]["open"] == 100.0
    assert out["meta"]["name"] == "NVIDIA CORP"


@pytest.mark.django_db
def test_candles_endpoint() -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        mock_ch.return_value = MagicMock()
        with patch("api.views.get_ticker_candles", return_value={"ticker": "NVDA", "candles": [], "count": 0}):
            c = Client()
            resp = c.get("/api/backtests/candles?ticker=NVDA&start_date=2026-01-01&end_date=2026-01-10")
            assert resp.status_code == 200
            assert resp.json()["ticker"] == "NVDA"


def test_get_run_orders_filtered_by_symbol_and_id() -> None:
    client = MagicMock()
    result = MagicMock()
    result.result_rows = [(json.dumps([
        {"id": "o-1", "symbol": {"value": "AAPL"}, "status": "filled", "quantity": 10},
        {"id": "o-2", "symbol": {"value": "UBER"}, "status": "filled", "quantity": 20},
        {"id": "o-3", "symbol": {"value": "UBER"}, "status": "filled", "quantity": 30},
    ]),)]
    client.query.return_value = result

    # Filter by symbol
    out = get_run_orders(client, "run-1", symbol="UBER")
    assert out["count"] == 2
    assert all(o["symbol"]["value"] == "UBER" for o in out["orders"])

    # Filter by order_id
    out_id = get_run_orders(client, "run-1", order_id="o-1")
    assert out_id["count"] == 1
    assert out_id["orders"][0]["id"] == "o-1"


def test_get_run_closed_trades_filtered_by_symbol_and_id() -> None:
    from screens.run_artifacts import get_run_closed_trades

    client = MagicMock()
    payload = {
        "totalPerformance": {
            "closedTrades": [
                {"id": "t-1", "symbol": "AAPL", "entryPrice": 150, "exitPrice": 160, "profit_loss": 100},
                {"id": "t-2", "symbol": "UBER", "entryPrice": 60, "exitPrice": 75, "profit_loss": 300},
            ]
        }
    }
    result = MagicMock()
    result.result_rows = [(json.dumps(payload),)]
    client.query.return_value = result

    # Filter by symbol
    out_sym = get_run_closed_trades(client, "run-1", symbol="UBER")
    assert out_sym["count"] == 1
    assert out_sym["trades"][0]["id"] == "t-2"

    # Filter by trade_id
    out_id = get_run_closed_trades(client, "run-1", trade_id="t-1")
    assert out_id["count"] == 1
    assert out_id["trades"][0]["id"] == "t-1"
