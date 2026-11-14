from unittest.mock import patch

from screens.ch import get_ch_client


def test_studio_uses_sigmarail_database_client_factory():
    client = object()
    with patch("sigmarail.database.get_client", return_value=client) as get_client:
        assert get_ch_client() is client
    get_client.assert_called_once_with()
