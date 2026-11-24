"""Exercise the Alpaca extension schema and 65-minute view in test ClickHouse."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sigmarail.alpaca_schema import schema_path
from sigmarail.alpaca_bars import run_import
from sigmarail.database import _split_sql_statements


def test_alpaca_schema_import_and_65m_view(global_client) -> None:
    database = global_client.query("SELECT currentDatabase()").result_rows[0][0]
    assert database == "sigmarail_test", f"Refusing integration test against {database!r}"
    for statement in _split_sql_statements(schema_path().read_text(encoding="utf-8")):
        global_client.command(statement)

    ticker = f"ZZ{uuid4().hex[:10].upper()}"
    session_date = date(2026, 11, 6)
    start_utc = datetime(2026, 11, 6, 14, 30, tzinfo=timezone.utc)

    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def __init__(self, payload: object) -> None:
            self.payload = payload

        def json(self) -> object:
            return self.payload

    class FakeAlpaca:
        def get(self, url: str, *, headers, params, timeout):
            if url.endswith("/v2/calendar"):
                return Response([{"date": session_date.isoformat(), "open": "09:30", "close": "16:00"}])
            bars = []
            for index in range(78):
                timestamp = start_utc + timedelta(minutes=5 * index)
                price = 100.0 + index
                bars.append({
                    "t": timestamp.isoformat().replace("+00:00", "Z"),
                    "o": price, "h": price + 2, "l": price - 1, "c": price + 1,
                    "v": 10.0, "n": 1, "vw": price + 0.5,
                })
            return Response({"bars": {ticker: bars}})

    args = argparse.Namespace(
        session_date=None,
        start_date=session_date.isoformat(),
        end_date=session_date.isoformat(),
        last_minutes=None,
        symbols=[ticker],
        symbols_file=None,
        environment="paper",
        feed="iex",
        adjustment="raw",
        symbol_batch_size=200,
        request_interval_seconds=0,
        write=True,
    )
    summary = run_import(
        args,
        credentials={"api_key": "fixture-key", "api_secret": "fixture-secret"},
        client=global_client,
        session=FakeAlpaca(),
    )
    assert summary["bars_fetched"] == 78
    assert summary["bars_inserted"] == 78
    assert summary["calendar_rows_written"] == 1

    result = global_client.query(
        "SELECT bar_start_utc, bar_end_utc, observed_5m_bars, open, high, low, close, volume "
        "FROM ext_alpaca_price_65m WHERE ticker = {ticker:String} "
        "AND session_date = {session_date:Date} ORDER BY bar_start_utc",
        parameters={"ticker": ticker, "session_date": session_date},
    ).result_rows
    assert len(result) == 6
    assert [row[2] for row in result] == [13] * 6
    assert result[0][3:] == (100.0, 114.0, 99.0, 113.0, 130.0)
    # ClickHouse returns DateTime64 values without tzinfo; the stored timezone is UTC.
    assert result[-1][1] == (start_utc + timedelta(minutes=390)).replace(tzinfo=None)
