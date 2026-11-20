"""Shared HMAC token format and validation for Vera download URLs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


def issue_download_token(
    *,
    secret: bytes,
    audience: str,
    resource_id: str,
    principal_id: str,
    ttl_seconds: int,
    now: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create a signed token with common audience, resource, owner and expiry claims."""
    if len(secret) < 32:
        raise ValueError("download signing secret must contain at least 32 bytes")
    issued_at = int(time.time()) if now is None else int(now)
    claims = {
        "aud": audience,
        "exp": issued_at + ttl_seconds,
        "iat": issued_at,
        "jti": secrets.token_urlsafe(18),
        "principal_id": principal_id,
        "resource_id": resource_id,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest()
    signature_part = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded}.{signature_part}", claims


def verify_download_token(
    token: str | None,
    *,
    secret: bytes,
    audience: str,
    resource_id: str,
    max_ttl_seconds: int,
    now: int | None = None,
) -> dict[str, Any] | None:
    """Verify the common token envelope and its audience/resource/time bounds."""
    if len(secret) < 32 or not token or len(token) > 8192:
        return None
    try:
        encoded, signature_part = token.split(".", 1)
        supplied_signature = base64.urlsafe_b64decode(
            signature_part + "=" * (-len(signature_part) % 4)
        )
        expected_signature = hmac.new(
            secret, encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        claims = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        current_time = int(time.time()) if now is None else int(now)
        if (
            not isinstance(claims, dict)
            or claims.get("aud") != audience
            or claims.get("resource_id") != resource_id
            or type(claims.get("iat")) is not int
            or type(claims.get("exp")) is not int
            or claims["iat"] > current_time + 30
            or claims["exp"] <= current_time
            or claims["exp"] - claims["iat"] > max_ttl_seconds
            or not isinstance(claims.get("principal_id"), str)
            or not isinstance(claims.get("jti"), str)
        ):
            return None
        return claims
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None
