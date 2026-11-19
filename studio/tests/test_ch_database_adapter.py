from unittest.mock import patch

from screens.ch import get_ch_client


def test_studio_uses_sigmarail_database_client_factory():
    client = object()
    config = type(
        "DatabaseConfig",
        (),
        {
            "host": "clickhouse.local",
            "http_port": 8123,
            "user": "reader",
            "password": "secret",
            "database": "sigmarail",
            "connect_timeout": 10,
            "send_receive_timeout": 20,
        },
    )()
    with (
        patch("sigmarail.config.get_database_config", return_value=config),
        patch("clickhouse_connect.get_client", return_value=client) as create_client,
    ):
        assert get_ch_client() is client
    assert create_client.call_args.kwargs == {
        "host": "clickhouse.local",
        "port": 8123,
        "username": "reader",
        "password": "secret",
        "database": "sigmarail",
        "connect_timeout": 10,
        "send_receive_timeout": 20,
        "settings": {"readonly": 2},
    }
