"""ClickHouse HTTP JSONEachRow client (stdlib only; testable without LEAN)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChHttpSettings:
    host: str
    port: str
    database: str
    user: str
    password: str


DebugLog = Callable[[str], None] | None


class ChHttpClient:
    """POST SQL to ClickHouse HTTP interface; parse JSONEachRow lines."""

    def __init__(self, settings: ChHttpSettings, debug_log: DebugLog = None):
        self._settings = settings
        self._debug_log = debug_log

    def query_json_each_row(
        self,
        sql: str,
        max_rows: int = 100_000,
        timeout: float = 30.0,
        *,
        fail_on_error: bool = False,
    ) -> list[dict[str, Any]]:
        query_params = urlencode(
            {
                "database": self._settings.database,
                "default_format": "JSONEachRow",
                "max_result_rows": str(max_rows),
                "result_overflow_mode": "throw",
            }
        )
        url = f"http://{self._settings.host}:{self._settings.port}/?{query_params}"
        headers = {
            "X-ClickHouse-User": self._settings.user,
            "X-ClickHouse-Key": self._settings.password,
            "Content-Type": "text/plain; charset=utf-8",
        }
        req = Request(url, data=sql.encode("utf-8"), headers=headers, method="POST")
        payload = None
        # Backtest containers can open many ClickHouse connections at startup.
        # A brief host/network refusal must not silently turn an entire point-in-
        # time regime series into an empty cache (which then correctly fails
        # closed and produces a misleading zero-trade run).
        retry_delays = (0.25, 0.75, 1.5)
        last_error: Exception | None = None
        for attempt in range(len(retry_delays) + 1):
            try:
                with urlopen(req, timeout=timeout) as resp:
                    payload = resp.read().decode("utf-8")
                break
            except HTTPError as exc:
                # ClickHouse received the request and rejected the SQL/auth;
                # retrying that response cannot repair it.
                if self._debug_log:
                    self._debug_log(f"ClickHouse query error ({url[:80]} user={self._settings.user}): {exc}")
                if fail_on_error:
                    raise RuntimeError(
                        f"ClickHouse rejected the feature query (HTTP {exc.code})"
                    ) from exc
                return []
            except (URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                if attempt < len(retry_delays):
                    time.sleep(retry_delays[attempt])
                    continue
                if self._debug_log:
                    self._debug_log(f"ClickHouse query error ({url[:80]} user={self._settings.user}): {exc}")
                if fail_on_error:
                    raise RuntimeError("ClickHouse feature query failed after retries") from exc
                return []

        if payload is None:
            if self._debug_log and last_error is not None:
                self._debug_log(f"ClickHouse query error ({url[:80]} user={self._settings.user}): {last_error}")
            if fail_on_error:
                raise RuntimeError("ClickHouse feature query returned no response")
            return []

        rows: list[dict[str, Any]] = []
        parse_errors = 0
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                parse_errors += 1
        if parse_errors and self._debug_log:
            self._debug_log(f"ClickHouse parse errors={parse_errors} first_bytes={payload[:200]!r}")
        if fail_on_error and parse_errors:
            raise RuntimeError(f"ClickHouse feature query returned {parse_errors} malformed row(s)")
        return rows

    def query_one_json_row(
        self,
        sql: str,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        r = self.query_json_each_row(sql, max_rows=1, timeout=timeout)
        return r[0] if r else None
