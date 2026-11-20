"""Studio's core-data endpoints validate and delegate to SigmaRail contracts."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


def test_core_dataset_catalog_uses_sigma_rail_runtime() -> None:
    expected = {"module_id": "sigmarail.core", "count": 1, "datasets": []}
    with patch("sigmarail.query.list_datasets", return_value=expected):
        response = APIClient().get("/api/data/datasets")

    assert response.status_code == 200
    assert response.json() == expected


def test_core_dataset_detail_reports_unknown_dataset() -> None:
    with patch("sigmarail.query.describe_dataset", side_effect=ValueError("unknown dataset")):
        response = APIClient().get("/api/data/datasets/sigmarail.core.unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown dataset"


def test_core_query_rejects_invalid_contract_before_execution() -> None:
    with patch("sigmarail.query.query_dataset") as execute:
        response = APIClient().post("/api/data/query", {}, format="json")

    assert response.status_code == 400
    execute.assert_not_called()


def test_core_query_delegates_validated_request() -> None:
    payload = {
        "module_id": "sigmarail.core",
        "dataset_id": "sigmarail.core.screener_price_tech_daily",
        "select": [{"field_id": "sigmarail.field.screener_price_tech_daily.ticker.ticker"}],
        "as_of_date": "2024-12-31",
    }
    result = {"module_id": "sigmarail.core", "dataset_id": payload["dataset_id"], "rows": []}
    with (
        patch("sigmarail.query.compile_query", return_value=("SELECT 1", {})) as compile_query,
        patch("sigmarail.query.query_dataset", return_value=result) as execute,
    ):
        response = APIClient().post("/api/data/query", payload, format="json")

    assert response.status_code == 200
    assert response.json() == result
    compile_query.assert_called_once()
    execute.assert_called_once()


@pytest.mark.integration
def test_core_query_endpoint_uses_shared_synthetic_database(global_client) -> None:
    """The Studio API reads the same populated test DB used by core integration tests."""
    payload = {
        "module_id": "sigmarail.core",
        "dataset_id": "sigmarail.core.screener_price_tech_daily",
        "select": [
            {"field_id": "sigmarail.field.screener_price_tech_daily.ticker.ticker"},
            {"field_id": "sigmarail.field.screener_price_tech_daily.close.close"},
        ],
        "where": {
            "op": "eq",
            "field_id": "sigmarail.field.screener_price_tech_daily.ticker.ticker",
            "value": "AAPL",
        },
        "as_of_date": "2024-12-31",
        "limit": 10,
    }

    active_db = global_client.query("SELECT currentDatabase()").result_rows[0][0]
    assert active_db == "sigmarail_test"

    response = APIClient().post("/api/data/query", payload, format="json")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["dataset_id"] == payload["dataset_id"]
    assert body["row_count"] == 1
    assert body["rows"][0]["ticker"] == "AAPL"
