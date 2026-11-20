"""HTTP client for the Vera query service — **fail-closed**.

Every transport/HTTP/JSON failure raises :class:`SigmaRailApiError` instead of returning
``None``. That matters: a swallowed failure used to look like an ordinary empty
result, so a backtest could record **0 orders** and still be read as a strategy
outcome. Callers that want to tolerate a failure must say so explicitly.

Also exposes the compatibility handshake (``C-API-SURFACE-V1``):

* :meth:`SigmaRailApiClient.meta` — dialect id/version + ``registry_digest``
* :meth:`SigmaRailApiClient.require_dialect` — raise when the service compiles with a
  different expression dialect than the one vendored into this tree
* :meth:`SigmaRailApiClient.source_fields` — the resolved field registry, for local
  spec validation

Stdlib-only (``urllib``): this module ships inside the LEAN container.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DebugLog = Callable[[str], None] | None

#: The expression dialect the runtime was built against (SigmaRail Spec, `C-VERA-EXPR-V1`).
EXPECTED_DIALECT_ID = "C-VERA-EXPR-V1"


class SigmaRailApiError(RuntimeError):
    """A Vera query service call failed and was not retried."""

    def __init__(self, operation: str, detail: str, status: int | None = None):
        self.operation = operation
        self.detail = detail
        self.status = status
        suffix = f" (HTTP {status})" if status is not None else ""
        super().__init__(f"SigmaRailApiClient[{operation}]{suffix}: {detail}")


class SigmaRailApiClient:
    """POST/GET JSON against the Vera query service; raise on failure."""

    def __init__(self, base_url: str, api_key: str | None = None, debug_log: DebugLog = None):
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._debug_log = debug_log

    def _log(self, msg: str) -> None:
        if self._debug_log:
            self._debug_log(msg)

    def _request(
        self,
        operation: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["X-API-Key"] = self._key
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # pragma: no cover - body already consumed
                pass
            self._log(f"SigmaRailApiClient[{operation}]: HTTP {exc.code} {detail}")
            raise SigmaRailApiError(operation, detail or exc.reason or "http error", status=exc.code) from exc
        except Exception as exc:
            self._log(f"SigmaRailApiClient[{operation}]: {exc}")
            raise SigmaRailApiError(operation, str(exc)) from exc
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            self._log(f"SigmaRailApiClient[{operation}]: invalid JSON ({exc})")
            raise SigmaRailApiError(operation, f"invalid JSON response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SigmaRailApiError(operation, f"expected a JSON object, got {type(parsed).__name__}")
        return parsed

    # --- execution ---------------------------------------------------------

    def screen_preview(self, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        return self._request("screen_preview", "POST", "/v1/screen/preview", payload, timeout)

    def universe_run(self, payload: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
        return self._request("universe_run", "POST", "/v1/universe/run", payload, timeout)

    def strategy_spec(self, ir_id: str, timeout: float = 30.0) -> dict[str, Any]:
        """Fetch a saved strategy document from SigmaRail Studio."""
        from urllib.parse import quote

        return self._request(
            "strategy_spec", "GET", f"/api/backtests/specs/{quote(ir_id, safe='')}", None, timeout
        )

    # --- compatibility (C-API-SURFACE-V1) ----------------------------------

    def meta(self, timeout: float = 10.0) -> dict[str, Any]:
        """Dialect identity + ``registry_digest`` for this service instance."""
        return self._request("meta", "GET", "/v1/meta", None, timeout)

    def source_fields(self, source: str, timeout: float = 30.0) -> dict[str, Any]:
        """Resolved field registry for one L7 source (validates specs locally)."""
        return self._request(
            "source_fields", "GET", f"/v1/schema/sources/{source}/fields", None, timeout
        )

    def require_dialect(
        self, meta: dict[str, Any] | None = None, timeout: float = 10.0
    ) -> dict[str, Any]:
        """Return ``/v1/meta``, raising if the service dialect is not the vendored one."""
        payload = meta if isinstance(meta, dict) else self.meta(timeout=timeout)
        dialect = payload.get("dialect")
        got = dialect.get("id") if isinstance(dialect, dict) else None
        if got != EXPECTED_DIALECT_ID:
            raise SigmaRailApiError(
                "meta",
                f"dialect mismatch: service={got!r} expected={EXPECTED_DIALECT_ID!r}",
            )
        return payload


def resolve_sigmarail_api_service_url(algorithm) -> str | None:
    # Prefer QC parameters so it can be set per job, with env fallback.
    if algorithm:
        u = algorithm.GetParameter("sigmarail-api-url") or ""
        if u.strip():
            return u.strip()
    u2 = os.environ.get("SIGMARAIL_API_URL", "").strip()
    return u2 or None


def resolve_sigmarail_api_service_api_key(algorithm) -> str | None:
    if algorithm:
        k = algorithm.GetParameter("sigmarail-api-api-key") or ""
        if k.strip():
            return k.strip()
    k2 = os.environ.get("SIGMARAIL_API_KEY", "").strip()
    return k2 or None
