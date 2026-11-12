"""Alpha-performance endpoint tests (mocked — no ClickHouse required).

Covers VeraProjects#74: GET /api/screens/fields/<name>/alpha-performance
delegates to vera_query_core.alpha_evaluation.evaluate_factor_performance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

_URL = "/api/screens/fields/rs_rating/alpha-performance"
_QS = "start=2025-01-01&end=2025-12-31&horizon=5d&quantiles=2&table=screener_price_tech_daily"


def _res(rows: list[tuple[Any, ...]]) -> MagicMock:
    m = MagicMock()
    m.result_rows = rows
    m.column_names = []
    return m


def _client_with(side_effect: list[MagicMock] | Exception) -> MagicMock:
    client = MagicMock()
    if isinstance(side_effect, Exception):
        client.query.side_effect = side_effect
    else:
        client.query.side_effect = side_effect
    return client


@pytest.mark.django_db
def test_alpha_performance_happy_path() -> None:
    client = _client_with(
        [
            _res([(1,)]),  # factor table exists
            _res([(1,)]),  # screener_forward_returns_daily exists
            _res([(1,)]),  # market_regime_signals_daily exists
            _res(  # quantiles
                [
                    (1, 200, -0.0010, 0.0030, -0.0040, 0.40, 50),
                    (2, 200, 0.0050, 0.0030, 0.0020, 0.62, 50),
                ]
            ),
            _res([("2025-01-02", 0.05), ("2025-01-03", 0.04)]),  # daily IC
            _res([(1.0, 40, 0.0030), (0.0, 10, -0.0010)]),  # regime attribution
            _res([("2025-01-02",), ("2025-01-03",)]),  # spine dates
            _res([("2025-01-02",), ("2025-01-03",)]),  # factor dates
            _res([("2025-01-02",), ("2025-01-03",)]),  # labelled dates
            _res([("2025-01-02",), ("2025-01-03",)]),  # eligible dates
        ]
    )
    with patch("api.views.get_ch_client", return_value=client):
        resp = Client().get(f"{_URL}?{_QS}")
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "quantiles",
        "ic_stats",
        "regime_attribution",
        "monotonicity_score",
        "summary",
        "verdict",
        "verdict_reasons",
    ):
        assert key in data
    assert data["factor"] == "rs_rating"
    assert data["factor_table"] == "screener_price_tech_daily"
    assert data["horizon"] == "5d"
    assert len(data["quantiles"]) == 2
    assert data["verdict"] in {"pass", "fail", "insufficient_data"}

    # Evaluator binds window + quantile count as CH parameters (never interpolated).
    params_seen: dict[str, Any] = {}
    for call in client.query.call_args_list:
        params_seen.update(call.kwargs.get("parameters") or {})
    assert params_seen.get("start") == "2025-01-01"
    assert params_seen.get("end") == "2025-12-31"
    assert params_seen.get("q") == 2
    client.close.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "qs",
    [
        "start=2025-01-01&end=2025-12-31&horizon=1h",
        "start=2025-01-01&end=2025-12-31&quantiles=99",
        "start=2025-01-01&end=2025-12-31&quantiles=abc",
        "end=2025-12-31",
        "start=2025-01-01",
    ],
)
def test_alpha_performance_invalid_params_400_no_ch(qs: str) -> None:
    with patch("api.views.get_ch_client") as mock_ch:
        resp = Client().get(f"{_URL}?{qs}")
    assert resp.status_code == 400
    assert resp.json()["detail"]
    mock_ch.assert_not_called()


@pytest.mark.django_db
def test_alpha_performance_missing_forward_mart_400() -> None:
    client = _client_with(
        [
            _res([(1,)]),  # factor table exists
            _res([(0,)]),  # forward mart missing
        ]
    )
    with patch("api.views.get_ch_client", return_value=client):
        resp = Client().get(f"{_URL}?{_QS}")
    assert resp.status_code == 400
    assert "screener_forward_returns_daily" in resp.json()["detail"]


@pytest.mark.django_db
def test_alpha_performance_unknown_column_400() -> None:
    def _raise(sql: str, **kwargs: Any) -> MagicMock:
        if "system.tables" in sql:
            return _res([(1,)])
        raise Exception("UNKNOWN_IDENTIFIER: Identifier 'f.rs_rating' cannot be resolved")

    client = MagicMock()
    client.query.side_effect = _raise
    with patch("api.views.get_ch_client", return_value=client):
        resp = Client().get(f"{_URL}?{_QS}")
    assert resp.status_code == 400
    assert "UNKNOWN_IDENTIFIER" in resp.json()["detail"]


@pytest.mark.django_db
def test_alpha_performance_table_resolved_from_catalog() -> None:
    client = _client_with([])
    client.query.side_effect = [
        _res([(1,)]),  # factor table
        _res([(1,)]),  # forward mart
        _res([(0,)]),  # regime table absent → no regime query
        _res([]),  # quantiles empty
        _res([]),  # IC empty
        _res([]),  # spine dates
        _res([]),  # factor dates
        _res([]),  # labelled dates
        _res([]),  # eligible dates
    ]
    catalog = [
        {
            "name": "atr_14_pct",
            "prefixed_name": "px.atr_14_pct",
            "table": "screener_price_tech_daily",
        }
    ]
    with (
        patch("api.views.get_ch_client", return_value=client),
        patch("api.views.list_screen_fields", return_value=catalog),
    ):
        resp = Client().get(
            "/api/screens/fields/px.atr_14_pct/alpha-performance"
            "?start=2025-01-01&end=2025-12-31"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["factor"] == "atr_14_pct"
    assert data["factor_table"] == "screener_price_tech_daily"
    assert data["verdict"] == "insufficient_data"
