"""LEAN universe contract lowering and query execution checks."""

from __future__ import annotations

from datetime import date

import pytest


def _request() -> dict:
    return {
        "start_date": "2024-12-31",
        "end_date": "2024-12-31",
        "mode": "detail",
        "export_format": "objects",
        "limit": 300_000,
        "spec": {
            "version": 2,
            "spine": "screener_price_tech_daily",
            "select": ["ticker", "date", "close"],
            "computed": [
                {
                    "alias": "above_50",
                    "kind": "bool",
                    "where": {
                        "type": "gte",
                        "left": {"type": "col", "name": "close"},
                        "right": {"type": "lit", "value": 50},
                    },
                },
                {
                    "alias": "score",
                    "kind": "number",
                    "expr": {
                        "type": "formula",
                        "op": "/",
                        "args": [
                            {"type": "col", "name": "close"},
                            {"type": "lit", "value": 50},
                        ],
                    },
                },
                {"alias": "screen_count", "kind": "number", "sum_aliases": ["above_50"]},
                {"alias": "mean_price", "kind": "number", "mean_available": ["close", "high"]},
            ],
            "where": {
                "type": "eq",
                "left": {"type": "col", "name": "ticker"},
                "right": {"type": "lit", "value": "AAPL"},
            },
            "post_where": {
                "type": "gt",
                "left": {"type": "col", "name": "score"},
                "right": {"type": "lit", "value": 0},
            },
            "order_by": [{"field": "score", "direction": "desc"}],
            "limit_per_day": 20,
        },
    }


class _FakeResult:
    column_names = ["ticker", "date", "close", "above_50", "score", "screen_count", "mean_price"]
    result_rows = [("AAPL", date(2024, 12, 31), 100.0, 1, 2.0, 1, 101.0)]


class _FakeClient:
    def __init__(self) -> None:
        self.sql = ""
        self.parameters = {}

    def query(self, sql: str, parameters: dict) -> _FakeResult:
        self.sql = sql
        self.parameters = parameters
        return _FakeResult()


def test_universe_adapter_compiles_full_bounded_expression_surface() -> None:
    from sigmarail.universe import universe_run

    client = _FakeClient()
    result = universe_run(_request(), client=client)

    assert "error" not in result, result
    assert result["registry_digest"].startswith("sha256:")
    assert result["computed_aliases"] == ["above_50", "score", "screen_count", "mean_price"]
    assert result["required_fields"] == ["ticker", "date", "close", "above_50", "score", "screen_count", "mean_price"]
    assert result["rows"][0]["date"] == "2024-12-31"
    assert "toUInt8(ifNull(" in client.sql
    assert "isNotNull(d0.`close`)" in client.sql
    assert "arrayAvg([" not in client.sql
    assert "SELECT * FROM (" in client.sql
    assert "LIMIT 20 BY `date` LIMIT 300000" in client.sql
    assert "AAPL" not in client.sql
    assert "AAPL" in client.parameters.values()


def test_universe_adapter_auto_resolves_only_declared_core_joins() -> None:
    from sigmarail.universe import _adapt_universe_request

    request = _request()
    request["spec"]["select"].append("mrt_roe")
    query, _ = _adapt_universe_request(request)

    assert len(query.joins) == 1
    assert "screener_fundamentals_daily" in query.joins[0].relationship_id


def test_universe_membership_aggregate_compiles_without_detail_limits() -> None:
    from sigmarail.universe import universe_membership_counts

    class AggregateClient:
        sql = ""
        parameters = {}

        def query(self, sql: str, parameters: dict) -> _FakeResult:
            self.sql = sql
            self.parameters = parameters
            result = _FakeResult()
            result.column_names = ["day", "member_count"]
            result.result_rows = [(date(2024, 12, 31), 1)]
            return result

    client = AggregateClient()
    result = universe_membership_counts(
        _request()["spec"],
        start_date="2024-12-01",
        end_date="2024-12-31",
        client=client,
    )

    assert result == [{"date": "2024-12-31", "count": 1}]
    assert "GROUP BY q.`date`" in client.sql
    assert "LIMIT" not in client.sql.upper()
    assert client.parameters["start_date"] == "2024-12-01"
    assert client.parameters["end_date"] == "2024-12-31"


def test_universe_measure_series_compiles_registered_computed_aliases() -> None:
    from sigmarail.universe import universe_measure_series

    class MeasureClient:
        sql = ""
        parameters = {}

        def query(self, sql: str, parameters: dict) -> _FakeResult:
            self.sql = sql
            self.parameters = parameters
            result = _FakeResult()
            result.column_names = ["day", "score", "above_50"]
            result.result_rows = [(date(2024, 12, 31), 2.0, 1.0)]
            return result

    client = MeasureClient()
    result = universe_measure_series(
        _request()["spec"],
        aliases=["score", "above_50"],
        start_date="2024-12-01",
        end_date="2024-12-31",
        client=client,
    )

    assert result == {"score": [2.0], "above_50": [1.0]}
    assert "GROUP BY u.`date`" in client.sql
    assert "AAPL" not in client.sql
    assert client.parameters["start_date"] == "2024-12-01"
    assert client.parameters["end_date"] == "2024-12-31"


def test_universe_measure_series_rejects_unregistered_alias() -> None:
    from sigmarail.universe import UniverseRequestError, universe_measure_series

    with pytest.raises(UniverseRequestError, match="declared in spec.computed"):
        universe_measure_series(
            _request()["spec"],
            aliases=["arbitrary_sql"],
            start_date="2024-12-01",
            end_date="2024-12-31",
            client=_FakeClient(),
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda body: body["spec"].update(where_sql="close > 0"), "where_sql is unsupported"),
        (lambda body: body["spec"].update(spine="screener_estimates_daily"), "supports screener_price_tech_daily"),
        (lambda body: body["spec"].update(select=["not_a_core_field"]), "not registered"),
        (lambda body: body["spec"].update(limit_per_day=5001), "between 1 and 5000"),
    ],
)
def test_universe_adapter_rejects_unsupported_inputs(mutate, message: str) -> None:
    from sigmarail.universe import UniverseRequestError, _adapt_universe_request

    request = _request()
    mutate(request)
    with pytest.raises((UniverseRequestError, ValueError), match=message):
        _adapt_universe_request(request)


def test_lean_compatibility_routes_publish_registry_and_reject_unsafe_sql(monkeypatch) -> None:
    from django.test import Client
    from sigmarail import universe as universe_module

    client = Client()
    monkeypatch.setenv("SIGMARAIL_API_KEY", "test-secret")
    assert client.get("/v1/meta").status_code == 401
    assert client.get("/v1/meta", HTTP_X_API_KEY="test-secret").status_code == 200
    monkeypatch.delenv("SIGMARAIL_API_KEY")
    meta = client.get("/v1/meta")
    sources = client.get("/v1/schema/sources")
    source_fields = client.get("/v1/schema/sources/px/fields")
    unsafe = _request()
    unsafe["spec"]["where_sql"] = "close > 0"

    assert meta.status_code == 200
    assert meta.json()["dialect"]["id"] == "C-VERA-EXPR-V1"
    assert meta.json()["registry_digest"].startswith("sha256:")
    assert sources.status_code == 200
    assert {row["prefix"] for row in sources.json()["sources"]} >= {"px", "fd", "rt", "st", "ow"}
    assert source_fields.status_code == 200
    assert source_fields.json()["field_count"] > 0
    monkeypatch.setattr(
        universe_module,
        "query_dataset",
        lambda query, client=None, **kwargs: {
            "row_count": 1,
            "rows": [{"ticker": "AAPL", "date": "2024-12-31"}],
            "columns": ["ticker", "date"],
        },
    )
    successful = client.post("/v1/universe/run", _request(), content_type="application/json")
    rejected = client.post("/v1/universe/run", unsafe, content_type="application/json")
    assert successful.status_code == 200
    assert successful.json()["rows"][0]["ticker"] == "AAPL"
    assert rejected.status_code == 400
    assert "where_sql is unsupported" in rejected.json()["error"]


def test_lean_api_accepts_docker_host_header() -> None:
    """Containers reach a host-run local Studio API as host.docker.internal."""
    from django.test import Client

    response = Client(HTTP_HOST="host.docker.internal").get("/v1/meta")

    assert response.status_code == 200
    assert response.json()["dialect"]["id"] == "C-VERA-EXPR-V1"


@pytest.mark.integration
def test_lean_universe_reads_synthetic_rows_and_computed_values(global_client) -> None:
    from sigmarail.universe import universe_run

    request = _request()
    result = universe_run(request, client=global_client)

    assert "error" not in result, result
    assert result["row_count"] == 1
    assert result["rows"][0]["ticker"] == "AAPL"
    assert result["rows"][0]["above_50"] == 1
    assert result["rows"][0]["score"] == pytest.approx(result["rows"][0]["close"] / 50)
