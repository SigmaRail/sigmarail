"""Light API-key gate for SigmaRail MCP streamable-http (Claude remote connector).

Accepts either:
- ``Authorization: Bearer <key>`` (Claude custom connector request headers)
- ``X-Api-Key: <key>`` (parity with ``SIGMARAIL_API_KEY`` on the query service)

Env: ``SIGMARAIL_MCP_API_KEY`` (required for streamable-http unless
``SIGMARAIL_MCP_ALLOW_INSECURE=1`` for local debugging only).
"""

from __future__ import annotations

import os
import re
import secrets
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/health", "/health/"})
SIGNED_EXPORT_PATH = re.compile(r"^/api/research/exports/[0-9a-f]{32}/download$")


def resolve_mcp_api_key() -> str:
    return os.environ.get("SIGMARAIL_MCP_API_KEY", "").strip()


def allow_insecure_http() -> bool:
    return os.environ.get("SIGMARAIL_MCP_ALLOW_INSECURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def extract_api_key(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Pull bearer or X-Api-Key from raw ASGI header list."""
    auth_value: str | None = None
    x_api_key: str | None = None
    for raw_name, raw_value in headers:
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1").strip()
        if name == "authorization":
            auth_value = value
        elif name == "x-api-key":
            x_api_key = value

    if auth_value and auth_value.lower().startswith("bearer "):
        token = auth_value[7:].strip()
        if token:
            return token
    if x_api_key:
        return x_api_key
    return None


def api_key_matches(provided: str | None, required: str) -> bool:
    if not provided or not required:
        return False
    if len(provided) != len(required):
        return False
    return secrets.compare_digest(provided, required)


class ApiKeyAuthMiddleware:
    """ASGI middleware: require ``SIGMARAIL_MCP_API_KEY`` on all non-public HTTP paths."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        if not api_key:
            raise ValueError("api_key must be non-empty")
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        # This exact GET route is protected by the export manager's signed,
        # owner-bound, single-use token. Keep every other export path/method
        # behind the MCP API-key gate.
        if path in PUBLIC_PATHS or (
            scope.get("method") == "GET" and SIGNED_EXPORT_PATH.fullmatch(path)
        ):
            await self.app(scope, receive, send)
            return

        provided = extract_api_key(list(scope.get("headers") or []))
        if not api_key_matches(provided, self.api_key):
            await _send_unauthorized(send)
            return

        await self.app(scope, receive, send)


async def _send_unauthorized(send: Send) -> None:
    body = b'{"error":"unauthorized","code":"invalid_api_key"}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="vera-mcp"'),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def wrap_app_with_api_key(app: ASGIApp, api_key: str | None = None) -> ASGIApp:
    """Wrap Starlette/ASGI app when a key is configured; else return app unchanged."""
    key = (api_key if api_key is not None else resolve_mcp_api_key()).strip()
    if not key:
        return app
    return ApiKeyAuthMiddleware(app, key)


def require_http_api_key_or_exit() -> str | None:
    """For streamable-http startup: return key, None if insecure allowed, else exit."""
    key = resolve_mcp_api_key()
    if key:
        return key
    if allow_insecure_http():
        return None
    raise SystemExit(
        "SIGMARAIL_MCP_API_KEY is required for MCP_TRANSPORT=streamable-http "
        "(set SIGMARAIL_MCP_ALLOW_INSECURE=1 only for local unauthenticated debugging)."
    )


def transport_security_for_http() -> Any:
    """DNS-rebinding settings for tunnel/public Host headers.

    When ``MCP_ALLOWED_HOSTS`` is set (comma-separated), validate Host against
    that list plus localhost. Otherwise disable Host checks — API key is the gate.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    raw = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    for local in ("127.0.0.1:*", "localhost:*", "[::1]:*"):
        if local not in hosts:
            hosts.append(local)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[],
    )
