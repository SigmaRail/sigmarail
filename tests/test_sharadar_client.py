"""Unit tests for Sharadar retail client helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from sigmarail.config import normalize_sharadar_base_url
from sigmarail.sharadar_client import api_table_name, download_table_with_pagination


def test_normalize_sharadar_base_url_rewrites_v2():
    assert normalize_sharadar_base_url("https://api.sharadar.com/v2") == (
        "https://api.sharadar.com/v1.0"
    )
    assert normalize_sharadar_base_url("https://api.sharadar.com/v1.0/") == (
        "https://api.sharadar.com/v1.0"
    )


def test_api_table_name_normalizes_internal_codes():
    assert api_table_name("SHARADAR/SEP") == "SEP"
    assert api_table_name("SFP") == "SFP"
    assert api_table_name("TICKERS") == "TICKERS"


@patch("sigmarail.sharadar_client.requests.get")
def test_download_pagination_writes_retail_rows_unchanged(mock_get, tmp_path):
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json.return_value = {
        "count": 2,
        "data": [
            {
                "ticker": "AAPL",
                "date": "2026-08-01",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 10,
                "closeadj": 1.0,
                "closeunadj": 1.0,
                "lastupdated": "2026-08-01",
            },
            {
                "ticker": "AAPL",
                "date": "2026-08-02",
                "open": 2.0,
                "high": 2.0,
                "low": 2.0,
                "close": 2.0,
                "volume": 20,
                "closeadj": 2.0,
                "closeunadj": 2.0,
                "lastupdated": "2026-08-02",
            },
        ],
    }
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json.return_value = {"count": 0, "data": []}
    mock_get.side_effect = [page1, page2]

    out = tmp_path / "SHARADAR_SEP.csv"
    n = download_table_with_pagination(
        "SEP",
        out,
        api_key="test-key",
        params={"lastupdated.gte": "2026-08-01"},
        base_url="https://api.sharadar.com/v1.0",
        page_limit=2,
    )
    assert n == 2
    df = pd.read_csv(out)
    assert len(df) == 2
    assert df.iloc[0]["ticker"] == "AAPL"
    called_url = mock_get.call_args_list[0][0][0]
    assert called_url == "https://api.sharadar.com/v1.0/data/SEP"
    assert "data.nasdaq.com" not in called_url


@patch("sigmarail.sharadar_client.requests.get")
def test_download_tickers_preserves_retail_table_values(mock_get, tmp_path):
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json.return_value = {
        "count": 1,
        "data": [
            {
                "table": "stocks",
                "permaticker": "1",
                "ticker": "AAPL",
                "name": "Apple",
                "figi": "BBG000",
            }
        ],
    }
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json.return_value = {"count": 0, "data": []}
    mock_get.side_effect = [page1, page2]

    out = tmp_path / "SHARADAR_TICKERS.csv"
    n = download_table_with_pagination(
        "TICKERS",
        out,
        api_key="test-key",
        params={"table": "stocks"},
        base_url="https://api.sharadar.com/v1.0",
    )
    assert n == 1
    df = pd.read_csv(out)
    assert df.iloc[0]["table"] == "stocks"
    assert "figi" in df.columns
