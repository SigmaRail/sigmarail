"""Bounded Alpaca five-minute bar retrieval for SigmaRail's Alpaca extension."""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

import requests

from sigmarail.config import create_shared_parser, process_shared_args
from sigmarail.credentials import CredentialStoreError, get_studio_alpaca_credentials
from sigmarail.database import get_client

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
PRICE_TABLE = "ext_alpaca_price"
CALENDAR_TABLE = "ext_alpaca_market_calendar"
PRICE_COLUMNS = (
    "ticker", "timestamp_utc", "session_date", "open", "high", "low", "close",
    "volume", "trade_count", "vwap", "feed", "adjustment", "ingested_at",
)
CALENDAR_COLUMNS = ("session_date", "session_open_utc", "session_close_utc", "ingested_at")
PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
LIVE_TRADING_URL = "https://api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"


class AlpacaImportError(RuntimeError):
    """A safe, actionable failure from Alpaca retrieval or import."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def regular_session_window(
    session_date: date,
    *,
    market_open: str = "09:30",
    market_close: str = "16:00",
    last_minutes: Optional[int] = 65,
) -> tuple[datetime, datetime]:
    """Return a UTC regular-session window, honoring New York DST/early closes."""
    if last_minutes is not None and last_minutes <= 0:
        raise ValueError("last_minutes must be positive")
    open_h, open_m = (int(part) for part in market_open.split(":"))
    close_h, close_m = (int(part) for part in market_close.split(":"))
    open_local = datetime.combine(session_date, wall_time(open_h, open_m), tzinfo=NY)
    close_local = datetime.combine(session_date, wall_time(close_h, close_m), tzinfo=NY)
    start_local = close_local - timedelta(minutes=last_minutes) if last_minutes is not None else open_local
    if close_local <= open_local or start_local < open_local:
        raise ValueError("requested window is outside the regular market session")
    return start_local.astimezone(UTC), close_local.astimezone(UTC)


def _headers(credentials: dict[str, str]) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": credentials["api_key"],
        "APCA-API-SECRET-KEY": credentials["api_secret"],
        "Accept": "application/json",
    }


def fetch_market_calendar(
    *,
    start_date: date,
    end_date: date,
    credentials: dict[str, str],
    environment: str = "paper",
    session: Any = None,
) -> list[tuple[date, str, str]]:
    """Read the official Alpaca market calendar, including shortened sessions."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if environment not in {"paper", "live"}:
        raise ValueError("environment must be 'paper' or 'live'")
    http = session or requests
    base_url = PAPER_TRADING_URL if environment == "paper" else LIVE_TRADING_URL
    try:
        response = http.get(
            f"{base_url}/v2/calendar",
            headers=_headers(credentials),
            params={"start": start_date.isoformat(), "end": end_date.isoformat(), "date_type": "TRADING"},
            timeout=45,
        )
    except requests.RequestException as exc:
        raise AlpacaImportError("Alpaca market-calendar request failed") from exc
    if response.status_code in (401, 403):
        raise AlpacaImportError("Alpaca rejected the saved profile credentials for this environment")
    if response.status_code >= 400:
        raise AlpacaImportError(f"Alpaca market-calendar request failed (HTTP {response.status_code})")
    payload = response.json()
    if not isinstance(payload, list):
        raise AlpacaImportError("Alpaca market-calendar response was not a list")
    sessions: list[tuple[date, str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or not all(item.get(key) for key in ("date", "open", "close")):
            raise AlpacaImportError("Alpaca market-calendar entry is missing date/open/close")
        day = date.fromisoformat(str(item["date"]))
        if start_date <= day <= end_date:
            sessions.append((day, str(item["open"]), str(item["close"])))
    return sorted(sessions)


def market_calendar_rows(
    sessions: Sequence[tuple[date, str, str]], *, ingested_at: Optional[datetime] = None
) -> list[tuple[Any, ...]]:
    imported_at = (ingested_at or _utc_now()).astimezone(UTC)
    rows = []
    for session_date, market_open, market_close in sessions:
        open_h, open_m = (int(part) for part in market_open.split(":"))
        close_h, close_m = (int(part) for part in market_close.split(":"))
        open_local = datetime.combine(session_date, wall_time(open_h, open_m), tzinfo=NY)
        close_local = datetime.combine(session_date, wall_time(close_h, close_m), tzinfo=NY)
        if close_local <= open_local:
            raise ValueError(f"invalid market session hours for {session_date}")
        rows.append((session_date, open_local.astimezone(UTC), close_local.astimezone(UTC), imported_at))
    return rows


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Alpaca timestamp lacks timezone: {value!r}")
    return parsed.astimezone(UTC)


def parse_bars(
    payload: dict[str, Any],
    *,
    start_utc: datetime,
    end_utc: datetime,
    feed: str,
    adjustment: str,
    ingested_at: Optional[datetime] = None,
) -> list[tuple[Any, ...]]:
    """Normalize Alpaca's multi-symbol response to extension-table rows."""
    imported_at = (ingested_at or _utc_now()).astimezone(UTC)
    bars_by_symbol = payload.get("bars") or {}
    if not isinstance(bars_by_symbol, dict):
        raise AlpacaImportError("Alpaca response 'bars' was not a symbol-to-bars object")
    rows: list[tuple[Any, ...]] = []
    for symbol, bars in bars_by_symbol.items():
        if not isinstance(bars, list):
            raise AlpacaImportError(f"Alpaca bars for {symbol} were not a list")
        for bar in bars:
            timestamp = _parse_timestamp(str(bar["t"]))
            if not (start_utc <= timestamp < end_utc):
                continue
            session_date = timestamp.astimezone(NY).date()
            count = bar.get("n")
            rows.append((
                str(symbol).upper(), timestamp, session_date,
                float(bar["o"]), float(bar["h"]), float(bar["l"]), float(bar["c"]),
                float(bar["v"]), int(count) if count is not None else None,
                float(bar["vw"]) if bar.get("vw") is not None else None,
                feed, adjustment, imported_at,
            ))
    return rows


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_bars(
    *,
    symbols: Sequence[str],
    start_utc: datetime,
    end_utc: datetime,
    credentials: dict[str, str],
    feed: str = "iex",
    adjustment: str = "raw",
    symbol_batch_size: int = 200,
    request_interval_seconds: float = 0.25,
    max_retries: int = 5,
    session: Any = None,
) -> tuple[list[tuple[Any, ...]], int]:
    """Fetch a bounded multi-symbol 5-minute interval with pagination/retries."""
    if not symbols:
        raise ValueError("provide at least one symbol; current Alpaca assets are not used as a historical universe")
    if feed not in {"sip", "iex"}:
        raise ValueError("feed must be 'sip' or 'iex'")
    if adjustment not in {"raw", "split", "dividend", "spin-off", "all"}:
        raise ValueError("unsupported Alpaca adjustment mode")
    if not 1 <= symbol_batch_size <= 500:
        raise ValueError("symbol_batch_size must be between 1 and 500")
    http = session or requests.Session()
    headers = _headers(credentials)
    base_params: dict[str, Any] = {
        "timeframe": "5Min",
        "start": start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "end": end_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "limit": 10000,
        "feed": feed,
        "adjustment": adjustment,
        "sort": "asc",
    }
    rows: list[tuple[Any, ...]] = []
    request_count = 0
    try:
        for symbol_group in _chunks(list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip())), symbol_batch_size):
            if not symbol_group:
                continue
            params = {**base_params, "symbols": ",".join(symbol_group)}
            while True:
                attempt = 0
                while True:
                    if request_count and request_interval_seconds:
                        time.sleep(request_interval_seconds)
                    try:
                        response = http.get(
                            f"{DATA_URL}/v2/stocks/bars", headers=headers,
                            params=params, timeout=45,
                        )
                    except requests.RequestException as exc:
                        if attempt >= max_retries:
                            raise AlpacaImportError("Alpaca bar request failed after retries") from exc
                        time.sleep(min(2**attempt, 30))
                        attempt += 1
                        continue
                    request_count += 1
                    if response.status_code in (401, 403):
                        raise AlpacaImportError("Alpaca rejected the saved profile credentials for market data")
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt >= max_retries:
                            raise AlpacaImportError(f"Alpaca bar request failed after retries (HTTP {response.status_code})")
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = float(retry_after) if retry_after else min(2**attempt, 30)
                        except ValueError:
                            delay = min(2**attempt, 30)
                        time.sleep(max(0.5, delay))
                        attempt += 1
                        continue
                    if response.status_code >= 400:
                        raise AlpacaImportError(f"Alpaca bar request failed (HTTP {response.status_code})")
                    break
                payload = response.json()
                rows.extend(parse_bars(
                    payload, start_utc=start_utc, end_utc=end_utc,
                    feed=feed, adjustment=adjustment,
                ))
                page_token = payload.get("next_page_token")
                if not page_token:
                    break
                params["page_token"] = page_token
    finally:
        if session is None:
            http.close()
    return rows, request_count


def insert_rows(client: Any, rows: Sequence[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    client.insert(PRICE_TABLE, list(rows), column_names=list(PRICE_COLUMNS))
    return len(rows)


def insert_market_calendar(client: Any, sessions: Sequence[tuple[date, str, str]]) -> int:
    rows = market_calendar_rows(sessions)
    if not rows:
        return 0
    client.insert(CALENDAR_TABLE, rows, column_names=list(CALENDAR_COLUMNS))
    return len(rows)


def _symbols(args: argparse.Namespace) -> list[str]:
    result: list[str] = []
    if args.symbols:
        result.extend(args.symbols)
    if args.symbols_file:
        result.extend(Path(args.symbols_file).read_text(encoding="utf-8").splitlines())
    normalized = list(dict.fromkeys(
        symbol.strip().upper()
        for raw in result
        for symbol in raw.split(",")
        if symbol.strip() and not symbol.lstrip().startswith("#")
    ))
    if not normalized:
        raise ValueError("pass --symbols or --symbols-file; the importer will not infer a current-day universe")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch bounded Alpaca 5-minute bars into SigmaRail's ext_alpaca_* tables.",
        parents=[create_shared_parser()],
    )
    dates = parser.add_mutually_exclusive_group(required=True)
    dates.add_argument("--session-date", help="One US market session date (YYYY-MM-DD)")
    dates.add_argument("--start-date", help="Inclusive first market-session date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Inclusive final date; required with --start-date")
    parser.add_argument("--last-minutes", type=int, help="Window ending at each session close; default is 65 minutes for --session-date, full sessions for a range")
    parser.add_argument("--symbols", nargs="+", help="Explicit ticker(s), comma-separated or repeated")
    parser.add_argument("--symbols-file", help="UTF-8 file with one ticker or comma-separated tickers per line")
    parser.add_argument("--studio-profile-id", required=True, help="UUID of a saved Alpaca account profile in SigmaRail Studio; secrets are read from the OS credential vault")
    parser.add_argument("--environment", choices=("paper", "live"), required=True, help="Environment of the selected Studio Alpaca profile; used only for the read-only calendar endpoint")
    parser.add_argument("--feed", choices=("sip", "iex"), default="iex")
    parser.add_argument("--adjustment", choices=("raw", "split", "dividend", "spin-off", "all"), default="raw")
    parser.add_argument("--symbol-batch-size", type=int, default=200)
    parser.add_argument("--request-interval-seconds", type=float, default=0.25)
    parser.add_argument("--write", action="store_true", help="Insert fetched bars into the selected ClickHouse database; default only fetches and reports")
    return parser


def _date_range(args: argparse.Namespace) -> tuple[date, date, Optional[int]]:
    if args.session_date:
        day = date.fromisoformat(args.session_date)
        return day, day, 65 if args.last_minutes is None else args.last_minutes
    if not args.end_date:
        raise ValueError("pass --end-date with --start-date")
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        raise ValueError("--start-date must be on or before --end-date")
    return start, end, args.last_minutes


def run_import(args: argparse.Namespace, *, credentials: dict[str, str], client: Any = None, session: Any = None) -> dict[str, int]:
    """Fetch requested sessions and optionally insert rows; injectable for tests."""
    start_date, end_date, minutes = _date_range(args)
    symbols = _symbols(args)
    sessions = fetch_market_calendar(
        start_date=start_date, end_date=end_date, credentials=credentials,
        environment=args.environment, session=session,
    )
    if not sessions:
        raise AlpacaImportError("Alpaca returned no trading sessions for the requested dates")
    calendar_written = 0
    if args.write:
        if client is None:
            raise ValueError("a ClickHouse client is required when --write is set")
        calendar_written = insert_market_calendar(client, sessions)

    rows_fetched = 0
    requests_made = 0
    rows_inserted = 0
    for session_date, market_open, market_close in sessions:
        start_utc, end_utc = regular_session_window(
            session_date, market_open=market_open, market_close=market_close,
            last_minutes=minutes,
        )
        rows, calls = fetch_bars(
            symbols=symbols, start_utc=start_utc, end_utc=end_utc,
            credentials=credentials, feed=args.feed, adjustment=args.adjustment,
            symbol_batch_size=args.symbol_batch_size,
            request_interval_seconds=args.request_interval_seconds, session=session,
        )
        rows_fetched += len(rows)
        requests_made += calls
        if args.write:
            rows_inserted += insert_rows(client, rows)
        print(
            f"session={session_date} symbols={len(symbols)} fetched_bars={len(rows)} "
            f"window={start_utc.isoformat()}..{end_utc.isoformat()}"
        )
    return {
        "sessions": len(sessions), "symbols": len(symbols), "bars_fetched": rows_fetched,
        "bars_inserted": rows_inserted, "calendar_rows_written": calendar_written,
        "requests": requests_made,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    process_shared_args(args)
    if bool(args.start_date) != bool(args.end_date):
        parser.error("pass both --start-date and --end-date for a date range")
    try:
        credentials = get_studio_alpaca_credentials(args.studio_profile_id)
        if not credentials:
            raise CredentialStoreError("No Alpaca credentials are saved for this Studio profile in the OS vault")
        client = get_client() if args.write else None
        try:
            result = run_import(args, credentials=credentials, client=client)
        finally:
            if client is not None:
                client.close()
    except (ValueError, CredentialStoreError, AlpacaImportError) as exc:
        parser.exit(2, f"error: {exc}\n")
    mode = "inserted" if args.write else "dry-run"
    print(f"mode={mode} database_write={'yes' if args.write else 'no'} {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
