"""Uniform DRF envelope: ``{data, meta}`` on success, ``{error: {code, message}}`` on error.

Opt-in via ``ENVELOPE_JSON=1`` — the rollout requires the SPA + API tests to consume the
new shape, so it stays off by default (no 255-site rewrite; the views are unchanged).
"""
from __future__ import annotations

from typing import Any

from rest_framework.renderers import JSONRenderer
from rest_framework.views import exception_handler as drf_exception_handler

_STATUS_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


def envelope_exception_handler(exc: Exception, context: Any) -> Any:
    """Convert DRF exceptions into ``{error: {code, message}}``."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "detail" in data:
        message = str(data["detail"])
    else:
        message = str(data)
    response.data = {
        "error": {"code": _STATUS_CODE.get(response.status_code, "error"), "message": message}
    }
    return response


class EnvelopeJSONRenderer(JSONRenderer):
    """Wrap successful (2xx/3xx) responses into ``{data, meta:{status}}``."""

    def render(self, data: Any, accepted_media_type: Any = None, renderer_context: Any = None) -> bytes:
        response = renderer_context.get("response") if renderer_context else None
        if response is not None and response.status_code < 400:
            data = {"data": data, "meta": {"status": response.status_code}}
        return super().render(data, accepted_media_type, renderer_context)
