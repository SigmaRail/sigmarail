"""Unit tests for SFP incremental download key (split rewrite consistency)."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from sigmarail.load import DataLoader, get_incremental_download_params


def test_sfp_uses_lastupdated_like_sep():
    """SFP must incremental on lastupdated (parity with SEP).

    Trade-date filters miss (1) split restatements of older bars and
    (2) ticker remounts (e.g. BNY→BNY1) where lastupdated is bumped but
    date stays historical.
    """
    assert DataLoader.SHARADAR_TABLES['SFP']['date_field'] == 'lastupdated'
    assert DataLoader.SHARADAR_TABLES['SEP']['date_field'] == 'lastupdated'
    assert DataLoader.SHARADAR_TABLES['ACTIONS']['date_field'] == 'date'


@patch('sigmarail.load.get_client')
def test_sfp_incremental_params_use_lastupdated_gte(mock_get_client):
    mock_client = MagicMock()
    # max(lastupdated) in CH
    mock_client.query.return_value.result_rows = [(datetime(2026, 4, 19, 23, 59, 59),)]
    mock_get_client.return_value = mock_client

    params = get_incremental_download_params('SFP')

    assert params == {'lastupdated.gte': '2026-04-20'}
    query_sql = mock_client.query.call_args[0][0]
    assert 'max(lastupdated)' in query_sql
    assert 'sfp' in query_sql.lower()


@patch('sigmarail.load.get_client')
def test_sep_incremental_params_unchanged(mock_get_client):
    mock_client = MagicMock()
    mock_client.query.return_value.result_rows = [(date(2026, 4, 19),)]
    mock_get_client.return_value = mock_client

    params = get_incremental_download_params('SEP')

    assert params == {'lastupdated.gte': '2026-04-20'}


@patch('sigmarail.load.download_table_with_pagination')
@patch('sigmarail.load.get_sharadar_config')
@patch('sigmarail.load.get_data_config')
@patch('sigmarail.load.get_project_root')
@patch('sigmarail.load.get_client')
def test_tickers_download_pulls_stocks_and_funds(
    mock_get_client, mock_project_root, mock_data_cfg, mock_sharadar, mock_download, tmp_path
):
    """TICKERS load must fetch stocks+funds metadata (retail-native table values)."""
    import pandas as pd

    mock_get_client.return_value = MagicMock()
    mock_project_root.return_value = tmp_path
    mock_data_cfg.return_value = MagicMock(root='data')
    mock_sharadar.return_value = MagicMock(
        api_key='test-key', base_url='https://api.sharadar.com/v1.0'
    )

    def _fake_download(code, output_path, api_key, params=None, base_url=None):
        assert code == 'TICKERS'
        assert params is not None
        assert params['table'] in ('stocks', 'funds')
        retail_table = params['table']
        pd.DataFrame(
            {
                'table': [retail_table],
                'ticker': ['AAA' if retail_table == 'stocks' else 'BBB'],
                'permaticker': [1 if retail_table == 'stocks' else 2],
                'figi': [''],
                'lastupdated': ['2026-01-01'],
            }
        ).to_csv(output_path, index=False)
        return 1

    mock_download.side_effect = _fake_download

    loader = DataLoader()
    out, n, _ = loader.download_data(
        'TICKERS', start_date='2026-01-01', end_date='2026-01-01', incremental=False
    )

    assert n == 2
    assert mock_download.call_count == 2
    seen = {call.kwargs['params']['table'] for call in mock_download.call_args_list}
    assert seen == {'stocks', 'funds'}
    df = pd.read_csv(out)
    assert set(df['table']) == {'stocks', 'funds'}
