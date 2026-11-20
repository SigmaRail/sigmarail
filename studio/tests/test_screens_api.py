"""API / adapter tests (mocked — no ClickHouse required)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from screens.adapter import ALL_SCREEN_PRESETS, list_screen_presets, preview_screen
from screens.ir_preview import list_field_values, list_screen_fields, load_template, preview_universe_ir


@pytest.mark.django_db
def test_health() -> None:
    c = Client()
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "sigmarail-studio"}


@pytest.mark.django_db
def test_presets_list_includes_equity() -> None:
    c = Client()
    resp = c.get("/api/screens/presets")
    assert resp.status_code == 200
    data = resp.json()
    ids = {p["id"] for p in data}
    assert "leaders" in ids
    assert "minervini_tt" in ids
    assert "canslim" in ids
    assert "high_rs" in ids
    labels = {p["id"]: p["label"] for p in data}
    assert labels["minervini_tt"] == "Minervini TT"
    assert labels["canslim"] == "CANSLIM"


def test_list_presets_helper() -> None:
    ids = {p["id"] for p in list_screen_presets()}
    assert "canslim" in ids
    assert "leaders" in ALL_SCREEN_PRESETS


@pytest.mark.django_db
def test_preview_unknown_preset_400() -> None:
    c = Client()
    resp = c.post(
        "/api/screens/preview",
        data={"as_of": "2026-08-21", "preset": "not_a_real_preset"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "unknown screen preset" in resp.json()["detail"]


def test_preview_unknown_preset_raises() -> None:
    class _C:
        def query(self, *a, **k):  # pragma: no cover
            raise AssertionError("should not query")

    with pytest.raises(ValueError, match="unknown screen preset"):
        preview_screen(_C(), as_of="2026-08-21", preset="not_a_real_preset")


_CORE_FIELDS = [
    {"name": "ticker", "prefix": "px", "table": "screener_price_tech_daily", "type": "String", "description": "Stock ticker symbol"},
    {"name": "date", "prefix": "px", "table": "screener_price_tech_daily", "type": "Date", "description": "Trading date"},
    {"name": "exchange", "prefix": "px", "table": "screener_price_tech_daily", "type": "LowCardinality(String)", "description": "Primary exchange (from reference data)"},
    {"name": "close", "prefix": "px", "table": "screener_price_tech_daily", "type": "Nullable(Float64)", "description": "Split-adjusted close"},
    {"name": "rs_rating", "prefix": "px", "table": "screener_price_tech_daily", "type": "UInt8", "description": "1-year RS percentile"},
    {"name": "overall_score", "prefix": "rt", "table": "screener_ratings_daily", "type": "Float64", "description": "Master composite score"},
    {"name": "sector", "prefix": "px", "table": "screener_price_tech_daily", "type": "String", "description": "Sector"},
    {"name": "industry", "prefix": "px", "table": "screener_price_tech_daily", "type": "String", "description": "Industry"},
]


def _patch_ch_schema():
    return patch("sigmarail.universe.field_catalog", return_value=list(_CORE_FIELDS))


def test_list_screen_fields_from_sigmarail_registry() -> None:
    with _patch_ch_schema():
        fields = list_screen_fields()
    names = {f["name"] for f in fields}
    expected = {row["name"] for row in _CORE_FIELDS}
    assert names == expected
    for f in fields:
        assert "name" in f and "label" in f and "category" in f
        assert f["category"] in {
            "technicals",
            "ratings",
            "fundamentals",
            "ownership",
            "other",
        }
    by_name = {f["name"]: f for f in fields}
    assert by_name["exchange"]["table"] == "screener_price_tech_daily"
    assert by_name["exchange"]["type"] == "LowCardinality(String)"
    assert by_name["exchange"]["description"] == "Primary exchange (from reference data)"
    assert not {"eps_cq_mean", "eps_ny_rev_pct_90d", "eps_last_surprise_pct"} & names


@pytest.mark.django_db
def test_fields_endpoint() -> None:
    c = Client()
    with _patch_ch_schema():
        resp = c.get("/api/screens/fields")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["fields"])
    names = {f["name"] for f in body["fields"]}
    assert "exchange" in names
    assert "sector" in names
    exchange = next(f for f in body["fields"] if f["name"] == "exchange")
    assert exchange["description"] == "Primary exchange (from reference data)"


def test_list_field_values_from_db() -> None:
    meta = {
        "exchange": {
            "table": "screener_price_tech_daily",
            "type": "LowCardinality(String)",
            "comment": "",
            "prefix": "px",
        },
        "close": {
            "table": "screener_price_tech_daily",
            "type": "Nullable(Float64)",
            "comment": "",
            "prefix": "px",
        },
    }
    client = MagicMock()
    client.query.return_value.result_rows = [("NASDAQ",), ("NYSE",), ("NYSEARCA",)]
    with (
        patch("screens.ir_preview._load_ch_column_meta", return_value=meta),
        patch("screens.ch.get_ch_client", return_value=client),
    ):
        vals = list_field_values("exchange", q="ny")
    assert vals == ["NASDAQ", "NYSE", "NYSEARCA"]
    sql = client.query.call_args[0][0]
    assert "screener_price_tech_daily" in sql
    assert "exchange" in sql
    with patch("screens.ir_preview._load_ch_column_meta", return_value=meta):
        assert list_field_values("close") == []
        with pytest.raises(ValueError, match="unknown field"):
            list_field_values("not_a_column")


@pytest.mark.django_db
def test_field_values_endpoint() -> None:
    c = Client()
    meta = {
        "exchange": {
            "table": "screener_price_tech_daily",
            "type": "LowCardinality(String)",
            "comment": "",
            "prefix": "px",
        }
    }
    client = MagicMock()
    client.query.return_value.result_rows = [("NYSE",)]
    with (
        patch("screens.ir_preview._load_ch_column_meta", return_value=meta),
        patch("screens.ch.get_ch_client", return_value=client),
    ):
        resp = c.get("/api/screens/fields/exchange/values?q=ny")
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"] == ["NYSE"]
    assert body["name"] == "exchange"


@pytest.mark.django_db
def test_preview_ir_missing_as_of_400() -> None:
    c = Client()
    resp = c.post(
        "/api/screens/preview-ir",
        data={"spec": {"version": 1}},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "as_of" in resp.json()["detail"]


@pytest.mark.django_db
def test_preview_ir_invalid_spec_400_no_ch() -> None:
    """Validation fails before ClickHouse connect."""
    c = Client()
    with patch("api.views.get_ch_client") as mock_ch:
        resp = c.post(
            "/api/screens/preview-ir",
            data={
                "as_of": "2026-08-21",
                "spec": {
                    "version": 1,
                    "from": "daily_screener",
                    "select": ["ticker"],
                    # missing where xor where_sql and order_by
                    "limit_per_day": 10,
                },
            },
            content_type="application/json",
        )
        assert resp.status_code == 400
        mock_ch.assert_not_called()


def _valid_min_spec() -> dict[str, Any]:
    return {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "overall_score"],
        "where": {
            "type": "gt",
            "left": {"type": "col", "name": "overall_score"},
            "right": {"type": "lit", "value": 70},
        },
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 10,
    }


def test_preview_universe_ir_happy_mocked() -> None:
    rows = [
        {"date": "2026-08-21", "ticker": "AAPL", "close": 200.0, "overall_score": 85.0},
        {"date": "2026-08-21", "ticker": "MSFT", "close": 400.0, "overall_score": 80.0},
    ]
    client = MagicMock()
    with (
        patch("sigmarail.universe.universe_run", return_value={"rows": rows, "row_count": 2}),
        patch("screens.ir_preview.enrich_rows_with_exchange", side_effect=lambda _client, data: data[0].update(exchange="NASDAQ")),
    ):
        out = preview_universe_ir(client, as_of="2026-08-21", spec_dict=_valid_min_spec())
    assert out["as_of"] == "2026-08-21"
    assert out["count"] == 2
    assert out["screen_ir"] == "universe_query_v1"
    assert out["rows"][0]["ticker"] == "AAPL"
    assert out["rows"][0]["overall_score"] == 85.0
    assert out["rows"][0]["exchange"] == "NASDAQ"
    assert out["spec"]["from"] == "daily_screener"
    assert "SELECT" in out["sql"]
    assert "params" in out and out["params"]["start_date"] == "2026-08-21"
    assert client.query.call_count == 0


@pytest.mark.django_db
def test_compile_sql_endpoint() -> None:
    c = Client()
    resp = c.post(
        "/api/screens/compile-sql",
        data={"spec": _valid_min_spec()},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "SELECT" in body["sql"]
    assert "params" in body
    assert body["params"]["start_date"] == "1970-01-01"
    assert body["params"]["end_date"] == "1970-01-01"


@pytest.mark.django_db
def test_preview_ir_endpoint_happy() -> None:
    rows = [{"date": "2026-08-21", "ticker": "NVDA", "close": 100.0, "overall_score": 90.0}]

    with (
        patch("api.views.get_ch_client", return_value=MagicMock()),
        patch("sigmarail.universe.universe_run", return_value={"rows": rows, "row_count": 1}),
        patch("screens.ir_preview.enrich_rows_with_exchange", side_effect=lambda _client, data: data[0].update(exchange="NASDAQ")),
    ):
        c = Client()
        resp = c.post(
            "/api/screens/preview-ir",
            data={"as_of": "2026-08-21", "spec": _valid_min_spec()},
            content_type="application/json",
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["rows"][0]["ticker"] == "NVDA"
    assert body["screen_ir"] == "universe_query_v1"


@pytest.mark.django_db
def test_templates_list_and_detail() -> None:
    c = Client()
    resp = c.get("/api/screens/templates")
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()["templates"]}
    assert "minervini" in ids

    detail = c.get("/api/screens/templates/minervini")
    assert detail.status_code == 200
    data = detail.json()
    assert data["spec"]["spine"] == "screener_price_tech_daily"
    assert data["spec"]["version"] == 2

    missing = c.get("/api/screens/templates/does_not_exist")
    assert missing.status_code == 404


def test_load_template_minervini() -> None:
    t = load_template("minervini_trend_template")
    spec = t["spec"]
    assert spec["order_by"][0]["field"] in ("rs_rating", "technical_rating")
    select = set(spec["select"])
    for col in (
        "technical_rating",
        "setup_quality_rating",
        "high_growth_momentum_rating",
        "sma200d_rising_30d",
        "avg_vol_50d",
        "high",
        "sma50d",
        "sma150d",
        "sma200d",
    ):
        assert col in select
    where_items = spec["where"]["items"]
    assert any(
        item.get("type") == "eq"
        and item.get("left", {}).get("name") == "sma200d_rising_30d"
        and item.get("right", {}).get("value") == 1
        for item in where_items
    )
    assert any(
        item.get("type") == "gte"
        and item.get("left", {}).get("name") == "high"
        and item.get("right", {}).get("type") == "formula"
        for item in where_items
    )
    assert any(
        item.get("type") == "gte"
        and item.get("left", {}).get("name") == "avg_vol_50d"
        and item.get("right", {}).get("value") == 100000
        for item in where_items
    )


@pytest.mark.django_db
def test_saved_screens_crud() -> None:
    c = Client()
    spec = _valid_min_spec()

    empty = c.get("/api/screens/saved")
    assert empty.status_code == 200
    initial_count = empty.json()["count"]

    created = c.post(
        "/api/screens/saved",
        data={"name": "Leaders IR", "spec": spec},
        content_type="application/json",
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["name"] == "Leaders IR"

    listed = c.get("/api/screens/saved")
    assert listed.json()["count"] == initial_count + 1

    got = c.get(f"/api/screens/saved/{sid}")
    assert got.status_code == 200
    assert got.json()["spec"]["limit_per_day"] == 10

    updated = c.put(
        f"/api/screens/saved/{sid}",
        data={"name": "Leaders IR v2", "spec": {**spec, "limit_per_day": 25}},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Leaders IR v2"
    assert updated.json()["spec"]["limit_per_day"] == 25

    conflict = c.post(
        "/api/screens/saved",
        data={"name": "Leaders IR v2", "spec": spec},
        content_type="application/json",
    )
    assert conflict.status_code == 409

    deleted = c.delete(f"/api/screens/saved/{sid}")
    assert deleted.status_code == 204
    assert c.get(f"/api/screens/saved/{sid}").status_code == 404


@pytest.mark.django_db
def test_screen_field_evaluate_distribution_and_latex() -> None:
    c = Client()
    mock_client = MagicMock()

    # Mock response for relative_strength query
    mock_res_row = MagicMock()
    mock_res_row.column_names = [
        "ticker", "date", "rs_rating", "yearly_performance", "performance_6m",
        "performance_3m", "performance_1m", "composite_performance", "momentum_rank"
    ]
    mock_res_row.result_rows = [
        ("NVDA", "2026-09-20", 88.5, 0.45, 0.25, 0.15, 0.05, 0.22, 120)
    ]

    mock_res_count = MagicMock()
    mock_res_count.result_rows = [(1500,)]

    # Mock response for distribution
    mock_res_dist = MagicMock()
    mock_res_dist.result_rows = [(1.0, 10.0, 25.0, 50.0, 75.0, 90.0, 99.0, 88.5)]

    mock_client.query.side_effect = [mock_res_row, mock_res_count, mock_res_dist]

    with patch("api.views.get_ch_client", return_value=mock_client):
        resp = c.get("/api/screens/fields/rs_rating/evaluate?ticker=NVDA&as_of_date=2026-09-20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "NVDA"
        assert data["field"] == "rs_rating"
        assert data["value"] == 88.5
        assert data["universe_size"] == 1500
        assert data["rank"] == 120
        assert data["cohort_percentile"] == 88.5
        assert data["distribution"]["median"] == 50.0
        assert data["distribution"]["p25"] == 25.0
        assert data["distribution"]["p75"] == 75.0
        assert "\\text{RS}" in data["substituted_latex"]
        assert "88.5" in data["substituted_latex"]
