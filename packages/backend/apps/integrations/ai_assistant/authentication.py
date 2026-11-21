"""Authentication for requests forwarded by the trusted Tailscale MCP gateway."""

import base64
import hashlib
import hmac
import json
import time

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.users.models import User
from .models import MCPUserIdentity


def _decode_segment(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


class TailscaleMCPGatewayAuthentication(BaseAuthentication):
    """Validate a short-lived HMAC assertion created after gateway token introspection."""

    header_name = "HTTP_X_MCP_GATEWAY_IDENTITY"

    def authenticate(self, request):
        assertion = request.META.get(self.header_name)
        if not assertion:
            return None

        secret = getattr(settings, "CHATGPT_MCP_GATEWAY_HMAC_SECRET", "")
        if not secret:
            raise AuthenticationFailed("MCP gateway identity is not configured")
        if len(assertion) > 8192:
            raise AuthenticationFailed("Invalid MCP gateway identity")

        try:
            encoded_payload, encoded_signature = assertion.split(".", 1)
            signature = _decode_segment(encoded_signature)
            payload = json.loads(_decode_segment(encoded_payload))
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise AuthenticationFailed("Invalid MCP gateway identity")

        expected = hmac.new(
            secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(signature, expected):
            raise AuthenticationFailed("Invalid MCP gateway signature")

        now = int(time.time())
        expected_issuer = getattr(settings, "CHATGPT_MCP_IDP_ISSUER", "")
        expected_audience = getattr(settings, "CHATGPT_MCP_RESOURCE_AUDIENCE", "")
        if (
            not isinstance(payload, dict)
            or payload.get("iss") != expected_issuer
            or payload.get("aud") != expected_audience
            or not isinstance(payload.get("sub"), str)
            or not payload["sub"]
            or len(payload["sub"]) > 512
            or payload.get("identity_verified") is not True
            or not isinstance(payload.get("email"), str)
            or not payload["email"].strip()
            or len(payload["email"]) > 255
            or not isinstance(payload.get("exp"), int)
            or payload["exp"] <= now
            or payload["exp"] > now + 3600
        ):
            raise AuthenticationFailed("MCP gateway identity is expired or has invalid claims")

        identity = MCPUserIdentity.objects.select_related("user").filter(
            issuer=payload["iss"], subject=payload["sub"]
        ).first()
        if identity is None:
            user = User.objects.filter(
                email__iexact=payload["email"].strip(), is_active=True, is_confirmed=True
            ).first()
            if user is None:
                raise AuthenticationFailed("No confirmed AppTension user matches this identity")
            identity, _created = MCPUserIdentity.objects.get_or_create(
                issuer=payload["iss"],
                subject=payload["sub"],
                defaults={"email": payload["email"].strip(), "user": user},
            )

        if not identity.user.is_active or not identity.user.is_confirmed:
            raise AuthenticationFailed("The linked AppTension user is inactive or unconfirmed")
        identity.save(update_fields=["last_seen_at"])
        return identity.user, {"gateway": True, "issuer": payload["iss"], "subject": payload["sub"]}

