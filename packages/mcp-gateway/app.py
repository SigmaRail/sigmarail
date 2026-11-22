"""OAuth front door for SigmaRail and the existing shared MCP routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from urllib.parse import urlencode, urlsplit

import httpx

IDP = os.environ.get("SIGMARAIL_MCP_IDP_ISSUER", "").rstrip("/")
RESOURCE = os.environ.get("SIGMARAIL_MCP_RESOURCE", "").rstrip("/")
UPSTREAM = os.environ.get("SIGMARAIL_MCP_UPSTREAM", "http://backend:80/api/ai-assistant/chatgpt/mcp/")
LEGACY = os.environ.get("LEGACY_MCP_GATEWAY", "http://host.docker.internal:8002").rstrip("/")
INTROSPECTION_URL = f"{IDP}/introspect"
USERINFO_URL = f"{IDP}/userinfo"
INTROSPECTION_CLIENT_ID = os.environ.get("SIGMARAIL_MCP_INTROSPECTION_CLIENT_ID", "")
INTROSPECTION_CLIENT_SECRET = os.environ.get("SIGMARAIL_MCP_INTROSPECTION_CLIENT_SECRET", "")
IDENTITY_HMAC_SECRET = os.environ.get("SIGMARAIL_MCP_IDENTITY_HMAC_SECRET", "")
MCP_PATH = "/sigmarail/mcp"
PROTECTED_RESOURCE_METADATA = f"/.well-known/oauth-protected-resource{MCP_PATH}"
DCR_PATH = "/register"
DCR_MAX_BODY_BYTES = 16 * 1024
DCR_ALLOWED_GRANTS = {"authorization_code", "refresh_token"}
DCR_ALLOWED_SCOPES = {"openid", "profile", "email"}
DCR_ALLOWED_AUTH_METHODS = {"client_secret_basic", "client_secret_post", "none"}
CHATGPT_CALLBACK_PATHS = (
    re.compile(r"^/connector/oauth/[A-Za-z0-9_-]{1,128}$"),
    re.compile(r"^/connector_platform_oauth_redirect$"),
)
logger = logging.getLogger(__name__)
HOP_BY_HOP = {
    b"connection", b"keep-alive", b"proxy-authenticate", b"proxy-authorization",
    b"te", b"trailer", b"transfer-encoding", b"upgrade",
}


def _json(status: int, payload: dict, headers: list[tuple[bytes, bytes]] | None = None):
    body = json.dumps(payload, separators=(",", ":")).encode()
    result = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if headers:
        result.extend(headers)
    return status, result, body


async def _send(send, status: int, headers: list[tuple[bytes, bytes]], body: bytes):
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _body(receive, max_bytes: int | None = None) -> bytes:
    parts = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b""
        if message["type"] == "http.request":
            part = message.get("body", b"")
            total += len(part)
            if max_bytes is not None and total > max_bytes:
                raise OverflowError("request body exceeds limit")
            parts.append(part)
            if not message.get("more_body", False):
                return b"".join(parts)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _identity_assertion(userinfo: dict, token_info: dict) -> str:
    subject = userinfo.get("sub")
    email = userinfo.get("email")
    # Keep failures diagnosable without writing identity values, OAuth tokens,
    # or assertion contents to logs.
    if not isinstance(subject, str) or not subject or len(subject) > 512:
        raise ValueError("identity_subject_invalid")
    introspection_subject = token_info.get("sub")
    # tsidp has a small but important claim-format difference: its OIDC
    # subject (and userinfo `sub`) is `userid:<id>`, while RFC 7662 introspection
    # emits the same Tailscale user ID as a bare decimal string. Verify the
    # exact canonical pair rather than comparing those two representations
    # literally. Keep accepting exact matches for other standards-compliant
    # issuers.
    if subject != introspection_subject and subject != f"userid:{introspection_subject}":
        raise ValueError("identity_subject_mismatch")
    if not isinstance(email, str) or not email.strip() or len(email) > 255:
        raise ValueError("identity_email_missing_or_invalid")
    # Tailscale tsidp authenticates the principal from the tailnet but does
    # not emit email_verified by default. Trust the authenticated issuer and
    # immutable subject; AppTension only links an initial identity to an
    # existing active, confirmed account with the matching email.
    if userinfo.get("email_verified") is False:
        raise ValueError("identity_email_claim_unverified")
    payload = {
        "iss": IDP,
        "aud": RESOURCE,
        "sub": subject,
        "email": email.strip(),
        "identity_verified": True,
        "exp": int(time.time()) + 120,
    }
    encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(IDENTITY_HMAC_SECRET.encode(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


async def _verified_identity(access_token: str) -> str | None:
    if not all((IDP, RESOURCE, INTROSPECTION_CLIENT_ID, INTROSPECTION_CLIENT_SECRET, IDENTITY_HMAC_SECRET)):
        raise RuntimeError("gateway OAuth and identity settings are incomplete")
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        introspection = await client.post(
            INTROSPECTION_URL,
            content=urlencode({"token": access_token}),
            headers={"content-type": "application/x-www-form-urlencoded"},
            auth=(INTROSPECTION_CLIENT_ID, INTROSPECTION_CLIENT_SECRET),
        )
        if introspection.status_code != 200:
            return None
        token_info = introspection.json()
        audiences = token_info.get("aud", [])
        if isinstance(audiences, str):
            audiences = [audiences]
        if (
            token_info.get("active") is not True
            or token_info.get("iss") != IDP
            or not any(isinstance(aud, str) and aud.rstrip("/") == RESOURCE for aud in audiences)
            or not isinstance(token_info.get("sub"), str)
        ):
            return None
        profile = await client.get(USERINFO_URL, headers={"authorization": f"Bearer {access_token}"})
        if profile.status_code != 200:
            return None
        return _identity_assertion(profile.json(), token_info)


async def _proxy(
    scope,
    receive,
    send,
    target: str,
    identity: str | None = None,
    body_override: bytes | None = None,
):
    body = await _body(receive) if body_override is None else body_override
    headers = []
    for key, value in scope.get("headers", []):
        if key.lower() in HOP_BY_HOP or key.lower() in {b"host", b"authorization", b"x-mcp-gateway-identity", b"tailscale-funnel-request"}:
            continue
        headers.append((key.decode("latin-1"), value.decode("latin-1")))
    if identity:
        headers.append(("X-MCP-Gateway-Identity", identity))
    query = scope.get("query_string", b"").decode("latin-1")
    path = scope.get("path", "/")
    if target == UPSTREAM:
        url = target
    else:
        url = f"{target}{path}" + (f"?{query}" if query else "")
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        request = client.build_request(
            scope.get("method", "GET"), url, headers=headers, content=body or None
        )
        response = await client.send(request, stream=True)
        out_headers = [(k.lower(), v) for k, v in response.headers.raw if k.lower() not in HOP_BY_HOP]
        await send({"type": "http.response.start", "status": response.status_code, "headers": out_headers})
        try:
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        finally:
            await response.aclose()
        await send({"type": "http.response.body", "body": b"", "more_body": False})


def _chatgpt_dcr_rejection(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "body_not_object"
    redirect_uris = payload.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not 1 <= len(redirect_uris) <= 4:
        return "redirect_uris"
    for uri in redirect_uris:
        if not isinstance(uri, str) or len(uri) > 512:
            return "redirect_uri_type_or_length"
        try:
            parsed = urlsplit(uri)
            port = parsed.port
        except ValueError:
            return "redirect_uri_invalid"
        if (
            parsed.scheme != "https"
            or parsed.hostname != "chatgpt.com"
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not any(pattern.fullmatch(parsed.path) for pattern in CHATGPT_CALLBACK_PATHS)
        ):
            return "redirect_uri_not_chatgpt"
    grants = payload.get("grant_types", ["authorization_code"])
    if (
        not isinstance(grants, list)
        or not grants
        or any(not isinstance(grant, str) for grant in grants)
        or not set(grants).issubset(DCR_ALLOWED_GRANTS)
    ):
        return "grant_types"
    if "authorization_code" not in grants:
        return "authorization_code_required"
    responses = payload.get("response_types", ["code"])
    if not isinstance(responses, list) or any(not isinstance(value, str) for value in responses) or responses != ["code"]:
        return "response_types"
    auth_method = payload.get("token_endpoint_auth_method", "client_secret_basic")
    if not isinstance(auth_method, str) or auth_method not in DCR_ALLOWED_AUTH_METHODS:
        return "token_endpoint_auth_method"
    scope = payload.get("scope", "")
    if (
        not isinstance(scope, str)
        or len(scope) > 256
        or not set(scope.split()).issubset(DCR_ALLOWED_SCOPES)
    ):
        return "scope"
    return None


async def app(scope, receive, send):
    if scope["type"] != "http":
        await _send(send, 404, [(b"content-length", b"0")], b"")
        return
    path = scope.get("path", "/")
    method = scope.get("method", "GET").upper()
    if path in {"/health", "/health/"}:
        status, headers, body = _json(200, {"ok": True, "service": "sigmarail-mcp-gateway"})
        await _send(send, status, headers, body)
        return
    # tsidp deliberately blocks DCR requests arriving through its Funnel. Relay
    # registration from this public gateway over the tailnet, and constrain it
    # to ChatGPT callback URLs and the OAuth methods/scopes advertised by tsidp.
    if path == DCR_PATH:
        if method == "OPTIONS":
            headers = [
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"POST, OPTIONS"),
                (b"access-control-allow-headers", b"*"),
                (b"access-control-max-age", b"600"),
                (b"content-length", b"0"),
            ]
            await _send(send, 204, headers, b"")
            return
        if method != "POST":
            status, headers, body = _json(
                405, {"error": "method_not_allowed"}, [(b"allow", b"POST, OPTIONS")]
            )
            await _send(send, status, headers, body)
            return
        try:
            request_body = await _body(receive, max_bytes=DCR_MAX_BODY_BYTES)
        except OverflowError:
            status, headers, body = _json(413, {"error": "registration_request_too_large"})
            await _send(send, status, headers, body)
            return
        try:
            registration = json.loads(request_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            registration = None
        rejection = _chatgpt_dcr_rejection(registration)
        if rejection:
            logger.warning("Rejected OAuth DCR request: %s", rejection)
            status, headers, body = _json(400, {"error": "unsupported_client_metadata"})
            await _send(send, status, headers, body)
            return
        if not IDP:
            status, headers, body = _json(503, {"error": "identity_provider_unavailable"})
            await _send(send, status, headers, body)
            return
        # ChatGPT's DCR client currently asks for the public-client method
        # "none", while tsidp issues confidential clients and only advertises
        # client_secret_basic/client_secret_post. Let tsidp create its normal
        # secret-backed client and return that registration response unchanged;
        # ChatGPT then receives the actual auth method and generated secret.
        if registration.get("token_endpoint_auth_method", "client_secret_basic") == "none":
            registration["token_endpoint_auth_method"] = "client_secret_post"
            request_body = json.dumps(registration, separators=(",", ":")).encode()
        try:
            await _proxy(scope, receive, send, IDP, body_override=request_body)
        except httpx.HTTPError:
            status, headers, body = _json(502, {"error": "identity_provider_unavailable"})
            await _send(send, status, headers, body)
        return
    # Tailscale Funnel's --set-path mounts a public prefix and strips that
    # prefix before forwarding to this service. Accept the rewritten root for
    # the exact OAuth metadata route as well as direct local requests.
    if path == PROTECTED_RESOURCE_METADATA or (path == "/" and method == "GET"):
        status, headers, body = _json(200, {
            "resource": RESOURCE,
            "authorization_servers": [IDP],
            "scopes_supported": ["openid", "profile", "email"],
            "bearer_methods_supported": ["header"],
        })
        await _send(send, status, headers, body)
        return
    # The public /sigmarail/mcp handler is rewritten to / by Funnel. The
    # literal path is still accepted for local gateway smoke tests.
    if path == MCP_PATH or (path == "/" and method == "POST"):
        if method != "POST":
            status, headers, body = _json(405, {"error": "method_not_allowed"}, [(b"allow", b"POST")])
            await _send(send, status, headers, body)
            return
        auth = next(
            (value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"authorization"),
            "",
        )
        if not auth.lower().startswith("bearer "):
            status, headers, body = _json(401, {"error": "unauthorized"}, [
                (b"www-authenticate", f'Bearer resource_metadata="https://turnip.tail850cb1.ts.net{PROTECTED_RESOURCE_METADATA}"'.encode())
            ])
            await _send(send, status, headers, body)
            return
        try:
            identity = await _verified_identity(auth[7:].strip())
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            logger.error("MCP identity verification failed: %s: %s", type(exc).__name__, str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "upstream request failed")
            status, headers, body = _json(503, {"error": "identity_provider_unavailable"})
            await _send(send, status, headers, body)
            return
        if not identity:
            status, headers, body = _json(401, {"error": "invalid_token"}, [
                (b"www-authenticate", f'Bearer resource_metadata="https://turnip.tail850cb1.ts.net{PROTECTED_RESOURCE_METADATA}"'.encode())
            ])
            await _send(send, status, headers, body)
            return
        try:
            await _proxy(scope, receive, send, UPSTREAM, identity)
        except httpx.HTTPError:
            status, headers, body = _json(502, {"error": "sigmarail_mcp_upstream_unavailable"})
            await _send(send, status, headers, body)
        return
    if path == "/mcp" or path.startswith("/mcp/") or path == "/deepvue/mcp" or path.startswith("/deepvue/mcp/"):
        try:
            await _proxy(scope, receive, send, LEGACY)
        except httpx.HTTPError:
            status, headers, body = _json(502, {"error": "legacy_mcp_upstream_unavailable"})
            await _send(send, status, headers, body)
        return
    status, headers, body = _json(404, {"error": "not_found"})
    await _send(send, status, headers, body)


app = app
