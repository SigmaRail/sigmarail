from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json

import pytest

from sigmarail import alpaca_bars
from sigmarail import credentials as credential_store


UTC = timezone.utc


def _bar(ts: datetime, *, offset: int = 0) -> dict[str, object]:
    return {
        "t": ts.isoformat().replace("+00:00", "Z"),
        "o": 100 + offset,
        "h": 102 + offset,
        "l": 99 + offset,
        "c": 101 + offset,
        "v": 1000 + offset,
        "n": 12,
        "vw": 100.5 + offset,
    }


def test_profile_credentials_read_only_from_studio_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    profile_id = "d67b619c-6947-4401-88a9-9880d5165c5e"

    class FakeKeyring:
        def get_password(self, service: str, account: str) -> str:
            assert service == f"sigmarail-studio/broker/{profile_id}"
            assert account == "credentials"
            return json.dumps({"alpaca-api-key": "key-value", "alpaca-api-secret": "secret-value"})

    monkeypatch.setattr(credential_store, "_keyring", lambda: FakeKeyring())
    assert credential_store.get_studio_alpaca_credentials(profile_id) == {
        "api_key": "key-value",
        "api_secret": "secret-value",
    }


def test_studio_profile_id_must_be_uuid() -> None:
    with pytest.raises(ValueError, match="UUID"):
        credential_store.get_studio_alpaca_credentials("not-a-profile")


def test_empty_credentials_profile_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKeyring:
        def get_password(self, service: str, account: str) -> None:
            return None

    monkeypatch.setattr(credential_store, "_keyring", lambda: FakeKeyring())
    assert credential_store.get_studio_alpaca_credentials("d67b619c-6947-4401-88a9-9880d5165c5e") is None


def test_session_window_handles_dst_and_last_65_minutes() -> None:
    start, end = alpaca_bars.regular_session_window(date(2026, 11, 6), last_minutes=65)
    assert start == datetime(2026, 11, 6, 19, 55, tzinfo=UTC)
    assert end == datetime(2026, 11, 6, 21, 0, tzinfo=UTC)


def test_market_calendar_uses_selected_paper_endpoint_and_returns_early_close() -> None:
    class Response:
        status_code = 200

        def json(self) -> list[dict[str, str]]:
            return [{"date": "2026-11-27", "open": "09:30", "close": "13:00"}]

    class Session:
        def get(self, url: str, *, headers, params, timeout):
            assert url == "https://paper-api.alpaca.markets/v2/calendar"
            assert params["start"] == "2026-11-27"
            assert headers["APCA-API-KEY-ID"] == "key-value"
            return Response()

    result = alpaca_bars.fetch_market_calendar(
        start_date=date(2026, 11, 27), end_date=date(2026, 11, 27),
        credentials={"api_key": "key-value", "api_secret": "secret-value"},
        session=Session(),
    )
    assert result == [(date(2026, 11, 27), "09:30", "13:00")]


def test_calendar_rows_convert_dst_hours_to_utc() -> None:
    rows = alpaca_bars.market_calendar_rows([
        (date(2026, 10, 30), "09:30", "16:00"),
        (date(2026, 11, 2), "09:30", "16:00"),
    ])
    assert rows[0][1:3] == (datetime(2026, 10, 30, 13, 30, tzinfo=UTC), datetime(2026, 10, 30, 20, 0, tzinfo=UTC))
    assert rows[1][1:3] == (datetime(2026, 11, 2, 14, 30, tzinfo=UTC), datetime(2026, 11, 2, 21, 0, tzinfo=UTC))


def test_parse_bars_keeps_only_requested_half_open_window() -> None:
    start = datetime(2026, 11, 6, 19, 55, tzinfo=UTC)
    end = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
    payload = {"bars": {"SPY": [
        _bar(start - timedelta(minutes=5)), _bar(start),
        _bar(end - timedelta(minutes=5)), _bar(end),
    ]}}
    rows = alpaca_bars.parse_bars(payload, start_utc=start, end_utc=end, feed="iex", adjustment="raw")
    assert len(rows) == 2
    assert [row[1] for row in rows] == [start, end - timedelta(minutes=5)]
    assert rows[0][0] == "SPY"
    assert rows[0][10:12] == ("iex", "raw")


def test_fetch_bars_uses_explicit_universe_and_follows_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 11, 6, 19, 55, tzinfo=UTC)
    end = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def json(self) -> dict[str, object]:
            return self.payload

    class Session:
        def get(self, url: str, *, headers, params, timeout):
            calls.append(dict(params))
            ts = start + timedelta(minutes=5 * (len(calls) - 1))
            payload: dict[str, object] = {"bars": {"SPY": [_bar(ts)]}}
            if len(calls) == 1:
                payload["next_page_token"] = "page-2"
            return Response(payload)

    monkeypatch.setattr(alpaca_bars.time, "sleep", lambda _: None)
    rows, n_requests = alpaca_bars.fetch_bars(
        symbols=["SPY"], start_utc=start, end_utc=end,
        credentials={"api_key": "key-value", "api_secret": "secret-value"},
        session=Session(), request_interval_seconds=0,
    )
    assert n_requests == 2
    assert len(rows) == 2
    assert calls[0]["symbols"] == "SPY"
    assert "page_token" not in calls[0]
    assert calls[1]["page_token"] == "page-2"


def test_fetch_bars_requires_explicit_universe() -> None:
    with pytest.raises(ValueError, match="explicit ticker|at least one symbol"):
        alpaca_bars.fetch_bars(
            symbols=[], start_utc=datetime(2026, 1, 2, tzinfo=UTC),
            end_utc=datetime(2026, 1, 2, 1, tzinfo=UTC),
            credentials={"api_key": "key", "api_secret": "secret"},
        )


def test_insert_uses_extension_namespace_and_explicit_columns() -> None:
    class Client:
        calls: list[tuple[object, ...]] = []

        def insert(self, table, rows, *, column_names) -> None:
            self.calls.append((table, rows, column_names))

    client = Client()
    row = ("SPY", datetime(2026, 11, 6, 19, 55, tzinfo=UTC), date(2026, 11, 6), 1, 2, 0, 1, 12, 1, 1, "iex", "raw", datetime.now(UTC))
    assert alpaca_bars.insert_rows(client, [row]) == 1
    assert client.calls[0][0] == "ext_alpaca_price"
    assert client.calls[0][2] == list(alpaca_bars.PRICE_COLUMNS)


def test_market_calendar_insert_uses_extension_namespace() -> None:
    class Client:
        calls: list[tuple[object, ...]] = []

        def insert(self, table, rows, *, column_names) -> None:
            self.calls.append((table, rows, column_names))

    client = Client()
    sessions = [(date(2026, 11, 6), "09:30", "16:00")]
    assert alpaca_bars.insert_market_calendar(client, sessions) == 1
    assert client.calls[0][0] == "ext_alpaca_market_calendar"


def test_schema_is_three_extension_objects() -> None:
    from sigmarail.alpaca_schema import schema_path
    from sigmarail.database import _split_sql_statements

    statements = _split_sql_statements(schema_path().read_text(encoding="utf-8"))
    assert len(statements) == 3
    assert "CREATE TABLE IF NOT EXISTS ext_alpaca_price" in statements[0]
    assert "CREATE TABLE IF NOT EXISTS ext_alpaca_market_calendar" in statements[1]
    assert "CREATE VIEW IF NOT EXISTS ext_alpaca_price_65m" in statements[2]
