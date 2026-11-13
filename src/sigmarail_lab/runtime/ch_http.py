"""ClickHouse HTTP JSONEachRow client (stdlib only; testable without LEAN)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
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
    ) -> list[dict[str, Any]]:
        query_params = urlencode(
            {
                "database": self._settings.database,
                "default_format": "JSONEachRow",
                "max_result_rows": str(max_rows),
            }
        )
        url = f"http://{self._settings.host}:{self._settings.port}/?{query_params}"
        headers = {
            "X-ClickHouse-User": self._settings.user,
            "X-ClickHouse-Key": self._settings.password,
            "Content-Type": "text/plain; charset=utf-8",
        }
        req = Request(url, data=sql.encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
        except Exception as exc:
            if self._debug_log:
                self._debug_log(f"ClickHouse query error ({url[:80]} user={self._settings.user}): {exc}")
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
        return rows

    def query_one_json_row(
        self,
        sql: str,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        r = self.query_json_each_row(sql, max_rows=1, timeout=timeout)
        return r[0] if r else None
