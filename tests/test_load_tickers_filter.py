"""Unit tests for sigmarail-load --tickers Sharadar filter."""

from unittest.mock import MagicMock, patch

import pandas as pd

from sigmarail.load import DataLoader, parse_ticker_list, _ticker_slug


def test_parse_ticker_list_comma_and_repeat():
    assert parse_ticker_list(["IESC", "sfbs,iesc"]) == ["IESC", "SFBS"]


def test_ticker_slug_single_and_many():
    assert _ticker_slug(["IESC"]) == "IESC"
    assert _ticker_slug(["A", "B", "C", "D"]) == "A_B_C_x4"


@patch("sigmarail.load.download_table_with_pagination")
@patch("sigmarail.load.get_sharadar_config")
@patch("sigmarail.load.get_data_config")
@patch("sigmarail.load.get_project_root")
@patch("sigmarail.load.get_client")
def test_sep_download_passes_ticker_param(
    mock_get_client,
    mock_project_root,
    mock_data_cfg,
    mock_sharadar,
    mock_download,
    tmp_path,
):
    mock_get_client.return_value = MagicMock()
    mock_project_root.return_value = tmp_path
    mock_data_cfg.return_value = MagicMock(root="data")
    mock_sharadar.return_value = MagicMock(
        api_key="test-key", base_url="https://api.sharadar.com/v1.0"
    )

    def _fake_download(code, output_path, api_key, params=None, base_url=None):
        assert params is not None
        assert params["ticker"] == "IESC"
        assert params["lastupdated.gte"] == "2026-08-24"
        pd.DataFrame(
            {
                "ticker": ["IESC"],
                "date": ["2026-08-26"],
                "lastupdated": ["2026-08-27"],
                "close": [331.48],
                "closeadj": [331.48],
                "closeunadj": [331.48],
            }
        ).to_csv(output_path, index=False)
        return 1

    mock_download.side_effect = _fake_download

    loader = DataLoader()
    out, n, _ = loader.download_data(
        "SEP",
        start_date="2026-08-24",
        end_date="2026-08-27",
        incremental=False,
        tickers=["IESC"],
    )

    assert n == 1
    assert out.name == "SHARADAR_SEP_IESC_2026-08-24_to_2026-08-27.csv"
    mock_download.assert_called_once()


@patch("sigmarail.load.download_table_with_pagination")
@patch("sigmarail.load.get_sharadar_config")
@patch("sigmarail.load.get_data_config")
@patch("sigmarail.load.get_project_root")
@patch("sigmarail.load.get_client")
def test_years_ignored_when_tickers_set(
    mock_get_client,
    mock_project_root,
    mock_data_cfg,
    mock_sharadar,
    mock_download,
    tmp_path,
):
    mock_get_client.return_value = MagicMock()
    mock_project_root.return_value = tmp_path
    mock_data_cfg.return_value = MagicMock(root="data")
    mock_sharadar.return_value = MagicMock(
        api_key="test-key", base_url="https://api.sharadar.com/v1.0"
    )
    mock_download.return_value = 0
    mock_download.side_effect = lambda **kwargs: (
        pd.DataFrame({"ticker": [kwargs["params"]["ticker"]]}).to_csv(
            kwargs["output_path"], index=False
        )
        or 1
    )

    loader = DataLoader()
    loader.download_data(
        "SEP",
        incremental=False,
        years="5",
        tickers=["IESC", "SFBS"],
    )

    assert mock_download.call_count == 2
    seen = {c.kwargs["params"]["ticker"] for c in mock_download.call_args_list}
    assert seen == {"IESC", "SFBS"}
